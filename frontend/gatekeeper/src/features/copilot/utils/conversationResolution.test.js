import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  clearConversationResolution,
  resolveConversationOnce,
} from "./conversationResolution";

describe("resolveConversationOnce", () => {
  beforeEach(() => {
    clearConversationResolution("repo-1", 42);
  });

  it("deduplicates concurrent resolution for the same repository and MR", async () => {
    const resolver = vi
      .fn()
      .mockImplementation(
        () =>
          new Promise((resolve) => {
            setTimeout(() => resolve("conv-1"), 10);
          }),
      );

    const [first, second] = await Promise.all([
      resolveConversationOnce("repo-1", 42, resolver),
      resolveConversationOnce("repo-1", 42, resolver),
    ]);

    expect(first).toBe("conv-1");
    expect(second).toBe("conv-1");
    expect(resolver).toHaveBeenCalledTimes(1);
  });

  it("reuses a cached conversation id without calling the resolver again", async () => {
    const resolver = vi.fn().mockResolvedValue("conv-1");

    await resolveConversationOnce("repo-1", 42, resolver);
    const cached = await resolveConversationOnce("repo-1", 42, resolver);

    expect(cached).toBe("conv-1");
    expect(resolver).toHaveBeenCalledTimes(1);
  });

  it("clears failed resolutions so a later attempt can retry", async () => {
    const failing = vi.fn().mockRejectedValue(new Error("network"));
    const succeeding = vi.fn().mockResolvedValue("conv-2");

    await expect(
      resolveConversationOnce("repo-1", 42, failing),
    ).rejects.toThrow("network");

    const conversationId = await resolveConversationOnce(
      "repo-1",
      42,
      succeeding,
    );

    expect(conversationId).toBe("conv-2");
    expect(failing).toHaveBeenCalledTimes(1);
    expect(succeeding).toHaveBeenCalledTimes(1);
  });
});
