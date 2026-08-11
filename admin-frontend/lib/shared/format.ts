export const STAGES = ["explorer", "planner", "finder", "checker", "workflow"];
export const STATUSES = ["running", "completed", "blocked", "failed", "passed", "draft"];

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(value));
}

export function durationLabel(milliseconds: number | null): string {
  if (milliseconds === null) return "—";
  if (milliseconds < 1_000) return `${milliseconds} ms`;
  return `${(milliseconds / 1_000).toFixed(milliseconds < 10_000 ? 1 : 0)} s`;
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    completed: "Hoàn tất",
    running: "Đang chạy",
    failed: "Thất bại",
    blocked: "Bị chặn",
    passed: "Đạt",
    warning: "Cảnh báo",
    draft: "Bản nháp"
  };
  return labels[status] ?? status;
}