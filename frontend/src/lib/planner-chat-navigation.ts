export function shouldApplyBackgroundChatResult(
  activeChatId: string | null,
  completedChatId: string,
): boolean {
  return activeChatId === completedChatId;
}
