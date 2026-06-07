# GitNexus Multi-File Handling Fix

## Problem

When `gitnexus_grep` returns multiple file matches (e.g., 49 files containing "toString"), the original implementation failed because:

1. The template `{{gitnexus_grep_step.result}}` resolved to the entire result object
2. The `gitnexus_file` tool expected a single file path string
3. Validation failed: "Parameter 'file_path' must be a string"

## Solution

Implemented a multi-file fetching system that:

1. **Auto-extracts all file paths** from `gitnexus_grep` results
2. **Fetches all files** when given a list of paths
3. **Merges content** from all files into a combined result

## Changes Made

### 1. Executor Template Resolution (`agents/executor.py`)

Updated `resolve_arguments` to auto-extract all file paths from `gitnexus_grep` results:

```python
# AUTO-EXTRACTION: For gitnexus_grep results with no path, extract all filePaths
if not path and isinstance(res, dict) and 'results' in res and isinstance(res['results'], list):
    file_paths = []
    for result_item in res['results']:
        if 'filePath' in result_item:
            file_paths.append(result_item['filePath'])
    if file_paths:
        return file_paths  # Return list of all file paths
```

### 2. GitNexus File Tool Schema (`agents/tools.py`)

Updated schema to accept both single and multiple file paths:

```python
"file_path": {
    "oneOf": [
        {"type": "STRING"},
        {"type": "ARRAY", "items": {"type": "STRING"}}
    ],
    "description": "File path or array of multiple file paths"
}
```

### 3. GitNexus File Function (`agents/tools.py`)

Updated `gitnexus_file` to handle both cases:

```python
# Handle single file path (string)
if isinstance(file_path, str):
    return await call_gitnexus_file(file_path=file_path, ...)

# Handle multiple file paths (list/array)
if isinstance(file_path, list) and len(file_path) > 0:
    # Fetch all files and merge content
    merged_content = ""
    for path in file_path:
        result = await call_gitnexus_file(file_path=path, ...)
        merged_content += f"\nFILE: {path}\n{content}\n"
    return {"status": "success", "merged_content": merged_content, ...}
```

### 4. Base Tool Validation (`agents/base_tool.py`)

Updated validation to support `oneOf` schema types:

```python
# Handle oneOf (allows multiple types)
if "oneOf" in prop_def:
    for option in prop_def["oneOf"]:
        if self._check_type(value, option["type"]):
            return True
    raise TypeError(f"Parameter must be one of types: ...")
```

## How It Works Now

When the Sentry workflow runs:

1. **gitnexus_grep** returns 49 file matches:
   ```python
   {'results': [
       {'filePath': 'src/utils/timeDifference.js', 'line': 39, ...},
       {'filePath': 'src/utils/performanceMonitor.js', 'line': 38, ...},
       ...
   ]}
   ```

2. **Template resolution** extracts all file paths:
   ```python
   ['src/utils/timeDifference.js', 'src/utils/performanceMonitor.js', ...]
   ```

3. **gitnexus_file** fetches all 49 files and merges content:
   ```python
   {
       'status': 'success',
       'files_count': 49,
       'merged_content': '\nFILE: src/utils/timeDifference.js\n...\n\nFILE: src/utils/performanceMonitor.js\n...',
       'individual_files': [...]
   }
   ```

4. **generate_fix** uses the merged content to generate a fix

## Benefits

- ✅ Handles any number of file results from grep
- ✅ Provides full context from all relevant files
- ✅ No manual intervention needed
- ✅ Backward compatible (still works with single file paths)

## Testing

The workflow should now successfully:
1. Grep for error patterns
2. Fetch all matching files
3. Generate a fix based on complete context
4. Create MR with the fix

## Example Output

```
[INFO] gitnexus_file fetching 49 files...
[INFO] Fetching file 1/49: src/utils/timeDifference.js
[INFO] Fetching file 2/49: src/utils/performanceMonitor.js
...
[OK] gitnexus_file Successfully fetched 49 files
```

## Files Modified

1. `agents/executor.py` - Auto-extraction of file paths from grep results
2. `agents/tools.py` - Multi-file schema and implementation
3. `agents/base_tool.py` - oneOf validation support
