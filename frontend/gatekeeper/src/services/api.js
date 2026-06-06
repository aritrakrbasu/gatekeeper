/**
 * API Service for Gatekeeper Frontend
 *
 * Handles all HTTP requests to the backend API with automatic
 * authentication headers and error handling.
 */

// In development with Vite proxy, use empty string for relative URLs
// In production, use the full API URL
const API_BASE_URL =
  import.meta.env.MODE === "production"
    ? import.meta.env.VITE_API_URL || "http://localhost:8000"
    : "";

/**
 * Generic API wrapper that handles authentication and errors
 */
async function apiRequest(endpoint, options = {}) {
  const token = localStorage.getItem("access_token");

  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  // Add auth token if available (unless skipAuth is true)
  if (token && !options.skipAuth) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const config = {
    ...options,
    headers,
  };

  // Debug logging
  console.log(`[API] ${config.method || 'GET'} ${endpoint}`, {
    hasAuth: !!headers["Authorization"],
    skipAuth: options.skipAuth
  });

  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, config);

    // Handle 401 Unauthorized - token expired or invalid
    if (response.status === 401) {
      console.error(`[API] 401 Unauthorized on ${endpoint} - logging out...`);
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      localStorage.removeItem("user");
      window.location.href = "/login";
      throw new Error("Authentication expired. Please login again.");
    }

    // Handle other errors
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || errorData.message || "Request failed",
      );
    }

    return await response.json();
  } catch (error) {
    console.error("API Request Error:", error);
    throw error;
  }
}

/**
 * API Methods
 */
export const api = {
  // ============================================================================
  // Authentication
  // ============================================================================

  /**
   * Get OAuth configuration status
   */
  getAuthConfig: () => apiRequest("/api/auth/config"),

  /**
   * Initiate GitLab OAuth flow
   */
  initiateGitLabOAuth: () => apiRequest("/api/auth/gitlab", { method: "POST" }),

  /**
   * Handle OAuth callback
   */
  handleOAuthCallback: (code, state) =>
    apiRequest(`/api/auth/gitlab/callback?code=${code}&state=${state}`, {
      method: "GET",
    }),

  /**
   * Verify JWT token
   */
  verifyToken: (token) =>
    apiRequest("/api/auth/verify", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),

  /**
   * Logout user
   */
  logout: (token) =>
    apiRequest("/api/auth/logout", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),

  // ============================================================================
  // Repositories
  // ============================================================================

  /**
   * Get all repositories
   * @param {number} limit - Optional limit on number of repositories to return
   */
  getRepositories: (limit) => {
    const params = limit ? `?limit=${limit}` : "";
    return apiRequest(`/api/repositories${params}`);
  },

  /**
   * Get repository details
   */
  getRepository: (id) => apiRequest(`/api/repositories/${id}`),

  /**
   * Get repository merge requests
   */
  getRepositoryMRs: (id) => apiRequest(`/api/repositories/${id}/mrs`),

  /**
   * Get repository policies
   */
  getRepositoryPolicies: (id) => apiRequest(`/api/repositories/${id}/policies`),

  /**
   * Search repositories
   */
  searchRepositories: (query) =>
    apiRequest(`/api/repositories/search?q=${encodeURIComponent(query)}`),

  /**
   * Import new repository
   */
  importRepository: (gitlabPath) =>
    apiRequest("/api/repositories/import", {
      method: "POST",
      body: JSON.stringify({ gitlab_path: gitlabPath }),
    }),

  /**
   * Get available GitLab repositories (not yet connected)
   */
  getAvailableRepositories: (searchQuery = "") => {
    const params = searchQuery ? `?q=${encodeURIComponent(searchQuery)}` : "";
    return apiRequest(`/api/repositories/available${params}`);
  },

  /**
   * Scan repository for credentials
   */
  scanRepository: (repoId, branches = []) =>
    apiRequest(`/api/repositories/${repoId}/scan`, {
      method: "POST",
      body: JSON.stringify({ branches }),
    }),

  /**
   * Onboard repository and save credentials
   */
  onboardRepository: (repoId, data) =>
    apiRequest(`/api/repositories/${repoId}/onboard`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /**
   * Update repository credentials
   */
  updateRepositoryCredentials: (repoId, data) =>
    apiRequest(`/api/repositories/${repoId}/credentials`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  /**
   * Get repository branches
   */
  getRepositoryBranches: (repoId) =>
    apiRequest(`/api/repositories/${repoId}/branches`),

  /**
   * Connect a repository with optional branch selection
   */
  connectRepository: (repoId, targetBranches) =>
    apiRequest(`/api/repositories/${repoId}/connect`, {
      method: "POST",
      body: JSON.stringify({ target_branches: targetBranches }),
    }),

  /**
   * Disconnect a repository
   */
  disconnectRepository: (repoId) =>
    apiRequest(`/api/repositories/${repoId}/disconnect`, {
      method: "DELETE",
    }),

  // ============================================================================
  // Dashboard
  // ============================================================================

  /**
   * Get recent merge requests
   */
  getRecentMRs: (limit = 10) =>
    apiRequest(`/api/dashboard/recent-mrs?limit=${limit}`),

  /**
   * Get repository health stats
   */
  getReposHealth: () => apiRequest("/api/dashboard/repos-health"),

  /**
   * Get global dashboard stats
   */
  getDashboardStats: () => apiRequest("/api/dashboard/stats"),

  // ============================================================================
  // Alerts
  // ============================================================================

  /**
   * Get all alerts
   */
  getAlerts: (severity) => {
    const params = severity ? `?severity=${severity}` : "";
    return apiRequest(`/api/alerts${params}`);
  },

  /**
   * Mark alert as read
   */
  markAlertRead: (id) =>
    apiRequest(`/api/alerts/${id}/read`, { method: "PUT" }),

  /**
   * Dismiss/delete alert
   */
  dismissAlert: (id) => apiRequest(`/api/alerts/${id}`, { method: "DELETE" }),

  /**
   * Mark all alerts as read
   */
  markAllAlertsRead: () =>
    apiRequest("/api/alerts/mark-all-read", { method: "PUT" }),

  // ============================================================================
  // Billing
  // ============================================================================

  /**
   * Get billing usage statistics
   */
  getBillingUsage: () => apiRequest("/api/billing/usage"),

  /**
   * Get Gemini cost breakdown
   */
  getGeminiCosts: () => apiRequest("/api/billing/gemini-cost"),

  /**
   * Get invoice history
   */
  getInvoices: () => apiRequest("/api/billing/invoices"),

  /**
   * Download invoice PDF
   */
  downloadInvoice: (id) =>
    apiRequest(`/api/billing/invoices/${id}/download`, { method: "POST" }),

  /**
   * Sync billing data from Arize Cloud
   * Called after login to fetch usage data
   */
  syncBilling: (forceResync = false) =>
    apiRequest("/api/billing/sync", {
      method: "POST",
      body: JSON.stringify({ force_resync: forceResync }),
    }),

  // ============================================================================
  // Settings
  // ============================================================================

  /**
   * Get Gemini settings
   */
  getGeminiSettings: () => apiRequest("/api/settings/gemini"),

  /**
   * Update Gemini settings
   */
  updateGeminiSettings: (settings) =>
    apiRequest("/api/settings/gemini", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),

  /**
   * Validate Gemini API token
   */
  validateGeminiToken: (token) =>
    apiRequest("/api/settings/gemini/validate", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),

  /**
   * Get global policy settings
   */
  getPolicySettings: () => apiRequest("/api/settings/policies"),

  /**
   * Update global policy settings
   */
  updatePolicySettings: (settings) =>
    apiRequest("/api/settings/policies", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),

  /**
   * Get user profile
   */
  getUserProfile: () => apiRequest("/api/user/profile"),

  /**
   * Update user profile
   */
  updateUserProfile: (profile) =>
    apiRequest("/api/user/profile", {
      method: "PUT",
      body: JSON.stringify(profile),
    }),

  // ============================================================================
  // Integrations
  // ============================================================================

  /**
   * Connect GitLab integration
   */
  connectGitLab: (accessToken, instanceUrl) =>
    apiRequest("/api/integrations/gitlab", {
      method: "POST",
      body: JSON.stringify({
        access_token: accessToken,
        instance_url: instanceUrl,
      }),
    }),

  /**
   * Disconnect GitLab integration
   */
  disconnectGitLab: () =>
    apiRequest("/api/integrations/gitlab", { method: "DELETE" }),

  /**
   * Connect Slack integration
   */
  connectSlack: (webhookUrl, channel) =>
    apiRequest("/api/integrations/slack", {
      method: "POST",
      body: JSON.stringify({ webhook_url: webhookUrl, channel }),
    }),

  /**
   * Update Slack settings
   */
  updateSlack: (webhookUrl, channel) =>
    apiRequest("/api/integrations/slack", {
      method: "PUT",
      body: JSON.stringify({ webhook_url: webhookUrl, channel }),
    }),

  // ============================================================================
  // Sentry Integration
  // ============================================================================

  /**
   * Initiate Sentry OAuth flow for a repository
   */
  initiateSentryOAuth: (repoId) =>
    apiRequest("/api/auth/sentry/init", {
      method: "POST",
      body: JSON.stringify({ repo_id: repoId, user_id: localStorage.getItem("user_id") || "" }),
    }),

  /**
   * Complete Sentry OAuth callback
   */
  completeSentryOAuth: (code, state) =>
    apiRequest("/api/auth/sentry/callback", {
      method: "POST",
      body: JSON.stringify({ code, state }),
      skipAuth: true, // Skip auth header for Sentry callback (public route)
    }),

  /**
   * Get Sentry integration status for a repository
   */
  getSentryStatus: (repoId) =>
    apiRequest(`/api/auth/sentry/status/${repoId}`),

  /**
   * Verify Sentry webhook configuration
   */
  verifySentryWebhook: (repoId) =>
    apiRequest("/api/auth/sentry/verify-webhook", {
      method: "POST",
      body: JSON.stringify({ repo_id: repoId }),
    }),

  /**
   * Confirm Sentry webhook is working after manual verification
   */
  confirmSentryWebhook: (repoId) =>
    apiRequest("/api/auth/sentry/confirm-webhook", {
      method: "POST",
      body: JSON.stringify({ repo_id: repoId }),
    }),

  /**
   * Disconnect Sentry integration for a repository
   */
  disconnectSentry: (repoId) =>
    apiRequest(`/api/integrations/sentry/${repoId}/disconnect`, {
      method: "POST",
    }),

  // ============================================================================
  // Feedback
  // ============================================================================

  /**
   * Submit feedback on AI analysis
   */
  submitFeedback: (repoId, mrId, vote, comment) =>
    apiRequest(`/api/repositories/${repoId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ mr_id: mrId, vote, comment }),
    }),

  /**
   * Get MR progress logs
   */
  getMRProgressLogs: (repoId, mrIid) =>
    apiRequest(`/api/repositories/${repoId}/mrs/${mrIid}/progress`),
};

export default api;
