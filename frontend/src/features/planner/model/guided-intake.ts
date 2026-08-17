import type { TripIntent } from "@/features/planner/api/plans";

export type GuidedIntakeStep =
  | "destination"
  | "dates"
  | "budget"
  | "note"
  | "complete";

export type GuidedIntakeAnswers = Partial<
  Record<Exclude<GuidedIntakeStep, "complete">, string>
>;

export const guidedIntakeOrder: Exclude<GuidedIntakeStep, "complete">[] = [
  "destination",
  "dates",
  "budget",
  "note",
];

export const guidedIntakeQuestions: Record<
  Exclude<GuidedIntakeStep, "complete">,
  string
> = {
  destination: "Bạn muốn đi đâu?",
  dates: "Khi nào bạn muốn đi?",
  budget: "Ngân sách của bạn?",
  note: "Có lưu ý gì không?",
};

export function budgetFromAnswer(
  answer: string,
  current: TripIntent["budget"]
): TripIntent["budget"] {
  const normalized = answer.trim().toLocaleLowerCase("vi-VN");
  const digits = normalized.replace(/[^\d]/g, "");
  let targetAmount = digits ? Number(digits) : null;
  const decimalMatch = normalized.match(
    /(\d+(?:[.,]\d+)?)\s*(triệu|tr|million)/
  );
  if (decimalMatch) {
    targetAmount = Math.round(
      Number(decimalMatch[1].replace(",", ".")) * 1_000_000
    );
  } else if (targetAmount != null && /\b(nghìn|ngàn|k)\b/.test(normalized)) {
    targetAmount *= 1_000;
  }
  const level = normalized.includes("cao")
    ? "high"
    : normalized.includes("thấp")
      ? "low"
      : normalized.includes("trung bình")
        ? "medium"
        : current.level;
  return { ...current, targetAmount, level };
}

export function buildGuidedIntakeRequest(
  answers: GuidedIntakeAnswers
): string {
  const labels: Record<Exclude<GuidedIntakeStep, "complete">, string> = {
    destination: "Điểm đến",
    dates: "Thời gian",
    budget: "Ngân sách",
    note: "Điều cần lưu ý",
  };
  const details = guidedIntakeOrder.flatMap((step) => {
    const value = answers[step]?.trim();
    return value && value !== "Bỏ qua" ? [`- ${labels[step]}: ${value}`] : [];
  });
  return details.length
    ? `Giúp mình lên kế hoạch chuyến đi.\n${details.join("\n")}`
    : "Giúp mình tạo một chuyến đi mới từ các nguồn đã nhập.";
}
