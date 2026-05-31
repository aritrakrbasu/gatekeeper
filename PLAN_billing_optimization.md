# Billing & Usage Efficiency Optimization Plan

## Context

Current billing implementation syncs traces from Arize Cloud (500 limit per request) to MongoDB with N+1 write issues. **NEW APPROACH:** Store pre-aggregated billing data in a SINGLE document per user with monthly nested structure.

## New Document Architecture

### Single User Billing Document
```json
{
  "_id": "billing:user_123",
  "user_id": "user_123",
  "sync_state": {
    "last_sync_at": "2026-05-30T10:30:00Z",
    "last_trace_id": "trace_abc123"  // Optional: for deduplication
  },
  "months": {
    "2026-05": {
      "summary": {
        "total_tokens": 1500000,
        "total_cost": 15.50,
        "mrs_count": 45
      },
      "models": {
        "gemini-1.5-pro": {"tokens": 1000000, "cost": 12.50},
        "gemini-1.5-flash": {"tokens": 500000, "cost": 3.00}
      },
      "days": {
        "01": {"tokens": 50000, "cost": 0.50, "mrs": 2},
        "02": {"tokens": 75000, "cost": 0.75, "mrs": 3}
      }
    }
  }
}
```

## Sync Strategy for 500 Span Limit

### Problem: Arize API only returns 500 spans max per request
### Solution: Paginated time-window sync with checkpoint tracking

**Algorithm:**
```python
async def sync_user_billing(user_id: str):
    doc = await get_billing_doc(user_id)
    last_sync = doc.get("sync_state", {}).get("last_sync_at")

    # Use smaller time windows (6 hours) to stay under 500 limit
    window_start = last_sync or (now - 24 hours)
    window_end = now

    while window_start < window_end:
        # Query 6-hour window (likely < 500 spans)
        window_end_step = min(window_start + 6hours, window_end)
        traces = await arize.get_traces(
            start=window_start,
            end=window_end_step,
            limit=500
        )

        if len(traces) == 500:
            # Hit limit - shrink window and retry
            window_end_step = window_start + 3hours
            continue  # retry with smaller window

        # Aggregate into memory
        for trace in traces:
            aggregate_trace(trace, doc)

        # Move window forward
        window_start = window_end_step

    # Single atomic update
    await update_billing_doc(user_id, doc)
```

**Benefits:**
- Handles unlimited spans via pagination
- Never misses traces (adaptive window sizing)
- Single DB write per sync
- Idempotent (can re-run safely)

## Implementation Plan

### Phase 1: New Document Schema (1 hour)
**File:** `services/billing_service.py`

1. Create new `billing_summaries` collection
2. Define `BillingSummary` model with nested monthly structure
3. Add index on `user_id` for fast lookups

### Phase 2: Paginated Sync Logic (2-3 hours)
**File:** `services/billing_service.py`

1. Implement adaptive time-window sync
2. Add in-memory aggregation per trace
3. Single atomic `update_one()` at end
4. Store `sync_state` checkpoint

### Phase 3: Migration from Old Schema (1 hour)
**File:** `services/billing_service.py`

1. One-time migration script
2. Aggregate existing `llm_usage_records` into new format
3. Verify data integrity
4. Deprecate old collections

### Phase 4: Update Queries (1 hour)
**Files:** `services/billing_service.py`, `main.py`

1. `get_billing_dashboard_data()` - single document read
2. `get_user_invoices()` - extract from `months` keys
3. `get_daily_usage()` - extract from current month's `days`

## Critical Files to Modify

1. **`services/billing_service.py`** - New sync logic, document structure
2. **`config/arize_client.py`** - May need pagination helper
3. **`main.py`** - Update API endpoints (simpler queries)

## Verification Steps

1. **Test with < 500 spans**: Verify single-window sync works
2. **Test with > 500 spans**: Verify adaptive window pagination works
3. **Test idempotency**: Run sync twice, verify no duplicates
4. **Test migration**: Verify old data migrates correctly
5. **Load test**: Simulate 2000+ spans in sync window

## Expected Impact

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| DB writes per sync | ~500 | 1 | 99.8% reduction |
| DB reads | Multiple | 1 | Single query |
| Storage size | N records | 1 document | ~90% reduction |
| Sync reliability | May miss >500 | Guaranteed all | 100% coverage |

## Implementation Order

1. **Phase 1** - Document schema (foundational)
2. **Phase 2** - Paginated sync (core logic)
3. **Phase 4** - Update queries (make it work)
4. **Phase 3** - Migration (can run in background)
