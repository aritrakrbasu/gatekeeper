/**
 * React Query Setup for Gatekeeper Frontend
 *
 * Provides centralized query client configuration with caching,
 * retry logic, and automatic refetching strategies.
 */

import { QueryClient } from "@tanstack/react-query";

/**
 * Query client instance with optimized caching settings
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Time in milliseconds that data remains fresh (no refetch needed)
      staleTime: 5 * 60 * 1000, // 5 minutes

      // Time in milliseconds that unused cache entries are kept
      gcTime: 30 * 60 * 1000, // 30 minutes (previously cacheTime)

      // Number of retry attempts for failed requests
      retry: (failureCount, error) => {
        // Don't retry on 401 (auth errors) or 404 (not found)
        if (error?.status === 401 || error?.status === 404) {
          return false;
        }
        // Retry up to 2 times for other errors
        return failureCount < 2;
      },

      // Delay between retries (exponential backoff)
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),

      // Refetch on window focus (optional, can be disabled per query)
      refetchOnWindowFocus: false,

      // Refetch on component mount
      refetchOnMount: true,

      // Refetch on reconnect
      refetchOnReconnect: true,
    },

    mutations: {
      // Retry logic for mutations
      retry: false,

      // Don't throw errors automatically (handle in components)
      throwOnError: false,
    },
  },
});

/**
 * Query key factory for consistent cache keys across the app
 * Using a factory prevents typos and makes cache invalidation easier
 */
export const queryKeys = {
  // ============================================================================
  // Authentication
  // ============================================================================
  auth: {
    all: ["auth"],
    config: () => ["auth", "config"],
    verify: (token) => ["auth", "verify", token],
  },

  // ============================================================================
  // Repositories
  // ============================================================================
  repositories: {
    all: ["repositories"],
    lists: () => ["repositories", "list"],
    list: (filters) => ["repositories", "list", filters],
    details: () => ["repositories", "detail"],
    detail: (id) => ["repositories", "detail", id],
    mrs: (id) => ["repositories", id, "mrs"],
    policies: (id) => ["repositories", id, "policies"],
    available: (search) => ["repositories", "available", search],
    search: (query) => ["repositories", "search", query],
  },

  // ============================================================================
  // Dashboard
  // ============================================================================
  dashboard: {
    all: ["dashboard"],
    stats: () => ["dashboard", "stats"],
    recentMRs: (limit) => ["dashboard", "recent-mrs", limit],
    reposHealth: () => ["dashboard", "repos-health"],
  },

  // ============================================================================
  // Alerts
  // ============================================================================
  alerts: {
    all: ["alerts"],
    lists: () => ["alerts", "list"],
    list: (severity) => ["alerts", "list", severity],
  },

  // ============================================================================
  // Billing
  // ============================================================================
  billing: {
    all: ["billing"],
    usage: () => ["billing", "usage"],
    geminiCosts: () => ["billing", "gemini-costs"],
    invoices: () => ["billing", "invoices"],
  },

  // ============================================================================
  // Settings
  // ============================================================================
  settings: {
    all: ["settings"],
    gemini: () => ["settings", "gemini"],
    policies: () => ["settings", "policies"],
    profile: () => ["settings", "profile"],
  },

  // ============================================================================
  // Integrations
  // ============================================================================
  integrations: {
    all: ["integrations"],
    gitlab: () => ["integrations", "gitlab"],
    slack: () => ["integrations", "slack"],
  },
};
