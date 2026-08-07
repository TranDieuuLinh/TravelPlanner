export type ConversationShortcut = {
  intent: "travel_advice";
  response: string;
};

const GREETINGS = new Set([
  "chào",
  "chào bạn",
  "hello",
  "hey",
  "hi",
  "hi bạn",
  "xin chào",
]);

const IDENTITY_QUESTIONS = new Set([
  "bạn là ai",
  "bạn là gì",
  "đây là đâu",
]);

const ORIGIN_QUESTIONS = new Set([
  "ai tạo ra bạn",
  "bạn đến từ đâu",
  "bạn được tạo ra ở đâu",
  "bạn ở đâu",
  "bạn sống ở đâu",
]);

const CAPABILITY_QUESTIONS = new Set([
  "bạn làm được gì",
  "bạn có thể giúp gì",
  "bạn có thể giúp gì cho tôi",
  "bạn giúp được gì",
]);

/**
 * Keep obvious guest small-talk out of the planning pipeline.
 *
 * Authenticated chat is classified by the server supervisor. Guest mode has
 * no durable chat/turn endpoint, so only exact, high-signal conversational
 * utterances are handled locally. Everything else keeps using Explorer.
 */
export function guestConversationShortcut(
  content: string,
): ConversationShortcut | null {
  const normalized = normalizeUtterance(content);
  if (GREETINGS.has(normalized)) {
    return {
      intent: "travel_advice",
      response:
        "Chào bạn! Mình có thể trò chuyện về chuyến đi, gợi ý điểm đến hoặc cùng bạn tạo lịch trình khi bạn muốn.",
    };
  }
  if (IDENTITY_QUESTIONS.has(normalized)) {
    return {
      intent: "travel_advice",
      response:
        "Mình là trợ lý du lịch TravelPlanner. Mình có thể tư vấn điểm đến và chỉ bắt đầu tạo lịch trình khi yêu cầu của bạn là một chuyến đi.",
    };
  }
  if (ORIGIN_QUESTIONS.has(normalized)) {
    return {
      intent: "travel_advice",
      response:
        "Mình là trợ lý AI của TravelPlanner nên không có quê quán hay nơi ở như con người. Mình ở đây để trò chuyện và giúp bạn khi bạn muốn lên kế hoạch du lịch.",
    };
  }
  if (CAPABILITY_QUESTIONS.has(normalized)) {
    return {
      intent: "travel_advice",
      response:
        "Mình có thể trò chuyện về du lịch, tìm địa điểm, đọc nguồn tham khảo và giúp bạn tạo hoặc chỉnh sửa lịch trình.",
    };
  }
  return null;
}

function normalizeUtterance(content: string): string {
  return content
    .normalize("NFC")
    .toLocaleLowerCase("vi")
    .trim()
    .replace(/[!?.,;:…]+$/gu, "")
    .trim()
    .replace(/\s+/gu, " ");
}
