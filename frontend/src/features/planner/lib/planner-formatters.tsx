import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import type {
  ExplorerContext,
  PlaceCategory,
} from "@/features/planner/api/plans";
import { dateKeyForTripDay } from "@/features/planner/utils/plannerCoordinates";
import {
  sourceProviderKind,
  type SourceProviderKind,
} from "@/features/planner/lib/source-provider";

export function categoryFromPlaceType(placeType: string): PlaceCategory {
  const normalized = placeType
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  if (
    normalized.includes("food") ||
    normalized.includes("restaurant") ||
    normalized.includes("an uong") ||
    normalized.includes("am thuc") ||
    normalized.includes("nha hang")
  )
    return "food";
  if (
    normalized.includes("cafe") ||
    normalized.includes("coffee") ||
    normalized.includes("ca phe") ||
    normalized.includes("giai khat")
  )
    return "cafe";
  if (
    normalized.includes("hotel") ||
    normalized.includes("accommodation") ||
    normalized.includes("lodging")
  )
    return "hotel";
  if (
    normalized.includes("transport") ||
    normalized.includes("station") ||
    normalized.includes("transit")
  )
    return "transport";
  if (normalized.includes("break") || normalized.includes("free"))
    return "free_time";
  if (
    normalized.includes("museum") ||
    normalized.includes("culture") ||
    normalized.includes("temple") ||
    normalized.includes("heritage")
  )
    return "culture";
  if (
    normalized.includes("nature") ||
    normalized.includes("park") ||
    normalized.includes("garden")
  )
    return "nature";
  if (normalized.includes("shop") || normalized.includes("market"))
    return "shopping";
  if (normalized.includes("night") || normalized.includes("bar"))
    return "nightlife";
  if (normalized.includes("wellness") || normalized.includes("spa"))
    return "wellness";
  if (normalized.includes("adventure") || normalized.includes("hiking"))
    return "adventure";
  if (normalized.includes("beach")) return "beach";
  if (normalized.includes("family") || normalized.includes("zoo"))
    return "family";
  if (
    normalized.includes("attraction") ||
    normalized.includes("visit") ||
    normalized.includes("place")
  )
    return "attraction";
  return "other";
}

export function itineraryDisplayName(name: string): string {
  return name.replace(/^Điểm du lịch\s+/i, "").trim() || name;
}

export function handleDayTabKeyDown(event: ReactKeyboardEvent<HTMLDivElement>): void {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
    return;
  }

  const tabs = Array.from(
    event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')
  );
  const currentIndex = tabs.indexOf(
    document.activeElement as HTMLButtonElement
  );
  if (currentIndex < 0) return;

  event.preventDefault();
  const nextIndex =
    event.key === "Home"
      ? 0
      : event.key === "End"
      ? tabs.length - 1
      : (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) %
        tabs.length;
  tabs[nextIndex]?.focus();
  tabs[nextIndex]?.click();
}

export function dateLabelForTripDay(
  startDate: string | null | undefined,
  day: number
): string {
  const dateKey = dateKeyForTripDay(startDate, day);
  if (dateKey.startsWith("day-")) return `Ngày ${day}`;

  const [year, month, date] = dateKey.split("-");
  return `Ngày ${day} · ${date}/${month}/${year}`;
}

export function shortDateLabelForTripDay(
  startDate: string | null | undefined,
  day: number
): string | null {
  const dateKey = dateKeyForTripDay(startDate, day);
  if (dateKey.startsWith("day-")) return null;

  const [, month, date] = dateKey.split("-");
  return `${date}/${month}`;
}

export function budgetLevelLabel(
  level: ExplorerContext["tripIntent"]["budget"]["level"]
): string {
  return { low: "Thấp", medium: "Trung bình", high: "Cao" }[level];
}

export function geolocationErrorMessage(error: GeolocationPositionError): string {
  if (error.code === error.PERMISSION_DENIED) {
    return "Trình duyệt đang chặn quyền vị trí. Hãy cho phép vị trí trong phần quyền của trang rồi bấm lại icon định vị.";
  }
  if (error.code === error.POSITION_UNAVAILABLE) {
    return "Thiết bị chưa xác định được vị trí hiện tại.";
  }
  if (error.code === error.TIMEOUT) {
    return "Định vị mất quá nhiều thời gian. Vui lòng thử lại.";
  }
  return "Không thể lấy vị trí hiện tại.";
}

export type DeviceOrientationPermissionEvent = typeof DeviceOrientationEvent & {
  requestPermission?: () => Promise<PermissionState>;
};

type DeviceOrientationEventWithCompass = DeviceOrientationEvent & {
  webkitCompassHeading?: number;
};

export function normalizeDeviceHeading(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return ((value % 360) + 360) % 360;
}

export function headingFromOrientationEvent(
  event: DeviceOrientationEvent
): number | null {
  const iosHeading = (event as DeviceOrientationEventWithCompass)
    .webkitCompassHeading;
  const normalizedIosHeading = normalizeDeviceHeading(iosHeading);
  if (normalizedIosHeading != null) return normalizedIosHeading;
  const alphaHeading = normalizeDeviceHeading(event.alpha);
  return alphaHeading == null
    ? null
    : normalizeDeviceHeading(360 - alphaHeading);
}

export function itinerarySourceLabel(
  sourceRefs: string[],
  sourceProvider: string | null | undefined,
  source: string
): {
  kind: "url" | "selected";
  text: string;
  url?: string;
  provider: SourceProviderKind;
  displayUrl?: string;
} | null {
  for (const sourceRef of sourceRefs) {
    if (!sourceRef.startsWith("http://") && !sourceRef.startsWith("https://")) {
      continue;
    }
    const provider = sourceProviderKind(sourceRef, sourceProvider);
    if (!provider) continue;
    return {
      kind: "url",
      text: `${sourceProviderLabel(provider)} URL`,
      url: sourceRef,
      provider,
      displayUrl: compactSourceUrl(sourceRef),
    };
  }
  if (source === "selected_place") {
    return {
      kind: "selected",
      text: "Địa điểm đã chọn",
      provider: "url",
    };
  }
  return null;
}

export function sourceProviderLabel(provider: SourceProviderKind): string {
  if (provider === "youtube") return "YouTube";
  if (provider === "tiktok") return "TikTok";
  if (provider === "instagram") return "Instagram";
  return "Website";
}

export function compactSourceUrl(sourceUrl: string): string {
  try {
    const url = new URL(sourceUrl);
    const hostname = url.hostname.replace(/^www\./, "");
    const path = `${url.pathname}${url.search}`.replace(/\/$/, "");
    return `${hostname}${path}` || hostname;
  } catch {
    return sourceUrl;
  }
}

export function SourceProviderIcon({ provider }: { provider: SourceProviderKind }) {
  if (provider === "youtube") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M4.5 7.5c.2-1.1 1.1-2 2.2-2.2C8.4 5 12 5 12 5s3.6 0 5.3.3c1.1.2 2 1.1 2.2 2.2.3 1.4.3 4.5.3 4.5s0 3.1-.3 4.5c-.2 1.1-1.1 2-2.2 2.2-1.7.3-5.3.3-5.3.3s-3.6 0-5.3-.3c-1.1-.2-2-1.1-2.2-2.2-.3-1.4-.3-4.5-.3-4.5s0-3.1.3-4.5Z" />
        <path d="m10 9 5 3-5 3V9Z" />
      </svg>
    );
  }
  if (provider === "tiktok") {
    return (
      <svg
        aria-hidden="true"
        className="sourceProviderIconTikTok"
        viewBox="0 0 24 24"
      >
        <path
          className="sourceProviderIconTikTokCyan"
          d="M13.2 4v10.1a4.2 4.2 0 1 1-4.2-4.2"
        />
        <path
          className="sourceProviderIconTikTokCyan"
          d="M13.2 4c.7 2.7 2.4 4.4 5 4.9"
        />
        <path
          className="sourceProviderIconTikTokRed"
          d="M14.8 4.8v10.1a4.2 4.2 0 1 1-4.2-4.2"
        />
        <path
          className="sourceProviderIconTikTokRed"
          d="M14.8 4.8c.7 2.7 2.4 4.4 5 4.9"
        />
        <path
          className="sourceProviderIconTikTokBlack"
          d="M14 4.4v10.1a4.2 4.2 0 1 1-4.2-4.2"
        />
        <path
          className="sourceProviderIconTikTokBlack"
          d="M14 4.4c.7 2.7 2.4 4.4 5 4.9"
        />
      </svg>
    );
  }
  if (provider === "instagram") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <rect x="5" y="5" width="14" height="14" rx="4" />
        <circle cx="12" cy="12" r="3.2" />
        <path d="M16.8 7.4h.1" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.8 12h16.4M12 3.5c2.2 2.3 3.3 5.1 3.3 8.5S14.2 18.2 12 20.5M12 3.5C9.8 5.8 8.7 8.6 8.7 12s1.1 6.2 3.3 8.5" />
    </svg>
  );
}

export function paceLabel(pace: string): string {
  const normalized = pace.toLowerCase();
  if (normalized.includes("slow")) return "thư thả";
  if (normalized.includes("fast")) return "nhanh";
  if (normalized.includes("balance")) return "vừa phải";
  return pace;
}

export function isDisplayableImageUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

export function formatCompactCount(value: number): string {
  return new Intl.NumberFormat("vi-VN", { notation: "compact" }).format(value);
}

export function formatOpeningHoursForPlanDay(
  openingHours:
    | Array<{
        dayOfWeek?: number | null;
        rawTimeSlots?: string | null;
        openTime?: string | null;
        closeTime?: string | null;
        is24Hours?: boolean | null;
      }>
    | undefined,
  dayNumber: number,
  startDate?: string | null
): string | null {
  if (!openingHours?.length) return null;
  const dayOfWeek =
    dayOfWeekForTripDay(dayNumber, startDate) ?? currentDayOfWeekInVietnam();
  const entry = openingHours.find(
    (candidate) => openingHourDayNumber(candidate) === dayOfWeek
  );
  if (!entry) {
    return (
      formatOpeningHoursSchedule(openingHours)[0]?.value ??
      formatOpeningHoursSummary(openingHours)
    );
  }
  if (entry?.is24Hours) return "Mở cửa 24 giờ";
  return formatOpeningHourSlots(entry);
}

export function formatOpeningHoursSummary(
  openingHours: Array<{
    dayOfWeek?: number | null;
    dayName?: string | null;
    rawTimeSlots?: string | null;
    openTime?: string | null;
    closeTime?: string | null;
    is24Hours?: boolean | null;
  }>
): string | null {
  const normalized = openingHours
    .map((entry) => ({
      label: openingHourDayLabel(entry.dayName),
      value: entry.is24Hours ? "Mở cửa 24 giờ" : formatOpeningHourSlots(entry),
    }))
    .filter((entry): entry is { label: string | null; value: string } =>
      Boolean(entry.value)
    );
  if (normalized.length === 0) return null;
  const uniqueValues = new Set(normalized.map((entry) => entry.value));
  if (uniqueValues.size === 1) return normalized[0].value;
  return normalized
    .slice(0, 3)
    .map((entry) =>
      entry.label ? `${entry.label}: ${entry.value}` : entry.value
    )
    .join("; ");
}

export function formatOpeningHoursSchedule(
  openingHours:
    | Array<{
        dayOfWeek?: number | null;
        dayName?: string | null;
        rawTimeSlots?: string | null;
        openTime?: string | null;
        closeTime?: string | null;
        is24Hours?: boolean | null;
      }>
    | undefined
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
        value,
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

const FULL_OPENING_HOUR_DAY_LABELS: Record<number, string> = {
  1: "Thứ Hai",
  2: "Thứ Ba",
  3: "Thứ Tư",
  4: "Thứ Năm",
  5: "Thứ Sáu",
  6: "Thứ Bảy",
  7: "Chủ Nhật",
};

export function openingHourDayNumber(entry: {
  dayOfWeek?: number | null;
  dayName?: string | null;
}): number | null {
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
    cn: 7,
  };
  return dayNumbers[normalized] ?? null;
}

export function formatOpeningHourSlots(entry: {
  rawTimeSlots?: string | null;
  openTime?: string | null;
  closeTime?: string | null;
}): string | null {
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
    sunday: "CN",
  };
  return labels[normalized] ?? value?.trim() ?? null;
}

export function dayOfWeekForTripDay(
  dayNumber: number,
  startDate?: string | null
): number | null {
  if (!startDate) return null;
  const date = new Date(`${startDate}T12:00:00`);
  if (Number.isNaN(date.getTime())) return null;
  date.setDate(date.getDate() + Math.max(0, dayNumber - 1));
  const day = date.getDay();
  return day === 0 ? 7 : day;
}

export function currentDayOfWeekInVietnam(): number {
  const weekday = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Ho_Chi_Minh",
    weekday: "long",
  })
    .format(new Date())
    .toLowerCase();
  const dayNumbers: Record<string, number> = {
    monday: 1,
    tuesday: 2,
    wednesday: 3,
    thursday: 4,
    friday: 5,
    saturday: 6,
    sunday: 7,
  };
  return dayNumbers[weekday] ?? 1;
}
