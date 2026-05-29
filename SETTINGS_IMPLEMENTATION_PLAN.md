# Settings Page Implementation Plan

## Context

The Settings page (`frontend/gatekeeper/src/pages/Settings.jsx`) is currently a static mock UI with hardcoded values. The frontend API service and React Query hooks are already defined, but the backend endpoints are missing. This plan implements the complete backend infrastructure and integrates the frontend.

**Key Requirement:** Each user has their own Gemini API token and model preference. All Gemini API calls must use the logged-in user's personal settings.

**Existing Foundation:**
- Frontend API service (`frontend/gatekeeper/src/services/api.js`) - already has all methods defined
- React Query hooks (`frontend/gatekeeper/src/services/queries.js`) - already have hooks for settings
- API models (`api_models.py`) - models like `GeminiSettingsResponse`, `PolicySettingsResponse`, `UserResponse` exist
- Encryption service (`services/encryption_service.py`) - for secure token storage
- MongoDB client (`services/mongo_client.py`) - for persistent storage

## Implementation Plan

### 1. MongoDB Users Collection Schema

Create a single `users` collection in MongoDB with the following document structure:

```python
{
    "_id": "user_id_from_oauth",
    "profile": {
        "name": "John Doe",
        "username": "johndoe",
        "email": "john.doe@company.com",
        "avatar_url": "https://...",
        "created_at": "2024-01-01T00:00:00Z"
    },
    "gitlab": {
        "connected": true,
        "access_token": "encrypted_token",
        "refresh_token": "encrypted_refresh_token",
        "instance_url": "https://gitlab.com",
        "connected_at": "2024-01-01T00:00:00Z",
        "last_used": "2024-01-15T10:30:00Z"
    },
    "gemini": {
        "api_token_encrypted": "encrypted_gemini_token",
        "selected_model": "gemini-1.5-pro",
        "token_configured": true,
        "validated_at": "2024-01-15T10:30:00Z"
    },
    "preferences": {
        "auto_review_enabled": true,
        "strict_mode_enabled": false,
        "email_alerts_enabled": true,
        "max_review_depth": 5,
        "timeout_seconds": 300
    },
    "updated_at": "2024-01-15T10:30:00Z"
}
```

### 2. Create User Service (`services/user_service.py`)

Create a single service that manages everything in the `users` collection:

```python
# Key functions:
- get_user(user_id: str) -> dict  # Get full user document
- update_user(user_id: str, updates: dict) -> dict
- get_user_profile(user_id: str) -> UserResponse
- update_user_profile(user_id, profile: dict) -> UserResponse
- get_gemini_settings(user_id: str) -> GeminiSettingsResponse
- update_gemini_settings(user_id, api_token: str, model: str) -> GeminiSettingsResponse
- validate_gemini_token(token: str) -> ValidateTokenResponse  # Calls Google API directly
- get_policy_settings(user_id: str) -> PolicySettingsResponse
- update_policy_settings(user_id, settings: dict) -> PolicySettingsResponse
- get_gitlab_integration_status(user_id: str) -> IntegrationStatusResponse
- disconnect_gitlab_integration(user_id: str) -> dict
```

### 3. Update `services/__init__.py`

Add `user_service` to the imports so it can be used in `main.py`:
```python
from services import mcp_service, review_service, auth_service, repository_service, mongo_client, user_service
```

### 4. Add Backend Endpoints to `main.py`

Add the following endpoints after the repository endpoints section:

```python
# ============================================================================
# Settings Endpoints
# ============================================================================

@app.get("/api/settings/gemini", response_model=GeminiSettingsResponse)
@app.put("/api/settings/gemini", response_model=GeminiSettingsResponse)
@app.post("/api/settings/gemini/validate", response_model=ValidateTokenResponse)
@app.get("/api/settings/policies", response_model=PolicySettingsResponse)
@app.put("/api/settings/policies", response_model=PolicySettingsResponse)

# ============================================================================
# User Profile Endpoints
# ============================================================================

@app.get("/api/user/profile", response_model=UserResponse)
@app.put("/api/user/profile", response_model=UserResponse)

# ============================================================================
# Integrations Endpoints
# ============================================================================

# GitLab integration status (returns current OAuth session status from auth_service)
@app.get("/api/integrations/gitlab", response_model=IntegrationStatusResponse)

# Disconnect GitLab (clears session - essentially logout)
@app.delete("/api/integrations/gitlab")
```

Each endpoint should:
- Extract user_id from JWT token via `authorization` header
- Call the appropriate service function
- Return appropriate responses

### 5. Update API Models in `api_models.py`

Add request models for updates (already have response models):

```python
class UpdateGeminiSettingsRequest(BaseModel):
    api_token: Optional[str] = None
    selected_model: GeminiModel = GeminiModel.GEMINI_1_5_PRO

class UpdatePolicySettingsRequest(BaseModel):
    auto_review_enabled: bool
    strict_mode_enabled: bool
    email_alerts_enabled: bool
    max_review_depth: int = 5
    timeout_seconds: int = 300

class UpdateUserProfileRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
```

### 6. Update User Onboarding Flow

Update the OAuth callback and user creation flow to collect Gemini settings:

**In `auth_service.py` - Update `handle_oauth_callback`:**
- After successful GitLab OAuth, create/update user document with basic profile info
- User will complete Gemini setup in onboarding flow

**Frontend Onboarding Component:**
- After OAuth redirect, show onboarding form if Gemini not configured
- Collect: Gemini API token, Model selection preference
- Call `/api/settings/gemini` PUT endpoint to save settings
- Only proceed to main app after Gemini is configured

### 7. Update Review Service for Per-User Gemini

**In `services/review_service.py`:**
- Modify to fetch user's Gemini settings before making API calls
- Use the user's encrypted API token and selected model preference
- Pass user_id to review functions and look up their settings

```python
async def get_user_gemini_config(user_id: str) -> dict:
    """Get user's Gemini API token and model preference."""
    user = await user_service.get_user(user_id)
    if not user or not user.get("gemini", {}).get("api_token_encrypted"):
        raise HTTPException(400, "Gemini API not configured for user")
    return {
        "api_token": decrypt_value(user["gemini"]["api_token_encrypted"]),
        "model": user["gemini"].get("selected_model", "gemini-1.5-pro")
    }
```

### 8. Update Frontend Settings.jsx

Refactor the component to use React Query hooks:

**Changes:**
1. Import and use hooks from `services/queries.js`:
   - `useGeminiSettings()` - fetch Gemini settings
   - `useUpdateGeminiSettings()` - update Gemini settings
   - `useValidateGeminiToken()` - validate API token
   - `usePolicySettings()` - fetch policy settings
   - `useUpdatePolicySettings()` - update policy settings
   - `useUserProfile()` - fetch user profile
   - `useDisconnectGitLab()` - GitLab disconnect (logout)

2. Replace hardcoded state with API data:
   - Token from `geminiSettings.data` (masked)
   - Model from `geminiSettings.data.selected_model`
   - Toggles from `policySettings.data`
   - User info from `userProfile.data`

3. Add loading states with spinners
4. Add error states with retry buttons
5. Add success notifications after updates
6. Make "Save Changes" button actually call mutations

### Files to Modify/Create

| File | Action | Description |
|------|--------|-------------|
| `services/user_service.py` | Create | Single service for all user data (profile, settings, integrations) stored in `users` collection |
| `services/__init__.py` | Edit | Add `user_service` to imports |
| `services/auth_service.py` | Edit | Update OAuth callback to create user on first login |
| `services/review_service.py` | Edit | Use per-user Gemini token and model preference for API calls |
| `main.py` | Edit | Add settings, user, and integration endpoints |
| `api_models.py` | Edit | Add request models for updates |
| `frontend/gatekeeper/src/pages/Settings.jsx` | Edit | Integrate with React Query hooks |
| `frontend/gatekeeper/src/components/Onboarding.jsx` | Create | Collect Gemini settings during user onboarding |

### Key Patterns to Follow

**Authentication Pattern:**
```python
user_id = None
if authorization:
    token = authorization.replace("Bearer ", "")
    user_info = auth_service.verify_token(token)
    user_id = user_info.get("id")
```

**Encryption Pattern:**
```python
from services.encryption_service import encrypt_value, decrypt_value
encrypted_token = encrypt_value(api_token)
```

**MongoDB Pattern (users collection):**
```python
from services.mongo_client import get_mongo_session
mongo = await get_mongo_session()

# Get user document
user = await mongo.db.users.find_one({"_id": user_id})

# Update user document
await mongo.db.users.update_one(
    {"_id": user_id},
    {"$set": {"gemini.selected_model": "gemini-1.5-pro", "updated_at": datetime.utcnow()}}
)

# Create new user
await mongo.db.users.insert_one({
    "_id": user_id,
    "profile": {...},
    "gitlab": {...},
    "gemini": {...},
    "preferences": {...},
    "updated_at": datetime.utcnow()
})
```

**Frontend Mutation Pattern:**
```javascript
const updateMutation = useUpdateGeminiSettings();
const handleSubmit = async () => {
  await updateMutation.mutateAsync(formData);
  // Success notification
};
```

## Verification

1. Start the backend server and verify no import errors
2. Check `/api/settings/gemini` returns valid response with authentication
3. Check `/api/settings/policies` returns valid response
4. Check `/api/user/profile` returns user data
5. Test token validation via `/api/settings/gemini/validate`
6. In the frontend Settings page:
   - Verify data loads from API
   - Verify toggles update successfully
   - Verify token verification works
   - Verify model selection saves
   - Verify GitLab disconnect works
7. Test onboarding flow for new users
8. Verify review service uses per-user Gemini settings
