export type UrlPlaceCountReport = {
  candidateCount: number;
  persistedCount: number;
};

function safeCount(value: number): number {
  return Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0;
}

export function urlPlaceCountLabel(report: UrlPlaceCountReport): string {
  const uniqueSourceCount = safeCount(report.candidateCount);
  const displayedCount = Math.min(
    safeCount(report.persistedCount),
    uniqueSourceCount
  );

  if (uniqueSourceCount === 0) return "Chưa tìm thấy địa điểm";

  return `${displayedCount} trên ${uniqueSourceCount} được hiển thị`;
}
