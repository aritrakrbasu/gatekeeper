/**
 * Deduplicate Copilot conversation resolution across React Strict Mode
 * remounts and concurrent hook instances for the same repository/MR pair.
 */

const resolutionCache = new Map();

function cacheKey(repositoryId, mrIid) {
  return `${repositoryId}:${mrIid}`;
}

/**
 * Resolve a conversation id once per repository/MR scope.
 *
 * @param {string} repositoryId
 * @param {number|string} mrIid
 * @param {() => Promise<string>} resolver
 * @returns {Promise<string>}
 */
export async function resolveConversationOnce(repositoryId, mrIid, resolver) {
  const key = cacheKey(repositoryId, mrIid);
  const cached = resolutionCache.get(key);

  if (typeof cached === "string") {
    return cached;
  }

  if (cached instanceof Promise) {
    return cached;
  }

  const promise = resolver()
    .then((conversationId) => {
      resolutionCache.set(key, conversationId);
      return conversationId;
    })
    .catch((error) => {
      resolutionCache.delete(key);
      throw error;
    });

  resolutionCache.set(key, promise);
  return promise;
}

/**
 * Clear cached resolution when the drawer closes or MR context changes.
 */
export function clearConversationResolution(repositoryId, mrIid) {
  if (!repositoryId || !mrIid) {
    return;
  }
  resolutionCache.delete(cacheKey(repositoryId, mrIid));
}
