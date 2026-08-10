const TIME_WINDOW_LABELS: Record<string, string> = {
  morning: "Buổi sáng",
  afternoon: "Buổi chiều",
  evening: "Buổi tối",
  night: "Ban đêm",
  breakfast: "Bữa sáng",
  lunch: "Bữa trưa",
  dinner: "Bữa tối",
};

function normalizeTime(value: string): string {
  const trimmed = value.trim();
  if (/^\d{1,2}:\d{2}$/.test(trimmed)) {
    const [hours, minutes] = trimmed.split(":");
    return `${hours.padStart(2, "0")}:${minutes}`;
  }
  return trimmed;
}

/** Chuẩn hóa khung giờ từ dữ liệu legacy hoặc backend mới để hiển thị. */
export function formatItineraryTimeWindow(
  timeWindow: string | null | undefined,
): string | null {
  if (!timeWindow?.trim()) return null;

  const value = timeWindow.trim();
  const label = TIME_WINDOW_LABELS[value.toLowerCase()];
  if (label) return label;

  const range = value.split(/\s*(?:-|–|—|to|đến)\s*/i);
  if (range.length === 2 && range.every((part) => /^\d{1,2}:\d{2}$/.test(part))) {
    return `${normalizeTime(range[0])}–${normalizeTime(range[1])}`;
  }

  return value;
}

/** Tạo nhãn trợ năng đầy đủ cho badge khung giờ. */
export function itineraryTimeWindowAriaLabel(
  timeWindow: string | null | undefined,
): string | null {
  const formatted = formatItineraryTimeWindow(timeWindow);
  return formatted ? `Khung giờ: ${formatted}` : null;
}
