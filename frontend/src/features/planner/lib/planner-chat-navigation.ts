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
  if (requestedChatId && chatIds.includes(requestedChatId)) return requestedChatId;
  if (hasPrefilledRequest) return null;
  return chatIds[0] ?? null;
}
