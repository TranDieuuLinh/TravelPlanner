import type { TripChat } from "@/features/planner/api/plans";

export type VisibleConversationMessage = {
  id: number | string;
  role: "assistant" | "user";
  text: string;
};

const LEGACY_PLAN_UPDATE_PATTERN =
  /^(?:Đã (?:tạo lịch trình|cập nhật lịch trình|cập nhật lịch trình hiện tại|thêm địa điểm|cập nhật thông tin địa điểm|xóa địa điểm|sắp xếp lại thứ tự địa điểm|chọn phương tiện|chọn .+ cho .+|xác minh thêm|hoàn tác thay đổi)|Đã xóa địa điểm .* khỏi danh sách chưa xếp lịch)/i;
const LEGACY_TRIP_THEME_ERROR = "TripThemePlanner cannot create trip themes";
const FRIENDLY_TRIP_THEME_ERROR =
  "Mình chưa thể lập lịch trình vì điểm đến này chưa có đủ địa điểm phù hợp; bạn hãy chọn một địa điểm cụ thể hoặc thử điểm đến khác.";

function normalizeAssistantMessage(content: string): string {
  return content.includes(LEGACY_TRIP_THEME_ERROR)
    ? FRIENDLY_TRIP_THEME_ERROR
    : content;
}

function isPlanUpdateMessage(
  message: TripChat["messages"][number]
): boolean {
  if (message.role !== "assistant") return false;
  if (message.messageKind === "plan_update") return true;
  if (message.contentBlocks?.some((block) => block.type === "planDiff")) {
    return true;
  }
  return (
    message.planRevision != null &&
    LEGACY_PLAN_UPDATE_PATTERN.test(message.content.trim())
  );
}

/**
 * The floating chat is a Q&A surface. Plan mutations remain available through
 * revision history and toasts, but their operational acknowledgements do not
 * appear as assistant answers.
 */
export function visibleConversationMessages(
  chat: Pick<TripChat, "messages">
): VisibleConversationMessage[] {
  return chat.messages
    .filter((message) => !isPlanUpdateMessage(message))
    .map((message) => ({
      id: message.id,
      role: message.role,
      text: [
        normalizeAssistantMessage(message.content),
        message.attachmentNames.length
          ? `📎 ${message.attachmentNames.length} ảnh`
          : "",
      ]
        .filter(Boolean)
        .join("\n"),
    }));
}
