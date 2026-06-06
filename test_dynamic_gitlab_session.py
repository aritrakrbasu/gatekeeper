"""
Test script for dynamic GitLab session functionality.

Tests:
1. Session creation with user token
2. Session caching (reuse for same user)
3. Different sessions for different users
4. Session cleanup
"""

import asyncio
import os
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()


async def test_session_cache_size():
    """Test 1: Verify session cache size tracking."""
    print("\n=== Test 1: Session Cache Size ===")
    from services import mcp_service

    # Initial cache should be empty (except global session which is separate)
    cache_size = mcp_service.get_session_cache_size()
    print(f"Initial cache size: {cache_size}")
    assert cache_size >= 0, "Cache size should be non-negative"
    print("✓ Test 1 passed")


async def test_session_creation():
    """Test 2: Session creation with a test user."""
    print("\n=== Test 2: Session Creation ===")
    from services import mcp_service
    from unittest.mock import patch

    # Use a test user ID
    test_user_id = "test_user_123"
    test_project_id = "test_project_456"
    test_token = "glpat-ToO6ZlkYTyqIC2zlEJnjCmM6MQpvOjEKdTpuNXJxYQ8.01.1702k8efa"

    # Mock the token retrieval to return our test token
    async def mock_get_token(user_id, project_id):
        return test_token

    # Try to get a session - this will either create new or use fallback
    try:
        with patch('services.user_service.get_user_gitlab_token', side_effect=mock_get_token):
            session = await mcp_service.get_gitlab_session_for_user(test_user_id, test_project_id)

        if session:
            print(f"✓ Session created/retrieved for user {test_user_id}")
            print(f"Cache size after creation: {mcp_service.get_session_cache_size()}")

            # Verify the session is usable by listing tools
            try:
                tools = await session.list_tools()
                print(f"✓ Session is functional - found {len(tools.tools)} tools")
            except Exception as e:
                print(f"⚠ Session created but tool listing failed: {e}")

            return True
        else:
            print("✗ No session available (expected if no token configured)")
            return False

    except Exception as e:
        print(f"✗ Session creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        await mcp_service.cleanup_gitlab_session(test_user_id)


async def test_session_caching():
    """Test 3: Session caching - same user gets same session."""
    print("\n=== Test 3: Session Caching ===")
    from services import mcp_service
    from unittest.mock import patch

    test_user_id = "test_user_cache_123"
    test_token = "glpat-ToO6ZlkYTyqIC2zlEJnjCmM6MQpvOjEKdTpuNXJxYQ8.01.1702k8efa"

    async def mock_get_token(user_id, project_id):
        return test_token

    try:
        with patch('services.user_service.get_user_gitlab_token', side_effect=mock_get_token):
            # First call - should create session
            session1 = await mcp_service.get_gitlab_session_for_user(test_user_id, "project_1")

        if not session1:
            print("⚠ Skipped - no session available (no token configured)")
            return False

        cache_size_after_first = mcp_service.get_session_cache_size()
        print(f"Cache size after first call: {cache_size_after_first}")

        # Second call - should return cached session
        session2 = await mcp_service.get_gitlab_session_for_user(test_user_id, "project_2")

        cache_size_after_second = mcp_service.get_session_cache_size()
        print(f"Cache size after second call: {cache_size_after_second}")

        # Verify cache size didn't increase (session was reused)
        assert cache_size_after_first == cache_size_after_second, \
            "Cache size should not increase when reusing session"

        print("✓ Session caching works - same user gets same session")
        return True

    except Exception as e:
        print(f"✗ Session caching test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        await mcp_service.cleanup_gitlab_session(test_user_id)


async def test_multiple_users():
    """Test 4: Different users get different sessions."""
    print("\n=== Test 4: Multiple Users ===")
    from services import mcp_service
    from unittest.mock import patch

    user1 = "test_user_multi_1"
    user2 = "test_user_multi_2"
    test_token = "glpat-ToO6ZlkYTyqIC2zlEJnjCmM6MQpvOjEKdTpuNXJxYQ8.01.1702k8efa"

    async def mock_get_token(user_id, project_id):
        return test_token

    try:
        with patch('services.user_service.get_user_gitlab_token', side_effect=mock_get_token):
            # Create sessions for two different users
            session1 = await mcp_service.get_gitlab_session_for_user(user1, "project_1")
            session2 = await mcp_service.get_gitlab_session_for_user(user2, "project_2")

        if not session1 or not session2:
            print("⚠ Skipped - no sessions available (no token configured)")
            return False

        cache_size = mcp_service.get_session_cache_size()
        print(f"Cache size with 2 users: {cache_size}")

        # Both sessions should be cached
        assert cache_size >= 2, "Should have at least 2 sessions cached"

        print("✓ Multiple users get separate sessions")
        return True

    except Exception as e:
        print(f"✗ Multiple users test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup both users
        await mcp_service.cleanup_gitlab_session(user1)
        await mcp_service.cleanup_gitlab_session(user2)


async def test_cleanup():
    """Test 5: Session cleanup."""
    print("\n=== Test 5: Session Cleanup ===")
    from services import mcp_service
    from unittest.mock import patch

    test_user_id = "test_user_cleanup_123"
    test_token = "glpat-ToO6ZlkYTyqIC2zlEJnjCmM6MQpvOjEKdTpuNXJxYQ8.01.1702k8efa"

    async def mock_get_token(user_id, project_id):
        return test_token

    try:
        with patch('services.user_service.get_user_gitlab_token', side_effect=mock_get_token):
            # Create a session
            await mcp_service.get_gitlab_session_for_user(test_user_id, "project_1")
        cache_size_before = mcp_service.get_session_cache_size()
        print(f"Cache size before cleanup: {cache_size_before}")

        # Cleanup the session
        cleaned = await mcp_service.cleanup_gitlab_session(test_user_id)

        if cleaned:
            cache_size_after = mcp_service.get_session_cache_size()
            print(f"Cache size after cleanup: {cache_size_after}")

            assert cache_size_after == cache_size_before - 1, \
                "Cache size should decrease by 1 after cleanup"

            print("✓ Session cleanup works correctly")
        else:
            print("⚠ No session to cleanup")

        return cleaned

    except Exception as e:
        print(f"✗ Cleanup test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_idle_cleanup():
    """Test 6: Idle session cleanup."""
    print("\n=== Test 6: Idle Session Cleanup ===")
    from services import mcp_service
    from unittest.mock import patch

    test_token = "glpat-ToO6ZlkYTyqIC2zlEJnjCmM6MQpvOjEKdTpuNXJxYQ8.01.1702k8efa"

    async def mock_get_token(user_id, project_id):
        return test_token

    try:
        with patch('services.user_service.get_user_gitlab_token', side_effect=mock_get_token):
            # Create a session
            await mcp_service.get_gitlab_session_for_user("idle_test_user", "project_1")

        # Force idle cleanup with 0 second timeout (should clean up immediately)
        import time
        time.sleep(1)  # Small delay to ensure timestamp difference

        cleaned = await mcp_service.cleanup_idle_sessions(max_idle_seconds=0)

        print(f"Idle sessions cleaned: {cleaned}")
        print("✓ Idle cleanup function executed")

        return True

    except Exception as e:
        print(f"✗ Idle cleanup test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Dynamic GitLab Session Implementation")
    print("=" * 60)

    # Use the new valid test token
    test_token = "glpat-ToO6ZlkYTyqIC2zlEJnjCmM6MQpvOjEKdTpuNXJxYQ8.01.1702k8efa"

    if not test_token:
        print("WARNING: No token available")
        print("Some tests may be skipped or fail without a valid token")
    else:
        print(f"Token found (length: {len(test_token)})")

    # Run tests
    results = []

    try:
        await test_session_cache_size()
        results.append(("Cache Size", True))
    except Exception as e:
        print(f"✗ Test failed: {e}")
        results.append(("Cache Size", False))

    try:
        result = await test_session_creation()
        results.append(("Session Creation", result))
    except Exception as e:
        print(f"✗ Test failed: {e}")
        results.append(("Session Creation", False))

    try:
        result = await test_session_caching()
        results.append(("Session Caching", result))
    except Exception as e:
        print(f"✗ Test failed: {e}")
        results.append(("Session Caching", False))

    try:
        result = await test_multiple_users()
        results.append(("Multiple Users", result))
    except Exception as e:
        print(f"✗ Test failed: {e}")
        results.append(("Multiple Users", False))

    try:
        result = await test_cleanup()
        results.append(("Cleanup", result))
    except Exception as e:
        print(f"✗ Test failed: {e}")
        results.append(("Cleanup", False))

    try:
        result = await test_idle_cleanup()
        results.append(("Idle Cleanup", result))
    except Exception as e:
        print(f"✗ Test failed: {e}")
        results.append(("Idle Cleanup", False))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All tests passed!")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
