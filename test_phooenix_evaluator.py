"""
Test script for Phoenix SDK Evaluator migration.

This script tests the new Phoenix SDK-based evaluator to ensure:
1. Module imports work correctly
2. Evaluator can be instantiated
3. Async evaluation functions work
4. Results are properly formatted
5. Fallback to legacy evaluator works
"""

import os
import sys
import asyncio
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Test data
SAMPLE_DIFF = """diff --git a/app.py b/app.py
index 1234567..abcdefg 100644
--- a/app.py
+++ b/app.py
@@ -10,7 +10,7 @@ def authenticate_user(username, password):
     conn = psycopg2.connect(connection_string)
     cursor = conn.cursor()

-    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
+    query = "SELECT * FROM users WHERE username=%s AND password=%s"
     cursor.execute(query, (username, password))
     result = cursor.fetchone()

@@ -25,6 +25,11 @@ def authenticate_user(username, password):

     return result

+def get_api_key():
+    # TODO: Move to environment variable
+    return "sk-1234567890abcdef"
+
 def main():
     user = authenticate_user("admin", "password123")
     if user:
"""

SAMPLE_REVIEW = """## Security Review

### 🔴 Critical Issues Found

1. **SQL Injection Vulnerability (FIXED)**
   - **Location**: Line 13 (before fix)
   - **Issue**: Original code used string concatenation for SQL query
   - **Severity**: CRITICAL
   - **Status**: ✅ The new code properly uses parameterized queries with `%s` placeholders
   - **Recommendation**: Good fix! The parameterized query prevents SQL injection.

2. **Hardcoded API Key**
   - **Location**: Lines 29-31
   - **Issue**: API key is hardcoded in source code (`sk-1234567890abcdef`)
   - **Severity**: CRITICAL
   - **Status**: ⚠️ This is a security vulnerability
   - **Recommendation**: Move the API key to environment variables:
     ```python
     import os
     api_key = os.getenv("API_KEY")
     if not api_key:
         raise ValueError("API_KEY environment variable not set")
     ```

### 🟡 Code Quality Observations

1. **Good Practices**:
   - ✅ Proper use of context manager (`with` statement) for database connection
   - ✅ Query parameters are properly passed as tuple
   - ✅ Clear function structure

2. **Suggestions**:
   - Consider using connection pooling for better performance
   - Add input validation for username format
   - Consider logging authentication attempts for audit trail

### Summary
- **Security Score**: 3/5 (Good catch on SQL injection fix, but hardcoded key remains)
- **Code Quality**: 4/5 (Clean code with room for optimization)
- **Actionability**: 5/5 (Specific code examples provided)
"""


async def test_1_imports():
    """Test 1: Verify all imports work correctly."""
    print("\n" + "="*60)
    print("TEST 1: Module Imports")
    print("="*60)

    try:
        from ai_observability import (
            PHOENIX_SDK_AVAILABLE,
            EvaluationCriteria,
            get_phoenix_sdk_evaluator,
            get_legacy_evaluator,
        )
        print(f"✅ Phoenix SDK Available: {PHOENIX_SDK_AVAILABLE}")

        # Check all criteria are available
        criteria_count = len(EvaluationCriteria)
        print(f"✅ EvaluationCriteria: {criteria_count} criteria defined")
        print(f"   {', '.join([c.value for c in EvaluationCriteria])}")

        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False


async def test_2_instantiation():
    """Test 2: Verify evaluator can be instantiated."""
    print("\n" + "="*60)
    print("TEST 2: Evaluator Instantiation")
    print("="*60)

    try:
        from ai_observability import get_phoenix_sdk_evaluator

        evaluator = get_phoenix_sdk_evaluator()
        print(f"✅ Evaluator type: {type(evaluator).__name__}")
        print(f"✅ Model: {evaluator.model}")
        print(f"✅ Concurrency: {evaluator.concurrency}")
        print(f"✅ Max retries: {evaluator.max_retries}")
        print(f"✅ Available evaluators: {len(evaluator.evaluators)}")

        # Check individual evaluators
        for name in evaluator.evaluators.keys():
            print(f"   - {name}")

        return True
    except Exception as e:
        print(f"❌ Instantiation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_3_evaluate_review():
    """Test 3: Run a full code review evaluation."""
    print("\n" + "="*60)
    print("TEST 3: Code Review Evaluation")
    print("="*60)

    try:
        from ai_observability import get_phoenix_sdk_evaluator, EvaluationCriteria

        evaluator = get_phoenix_sdk_evaluator()

        print("[*] Running evaluation (this may take 30-60 seconds)...")

        result = await evaluator.evaluate_review_async(
            diff=SAMPLE_DIFF,
            review=SAMPLE_REVIEW,
            criteria=[
                EvaluationCriteria.SECURITY_COVERAGE,
                EvaluationCriteria.CODE_QUALITY_COVERAGE,
                EvaluationCriteria.ACTIONABILITY,
                EvaluationCriteria.CLARITY,
            ],
            metadata={
                "test": True,
                "test_name": "phoenix_sdk_migration",
            }
        )

        print(f"\n✅ Evaluation completed!")
        print(f"\n📊 Results:")
        print(f"   Average Score: {result['average_score']}/5")
        print(f"   Criteria Evaluated: {result['criteria_evaluated']}")
        print(f"   Timestamp: {result['timestamp']}")

        print(f"\n📋 Individual Scores:")
        for eval_data in result['evaluations']:
            emoji = "🟢" if eval_data['score'] >= 4 else "🟡" if eval_data['score'] >= 3 else "🔴"
            print(f"   {emoji} {eval_data['criteria']}: {eval_data['score']}/5")
            if eval_data.get('explanation'):
                explanation = eval_data['explanation'][:100] + "..." if len(eval_data['explanation']) > 100 else eval_data['explanation']
                print(f"      {explanation}")

        # Verify expected score range
        if result['average_score'] >= 2 and result['average_score'] <= 5:
            print(f"\n✅ Score within expected range (2-5)")
        else:
            print(f"\n⚠️ Unexpected score: {result['average_score']}")

        return True
    except Exception as e:
        print(f"❌ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_4_formatting():
    """Test 4: Test markdown formatting."""
    print("\n" + "="*60)
    print("TEST 4: Markdown Formatting")
    print("="*60)

    try:
        from ai_observability import get_phoenix_sdk_evaluator, EvaluationCriteria

        evaluator = get_phoenix_sdk_evaluator()

        # Run evaluation first
        result = await evaluator.evaluate_review_async(
            diff=SAMPLE_DIFF[:500],  # Shorter for speed
            review=SAMPLE_REVIEW[:500],
            criteria=[EvaluationCriteria.SECURITY_COVERAGE],
        )

        # Format as markdown
        markdown = evaluator.format_evaluation_markdown(result)

        print("✅ Markdown formatting successful")
        print("\n📄 Sample Output (first 500 chars):")
        print(markdown[:500] + "...")

        return True
    except Exception as e:
        print(f"❌ Formatting failed: {e}")
        return False


async def test_5_fallback():
    """Test 5: Verify fallback to legacy evaluator."""
    print("\n" + "="*60)
    print("TEST 5: Legacy Fallback")
    print("="*60)

    try:
        from ai_observability import get_legacy_evaluator

        # This should work even if Phoenix SDK fails
        legacy_evaluator = get_legacy_evaluator()
        print(f"✅ Legacy evaluator type: {type(legacy_evaluator).__name__}")

        # Test that legacy evaluator still works
        result = await legacy_evaluator.evaluate_review(
            diff=SAMPLE_DIFF[:500],
            review=SAMPLE_REVIEW[:500],
            criteria=[EvaluationCriteria.SECURITY_COVERAGE],
        )

        print(f"✅ Legacy evaluation works!")
        print(f"   Average Score: {result['average_score']}/5")

        return True
    except Exception as e:
        print(f"❌ Legacy fallback failed: {e}")
        return False


async def test_6_auto_fix():
    """Test 6: Test auto-fix evaluation."""
    print("\n" + "="*60)
    print("TEST 6: Auto-Fix Evaluation")
    print("="*60)

    try:
        from ai_observability import get_phoenix_sdk_evaluator, EvaluationCriteria

        evaluator = get_phoenix_sdk_evaluator()

        SAMPLE_FIXES = """{
  "fixable": true,
  "fixes": [
    {
      "hunk_id": "hunk_1",
      "issue": "Hardcoded API key",
      "original_lines": ["    return \"sk-1234567890abcdef\""],
      "fixed_lines": ["    return os.getenv(\"API_KEY\")"],
      "extracted_env_vars": {"API_KEY": "sk-1234567890abcdef"}
    }
  ]
}"""

        print("[*] Running auto-fix evaluation...")

        result = await evaluator.evaluate_auto_fix_async(
            fixes=SAMPLE_FIXES,
            review=SAMPLE_REVIEW[:500],
            criteria=[
                EvaluationCriteria.FIX_CORRECTNESS,
                EvaluationCriteria.FIX_SAFETY,
            ],
        )

        print(f"\n✅ Auto-fix evaluation completed!")
        print(f"   Average Score: {result['average_score']}/5")

        for eval_data in result['evaluations']:
            print(f"   - {eval_data['criteria']}: {eval_data['score']}/5")

        return True
    except Exception as e:
        print(f"❌ Auto-fix evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "="*60)
    print("🧪 PHOENIX SDK EVALUATOR TEST SUITE")
    print("="*60)

    tests = [
        ("Module Imports", test_1_imports),
        ("Evaluator Instantiation", test_2_instantiation),
        ("Code Review Evaluation", test_3_evaluate_review),
        ("Markdown Formatting", test_4_formatting),
        ("Legacy Fallback", test_5_fallback),
        ("Auto-Fix Evaluation", test_6_auto_fix),
    ]

    results = []

    for name, test_func in tests:
        try:
            success = await test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ Test '{name}' crashed: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Phoenix SDK evaluator is working correctly.")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Please review the output above.")
        return 1


def main():
    """Main entry point."""
    print("Starting Phoenix SDK Evaluator tests...")
    print("This will take 1-2 minutes to complete.\n")

    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
