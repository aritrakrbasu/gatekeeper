"""
Billing service for usage tracking and cost calculation.

This service handles:
- Storing LLM usage records from Phoenix traces
- Calculating billing cycle summaries
- Syncing usage data from Phoenix
- Providing billing data for the frontend
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from services import mongo_client
from config.arize_client import get_arize_client


# ============================================================================
# MongoDB Collections
# ============================================================================

async def ensure_indexes():
    """Create indexes for billing collections."""
    try:
        # billing_summaries indexes (NEW single-document approach)
        await mongo_client.create_index(
            "billing_summaries",
            [("user_id", 1)],
            unique=True
        )

        # Legacy collections (kept for migration compatibility)
        await mongo_client.create_index(
            "llm_usage_records",
            [("user_id", 1), ("trace_id", 1)],
            unique=True
        )
        await mongo_client.create_index(
            "llm_usage_records",
            [("user_id", 1), ("billing_cycle", 1)]
        )
        await mongo_client.create_index(
            "llm_usage_records",
            [("timestamp", -1)]
        )

        await mongo_client.create_index(
            "billing_cycles",
            [("user_id", 1), ("cycle", 1)],
            unique=True
        )

        print("[OK] Billing collection indexes created successfully")
    except Exception as e:
        print(f"[WARN] Failed to create billing indexes: {e}")


# ============================================================================
# NEW: Single-Document Billing Architecture
# ============================================================================

async def _get_or_create_billing_summary(user_id: str) -> Dict:
    """Get existing billing summary document or create new one."""
    doc = await mongo_client.find_one("billing_summaries", {"user_id": user_id})

    if not doc:
        # Create new billing summary document using upsert to handle race conditions
        now = datetime.utcnow()
        new_doc = {
            "_id": f"billing:{user_id}",
            "user_id": user_id,
            "sync_state": {
                "last_sync_at": None,
                "last_trace_id": None
            },
            "months": {},
            "created_at": now,
            "updated_at": now
        }

        # Try to insert, but if it already exists (race condition), just fetch it
        try:
            await mongo_client.insert_one("billing_summaries", new_doc)
            print(f"[INFO] Created new billing summary for user: {user_id}")
            doc = new_doc
        except Exception as e:
            # If we get a duplicate key error, the document was created by another request
            # Just fetch it again
            if "duplicate key" in str(e).lower() or "E11000" in str(e):
                print(f"[INFO] Billing summary already exists for user: {user_id}, fetching existing")
                doc = await mongo_client.find_one("billing_summaries", {"user_id": user_id})
                if doc:
                    return doc
                # If still not found, there's a bigger issue
                raise Exception(f"Failed to create or fetch billing summary for user: {user_id}")
            else:
                raise

    return doc


async def _aggregate_trace_to_monthly_data(trace: Dict, user_id: str, monthly_data: Dict):
    """
    Aggregate a single trace into the monthly data structure (in-memory).

    This builds up the aggregated data structure in memory before the
    final single atomic write to MongoDB.
    """
    attributes = trace.get("attributes", {})

    # Extract trace data
    trace_id = trace.get("trace_id", "")
    input_tokens = attributes.get("llm_input_tokens", 0)
    output_tokens = attributes.get("llm_output_tokens", 0)
    total_tokens = attributes.get("llm_total_tokens", 0) or (input_tokens + output_tokens)
    model_name = attributes.get("llm_model_name", "gemini-3.5-flash")

    # Skip if no tokens
    if total_tokens == 0:
        return

    # Get cost from trace (required)
    estimated_cost = attributes.get("llm_total_cost", 0)
    if not estimated_cost or estimated_cost == 0:
        print(f"[WARN] Trace {trace_id[:8]}... has no cost information, skipping")
        return  # Skip traces without cost information

    # Get trace timestamp for day grouping
    # If no timestamp on trace, use current time
    trace_time = attributes.get("timestamp")
    if not trace_time:
        print(f"[WARN] Trace {trace_id[:8]}... has no timestamp, using current time")
        trace_time = datetime.utcnow()
    elif isinstance(trace_time, str):
        try:
            # Handle ISO format with or without timezone
            if trace_time.endswith('Z'):
                trace_time = datetime.fromisoformat(trace_time.replace('Z', '+00:00'))
            else:
                trace_time = datetime.fromisoformat(trace_time)
            # Convert to UTC if timezone aware
            if trace_time.tzinfo is not None:
                trace_time = trace_time.replace(tzinfo=None)
        except ValueError as e:
            print(f"[WARN] Failed to parse timestamp '{trace_time}': {e}, using current time")
            trace_time = datetime.utcnow()
    elif isinstance(trace_time, datetime):
        # Convert to UTC naive datetime
        if trace_time.tzinfo is not None:
            trace_time = trace_time.replace(tzinfo=None)
    else:
        print(f"[WARN] Unknown timestamp type {type(trace_time)}, using current time")
        trace_time = datetime.utcnow()

    month_key = trace_time.strftime("%Y-%m")
    day_key = trace_time.strftime("%d")  # Day as "01", "02", etc.

    # Initialize month if not exists
    if month_key not in monthly_data:
        monthly_data[month_key] = {
            "summary": {
                "total_tokens": 0,
                "total_cost": 0.0,
                "mrs_count": 0
            },
            "models": {},
            "days": {}
        }

    month = monthly_data[month_key]

    # Update summary
    month["summary"]["total_tokens"] += total_tokens
    month["summary"]["total_cost"] += estimated_cost

    # Track MRs
    mr_id = attributes.get("mr_id")
    if mr_id:
        if "mr_ids" not in month:
            month["mr_ids"] = []
        if mr_id not in month["mr_ids"]:
            month["mr_ids"].append(mr_id)
            month["summary"]["mrs_count"] += 1

    # Update model breakdown
    if model_name not in month["models"]:
        month["models"][model_name] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost": 0.0
        }

    month["models"][model_name]["input_tokens"] += input_tokens
    month["models"][model_name]["output_tokens"] += output_tokens
    month["models"][model_name]["total_tokens"] += total_tokens
    month["models"][model_name]["cost"] += estimated_cost

    # Update daily breakdown
    if day_key not in month["days"]:
        month["days"][day_key] = {
            "tokens": 0,
            "cost": 0.0,
            "mrs": 0,
            "mr_ids": []
        }

    month["days"][day_key]["tokens"] += total_tokens
    month["days"][day_key]["cost"] += estimated_cost

    if mr_id and mr_id not in month["days"][day_key]["mr_ids"]:
        month["days"][day_key]["mr_ids"].append(mr_id)
        month["days"][day_key]["mrs"] += 1


async def sync_user_billing_optimized(
    user_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    force_resync: bool = False
) -> Dict:
    """
    NEW: Optimized sync using single-document architecture.

    Uses adaptive time-window pagination to handle Arize's 500 span limit:
    - Starts with 6-hour windows
    - Shrinks to 3 hours if 500 limit is hit
    - Aggregates all data in memory
    - Single atomic write at end

    Args:
        user_id: User to sync
        start_date: Start of sync period (defaults to last sync or 24 hours ago)
        end_date: End of sync period (defaults to now)
        force_resync: If True, ignore last_sync checkpoint

    Returns:
        Sync result with statistics
    """
    try:
        print(f"[INFO] Starting optimized billing sync for user: {user_id}")

        client = await get_arize_client()
        if not client.is_connected():
            return {"success": False, "error": "Arize Cloud not connected"}

        # Get or create billing summary document
        billing_doc = await _get_or_create_billing_summary(user_id)

        # Determine sync window
        now = datetime.utcnow()
        end_date = end_date or now

        if force_resync or not billing_doc["sync_state"]["last_sync_at"]:
            # No previous sync or forced resync - default to 24 hours
            start_date = start_date or (now - timedelta(hours=24))
            print(f"[INFO] Force resync or first sync: syncing last 24 hours from {start_date}")
        else:
            # Resume from last sync
            start_date = billing_doc["sync_state"]["last_sync_at"]
            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                # Convert to UTC naive
                if start_date.tzinfo is not None:
                    start_date = start_date.replace(tzinfo=None)

            # If the last sync was very recent (less than 1 hour), sync last 24 hours instead
            # This ensures we catch any traces that might have been missed
            if (now - start_date).total_seconds() < 3600:
                print(f"[INFO] Last sync was very recent ({(now - start_date).total_seconds()/60:.1f} minutes ago), syncing last 24 hours instead")
                start_date = now - timedelta(hours=24)
            else:
                print(f"[INFO] Resuming from last sync at {start_date}")

        print(f"[INFO] Sync window: {start_date} to {end_date}")

        # Get existing months for deduplication BEFORE aggregation starts
        existing_months = billing_doc.get("months", {})

        # Initialize in-memory aggregation structure with existing MR data for deduplication
        monthly_aggregates = {}
        for month_key, month_data in existing_months.items():
            # Pre-populate with existing MR IDs and metrics so deduplication and aggregation work
            monthly_aggregates[month_key] = {
                "summary": month_data.get("summary", {
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "mrs_count": 0
                }),
                "models": month_data.get("models", {}).copy(),
                "mr_ids": month_data.get("mr_ids", []).copy(),
                "days": {
                    day_key: {
                        "tokens": day_data.get("tokens", 0),
                        "cost": day_data.get("cost", 0.0),
                        "mrs": day_data.get("mrs", 0),
                        "mr_ids": day_data.get("mr_ids", []).copy()
                    }
                    for day_key, day_data in month_data.get("days", {}).items()
                }
            }

        total_synced = 0
        total_skipped = 0
        last_trace_id = None

        # Adaptive time-window sync
        window_start = start_date
        window_size_hours = 6  # Start with 6-hour windows

        while window_start < end_date:
            window_end = min(window_start + timedelta(hours=window_size_hours), end_date)

            # Calculate hours for API call
            hours_ago = int((now - window_start).total_seconds() / 3600)

            print(f"[INFO] Fetching traces: {window_start} to {window_end} ({window_size_hours}h window)")

            # Fetch traces from Arize
            traces = await client.get_recent_traces(
                limit=500,
                hours_ago=hours_ago,
                user_id=user_id
            )

            # Check if we hit the 500 limit
            if len(traces) == 500:
                print(f"[WARN] Hit 500 span limit, shrinking window to 3 hours")
                window_size_hours = 3
                continue  # Retry with smaller window

            # Filter traces to current window and aggregate
            window_synced = 0
            for trace in traces:
                # Check if trace belongs to current user
                attributes = trace.get("attributes", {})
                trace_user_id = attributes.get("user_id") or attributes.get("user.id")

                if trace_user_id and str(trace_user_id) != str(user_id):
                    total_skipped += 1
                    continue

                # Aggregate this trace
                await _aggregate_trace_to_monthly_data(trace, user_id, monthly_aggregates)
                window_synced += 1
                total_synced += 1

                # Track last trace ID
                trace_id = trace.get("trace_id")
                if trace_id:
                    last_trace_id = trace_id

            print(f"[INFO] Window synced: {window_synced} traces")

            # Move to next window
            window_start = window_end

            # Reset window size for next iteration (if we didn't hit limit)
            if window_synced < 400:  # Safety margin
                window_size_hours = 6

        # Merge aggregated data into existing monthly data
        for month_key, month_data in monthly_aggregates.items():
            # Merge with existing month data
            if month_key in existing_months:
                existing = existing_months[month_key]
                prev_tokens = existing["summary"]["total_tokens"]
                prev_cost = existing["summary"]["total_cost"]

                # Initialize mr_ids if not present (backward compatibility)
                if "mr_ids" not in existing:
                    existing["mr_ids"] = []

                # Merge mr_ids at monthly level
                new_mr_ids = [mr_id for mr_id in month_data.get("mr_ids", [])
                              if mr_id not in existing["mr_ids"]]
                existing["mr_ids"].extend(new_mr_ids)
                # Update mrs_count to only count NEW MRs (deduplication)
                existing["summary"]["mrs_count"] += len(new_mr_ids)

                # Only add tokens/cost if there were new traces in this month
                if "summary" in month_data:
                    existing["summary"]["total_tokens"] += month_data["summary"]["total_tokens"]
                    existing["summary"]["total_cost"] += month_data["summary"]["total_cost"]

                    # Merge models
                    for model, stats in month_data.get("models", {}).items():
                        if model not in existing["models"]:
                            existing["models"][model] = stats.copy()
                        else:
                            existing["models"][model]["input_tokens"] += stats["input_tokens"]
                            existing["models"][model]["output_tokens"] += stats["output_tokens"]
                            existing["models"][model]["total_tokens"] += stats["total_tokens"]
                            existing["models"][model]["cost"] += stats["cost"]

                # Merge days
                for day, day_stats in month_data.get("days", {}).items():
                    # Skip if day_stats only has mr_ids (pre-populated, no new traces)
                    if "tokens" not in day_stats:
                        continue

                    if day not in existing["days"]:
                        # New day - copy directly (mr_ids already included)
                        existing["days"][day] = day_stats.copy()
                    else:
                        # Existing day - merge with deduplication
                        existing_day = existing["days"][day]
                        # Initialize mr_ids if not present (backward compatibility)
                        if "mr_ids" not in existing_day:
                            existing_day["mr_ids"] = []

                        # Merge mr_ids at daily level
                        new_day_mr_ids = [mr_id for mr_id in day_stats.get("mr_ids", [])
                                          if mr_id not in existing_day["mr_ids"]]
                        existing_day["mr_ids"].extend(new_day_mr_ids)
                        # Update mrs to only count NEW MRs (deduplication)
                        existing_day["mrs"] += len(new_day_mr_ids)

                        existing_day["tokens"] += day_stats["tokens"]
                        existing_day["cost"] += day_stats["cost"]
            else:
                # New month - only add if it has actual trace data (not just pre-populated)
                if "summary" in month_data and "models" in month_data:
                    existing_months[month_key] = month_data.copy()

        # Update billing summary document with single atomic write
        await mongo_client.update_one(
            "billing_summaries",
            {"user_id": user_id},
            {
                "$set": {
                    "months": existing_months,
                    "sync_state.last_sync_at": now.isoformat(),
                    "sync_state.last_trace_id": last_trace_id,
                    "updated_at": now.isoformat()
                }
            }
        )

        print(f"[INFO] Sync complete: {total_synced} synced, {total_skipped} skipped")

        return {
            "success": True,
            "synced": total_synced,
            "skipped": total_skipped,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "user_id": user_id,
            "months_updated": list(monthly_aggregates.keys())
        }

    except Exception as e:
        print(f"[ERROR] Failed optimized billing sync: {e}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Usage Record Storage
# ============================================================================

async def store_usage_record(
    user_id: str,
    trace_id: str,
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    estimated_cost: float,
    metadata: Optional[Dict] = None
) -> bool:
    """
    Store a single usage record.

    Args:
        user_id: User who made the request
        trace_id: Phoenix trace ID
        model_name: Model used (e.g., "gemini-3.5-flash")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        total_tokens: Total tokens
        estimated_cost: Calculated cost
        metadata: Optional metadata (mr_id, repository_id, etc.)

    Returns:
        True if stored successfully
    """
    try:
        timestamp = datetime.utcnow()
        billing_cycle = timestamp.strftime("%Y-%m")

        record = {
            "user_id": user_id,
            "trace_id": trace_id,
            "timestamp": timestamp,
            "billing_cycle": billing_cycle,
            "model_name": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated_cost": estimated_cost,
            "metadata": metadata or {},
            "synced_at": timestamp
        }

        # Use upsert to avoid duplicates
        await mongo_client.upsert_one(
            "llm_usage_records",
            {"user_id": user_id, "trace_id": trace_id},
            record
        )

        # Update billing cycle summary
        await _update_billing_cycle_summary(user_id, billing_cycle)

        return True

    except Exception as e:
        print(f"[ERROR] Failed to store usage record: {e}")
        return False


async def _update_billing_cycle_summary(user_id: str, cycle: str):
    """Update the billing cycle summary with latest data."""
    try:
        # Get all usage records for this cycle
        records = await mongo_client.find(
            "llm_usage_records",
            {"user_id": user_id, "billing_cycle": cycle}
        )

        if not records:
            return

        # Calculate totals
        total_tokens = sum(r.get("total_tokens", 0) for r in records)
        total_cost = sum(r.get("estimated_cost", 0) for r in records)

        # Count unique MRs
        mr_ids = set()
        for r in records:
            if r.get("metadata", {}).get("mr_id"):
                mr_ids.add(r["metadata"]["mr_id"])
        total_mrs = len(mr_ids)

        # Group by model
        model_breakdown = {}
        for r in records:
            model = r.get("model_name", "unknown")
            if model not in model_breakdown:
                model_breakdown[model] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "cost": 0
                }
            model_breakdown[model]["input_tokens"] += r.get("input_tokens", 0)
            model_breakdown[model]["output_tokens"] += r.get("output_tokens", 0)
            model_breakdown[model]["total_tokens"] += r.get("total_tokens", 0)
            model_breakdown[model]["cost"] += r.get("estimated_cost", 0)

        # Calculate cycle dates
        year, month = map(int, cycle.split("-"))
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)

        # Format model breakdown for storage
        model_breakdown_list = [
            {
                "model_name": model,
                "input_tokens": data["input_tokens"],
                "output_tokens": data["output_tokens"],
                "total_tokens": data["total_tokens"],
                "cost": data["cost"]
            }
            for model, data in model_breakdown.items()
        ]

        # Update or create billing cycle
        await mongo_client.upsert_one(
            "billing_cycles",
            {"user_id": user_id, "cycle": cycle},
            {
                "user_id": user_id,
                "cycle": cycle,
                "start_date": start_date,
                "end_date": end_date,
                "status": "active",
                "summary": {
                    "total_tokens": total_tokens,
                    "total_cost": total_cost,
                    "total_mrs_processed": total_mrs,
                    "model_breakdown": model_breakdown_list
                },
                "updated_at": datetime.utcnow(),
                "last_sync_at": datetime.utcnow()
            }
        )

    except Exception as e:
        print(f"[ERROR] Failed to update billing cycle summary: {e}")


# ============================================================================
# Sync from Arize Cloud
# ============================================================================

async def sync_user_usage_from_arize(
    user_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    force_resync: bool = False
) -> Dict:
    """
    Sync usage data from Arize Cloud traces for a user.

    Args:
        user_id: User to sync
        start_date: Start of sync period (defaults to beginning of current cycle)
        end_date: End of sync period (defaults to now)
        force_resync: If True, re-sync all data

    Returns:
        Sync result with statistics
    """
    try:
        print(f"[INFO] Starting sync for user_id: {user_id} (type: {type(user_id).__name__})")

        client = await get_arize_client()
        if not client.is_connected():
            return {"success": False, "error": "Arize Cloud not connected"}

        # Default to current billing cycle
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            # Start of current month
            start_date = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get traces for user
        hours_ago = int((end_date - start_date).total_seconds() / 3600)
        print(f"[INFO] Syncing usage for user {user_id} from last {hours_ago} hours...")

        # Get traces from Arize Cloud with user_id filter
        # Note: Arize API has a limit of 500 spans per request
        traces = await client.get_recent_traces(
            limit=500,
            hours_ago=hours_ago,
            user_id=user_id  # Filter by user_id at API level
        )

        print(f"[INFO] Retrieved {len(traces)} traces from Arize Cloud")

        synced = 0
        skipped = 0
        errors = 0

        # Collect all user_ids found in traces for debugging
        user_ids_found = set()

        for trace in traces:
            try:
                # Extract trace ID
                trace_id = trace.get("trace_id")
                if not trace_id:
                    skipped += 1
                    continue

                # Check if user_id matches in attributes
                attributes = trace.get("attributes", {})
                # Check for both user.id (OpenInference convention) and user_id (underscore)
                trace_user_id = attributes.get("user_id") or attributes.get("user.id")

                # Collect user_ids for debugging
                if trace_user_id:
                    user_ids_found.add(str(trace_user_id))

                # If trace has a user_id that doesn't match the requesting user, skip
                # This handles multi-tenant scenarios where traces have specific user ownership
                if trace_user_id and str(trace_user_id) != str(user_id):
                    skipped += 1
                    continue

                # If no user_id in trace, associate with requesting user
                # (This is a fallback for traces that don't have user_id set)
                # Continue processing - will use the requesting user_id below

                # Extract token usage from span attributes
                # Note: OpenTelemetry uses underscores, not dots
                input_tokens = attributes.get("llm_input_tokens", 0)
                output_tokens = attributes.get("llm_output_tokens", 0)
                model_name = attributes.get("llm_model_name", "gemini-3.5-flash")

                if not input_tokens and not output_tokens:
                    skipped += 1
                    continue

                # Calculate totals and cost
                total_tokens = input_tokens + output_tokens

                # Get cost from trace (required)
                estimated_cost = attributes.get("llm_total_cost", 0)
                if not estimated_cost or estimated_cost == 0:
                    print(f"[WARN] Trace {trace_id[:8]}... has no cost information, skipping")
                    skipped += 1
                    continue

                # Get metadata from trace
                metadata = {
                    "mr_id": attributes.get("mr_id"),
                    "repository_id": attributes.get("repository_id"),
                    "operation_type": attributes.get("operation_type", "review")
                }

                # Store record (upsert to avoid duplicates)
                success = await store_usage_record(
                    user_id=user_id,
                    trace_id=trace_id,
                    model_name=model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    estimated_cost=estimated_cost,
                    metadata=metadata
                )

                if success:
                    synced += 1
                else:
                    errors += 1

            except Exception as e:
                print(f"[ERROR] Failed to sync trace {trace.get('trace_id')}: {e}")
                errors += 1

        print(f"[INFO] Sync complete: {synced} synced, {skipped} skipped, {errors} errors")

        # Additional debugging info
        print(f"[INFO] Final stats - synced={synced}, skipped={skipped}, errors={errors}, total_traces={len(traces)}")
        if user_ids_found:
            print(f"[INFO] User IDs found in traces: {list(user_ids_found)}")
        else:
            print(f"[INFO] No user IDs found in traces - all traces without user context")

        return {
            "success": True,
            "synced": synced,
            "skipped": skipped,
            "errors": errors,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_traces": len(traces),
            "user_id": user_id
        }

    except Exception as e:
        print(f"[ERROR] Failed to sync user usage: {e}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}


# Backwards compatibility alias
async def sync_user_usage_from_phoenix(*args, **kwargs):
    """Alias for backwards compatibility. Use sync_user_usage_from_arize instead."""
    return await sync_user_usage_from_arize(*args, **kwargs)


# ============================================================================
# Get Billing Data for Frontend
# ============================================================================

async def get_daily_usage(user_id: str, days: int = 14) -> List[Dict]:
    """
    Get daily usage data for the last N days.

    Args:
        user_id: User to get data for
        days: Number of days to look back (default: 14)

    Returns:
        List of daily usage records with date, tokens, and cost
    """
    try:
        # Calculate date range
        now = datetime.utcnow()
        start_date = now - timedelta(days=days)

        # Get usage records within the date range
        records = await mongo_client.find(
            "llm_usage_records",
            {
                "user_id": user_id,
                "timestamp": {"$gte": start_date}
            }
        )

        # Group by date
        daily_data = {}
        for r in records:
            timestamp = r.get("timestamp")
            if timestamp:
                # Extract just the date part (no time)
                date_key = timestamp.strftime("%Y-%m-%d")
                if date_key not in daily_data:
                    daily_data[date_key] = {
                        "tokens": 0,
                        "cost": 0.0
                    }
                daily_data[date_key]["tokens"] += r.get("total_tokens", 0)
                daily_data[date_key]["cost"] += r.get("estimated_cost", 0.0)

        # Fill in missing days with zeros and create ordered list
        daily_usage = []
        for i in range(days):
            date = now - timedelta(days=days - 1 - i)
            date_str = date.strftime("%Y-%m-%d")
            daily_usage.append({
                "date": date.isoformat(),
                "tokens": daily_data.get(date_str, {}).get("tokens", 0),
                "cost": daily_data.get(date_str, {}).get("cost", 0.0)
            })

        return daily_usage

    except Exception as e:
        print(f"[ERROR] Failed to get daily usage: {e}")
        # Return empty daily usage on error
        now = datetime.utcnow()
        daily_usage = []
        for i in range(days):
            date = now - timedelta(days=days - 1 - i)
            daily_usage.append({
                "date": date.isoformat(),
                "tokens": 0,
                "cost": 0.0
            })
        return daily_usage


async def get_billing_dashboard_data(user_id: str) -> Dict:
    """
    Get billing data for the frontend dashboard.

    Args:
        user_id: User to get data for

    Returns:
        Billing dashboard data
    """
    try:
        # Get current billing cycle
        now = datetime.utcnow()
        current_cycle = now.strftime("%Y-%m")

        # Get current cycle data
        cycle_doc = await mongo_client.find_one(
            "billing_cycles",
            {"user_id": user_id, "cycle": current_cycle}
        )

        if not cycle_doc:
            # No data for current cycle
            daily_usage = await get_daily_usage(user_id)
            return {
                "current_cycle_start": now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(),
                "current_cycle_end": now.isoformat(),
                "total_tokens": 0,
                "total_mrs_processed": 0,
                "estimated_cost": 0.0,
                "model_usage": [],
                "daily_usage": daily_usage
            }

        summary = cycle_doc.get("summary", {})

        # Format model usage for frontend
        model_usage = []
        for model_data in summary.get("model_breakdown", []):
            model_usage.append({
                "model_name": model_data["model_name"],
                "input_tokens": model_data["input_tokens"],
                "output_tokens": model_data["output_tokens"],
                "total_tokens": model_data["total_tokens"],
                "estimated_cost": model_data["cost"]
            })

        # Get daily usage data
        daily_usage = await get_daily_usage(user_id)

        return {
            "current_cycle_start": cycle_doc["start_date"].isoformat(),
            "current_cycle_end": cycle_doc["end_date"].isoformat(),
            "total_tokens": summary.get("total_tokens", 0),
            "total_mrs_processed": summary.get("total_mrs_processed", 0),
            "estimated_cost": summary.get("total_cost", 0.0),
            "model_usage": model_usage,
            "daily_usage": daily_usage
        }

    except Exception as e:
        print(f"[ERROR] Failed to get billing dashboard data: {e}")
        raise


async def get_user_invoices(user_id: str, limit: int = 12) -> List[Dict]:
    """
    Get invoice history for a user.

    Args:
        user_id: User to get invoices for
        limit: Maximum number of invoices to return

    Returns:
        List of invoice data
    """
    try:
        # Get completed billing cycles
        cycles = await mongo_client.find(
            "billing_cycles",
            {"user_id": user_id, "status": "completed"},
            limit=limit
        )

        # Also include active cycles with some usage
        active_cycles = await mongo_client.find(
            "billing_cycles",
            {"user_id": user_id, "summary.total_cost": {"$gt": 0}},
            limit=limit
        )

        # Merge and dedupe by cycle
        all_cycles = {c["cycle"]: c for c in cycles + active_cycles}
        sorted_cycles = sorted(all_cycles.values(), key=lambda x: x["cycle"], reverse=True)[:limit]

        invoices = []
        for cycle in sorted_cycles:
            summary = cycle.get("summary", {})
            invoices.append({
                "id": str(cycle.get("_id", "")),
                "invoice_date": cycle["end_date"].isoformat(),
                "amount": round(summary.get("total_cost", 0.0), 2),
                "currency": "USD",
                "status": "paid" if cycle.get("status") == "completed" else "pending",
                "invoice_number": f"INV-{cycle['cycle'].upper()}",
                "pdf_url": None  # TODO: Generate PDF
            })

        return invoices

    except Exception as e:
        print(f"[ERROR] Failed to get user invoices: {e}")
        return []


# ============================================================================
# NEW: Optimized Query Functions for Single-Document Architecture
# ============================================================================

async def get_billing_dashboard_data_optimized(user_id: str) -> Dict:
    """
    Get billing data for the frontend dashboard using optimized single-document query.

    Args:
        user_id: User to get data for

    Returns:
        Billing dashboard data
    """
    try:
        # Get billing summary document (single query)
        doc = await mongo_client.find_one("billing_summaries", {"user_id": user_id})

        if not doc or not doc.get("months"):
            # No billing data yet
            now = datetime.utcnow()
            return {
                "current_cycle_start": now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(),
                "current_cycle_end": now.isoformat(),
                "total_tokens": 0,
                "total_mrs_processed": 0,
                "estimated_cost": 0.0,
                "model_usage": [],
                "daily_usage": _get_empty_daily_usage(14)
            }

        # Get current month data
        now = datetime.utcnow()
        current_month = now.strftime("%Y-%m")
        months = doc.get("months", {})

        # Use current month if available, otherwise most recent month
        month_data = months.get(current_month)
        if not month_data and months:
            # Use most recent month
            latest_month = sorted(months.keys(), reverse=True)[0]
            month_data = months[latest_month]
            # Update dates to reflect latest month
            year, month = map(int, latest_month.split("-"))
            now = datetime(year, month, 1)

        if not month_data:
            return {
                "current_cycle_start": now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(),
                "current_cycle_end": now.isoformat(),
                "total_tokens": 0,
                "total_mrs_processed": 0,
                "estimated_cost": 0.0,
                "model_usage": [],
                "daily_usage": _get_empty_daily_usage(14)
            }

        summary = month_data.get("summary", {})

        # Format model usage for frontend
        model_usage = []
        for model_name, model_stats in month_data.get("models", {}).items():
            model_usage.append({
                "model_name": model_name,
                "input_tokens": model_stats.get("input_tokens", 0),
                "output_tokens": model_stats.get("output_tokens", 0),
                "total_tokens": model_stats.get("total_tokens", 0),
                "estimated_cost": model_stats.get("cost", 0.0)
            })

        # Get daily usage from current month
        days_data = month_data.get("days", {})
        daily_usage = _convert_days_to_daily_usage(days_data, days=14)

        # Calculate cycle dates
        cycle_month = current_month if current_month in months else sorted(months.keys(), reverse=True)[0]
        year, month = map(int, cycle_month.split("-"))
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)

        # Calculate projected monthly cost
        current_cost = summary.get("total_cost", 0.0)
        days_in_month = (end_date - start_date).days + 1  # +1 to include both start and end
        days_elapsed = len([d for d in days_data.values() if d.get("tokens", 0) > 0])  # Count days with usage
        if days_elapsed == 0:
            days_elapsed = (now - start_date).days + 1  # Fallback to calendar days elapsed

        projected_data = calculate_projected_monthly_cost(current_cost, days_elapsed, days_in_month)

        return {
            "current_cycle_start": start_date.isoformat(),
            "current_cycle_end": end_date.isoformat(),
            "total_tokens": summary.get("total_tokens", 0),
            "total_mrs_processed": summary.get("mrs_count", 0),
            "estimated_cost": round(current_cost, 6),  # Actual cost so far
            "projected_monthly_cost": projected_data["projected_cost"],  # Projected cost for full month
            "average_daily_cost": projected_data["average_daily_cost"],  # Average daily cost
            "days_elapsed": projected_data["days_elapsed"],  # Days with usage
            "remaining_days": projected_data["remaining_days"],  # Remaining days in month
            "model_usage": model_usage,
            "daily_usage": daily_usage
        }

    except Exception as e:
        print(f"[ERROR] Failed to get billing dashboard data (optimized): {e}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        raise


async def get_user_invoices_optimized(user_id: str, limit: int = 12) -> List[Dict]:
    """
    Get invoice history using optimized single-document query.

    Args:
        user_id: User to get invoices for
        limit: Maximum number of invoices to return

    Returns:
        List of invoice data
    """
    try:
        # Get billing summary document (single query)
        doc = await mongo_client.find_one("billing_summaries", {"user_id": user_id})

        if not doc or not doc.get("months"):
            return []

        invoices = []
        months = sorted(doc.get("months", {}).keys(), reverse=True)[:limit]

        for month_key in months:
            month_data = doc["months"][month_key]
            summary = month_data.get("summary", {})

            # Calculate month dates
            year, month = map(int, month_key.split("-"))
            start_date = datetime(year, month, 1)
            if month == 12:
                end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
            else:
                end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)

            # Skip months with no usage
            if summary.get("total_cost", 0) == 0:
                continue

            invoices.append({
                "id": f"{user_id}_{month_key}",
                "invoice_date": end_date.isoformat(),
                "amount": round(summary.get("total_cost", 0.0), 2),
                "currency": "USD",
                "status": "pending",  # TODO: Add payment status tracking
                "invoice_number": f"INV-{month_key.upper()}",
                "pdf_url": None  # TODO: Generate PDF
            })

        return invoices

    except Exception as e:
        print(f"[ERROR] Failed to get user invoices (optimized): {e}")
        return []


async def get_daily_usage_optimized(user_id: str, days: int = 14) -> List[Dict]:
    """
    Get daily usage data using optimized single-document query.

    Args:
        user_id: User to get data for
        days: Number of days to look back (default: 14)

    Returns:
        List of daily usage records with date, tokens, and cost
    """
    try:
        # Get billing summary document
        doc = await mongo_client.find_one("billing_summaries", {"user_id": user_id})

        if not doc or not doc.get("months"):
            return _get_empty_daily_usage(days)

        # Get current month
        now = datetime.utcnow()
        current_month = now.strftime("%Y-%m")
        months = doc.get("months", {})

        # Use current month data
        month_data = months.get(current_month)
        if not month_data:
            return _get_empty_daily_usage(days)

        days_data = month_data.get("days", {})
        return _convert_days_to_daily_usage(days_data, days)

    except Exception as e:
        print(f"[ERROR] Failed to get daily usage (optimized): {e}")
        return _get_empty_daily_usage(days)


def _get_empty_daily_usage(days: int = 14) -> List[Dict]:
    """Generate empty daily usage structure with zeros."""
    now = datetime.utcnow()
    daily_usage = []
    for i in range(days):
        date = now - timedelta(days=days - 1 - i)
        daily_usage.append({
            "date": date.isoformat(),
            "tokens": 0,
            "cost": 0.0
        })
    return daily_usage


def _convert_days_to_daily_usage(days_data: Dict, days: int = 14) -> List[Dict]:
    """
    Convert internal days structure to frontend daily usage format.

    Args:
        days_data: Internal days dict with keys "01", "02", etc.
        days: Number of days to return

    Returns:
        List of daily usage records
    """
    now = datetime.utcnow()
    daily_usage = []

    for i in range(days):
        date = now - timedelta(days=days - 1 - i)
        day_key = date.strftime("%d")  # Day as "01", "02", etc.

        daily_usage.append({
            "date": date.isoformat(),
            "tokens": days_data.get(day_key, {}).get("tokens", 0),
            "cost": days_data.get(day_key, {}).get("cost", 0.0)
        })

    return daily_usage


def calculate_projected_monthly_cost(current_cost: float, days_elapsed: int, days_in_month: int = None) -> Dict[str, float]:
    """
    Calculate projected monthly cost based on average daily usage.

    Args:
        current_cost: Total cost accumulated so far this month
        days_elapsed: Number of days that have passed in the month
        days_in_month: Total days in the month (defaults to current month's days)

    Returns:
        Dict with projected_cost, average_daily_cost, and remaining_days
    """
    if days_in_month is None:
        # Get current month's days
        now = datetime.utcnow()
        if now.month == 12:
            next_month = datetime(now.year + 1, 1, 1)
        else:
            next_month = datetime(now.year, now.month + 1, 1)
        days_in_month = (next_month - datetime(now.year, now.month, 1)).days

    # Avoid division by zero
    if days_elapsed == 0:
        days_elapsed = 1

    # Calculate average daily cost
    average_daily_cost = current_cost / days_elapsed

    # Calculate remaining days
    remaining_days = days_in_month - days_elapsed

    # Projected cost for the full month
    projected_cost = current_cost + (average_daily_cost * remaining_days)

    return {
        "projected_cost": round(projected_cost, 6),
        "average_daily_cost": round(average_daily_cost, 6),
        "remaining_days": remaining_days,
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
        "current_cost": current_cost
    }


# ============================================================================
# Migration: Legacy to New Single-Document Format
# ============================================================================

async def migrate_billing_data_to_new_format() -> Dict:
    """
    One-time migration from legacy llm_usage_records + billing_cycles to new
    single-document billing_summaries format.

    This should be called once during deployment or manually.

    Returns:
        Migration statistics
    """
    try:
        print("[INFO] Starting billing data migration to new format...")

        # Get all users who have billing data
        billing_cycles = await mongo_client.find("billing_cycles", {})
        migrated_users = 0
        migrated_months = 0
        errors = 0

        for cycle_doc in billing_cycles:
            try:
                user_id = cycle_doc.get("user_id")
                cycle = cycle_doc.get("cycle")  # Format: "2026-05"

                if not user_id or not cycle:
                    continue

                # Get or create billing summary
                billing_summary = await _get_or_create_billing_summary(user_id)

                # Extract data from legacy billing cycle
                summary = cycle_doc.get("summary", {})
                model_breakdown = summary.get("model_breakdown", [])

                # Build new month structure
                month_data = {
                    "summary": {
                        "total_tokens": summary.get("total_tokens", 0),
                        "total_cost": summary.get("total_cost", 0.0),
                        "mrs_count": summary.get("total_mrs_processed", 0)
                    },
                    "models": {},
                    "days": {}
                }

                # Convert model breakdown
                for model_data in model_breakdown:
                    model_name = model_data.get("model_name", "unknown")
                    month_data["models"][model_name] = {
                        "input_tokens": model_data.get("input_tokens", 0),
                        "output_tokens": model_data.get("output_tokens", 0),
                        "total_tokens": model_data.get("total_tokens", 0),
                        "cost": model_data.get("cost", 0.0)
                    }

                # Get daily usage from llm_usage_records for this month
                year, month = map(int, cycle.split("-"))
                start_date = datetime(year, month, 1)
                if month == 12:
                    end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
                else:
                    end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)

                records = await mongo_client.find(
                    "llm_usage_records",
                    {
                        "user_id": user_id,
                        "billing_cycle": cycle
                    }
                )

                # Aggregate daily data
                for record in records:
                    timestamp = record.get("timestamp")
                    if timestamp:
                        day_key = timestamp.strftime("%d")
                        if day_key not in month_data["days"]:
                            month_data["days"][day_key] = {
                                "tokens": 0,
                                "cost": 0.0,
                                "mrs": 0
                            }

                        month_data["days"][day_key]["tokens"] += record.get("total_tokens", 0)
                        month_data["days"][day_key]["cost"] += record.get("estimated_cost", 0.0)

                # Merge into existing months
                existing_months = billing_summary.get("months", {})
                existing_months[cycle] = month_data

                # Update document
                await mongo_client.update_one(
                    "billing_summaries",
                    {"user_id": user_id},
                    {
                        "$set": {
                            "months": existing_months,
                            "sync_state.last_sync_at": cycle_doc.get("last_sync_at"),
                            "updated_at": datetime.utcnow().isoformat()
                        }
                    }
                )

                migrated_users += 1
                migrated_months += 1

                print(f"[OK] Migrated {user_id} / {cycle}")

            except Exception as e:
                print(f"[ERROR] Failed to migrate cycle {cycle_doc.get('_id')}: {e}")
                errors += 1

        print(f"[INFO] Migration complete: {migrated_users} users, {migrated_months} months, {errors} errors")

        return {
            "success": True,
            "migrated_users": migrated_users,
            "migrated_months": migrated_months,
            "errors": errors
        }

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}
