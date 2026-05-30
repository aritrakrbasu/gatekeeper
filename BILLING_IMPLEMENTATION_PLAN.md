# Billing & Usage Tracking Implementation Plan

## Context

This plan implements a billing and usage tracking system that:
- Collects LLM usage data (tokens, costs, model names) from Arize/Phoenix traces
- Stores usage data in MongoDB organized by user and billing cycle
- Provides API endpoints for the frontend Billing.jsx page
- Implements proper sync/resync mechanisms to avoid data corruption

**Current State:**
- Arize/Phoenix infrastructure exists but is **NOT initialized** (`config/arize_config.py`, `config/phoenix_mcp.py`)
- No LLM usage tracking is active in `services/gemini_service.py`
- Frontend `Billing.jsx` expects data but uses dummy values
- Frontend API service (`frontend/gatekeeper/src/services/api.js`) has billing endpoints defined but backend doesn't implement them
- MongoDB collections exist for users/repositories but no billing-related collections

**Key Challenge:** Webhooks don't have user context. We'll derive user_id from repository ownership.

---

## Implementation Plan

### Phase 1: Enable Arize/Phoenix Observability

**Files to modify:**
- `main.py` - Add Arize initialization to startup event
- `config/arize_config.py` - Already has the functions, just needs to be called

**Changes:**

1. **Initialize Arize in `main.py` startup_event:**
```python
@app.on_event("startup")
async def startup_event():
    # ... existing code ...

    # Initialize Arize observability
    from config.arize_config import init_arize, instrument_google_genai

    if init_arize(project_name="gatekeeper"):
        instrument_google_genai()
```

2. **Initialize Phoenix client:**
```python
    from config.arize_config import init_phoenix_client
    init_phoenix_client()
```

---

### Phase 2: Capture Usage Data in Gemini Service

**File to modify:** `services/gemini_service.py`

**Changes:**

1. **Modify `run_gemini_review()` to return usage data:**
```python
async def run_gemini_review(raw_diff_content: str, impact_context: str, user_config: Dict = None, user_id: str = None) -> dict:
    # ... existing code ...

    response = await call_gemini_with_retry(...)

    # Extract usage metadata
    usage_metadata = getattr(response, 'usage_metadata', None)
    usage_data = {
        "input_tokens": getattr(usage_metadata, 'prompt_token_count', 0) if usage_metadata else 0,
        "output_tokens": getattr(usage_metadata, 'candidates_token_count', 0) if usage_metadata else 0,
        "total_tokens": getattr(usage_metadata, 'total_token_count', 0) if usage_metadata else 0,
        "model_name": model
    }

    # Set span attributes for Phoenix
    if user_id:
        from config.arize_config import set_span_attributes
        set_span_attributes(
            user_id=user_id,
            input_tokens=usage_data["input_tokens"],
            output_tokens=usage_data["output_tokens"],
            model_name=model
        )

    return {
        "review_text": response.text,
        "usage": usage_data
    }
```

2. **Do the same for `run_gemini_fix_analysis()`:**
   - Return usage data alongside the JSON response
   - Set span attributes with user_id and token counts

---

### Phase 3: Inject User Context in Review Pipeline

**File to modify:** `services/review_service.py`

**Changes:**

The `get_user_config_from_repo()` function already exists and extracts user_id. We need to:

1. **Pass user_id through the review pipeline:**
```python
async def orchestrate_review(payload: dict) -> dict:
    # Get user config (which includes user_id from repository owner)
    user_config = await get_user_config_from_repo(str(project_id))

    # Extract user_id from repository
    repo = await repository_service.get_repository(str(project_id))
    user_id = repo.get("user_id") if repo else None

    # ... existing code ...

    # Pass user_id to Gemini calls
    audit_report = await run_gemini_review(
        raw_diff_content,
        impact_context,
        user_config,
        user_id=user_id  # NEW PARAMETER
    )

    # Extract usage data
    usage_data = audit_report.get("usage", {})
    review_text = audit_report.get("review_text")
```

2. **Store usage in MongoDB after Gemini calls:**
   - Create a function to store usage records
   - Call it after each Gemini API call

---

### Phase 4: Create MongoDB Collections and Models

**New files to create:**

1. **`services/billing_service.py`** - Core billing logic

```python
"""
Billing service for usage tracking and cost calculation.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from services import mongo_client
from services.pricing import calculate_cost
from config.phoenix_mcp import get_phoenix_bridge

# ============================================================================
# MongoDB Collections
# ============================================================================

async def ensure_indexes():
    """Create indexes for billing collections."""
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
                    "model_breakdown": [
                        {
                            "model_name": model,
                            "input_tokens": data["input_tokens"],
                            "output_tokens": data["output_tokens"],
                            "total_tokens": data["total_tokens"],
                            "cost": data["cost"]
                        }
                        for model, data in model_breakdown.items()
                    ]
                },
                "updated_at": datetime.utcnow(),
                "last_sync_at": datetime.utcnow()
            }
        )

    except Exception as e:
        print(f"[ERROR] Failed to update billing cycle summary: {e}")


# ============================================================================
# Sync from Phoenix
# ============================================================================

async def sync_user_usage_from_phoenix(
    user_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    force_resync: bool = False
) -> Dict:
    """
    Sync usage data from Phoenix traces for a user.

    Args:
        user_id: User to sync
        start_date: Start of sync period (defaults to beginning of current cycle)
        end_date: End of sync period (defaults to now)
        force_resync: If True, re-sync all data

    Returns:
        Sync result with statistics
    """
    try:
        bridge = await get_phoenix_bridge()
        if not bridge.is_connected():
            return {"success": False, "error": "Phoenix not connected"}

        # Default to current billing cycle
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            # Start of current month
            start_date = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get traces for user
        traces = await bridge.get_recent_traces(
            limit=1000,
            span_name="generate_content",
            hours_ago=int((end_date - start_date).total_seconds() / 3600)
        )

        synced = 0
        skipped = 0
        errors = 0

        for trace in traces:
            try:
                # Extract trace ID
                trace_id = trace.get("trace_id")
                if not trace_id:
                    skipped += 1
                    continue

                # Check if user_id matches in attributes
                attributes = trace.get("attributes", {})
                if attributes.get("user_id") != user_id:
                    skipped += 1
                    continue

                # Extract token usage from span attributes
                input_tokens = attributes.get("llm.input_tokens", 0)
                output_tokens = attributes.get("llm.output_tokens", 0)
                model_name = attributes.get("llm.model_name", "gemini-3.5-flash")

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

        return {
            "success": True,
            "synced": synced,
            "skipped": skipped,
            "errors": errors,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }

    except Exception as e:
        print(f"[ERROR] Failed to sync user usage: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Get Billing Data for Frontend
# ============================================================================

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
            return {
                "current_cycle_start": now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(),
                "current_cycle_end": now.isoformat(),
                "total_tokens": 0,
                "total_mrs_processed": 0,
                "estimated_cost": 0.0,
                "model_usage": []
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

        return {
            "current_cycle_start": cycle_doc["start_date"].isoformat(),
            "current_cycle_end": cycle_doc["end_date"].isoformat(),
            "total_tokens": summary.get("total_tokens", 0),
            "total_mrs_processed": summary.get("total_mrs_processed", 0),
            "estimated_cost": summary.get("total_cost", 0.0),
            "model_usage": model_usage
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
            sort=[("cycle", -1)],
            limit=limit
        )

        invoices = []
        for cycle in cycles:
            summary = cycle.get("summary", {})
            invoices.append({
                "id": str(cycle.get("_id", "")),
                "invoice_date": cycle["end_date"],
                "amount": summary.get("total_cost", 0.0),
                "currency": "USD",
                "status": "paid",
                "invoice_number": f"INV-{cycle['cycle'].upper()}",
                "pdf_url": None  # TODO: Generate PDF
            })

        return invoices

    except Exception as e:
        print(f"[ERROR] Failed to get user invoices: {e}")
        return []
```

2. **`services/pricing.py`** - Cost calculation logic

```python
"""
Gemini API pricing and cost calculation.
"""

from typing import Dict, Tuple

# Gemini pricing as of 2026 (per 1M tokens)
GEMINI_PRICING = {
    "gemini-3.5-flash": {
        "input_per_million": 0.075,   # $0.075 per 1M input tokens
        "output_per_million": 0.15    # $0.15 per 1M output tokens
    },
    "gemini-3.1-pro-preview": {
        "input_per_million": 0.50,    # $0.50 per 1M input tokens
        "output_per_million": 1.50    # $1.50 per 1M output tokens
    }
}


async def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """
    Calculate cost based on Gemini pricing.

    Args:
        model_name: Model used
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens

    Returns:
        Estimated cost in USD
    """
    pricing = GEMINI_PRICING.get(model_name, GEMINI_PRICING["gemini-3.5-flash"])

    input_cost = (input_tokens / 1_000_000) * pricing["input_per_million"]
    output_cost = (output_tokens / 1_000_000) * pricing["output_per_million"]

    return round(input_cost + output_cost, 6)


def get_pricing_info() -> Dict[str, Dict[str, float]]:
    """Get all pricing information."""
    return GEMINI_PRICING
```

---

### Phase 5: Add API Endpoints

**File to modify:** `main.py`

**Add new endpoints:**

```python
# ============================================================================
# Billing Endpoints
# ============================================================================

@app.get("/api/billing/usage", response_model=BillingUsageResponse)
async def get_billing_usage(authorization: str = Header(None)):
    """Get billing usage statistics for current user."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        # Sync latest data from Phoenix (optional, can be background task)
        # await billing_service.sync_user_usage_from_phoenix(user_id)

        # Get billing data
        data = await billing_service.get_billing_dashboard_data(user_id)

        return BillingUsageResponse(**data)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to get billing usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/billing/sync")
async def sync_billing_data(
    request: SyncRequest,
    authorization: str = Header(None)
):
    """Sync billing data from Phoenix."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        # Sync from Phoenix
        result = await billing_service.sync_user_usage_from_phoenix(
            user_id=user_id,
            force_resync=request.force_resync
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to sync billing data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/billing/invoices", response_model=List[InvoiceResponse])
async def get_invoices(
    limit: int = 12,
    authorization: str = Header(None)
):
    """Get invoice history."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        invoices = await billing_service.get_user_invoices(user_id, limit)

        return [InvoiceResponse(**inv) for inv in invoices]

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to get invoices: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Add to imports in `main.py`:**
```python
from services import billing_service
from api_models import SyncRequest
```

**Add to `api_models.py`:**
```python
class SyncRequest(BaseModel):
    """Request to sync usage data."""
    cycle: Optional[str] = None  # Specific cycle or current
    force_resync: bool = False
```

---

### Phase 6: Update Frontend Billing Page

**File to modify:** `frontend/gatekeeper/src/pages/Billing.jsx`

**Changes:**

1. **Add React Query for data fetching:**
```javascript
import { useQuery } from "@tanstack/react-query";
import { api } from "../services/api";

const Billing = () => {
  // Fetch billing data
  const { data: billingData, isLoading } = useQuery({
    queryKey: ['billing-usage'],
    queryFn: () => api.getBillingUsage(),
  });

  const { data: invoices } = useQuery({
    queryKey: ['billing-invoices'],
    queryFn: () => api.getInvoices(),
  });

  if (isLoading) {
    return <div>Loading...</div>;
  }

  // Use billingData instead of dummy data
  const usageStats = {
    currentTotal: `$${billingData?.estimated_cost.toFixed(2) || '0.00'}`,
    projectedTotal: `$${(billingData?.estimated_cost * 1.2 || 0).toFixed(2)}`,
    totalTokens: formatTokens(billingData?.total_tokens),
    mrsProcessed: billingData?.total_mrs_processed || 0
  };

  // Map model_usage to geminiBreakdown format
  const geminiBreakdown = (billingData?.model_usage || []).map(model => ({
    model: formatModelName(model.model_name),
    inputTokens: formatTokens(model.input_tokens),
    outputTokens: formatTokens(model.output_tokens),
    cost: `$${model.estimated_cost.toFixed(2)}`,
    percentage: calculatePercentage(model.estimated_cost, billingData.estimated_cost)
  }));

  // ... rest of component
};
```

---

## Resync Strategy

### Safe Resync Approach

1. **Upsert Records**: Always use upsert based on `(user_id, trace_id)` unique key to avoid duplicates

2. **Billing Cycle Aggregation**: Re-calculate from all usage records in the cycle rather than incrementing

3. **Sync Tracking**: Store `last_sync_at` timestamps to know what needs syncing

4. **Force Resync Safety**:
   - Never delete existing data unless explicitly requested
   - Mark cycle as "pending" during resync
   - Rollback on error

---

## Verification Steps

1. **Test Arize Initialization:**
   - Check logs for `[✅] Arize observability initialized`
   - Verify traces appear in Phoenix UI

2. **Test Usage Capture:**
   - Trigger a webhook event
   - Check Phoenix for trace with user_id and token attributes
   - Verify record in `llm_usage_records` collection

3. **Test Billing API:**
   - Call `/api/billing/usage` with valid token
   - Verify response matches expected format
   - Check `Billing.jsx` displays real data

4. **Test Resync:**
   - Call `/api/billing/sync` with `force_resync=true`
   - Verify no duplicate records created
   - Verify cycle summary updated correctly

---

## Critical Files Summary

| File | Action | Description |
|------|--------|-------------|
| `main.py` | MODIFY | Add Arize init and billing endpoints |
| `services/gemini_service.py` | MODIFY | Return usage data, set span attributes |
| `services/review_service.py` | MODIFY | Pass user_id, store usage |
| `services/billing_service.py` | CREATE | Core billing logic |
| `services/pricing.py` | CREATE | Cost calculation |
| `api_models.py` | MODIFY | Add SyncRequest model |
| `frontend/gatekeeper/src/pages/Billing.jsx` | MODIFY | Use real API data |

---

## Implementation Order

1. Phase 1: Enable Arize (test with logs)
2. Phase 2: Capture usage (test with webhook)
3. Phase 3: Inject user context (verify in traces)
4. Phase 4: Create billing service (test sync manually)
5. Phase 5: Add endpoints (test with API client)
6. Phase 6: Update frontend (verify UI displays data)

---

## Environment Variables Needed

Ensure these are set in `.env`:

```bash
# Arize Configuration
ARIZE_SPACE_ID=your_space_id
ARIZE_API_KEY=your_api_key

# Phoenix Configuration
PHOENIX_MODE=cloud
PHOENIX_API_KEY=your_phoenix_api_key
PHOENIX_BASE_URL=https://app.phoenix.arize.com
PHOENIX_PROJECT_NAME=gatekeeper
```
