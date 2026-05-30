"""
Test script to verify direct billing tracking works.
"""
import asyncio
from datetime import datetime
from services.mongo_client import find, upsert_one
from services.pricing import calculate_cost
from services.billing_service import _update_billing_cycle_summary, get_billing_dashboard_data


async def test_direct_billing():
    """Test direct billing tracking."""
    print("=== Testing Direct Billing Tracking ===\n")

    # Simulate a usage record
    user_id = "test-user-123"
    model_name = "gemini-3.5-flash"
    input_tokens = 1000
    output_tokens = 500
    total_tokens = 1500

    # Calculate cost
    cost = await calculate_cost(model_name, input_tokens, output_tokens)
    print(f"Test cost: ${cost:.6f} for {input_tokens}+{output_tokens} tokens")

    # Get current billing cycle
    now = datetime.utcnow()
    billing_cycle = now.strftime("%Y-%m")

    # Store a test record
    record = {
        "user_id": user_id,
        "trace_id": f"test-{now.strftime('%Y%m%d%H%M%S%f')}",
        "timestamp": now,
        "billing_cycle": billing_cycle,
        "model_name": model_name,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost": cost,
        "metadata": {
            "mr_id": "test-mr-123",
            "repository_id": "test-repo-456",
            "operation_type": "review"
        },
        "synced_at": now
    }

    print(f"\n1. Storing test record...")
    success = await upsert_one(
        "llm_usage_records",
        {"user_id": user_id, "trace_id": record["trace_id"]},
        record
    )
    print(f"   Result: {'SUCCESS' if success else 'FAILED'}")

    # Update billing cycle summary
    print(f"\n2. Updating billing cycle summary...")
    await _update_billing_cycle_summary(user_id, billing_cycle)
    print(f"   Summary updated")

    # Verify the record was stored
    print(f"\n3. Verifying record was stored...")
    records = await find("llm_usage_records", {"user_id": user_id})
    print(f"   Found {len(records)} records for user {user_id}")

    if records:
        print(f"   Latest record: {records[-1]}")

    # Get billing dashboard data
    print(f"\n4. Getting billing dashboard data...")
    billing_data = await get_billing_dashboard_data(user_id)
    print(f"   Total tokens: {billing_data.get('total_tokens', 0)}")
    print(f"   Total MRs: {billing_data.get('total_mrs_processed', 0)}")
    print(f"   Estimated cost: ${billing_data.get('estimated_cost', 0):.6f}")
    print(f"   Model usage: {billing_data.get('model_usage', [])}")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_direct_billing())
