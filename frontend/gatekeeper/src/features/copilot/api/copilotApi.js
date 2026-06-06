/**
 * Copilot REST API client.
 *
 * Separate from the main api.js object — Copilot endpoints live here
 * to keep the feature module self-contained.
 */

import { apiRequest } from "../../../services/api";

function buildQueryString(params = {}) {
  const search = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  });

  const query = search.toString();
  return query ? `?${query}` : "";
}

export const copilotApi = {
  /**
   * Create a new Copilot conversation.
   * Supply exactly one of execution_id or mr_iid.
   */
  createConversation: (data) =>
    apiRequest("/api/copilot/conversations", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /**
   * Single-request hydration for a conversation screen.
   */
  getBootstrap: (conversationId) =>
    apiRequest(`/api/copilot/conversations/${conversationId}/bootstrap`),

  /**
   * LangGraph-derived conversation state snapshot.
   */
  getState: (conversationId) =>
    apiRequest(`/api/copilot/conversations/${conversationId}/state`),

  /**
   * Navigation link to ARIL execution / graph explorers.
   */
  getExecution: (conversationId) =>
    apiRequest(`/api/copilot/conversations/${conversationId}/execution`),

  /**
   * Paginated conversation listing with optional filters.
   */
  getConversations: (filters = {}) =>
    apiRequest(
      `/api/copilot/conversations${buildQueryString({
        repository_id: filters.repository_id,
        execution_id: filters.execution_id,
        status: filters.status,
        page: filters.page,
        page_size: filters.page_size,
      })}`,
    ),

  /**
   * Pending approval queue for the authenticated user.
   */
  getPendingApprovals: (filters = {}) =>
    apiRequest(
      `/api/copilot/approvals/pending${buildQueryString({
        repository_id: filters.repository_id,
        page: filters.page,
        page_size: filters.page_size,
      })}`,
    ),

  /**
   * MR execution preflight — checks whether Copilot can investigate this MR.
   */
  getMrExecution: (repositoryId, mrIid) =>
    apiRequest(`/api/repositories/${repositoryId}/mrs/${mrIid}/execution`),
};

export default copilotApi;
