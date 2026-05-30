"""
Test script to investigate Arize SDK capabilities for querying traces.
"""
import os
import sys
from dotenv import load_dotenv
from arize import ArizeClient

load_dotenv()

space_id = os.getenv('ARIZE_SPACE_ID', '')
api_key = os.getenv('ARIZE_API_KEY', '')

print(f"Space ID: {space_id[:20]}...{space_id[-10:] if space_id else 'None'}")
print(f"API Key: {api_key[:20]}...{api_key[-10:] if api_key else 'None'}")

if space_id and api_key:
    try:
        client = ArizeClient(api_key=api_key)
        print("[OK] ArizeClient initialized successfully")

        # Check all main properties
        print("\n=== Available client properties ===")
        for attr in ['spaces', 'projects', 'spans', 'datasets', 'models', 'experiments', 'prompts']:
            if hasattr(client, attr):
                obj = getattr(client, attr)
                print(f"  {attr}: {type(obj).__name__}")
                # Try to get methods from the object
                try:
                    methods = [m for m in dir(obj) if not m.startswith('_') and callable(getattr(obj, m, None))]
                    if methods:
                        print(f"    Methods: {methods[:10]}")
                except:
                    pass

        # Try to query spans/traces
        print("\n=== Getting projects ===")
        if hasattr(client, 'projects'):
            try:
                projects_obj = client.projects
                projects_response = projects_obj.list()
                print(f"  Projects response type: {type(projects_response)}")
                print(f"  Projects response attributes: {[x for x in dir(projects_response) if not x.startswith('_')]}")

                # Try to get the actual projects list
                projects = None
                if hasattr(projects_response, 'projects'):
                    projects = projects_response.projects
                elif hasattr(projects_response, 'data'):
                    projects = projects_response.data
                elif hasattr(projects_response, '__iter__'):
                    try:
                        projects = list(projects_response)
                    except:
                        pass

                if projects is not None:
                    print(f"  Found {len(projects)} projects")
                    for proj in projects[:5]:
                        proj_id = getattr(proj, 'id', getattr(proj, 'project_id', 'unknown'))
                        proj_name = getattr(proj, 'name', 'unknown')
                        print(f"    - {proj_id}: {proj_name}")

                    # Try to find the main gatekeeper project
                    gatekeeper_project = None
                    for proj in projects:
                        proj_name = getattr(proj, 'name', '')
                        if proj_name == 'gatekeeper':
                            gatekeeper_project = proj
                            break

                    # Fall back to first project if gatekeeper not found
                    if not gatekeeper_project and projects:
                        gatekeeper_project = projects[0]

                    if gatekeeper_project:
                        proj_id = getattr(gatekeeper_project, 'id', getattr(gatekeeper_project, 'project_id', 'unknown'))
                        proj_name = getattr(gatekeeper_project, 'name', 'unknown')
                        print(f"\n=== Trying to query spans for project: {proj_name} (id: {proj_id}) ===")

                        spans_obj = client.spans
                        print(f"Spans object type: {type(spans_obj)}")

                        # Try to list spans for the project
                        print("  Trying to list spans...")
                        spans_response = spans_obj.list(project=proj_id, limit=10)

                        # Handle the response object
                        print(f"  Spans response type: {type(spans_response)}")

                        spans_list = None
                        if hasattr(spans_response, 'spans'):
                            spans_list = spans_response.spans
                        elif hasattr(spans_response, 'data'):
                            spans_list = spans_response.data
                        elif hasattr(spans_response, '__iter__'):
                            try:
                                spans_list = list(spans_response)
                            except:
                                pass

                        print(f"  Got {len(spans_list) if spans_list else 0} spans")

                        if spans_list:
                            print(f"\n  Checking spans for user_id and token usage...")
                            for i, span in enumerate(spans_list[:3]):
                                print(f"\n  Span {i+1}:")
                                if hasattr(span, 'attributes'):
                                    attrs = span.attributes
                                    if isinstance(attrs, dict):
                                        print(f"    Attribute keys: {list(attrs.keys())[:15]}...")

                                        # Check for user_id
                                        if 'user_id' in attrs:
                                            print(f"    User ID: {attrs['user_id']}")

                                        # Check for LLM token usage
                                        if 'llm.token_count.total' in attrs:
                                            print(f"    Total tokens: {attrs['llm.token_count.total']}")
                                            print(f"    Prompt tokens: {attrs.get('llm.token_count.prompt', 'N/A')}")
                                            print(f"    Completion tokens: {attrs.get('llm.token_count.completion', 'N/A')}")
                                            print(f"    Model: {attrs.get('llm.model_name', 'N/A')}")
                                            print(f"    Cost: {attrs.get('llm.cost.total', 'N/A')}")
            except Exception as e:
                print(f"  Error: {e}")
                import traceback
                traceback.print_exc()

    except Exception as e:
        print(f"[ERROR] Error initializing ArizeClient: {e}")
        import traceback
        traceback.print_exc()
else:
    print("[ERROR] Missing credentials")
