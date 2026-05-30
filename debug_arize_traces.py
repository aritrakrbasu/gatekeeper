"""
Debug script to check Arize trace attributes in detail.
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def debug_arize_traces():
    """Debug Arize traces to see all attributes."""
    print("=== Debugging Arize Trace Attributes ===\n")

    from config.arize_client import get_arize_client

    # Get the client
    print("1. Getting Arize client...")
    client = await get_arize_client()
    print(f"   Connected: {client.is_connected()}")

    if not client.is_connected():
        print("   ERROR: Client not connected!")
        return

    # Get recent traces
    print("\n2. Getting recent traces...")
    traces = await client.get_recent_traces(limit=5, hours_ago=24)

    print(f"   Retrieved {len(traces)} traces\n")

    if not traces:
        print("   No traces found!")
        return

    # Print detailed info for each trace
    for i, trace in enumerate(traces):
        print(f"\n--- Trace {i+1} ---")
        print(f"trace_id: {trace.get('trace_id', 'N/A')[:16]}...")
        print(f"span_id: {trace.get('span_id', 'N/A')[:16]}...")

        attrs = trace.get('attributes', {})
        print(f"\nAll attributes ({len(attrs)}):")
        for key, value in sorted(attrs.items()):
            if isinstance(value, dict):
                print(f"  {key}: <dict with {len(value)} keys>")
                for k2, v2 in sorted(value.items()):
                    print(f"    {k2}: {str(v2)[:50]}...")
            elif isinstance(value, (list, tuple)):
                print(f"  {key}: <{type(value).__name__} with {len(value)} items>")
            elif isinstance(value, str) and len(value) > 100:
                print(f"  {key}: {value[:100]}...")
            else:
                print(f"  {key}: {value}")

    print("\n=== Debug Complete ===")

if __name__ == "__main__":
    asyncio.run(debug_arize_traces())
