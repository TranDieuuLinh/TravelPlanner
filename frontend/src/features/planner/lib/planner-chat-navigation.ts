export function shouldApplyBackgroundChatResult(
  activeChatId: string | null,
  completedChatId: string,
): boolean {
  return activeChatId === completedChatId;
}

export function resolvePlannerEntryChatId(
  requestedChatId: string | null,
  hasPrefilledRequest: boolean,
  chatIds: readonly string[],
): string | null {
  if (hasPrefilledRequest) return null;
  if (requestedChatId && chatIds.includes(requestedChatId)) return requestedChatId;
  return null;
}
