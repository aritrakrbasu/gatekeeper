import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../../../services/api", () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from "../../../services/api";
import { copilotApi } from "./copilotApi";

describe("copilotApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("createConversation posts to conversations endpoint", async () => {
    apiRequest.mockResolvedValue({ conversation_id: "conv-1" });

    const payload = { repository_id: "123", mr_iid: 42 };
    await copilotApi.createConversation(payload);

    expect(apiRequest).toHaveBeenCalledWith("/api/copilot/conversations", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  });

  it("getBootstrap fetches bootstrap endpoint", async () => {
    await copilotApi.getBootstrap("conv-1");
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/copilot/conversations/conv-1/bootstrap",
    );
  });

  it("getState fetches state endpoint", async () => {
    await copilotApi.getState("conv-1");
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/copilot/conversations/conv-1/state",
    );
  });

  it("getExecution fetches execution link endpoint", async () => {
    await copilotApi.getExecution("conv-1");
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/copilot/conversations/conv-1/execution",
    );
  });

  it("getConversations builds query string from filters", async () => {
    await copilotApi.getConversations({
      repository_id: "123",
      status: "running",
      page: 2,
      page_size: 10,
    });

    expect(apiRequest).toHaveBeenCalledWith(
      "/api/copilot/conversations?repository_id=123&status=running&page=2&page_size=10",
    );
  });

  it("getMrExecution fetches MR preflight endpoint", async () => {
    await copilotApi.getMrExecution("repo-1", 42);
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/repositories/repo-1/mrs/42/execution",
    );
  });

  it("getPendingApprovals builds approval query string", async () => {
    await copilotApi.getPendingApprovals({
      repository_id: "123",
      page: 1,
    });

    expect(apiRequest).toHaveBeenCalledWith(
      "/api/copilot/approvals/pending?repository_id=123&page=1",
    );
  });
});
