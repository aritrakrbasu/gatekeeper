# Template Syntax Fix for Sentry Workflow

## Problem

The planner was generating invalid template expressions in `arguments_json` that broke validation:

```json
{
  "start_line": "{{gitnexus_grep_step.result.results[0].line+10}}"
}
```

This fails because:
1. `{{...line+10}}` contains arithmetic (`+10`) which is not a valid template expression
2. The executor can't resolve it, so it remains as a string
3. Tool schema validation expects an INTEGER, not a string
4. Result: `TypeError: Parameter 'start_line' must be an integer`

## Root Cause

The planner instruction was too vague about template syntax, allowing Gemini to generate:
- Arithmetic operations: `{{step_id.result.field+10}}`
- Complex array indexing: `{{step_id.result.results[0].filePath}}`
- Mixed expressions

## Solution

Updated `agents/planner.py` to specify strict template syntax rules:

### 1. Added Template Syntax Rules (lines 83-90)
```
TEMPLATE SYNTAX RULES (CRITICAL):
a. Use ONLY simple field references: '{{step_id.result.field}}'
b. NEVER use arithmetic: NO '{{step_id.result.field+10}}'
c. NEVER use array indexing: NO '{{step_id.result.results[0].field}}'
d. NEVER use complex expressions
e. If a step returns an array, pass the entire result: '{{step_id.result}}'
f. The executor will handle array extraction automatically
```

### 2. Updated gitnexus_file Step Instruction (lines 126-137)
Changed from:
```
Arguments: '{"file_path": "<path_from_grep_results>", "start_line": <optional>, "end_line": <optional>}'
```

To:
```
CRITICAL TEMPLATE SYNTAX RULES:
- Use ONLY simple field references: '{{step_id.result.field}}'
- NEVER use arithmetic or array indexing in templates
- For gitnexus_file, read the ENTIRE file (no start_line/end_line):
  Arguments: '{"file_path": "{{gitnexus_grep_step.result}}"}'
```

### 3. Updated MongoDB Path (lines 113-118)
Similar fixes for the MongoDB schema inspection workflow path.

### 4. Updated generate_fix Step (lines 146-157)
Explicit template syntax patterns for the fix generation step.

## How the Executor Resolves Templates

The `resolve_arguments` function in `agents/tools.py` supports:
- ✅ `{{step_id.result}}` - Simple reference
- ✅ `{{step_id.result.field}}` - Field access
- ✅ `{{step_id.result[0]}}` - Array indexing (with numbers only)
- ✅ `{{step_id.result[0].field}}` - Array + field access

But does NOT support:
- ❌ `{{step_id.result.field+10}}` - Arithmetic
- ❌ `{{step_id.result.field || "default"}}` - Logic operations
- ❌ `{{step_id.result.results[0].line+10}}` - Complex expressions

## Testing

After the fix, the planner should generate valid templates like:

```json
{
  "file_path": "{{gitnexus_grep_step.result}}"
}
```

Instead of invalid ones like:

```json
{
  "file_path": "{{gitnexus_grep_step.result.results[0].filePath}}",
  "start_line": "{{gitnexus_grep_step.result.results[0].line+10}}"
}
```

## Expected Behavior

1. Planner generates clean template references
2. Executor resolves templates to actual values
3. Tool validation passes with correct types
4. Tools execute successfully

## Files Modified

1. `agents/planner.py` - Updated template syntax rules in Sentry workflow instruction
