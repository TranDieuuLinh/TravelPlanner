import type { ExplorePlace } from "@/features/planner/api/plans";
import {
  isCarMode,
  isPublicTransitMode,
  isWalkingMode,
} from "@/features/planner/lib/transport-options";

export function formatCompactCount(value: number): string {
  if (value >= 1_000_000) return `${Number((value / 1_000_000).toFixed(1))}M`;
  if (value >= 1000) return `${Number((value / 1000).toFixed(1))}N`;
  return String(value);
}

export function formatMapDistance(distanceMeters: number): string {
  if (!Number.isFinite(distanceMeters) || distanceMeters <= 0) return "Khoảng cách đang cập nhật";
  return distanceMeters >= 1000
    ? `${(distanceMeters / 1000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} km`
    : `${Math.round(distanceMeters).toLocaleString("vi-VN")} m`;
}

export function mapNavigationModeLabel(mode: string): string {
  if (isWalkingMode(mode)) return "Đi bộ";
  if (isPublicTransitMode(mode)) return "Phương tiện công cộng";
  if (isCarMode(mode)) return "Ô tô";
  return "Tuyến đường";
}

export function formatOpeningHoursForDay(
  openingHours: ExplorePlace["openingHours"],
  dayLabel: string
): string | null {
  if (!openingHours?.length) return null;
  const dayIndex = dayIndexFromVietnameseLabel(dayLabel);
  const entry = openingHours.find((candidate) => (
    dayIndex != null && openingHourDayNumber(candidate) === dayIndex
  ));
  if (!entry) return formatOpeningHoursSummary(openingHours);
  if (entry?.is24Hours) return "Mở cửa 24 giờ";
  return formatOpeningHourSlots(entry);
}

export function formatOpeningHoursSchedule(
  openingHours: ExplorePlace["openingHours"]
): Array<{ dayOfWeek: number | null; label: string; value: string }> {
  if (!openingHours?.length) return [];

  return openingHours
    .map((entry) => {
      const dayOfWeek = openingHourDayNumber(entry);
      const value = entry.is24Hours
        ? "Mở cửa 24 giờ"
        : formatOpeningHourSlots(entry);
      if (!value) return null;
      return {
        dayOfWeek,
        label:
          (dayOfWeek != null && FULL_OPENING_HOUR_DAY_LABELS[dayOfWeek]) ||
          entry.dayName?.trim() ||
          "Ngày khác",
        value
      };
    })
    .filter(
      (
        entry
      ): entry is { dayOfWeek: number | null; label: string; value: string } =>
        entry != null
    )
    .sort(
      (left, right) =>
        (left.dayOfWeek ?? Number.MAX_SAFE_INTEGER) -
        (right.dayOfWeek ?? Number.MAX_SAFE_INTEGER)
    );
}

export const FULL_OPENING_HOUR_DAY_LABELS: Record<number, string> = {
  1: "Thứ Hai",
  2: "Thứ Ba",
  3: "Thứ Tư",
  4: "Thứ Năm",
  5: "Thứ Sáu",
  6: "Thứ Bảy",
  7: "Chủ Nhật"
};

export function formatOpeningHoursSummary(
  openingHours: NonNullable<ExplorePlace["openingHours"]>
): string | null {
  const normalized = openingHours
    .map((entry) => ({
      label: openingHourDayLabel(entry.dayName),
      value: entry.is24Hours ? "Mở cửa 24 giờ" : formatOpeningHourSlots(entry)
    }))
    .filter((entry): entry is { label: string | null; value: string } => Boolean(entry.value));
  if (normalized.length === 0) return null;
  const uniqueValues = new Set(normalized.map((entry) => entry.value));
  if (uniqueValues.size === 1) return normalized[0].value;
  return normalized
    .slice(0, 3)
    .map((entry) => entry.label ? `${entry.label}: ${entry.value}` : entry.value)
    .join("; ");
}

export function formatOpeningHourSlots(
  entry: NonNullable<ExplorePlace["openingHours"]>[number]
): string | null {
  const rawSlots = entry.rawTimeSlots?.trim();
  if (rawSlots) return rawSlots;

  const openTime = entry.openTime?.trim();
  const closeTime = entry.closeTime?.trim();
  if (openTime && closeTime) return `${openTime}–${closeTime}`;
  return openTime || closeTime || null;
}

export function openingHourDayLabel(value?: string | null): string | null {
  const normalized = value?.trim().toLowerCase();
  if (!normalized) return null;
  const labels: Record<string, string> = {
    monday: "T2",
    tuesday: "T3",
    wednesday: "T4",
    thursday: "T5",
    friday: "T6",
    saturday: "T7",
    sunday: "CN"
  };
  return labels[normalized] ?? value?.trim() ?? null;
}

export function openingHourDayNumber(
  entry: NonNullable<ExplorePlace["openingHours"]>[number]
): number | null {
  if (
    entry.dayOfWeek != null &&
    entry.dayOfWeek >= 1 &&
    entry.dayOfWeek <= 7
  ) {
    return entry.dayOfWeek;
  }

  const normalized = entry.dayName
    ?.trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
  if (!normalized) return null;
  const dayNumbers: Record<string, number> = {
    monday: 1,
    "thu hai": 1,
    "thu 2": 1,
    t2: 1,
    tuesday: 2,
    "thu ba": 2,
    "thu 3": 2,
    t3: 2,
    wednesday: 3,
    "thu tu": 3,
    "thu 4": 3,
    t4: 3,
    thursday: 4,
    "thu nam": 4,
    "thu 5": 4,
    t5: 4,
    friday: 5,
    "thu sau": 5,
    "thu 6": 5,
    t6: 5,
    saturday: 6,
    "thu bay": 6,
    "thu 7": 6,
    t7: 6,
    sunday: 7,
    "chu nhat": 7,
    cn: 7
  };
  return dayNumbers[normalized] ?? null;
}

export function dayIndexFromVietnameseLabel(value: string): number | null {
  const normalized = value.toLowerCase();
  if (normalized.includes("thứ hai")) return 1;
  if (normalized.includes("thứ ba")) return 2;
  if (normalized.includes("thứ tư")) return 3;
  if (normalized.includes("thứ năm")) return 4;
  if (normalized.includes("thứ sáu")) return 5;
  if (normalized.includes("thứ bảy")) return 6;
  if (normalized.includes("chủ nhật")) return 7;
  const dateMatch = value.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (dateMatch) {
    const date = new Date(
      Number(dateMatch[3]),
      Number(dateMatch[2]) - 1,
      Number(dateMatch[1])
    );
    const jsDay = date.getDay();
    return jsDay === 0 ? 7 : jsDay;
  }
  const currentDay = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Ho_Chi_Minh",
    weekday: "long"
  }).format(new Date());
  return openingHourDayNumber({ dayName: currentDay });
}

export function FitMapIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" />
    </svg>
  );
}

export function CompassIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="9" />
      <path d="m15.5 8.5-2.2 4.8-4.8 2.2 2.2-4.8z" />
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2" />
    </svg>
  );
}

export function CloseIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="m7 7 10 10M17 7 7 17" />
    </svg>
  );
}

export function DirectionsIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="m12 3 9 9-9 9-9-9z" />
      <path d="M8 12h7m-3-3 3 3-3 3" />
    </svg>
  );
}
