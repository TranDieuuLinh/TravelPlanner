import type { TripIntent } from "@/features/planner/api/plans";

export type GuidedIntakeStep =
  | "destination"
  | "dates"
  | "budget"
  | "travelers"
  | "note"
  | "complete";

export type GuidedIntakeAnswers = Partial<
  Record<Exclude<GuidedIntakeStep, "complete">, string>
>;

export type TravelerCounts = {
  adults: number;
  children: number;
  infants: number;
  pets: number;
};

export const guidedIntakeOrder: Exclude<GuidedIntakeStep, "complete">[] = [
  "destination",
  "dates",
  "travelers",
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
  travelers: "Bạn đi cùng ai?",
  note: "Có lưu ý gì không?",
};

export const travelerOptions: ReadonlyArray<{
  key: keyof TravelerCounts;
  label: string;
  description: string;
  minimum: number;
  maximum: number;
}> = [
  {
    key: "adults",
    label: "Người lớn",
    description: "Từ 13 tuổi",
    minimum: 1,
    maximum: 20,
  },
  {
    key: "children",
    label: "Trẻ em",
    description: "Từ 2–12 tuổi",
    minimum: 0,
    maximum: 20,
  },
  {
    key: "infants",
    label: "Em bé",
    description: "Dưới 2 tuổi",
    minimum: 0,
    maximum: 10,
  },
  {
    key: "pets",
    label: "Thú cưng",
    description: "Mang theo trong chuyến đi",
    minimum: 0,
    maximum: 5,
  },
];

export function travelerAnswer(counts: TravelerCounts): string {
  return [
    counts.adults ? `${counts.adults} người lớn` : "",
    counts.children ? `${counts.children} trẻ em` : "",
    counts.infants ? `${counts.infants} em bé` : "",
    counts.pets ? `${counts.pets} thú cưng` : "",
  ]
    .filter(Boolean)
    .join(", ");
}

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
    travelers: "Nhóm đi",
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
