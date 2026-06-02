"""
Test script to debug span attribute propagation.
"""
import os
from dotenv import load_dotenv

load_dotenv()

async def test_span_attributes():
    """Test if span attributes are being captured by Arize."""
    from config.arize_client import get_arize_client

    print("=== Testing Span Attribute Propagation ===\n")

    client = await get_arize_client()

    # Get the raw spans from Arize to see what attributes are actually there
    from arize import ArizeClient
    arize_client = ArizeClient(api_key=os.getenv('ARIZE_API_KEY'))

    # Get project
    projects_response = arize_client.projects.list()
    projects = getattr(projects_response, 'projects', [])
    if projects:
        project_id = getattr(projects[0], 'id', '')

        # Get raw spans from the last 24 hours
        from datetime import datetime, timedelta, timezone
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=24)

        spans_response = arize_client.spans.list(
            project=project_id,
            start_time=start_time,
            end_time=end_time,
            limit=10
        )

        spans = getattr(spans_response, 'spans', [])
        print(f"Retrieved {len(spans)} raw spans from Arize\n")

        for i, span in enumerate(spans[:5]):
            print(f"Span {i+1}:")
            print(f"  Kind: {getattr(span, 'kind', 'unknown')}")
            print(f"  Name: {getattr(span, 'name', 'unknown')}")

            # Get all attributes
            attrs = getattr(span, 'attributes', {})
            print(f"  All attribute keys: {list(attrs.keys())[:20]}")

            # Check for our custom attributes
            print(f"  user_id: {attrs.get('user_id', 'NOT SET')}")
            print(f"  mr_id: {attrs.get('mr_id', 'NOT SET')}")
            print(f"  repository_id: {attrs.get('repository_id', 'NOT SET')}")

            # Check for LLM token attributes
            if 'llm.token_count.total' in attrs:
                print(f"  Has LLM tokens: YES")
                print(f"    Input: {attrs.get('llm.token_count.prompt')}")
                print(f"    Output: {attrs.get('llm.token_count.completion')}")
                print(f"    Total: {attrs.get('llm.token_count.total')}")
            print()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_span_attributes())
