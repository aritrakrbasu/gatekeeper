"""
Debug script to test Arize Cloud billing integration.
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_arize_billing():
    """Test the Arize billing integration."""
    print("=== Testing Arize Cloud Billing Integration ===\n")

    # Import the client
    from config.arize_client import get_arize_client

    # Get the client
    print("1. Getting Arize client...")
    client = await get_arize_client()
    print(f"   Connected: {client.is_connected()}")

    if not client.is_connected():
        print("   ERROR: Client not connected!")
        return

    # Try to get recent traces
    print("\n2. Getting recent traces...")
    traces = await client.get_recent_traces(limit=10, hours_ago=24)

    print(f"   Retrieved {len(traces)} traces")

    if traces:
        print(f"\n3. First trace structure:")
        first = traces[0]
        print(f"   Keys: {list(first.keys())}")
        print(f"   Attributes: {first.get('attributes', {})}")

        # Check for user_id
        attrs = first.get('attributes', {})
        if 'user_id' in attrs:
            print(f"   Has user_id: {attrs['user_id']}")
        else:
            print(f"   No user_id in attributes")

        # Check all traces for user_id
        print(f"\n4. Checking all traces for user_id:")
        for i, trace in enumerate(traces):
            attrs = trace.get('attributes', {})
            has_user_id = 'user_id' in attrs
            print(f"   Trace {i+1}: user_id={attrs.get('user_id') if has_user_id else 'NOT SET'}")
    else:
        print("   No traces found!")

    print("\n=== Test Complete ===")

if __name__ == "__main__":
    asyncio.run(test_arize_billing())
