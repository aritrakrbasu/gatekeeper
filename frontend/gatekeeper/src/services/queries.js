/**
 * React Query Hooks for Gatekeeper Frontend
 *
 * Custom hooks that wrap API calls with React Query for automatic
 * caching, refetching, and loading/error state management.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "./api";
import { queryKeys } from "./queryClient";

// ============================================================================
// Authentication Hooks
// ============================================================================

/**
 * Get OAuth configuration
 */
export function useAuthConfig() {
  return useQuery({
    queryKey: queryKeys.auth.config(),
    queryFn: api.getAuthConfig,
    staleTime: 30 * 60 * 1000, // 30 minutes - auth config rarely changes
  });
}

/**
 * Verify JWT token
 */
export function useVerifyToken(token) {
  return useQuery({
    queryKey: queryKeys.auth.verify(token),
    queryFn: () => api.verifyToken(token),
    enabled: !!token,
    retry: false,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Logout mutation
 */
export function useLogout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (token) => api.logout(token),
    onSuccess: () => {
      // Clear all queries on logout
      queryClient.clear();
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      localStorage.removeItem("user");
      window.location.href = "/login";
    },
  });
}

// ============================================================================
// Repository Hooks
// ============================================================================

/**
 * Get all repositories
 * @param {Object} options - Query options
 * @param {number} options.limit - Limit on number of repositories to return
 * @param {number} options.staleTime - How long data is fresh (default: 5 min)
 */
export function useRepositories(options = {}) {
  const { limit, staleTime } = options;
  return useQuery({
    queryKey: queryKeys.repositories.list(limit ? String(limit) : undefined),
    queryFn: () => api.getRepositories(limit),
    staleTime: staleTime || 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Get repository details
 * @param {string|number} id - Repository ID
 */
export function useRepository(id) {
  return useQuery({
    queryKey: queryKeys.repositories.detail(id),
    queryFn: () => api.getRepository(id),
    enabled: !!id,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Get repository merge requests
 * @param {string|number} repoId - Repository ID
 * @param {Object} options - Query options
 */
export function useRepositoryMRs(repoId, options = {}) {
  return useQuery({
    queryKey: queryKeys.repositories.mrs(repoId),
    queryFn: () => api.getRepositoryMRs(repoId),
    enabled: !!repoId,
    staleTime: options.staleTime || 2 * 60 * 1000, // 2 minutes - MRs change more often
    refetchInterval: options.refetchInterval || false,
  });
}

/**
 * Get repository policies
 * @param {string|number} repoId - Repository ID
 */
export function useRepositoryPolicies(repoId) {
  return useQuery({
    queryKey: queryKeys.repositories.policies(repoId),
    queryFn: () => api.getRepositoryPolicies(repoId),
    enabled: !!repoId,
    staleTime: 10 * 60 * 1000, // 10 minutes - policies rarely change
  });
}

/**
 * Get available repositories (for connection modal)
 * @param {string} searchQuery - Search filter
 * @param {boolean} enabled - Whether query is enabled
 */
export function useAvailableRepositories(searchQuery = "", enabled = true) {
  return useQuery({
    queryKey: queryKeys.repositories.available(searchQuery),
    queryFn: () => api.getAvailableRepositories(searchQuery),
    enabled,
    staleTime: 2 * 60 * 1000, // 2 minutes
  });
}

/**
 * Search repositories
 * @param {string} query - Search query
 * @param {boolean} enabled - Whether query is enabled
 */
export function useSearchRepositories(query, enabled = true) {
  return useQuery({
    queryKey: queryKeys.repositories.search(query),
    queryFn: () => api.searchRepositories(query),
    enabled: enabled && !!query && query.length > 2,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Import repository mutation
 */
export function useImportRepository() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (gitlabPath) => api.importRepository(gitlabPath),
    onSuccess: () => {
      // Invalidate and refetch repositories list
      queryClient.invalidateQueries({ queryKey: queryKeys.repositories.lists() });
    },
  });
}

/**
 * Scan repository mutation
 */
export function useScanRepository() {
  return useMutation({
    mutationFn: (repoId) => api.scanRepository(repoId),
  });
}

/**
 * Onboard repository mutation
 */
export function useOnboardRepository() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ repoId, data }) => api.onboardRepository(repoId, data),
    onSuccess: () => {
      // Invalidate repositories list
      queryClient.invalidateQueries({ queryKey: queryKeys.repositories.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.repositories.all });
    },
  });
}

/**
 * Update repository credentials mutation
 */
export function useUpdateRepositoryCredentials() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ repoId, data }) => api.updateRepositoryCredentials(repoId, data),
    onSuccess: (_, variables) => {
      // Invalidate the specific repository query to refresh connection status
      queryClient.invalidateQueries({ queryKey: queryKeys.repositories.detail(variables.repoId) });
    },
  });
}

/**
 * Connect repository mutation
 */
export function useConnectRepository() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (repoId) => api.connectRepository(repoId),
    onSuccess: () => {
      // Invalidate repositories and available repositories
      queryClient.invalidateQueries({ queryKey: queryKeys.repositories.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.repositories.all });
    },
  });
}

/**
 * Disconnect repository mutation
 */
export function useDisconnectRepository() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (repoId) => api.disconnectRepository(repoId),
    onSuccess: () => {
      // Invalidate repositories list
      queryClient.invalidateQueries({ queryKey: queryKeys.repositories.lists() });
    },
  });
}

// ============================================================================
// Dashboard Hooks
// ============================================================================

/**
 * Get dashboard stats
 * @param {Object} options - Query options
 */
export function useDashboardStats(options = {}) {
  return useQuery({
    queryKey: queryKeys.dashboard.stats(),
    queryFn: api.getDashboardStats,
    staleTime: options.staleTime || 3 * 60 * 1000, // 3 minutes
    refetchInterval: options.refetchInterval || 60 * 1000, // Auto-refresh every minute
  });
}

/**
 * Get recent merge requests
 * @param {number} limit - Number of MRs to fetch
 */
export function useRecentMRs(limit = 10) {
  return useQuery({
    queryKey: queryKeys.dashboard.recentMRs(limit),
    queryFn: () => api.getRecentMRs(limit),
    staleTime: 1 * 60 * 1000, // 1 minute - recent MRs change frequently
    refetchInterval: 30 * 1000, // Auto-refresh every 30 seconds
  });
}

/**
 * Get repositories health stats
 */
export function useReposHealth() {
  return useQuery({
    queryKey: queryKeys.dashboard.reposHealth(),
    queryFn: api.getReposHealth,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// ============================================================================
// Alerts Hooks
// ============================================================================

/**
 * Get alerts
 * @param {string} severity - Filter by severity
 */
export function useAlerts(severity) {
  return useQuery({
    queryKey: queryKeys.alerts.list(severity),
    queryFn: () => api.getAlerts(severity),
    staleTime: 1 * 60 * 1000, // 1 minute
    refetchInterval: 30 * 1000, // Auto-refresh every 30 seconds
  });
}

/**
 * Mark alert as read mutation
 */
export function useMarkAlertRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id) => api.markAlertRead(id),
    onSuccess: () => {
      // Invalidate alerts list
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.lists() });
    },
  });
}

/**
 * Dismiss alert mutation
 */
export function useDismissAlert() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id) => api.dismissAlert(id),
    onSuccess: () => {
      // Invalidate alerts list
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.lists() });
    },
  });
}

/**
 * Mark all alerts as read mutation
 */
export function useMarkAllAlertsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.markAllAlertsRead(),
    onSuccess: () => {
      // Invalidate alerts list
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.lists() });
    },
  });
}

// ============================================================================
// Billing Hooks
// ============================================================================

/**
 * Get billing usage
 */
export function useBillingUsage() {
  return useQuery({
    queryKey: queryKeys.billing.usage(),
    queryFn: api.getBillingUsage,
    staleTime: 60 * 60 * 1000, // 1 hour - billing data updates infrequently
  });
}

/**
 * Get Gemini costs
 */
export function useGeminiCosts() {
  return useQuery({
    queryKey: queryKeys.billing.geminiCosts(),
    queryFn: api.getGeminiCosts,
    staleTime: 60 * 60 * 1000, // 1 hour
  });
}

/**
 * Get invoices
 */
export function useInvoices() {
  return useQuery({
    queryKey: queryKeys.billing.invoices(),
    queryFn: api.getInvoices,
    staleTime: 60 * 60 * 1000, // 1 hour
  });
}

// ============================================================================
// Settings Hooks
// ============================================================================

/**
 * Get Gemini settings
 */
export function useGeminiSettings() {
  return useQuery({
    queryKey: queryKeys.settings.gemini(),
    queryFn: api.getGeminiSettings,
    staleTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Update Gemini settings mutation
 */
export function useUpdateGeminiSettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (settings) => api.updateGeminiSettings(settings),
    onSuccess: () => {
      // Invalidate settings query
      queryClient.invalidateQueries({ queryKey: queryKeys.settings.gemini() });
    },
  });
}

/**
 * Validate Gemini token mutation
 */
export function useValidateGeminiToken() {
  return useMutation({
    mutationFn: (token) => api.validateGeminiToken(token),
  });
}

/**
 * Get policy settings
 */
export function usePolicySettings() {
  return useQuery({
    queryKey: queryKeys.settings.policies(),
    queryFn: api.getPolicySettings,
    staleTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Update policy settings mutation
 */
export function useUpdatePolicySettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (settings) => api.updatePolicySettings(settings),
    onSuccess: () => {
      // Invalidate settings query
      queryClient.invalidateQueries({ queryKey: queryKeys.settings.policies() });
    },
  });
}

/**
 * Get user profile
 */
export function useUserProfile() {
  return useQuery({
    queryKey: queryKeys.settings.profile(),
    queryFn: api.getUserProfile,
    staleTime: 15 * 60 * 1000, // 15 minutes
  });
}

/**
 * Update user profile mutation
 */
export function useUpdateUserProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (profile) => api.updateUserProfile(profile),
    onSuccess: () => {
      // Invalidate profile query
      queryClient.invalidateQueries({ queryKey: queryKeys.settings.profile() });
    },
  });
}

// ============================================================================
// Integrations Hooks
// ============================================================================

/**
 * Connect GitLab mutation
 */
export function useConnectGitLab() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ accessToken, instanceUrl }) =>
      api.connectGitLab(accessToken, instanceUrl),
    onSuccess: () => {
      // Invalidate relevant queries
      queryClient.invalidateQueries({ queryKey: queryKeys.integrations.all });
    },
  });
}

/**
 * Disconnect GitLab mutation
 */
export function useDisconnectGitLab() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.disconnectGitLab(),
    onSuccess: () => {
      // Invalidate relevant queries
      queryClient.invalidateQueries({ queryKey: queryKeys.integrations.all });
    },
  });
}

/**
 * Connect Slack mutation
 */
export function useConnectSlack() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ webhookUrl, channel }) =>
      api.connectSlack(webhookUrl, channel),
    onSuccess: () => {
      // Invalidate relevant queries
      queryClient.invalidateQueries({ queryKey: queryKeys.integrations.all });
    },
  });
}

/**
 * Update Slack settings mutation
 */
export function useUpdateSlack() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ webhookUrl, channel }) =>
      api.updateSlack(webhookUrl, channel),
    onSuccess: () => {
      // Invalidate relevant queries
      queryClient.invalidateQueries({ queryKey: queryKeys.integrations.all });
    },
  });
}

/**
 * Submit feedback mutation
 */
export function useSubmitFeedback() {
  return useMutation({
    mutationFn: ({ repoId, mrId, vote, comment }) =>
      api.submitFeedback(repoId, mrId, vote, comment),
  });
}

/**
 * Get MR progress logs
 * @param {string|number} repoId - Repository ID
 * @param {string|number} mrIid - Merge Request IID
 * @param {Object} options - Query options
 */
export function useMRProgressLogs(repoId, mrIid, options = {}) {
  return useQuery({
    queryKey: ['mrProgress', repoId, mrIid],
    queryFn: () => api.getMRProgressLogs(repoId, mrIid),
    enabled: !!repoId && !!mrIid,
    staleTime: options.staleTime || 5 * 1000, // 5 seconds - logs update frequently
    refetchInterval: options.refetchInterval || 3000, // Poll every 3 seconds for new logs
  });
}
