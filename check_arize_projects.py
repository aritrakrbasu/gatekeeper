"""
Check all Arize projects and their recent spans.
"""
import os
from dotenv import load_dotenv

load_dotenv()

async def check_all_projects():
    """Check all projects and their recent spans."""
    from arize import ArizeClient
    from datetime import datetime, timedelta, timezone

    client = ArizeClient(api_key=os.getenv('ARIZE_API_KEY'))

    # Get all projects
    projects_response = client.projects.list()
    projects = getattr(projects_response, 'projects', [])

    print(f"Found {len(projects)} projects:\n")

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=48)

    for project in projects:
        project_id = getattr(project, 'id', '')
        project_name = getattr(project, 'name', 'unknown')

        print(f"Project: {project_name}")
        print(f"  ID: {project_id}")

        # Try to get spans from this project
        try:
            spans_response = client.spans.list(
                project=project_id,
                start_time=start_time,
                end_time=end_time,
                limit=5
            )

            spans = getattr(spans_response, 'spans', [])
            print(f"  Spans (last 48h): {len(spans)}")

            if spans:
                print(f"  Sample span attributes:")
                first_span = spans[0]
                attrs = getattr(first_span, 'attributes', {})
                print(f"    Keys: {list(attrs.keys())[:15]}")
                print(f"    user_id: {attrs.get('user_id', 'NOT SET')}")
                print(f"    mr_id: {attrs.get('mr_id', 'NOT SET')}")
                print(f"    repository_id: {attrs.get('repository_id', 'NOT SET')}")
                if 'llm.token_count.total' in attrs:
                    print(f"    Has LLM data: YES")
        except Exception as e:
            print(f"  Error: {e}")

        print()

if __name__ == "__main__":
    import asyncio
    asyncio.run(check_all_projects())
