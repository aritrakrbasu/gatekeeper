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
    status: MRStatus
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


class BillingUsageResponse(BaseModel):
    """Billing usage statistics response."""
    current_cycle_start: datetime
    current_cycle_end: datetime
    total_tokens: int
    total_mrs_processed: int
    estimated_cost: float
    model_usage: List[ModelUsage]


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
    GEMINI_1_5_PRO = "gemini-1.5-pro"
    GEMINI_1_5_FLASH = "gemini-1.5-flash"


class GeminiSettingsResponse(BaseModel):
    """Gemini API settings response."""
    api_token_configured: bool
    selected_model: GeminiModel
    model_options: List[GeminiModel] = [GeminiModel.GEMINI_1_5_PRO, GeminiModel.GEMINI_1_5_FLASH]


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
