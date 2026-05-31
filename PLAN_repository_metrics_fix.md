# Plan: Fix Repository Metrics Data in Cards

## Problem Summary
The repository cards in the frontend (`Repositories.jsx`) display four key metrics that are currently not being populated:
1. **MRs Analyzed** - Shows 0 instead of actual count
2. **Avg. Review Time** - Shows "0s" instead of actual time
3. **Auto-Fix MRs Opened** - Shows 0 instead of actual count
4. **Fixes Merged** - Shows 0 instead of actual count

## Root Cause Analysis

### Frontend Expectations (Repositories.jsx)
The frontend accesses these fields:
```jsx
// MRs Analyzed
{repo.metrics?.mrs_analyzed ?? repo.mrsAnalyzed ?? 0}

// Avg Review Time
{repo.metrics?.avg_review_time ?? repo.avgReviewTime ?? "0s"}

// Auto-Fix MRs Opened
{repo.metrics?.auto_fixes_proposed ?? repo.autoFixesProposed ?? 0}

// Fixes Merged
{repo.metrics?.fixes_merged ?? repo.fixesMerged ?? 0}
```

### Backend Current Output (repository_service.py:get_all_repositories)
The current implementation returns only basic fields:
```python
{
    "id": repo.get("id", ""),
    "name": repo.get("name", ""),
    "full_name": repo.get("full_name", ""),
    "visibility": repo.get("visibility", ""),
    "url": repo.get("url", ""),
    "last_sync": repo.get("last_sync", datetime.now().isoformat()),
    "health_score": repo.get("health_score", 100.0),
    "status": repo.get("status", "active"),
    "description": repo.get("description", ""),
    "created_at": repo.get("created_at", datetime.now().isoformat()),
    "target_branches": repo.get("target_branches", []),
}
```

**Missing fields:** `metrics` object containing all metric data.

## Solution

### 1. Backend Changes (repository_service.py)

#### A. Update `get_all_repositories()` function
Add the `metrics` field to the repository response object:

```python
# In get_all_repositories() around line 277-290
for repo in user_repos:
    repos.append({
        # ... existing fields ...
        "metrics": {
            "mrs_analyzed": repo.get("mrs_reviewed", 0),
            "avg_review_time": repo.get("avg_review_time", 0),
            "auto_fixes_proposed": repo.get("auto_fixes_proposed", 0),
            "fixes_merged": repo.get("fixes_merged", 0),
        }
    })
```

#### B. Update `get_repository()` function
Ensure consistency in the `stats` field or rename to `metrics`:

```python
# Currently returns "stats" but frontend expects "metrics"
# Either update frontend to use "stats" or backend to return "metrics"
```

### 2. Database Fields Required
The following fields should be stored in MongoDB for each repository:
- `mrs_reviewed` - Number of MRs analyzed (already exists)
- `avg_review_time` - Average time in minutes (already exists)
- `auto_fixes_proposed` - Number of auto-fix MRs created (needs to be added)
- `fixes_merged` - Number of auto-fixes successfully merged (needs to be added)

### 3. Implementation Steps

1. **Update backend `get_all_repositories()`** to include metrics object
2. **Initialize default values** for new metrics fields when repositories are created
3. **Add counters** in the MR processing workflow to track:
   - When an MR is analyzed (increment `mrs_reviewed`)
   - When an auto-fix MR is created (increment `auto_fixes_proposed`)
   - When an auto-fix MR is merged (increment `fixes_merged`)
4. **Test** that the frontend displays the data correctly

## Files to Modify

1. **services/repository_service.py**
   - `get_all_repositories()` - Add metrics to response
   - `connect_repository()` - Initialize new metric fields
   - `onboard_repository()` - Initialize new metric fields

2. **services/review_service.py** (if it exists)
   - Add logic to increment metrics when MRs are processed

3. **Frontend verification**
   - Confirm the data structure matches after backend changes

## Expected Data Structure After Fix

```json
{
  "id": "12345",
  "name": "my-repo",
  "metrics": {
    "mrs_analyzed": 42,
    "avg_review_time": "2.5",
    "auto_fixes_proposed": 8,
    "fixes_merged": 5
  },
  "last_sync": "2026-05-31T10:30:00Z",
  "status": "active",
  ...
}
```
