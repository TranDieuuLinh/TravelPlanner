export type UrlOnlyInputResult =
  | { ok: true; urls: string[] }
  | { ok: false; message: string };

export const URL_SOURCE_ACTION_PROMPTS = [
  {
    label: "Tạo lịch trình từ liên kết",
    value: "Tạo lịch trình chuyến đi từ liên kết này",
  },
  {
    label: "Tóm tắt nội dung liên kết",
    value: "Tóm tắt nội dung liên kết này",
  },
] as const;

export function canSubmitPlannerSource(prompt: string, urls: string[]): boolean {
  return Boolean(prompt.trim()) && urls.length > 0;
}

export function parseUrlOnlyInput(value: string): UrlOnlyInputResult {
  const entries = value
    .split(/\s+/)
    .map((entry) => entry.trim())
    .filter(Boolean);

  if (entries.length === 0) {
    return { ok: false, message: "Dán ít nhất một URL để tiếp tục." };
  }

  if (entries.length > 20) {
    return { ok: false, message: "Mỗi lần chỉ có thể nhập tối đa 20 URL." };
  }

  const urls: string[] = [];
  for (const entry of entries) {
    try {
      const url = new URL(entry);
      if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error();
      urls.push(url.toString());
    } catch {
      return {
        ok: false,
        message: "Ô này chỉ nhận URL đầy đủ, ví dụ https://www.tiktok.com/…"
      };
    }
  }

  return { ok: true, urls: Array.from(new Set(urls)) };
}
