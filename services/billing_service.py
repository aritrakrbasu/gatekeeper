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
from services.pricing import calculate_cost
from config.arize_client import get_arize_client


# ============================================================================
# MongoDB Collections
# ============================================================================

async def ensure_indexes():
    """Create indexes for billing collections."""
    try:
        # llm_usage_records indexes
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

        # billing_cycles indexes
        await mongo_client.create_index(
            "billing_cycles",
            [("user_id", 1), ("cycle", 1)],
            unique=True
        )

        print("[OK] Billing collection indexes created successfully")
    except Exception as e:
        print(f"[WARN] Failed to create billing indexes: {e}")


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

                # Debug: print first few traces to understand structure
                if synced == 0 and skipped < 3:
                    print(f"[DEBUG] Trace {trace_id[:8]}... attributes: {list(attributes.keys())[:15]}")
                    print(f"[DEBUG] Trace user_id: {trace_user_id} (looking for: {user_id})")
                    if not trace_user_id:
                        print(f"[DEBUG] No user_id in trace - checking if we should associate with requesting user")

                # If trace has a user_id that doesn't match the requesting user, skip
                # This handles multi-tenant scenarios where traces have specific user ownership
                if trace_user_id and str(trace_user_id) != str(user_id):
                    print(f"[DEBUG] Skipping trace - user_id mismatch: {trace_user_id} != {user_id}")
                    skipped += 1
                    continue

                # If no user_id in trace, associate with requesting user
                # (This is a fallback for traces that don't have user_id set)
                if not trace_user_id:
                    print(f"[DEBUG] No user_id in trace - associating with requesting user: {user_id}")
                    # Continue processing - will use the requesting user_id below

                # Extract token usage from span attributes
                # Note: OpenTelemetry uses underscores, not dots
                input_tokens = attributes.get("llm_input_tokens", 0)
                output_tokens = attributes.get("llm_output_tokens", 0)
                model_name = attributes.get("llm_model_name", "gemini-3.5-flash")

                print(f"[DEBUG] Found matching trace: {input_tokens} input, {output_tokens} output tokens")

                if not input_tokens and not output_tokens:
                    skipped += 1
                    continue

                # Calculate totals and cost
                total_tokens = input_tokens + output_tokens
                estimated_cost = await calculate_cost(model_name, input_tokens, output_tokens)

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
