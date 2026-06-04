"""
Pydantic models for API requests and responses.
Used for request validation and response serialization across all API endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ============================================================================
# Authentication Models
# ============================================================================

class OAuthRequest(BaseModel):
    """Request to initiate OAuth flow."""
    provider: str = Field(..., description="OAuth provider (e.g., 'gitlab')")


class OAuthCallbackRequest(BaseModel):
    """OAuth callback request with authorization code."""
    code: str = Field(..., description="Authorization code from OAuth provider")
    state: str = Field(..., description="State parameter for CSRF protection")


class UserResponse(BaseModel):
    """User profile response."""
    id: str
    name: str
    username: str
    email: str
    avatar_url: Optional[str] = None
    created_at: datetime


class TokenResponse(BaseModel):
    """JWT token response after successful authentication."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token expiration time in seconds")
    user: UserResponse


class VerifyTokenRequest(BaseModel):
    """Request to verify a JWT token."""
    token: str = Field(..., description="JWT token to verify")


class VerifyTokenResponse(BaseModel):
    """Response from token verification."""
    valid: bool
    user: Optional[UserResponse] = None
    message: Optional[str] = None


class LogoutResponse(BaseModel):
    """Response from logout endpoint."""
    message: str = "Successfully logged out"


# ============================================================================
# Repository Models (for future phases)
# ============================================================================

class RepositoryVisibility(str, Enum):
    """Repository visibility levels."""
    PUBLIC = "public"
    PRIVATE = "private"
    INTERNAL = "internal"


class RepositoryStatus(str, Enum):
    """Repository sync status."""
    ACTIVE = "active"
    SYNCING = "syncing"
    ERROR = "error"
    PENDING = "pending"


class RepositoryMetrics(BaseModel):
    """Repository metrics for analytics."""
    mrs_analyzed: int = 0
    avg_review_time: str = "0s"
    auto_fixes_proposed: int = 0
    fixes_merged: int = 0


class RepositoryResponse(BaseModel):
    """Repository information response."""
    id: str
    name: str
    full_name: str
    visibility: RepositoryVisibility
    url: str
    last_sync: Optional[datetime] = None
    health_score: Optional[float] = None
    status: RepositoryStatus
    description: Optional[str] = None
    created_at: datetime
    metrics: Optional[RepositoryMetrics] = None


# ============================================================================
# Merge Request Models
# ============================================================================

class MRStatus(str, Enum):
    """Merge request status."""
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"
    DRAFT = "draft"


class MergeRequestResponse(BaseModel):
    """Merge request response."""
    id: str
    iid: int
    title: str
    repository_id: str
    repository_name: str
    status: MRStatus
    author: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    web_url: str
    ai_summary: Optional[str] = None
    health_score: Optional[float] = None


# ============================================================================
# Alert Models
# ============================================================================

class AlertSeverity(str, Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertType(str, Enum):
    """Alert types."""
    SECURITY = "security"
    PERFORMANCE = "performance"
    BUG = "bug"
    CODE_QUALITY = "code_quality"
    DEPENDENCY = "dependency"


class AlertResponse(BaseModel):
    """Alert response."""
    id: str
    severity: AlertSeverity
    type: AlertType
    title: str
    repository_id: Optional[str] = None
    repository_name: Optional[str] = None
    description: str
    created_at: datetime
    unread: bool = True
    action_url: Optional[str] = None
    resolved: bool = False


class MarkAlertReadResponse(BaseModel):
    """Response after marking alert as read."""
    message: str = "Alert marked as read"


# ============================================================================
# Dashboard Models
# ============================================================================

class DashboardStatsResponse(BaseModel):
    """Dashboard statistics response."""
    issues_prevented_total: int
    issues_prevented_month: int
    avg_review_time: float
    code_health_score: float
    mrs_reviewed_total: int
    mrs_reviewed_month: int
    active_repositories: int


class RecentMRResponse(BaseModel):
    """Recent merge request for dashboard."""
    id: str
    title: str
    repository_name: str
    status: str  # Changed from MRStatus enum to str to support additional statuses like "reviewed", "reviewing"
    created_at: datetime
    web_url: str


class RepositoryHealthResponse(BaseModel):
    """Repository health summary for dashboard."""
    repository_id: str
    name: str
    health_score: float
    mrs_reviewed: int
    last_review: Optional[datetime] = None


# ============================================================================
# Billing Models
# ============================================================================

class ModelUsage(BaseModel):
    """Model-specific usage statistics."""
    model_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float


class DailyUsage(BaseModel):
    """Daily usage statistics for chart."""
    date: str  # ISO format date string
    tokens: int
    cost: float


class BillingUsageResponse(BaseModel):
    """Billing usage statistics response."""
    current_cycle_start: datetime
    current_cycle_end: datetime
    total_tokens: int
    total_mrs_processed: int
    estimated_cost: float  # Actual cost accumulated so far
    projected_monthly_cost: float = 0.0  # Projected cost for full month
    average_daily_cost: float = 0.0  # Average daily cost
    days_elapsed: int = 0  # Days with usage
    remaining_days: int = 0  # Remaining days in month
    model_usage: List[ModelUsage]
    daily_usage: List[DailyUsage] = []


class SyncRequest(BaseModel):
    """Request to sync usage data from Phoenix."""
    cycle: Optional[str] = None  # Specific cycle or current
    force_resync: bool = False


class InvoiceStatus(str, Enum):
    """Invoice status."""
    PAID = "paid"
    PENDING = "pending"
    FAILED = "failed"


class InvoiceResponse(BaseModel):
    """Invoice response."""
    id: str
    invoice_date: datetime
    amount: float
    currency: str = "USD"
    status: InvoiceStatus
    invoice_number: str
    pdf_url: Optional[str] = None


# ============================================================================
# Settings Models
# ============================================================================

class GeminiModel(str, Enum):
    """Available Gemini models."""
    GEMINI_3_5_FLASH = "gemini-3.5-flash"
    GEMINI_3_1_PRO_PREVIEW = "gemini-3.1-pro-preview"


class GeminiSettingsResponse(BaseModel):
    """Gemini API settings response."""
    api_token_configured: bool
    selected_model: GeminiModel
    model_options: List[GeminiModel] = [GeminiModel.GEMINI_3_5_FLASH, GeminiModel.GEMINI_3_1_PRO_PREVIEW]


class ValidateTokenRequest(BaseModel):
    """Request to validate Gemini API token."""
    token: str = Field(..., description="Gemini API token to validate")


class ValidateTokenResponse(BaseModel):
    """Response from token validation."""
    valid: bool
    message: str


class PolicySettingsResponse(BaseModel):
    """Global policy settings response."""
    auto_review_enabled: bool
    strict_mode_enabled: bool
    email_alerts_enabled: bool
    slack_integration_enabled: bool
    max_review_depth: int = 5
    timeout_seconds: int = 300


# ============================================================================
# Integration Models
# ============================================================================

class GitLabConnectRequest(BaseModel):
    """Request to connect GitLab integration."""
    access_token: str = Field(..., description="GitLab personal access token")
    instance_url: Optional[str] = Field("https://gitlab.com", description="GitLab instance URL")


class SlackConnectRequest(BaseModel):
    """Request to connect Slack integration."""
    webhook_url: str = Field(..., description="Slack incoming webhook URL")
    channel: Optional[str] = Field(None, description="Default channel for notifications")


class IntegrationStatusResponse(BaseModel):
    """Integration status response."""
    provider: str
    connected: bool
    configured_at: Optional[datetime] = None
    last_used: Optional[datetime] = None


# ============================================================================
# Settings Request Models
# ============================================================================


class UpdateGeminiSettingsRequest(BaseModel):
    """Request to update Gemini settings."""
    api_token: Optional[str] = None
    selected_model: GeminiModel = GeminiModel.GEMINI_3_5_FLASH


class UpdatePolicySettingsRequest(BaseModel):
    """Request to update policy settings."""
    auto_review_enabled: bool
    strict_mode_enabled: bool
    email_alerts_enabled: bool
    slack_integration_enabled: bool = False
    max_review_depth: int = 5
    timeout_seconds: int = 300


class UpdateUserProfileRequest(BaseModel):
    """Request to update user profile."""
    name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None


# ============================================================================
# Feedback Models
# ============================================================================

class FeedbackVote(str, Enum):
    """Feedback vote options."""
    UP = "up"
    DOWN = "down"


class SubmitFeedbackRequest(BaseModel):
    """Request to submit feedback on AI analysis."""
    mr_id: str
    vote: FeedbackVote
    comment: Optional[str] = Field(None, max_length=1000)


class FeedbackResponse(BaseModel):
    """Feedback submission response."""
    message: str = "Feedback submitted successfully"
    id: str


# ============================================================================
# Onboarding & Scan Models
# ============================================================================

class ScanRepositoryRequest(BaseModel):
    """Request to scan a repository for credentials with optional branch selection."""
    branches: Optional[List[str]] = Field(default_factory=list, description="Branches to scan for secrets")


class ScanRepositoryResponse(BaseModel):
    """Response from repository credentials scan."""
    mongodb_uri: Optional[str] = None
    fivetran_api_key: Optional[str] = None
    fivetran_api_secret: Optional[str] = None
    detected_in_files: List[str] = []
    branch_credentials: Optional[dict] = None
    all_mongodb_uris: Optional[List[dict]] = Field(default_factory=list)
    all_fivetran_keys: Optional[List[dict]] = Field(default_factory=list)
    all_fivetran_secrets: Optional[List[dict]] = Field(default_factory=list)


class OnboardRepositoryRequest(BaseModel):
    """Request to onboard a repository with connection credentials."""
    mongodb_uri: Optional[str] = None
    fivetran_api_key: Optional[str] = None
    fivetran_api_secret: Optional[str] = None
    encrypt_credentials: bool = True
    target_branch: Optional[str] = None  # Branch for webhooks to monitor
    branches: Optional[List[str]] = Field(default_factory=list, description="Branches to activate Gatekeeper for")
    branch_credentials: Optional[dict] = None


class UpdateRepositoryRequest(BaseModel):
    """Request to update repository credentials."""
    mongodb_uri: Optional[str] = None
    fivetran_api_key: Optional[str] = None
    fivetran_api_secret: Optional[str] = None
    encrypt_credentials: bool = True
    branches: Optional[List[str]] = Field(default_factory=list, description="Branches to activate Gatekeeper for")
    branch_credentials: Optional[dict] = None


class UpdateRepositoryResponse(BaseModel):
    """Response after updating repository credentials."""
    message: str
    mongodb_uri_configured: bool
    fivetran_key_configured: bool
    fivetran_secret_configured: bool
    credentials_encrypted: bool

