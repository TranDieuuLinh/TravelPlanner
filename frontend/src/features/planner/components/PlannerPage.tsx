"use client";

import {
  Fragment,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/features/auth/components/AuthProvider";
import { PenguinMascot } from "@/components/PenguinMascot";
import {
  PlannerChatComposer,
  PlannerChatHeader,
  PlannerChatMessages,
} from "@/features/planner/components/PlannerChatUI";
import { PlannerDiscoveryPanel } from "@/features/planner/components/PlannerDiscoveryPanel";
import { DestinationSourceLink } from "@/features/planner/components/DestinationSourceLink";
import { GroupPlanningPanel } from "@/features/planner/components/GroupPlanningPanel";
import {
  PlaceReviewsModal,
  type PlaceReviewsModalPlace,
} from "@/features/planner/components/PlaceReviewsModal";
import { APIError } from "@/shared/api/client";
import {
  addTripChatItem,
  calculateDayDirections,
  confirmTripChatCandidateResolution,
  createTripChat,
  createPlanFromExplorer,
  deleteAllTripChats,
  deleteUrlImportJob,
  deleteTripChat,
  enqueueTripChatUrls,
  enrichPlanRoutes,
  enrichTripChatRoutes,
  exploreFullIntake,
  getTripChat,
  listTripChats,
  listUrlImportJobs,
  removeTripChatItem,
  removeTripChatUnscheduledPlace,
  reorderTripChatItem,
  retryTripChatTransportLeg,
  searchPlaces,
  selectTripChatTransportOption,
  updateTripChatIntent,
  updateTripChatItem,
  type PlaceSuggestion,
  type ExplorerContext,
  type ExploreResponse,
  type PlaceCategory,
  type TransportOption,
  type TransportLeg,
  type TripChat,
  type TripIntent,
  type TripChatSummary,
  type UnscheduledPlace,
  type TripChatTurn,
  type UrlImportJob,
  type TravelPlan,
} from "@/features/planner/api/plans";
import { useConversationTurn } from "@/features/planner/hooks/useConversationTurn";
import {
  enqueueGuestUrlJobs,
  enqueueGuestPromptJob,
  deleteGuestUrlJob,
  GUEST_URL_JOBS_EVENT,
  GUEST_URL_JOB_RESULT_EVENT,
  listGuestUrlJobs,
  type GuestUrlImportJob,
} from "@/features/planner/lib/guest-url-jobs";
import {
  PlannerMap,
  type PlannerMapCurrentLocation,
  type PlannerMapPlace,
  type PlannerMapRoute,
  type PlannerMapSearchPlace,
} from "@/features/planner/components/PlannerMap";
import { createDayColorMap } from "@/features/planner/lib/day-colors";
import {
  isAvailableTransportOption,
  isCarMode,
  isPublicTransitMode,
  isWalkingMode,
  resolveSelectedTransportOption,
  transportOptionSelectionKey,
  visibleTransportOptions,
} from "@/features/planner/lib/transport-options";
import { visiblePlanDays, visiblePlanItems } from "@/features/planner/lib/visible-plan-days";
import {
  formatPlanNote,
  formatSourceNoteForDisplay,
  planItemNotePresentation,
} from "@/features/planner/lib/plan-note";
import { planItemMapKey } from "@/features/planner/lib/plan-map-key";
import { rebaseItineraryItemOrder } from "@/features/planner/lib/itinerary-order";
import {
  itinerarySearchResultKey,
  searchItineraryPlaces,
  type ItinerarySearchResult,
} from "@/features/planner/lib/itinerary-search";
import {
  resolvePlannerEntryChatId,
  shouldApplyBackgroundChatResult,
} from "@/features/planner/lib/planner-chat-navigation";
import { dragAutoScrollVelocity } from "@/features/planner/lib/drag-auto-scroll";
import { parseUrlOnlyInput } from "@/features/planner/lib/url-only-input";
import { guestConversationShortcut } from "@/features/planner/lib/conversation-shortcuts";
import { visibleConversationMessages } from "@/features/planner/lib/conversation-messages";
import {
  addTripDays,
  defaultTripEndDate,
  formatPlannerDate,
  tripDaysBetween,
} from "@/features/planner/utils/plannerDates";
import {
  dateKeyForTripDay,
  hasPlanItemCoordinates,
} from "@/features/planner/utils/plannerCoordinates";
import {
  planLegSelectionKey,
  planPlaceNamesMatch,
  selectedTransportOption,
  transportLegsMatch,
  transportOptionsForLeg,
} from "@/features/planner/utils/transportSelection";
import {
  formatItineraryTimeWindow,
  itineraryTimeWindowAriaLabel,
} from "@/features/planner/lib/time-window";
import {
  sourceProviderKind,
  type SourceProviderKind,
} from "@/features/planner/lib/source-provider";

import {
  categoryFromPlaceType,
  itineraryDisplayName,
  handleDayTabKeyDown,
  dateLabelForTripDay,
  shortDateLabelForTripDay,
  budgetLevelLabel,
  geolocationErrorMessage,
  normalizeDeviceHeading,
  headingFromOrientationEvent,
  itinerarySourceLabel,
  sourceProviderLabel,
  compactSourceUrl,
  SourceProviderIcon,
  paceLabel,
  isDisplayableImageUrl,
  formatCompactCount,
  formatOpeningHoursForPlanDay,
  formatOpeningHoursSummary,
  formatOpeningHoursSchedule,
  openingHourDayNumber,
  formatOpeningHourSlots,
  openingHourDayLabel,
  dayOfWeekForTripDay,
  currentDayOfWeekInVietnam,
} from "@/features/planner/lib/planner-formatters";
import type { DeviceOrientationPermissionEvent } from "@/features/planner/lib/planner-formatters";
import {
  transportModeLabel,
  transportLegAfterItem,
  planTransportRouteMapKey,
  directionTransportRouteMapKey,
  promoteTransportOptionInPlan,
  isDevelopmentTransitFixture,
  isDrawableTransportRoute,
  hasValidGeometryCoordinates,
  formatDistance,
  formatDuration,
} from "@/features/planner/lib/planner-transport";
import {
  ItineraryReviewRating,
  UnscheduledPlacesSection,
} from "@/features/planner/components/PlannerSubcomponents";
import { TripProjectSidebar } from "@/features/planner/components/TripProjectSidebar";
import { GuidedIntakeDialog } from "@/features/planner/components/GuidedIntakeDialog";
import {
  ChevronDownIcon,
  CloseIcon,
  ClockIcon,
  SidebarIcon,
  HistoryMenuButton,
  MapPinIcon,
  NewChatIcon,
  TrashIcon,
  TransportModeIcon,
  TransportOptionCard,
} from "@/features/planner/components/PlannerIcons";

type ChatMessage = {
  id: number | string;
  role: "assistant" | "user";
  text: string;
};

type PlannerToast = {
  id: number;
  text: string;
};

type ActivePlanningJob = { id: string; guest: boolean };

type WorkflowStage =
  | "idle"
  | "classifying"
  | "preparing"
  | "exploring"
  | "planning"
  | "ready"
  | "failed";
type GuidedIntakeStep =
  | "destination"
  | "dates"
  | "budget"
  | "travelers"
  | "note"
  | "complete";
type GuidedIntakeAnswers = Partial<
  Record<Exclude<GuidedIntakeStep, "complete">, string>
>;
type TravelerCounts = {
  adults: number;
  children: number;
  infants: number;
  pets: number;
};
type LocationStatus = "idle" | "locating" | "ready" | "error";
type PlaceLocationTarget = "add" | "edit";
type DirectionsStatus = "idle" | "routing" | "ready" | "error";

const DESTINATION_NOTE_LABELS: Record<string, string> = {
  destination_traffic: "Giao thông đông đúc và khó đoán",
  destination_transport: "Sử dụng Grab hoặc Xanh SM",
  destination_water: "Không uống nước máy",
  destination_security: "Luôn giữ tư trang bên mình",
  destination_pricing: "Thỏa thuận tổng giá trước",
  destination_etiquette: "Tôn trọng đền chùa và địa điểm văn hóa",
  destination_train_safety: "Phố đường tàu vẫn đang hoạt động",
};

function destinationNoteLabel(type: string, index: number) {
  return DESTINATION_NOTE_LABELS[type] ?? `Ghi chú địa phương ${index + 1}`;
}

type FloatingChatRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type ChatResizeDirection = "n" | "ne" | "e" | "se" | "s" | "sw" | "w" | "nw";

type ChatPointerInteraction = {
  mode: "move" | "resize";
  resizeDirection?: ChatResizeDirection;
  pointerId: number;
  startX: number;
  startY: number;
  rect: FloatingChatRect;
};

type MobileItineraryDrag = {
  pointerId: number;
  startY: number;
};

type TripPlaceSummary = TravelPlan["days"][number]["items"][number] & {
  day: number;
  order: number;
  mapKey: string | null;
};

type DirectionStop = {
  itemId?: string | null;
  name: string;
  address?: string | null;
  latitude: number;
  longitude: number;
  mapKey: string | null;
};

const guidedIntakeOrder: Exclude<GuidedIntakeStep, "complete">[] = [
  "destination",
  "dates",
  "travelers",
  "budget",
  "note",
];

const guidedIntakeQuestions: Record<
  Exclude<GuidedIntakeStep, "complete">,
  string
> = {
  destination: "Bạn muốn đi đâu?",
  dates: "Khi nào bạn muốn đi?",
  budget: "Ngân sách của bạn?",
  travelers: "Bạn đi cùng ai?",
  note: "Có lưu ý gì không?",
};

const guidedIntakePlaceholders: Record<
  Exclude<GuidedIntakeStep, "complete">,
  string
> = {
  destination: "Ví dụ: Kyoto, Đà Lạt, miền Tây…",
  dates: "Ví dụ: 12–15/09 hoặc cuối tuần sau…",
  budget: "Ví dụ: khoảng 8 triệu cho cả nhóm…",
  travelers: "Ví dụ: 2 người lớn và 1 bé…",
  note: "Thêm một lưu ý nếu có…",
};

const travelerOptions: ReadonlyArray<{
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

function travelerAnswer(counts: TravelerCounts): string {
  return [
    counts.adults ? `${counts.adults} người lớn` : "",
    counts.children ? `${counts.children} trẻ em` : "",
    counts.infants ? `${counts.infants} em bé` : "",
    counts.pets ? `${counts.pets} thú cưng` : "",
  ]
    .filter(Boolean)
    .join(", ");
}

const NEW_CHAT_GREETING = "Dán link hoặc mô tả chuyến đi để mình plan du lịch.";

const URL_PATTERN = /https?:\/\/[^\s<>"']+/i;
const URL_PATTERN_GLOBAL = /https?:\/\/[^\s<>"']+/gi;
const ITINERARY_NO_IMAGE_SRC = "/images/penguin-no-image.png";
const UNSCHEDULED_PLAN_DAY = -1;
const GROUP_PLAN_DAY = -2;
const ITINERARY_MIN_PERCENT = 28;
const ITINERARY_MAX_PERCENT = 68;
const FLOATING_CHAT_MARGIN = 8;
const FLOATING_CHAT_MIN_WIDTH = 300;
const FLOATING_CHAT_MIN_HEIGHT = 320;
const FLOATING_CHAT_COLLAPSED_SIZE = 116;
const CHAT_RESIZE_HANDLES: ReadonlyArray<{
  direction: ChatResizeDirection;
  label: string;
}> = [
  { direction: "n", label: "Đổi chiều cao từ cạnh trên" },
  { direction: "ne", label: "Đổi kích thước từ góc trên bên phải" },
  { direction: "e", label: "Đổi chiều rộng từ cạnh phải" },
  { direction: "se", label: "Đổi kích thước từ góc dưới bên phải" },
  { direction: "s", label: "Đổi chiều cao từ cạnh dưới" },
  { direction: "sw", label: "Đổi kích thước từ góc dưới bên trái" },
  { direction: "w", label: "Đổi chiều rộng từ cạnh trái" },
  { direction: "nw", label: "Đổi kích thước từ góc trên bên trái" },
];
function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

function formatBudget(result: ExplorerContext): string {
  const budget = result.tripIntent.budget;
  const formatter = new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: budget.currency,
    maximumFractionDigits: 0,
  });

  if (budget.targetAmount != null) {
    return `Khoảng ${formatter.format(budget.targetAmount)}`;
  }
  return "Chưa có số tiền ước tính";
}

function formatTripTiming(
  timing: ExplorerContext["tripIntent"]["timing"]
): string {
  if (timing.startDate && timing.endDate) {
    return `${formatPlannerDate(timing.startDate)} – ${formatPlannerDate(
      timing.endDate
    )}`;
  }
  if (timing.startDate) {
    return `Từ ${formatPlannerDate(timing.startDate)}`;
  }
  if (timing.endDate) {
    return `Đến ${formatPlannerDate(timing.endDate)}`;
  }
  return `${timing.days} ngày`;
}

function formatTripParty(
  party: ExplorerContext["tripIntent"]["travelParty"]
): string {
  return travelerAnswer(party) || "Chưa xác định";
}

function formatTripBudget(intent: TripIntent): string {
  if (intent.budget.targetAmount != null) {
    return new Intl.NumberFormat("vi-VN", {
      style: "currency",
      currency: intent.budget.currency,
      maximumFractionDigits: 0,
    }).format(intent.budget.targetAmount);
  }
  return `Mức ${budgetLevelLabel(intent.budget.level).toLocaleLowerCase("vi-VN")}`;
}

function guidedAnswersFromTripIntent(intent: TripIntent): GuidedIntakeAnswers {
  return {
    destination: intent.destination,
    dates: formatTripTiming(intent.timing),
    travelers: formatTripParty(intent.travelParty),
    budget: formatTripBudget(intent),
    note: intent.notes.join(" · "),
  };
}

function budgetFromAnswer(answer: string, current: TripIntent["budget"]) {
  const normalized = answer.trim().toLocaleLowerCase("vi-VN");
  const digits = normalized.replace(/[^\d]/g, "");
  let targetAmount = digits ? Number(digits) : null;
  const decimalMatch = normalized.match(/(\d+(?:[.,]\d+)?)\s*(triệu|tr|million)/);
  if (decimalMatch) {
    targetAmount = Math.round(Number(decimalMatch[1].replace(",", ".")) * 1_000_000);
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

function finishedTripFacts(context: ExplorerContext) {
  const intent = context.tripIntent;
  const budget =
    intent.budget.targetAmount != null
      ? formatBudget(context)
      : `Mức ${budgetLevelLabel(intent.budget.level).toLocaleLowerCase(
          "vi-VN"
        )}`;

  return [
    { label: "Điểm đến", value: intent.destination || "Chưa xác định" },
    { label: "Thời gian", value: formatTripTiming(intent.timing) },
    { label: "Nhóm đi", value: formatTripParty(intent.travelParty) },
    { label: "Ngân sách", value: budget },
    {
      label: "Lưu ý",
      value: intent.notes.length ? intent.notes.join(" · ") : "Không có lưu ý",
    },
  ];
}

function extractMessageUrls(value: string): string[] {
  return Array.from(
    new Set(
      (value.match(URL_PATTERN_GLOBAL) ?? []).map((url) =>
        url.replace(/[.,;:!?\)\]\}]+$/, "")
      )
    )
  );
}

function buildGuidedIntakeRequest(answers: GuidedIntakeAnswers): string {
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

export default function PlannerPage() {
  return (
    <Suspense
      fallback={<div className="routeLoading">Đang mở AI Planner…</div>}
    >
      <Planner />
    </Suspense>
  );
}

function Planner() {
  const router = useRouter();
  const params = useSearchParams();
  const { user, loading: authLoading } = useAuth();
  const initialChatId = params.get("chatId")?.trim() || null;
  const initialEntryChatIdRef = useRef(initialChatId);
  const initialDestination = params.get("destination") ?? "";
  const initialPrompt = params.get("prompt")?.trim() ?? "";
  const hasPrefilledRequest = Boolean(initialPrompt || initialDestination);
  const [prompt, setPrompt] = useState(
    initialPrompt
  );
  const [urlInput, setUrlInput] = useState("");
  const [urlInputError, setUrlInputError] = useState("");
  const messageListRef = useRef<HTMLDivElement>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement>(null);
  const urlInputRef = useRef<HTMLTextAreaElement>(null);
  const guidedInputRef = useRef<HTMLInputElement>(null);
  const toastTimerRef = useRef<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 1,
      role: "assistant",
      text: hasPrefilledRequest
        ? "Mình đã điền sẵn yêu cầu bạn vừa gửi. Bạn có thể chỉnh lại, thêm URL nguồn rồi gửi khi sẵn sàng."
        : NEW_CHAT_GREETING,
    },
  ]);
  const [guidedIntakeStep, setGuidedIntakeStep] = useState<GuidedIntakeStep>(
    hasPrefilledRequest ? "complete" : "destination"
  );
  const [guidedIntakeAnswers, setGuidedIntakeAnswers] =
    useState<GuidedIntakeAnswers>(() =>
      initialDestination ? { destination: initialDestination } : {}
    );
  const [guidedIntakeOpen, setGuidedIntakeOpen] = useState(false);
  const [guidedDraft, setGuidedDraft] = useState(initialDestination);
  const [guidedStartDate, setGuidedStartDate] = useState("");
  const [guidedEndDate, setGuidedEndDate] = useState("");
  const [travelerCounts, setTravelerCounts] = useState<TravelerCounts>({
    adults: 1,
    children: 0,
    infants: 0,
    pets: 0,
  });
  const [savingTripIntent, setSavingTripIntent] = useState(false);
  const [plannerToast, setPlannerToast] = useState<PlannerToast | null>(null);
  const showPlannerToast = useCallback((text: string) => {
    if (toastTimerRef.current != null)
      window.clearTimeout(toastTimerRef.current);
    setPlannerToast({ id: Date.now(), text });
    toastTimerRef.current = window.setTimeout(() => {
      setPlannerToast(null);
      toastTimerRef.current = null;
    }, 2400);
  }, []);
  const [exploreResult, setExploreResult] = useState<ExploreResponse | null>(
    null
  );
  const [selectedMapPlaceKey, setSelectedMapPlaceKey] = useState<string | null>(
    null
  );
  const [selectedMapRouteKey, setSelectedMapRouteKey] = useState<string | null>(
    null
  );
  const [itineraryReviewPlace, setItineraryReviewPlace] =
    useState<PlaceReviewsModalPlace | null>(null);
  const [activePlanDay, setActivePlanDay] = useState<number | null>(null);
  const [itinerarySearchQuery, setItinerarySearchQuery] = useState("");
  const [destinationDetailsOpen, setDestinationDetailsOpen] = useState(false);
  const [currentLocation, setCurrentLocation] =
    useState<PlannerMapCurrentLocation | null>(null);
  const [dayDirectionLegs, setDayDirectionLegs] = useState<TransportLeg[]>([]);
  const [navigationDestinationKey, setNavigationDestinationKey] = useState<
    string | null
  >(null);
  const [selectedDirectionOptionKeys, setSelectedDirectionOptionKeys] =
    useState<Record<number, string>>({});
  const [selectedPlanLegOptionKeys, setSelectedPlanLegOptionKeys] = useState<
    Record<string, string>
  >({});
  const [savingTransportOptionKey, setSavingTransportOptionKey] = useState<
    string | null
  >(null);
  const [retryingTransportLegKey, setRetryingTransportLegKey] = useState<
    string | null
  >(null);
  const [transportLegRetryErrors, setTransportLegRetryErrors] = useState<
    Record<string, string>
  >({});
  const [expandedTransportOptionKeys, setExpandedTransportOptionKeys] =
    useState<Record<string, boolean>>({});
  const [directionsActive, setDirectionsActive] = useState(false);
  const [directionsSearchOpen, setDirectionsSearchOpen] = useState(false);
  const [directionOriginQuery, setDirectionOriginQuery] = useState("");
  const [directionOriginSuggestions, setDirectionOriginSuggestions] = useState<
    PlaceSuggestion[]
  >([]);
  const [selectedDirectionOrigin, setSelectedDirectionOrigin] =
    useState<PlannerMapCurrentLocation | null>(null);
  const [searchingDirectionOrigin, setSearchingDirectionOrigin] =
    useState(false);
  const [destinationQuery, setDestinationQuery] = useState("");
  const [selectedNavigationDestination, setSelectedNavigationDestination] =
    useState<DirectionStop | null>(null);
  const [directionsStatus, setDirectionsStatus] =
    useState<DirectionsStatus>("idle");
  const [directionsError, setDirectionsError] = useState("");
  const [locationFocusRequest, setLocationFocusRequest] = useState(0);
  const [routeFocusRequest, setRouteFocusRequest] = useState(0);
  const [locationStatus, setLocationStatus] = useState<LocationStatus>("idle");
  const [locationError, setLocationError] = useState("");
  const [placeLocationTarget, setPlaceLocationTarget] =
    useState<PlaceLocationTarget | null>(null);
  const placeLocationTargetRef = useRef<PlaceLocationTarget | null>(null);
  const directionsPendingLocationRef = useRef(false);
  const directionsDestinationRef = useRef<DirectionStop | null>(null);
  const directionsRequestIdRef = useRef(0);
  const autoRetriedTransportLegKeysRef = useRef<Set<string>>(new Set());
  const locationWatchIdRef = useRef<number | null>(null);
  const latestLocationRef = useRef<PlannerMapCurrentLocation | null>(null);
  const orientationListenerRef = useRef<
    ((event: DeviceOrientationEvent) => void) | null
  >(null);
  const orientationTrackingRef = useRef(false);
  const [plan, setPlan] = useState<TravelPlan | null>(null);
  const [workflowStage, setWorkflowStage] = useState<WorkflowStage>("idle");
  const [loading, setLoading] = useState(false);
  const [backgroundPlanning, setBackgroundPlanning] = useState(false);
  const [initialPlanningActive, setInitialPlanningActive] = useState(false);
  const [activePlanningJobs, setActivePlanningJobs] = useState<
    ActivePlanningJob[]
  >([]);
  const [queueingUrls, setQueueingUrls] = useState(false);
  const [error, setError] = useState("");
  const [tripChats, setTripChats] = useState<TripChatSummary[]>([]);
  const [urlJobSnapshot, setUrlJobSnapshot] = useState<UrlImportJob[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const activeChatIdRef = useRef<string | null>(null);
  const chatLoadControllerRef = useRef<AbortController | null>(null);
  const activeRequestIdRef = useRef(0);
  const routeEnrichmentRequestRef = useRef<string | null>(null);
  const submittingEntryRef = useRef(false);
  const [chatRevision, setChatRevision] = useState(0);
  const [tripIntentVersion, setTripIntentVersion] = useState(0);
  const [tripIntentPlanStatus, setTripIntentPlanStatus] = useState<
    TripChat["tripIntentPlanStatus"]
  >("synced");
  const [deletingChatId, setDeletingChatId] = useState<string | null>(null);
  const [deletingAllChats, setDeletingAllChats] = useState(false);
  const [historyCollapsed, setHistoryCollapsed] = useState(true);
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [mobileItineraryExpanded, setMobileItineraryExpanded] = useState(false);
  const [itineraryWidthPercent, setItineraryWidthPercent] = useState(40);
  const [floatingChatRect, setFloatingChatRect] =
    useState<FloatingChatRect | null>(null);
  const plannerLayoutRef = useRef<HTMLElement>(null);
  const plannerChatRef = useRef<HTMLElement>(null);
  const chatPointerInteractionRef = useRef<ChatPointerInteraction | null>(null);
  const mobileItineraryDragRef = useRef<MobileItineraryDrag | null>(null);
  const suppressMobileItineraryClickRef = useRef(false);
  const mobilePlanInitializedRef = useRef(false);
  const previousChatCollapsedRef = useRef(chatCollapsed);
  const suppressChatToggleClickRef = useRef(false);
  const expandedChatSizeRef = useRef<Pick<
    FloatingChatRect,
    "width" | "height"
  > | null>(null);
  const [plannerEntryResolved, setPlannerEntryResolved] = useState(false);

  const clampFloatingChatRect = useCallback(
    (rect: FloatingChatRect, collapsed = chatCollapsed): FloatingChatRect => {
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const margin = FLOATING_CHAT_MARGIN;
      if (collapsed) {
        const width = Math.min(rect.width, viewportWidth - margin * 2);
        const height = Math.min(rect.height, viewportHeight - margin * 2);
        return {
          x: clamp(
            rect.x,
            margin,
            Math.max(margin, viewportWidth - width - margin)
          ),
          y: clamp(
            rect.y,
            margin,
            Math.max(margin, viewportHeight - height - margin)
          ),
          width,
          height,
        };
      }

      const width = clamp(
        rect.width,
        Math.min(FLOATING_CHAT_MIN_WIDTH, viewportWidth - margin * 2),
        viewportWidth - margin * 2
      );
      const height = clamp(
        rect.height,
        Math.min(FLOATING_CHAT_MIN_HEIGHT, viewportHeight - margin * 2),
        viewportHeight - margin * 2
      );

      return {
        x: clamp(
          rect.x,
          margin,
          Math.max(margin, viewportWidth - width - margin)
        ),
        y: clamp(
          rect.y,
          margin,
          Math.max(margin, viewportHeight - height - margin)
        ),
        width,
        height,
      };
    },
    [chatCollapsed]
  );

  const currentFloatingChatRect = useCallback((): FloatingChatRect | null => {
    const bounds = plannerChatRef.current?.getBoundingClientRect();
    if (!bounds) return null;
    return clampFloatingChatRect({
      x: bounds.left,
      y: bounds.top,
      width: bounds.width,
      height: bounds.height,
    });
  }, [clampFloatingChatRect]);

  function toggleChatCollapsed() {
    if (suppressChatToggleClickRef.current) {
      suppressChatToggleClickRef.current = false;
      return;
    }
    const currentRect = currentFloatingChatRect();
    if (!currentRect || window.innerWidth <= 900) {
      setChatCollapsed((collapsed) => !collapsed);
      return;
    }

    if (!chatCollapsed) {
      expandedChatSizeRef.current = {
        width: currentRect.width,
        height: currentRect.height,
      };
      const dockRight =
        currentRect.x + currentRect.width / 2 >= window.innerWidth / 2;
      const dockBottom =
        currentRect.y + currentRect.height / 2 >= window.innerHeight / 2;
      setFloatingChatRect(
        clampFloatingChatRect(
          {
            x: dockRight
              ? currentRect.x + currentRect.width - FLOATING_CHAT_COLLAPSED_SIZE
              : currentRect.x,
            y: dockBottom
              ? currentRect.y +
                currentRect.height -
                FLOATING_CHAT_COLLAPSED_SIZE
              : currentRect.y,
            width: FLOATING_CHAT_COLLAPSED_SIZE,
            height: FLOATING_CHAT_COLLAPSED_SIZE,
          },
          true
        )
      );
      setChatCollapsed(true);
      return;
    }

    const defaultWidth = Math.min(
      410,
      window.innerWidth - FLOATING_CHAT_MARGIN * 2
    );
    const defaultHeight = Math.min(
      610,
      window.innerHeight - FLOATING_CHAT_MARGIN * 2
    );
    const expandedSize = expandedChatSizeRef.current ?? {
      width: defaultWidth,
      height: defaultHeight,
    };
    const openLeft =
      currentRect.x + currentRect.width / 2 >= window.innerWidth / 2;
    const openUp =
      currentRect.y + currentRect.height / 2 >= window.innerHeight / 2;
    setFloatingChatRect(
      clampFloatingChatRect(
        {
          x: openLeft
            ? currentRect.x + currentRect.width - expandedSize.width
            : currentRect.x,
          y: openUp
            ? currentRect.y + currentRect.height - expandedSize.height
            : currentRect.y,
          width: expandedSize.width,
          height: expandedSize.height,
        },
        false
      )
    );
    setChatCollapsed(false);
  }

  function resizedFloatingChatRect(
    rect: FloatingChatRect,
    direction: ChatResizeDirection,
    deltaX: number,
    deltaY: number
  ): FloatingChatRect {
    const right = rect.x + rect.width;
    const bottom = rect.y + rect.height;
    const nextLeft = direction.includes("w")
      ? clamp(
          rect.x + deltaX,
          FLOATING_CHAT_MARGIN,
          right -
            Math.min(FLOATING_CHAT_MIN_WIDTH, right - FLOATING_CHAT_MARGIN)
        )
      : rect.x;
    const nextRight = direction.includes("e")
      ? clamp(
          right + deltaX,
          rect.x +
            Math.min(
              FLOATING_CHAT_MIN_WIDTH,
              window.innerWidth - FLOATING_CHAT_MARGIN - rect.x
            ),
          window.innerWidth - FLOATING_CHAT_MARGIN
        )
      : right;
    const nextTop = direction.includes("n")
      ? clamp(
          rect.y + deltaY,
          FLOATING_CHAT_MARGIN,
          bottom -
            Math.min(FLOATING_CHAT_MIN_HEIGHT, bottom - FLOATING_CHAT_MARGIN)
        )
      : rect.y;
    const nextBottom = direction.includes("s")
      ? clamp(
          bottom + deltaY,
          rect.y +
            Math.min(
              FLOATING_CHAT_MIN_HEIGHT,
              window.innerHeight - FLOATING_CHAT_MARGIN - rect.y
            ),
          window.innerHeight - FLOATING_CHAT_MARGIN
        )
      : bottom;

    return {
      x: nextLeft,
      y: nextTop,
      width: nextRight - nextLeft,
      height: nextBottom - nextTop,
    };
  }

  function beginChatPointerInteraction(
    event: ReactPointerEvent<HTMLButtonElement>,
    mode: ChatPointerInteraction["mode"],
    resizeDirection?: ChatResizeDirection
  ) {
    if (event.button !== 0 || window.innerWidth <= 900) return;
    const rect = currentFloatingChatRect();
    if (!rect) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    chatPointerInteractionRef.current = {
      mode,
      resizeDirection,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      rect,
    };
    setFloatingChatRect(rect);
  }

  function updateChatPointerInteraction(
    event: ReactPointerEvent<HTMLButtonElement>
  ) {
    const interaction = chatPointerInteractionRef.current;
    if (!interaction || interaction.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - interaction.startX;
    const deltaY = event.clientY - interaction.startY;

    if (Math.abs(deltaX) > 4 || Math.abs(deltaY) > 4) {
      suppressChatToggleClickRef.current = true;
    }

    if (interaction.mode === "move") {
      setFloatingChatRect(
        clampFloatingChatRect({
          ...interaction.rect,
          x: interaction.rect.x + deltaX,
          y: interaction.rect.y + deltaY,
        })
      );
      return;
    }

    setFloatingChatRect(
      resizedFloatingChatRect(
        interaction.rect,
        interaction.resizeDirection ?? "se",
        deltaX,
        deltaY
      )
    );
  }

  function endChatPointerInteraction(
    event: ReactPointerEvent<HTMLButtonElement>
  ) {
    if (chatPointerInteractionRef.current?.pointerId !== event.pointerId)
      return;
    chatPointerInteractionRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function moveChatWithKeyboard(event: ReactKeyboardEvent<HTMLButtonElement>) {
    const offsets: Record<string, [number, number]> = {
      ArrowLeft: [-12, 0],
      ArrowRight: [12, 0],
      ArrowUp: [0, -12],
      ArrowDown: [0, 12],
    };
    const offset = offsets[event.key];
    if (!offset || window.innerWidth <= 900) return;
    event.preventDefault();
    const rect = floatingChatRect ?? currentFloatingChatRect();
    if (!rect) return;
    setFloatingChatRect(
      clampFloatingChatRect({
        ...rect,
        x: rect.x + offset[0],
        y: rect.y + offset[1],
      })
    );
  }

  function resizeChatWithKeyboard(
    event: ReactKeyboardEvent<HTMLButtonElement>,
    direction: ChatResizeDirection
  ) {
    const offsets: Record<string, [number, number]> = {
      ArrowLeft: [-16, 0],
      ArrowRight: [16, 0],
      ArrowUp: [0, -16],
      ArrowDown: [0, 16],
    };
    const offset = offsets[event.key];
    if (!offset || window.innerWidth <= 900) return;
    event.preventDefault();
    const rect = floatingChatRect ?? currentFloatingChatRect();
    if (!rect) return;
    setFloatingChatRect(
      resizedFloatingChatRect(
        rect,
        direction,
        direction.includes("w") || direction.includes("e") ? offset[0] : 0,
        direction.includes("n") || direction.includes("s") ? offset[1] : 0
      )
    );
  }

  function updateItineraryWidth(clientX: number) {
    const bounds = plannerLayoutRef.current?.getBoundingClientRect();
    if (!bounds || bounds.width <= 0) return;
    setItineraryWidthPercent(
      clamp(
        ((clientX - bounds.left) / bounds.width) * 100,
        ITINERARY_MIN_PERCENT,
        ITINERARY_MAX_PERCENT
      )
    );
  }

  function beginItineraryResize(event: ReactPointerEvent<HTMLButtonElement>) {
    if (event.button !== 0 || window.innerWidth <= 900) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    updateItineraryWidth(event.clientX);
  }

  function beginMobileItineraryDrag(
    event: ReactPointerEvent<HTMLButtonElement>
  ) {
    if (event.button !== 0 || window.innerWidth > 780) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    mobileItineraryDragRef.current = {
      pointerId: event.pointerId,
      startY: event.clientY,
    };
  }

  function endMobileItineraryDrag(
    event: ReactPointerEvent<HTMLButtonElement>
  ) {
    const drag = mobileItineraryDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const deltaY = event.clientY - drag.startY;
    mobileItineraryDragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (Math.abs(deltaY) < 36) return;
    event.preventDefault();
    suppressMobileItineraryClickRef.current = true;
    setMobileItineraryExpanded(deltaY < 0);
  }

  function cancelMobileItineraryDrag(
    event: ReactPointerEvent<HTMLButtonElement>
  ) {
    if (mobileItineraryDragRef.current?.pointerId !== event.pointerId) return;
    mobileItineraryDragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function resizeItineraryWithKeyboard(
    event: ReactKeyboardEvent<HTMLButtonElement>
  ) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    setItineraryWidthPercent((current) =>
      clamp(
        current + (event.key === "ArrowLeft" ? -2 : 2),
        ITINERARY_MIN_PERCENT,
        ITINERARY_MAX_PERCENT
      )
    );
  }

  useEffect(() => {
    function keepFloatingChatVisible() {
      if (window.innerWidth <= 900) {
        setFloatingChatRect(null);
        if (window.innerWidth <= 780 && plan) {
          mobilePlanInitializedRef.current = true;
          setChatCollapsed(true);
          setMobileItineraryExpanded(false);
        } else {
          setChatCollapsed(false);
        }
        return;
      }
      setFloatingChatRect((current) =>
        current ? clampFloatingChatRect(current) : null
      );
    }
    window.addEventListener("resize", keepFloatingChatVisible);
    return () => window.removeEventListener("resize", keepFloatingChatVisible);
  }, [clampFloatingChatRect, plan]);

  useEffect(() => {
    if (!plan) {
      mobilePlanInitializedRef.current = false;
      return;
    }
    if (
      !mobilePlanInitializedRef.current &&
      window.matchMedia("(max-width: 780px)").matches
    ) {
      mobilePlanInitializedRef.current = true;
      setChatCollapsed(true);
      setMobileItineraryExpanded(false);
    }
  }, [plan]);

  useEffect(() => {
    if (!plan || chatCollapsed) return;
    setFloatingChatRect((current) => {
      if (!current) return null;
      const looksCollapsed =
        current.width <= FLOATING_CHAT_COLLAPSED_SIZE + 4 &&
        current.height <= FLOATING_CHAT_COLLAPSED_SIZE + 4;
      return looksCollapsed ? null : clampFloatingChatRect(current, false);
    });
  }, [chatCollapsed, clampFloatingChatRect, plan]);

  useEffect(() => {
    const wasCollapsed = previousChatCollapsedRef.current;
    previousChatCollapsedRef.current = chatCollapsed;
    if (
      !plan ||
      chatCollapsed ||
      !wasCollapsed ||
      !window.matchMedia("(max-width: 780px)").matches
    ) {
      return;
    }

    const focusTimer = window.setTimeout(() => {
      composerTextareaRef.current?.focus({ preventScroll: true });
    }, 180);
    return () => window.clearTimeout(focusTimer);
  }, [chatCollapsed, plan]);

  useEffect(() => {
    const hasLegacyCoarseRoutes = plan?.days.some((day) =>
      day.transportLegs.some((leg) => leg.source === "geodesic_estimate")
    );
    if (
      !activeChatId ||
      !plan ||
      (plan.routeEnrichmentStatus !== "pending" &&
        !(plan.routeEnrichmentStatus === "completed" && hasLegacyCoarseRoutes))
    ) {
      return;
    }
    const requestKey = `${activeChatId}:${chatRevision}`;
    if (routeEnrichmentRequestRef.current === requestKey) return;
    routeEnrichmentRequestRef.current = requestKey;
    let cancelled = false;

    void enrichTripChatRoutes({
      chatId: activeChatId,
      expectedRevision: chatRevision,
    })
      .then((updated) => {
        if (cancelled || activeChatIdRef.current !== updated.id) return;
        applyTripChatBackgroundResult(updated);
      })
      .catch(async (requestError) => {
        if (cancelled || activeChatIdRef.current !== activeChatId) return;
        if (requestError instanceof APIError && requestError.status === 409) {
          try {
            const latest = await getTripChat(activeChatId);
            if (!cancelled) applyTripChatBackgroundResult(latest);
          } catch {
            // A later chat refresh can retry route enrichment.
          }
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeChatId, chatRevision, plan]);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current != null)
        window.clearTimeout(toastTimerRef.current);
      if (locationWatchIdRef.current != null && "geolocation" in navigator) {
        navigator.geolocation.clearWatch(locationWatchIdRef.current);
      }
      locationWatchIdRef.current = null;
      if (orientationListenerRef.current) {
        window.removeEventListener(
          "deviceorientation",
          orientationListenerRef.current,
          true
        );
        window.removeEventListener(
          "deviceorientationabsolute",
          orientationListenerRef.current,
          true
        );
      }
      orientationListenerRef.current = null;
      orientationTrackingRef.current = false;
    };
  }, []);

  useEffect(() => {
    async function handleUrlJobUpdate(event: Event) {
      const job = (event as CustomEvent<UrlImportJob>).detail;
      if (!job) return;
      if (job.chatId !== activeChatId) return;
      if (job.status === "queued" || job.status === "running") {
        setBackgroundPlanning(true);
        setWorkflowStage(job.status === "queued" ? "preparing" : job.explorerTiming ? "planning" : "exploring");
      } else if (job.status === "failed") {
        setBackgroundPlanning(false);
        setInitialPlanningActive(false);
        setActivePlanningJobs([]);
        setError(job.errorMessage || "Không thể tạo lịch trình từ URL này.");
      }
      try {
        const chat = await getTripChat(job.chatId);
        if (chat.revision >= chatRevision) {
          applyTripChat(chat);
          if (chat.currentPlan) {
            setBackgroundPlanning(false);
            setActivePlanningJobs([]);
          }
          setTripChats(await listTripChats());
        }
      } catch {
        // The global job panel retains the actionable failure state.
      }
    }
    window.addEventListener("travelplanner:url-job-update", handleUrlJobUpdate);
    return () =>
      window.removeEventListener("travelplanner:url-job-update", handleUrlJobUpdate);
  }, [activeChatId, chatRevision]);

  useEffect(() => {
    if (
      !activeChatId ||
      (tripIntentPlanStatus !== "queued" &&
        tripIntentPlanStatus !== "running")
    ) {
      return;
    }
    let cancelled = false;
    const targetVersion = tripIntentVersion;

    async function refreshRegeneratedPlan() {
      while (!cancelled) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        if (cancelled || !activeChatId) return;
        try {
          const latest = await getTripChat(activeChatId);
          if (cancelled || latest.tripIntentVersion < targetVersion) continue;
          setTripIntentVersion(latest.tripIntentVersion);
          setTripIntentPlanStatus(latest.tripIntentPlanStatus);
          if (
            latest.tripIntentPlanStatus === "synced" ||
            latest.tripIntentPlanStatus === "failed"
          ) {
            applyTripChatBackgroundResult(latest);
            if (latest.tripIntentPlanStatus === "synced") {
              showPlannerToast("Lịch trình đã đồng bộ theo thông tin mới");
            } else {
              showPlannerToast(
                "Thông tin đã lưu, nhưng chưa tạo lại được lịch trình"
              );
            }
            return;
          }
        } catch {
          // A transient refresh failure must not block another intent edit.
        }
      }
    }

    void refreshRegeneratedPlan();
    return () => {
      cancelled = true;
    };
  }, [
    activeChatId,
    tripIntentPlanStatus,
    tripIntentVersion,
    showPlannerToast,
  ]);

  useEffect(() => {
    if (!user) {
      setUrlJobSnapshot([]);
      return;
    }

    const applySnapshot = (jobs: UrlImportJob[]) => {
      setUrlJobSnapshot(jobs);
      const chatId = activeChatIdRef.current;
      if (!chatId) return;
      const active = jobs.filter(
        (job) =>
          job.chatId === chatId &&
          (job.status === "queued" || job.status === "running")
      );
      setActivePlanningJobs(
        active.map((job) => ({ id: job.id, guest: false }))
      );
      setBackgroundPlanning(active.length > 0);
      if (active.length > 0) {
        setInitialPlanningActive(true);
        setWorkflowStage(
          active.every((job) => job.status === "queued")
            ? "preparing"
            : active.some((job) => Boolean(job.explorerTiming))
            ? "planning"
            : "exploring"
        );
      }
    };
    const handleSnapshot = (event: Event) => {
      const jobs = (event as CustomEvent<UrlImportJob[]>).detail;
      if (Array.isArray(jobs)) applySnapshot(jobs);
    };

    window.addEventListener("travelplanner:url-jobs-snapshot", handleSnapshot);
    void listUrlImportJobs()
      .then((response) => applySnapshot(response.jobs))
      .catch(() => undefined);
    return () =>
      window.removeEventListener("travelplanner:url-jobs-snapshot", handleSnapshot);
  }, [user?.id]);

  useEffect(() => {
    const applyGuestResult = (job: GuestUrlImportJob) => {
      if (job.status !== "succeeded" || !job.result) return;
      setGuidedIntakeStep("complete");
      setGuidedIntakeOpen(false);
      setBackgroundPlanning(false);
      setInitialPlanningActive(false);
      setActivePlanningJobs([]);
      setExploreResult(job.result.explore);
      setPlan(job.result.plan);
      setWorkflowStage("ready");
      setSelectedMapPlaceKey(null);
      setError("");
    };
    const handleGuestResult = (event: Event) => {
      applyGuestResult((event as CustomEvent<GuestUrlImportJob>).detail);
    };
    const handleGuestJobs = (event: Event) => {
      const jobs = (event as CustomEvent<GuestUrlImportJob[]>).detail ?? [];
      const activeJobs = jobs.filter(
        (job) => job.status === "queued" || job.status === "running"
      );
      setActivePlanningJobs(activeJobs.map((job) => ({ id: job.id, guest: true })));
      setBackgroundPlanning(activeJobs.length > 0);
      setInitialPlanningActive(activeJobs.length > 0);
      if (activeJobs.length > 0) {
        setWorkflowStage(
          activeJobs.every((job) => job.status === "queued")
            ? "preparing"
            : activeJobs.some(
            (job) =>
              job.phase === "planning"
          )
            ? "planning"
            : "exploring"
        );
      }
    };
    window.addEventListener(GUEST_URL_JOB_RESULT_EVENT, handleGuestResult);
    window.addEventListener(GUEST_URL_JOBS_EVENT, handleGuestJobs);
    const latest = listGuestUrlJobs()
      .filter((job) => job.status === "succeeded" && job.result)
      .sort(
        (left, right) =>
          Date.parse(right.finishedAt ?? "") - Date.parse(left.finishedAt ?? "")
      )[0];
    if (latest) applyGuestResult(latest);
    return () => {
      window.removeEventListener(GUEST_URL_JOB_RESULT_EVENT, handleGuestResult);
      window.removeEventListener(GUEST_URL_JOBS_EVENT, handleGuestJobs);
    };
  }, []);

  const [editingItem, setEditingItem] = useState<{
    day: number;
    itemId: string;
    originalName: string;
    name: string;
  } | null>(null);
  const [addingDay, setAddingDay] = useState<number | null>(null);
  const [addName, setAddName] = useState("");
  const [addPlaceType, setAddPlaceType] = useState("attraction");
  const [addPosition, setAddPosition] = useState(0);
  const [addNotes, setAddNotes] = useState("");
  const [placeSuggestions, setPlaceSuggestions] = useState<PlaceSuggestion[]>(
    []
  );
  const [selectedSuggestion, setSelectedSuggestion] =
    useState<PlaceSuggestion | null>(null);
  const [searchingSuggestions, setSearchingSuggestions] = useState(false);
  const [addSearchCompleted, setAddSearchCompleted] = useState(false);
  const [addSearchFailed, setAddSearchFailed] = useState(false);
  const [editPlaceSuggestions, setEditPlaceSuggestions] = useState<
    PlaceSuggestion[]
  >([]);
  const [selectedEditSuggestion, setSelectedEditSuggestion] =
    useState<PlaceSuggestion | null>(null);
  const [searchingEditSuggestions, setSearchingEditSuggestions] =
    useState(false);
  const [editSearchCompleted, setEditSearchCompleted] = useState(false);
  const [editSearchFailed, setEditSearchFailed] = useState(false);
  const [mutatingItem, setMutatingItem] = useState(false);
  const [candidateResolutionProgress, setCandidateResolutionProgress] = useState<
    Record<string, { key: string; status: "queued" | "resolving" }>
  >({});
  const candidateResolutionQueueRef = useRef<
    Array<{
      chatId: string;
      matchRank: number;
      place: UnscheduledPlace;
    }>
  >([]);
  const candidateResolutionCandidateIdsRef = useRef(new Set<string>());
  const candidateResolutionRunningRef = useRef(false);
  const [noteEditor, setNoteEditor] = useState<{
    day: number;
    itemId: string | null;
    itemName: string;
    sourceNotes: ReturnType<typeof planItemNotePresentation>["sourceNotes"];
    personalNotes: string;
  } | null>(null);
  const noteTextareaRef = useRef<HTMLTextAreaElement>(null);
  const [openQuickActionKey, setOpenQuickActionKey] = useState<string | null>(
    null
  );

  useEffect(() => {
    const modalIsClosed =
      (placeLocationTarget === "add" && addingDay == null) ||
      (placeLocationTarget === "edit" && editingItem == null);
    if (!modalIsClosed) return;
    placeLocationTargetRef.current = null;
    setPlaceLocationTarget(null);
  }, [addingDay, editingItem, placeLocationTarget]);

  useEffect(() => {
    if (!noteEditor) return;

    const focusFrame = window.requestAnimationFrame(() => {
      noteTextareaRef.current?.focus({ preventScroll: true });
    });

    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && !mutatingItem) setNoteEditor(null);
    };
    window.addEventListener("keydown", closeOnEscape);

    return () => {
      window.cancelAnimationFrame(focusFrame);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [mutatingItem, noteEditor]);

  useEffect(() => {
    if (!openQuickActionKey) return;
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setOpenQuickActionKey(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [openQuickActionKey]);
  const conversationTurnRef = useRef<ReturnType<typeof useConversationTurn> | null>(null);

  const handleTurnTerminal = useCallback(
    async (result: { turn: TripChatTurn; outcome: string }) => {
      if (result.outcome === "awaiting_confirmation") {
        if (
          shouldApplyBackgroundChatResult(
            activeChatIdRef.current,
            result.turn.chatId
          )
        ) {
          const confirmation = conversationTurnRef.current?.confirm({
            chatId: result.turn.chatId,
            turnId: result.turn.id,
          });
          if (confirmation) {
            void confirmation.catch((caught) => {
              const message =
                caught instanceof Error ? caught.message : String(caught);
              setError(message);
            });
          }
        }
        return;
      }
      const resultBelongsToActiveChat = shouldApplyBackgroundChatResult(
        activeChatIdRef.current,
        result.turn.chatId
      );
      let refreshedHasPlan: boolean | null = null;
      try {
        if (resultBelongsToActiveChat) {
          const fresh = await getTripChat(result.turn.chatId);
          refreshedHasPlan = Boolean(fresh.currentPlan);
          if (
            shouldApplyBackgroundChatResult(
              activeChatIdRef.current,
              result.turn.chatId
            )
          ) {
            applyTripChat(fresh);
          }
        }
        setTripChats(await listTripChats());
      } catch (caught) {
        if (
          shouldApplyBackgroundChatResult(
            activeChatIdRef.current,
            result.turn.chatId
          )
        ) {
          const message =
            caught instanceof Error ? caught.message : String(caught);
          setError(message);
        }
      } finally {
        if (
          shouldApplyBackgroundChatResult(
            activeChatIdRef.current,
            result.turn.chatId
          )
        ) {
          setInitialPlanningActive(false);
          setWorkflowStage(
            result.outcome === "completed"
              ? refreshedHasPlan === false
                ? "idle"
                : "ready"
              : "failed"
          );
          if (result.turn.errorMessage) setError(result.turn.errorMessage);
          setSelectedMapPlaceKey(null);
        }
      }
    },
    []
  );

  const conversationTurn = useConversationTurn(handleTurnTerminal);
  conversationTurnRef.current = conversationTurn;

  useEffect(() => {
    if (!initialPlanningActive) return;
    if (conversationTurn.error) {
      setInitialPlanningActive(false);
      setWorkflowStage("failed");
      setError(conversationTurn.error);
      return;
    }
    if (
      conversationTurn.status === "queued"
    ) {
      setWorkflowStage("classifying");
      return;
    }
    if (conversationTurn.status === "classifying") {
      setWorkflowStage("classifying");
      return;
    }
    if (
      conversationTurn.status === "executing" ||
      conversationTurn.status === "awaiting_confirmation"
    ) {
      setWorkflowStage("planning");
      return;
    }
    if (
      conversationTurn.status === "failed" ||
      conversationTurn.status === "cancelled"
    ) {
      setInitialPlanningActive(false);
      setWorkflowStage("failed");
    }
  }, [
    conversationTurn.error,
    conversationTurn.status,
    initialPlanningActive,
  ]);

  function openItemEditor(
    day: number,
    item: TravelPlan["days"][number]["items"][number]
  ) {
    if (!item.itemId || !activeChatId) return;
    setEditingItem({
      day,
      itemId: item.itemId,
      originalName: item.name,
      name: item.name,
    });
    setSelectedEditSuggestion(
      item.address ||
        item.latitude != null ||
        item.longitude != null ||
        item.placeId
        ? {
            name: item.name,
            address: item.address,
            latitude: item.latitude,
            longitude: item.longitude,
            placeId: item.placeId,
          }
        : null
    );
    setEditPlaceSuggestions([]);
  }

  useEffect(() => {
    if (
      !addName.trim() ||
      addName.trim().length < 2 ||
      selectedSuggestion?.name === addName
    ) {
      setPlaceSuggestions([]);
      setSearchingSuggestions(false);
      setAddSearchCompleted(false);
      setAddSearchFailed(false);
      return;
    }

    let cancelled = false;
    setAddSearchCompleted(false);
    setAddSearchFailed(false);
    const timer = setTimeout(async () => {
      setSearchingSuggestions(true);
      try {
        const results = await searchPlaces(addName.trim(), plan?.destination);
        if (!cancelled) setPlaceSuggestions(results);
      } catch {
        if (!cancelled) {
          setPlaceSuggestions([]);
          setAddSearchFailed(true);
        }
      } finally {
        if (!cancelled) {
          setSearchingSuggestions(false);
          setAddSearchCompleted(true);
        }
      }
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [addName, plan?.destination, selectedSuggestion]);

  useEffect(() => {
    const query = directionOriginQuery.trim();
    if (
      !directionsSearchOpen ||
      query.length < 2 ||
      selectedDirectionOrigin?.label === query ||
      query === "Vị trí hiện tại"
    ) {
      setDirectionOriginSuggestions([]);
      setSearchingDirectionOrigin(false);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setSearchingDirectionOrigin(true);
      try {
        const results = await searchPlaces(query, plan?.destination);
        if (!cancelled) {
          setDirectionOriginSuggestions(
            results.filter(
              (suggestion) =>
                typeof suggestion.latitude === "number" &&
                typeof suggestion.longitude === "number"
            )
          );
        }
      } catch {
        if (!cancelled) setDirectionOriginSuggestions([]);
      } finally {
        if (!cancelled) setSearchingDirectionOrigin(false);
      }
    }, 300);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [
    directionOriginQuery,
    directionsSearchOpen,
    plan?.destination,
    selectedDirectionOrigin,
  ]);

  useEffect(() => {
    const query = editingItem?.name.trim() ?? "";
    if (
      !editingItem ||
      query.length < 2 ||
      selectedEditSuggestion?.name === query
    ) {
      setEditPlaceSuggestions([]);
      setSearchingEditSuggestions(false);
      setEditSearchCompleted(false);
      setEditSearchFailed(false);
      return;
    }

    let cancelled = false;
    setEditSearchCompleted(false);
    setEditSearchFailed(false);
    const timer = setTimeout(async () => {
      setSearchingEditSuggestions(true);
      try {
        const results = await searchPlaces(query, plan?.destination);
        if (!cancelled) setEditPlaceSuggestions(results);
      } catch {
        if (!cancelled) {
          setEditPlaceSuggestions([]);
          setEditSearchFailed(true);
        }
      } finally {
        if (!cancelled) {
          setSearchingEditSuggestions(false);
          setEditSearchCompleted(true);
        }
      }
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [editingItem, plan?.destination, selectedEditSuggestion]);

  async function handleDeleteItem(day: number, itemId: string) {
    if (!activeChatId || !plan) return;
    if (!confirm("Bạn có chắc chắn muốn xóa địa điểm này khỏi lịch trình?"))
      return;
    const previousPlan = plan;
    const deletedItem = plan.days
      .find((planDay) => planDay.day === day)
      ?.items.find((item) => item.itemId === itemId);
    setPlan({
      ...plan,
      days: plan.days.map((planDay) =>
        planDay.day !== day
          ? planDay
          : {
              ...planDay,
              items: planDay.items.filter((item) => item.itemId !== itemId),
              transportLegs: planDay.transportLegs.filter(
                (leg) =>
                  leg.fromItemId !== itemId &&
                  leg.toItemId !== itemId &&
                  (!deletedItem ||
                    (!planPlaceNamesMatch(leg.fromPlace, deletedItem.name) &&
                      !planPlaceNamesMatch(leg.toPlace, deletedItem.name)))
              ),
            }
      ),
    });
    setMutatingItem(true);
    setError("");
    try {
      const updatedChat = await removeTripChatItem({
        chatId: activeChatId,
        expectedRevision: chatRevision,
        day,
        itemId,
      });
      setChatRevision(updatedChat.revision);
      if (updatedChat.currentPlan) setPlan(updatedChat.currentPlan);
      showPlannerToast("Đã xóa địa điểm");
    } catch (err: any) {
      setPlan(previousPlan);
      setError(err?.message || "Không thể xóa địa điểm.");
    } finally {
      setMutatingItem(false);
    }
  }

  async function handleSaveEditItem(e: React.FormEvent) {
    e.preventDefault();
    if (!editingItem || !activeChatId) return;
    if (
      editingItem.name.trim() !== editingItem.originalName.trim() &&
      !selectedEditSuggestion
    )
      return;
    setMutatingItem(true);
    setError("");
    try {
      const updatedChat = await updateTripChatItem({
        chatId: activeChatId,
        expectedRevision: chatRevision,
        day: editingItem.day,
        itemId: editingItem.itemId,
        item: {
          placeId: selectedEditSuggestion?.placeId,
          name: editingItem.name.trim(),
          address: selectedEditSuggestion?.address,
          latitude: selectedEditSuggestion?.latitude,
          longitude: selectedEditSuggestion?.longitude,
        },
      });
      setChatRevision(updatedChat.revision);
      if (updatedChat.currentPlan) setPlan(updatedChat.currentPlan);
      showPlannerToast("Đã lưu thay đổi");
      setEditingItem(null);
      setSelectedEditSuggestion(null);
      setEditPlaceSuggestions([]);
    } catch (err: any) {
      setError(err?.message || "Không thể cập nhật địa điểm.");
    } finally {
      setMutatingItem(false);
    }
  }

  async function handleSavePersonalNotes(
    event: React.FormEvent<HTMLFormElement>,
    day: number,
    itemId: string
  ) {
    event.preventDefault();
    if (!activeChatId || mutatingItem) return;
    const form = new FormData(event.currentTarget);
    const personalNotes = String(form.get("personalNotes") ?? "").trim();
    setMutatingItem(true);
    setError("");
    try {
      const updatedChat = await updateTripChatItem({
        chatId: activeChatId,
        expectedRevision: chatRevision,
        day,
        itemId,
        item: { personalNotes },
      });
      setChatRevision(updatedChat.revision);
      if (updatedChat.currentPlan) setPlan(updatedChat.currentPlan);
      showPlannerToast("Đã lưu ghi chú");
      setNoteEditor(null);
    } catch (caught: any) {
      setError(caught?.message || "Không thể lưu ghi chú.");
    } finally {
      setMutatingItem(false);
    }
  }

  async function handleAddPlanItem(e: React.FormEvent) {
    e.preventDefault();
    if (addingDay == null || !activeChatId || !selectedSuggestion) return;
    setMutatingItem(true);
    setError("");
    try {
      const updatedChat = await addTripChatItem({
        chatId: activeChatId,
        expectedRevision: chatRevision,
        item: {
          day: addingDay,
          placeId: selectedSuggestion?.placeId || undefined,
          name: addName.trim(),
          placeType: addPlaceType,
          position: addPosition,
          personalNotes: addNotes.trim() || undefined,
          address: selectedSuggestion?.address || undefined,
          latitude: selectedSuggestion?.latitude ?? undefined,
          longitude: selectedSuggestion?.longitude ?? undefined,
          rating: selectedSuggestion?.rating ?? undefined,
          reviewCount: selectedSuggestion?.reviewCount ?? undefined,
          imageUrls: selectedSuggestion?.imageUrl
            ? [selectedSuggestion.imageUrl]
            : undefined,
        },
      });
      setChatRevision(updatedChat.revision);
      if (updatedChat.currentPlan) setPlan(updatedChat.currentPlan);
      showPlannerToast("Đã thêm địa điểm");
      setAddingDay(null);
      setAddName("");
      setAddNotes("");
      setSelectedSuggestion(null);
      setPlaceSuggestions([]);
    } catch (err: any) {
      setError(err?.message || "Không thể thêm địa điểm.");
    } finally {
      setMutatingItem(false);
    }
  }

  const [draggedItemKey, setDraggedItemKey] = useState<{
    day: number;
    itemId: string;
  } | null>(null);
  const [dragOverItemId, setDragOverItemId] = useState<string | null>(null);
  const [reorderingDay, setReorderingDay] = useState<number | null>(null);
  const itineraryScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (reorderingDay == null) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [reorderingDay]);

  useEffect(() => {
    if (!draggedItemKey) return;

    let pointerY: number | null = null;
    let animationFrame: number | null = null;

    function scrollTowardPointer() {
      animationFrame = null;
      if (pointerY == null) return;

      const scrollArea = itineraryScrollRef.current;
      const scrollAreaCanScroll = Boolean(
        scrollArea && scrollArea.scrollHeight > scrollArea.clientHeight + 1
      );

      if (scrollArea && scrollAreaCanScroll) {
        const bounds = scrollArea.getBoundingClientRect();
        const velocity = dragAutoScrollVelocity(pointerY, {
          start: bounds.top,
          end: bounds.bottom,
        });
        if (velocity !== 0) scrollArea.scrollTop += velocity;
      } else {
        const velocity = dragAutoScrollVelocity(pointerY, {
          start: 0,
          end: window.innerHeight,
        });
        if (velocity !== 0) window.scrollBy(0, velocity);
      }

      animationFrame = window.requestAnimationFrame(scrollTowardPointer);
    }

    function handleDragOver(event: DragEvent) {
      // Keep this internal drag a valid drop operation while it crosses the
      // sticky day tabs or the gaps between itinerary cards.
      event.preventDefault();
      pointerY = event.clientY;
      if (animationFrame == null) {
        animationFrame = window.requestAnimationFrame(scrollTowardPointer);
      }
    }

    function stopAutoScroll() {
      pointerY = null;
      if (animationFrame != null) window.cancelAnimationFrame(animationFrame);
      animationFrame = null;
    }

    document.addEventListener("dragover", handleDragOver);
    document.addEventListener("dragend", stopAutoScroll);
    document.addEventListener("drop", stopAutoScroll);

    return () => {
      stopAutoScroll();
      document.removeEventListener("dragover", handleDragOver);
      document.removeEventListener("dragend", stopAutoScroll);
      document.removeEventListener("drop", stopAutoScroll);
    };
  }, [draggedItemKey]);

  async function handleReorderItems(day: number, newOrderedItemIds: string[]) {
    if (!activeChatId || !plan || mutatingItem) return;
    setMutatingItem(true);
    setReorderingDay(day);
    setError("");
    let rollbackPlan = plan;
    let expectedRevision = chatRevision;
    let requestedItemIds = newOrderedItemIds;

    const reorderPlan = (
      sourcePlan: TravelPlan,
      itemIds: string[]
    ): TravelPlan => ({
      ...sourcePlan,
      days: sourcePlan.days.map((planDay) => {
        if (planDay.day !== day) return planDay;
        const itemsMap = new Map(
          planDay.items.map((item) => [item.itemId, item])
        );
        const reorderedItems = itemIds
          .map((itemId) => itemsMap.get(itemId))
          .filter((item): item is (typeof planDay.items)[number] =>
            Boolean(item)
          );
        planDay.items.forEach((item) => {
          if (item.itemId && !itemIds.includes(item.itemId))
            reorderedItems.push(item);
        });
        return { ...planDay, items: reorderedItems, transportLegs: [] };
      }),
    });

    setPlan(reorderPlan(plan, requestedItemIds));

    try {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const updatedChat = await reorderTripChatItem({
            chatId: activeChatId,
            expectedRevision,
            day,
            itemIds: requestedItemIds,
          });
          applyTripChat(updatedChat);
          showPlannerToast(`Đã cập nhật thứ tự Ngày ${day}`);
          return;
        } catch (caught) {
          if (
            !(caught instanceof APIError) ||
            caught.code !== "VERSION_CONFLICT" ||
            attempt === 2
          ) {
            throw caught;
          }

          const latestChat = await getTripChat(activeChatId);
          applyTripChat(latestChat);
          if (!latestChat.currentPlan) return;

          rollbackPlan = latestChat.currentPlan;
          expectedRevision = latestChat.revision;
          const latestDay = latestChat.currentPlan.days.find(
            (planDay) => planDay.day === day
          );
          if (!latestDay) return;

          const latestItemIds = latestDay.items
            .map((item) => item.itemId)
            .filter((itemId): itemId is string => Boolean(itemId));
          requestedItemIds = rebaseItineraryItemOrder(
            latestItemIds,
            requestedItemIds
          );
          setPlan(reorderPlan(latestChat.currentPlan, requestedItemIds));
        }
      }
    } catch (err: any) {
      setPlan(rollbackPlan);
      setError(err?.message || "Không thể sắp xếp lại vị trí địa điểm.");
    } finally {
      setMutatingItem(false);
      setReorderingDay(null);
    }
  }

  function handleMoveItemOrder(
    day: number,
    itemIndex: number,
    direction: "up" | "down"
  ) {
    const targetDayObj = plan?.days.find((d) => d.day === day);
    if (!targetDayObj) return;

    const items = [...targetDayObj.items];
    const targetIndex = direction === "up" ? itemIndex - 1 : itemIndex + 1;
    if (targetIndex < 0 || targetIndex >= items.length) return;

    const temp = items[itemIndex];
    items[itemIndex] = items[targetIndex];
    items[targetIndex] = temp;

    const itemIds = items
      .map((it) => it.itemId)
      .filter((id): id is string => Boolean(id));
    handleReorderItems(day, itemIds);
  }

  useEffect(() => {
    if (historyCollapsed) return;

    function closeProjectSidebar(event: KeyboardEvent) {
      if (event.key === "Escape") setHistoryCollapsed(true);
    }

    window.addEventListener("keydown", closeProjectSidebar);
    return () => window.removeEventListener("keydown", closeProjectSidebar);
  }, [historyCollapsed]);

  useEffect(() => {
    const entryChatId = initialEntryChatIdRef.current;
    if (authLoading || !user) {
      if (authLoading) {
        setPlannerEntryResolved(false);
      } else {
        syncPlannerChatUrl(null);
        setTripChats([]);
        activeChatIdRef.current = null;
        setActiveChatId(null);
        setChatRevision(0);
        setExploreResult(null);
        setPlan(null);
        setCurrentLocation(null);
        setDayDirectionLegs([]);
        setSelectedDirectionOptionKeys({});
        setSelectedPlanLegOptionKeys({});
        setDirectionsActive(false);
        setDirectionsStatus("idle");
        setDirectionsError("");
        setDirectionOriginQuery("");
        setDirectionOriginSuggestions([]);
        setSelectedDirectionOrigin(null);
        setSearchingDirectionOrigin(false);
        setLocationFocusRequest(0);
        directionsPendingLocationRef.current = false;
        directionsRequestIdRef.current += 1;
        setLocationStatus("idle");
        setLocationError("");
        setWorkflowStage("idle");
        setBackgroundPlanning(false);
        setInitialPlanningActive(false);
        setActivePlanningJobs([]);
        setChatCollapsed(false);
        setGuidedIntakeStep(hasPrefilledRequest ? "complete" : "destination");
        setGuidedIntakeOpen(false);
        setGuidedDraft(initialDestination);
        setGuidedIntakeAnswers({});
        setMessages([
          {
            id: Date.now(),
            role: "assistant",
            text: hasPrefilledRequest
              ? "Mình đã điền sẵn yêu cầu bạn vừa gửi. Bạn có thể chỉnh lại, thêm URL nguồn rồi gửi khi sẵn sàng."
              : NEW_CHAT_GREETING,
          },
        ]);
        setPlannerEntryResolved(true);
      }
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    setPlannerEntryResolved(false);
    setTripChats([]);

    // A deep-linked chat can be loaded directly. Waiting for the full history
    // list first adds an unnecessary round trip and leaves the planner on the
    // "new chat" loading screen after every reload.
    if (entryChatId && !hasPrefilledRequest) {
      void openTripChat(entryChatId);
    }

    void listTripChats({ signal: controller.signal })
      .then((chats) => {
        if (cancelled) return;
        setTripChats(chats);
        if (entryChatId && !hasPrefilledRequest) return;
        const entryChatIdToOpen = resolvePlannerEntryChatId(
          entryChatId,
          hasPrefilledRequest,
          chats.map((chat) => chat.id),
        );
        if (entryChatIdToOpen) {
          void openTripChat(entryChatIdToOpen);
        } else if (entryChatId) {
          syncPlannerChatUrl(null);
          setPlannerEntryResolved(true);
        } else {
          setPlannerEntryResolved(true);
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Không thể tải lịch sử chuyến đi. Bạn vẫn có thể bắt đầu chat mới."
          );
          // The deep-linked chat is loading independently of the history
          // sidebar, so keep its loading state until getTripChat finishes.
          if (!(entryChatId && !hasPrefilledRequest)) {
            setPlannerEntryResolved(true);
          }
        }
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
    // Query-string chat changes are handled by openTripChat/resetWorkflow.
    // Depending on initialChatId here makes Next's patched history.replaceState
    // rerun this bootstrap and clear the chat while it is being opened.
  }, [authLoading, hasPrefilledRequest, user?.id]);

  useEffect(() => {
    return () => {
      directionsPendingLocationRef.current = false;
      directionsRequestIdRef.current += 1;
    };
  }, [user?.id]);

  useEffect(() => {
    const messageList = messageListRef.current;
    if (messageList) {
      messageList.scrollTo({
        top: messageList.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [guidedIntakeStep, messages, workflowStage]);

  useEffect(() => {
    if (!guidedIntakeOpen) return;
    guidedInputRef.current?.focus();
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setGuidedIntakeOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [guidedIntakeOpen, guidedIntakeStep]);

  const displayedExploreResult = exploreResult;
  const displayedStartDate =
    displayedExploreResult?.explorer.tripIntent.timing.startDate;
  const displayedPlan = useMemo(
    () =>
      plan
        ? {
            ...plan,
            days: visiblePlanDays(
              plan.days.map((day) => ({
                ...day,
                items: visiblePlanItems(day.items),
              }))
            ),
          }
        : null,
    [plan]
  );
  const awaitingInitialPlan =
    !displayedPlan &&
    (initialPlanningActive || backgroundPlanning || loading);

  const planDayColorKeys = useMemo(() => {
    const startDate = displayedStartDate;
    return (
      displayedPlan?.days.map((day) => dateKeyForTripDay(startDate, day.day)) ??
      []
    );
  }, [displayedPlan, displayedStartDate]);
  const planDayColors = useMemo(
    () => createDayColorMap(planDayColorKeys),
    [planDayColorKeys]
  );
  const displayedPlanDays = useMemo(() => {
    if (!displayedPlan) return [];
    if (activePlanDay == null) return displayedPlan.days;
    return displayedPlan.days.filter((day) => day.day === activePlanDay);
  }, [activePlanDay, displayedPlan]);
  const itinerarySearchResults = useMemo(
    () => searchItineraryPlaces(displayedPlan?.days ?? [], itinerarySearchQuery),
    [displayedPlan, itinerarySearchQuery]
  );
  const destinationStories = useMemo(
    () =>
      (displayedPlan?.regionStories ?? [])
        .map((story) => ({
          story,
          text: formatSourceNoteForDisplay(story.text),
        }))
        .filter(({ text }) => Boolean(text)),
    [displayedPlan]
  );
  const destinationHistoryStories = useMemo(
    () =>
      destinationStories.filter(
        ({ story }) =>
          story.type === "destination_history" ||
          !story.type.startsWith("destination_")
      ),
    [destinationStories]
  );
  const destinationAdviceStories = useMemo(
    () =>
      destinationStories.filter(
        ({ story }) =>
          story.type.startsWith("destination_") &&
          story.type !== "destination_history"
      ),
    [destinationStories]
  );
  const destinationSummary = destinationHistoryStories[0]?.text;

  useEffect(() => {
    setItinerarySearchQuery("");
    setDestinationDetailsOpen(false);
  }, [activeChatId]);

  useEffect(() => {
    if (!destinationDetailsOpen) return;
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setDestinationDetailsOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [destinationDetailsOpen]);
  const addingPlanDay = useMemo(
    () => plan?.days.find((day) => day.day === addingDay) ?? null,
    [addingDay, plan]
  );
  const addingDayVisibleItems = useMemo(
    () => visiblePlanItems(addingPlanDay?.items ?? []),
    [addingPlanDay]
  );

  useEffect(() => {
    setActivePlanDay((current) => {
      if (current == null) return displayedPlan?.days[0]?.day ?? null;
      if (current === UNSCHEDULED_PLAN_DAY) return current;
      if (displayedPlan?.days.some((day) => day.day === current))
        return current;
      return displayedPlan?.days[0]?.day ?? null;
    });
  }, [displayedPlan]);

  useEffect(() => {
    setSelectedMapRouteKey(null);
  }, [activePlanDay, directionsActive]);

  useEffect(() => {
    directionsPendingLocationRef.current = false;
    directionsRequestIdRef.current += 1;
    setDirectionsActive(false);
    setDirectionsSearchOpen(false);
    setDirectionOriginQuery("");
    setDirectionOriginSuggestions([]);
    setSelectedDirectionOrigin(null);
    setSearchingDirectionOrigin(false);
    setDestinationQuery("");
    setSelectedNavigationDestination(null);
    setDayDirectionLegs([]);
    setSelectedDirectionOptionKeys({});
    setDirectionsStatus("idle");
    setDirectionsError("");
    setNavigationDestinationKey(null);
    directionsDestinationRef.current = null;
  }, [activePlanDay]);

  useEffect(() => {
    directionsPendingLocationRef.current = false;
    directionsRequestIdRef.current += 1;
    setDirectionsActive(false);
    setDirectionsSearchOpen(false);
    setDirectionOriginQuery("");
    setDirectionOriginSuggestions([]);
    setSelectedDirectionOrigin(null);
    setSearchingDirectionOrigin(false);
    setDayDirectionLegs([]);
    setSelectedDirectionOptionKeys({});
    setSelectedPlanLegOptionKeys({});
    setSelectedMapRouteKey(null);
    setDirectionsStatus("idle");
    setDirectionsError("");
  }, [displayedPlan]);

  const tripPlaces = useMemo<TripPlaceSummary[]>(() => {
    if (!displayedPlan) return [];

    return displayedPlan.days.flatMap((day) => {
      let dayOrder = 0;
      return day.items.flatMap((item, itemIndex) => {
        if (item.timelineCategory === "break") return [];
        dayOrder += 1;
        return [
          {
            ...item,
            day: day.day,
            order: dayOrder,
            mapKey: hasPlanItemCoordinates(item)
              ? planItemMapKey({
                  day: day.day,
                  itemId: item.itemId,
                  itemIndex,
                  name: item.name,
                })
              : null,
          },
        ];
      });
    });
  }, [displayedPlan]);
  const mapPlaces = useMemo<PlannerMapPlace[]>(() => {
    const startDate = displayedExploreResult?.explorer.tripIntent.timing.startDate;
    return tripPlaces
      .filter((item) => activePlanDay == null || item.day === activePlanDay)
      .flatMap((item) =>
        item.mapKey
          ? [
              {
                destination:
                  displayedPlan?.destination ??
                  displayedExploreResult?.explorer.tripIntent.destination ??
                  "",
                name: item.name,
                category: categoryFromPlaceType(item.placeType),
                placeId: item.placeId,
                address: item.address || `Ngày ${item.day}`,
                latitude: item.latitude ?? null,
                longitude: item.longitude ?? null,
                notes: item.notes,
                noteSources: item.noteSources,
                personalNotes: item.personalNotes,
                sourceRefs: item.sourceRefs,
                sourceProvider: item.sourceProvider,
                sourceActivity: item.sourceActivity,
                imageUrl: item.imageUrls?.find(isDisplayableImageUrl) ?? null,
                openingHours: item.openingHours,
                rating: item.rating,
                reviewCount: item.reviewCount,
                sourceLink: item.sourceLink,
                mapKey: item.mapKey,
                mapOrder: item.order,
                dayColorKey: dateKeyForTripDay(startDate, item.day),
                dayLabel: dateLabelForTripDay(startDate, item.day),
                timeWindow: item.timeWindow,
              },
            ]
          : []
      );
  }, [
    activePlanDay,
    displayedPlan?.destination,
    displayedExploreResult?.explorer.tripIntent.timing.startDate,
    tripPlaces,
  ]);
  const mapOrderByPlaceKey = useMemo(
    () => new Map(mapPlaces.map((place) => [place.mapKey, place.mapOrder])),
    [mapPlaces]
  );
  const activeDayDirectionStops = useMemo<DirectionStop[]>(
    () =>
      activePlanDay == null
        ? []
        : tripPlaces.filter(
            (
              item
            ): item is TripPlaceSummary & {
              latitude: number;
              longitude: number;
            } => item.day === activePlanDay && hasPlanItemCoordinates(item)
          ),
    [activePlanDay, tripPlaces]
  );
  const activeNavigationDestination = useMemo(
    () =>
      selectedNavigationDestination ??
      activeDayDirectionStops.find(
        (item) => item.mapKey === navigationDestinationKey
      ) ??
      activeDayDirectionStops[0] ??
      null,
    [
      activeDayDirectionStops,
      navigationDestinationKey,
      selectedNavigationDestination,
    ]
  );
  const directionDestinationOptions = useMemo<PlannerMapSearchPlace[]>(
    () =>
      activeDayDirectionStops.map((stop, index) => ({
        key: stop.mapKey ?? `plan-stop-${index}`,
        name: `Point ${index + 1} · ${stop.name}`,
        detail: stop.address,
        latitude: stop.latitude,
        longitude: stop.longitude,
        kind: "plan",
      })),
    [activeDayDirectionStops]
  );
  const directionOriginSearchSuggestions = useMemo<PlannerMapSearchPlace[]>(
    () =>
      directionOriginSuggestions.flatMap((suggestion, index) =>
        typeof suggestion.latitude === "number" &&
        typeof suggestion.longitude === "number"
          ? [
              {
                key: suggestion.placeId ?? `origin-${index}`,
                name: suggestion.name,
                detail: suggestion.address,
                latitude: suggestion.latitude,
                longitude: suggestion.longitude,
                kind: "searched" as const,
              },
            ]
          : []
      ),
    [directionOriginSuggestions]
  );
  const directionDestinationSuggestions = useMemo<
    PlannerMapSearchPlace[]
  >(() => {
    const query = destinationQuery.trim().toLocaleLowerCase("vi");
    const localMatches = directionDestinationOptions.filter((place) =>
      `${place.name} ${place.detail ?? ""}`
        .toLocaleLowerCase("vi")
        .includes(query)
    );
    return localMatches.filter(
      (place, index, all) =>
        all.findIndex(
          (candidate) =>
            candidate.latitude === place.latitude &&
            candidate.longitude === place.longitude
        ) === index
    );
  }, [destinationQuery, directionDestinationOptions]);
  const activeDayItineraryRouteSummary = useMemo(() => {
    const day = displayedPlan?.days.find((item) => item.day === activePlanDay);
    if (!day) return { distanceMeters: 0, durationMinutes: 0 };
    return day.transportLegs.reduce(
      (total, leg, index) => {
        const selected = selectedTransportOption(
          leg,
          selectedPlanLegOptionKeys[planLegSelectionKey(day.day, index)]
        );
        return {
          distanceMeters: total.distanceMeters + selected.distanceMeters,
          durationMinutes:
            total.durationMinutes + selected.estimatedDurationMinutes,
        };
      },
      { distanceMeters: 0, durationMinutes: 0 }
    );
  }, [activePlanDay, displayedPlan, selectedPlanLegOptionKeys]);
  const mapDirectionOrigin = useMemo(
    () =>
      directionsSearchOpen
        ? selectedDirectionOrigin
        : directionsActive
        ? selectedDirectionOrigin ?? currentLocation
        : directionsStatus === "ready" && selectedDirectionOrigin
        ? selectedDirectionOrigin
        : currentLocation,
    [
      currentLocation,
      directionsActive,
      directionsSearchOpen,
      directionsStatus,
      selectedDirectionOrigin,
    ]
  );
  const selectedDayDirectionLegs = useMemo(
    () =>
      dayDirectionLegs.map((leg, index) =>
        selectedTransportOption(leg, selectedDirectionOptionKeys[index])
      ),
    [dayDirectionLegs, selectedDirectionOptionKeys]
  );
  const activeDayRouteSummary = useMemo(() => {
    const firstStop = activeDayDirectionStops[0];
    const startLegRoute = dayDirectionLegs[0];
    const startLeg = selectedDayDirectionLegs[0];
    const reachesFirstStop = Boolean(
      firstStop &&
        startLegRoute &&
        startLeg &&
        (firstStop.itemId && startLegRoute.toItemId
          ? firstStop.itemId === startLegRoute.toItemId
          : firstStop.name.trim().toLocaleLowerCase("vi") ===
            startLegRoute.toPlace.trim().toLocaleLowerCase("vi"))
    );
    if (!reachesFirstStop || !startLeg) {
      return activeDayItineraryRouteSummary;
    }
    return {
      distanceMeters:
        activeDayItineraryRouteSummary.distanceMeters + startLeg.distanceMeters,
      durationMinutes:
        activeDayItineraryRouteSummary.durationMinutes +
        startLeg.estimatedDurationMinutes,
    };
  }, [
    activeDayDirectionStops,
    activeDayItineraryRouteSummary,
    dayDirectionLegs,
    selectedDayDirectionLegs,
  ]);
  const mapRoutes = useMemo<PlannerMapRoute[]>(() => {
    if (!displayedPlan) return [];
    const startDate = displayedExploreResult?.explorer.tripIntent.timing.startDate;
    const itineraryRoutes: PlannerMapRoute[] = displayedPlan.days
      .filter((day) => activePlanDay == null || day.day === activePlanDay)
      .flatMap((day) =>
        day.transportLegs.flatMap((leg, index) => {
          const selected = selectedTransportOption(
            leg,
            selectedPlanLegOptionKeys[planLegSelectionKey(day.day, index)]
          );
          if (!isDrawableTransportRoute(selected)) return [];
          return [
            {
              key: planTransportRouteMapKey(day.day, index, selected),
              mode: selected.mode,
              fromPlace: leg.fromPlace,
              toPlace: leg.toPlace,
              distanceMeters: selected.distanceMeters,
              estimatedDurationMinutes: selected.estimatedDurationMinutes,
              coordinates: selected.geometryCoordinates,
              verified: selected.verified,
              source: selected.source,
              dayColorKey: dateKeyForTripDay(startDate, day.day),
              kind: "itinerary" as const,
              segments: selected.details?.segments,
            },
          ];
        })
      );

    if (
      (directionsActive || directionsSearchOpen ||
        (directionsStatus === "ready" &&
          selectedDirectionOrigin &&
          selectedNavigationDestination)) &&
      selectedDayDirectionLegs.length > 0 &&
      activePlanDay != null
    ) {
      const activeDay = displayedPlan.days.find(
        (day) => day.day === activePlanDay
      );
      selectedDayDirectionLegs
        .map((leg, index) => ({ leg, index }))
        .filter(
          ({ leg, index }) =>
            isDrawableTransportRoute(leg) &&
            !activeDay?.transportLegs.some((planLeg) =>
              transportLegsMatch(planLeg, dayDirectionLegs[index])
            )
        )
        .forEach(({ leg, index }) => {
          itineraryRoutes.push({
            key: directionTransportRouteMapKey(activePlanDay, index, leg),
            mode: leg.mode,
            fromPlace: dayDirectionLegs[index]?.fromPlace ?? "Vị trí của tôi",
            toPlace: dayDirectionLegs[index]?.toPlace ?? "Điểm đến",
            distanceMeters: leg.distanceMeters,
            estimatedDurationMinutes: leg.estimatedDurationMinutes,
            coordinates: leg.geometryCoordinates,
            verified: leg.verified,
            source: leg.source,
            dayColorKey: dateKeyForTripDay(startDate, activePlanDay),
            kind: index === 0 ? "current_location" : "itinerary",
            segments: leg.details?.segments,
          });
        });
    }
    return itineraryRoutes;
  }, [
    activePlanDay,
    directionsActive,
    directionsSearchOpen,
    directionsStatus,
    selectedDirectionOrigin,
    selectedNavigationDestination,
    displayedExploreResult?.explorer.tripIntent.timing.startDate,
    displayedPlan,
    selectedPlanLegOptionKeys,
    dayDirectionLegs,
    selectedDayDirectionLegs,
  ]);
  const selectedMapRoute = useMemo(
    () => mapRoutes.find((route) => route.key === selectedMapRouteKey) ?? null,
    [mapRoutes, selectedMapRouteKey]
  );

  async function requestDayDirections(
    origin: PlannerMapCurrentLocation,
    destination: DirectionStop | null = directionsDestinationRef.current,
    focusNavigation = false
  ) {
    const destinations = destination ? [destination] : activeDayDirectionStops;
    if (activePlanDay == null || destinations.length === 0) {
      return;
    }
    const requestId = ++directionsRequestIdRef.current;
    setDayDirectionLegs([]);
    setDirectionsStatus("routing");
    setDirectionsError("");
    try {
      const legs = await calculateDayDirections({
        origin: {
          latitude: origin.latitude,
          longitude: origin.longitude,
          name: origin.label,
        },
        destinations: destinations.map((stop) => ({
          itemId: stop.itemId ?? null,
          name: stop.name,
          address: stop.address ?? null,
          latitude: stop.latitude,
          longitude: stop.longitude,
        })),
        departureTime: new Date().toISOString(),
      });
      if (requestId !== directionsRequestIdRef.current) return;
      setDayDirectionLegs(legs);
      const planDay = displayedPlan?.days.find(
        (day) => day.day === activePlanDay
      );
      if (planDay) {
        const synchronizedModes: Record<number, string> = {};
        legs.forEach((leg, navigationLegIndex) => {
          const planLegIndex = planDay.transportLegs.findIndex((planLeg) =>
            transportLegsMatch(planLeg, leg)
          );
          if (planLegIndex < 0) return;
          const selectedMode =
            selectedPlanLegOptionKeys[
              planLegSelectionKey(planDay.day, planLegIndex)
            ];
          if (selectedMode) {
            synchronizedModes[navigationLegIndex] = selectedMode;
          }
        });
        setSelectedDirectionOptionKeys(synchronizedModes);
      }
      setDirectionsStatus("ready");
      // Enter the navigation camera as soon as route geometry is available,
      // so the first directions click also applies the compass bearing.
      if (focusNavigation) {
        setLocationFocusRequest((current) => current + 1);
      }
    } catch (caught) {
      if (requestId !== directionsRequestIdRef.current) return;
      setDayDirectionLegs([]);
      setDirectionsStatus("error");
      const message = caught instanceof Error ? caught.message : "";
      setDirectionsError(
        message.trim().toLowerCase() === "not found"
          ? "Backend chưa có endpoint chỉ đường theo ngày. Hãy khởi động lại backend với bản code mới."
          : message
          ? message
          : "Không thể tính đường cho ngày đang chọn."
      );
    }
  }

  function locateCurrentPosition() {
    if (!("geolocation" in navigator)) {
      placeLocationTargetRef.current = null;
      setLocationStatus("error");
      setLocationError("Trình duyệt này không hỗ trợ định vị.");
      return;
    }
    if (!window.isSecureContext) {
      placeLocationTargetRef.current = null;
      setLocationStatus("error");
      setLocationError(
        "Định vị cần HTTPS hoặc localhost. Hãy mở ứng dụng qua kết nối an toàn."
      );
      return;
    }

    setLocationStatus("locating");
    setLocationError("");
    void requestDeviceHeadingPermission();
    if (locationWatchIdRef.current != null) {
      navigator.geolocation.clearWatch(locationWatchIdRef.current);
      locationWatchIdRef.current = null;
    }

    locationWatchIdRef.current = navigator.geolocation.watchPosition(
      (position) => {
        const isFirstLocationFix = latestLocationRef.current == null;
        const directionsWereWaiting = directionsPendingLocationRef.current;
        const previousHeading = latestLocationRef.current?.heading ?? null;
        const nextLocation = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          heading:
            normalizeDeviceHeading(position.coords.heading) ?? previousHeading,
        };
        latestLocationRef.current = nextLocation;
        setCurrentLocation(nextLocation);
        const pendingPlaceTarget = placeLocationTargetRef.current;
        if (pendingPlaceTarget) {
          placeLocationTargetRef.current = null;
          setPlaceLocationTarget(null);
          applyCurrentLocationToPlaceSearch(pendingPlaceTarget, nextLocation);
        }
        if (
          !directionsWereWaiting &&
          (isFirstLocationFix || locationStatus === "locating")
        ) {
          setLocationFocusRequest((current) => current + 1);
        }
        if (directionsWereWaiting) {
          directionsPendingLocationRef.current = false;
          void requestDayDirections(
            {
              ...nextLocation,
              label: "Vị trí của tôi",
              kind: "device",
            },
            directionsDestinationRef.current,
            true
          );
        }
        setLocationStatus("ready");
      },
      (geolocationError) => {
        const directionsWereWaiting = directionsPendingLocationRef.current;
        directionsPendingLocationRef.current = false;
        setLocationStatus("error");
        setLocationError(geolocationErrorMessage(geolocationError));
        placeLocationTargetRef.current = null;
        if (directionsWereWaiting) {
          setDirectionsStatus("error");
          setDirectionsError(
            "Không thể bắt đầu chỉ đường khi chưa lấy được vị trí."
          );
        }
      },
      {
        enableHighAccuracy: true,
        timeout: 12_000,
        maximumAge: 5_000,
      }
    );
  }

  function recenterCurrentPosition() {
    directionsPendingLocationRef.current = directionsActive && !currentLocation;
    if (currentLocation) {
      setLocationFocusRequest((current) => current + 1);
    }
    locateCurrentPosition();
  }

  function applyCurrentLocationToPlaceSearch(
    target: PlaceLocationTarget,
    location: Pick<PlannerMapCurrentLocation, "latitude" | "longitude">
  ) {
    const suggestion: PlaceSuggestion = {
      name: "Vị trí hiện tại",
      address: `Tọa độ ${location.latitude.toFixed(
        6
      )}, ${location.longitude.toFixed(6)}`,
      latitude: location.latitude,
      longitude: location.longitude,
    };

    if (target === "add") {
      setAddName(suggestion.name);
      setSelectedSuggestion(suggestion);
      setPlaceSuggestions([]);
      setAddSearchCompleted(false);
      setAddSearchFailed(false);
      return;
    }

    setEditingItem((current) =>
      current ? { ...current, name: suggestion.name } : current
    );
    setSelectedEditSuggestion(suggestion);
    setEditPlaceSuggestions([]);
    setEditSearchCompleted(false);
    setEditSearchFailed(false);
  }

  function useCurrentLocationForPlace(target: PlaceLocationTarget) {
    setPlaceLocationTarget(target);
    setLocationError("");
    if (currentLocation) {
      placeLocationTargetRef.current = null;
      applyCurrentLocationToPlaceSearch(target, currentLocation);
      setPlaceLocationTarget(null);
      return;
    }
    placeLocationTargetRef.current = target;
    locateCurrentPosition();
  }

  async function requestDeviceHeadingPermission() {
    if (!("DeviceOrientationEvent" in window)) return;
    const orientationEvent =
      window.DeviceOrientationEvent as DeviceOrientationPermissionEvent;
    try {
      if (typeof orientationEvent.requestPermission === "function") {
        const permission = await orientationEvent.requestPermission();
        if (permission !== "granted") return;
      }
      enableDeviceHeadingTracking();
    } catch {
      // GPS heading is still enough while the user is moving.
    }
  }

  function enableDeviceHeadingTracking() {
    if (orientationTrackingRef.current) return;
    orientationTrackingRef.current = true;
    const listener = (event: DeviceOrientationEvent) => {
      updateDeviceHeading(event);
    };
    orientationListenerRef.current = listener;
    window.addEventListener("deviceorientation", listener, true);
    window.addEventListener("deviceorientationabsolute", listener, true);
  }

  function updateDeviceHeading(event: DeviceOrientationEvent) {
    const heading = headingFromOrientationEvent(event);
    if (heading == null) return;
    latestLocationRef.current = latestLocationRef.current
      ? { ...latestLocationRef.current, heading }
      : null;
    setCurrentLocation((current) => {
      if (!current) return current;
      return { ...current, heading };
    });
  }

  function startDayDirections(
    destination = activeNavigationDestination,
    originOverride?: PlannerMapCurrentLocation | null
  ) {
    if (activePlanDay == null || !destination) {
      setDirectionsStatus("error");
      setDirectionsError(
        "Chọn một ngày có địa điểm trước khi bắt đầu chỉ đường."
      );
      return;
    }
    const origin = originOverride ?? selectedDirectionOrigin ?? currentLocation;
    setNavigationDestinationKey(destination.mapKey);
    setSelectedNavigationDestination(destination);
    setDestinationQuery(destination.name);
    directionsDestinationRef.current = destination;
    setSelectedDirectionOrigin(origin);
    setSelectedDirectionOptionKeys({});
    setDirectionsActive(true);
    if (origin) {
      void requestDayDirections(origin, destination, true);
      return;
    }
    directionsPendingLocationRef.current = true;
    setDirectionsStatus("routing");
    locateCurrentPosition();
  }

  function openDirectionsSearch() {
    const initialDestination = activeNavigationDestination;
    setDirectionsSearchOpen(true);
    setDirectionOriginSuggestions([]);
    let nextOrigin: PlannerMapCurrentLocation | null = selectedDirectionOrigin;
    if (selectedDirectionOrigin) {
      setDirectionOriginQuery(
        selectedDirectionOrigin.kind === "device"
          ? "Vị trí hiện tại"
          : selectedDirectionOrigin.label ?? ""
      );
    } else {
      if (currentLocation) {
        nextOrigin = {
          ...currentLocation,
          label: "Vị trí của tôi",
          kind: "device",
        };
        setSelectedDirectionOrigin(nextOrigin);
        setDirectionOriginQuery("Vị trí hiện tại");
      } else {
        nextOrigin = null;
        setDirectionOriginQuery("");
      }
    }
    if (initialDestination && !selectedNavigationDestination) {
      setSelectedNavigationDestination(initialDestination);
      setDestinationQuery(initialDestination.name);
    }
    if (nextOrigin && initialDestination) {
      directionsDestinationRef.current = initialDestination;
      void requestDayDirections(nextOrigin, initialDestination);
    }
  }

  function closeDirectionsSearch() {
    setDirectionsSearchOpen(false);
    setDirectionOriginSuggestions([]);
  }

  function chooseDirectionOrigin(place: PlannerMapSearchPlace) {
    setSelectedDirectionOrigin({
      latitude: place.latitude,
      longitude: place.longitude,
      accuracy: 0,
      heading: null,
      label: place.name,
      detail: place.detail ?? "Điểm đi đã chọn",
      kind: "searched",
    });
    setDirectionOriginQuery(place.name);
    setDirectionOriginSuggestions([]);
    if (selectedNavigationDestination) {
      void requestDayDirections(
        {
          latitude: place.latitude,
          longitude: place.longitude,
          accuracy: 0,
          heading: null,
          label: place.name,
          detail: place.detail ?? "Điểm đi đã chọn",
          kind: "searched",
        },
        selectedNavigationDestination
      );
    }
  }

  function updateDirectionOriginQuery(value: string) {
    setDirectionOriginQuery(value);
    setSelectedDirectionOrigin(null);
    directionsRequestIdRef.current += 1;
    setDayDirectionLegs([]);
    setDirectionsStatus("idle");
  }

  function chooseCurrentDirectionOrigin() {
    if (currentLocation) {
      setSelectedDirectionOrigin({
        ...currentLocation,
        label: "Vị trí của tôi",
        kind: "device",
      });
      setDirectionOriginQuery("Vị trí hiện tại");
      setDirectionOriginSuggestions([]);
      if (selectedNavigationDestination) {
        void requestDayDirections(
          {
            ...currentLocation,
            label: "Vị trí của tôi",
            kind: "device",
          },
          selectedNavigationDestination
        );
      }
      return;
    }
    locateCurrentPosition();
  }

  function updateDirectionDestinationQuery(value: string) {
    setDestinationQuery(value);
    setSelectedNavigationDestination(null);
    setNavigationDestinationKey(null);
    directionsRequestIdRef.current += 1;
    setDayDirectionLegs([]);
    setDirectionsStatus("idle");
  }

  function chooseDirectionDestination(place: PlannerMapSearchPlace) {
    const planStop = activeDayDirectionStops.find(
      (stop) =>
        stop.latitude === place.latitude && stop.longitude === place.longitude
    );
    const destination: DirectionStop = planStop ?? {
      itemId: null,
      name: place.name.replace(/^Point \d+ · /, ""),
      address: place.detail,
      latitude: place.latitude,
      longitude: place.longitude,
      mapKey: place.kind === "plan" ? place.key : null,
    };
    setSelectedNavigationDestination(destination);
    setNavigationDestinationKey(destination.mapKey);
    setDestinationQuery(place.name);
    directionsDestinationRef.current = destination;
    if (selectedDirectionOrigin) {
      void requestDayDirections(selectedDirectionOrigin, destination);
    }
  }

  function submitDirectionSearch() {
    if (!selectedNavigationDestination || !selectedDirectionOrigin) return;
    setDirectionsSearchOpen(false);
    startDayDirections(selectedNavigationDestination, selectedDirectionOrigin);
  }

  function clearDayDirections() {
    directionsPendingLocationRef.current = false;
    directionsRequestIdRef.current += 1;
    setDirectionsActive(false);
    setDirectionsSearchOpen(false);
    setDirectionsError("");
    setSelectedMapPlaceKey(null);
    setSelectedMapRouteKey(null);
  }

  async function chooseDirectionOption(
    legIndex: number,
    option: TransportOption
  ) {
    const mode = option.mode;
    const optionKey = transportOptionSelectionKey(option);
    const previousDirectionRouteKey =
      activePlanDay != null
        ? directionTransportRouteMapKey(
            activePlanDay,
            legIndex,
            selectedTransportOption(
              dayDirectionLegs[legIndex],
              selectedDirectionOptionKeys[legIndex]
            )
          )
        : null;
    setSelectedDirectionOptionKeys((current) => ({
      ...current,
      [legIndex]: optionKey,
    }));
    if (
      previousDirectionRouteKey &&
      activePlanDay != null &&
      selectedMapRouteKey === previousDirectionRouteKey
    ) {
      setSelectedMapRouteKey(
        directionTransportRouteMapKey(activePlanDay, legIndex, option)
      );
    }
    if (activePlanDay != null && isDrawableTransportRoute(option)) {
      setSelectedMapPlaceKey(null);
      setSelectedMapRouteKey(
        directionTransportRouteMapKey(activePlanDay, legIndex, option)
      );
      setRouteFocusRequest((current) => current + 1);
    }
    const navigationLeg = dayDirectionLegs[legIndex];
    const planDay = displayedPlan?.days.find(
      (day) => day.day === activePlanDay
    );
    if (!navigationLeg || !planDay) return;
    const planLegIndex = planDay.transportLegs.findIndex((leg) =>
      transportLegsMatch(leg, navigationLeg)
    );
    if (planLegIndex >= 0) {
      setSelectedPlanLegOptionKeys((current) => ({
        ...current,
        [planLegSelectionKey(planDay.day, planLegIndex)]: optionKey,
      }));
      await choosePlanTransportOption(planDay.day, planLegIndex, option);
    }
  }

  async function choosePlanTransportOption(
    day: number,
    legIndex: number,
    option: TransportOption
  ) {
    const mode = option.mode;
    const optionKey = transportOptionSelectionKey(option);
    const selectionKey = planLegSelectionKey(day, legIndex);
    const previousOptionKeys = selectedPlanLegOptionKeys;
    const previousPlan = plan;
    const currentPlanLeg = displayedPlan?.days.find(
      (planDay) => planDay.day === day
    )?.transportLegs[legIndex];
    const previousPlanRouteKey = currentPlanLeg
      ? planTransportRouteMapKey(
          day,
          legIndex,
          selectedTransportOption(
            currentPlanLeg,
            selectedPlanLegOptionKeys[selectionKey]
          )
        )
      : null;
    setSelectedPlanLegOptionKeys((current) => ({
      ...current,
      [selectionKey]: optionKey,
    }));
    if (previousPlanRouteKey && selectedMapRouteKey === previousPlanRouteKey) {
      setSelectedMapRouteKey(planTransportRouteMapKey(day, legIndex, option));
    }
    if (plan) {
      setPlan(promoteTransportOptionInPlan(plan, day, legIndex, option));
    }
    setDirectionsActive(false);
    if (isDrawableTransportRoute(option)) {
      setSelectedMapPlaceKey(null);
      setSelectedMapRouteKey(planTransportRouteMapKey(day, legIndex, option));
      setRouteFocusRequest((current) => current + 1);
    }
    const planLeg = displayedPlan?.days.find((planDay) => planDay.day === day)
      ?.transportLegs[legIndex];
    if (!planLeg) return;
    const navigationLegIndex = dayDirectionLegs.findIndex((leg) =>
      transportLegsMatch(leg, planLeg)
    );
    if (navigationLegIndex >= 0) {
      setSelectedDirectionOptionKeys((current) => ({
        ...current,
        [navigationLegIndex]: optionKey,
      }));
    }
    if (!activeChatId || !previousPlan) return;

    setSavingTransportOptionKey(selectionKey);
    setError("");
    try {
      const updatedChat = await selectTripChatTransportOption({
        chatId: activeChatId,
        expectedRevision: chatRevision,
        day,
        legIndex,
        mode,
        optionKey,
        source: option.source,
        distanceMeters: option.distanceMeters,
        estimatedDurationMinutes: option.estimatedDurationMinutes,
      });
      setChatRevision(updatedChat.revision);
      if (updatedChat.currentPlan) setPlan(updatedChat.currentPlan);
      showPlannerToast("Đã chọn phương tiện");
    } catch (caught: any) {
      setSelectedPlanLegOptionKeys(previousOptionKeys);
      setPlan(previousPlan);
      setError(caught?.message || "Không thể lưu lựa chọn phương tiện.");
    } finally {
      setSavingTransportOptionKey(null);
    }
  }

  async function retryPlanTransportLeg(day: number, legIndex: number) {
    const retryKey = planLegSelectionKey(day, legIndex);
    const chatId = activeChatIdRef.current ?? activeChatId ?? initialChatId;
    if (!chatId) {
      setTransportLegRetryErrors((current) => ({
        ...current,
        [retryKey]: "Không thể lưu tuyến khi chưa mở chuyến đi.",
      }));
      return;
    }

    setRetryingTransportLegKey(retryKey);
    setTransportLegRetryErrors((current) => {
      const next = { ...current };
      delete next[retryKey];
      return next;
    });
    try {
      const updatedChat = await retryTripChatTransportLeg({
        chatId,
        expectedRevision: chatRevision,
        day,
        legIndex,
      });
      setChatRevision(updatedChat.revision);
      if (updatedChat.currentPlan) setPlan(updatedChat.currentPlan);
      setSelectedPlanLegOptionKeys((current) => {
        const next = { ...current };
        delete next[retryKey];
        return next;
      });
      showPlannerToast("Đã tính lại tuyến đường");
    } catch (caught: any) {
      setTransportLegRetryErrors((current) => ({
        ...current,
        [retryKey]: caught?.message || "Vẫn chưa tính được tuyến. Hãy thử lại.",
      }));
    } finally {
      setRetryingTransportLegKey(null);
    }
  }

  useEffect(() => {
    const chatId = activeChatIdRef.current ?? activeChatId ?? initialChatId;
    if (!chatId || !displayedPlan || retryingTransportLegKey) return;

    for (const day of displayedPlan.days) {
      for (let legIndex = 0; legIndex < day.transportLegs.length; legIndex += 1) {
        const leg = day.transportLegs[legIndex];
        if (transportOptionsForLeg(leg).length > 0) continue;
        const attemptKey = [
          chatId,
          day.day,
          legIndex,
          leg.mode,
          leg.source,
          Math.round(leg.distanceMeters),
        ].join(":");
        if (autoRetriedTransportLegKeysRef.current.has(attemptKey)) continue;
        autoRetriedTransportLegKeysRef.current.add(attemptKey);
        void retryPlanTransportLeg(day.day, legIndex);
        return;
      }
    }
  }, [
    activeChatId,
    chatRevision,
    displayedPlan,
    initialChatId,
    retryingTransportLegKey,
  ]);

  function selectRouteOnMapWithoutFocus(routeKey: string) {
    setSelectedMapPlaceKey(null);
    setSelectedMapRouteKey(routeKey);
  }

  function focusRouteOnMap(routeKey: string) {
    if (selectedMapRouteKey === routeKey) {
      setSelectedMapRouteKey(null);
      return;
    }
    setSelectedMapPlaceKey(null);
    setSelectedMapRouteKey(routeKey);
    setRouteFocusRequest((current) => current + 1);
    // On phones the itinerary is a sheet layered above the map. Collapse it
    // before scrolling so the selected route is actually visible to the user.
    setMobileItineraryExpanded(false);
    window.requestAnimationFrame(() => {
      document.querySelector(".plannerMap")?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    });
  }

  const selectRouteFromMap = useCallback(
    (routeKey: string) => {
      if (selectedMapRouteKey === routeKey) {
        setSelectedMapRouteKey(null);
        return;
      }
      setSelectedMapPlaceKey(null);
      setSelectedMapRouteKey(routeKey);
      setRouteFocusRequest((current) => current + 1);
      window.requestAnimationFrame(() => {
        const matchingRoute = Array.from(
          document.querySelectorAll<HTMLElement>("[data-map-route-key]")
        ).find((element) => element.dataset.mapRouteKey === routeKey);
        matchingRoute?.scrollIntoView({ behavior: "smooth", block: "center" });
        const focusTarget =
          matchingRoute?.querySelector<HTMLElement>("button, summary") ??
          matchingRoute;
        focusTarget?.focus({ preventScroll: true });
      });
    },
    [selectedMapRouteKey]
  );

  function selectRouteFromItinerary(routeKey: string) {
    focusRouteOnMap(routeKey);
  }

  function handleItineraryRouteHighlight(
    event: ReactMouseEvent<HTMLButtonElement>,
    routeKey: string
  ) {
    event.stopPropagation();
    if (selectedMapRouteKey === routeKey) {
      setSelectedMapRouteKey(null);
      return;
    }
    focusRouteOnMap(routeKey);
  }

  function focusPlaceOnMap(mapKey: string) {
    setSelectedMapRouteKey(null);
    setSelectedMapPlaceKey(mapKey);
    setMobileItineraryExpanded(false);
    window.requestAnimationFrame(() => {
      document.querySelector(".plannerMap")?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    });
  }

  function selectItinerarySearchResult(result: ItinerarySearchResult) {
    const item = displayedPlan?.days.find((day) => day.day === result.day)
      ?.items[result.itemIndex];
    if (!item) return;

    const mapKey = hasPlanItemCoordinates(item)
      ? planItemMapKey({
          day: result.day,
          itemId: item.itemId,
          itemIndex: result.itemIndex,
          name: item.name,
        })
      : null;

    setActivePlanDay(result.day);
    setItinerarySearchQuery("");
    setSelectedMapRouteKey(null);
    setSelectedMapPlaceKey(mapKey);
    clearDayDirections();

    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const matchingCard = Array.from(
          document.querySelectorAll<HTMLElement>("[data-itinerary-search-key]")
        ).find(
          (element) => element.dataset.itinerarySearchKey === result.key
        );
        matchingCard?.scrollIntoView({ behavior: "smooth", block: "center" });
        matchingCard?.focus({ preventScroll: true });
      });
    });
  }

  function isInteractiveItineraryTarget(
    target: EventTarget | null,
    card: HTMLElement
  ) {
    if (!(target instanceof Element)) return false;
    const interactiveTarget = target.closest(
      'button, a, input, textarea, select, summary, [role="button"], [role="tab"], [role="option"]'
    );
    return interactiveTarget != null && interactiveTarget !== card;
  }

  function clearMapHighlight() {
    if (!selectedMapPlaceKey && !selectedMapRouteKey) return;
    setSelectedMapPlaceKey(null);
    setSelectedMapRouteKey(null);
  }

  function clearMapHighlightFromExternalControlClick(
    event: ReactMouseEvent<HTMLElement>
  ) {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest(".plannerMap")) return;
    // Route controls own their select/cancel toggle. Clearing during the
    // capture phase would render the button again before its click handler
    // runs, causing a cancel click to immediately select the route again.
    if (target.closest(".itineraryRouteMapButton")) return;
    if (
      !target.closest(
        'button, a, input, textarea, select, summary, [role="button"], [role="tab"], [role="option"]'
      )
    )
      return;
    clearMapHighlight();
  }

  const selectPlaceFromMap = useCallback((mapKey: string) => {
    setSelectedMapRouteKey(null);
    setSelectedMapPlaceKey(mapKey);
  }, []);

  const locationMessage = useMemo(() => {
    if (directionsStatus === "routing" && activePlanDay != null) {
      return "Đang tính tuyến đường…";
    }
    if (locationStatus === "locating") {
      return "Đang lấy vị trí từ thiết bị…";
    }
    if (locationStatus === "error") {
      return locationError;
    }
    if (directionsStatus === "error") return directionsError;
    if (directionsStatus === "ready" && dayDirectionLegs.length > 0) {
      const totalMinutes = selectedDayDirectionLegs.reduce(
        (total, leg) => total + leg.estimatedDurationMinutes,
        0
      );
      const totalDistanceMeters = selectedDayDirectionLegs.reduce(
        (total, leg) => total + leg.distanceMeters,
        0
      );
      const totalKilometers = (totalDistanceMeters / 1000).toLocaleString(
        "vi-VN",
        {
          maximumFractionDigits: 1,
          minimumFractionDigits: totalDistanceMeters < 1000 ? 1 : 0,
        }
      );
      return `⏱ ${formatDuration(totalMinutes)} · ${totalKilometers} km`;
    }
    return null;
  }, [
    activePlanDay,
    dayDirectionLegs,
    directionsError,
    directionsStatus,
    locationError,
    locationStatus,
    selectedDayDirectionLegs,
  ]);

  function updatedTripIntentForStep(
    intent: TripIntent,
    step: Exclude<GuidedIntakeStep, "complete">,
    answer: string
  ): TripIntent {
    if (step === "destination") {
      return { ...intent, destination: answer };
    }
    if (step === "dates") {
      const hasDates = Boolean(guidedStartDate && guidedEndDate);
      return {
        ...intent,
        timing: {
          ...intent.timing,
          startDate: hasDates ? guidedStartDate : null,
          endDate: hasDates ? guidedEndDate : null,
          days: hasDates
            ? tripDaysBetween(guidedStartDate, guidedEndDate)
            : intent.timing.days,
          flexibility: hasDates ? "fixed" : "unknown",
        },
      };
    }
    if (step === "travelers") {
      const type = travelerCounts.children || travelerCounts.infants
        ? "family"
        : travelerCounts.adults === 1
          ? "solo"
          : travelerCounts.adults === 2
            ? "couple"
            : "group";
      return {
        ...intent,
        travelParty: {
          ...intent.travelParty,
          ...travelerCounts,
          type,
        },
      };
    }
    if (step === "budget") {
      return { ...intent, budget: budgetFromAnswer(answer, intent.budget) };
    }
    return { ...intent, notes: answer ? [answer] : [] };
  }

  async function saveGuidedTripIntent(
    step: Exclude<GuidedIntakeStep, "complete">,
    answer: string
  ) {
    const currentIntent = exploreResult?.explorer.tripIntent;
    if (!activeChatId || !currentIntent) return false;
    setSavingTripIntent(true);
    setError("");
    try {
      let updated: TripChat;
      try {
        updated = await updateTripChatIntent({
          chatId: activeChatId,
          expectedRevision: chatRevision,
          expectedTripIntentVersion: tripIntentVersion,
          tripIntent: updatedTripIntentForStep(currentIntent, step, answer),
        });
      } catch (caught) {
        if (
          !(caught instanceof APIError) ||
          (caught.code !== "VERSION_CONFLICT" &&
            caught.code !== "TRIP_INTENT_SUPERSEDED")
        ) {
          throw caught;
        }
        const latest = await getTripChat(activeChatId);
        if (!latest.currentTripIntent) throw caught;
        updated = await updateTripChatIntent({
          chatId: activeChatId,
          expectedRevision: latest.revision,
          expectedTripIntentVersion: latest.tripIntentVersion,
          tripIntent: updatedTripIntentForStep(
            latest.currentTripIntent,
            step,
            answer
          ),
        });
      }
      applyTripChat(updated);
      setTripChats((current) => [
        {
          id: updated.id,
          title: updated.title,
          destination: updated.destination,
          revision: updated.revision,
          hasPlan: updated.hasPlan,
          createdAt: updated.createdAt,
          updatedAt: updated.updatedAt,
        },
        ...current.filter((chat) => chat.id !== updated.id),
      ]);
      void listTripChats()
        .then(setTripChats)
        .catch(() => {
          // The PATCH response already updated the visible chat and sidebar.
        });
      showPlannerToast("Đã lưu thông tin; lịch trình đang được đồng bộ nền");
      return true;
    } catch (caught) {
      if (caught instanceof APIError && caught.code === "VERSION_CONFLICT") {
        try {
          const latest = await getTripChat(activeChatId);
          applyTripChat(latest);
        } catch {
          // Keep the original version-conflict error visible to the user.
        }
      }
      setError(
        caught instanceof Error
          ? caught.message
          : "Không thể cập nhật thông tin chuyến đi."
      );
      return true;
    } finally {
      setSavingTripIntent(false);
    }
  }

  async function submitGuidedAnswer(rawAnswer: string) {
    if (guidedIntakeStep === "complete") return;
    const answer = rawAnswer.trim();
    if (!answer) {
      setError("Bạn có thể trả lời ngắn hoặc chọn Bỏ qua.");
      return;
    }

    const effectiveAnswer = answer === "Bỏ qua" ? "" : answer;
    const nextAnswers = {
      ...guidedIntakeAnswers,
      [guidedIntakeStep]: effectiveAnswer,
    };
    setGuidedIntakeAnswers(nextAnswers);
    setGuidedDraft(nextAnswers[guidedIntakeStep] ?? "");
    setError("");
    // Đóng hộp thoại ngay khi bắt đầu lưu để người dùng không bị giữ lại
    // trước màn hình "Đang cập nhật…" trong lúc request ghi vào DB hoàn tất.
    setGuidedIntakeOpen(false);
    if (
      await saveGuidedTripIntent(
        guidedIntakeStep,
        effectiveAnswer
      )
    ) {
      return;
    }
    showPlannerToast(
      `Đã cập nhật ${
        guidedIntakeQuestions[guidedIntakeStep].replace(/[?？]$/, "")
      }`
    );

    if (guidedIntakeStep === guidedIntakeOrder[guidedIntakeOrder.length - 1]) {
      setGuidedIntakeStep("complete");
      setGuidedIntakeOpen(false);
      setGuidedDraft("");
      void sendMessage(buildGuidedIntakeRequest(nextAnswers), false);
    }
  }

  function submitGuidedDates() {
    if (
      activeChatId &&
      exploreResult?.explorer.tripIntent &&
      Boolean(guidedStartDate) !== Boolean(guidedEndDate)
    ) {
      setError("Chọn đủ ngày bắt đầu và ngày kết thúc.");
      return;
    }
    let answer = "Bỏ qua";
    if (guidedStartDate && guidedEndDate) {
      answer = `${formatPlannerDate(guidedStartDate)} đến ${formatPlannerDate(
        guidedEndDate
      )}`;
    } else if (guidedStartDate) {
      answer = `Bắt đầu ${formatPlannerDate(guidedStartDate)}`;
    } else if (guidedEndDate) {
      answer = `Kết thúc trước ${formatPlannerDate(guidedEndDate)}`;
    }
    void submitGuidedAnswer(answer);
  }

  function updateTravelerCount(key: keyof TravelerCounts, delta: number) {
    const option = travelerOptions.find((candidate) => candidate.key === key);
    if (!option) return;
    setTravelerCounts((current) => ({
      ...current,
      [key]: clamp(current[key] + delta, option.minimum, option.maximum),
    }));
  }

  function openGuidedStep(step: Exclude<GuidedIntakeStep, "complete">) {
    const intent = exploreResult?.explorer.tripIntent;
    setGuidedIntakeStep(step);
    if (intent) {
      setGuidedIntakeAnswers(guidedAnswersFromTripIntent(intent));
      setGuidedStartDate(intent.timing.startDate ?? "");
      setGuidedEndDate(
        defaultTripEndDate(
          intent.timing.startDate,
          intent.timing.endDate,
          intent.timing.days
        )
      );
      setTravelerCounts({
        adults: intent.travelParty.adults,
        children: intent.travelParty.children,
        infants: intent.travelParty.infants,
        pets: intent.travelParty.pets,
      });
    }
    setGuidedDraft(
      intent
        ? step === "destination"
          ? intent.destination
          : step === "budget"
            ? formatTripBudget(intent)
            : step === "note"
              ? intent.notes.join(" · ")
              : guidedIntakeAnswers[step] ?? ""
        : guidedIntakeAnswers[step] ?? ""
    );
    setGuidedIntakeOpen(true);
    setError("");
  }

  async function sendMessage(requestText?: string, displayUserMessage = true) {
    const typedText = requestText?.trim() ?? prompt.trim();
    if (!typedText) {
      setError("Nhập yêu cầu hoặc dán URL trước khi gửi.");
      return;
    }
    if (!user) {
      const next = `${window.location.pathname}${window.location.search}`;
      router.push(`/login?next=${encodeURIComponent(next)}`);
      return;
    }
    const text = typedText;
    const requestUrls = extractMessageUrls(text);
    if (requestUrls.length > 20) {
      setError("Mỗi lần chỉ có thể gửi tối đa 20 URL.");
      return;
    }

    const userMessage: ChatMessage = {
      id: Date.now(),
      role: "user",
      text,
    };
    if (displayUserMessage) setMessages((current) => [...current, userMessage]);
    setPrompt("");
    const guestShortcut =
      !user && requestUrls.length === 0
        ? guestConversationShortcut(text)
        : null;
    if (guestShortcut) {
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: guestShortcut.response,
        },
      ]);
      setError("");
      return;
    }
    if (!plan) {
      setInitialPlanningActive(true);
      setWorkflowStage(user ? "classifying" : "preparing");
    }
    if (!user) {
      setBackgroundPlanning(true);
      const createdGuestJobs: GuestUrlImportJob[] = [];
      if (requestUrls.length > 0) {
        createdGuestJobs.push(
          ...enqueueGuestUrlJobs({ content: text, urls: requestUrls })
        );
      } else {
        createdGuestJobs.push(enqueueGuestPromptJob({ content: text }));
      }
      setActivePlanningJobs(
        createdGuestJobs.map((job) => ({ id: job.id, guest: true }))
      );
      setError("");
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: requestUrls.length > 0
            ? `Mình đang đọc ${requestUrls.length} nguồn và tìm các địa điểm có bằng chứng. Bạn có thể tiếp tục ở đây trong lúc nguồn được xử lý.`
            : "Mình đang chuẩn bị và lập lịch trình. Bạn có thể chuyển sang màn hình khác trong lúc tác vụ chạy nền.",
        },
      ]);
      return;
    }
    if (user && requestUrls.length > 0) {
      setQueueingUrls(true);
      setBackgroundPlanning(true);
      setError("");
      try {
        let chatId = activeChatId;
        let expectedRevision = chatRevision;
        if (!chatId) {
          const created = await createTripChat();
          chatId = created.id;
          expectedRevision = created.revision;
          activeChatIdRef.current = chatId;
          setActiveChatId(chatId);
          setChatRevision(created.revision);
          syncPlannerChatUrl(chatId);
        }
        let queued = false;
        let queuedJobs: UrlImportJob[] = [];
        for (let attempt = 0; attempt < 3; attempt += 1) {
          try {
            if (requestUrls.length > 0) {
              const batch = await enqueueTripChatUrls({
                chatId,
                content: text,
                expectedRevision,
                urls: requestUrls,
              });
              queuedJobs.push(...batch.jobs);
            }
            queued = true;
            break;
          } catch (caught) {
            if (
              !(caught instanceof APIError) ||
              caught.code !== "VERSION_CONFLICT" ||
              attempt === 2
            ) {
              throw caught;
            }
            const latest = await getTripChat(chatId);
            expectedRevision = latest.revision;
            applyTripChat(latest);
          }
        }
        if (!queued) throw new Error("Không thể thêm nguồn vào hàng chờ.");
        setActivePlanningJobs(
          queuedJobs.map((job) => ({ id: job.id, guest: false }))
        );
        setUrlJobSnapshot((current) => [
          ...queuedJobs,
          ...current.filter(
            (job) => !queuedJobs.some((queued) => queued.id === job.id)
          ),
        ]);
        setTripChats(await listTripChats());
        window.dispatchEvent(new CustomEvent("travelplanner:url-job-enqueued", {
          detail: queuedJobs
        }));
        setMessages((current) => [
          ...current,
          {
            id: Date.now() + 1,
            role: "assistant",
            text: `Mình đang đọc ${requestUrls.length} nguồn và tìm các địa điểm có bằng chứng. Bạn có thể tiếp tục ở đây trong lúc nguồn được xử lý.`,
          },
        ]);
      } catch (caught) {
        setBackgroundPlanning(false);
        setInitialPlanningActive(false);
        const message =
          caught instanceof Error
            ? caught.message
            : "Không thể thêm nguồn vào hàng chờ.";
        setError(message);
      } finally {
        setQueueingUrls(false);
      }
      return;
    }
    const requestId = activeRequestIdRef.current + 1;
    activeRequestIdRef.current = requestId;
    setLoading(true);
    setWorkflowStage("exploring");
    setError("");
    try {
      if (user) {
        let chatId = activeChatId;
        let expectedRevision = chatRevision;
        if (!chatId) {
          const created = await createTripChat();
          chatId = created.id;
          expectedRevision = created.revision;
          activeChatIdRef.current = chatId;
          setActiveChatId(chatId);
          setChatRevision(created.revision);
          syncPlannerChatUrl(chatId);
        }
        for (let attempt = 0; attempt < 3; attempt += 1) {
          try {
            const clientTurnId =
              typeof crypto !== "undefined" && "randomUUID" in crypto
                ? crypto.randomUUID()
                : `turn-${Date.now()}-${Math.random().toString(36).slice(2)}`;
            await conversationTurn.submitTurn({
              chatId,
              content: text,
              expectedRevision,
              clientTurnId,
              attachmentNames: [],
            });
            setSelectedMapPlaceKey(null);
            return;
          } catch (caught) {
            if (
              !(caught instanceof APIError) ||
              caught.code !== "VERSION_CONFLICT" ||
              attempt === 2
            ) {
              throw caught;
            }
            const latest = await getTripChat(chatId);
            expectedRevision = latest.revision;
            applyTripChat(latest);
          }
        }
        throw new Error("Không thể cập nhật chat.");
      }
      const nextExploreResult = await exploreFullIntake({
        rawRequest: text,
        images: [],
      });
      setExploreResult(nextExploreResult);
      setWorkflowStage("planning");
      const generation = await createPlanFromExplorer({
        context: nextExploreResult.explorer,
        intakeId: nextExploreResult.intakeId,
        userId: nextExploreResult.userId,
        allowFinderGapFill: nextExploreResult.allowFinderGapFill,
        allowReplaceSourcePlaces: nextExploreResult.allowReplaceSourcePlaces,
      });
      setPlan(generation.plan);
      if (generation.plan.routeEnrichmentStatus === "pending") {
        void enrichPlanRoutes(generation.plan.id)
          .then((enriched) => {
            if (activeRequestIdRef.current === requestId) setPlan(enriched);
          })
          .catch(() => {
            // The coarse plan remains usable; a later refresh can retry.
          });
      }
      setInitialPlanningActive(false);
      setWorkflowStage("ready");
      setSelectedMapPlaceKey(null);
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: nextExploreResult.allowFinderGapFill
            ? `Explorer đã hiểu yêu cầu cho ${nextExploreResult.explorer.tripIntent.destination}. Planner và Finder đã tạo lịch trình và có thể bổ sung địa điểm phù hợp.`
            : `Explorer đã hiểu yêu cầu cho ${nextExploreResult.explorer.tripIntent.destination}. Finder không thể bổ sung activity còn thiếu vào lịch trình này.`,
        },
      ]);
    } catch (caught) {
      if (activeRequestIdRef.current !== requestId) return;
      const message =
        caught instanceof Error ? caught.message : "Có lỗi xảy ra.";
      setInitialPlanningActive(false);
      setWorkflowStage("failed");
      setError(message);
      setMessages((current) => [
        ...current,
        { id: Date.now() + 1, role: "assistant", text: message },
      ]);
    } finally {
      if (activeRequestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }

  function resetWorkflow() {
    chatLoadControllerRef.current?.abort();
    chatLoadControllerRef.current = null;
    activeRequestIdRef.current += 1;
    activeChatIdRef.current = null;
    setLoading(false);
    setPrompt("");
    setUrlInput("");
    setUrlInputError("");
    setExploreResult(null);
    setPlan(null);
    setSelectedMapPlaceKey(null);
    setWorkflowStage("idle");
    setBackgroundPlanning(false);
    setInitialPlanningActive(false);
    setActivePlanningJobs([]);
    setChatCollapsed(false);
    setError("");
    setGuidedIntakeStep("destination");
    setGuidedIntakeOpen(false);
    setGuidedDraft("");
    setGuidedIntakeAnswers({});
    setGuidedStartDate("");
    setGuidedEndDate("");
    setTravelerCounts({ adults: 1, children: 0, infants: 0, pets: 0 });
    syncPlannerChatUrl(null);
    setMessages([
      {
        id: Date.now(),
        role: "assistant",
        text: NEW_CHAT_GREETING,
      },
    ]);
    if (user) {
      setActiveChatId(null);
      setChatRevision(0);
      setTripIntentVersion(0);
      setTripIntentPlanStatus("synced");
    }
  }

  async function cancelBackgroundPlanning() {
    const jobs = [...activePlanningJobs];
    setError("");
    await Promise.allSettled(
      jobs.map(async (job) => {
        if (job.guest) {
          deleteGuestUrlJob(job.id);
          return;
        }
        await deleteUrlImportJob(job.id);
      })
    );
    resetWorkflow();
    showPlannerToast("Đã dừng tác vụ và mở chat mới");
  }

  async function openTripChat(chatId: string) {
    syncPlannerChatUrl(chatId);
    if (chatId === activeChatIdRef.current) return;
    chatLoadControllerRef.current?.abort();
    const controller = new AbortController();
    chatLoadControllerRef.current = controller;
    activeRequestIdRef.current += 1;
    activeChatIdRef.current = chatId;
    setActiveChatId(chatId);
    setLoading(false);
    setBackgroundPlanning(false);
    setInitialPlanningActive(false);
    setActivePlanningJobs([]);
    setError("");
    try {
      const [chat, jobsResponse] = await Promise.all([
        getTripChat(chatId, { signal: controller.signal }),
        listUrlImportJobs().catch(() => ({ jobs: [] })),
      ]);
      if (!controller.signal.aborted && activeChatIdRef.current === chatId) {
        applyTripChat(chat);
        setPlannerEntryResolved(true);
        setUrlJobSnapshot(jobsResponse.jobs);
        const active = jobsResponse.jobs.filter(
          (job) =>
            job.chatId === chatId &&
            (job.status === "queued" || job.status === "running")
        );
        if (active.length) {
          setActivePlanningJobs(
            active.map((job) => ({ id: job.id, guest: false }))
          );
          setBackgroundPlanning(true);
          setInitialPlanningActive(!chat.currentPlan);
          setWorkflowStage(
            active.every((job) => job.status === "queued")
              ? "preparing"
              : active.some((job) => Boolean(job.explorerTiming))
              ? "planning"
              : "exploring"
          );
        } else {
          const activeTurn = (chat.turns ?? []).find((turn) =>
            turn.status === "queued" || turn.status === "classifying" || turn.status === "executing"
          );
          if (activeTurn) {
            setInitialPlanningActive(!chat.currentPlan);
            setWorkflowStage(
              activeTurn.status === "queued"
                ? "preparing"
                : activeTurn.status === "classifying"
                  ? "exploring"
                  : "planning"
            );
            void conversationTurn.resumeTurn(activeTurn).catch((caught) => {
              setInitialPlanningActive(false);
              setWorkflowStage("failed");
              setError(caught instanceof Error ? caught.message : "Không thể tiếp tục tác vụ.");
            });
          }
        }
      }
    } catch (caught) {
      if (!controller.signal.aborted && activeChatIdRef.current === chatId) {
        setError(
          caught instanceof Error ? caught.message : "Không thể mở chuyến đi."
        );
        setPlannerEntryResolved(true);
      }
    } finally {
      if (chatLoadControllerRef.current === controller) {
        chatLoadControllerRef.current = null;
      }
    }
  }

  function syncPlannerChatUrl(chatId: string | null) {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (chatId) url.searchParams.set("chatId", chatId);
    else url.searchParams.delete("chatId");
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  }

  async function handleDeleteTripChat(chat: TripChatSummary) {
    if (loading || deletingChatId || deletingAllChats) return;
    if (
      !window.confirm(
        `Xóa toàn bộ lịch sử chat “${chat.title}”? Hành động này không thể hoàn tác.`
      )
    ) {
      return;
    }

    setDeletingChatId(chat.id);
    setError("");
    try {
      await deleteTripChat(chat.id);
      setTripChats((current) => current.filter((item) => item.id !== chat.id));
      if (chat.id === activeChatId) {
        resetWorkflow();
      }
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Không thể xóa lịch sử chat."
      );
    } finally {
      setDeletingChatId(null);
    }
  }

  async function handleDeleteAllTripChats() {
    if (loading || deletingChatId || deletingAllChats || !tripChats.length) return;
    if (
      !window.confirm(
        `Xóa tất cả ${tripChats.length} cuộc trò chuyện? Toàn bộ tin nhắn và lịch trình trong lịch sử sẽ bị xóa vĩnh viễn.`
      )
    ) {
      return;
    }

    setDeletingAllChats(true);
    setError("");
    try {
      await deleteAllTripChats();
      setTripChats([]);
      resetWorkflow();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Không thể xóa tất cả lịch sử chat."
      );
    } finally {
      setDeletingAllChats(false);
    }
  }

  function applyTripChat(chat: TripChat) {
    setGuidedIntakeStep("complete");
    setGuidedIntakeOpen(false);
    setGuidedIntakeAnswers(
      chat.currentTripIntent
        ? guidedAnswersFromTripIntent(chat.currentTripIntent)
        : {}
    );
    setGuidedStartDate(chat.currentTripIntent?.timing.startDate ?? "");
    setGuidedEndDate(
      defaultTripEndDate(
        chat.currentTripIntent?.timing.startDate,
        chat.currentTripIntent?.timing.endDate,
        chat.currentTripIntent?.timing.days
      )
    );
    if (chat.currentTripIntent) {
      setTravelerCounts({
        adults: chat.currentTripIntent.travelParty.adults,
        children: chat.currentTripIntent.travelParty.children,
        infants: chat.currentTripIntent.travelParty.infants,
        pets: chat.currentTripIntent.travelParty.pets,
      });
    }
    activeChatIdRef.current = chat.id;
    setActiveChatId(chat.id);
    setChatRevision(chat.revision);
    setTripIntentVersion(chat.tripIntentVersion);
    setTripIntentPlanStatus(chat.tripIntentPlanStatus);
    setPlan(chat.currentPlan);
    setExploreResult(
      chat.currentTripIntent
        ? {
            intakeId: chat.currentIntakeId ?? "",
            userId: user ? String(user.id) : null,
            explorer: {
              tripIntent: chat.currentTripIntent,
              assumptions: [],
              missingInfoQuestions: [],
              preferenceSnapshot: { version: 1, signals: [], effectiveProfile: { version: 1, explicit: [], scores: {}, observationCount: 0 } },
              candidateReviews: chat.candidateReviews,
            },
            allowFinderGapFill: true,
            allowReplaceSourcePlaces: false,
          }
        : null
    );
    const conversationMessages = visibleConversationMessages(chat);
    setMessages(
      conversationMessages.length
        ? conversationMessages
        : [
            {
              id: `welcome-${chat.id}`,
              role: "assistant",
              text: "Hãy mô tả chuyến đi này. Những tin nhắn sau sẽ tiếp tục chỉnh sửa cùng một lịch trình.",
            },
          ]
    );
    setWorkflowStage(chat.currentPlan ? "ready" : "idle");
    if (chat.currentPlan) {
      setBackgroundPlanning(false);
      setInitialPlanningActive(false);
      setActivePlanningJobs([]);
    }
    setSelectedMapPlaceKey(null);
  }

  const activeJobChatIds = useMemo(
    () =>
      new Set(
        urlJobSnapshot
          .filter(
            (job) => job.status === "queued" || job.status === "running"
          )
          .map((job) => job.chatId)
      ),
    [urlJobSnapshot]
  );
  const orderedTripChats = useMemo(
    () =>
      [...tripChats].sort(
        (left, right) =>
          Number(activeJobChatIds.has(right.id)) -
          Number(activeJobChatIds.has(left.id))
      ),
    [activeJobChatIds, tripChats]
  );

  function handleComposerKeyDown(
    event: React.KeyboardEvent<HTMLTextAreaElement>
  ) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      if (!loading && !queueingUrls && (prompt.trim() || urlInput.trim())) {
        sendPlannerEntry();
      }
    }
  }

  function applyTripChatBackgroundResult(chat: TripChat) {
    if (chat.id !== activeChatIdRef.current) return;
    setChatRevision(chat.revision);
    setTripIntentVersion(chat.tripIntentVersion);
    setTripIntentPlanStatus(chat.tripIntentPlanStatus);
    setPlan(chat.currentPlan);
    setExploreResult((current) =>
      current && chat.currentTripIntent
        ? {
            ...current,
            intakeId: chat.currentIntakeId ?? "",
            explorer: {
              ...current.explorer,
              tripIntent: chat.currentTripIntent,
              candidateReviews: chat.candidateReviews,
            },
          }
        : current
    );
    setWorkflowStage(chat.currentPlan ? "ready" : "idle");
    setTripChats((current) =>
      current.map((item) =>
        item.id === chat.id
          ? {
              id: chat.id,
              title: chat.title,
              destination: chat.destination,
              revision: chat.revision,
              hasPlan: chat.hasPlan,
              createdAt: chat.createdAt,
              updatedAt: chat.updatedAt,
            }
          : item
      )
    );
  }

  function handleConfirmCandidateResolution(
    place: UnscheduledPlace,
    matchRank: number
  ) {
    if (!activeChatId || !place.candidateId) return;
    if (candidateResolutionCandidateIdsRef.current.has(place.candidateId)) return;

    const key = `${place.candidateId}:${matchRank}`;
    candidateResolutionCandidateIdsRef.current.add(place.candidateId);
    candidateResolutionQueueRef.current.push({
      chatId: activeChatId,
      matchRank,
      place,
    });
    setCandidateResolutionProgress((current) => ({
      ...current,
      [place.candidateId as string]: { key, status: "queued" },
    }));
    setError("");
    void drainCandidateResolutionQueue(chatRevision);
  }

  async function drainCandidateResolutionQueue(initialRevision: number) {
    if (candidateResolutionRunningRef.current) return;

    candidateResolutionRunningRef.current = true;
    setMutatingItem(true);
    let expectedRevision = initialRevision;

    try {
      while (candidateResolutionQueueRef.current.length > 0) {
        const choice = candidateResolutionQueueRef.current.shift();
        if (!choice?.place.candidateId) continue;

        const candidateId = choice.place.candidateId;
        const key = `${candidateId}:${choice.matchRank}`;
        setCandidateResolutionProgress((current) => ({
          ...current,
          [candidateId]: { key, status: "resolving" },
        }));

        try {
          const updated = await confirmTripChatCandidateResolution({
            chatId: choice.chatId,
            expectedRevision,
            candidateId,
            matchRank: choice.matchRank,
          });
          expectedRevision = updated.revision;
          if (activeChatIdRef.current === choice.chatId) {
            applyTripChat(updated);
          }
        } catch (caught) {
          if (activeChatIdRef.current === choice.chatId) {
            setError(
              caught instanceof Error
                ? caught.message
                : "Không thể xác nhận địa điểm này."
            );
          }
        } finally {
          candidateResolutionCandidateIdsRef.current.delete(candidateId);
          setCandidateResolutionProgress((current) => {
            const next = { ...current };
            delete next[candidateId];
            return next;
          });
        }
      }
    } finally {
      candidateResolutionRunningRef.current = false;
      setMutatingItem(false);
    }
  }

  async function handleDismissUnscheduledPlace(place: UnscheduledPlace) {
    if (!activeChatId || mutatingItem) return;
    if (
      !confirm(
        `Không thêm “${itineraryDisplayName(place.name)}” vào kế hoạch?`
      )
    ) {
      return;
    }

    setMutatingItem(true);
    setError("");
    try {
      const updated = await removeTripChatUnscheduledPlace({
        chatId: activeChatId,
        expectedRevision: chatRevision,
        place,
      });
      applyTripChat(updated);
      showPlannerToast("Đã bỏ địa điểm khỏi kế hoạch");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Không thể bỏ địa điểm khỏi kế hoạch."
      );
    } finally {
      setMutatingItem(false);
    }
  }

  function handleUrlPaste(event: React.ClipboardEvent<HTMLTextAreaElement>) {
    const pastedText = event.clipboardData.getData("text").trim();
    if (!parseUrlOnlyInput(pastedText).ok) return;

    event.preventDefault();
    const field = event.currentTarget;
    const selectionStart = field.selectionStart;
    const selectionEnd = field.selectionEnd;
    const nextValue = `${urlInput.slice(
      0,
      selectionStart
    )}${pastedText}\n${urlInput.slice(selectionEnd)}`;
    const nextCaretPosition = selectionStart + pastedText.length + 1;

    setUrlInput(nextValue);
    if (urlInputError) setUrlInputError("");
    window.requestAnimationFrame(() => {
      urlInputRef.current?.setSelectionRange(
        nextCaretPosition,
        nextCaretPosition
      );
    });
  }

  function buildEntryRequest(): string | null {
    const tripRequest = prompt.trim();
    if (!urlInput.trim()) return tripRequest || null;

    const result = parseUrlOnlyInput(urlInput);
    if (!result.ok) {
      setUrlInputError(result.message);
      return null;
    }

    setUrlInputError("");
    return [tripRequest, ...result.urls].filter(Boolean).join("\n");
  }

  function sendPlannerEntry() {
    if (submittingEntryRef.current || loading || queueingUrls) return;
    const request = buildEntryRequest();
    if (!request) {
      setError("Nhập yêu cầu hoặc dán URL trước khi gửi.");
      return;
    }

    submittingEntryRef.current = true;
    setPrompt("");
    setUrlInput("");
    void sendMessage(request).finally(() => {
      submittingEntryRef.current = false;
    });
  }

  function submitPlannerEntry(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    sendPlannerEntry();
  }

  function renderEntryTopbar() {
    return (
      <div className="plannerEntryTopbar">
        <header className="panelHeading itineraryHeading">
          <span className="planHeaderIcon" aria-hidden="true">
            <Image
              alt=""
              height={54}
              src="/images/penguin-plan.png"
              width={54}
            />
          </span>
          <div className="itineraryHeadingCopy">
            <strong>Kế hoạch chi tiết</strong>
            <div className="plannerIntakePeekaboo itineraryIntakePeekaboo">
              <small>
                <nav aria-label="Thông tin chuyến đi" className="plannerIntakeNav">
                  {(
                    [
                      ["destination", "Điểm đến"],
                      ["dates", "Thời gian"],
                      ["travelers", "Nhóm đi"],
                      ["budget", "Ngân sách"],
                      ["note", "Lưu ý"],
                    ] as const
                  ).map(([step, label]) => {
                    const value = guidedIntakeAnswers[step];
                    return (
                      <button
                        aria-label={value ? `${label}: ${value}` : label}
                        aria-current={
                          guidedIntakeOpen && guidedIntakeStep === step
                            ? "step"
                            : undefined
                        }
                        className={value ? "is-filled" : ""}
                        disabled={backgroundPlanning || loading || savingTripIntent}
                        key={step}
                        onClick={() => openGuidedStep(step)}
                        title={value || label}
                        type="button"
                      >
                        <span className="plannerIntakeCopy">{label}</span>
                      </button>
                    );
                  })}
                </nav>
              </small>
            </div>
          </div>
          <span aria-hidden="true" className="plannerIntakePenguin">
            <PenguinMascot size={36} variant="intakePeek" />
          </span>
          {user ? (
            <HistoryMenuButton
              className="plannerHistoryMenu--intake"
              onClick={() => setHistoryCollapsed(false)}
            />
          ) : null}
        </header>
      </div>
    );
  }

  return (
    <>
      <main
        className="plannerPage"
        onClickCapture={clearMapHighlightFromExternalControlClick}
      >
        {plannerToast ? (
          <div className="plannerToast" key={plannerToast.id} role="status">
            <span aria-hidden="true">✓</span>
            {plannerToast.text}
          </div>
        ) : null}
        {reorderingDay != null ? (
          <div
            aria-labelledby="route-recalculation-title"
            aria-modal="true"
            autoFocus
            className="plannerInteractionLock"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            tabIndex={-1}
          >
            <div className="plannerInteractionLockCard">
              <span
                aria-hidden="true"
                className="plannerInteractionLockSpinner"
              />
              <strong id="route-recalculation-title">
                Đang cập nhật tuyến đường…
              </strong>
              <small>
                Vui lòng đợi một chút. Lịch trình sẽ mở lại ngay khi tuyến mới
                sẵn sàng.
              </small>
            </div>
          </div>
        ) : null}
        <div
          aria-busy={reorderingDay != null}
          className="plannerWorkspace pageWidth"
          inert={reorderingDay != null ? true : undefined}
        >

          <TripProjectSidebar
            activeChatId={activeChatId}
            activeJobChatIds={activeJobChatIds}
            deletingAllChats={deletingAllChats}
            deletingChatId={deletingChatId}
            loading={loading}
            onClose={() => setHistoryCollapsed(true)}
            onDeleteAll={() => void handleDeleteAllTripChats()}
            onDeleteChat={(chat) => void handleDeleteTripChat(chat)}
            onNewChat={() => {
              resetWorkflow();
              setHistoryCollapsed(true);
            }}
            onOpenChat={(chatId) => {
              setHistoryCollapsed(true);
              void openTripChat(chatId);
            }}
            open={Boolean(user && !historyCollapsed)}
            orderedTripChats={orderedTripChats}
            tripChats={tripChats}
          />

          {!plannerEntryResolved ? (
            <div className="routeLoading">Đang tải cuộc trò chuyện…</div>
          ) : (
            <section
              className={`plannerLayout ${
                !displayedPlan ? "is-new-chat" : ""
              } ${backgroundPlanning || loading ? "is-planning" : ""} ${
                awaitingInitialPlan ? "is-awaiting-plan" : ""
              }`}
              ref={plannerLayoutRef}
              style={
                {
                  "--itinerary-panel-width": `${itineraryWidthPercent}%`,
                } as CSSProperties
              }
            >
              {!displayedPlan ? renderEntryTopbar() : null}

              <GuidedIntakeDialog
                counts={travelerCounts}
                draft={guidedDraft}
                endDate={guidedEndDate}
                onClose={() => setGuidedIntakeOpen(false)}
                onDraftChange={setGuidedDraft}
                onEndDateChange={setGuidedEndDate}
                onStartDateChange={(value) => {
                  setGuidedStartDate(value);
                  setGuidedEndDate(
                    value
                      ? addTripDays(
                          value,
                          exploreResult?.explorer.tripIntent.timing.days ?? 3
                        )
                      : ""
                  );
                }}
                onSubmitAnswer={(answer) => void submitGuidedAnswer(answer)}
                onSubmitDates={submitGuidedDates}
                onSubmitTravelers={() =>
                  void submitGuidedAnswer(travelerAnswer(travelerCounts))
                }
                onTravelerCountChange={updateTravelerCount}
                open={guidedIntakeOpen}
                saving={savingTripIntent}
                startDate={guidedStartDate}
                step={guidedIntakeStep as Exclude<GuidedIntakeStep, "complete">}
              />

              <aside
                aria-busy={awaitingInitialPlan}
                aria-label="Trợ lý lập kế hoạch TravelPlanner"
                className={`plannerChat panel ${
                  chatCollapsed ? "is-collapsed" : ""
                } ${
                  displayedPlan || awaitingInitialPlan
                    ? "plannerChat--compact"
                    : ""
                }`}
                ref={plannerChatRef}
                style={
                  floatingChatRect
                    ? ({
                        "--floating-chat-x": `${floatingChatRect.x}px`,
                        "--floating-chat-y": `${floatingChatRect.y}px`,
                        "--floating-chat-width": `${floatingChatRect.width}px`,
                        "--floating-chat-height": `${floatingChatRect.height}px`,
                      } as CSSProperties)
                    : undefined
                }
              >
                <PlannerChatHeader
                  collapsed={chatCollapsed}
                  contentId="planner-chat-content"
                  loading={awaitingInitialPlan}
                  moveHandleProps={{
                    onKeyDown: moveChatWithKeyboard,
                    onPointerCancel: endChatPointerInteraction,
                    onPointerDown: (event) =>
                      beginChatPointerInteraction(event, "move"),
                    onPointerMove: updateChatPointerInteraction,
                    onPointerUp: endChatPointerInteraction,
                  }}
                  onToggle={toggleChatCollapsed}
                  status={
                    awaitingInitialPlan
                      ? workflowStage === "classifying"
                        ? "Đang hiểu yêu cầu của bạn"
                        : "Đang chạy nền · có thể chuyển tab"
                      : workflowStage === "ready"
                        ? "Lịch trình sẵn sàng để chỉnh sửa"
                        : workflowStage === "failed"
                          ? "Cần bạn kiểm tra và thử lại"
                          : "Cùng bạn xây dựng chuyến đi"
                  }
                />
                <div className="plannerChatContent" id="planner-chat-content">
                  <PlannerChatMessages
                    messages={messages}
                    ref={messageListRef}
                  />
                  {awaitingInitialPlan ? (
                    <div
                      aria-atomic="true"
                      aria-live="polite"
                      className="plannerInlineProcessing"
                      role="status"
                    >
                      Đang suy nghĩ
                    </div>
                  ) : null}
                  {error ? <p className="formError">{error}</p> : null}
                  <PlannerChatComposer
                    disabled={loading}
                    onPromptChange={setPrompt}
                    onPromptKeyDown={handleComposerKeyDown}
                    onSubmit={submitPlannerEntry}
                    onUrlChange={(value) => {
                      setUrlInput(value);
                      if (urlInputError) setUrlInputError("");
                    }}
                    onUrlPaste={handleUrlPaste}
                    prompt={prompt}
                    promptPlaceholder={
                      displayedPlan
                        ? "Yêu cầu chỉnh sửa lịch trình…"
                        : "Mô tả chuyến đi bạn mong muốn…"
                    }
                    promptRef={composerTextareaRef}
                    queueingUrls={queueingUrls}
                    urlError={urlInputError}
                    urlInput={urlInput}
                    urlRef={urlInputRef}
                  />
                </div>
                {!chatCollapsed ? (
                  <div
                    aria-label="Các cạnh đổi kích thước cửa sổ chat"
                    className="plannerChatResizeHandles"
                    role="group"
                  >
                    {CHAT_RESIZE_HANDLES.map(({ direction, label }) => (
                      <button
                        aria-label={`${label}; dùng phím mũi tên hoặc kéo`}
                        className={`plannerChatResizeHandle plannerChatResizeHandle--${direction}`}
                        key={direction}
                        onKeyDown={(event) =>
                          resizeChatWithKeyboard(event, direction)
                        }
                        onPointerCancel={endChatPointerInteraction}
                        onPointerDown={(event) =>
                          beginChatPointerInteraction(
                            event,
                            "resize",
                            direction
                          )
                        }
                        onPointerMove={updateChatPointerInteraction}
                        onPointerUp={endChatPointerInteraction}
                        title={`${label} chat`}
                        type="button"
                      >
                        {direction === "se" ? (
                          <svg aria-hidden="true" viewBox="0 0 18 18">
                            <path d="M7 15h8V7M11 15h4v-4" />
                          </svg>
                        ) : null}
                      </button>
                    ))}
                  </div>
                ) : null}
              </aside>

              {!displayedPlan ? (
                <PlannerDiscoveryPanel
                  planning={backgroundPlanning || loading}
                />
              ) : null}

              <section
                className={`itinerary panel mobileItinerarySheet ${
                  mobileItineraryExpanded ? "is-expanded" : "is-peek"
                }`}
              >
                <button
                  aria-expanded={mobileItineraryExpanded}
                  aria-label={
                    mobileItineraryExpanded
                      ? "Thu gọn lịch trình để xem bản đồ"
                      : "Mở lịch trình chi tiết"
                  }
                  className="mobileItineraryHandle"
                  onClick={() => {
                    if (suppressMobileItineraryClickRef.current) {
                      suppressMobileItineraryClickRef.current = false;
                      return;
                    }
                    setMobileItineraryExpanded((expanded) => !expanded);
                  }}
                  onPointerCancel={cancelMobileItineraryDrag}
                  onPointerDown={beginMobileItineraryDrag}
                  onPointerUp={endMobileItineraryDrag}
                  type="button"
                >
                  <span aria-hidden="true" />
                  <strong>
                    {mobileItineraryExpanded ? "Vuốt xuống để xem bản đồ" : "Vuốt lên xem lịch trình"}
                  </strong>
                  <svg aria-hidden="true" viewBox="0 0 24 24">
                    <path d={mobileItineraryExpanded ? "m6 9 6 6 6-6" : "m6 15 6-6 6 6"} />
                  </svg>
                </button>
                <header className="panelHeading itineraryHeading">
                  <span className="planHeaderIcon" aria-hidden="true">
                    <Image
                      alt=""
                      height={52}
                      src="/images/penguin-plan.png"
                      width={52}
                    />
                  </span>
                  <div className="itineraryHeadingCopy">
                    <div className="itineraryHeadingTitle">
                      <strong>Kế hoạch chi tiết</strong>
                    </div>
                    <div className="plannerIntakePeekaboo itineraryIntakePeekaboo">
                      <small>
                        <nav aria-label="Thông tin chuyến đi" className="plannerIntakeNav">
                          {(
                            [
                              ["destination", "Điểm đến"],
                              ["dates", "Thời gian"],
                              ["travelers", "Nhóm đi"],
                              ["budget", "Ngân sách"],
                              ["note", "Lưu ý"],
                            ] as const
                          ).map(([step, label]) => {
                            const value = guidedIntakeAnswers[step];
                            return (
                              <button
                                aria-label={value ? `${label}: ${value}` : label}
                                aria-current={
                                  guidedIntakeOpen && guidedIntakeStep === step
                                    ? "step"
                                    : undefined
                                }
                                className={value ? "is-filled" : ""}
                                disabled={backgroundPlanning || loading || savingTripIntent}
                                key={step}
                                onClick={() => openGuidedStep(step)}
                                title={value || label}
                                type="button"
                              >
                                <span className="plannerIntakeCopy">{label}</span>
                              </button>
                            );
                          })}
                        </nav>
                      </small>
                    </div>
                  </div>
                  <span aria-hidden="true" className="plannerIntakePenguin">
                    <PenguinMascot size={36} variant="intakePeek" />
                  </span>
                  {user ? (
                    <HistoryMenuButton
                      className="plannerHistoryMenu--itinerary"
                      onClick={() => setHistoryCollapsed(false)}
                    />
                  ) : null}
                </header>
                {displayedPlan ? (
                  <div className="exploreResult" ref={itineraryScrollRef}>
                    {displayedExploreResult ? (
                      <section className="tripSummaryCard">
                      <div className="tripSummaryIntro">
                        <span className="destinationPin" aria-hidden="true">
                          ⌖
                        </span>
                        <div>
                          <span className="tripSummaryLabel">
                            Điểm đến của bạn
                          </span>
                          <h3>
                            {displayedExploreResult.explorer.tripIntent.destination}
                          </h3>
                          <p>
                            {displayedExploreResult.explorer.tripIntent.preferences.travelStyle}{" "}
                            · Nhịp độ{" "}
                            {paceLabel(
                              displayedExploreResult.explorer.tripIntent.preferences.pace
                            )}
                          </p>
                        </div>
                      </div>
                      <div
                        className="tripQuickFacts"
                        aria-label="Thông tin chuyến đi"
                      >
                        <div>
                          <span>Ngày có lịch trình</span>
                          <strong>{displayedPlan.days.length} ngày</strong>
                        </div>
                        <div>
                          <span>Nhóm đi</span>
                          <strong>
                            {displayedExploreResult.explorer.tripIntent.travelParty.adults + displayedExploreResult.explorer.tripIntent.travelParty.children + displayedExploreResult.explorer.tripIntent.travelParty.infants}{" "}
                            người
                          </strong>
                        </div>
                        <div>
                          <span>Mức ngân sách</span>
                          <strong>
                            {budgetLevelLabel(
                              displayedExploreResult.explorer.tripIntent.budget
                                .level
                            )}
                          </strong>
                        </div>
                      </div>
                      <div className="budgetSummary">
                        <span className="budgetIcon" aria-hidden="true">
                          ₫
                        </span>
                        <div>
                          <span>Mức chi dự kiến</span>
                          <strong>
                            {formatBudget(displayedExploreResult.explorer)}
                          </strong>
                        </div>
                      </div>
                      {displayedExploreResult.explorer.tripIntent.preferences.interests
                        .length ? (
                        <div className="interestGroup">
                          <span className="sectionMicroTitle">
                            Bạn muốn trải nghiệm
                          </span>
                          <div className="tagRow">
                            {displayedExploreResult.explorer.tripIntent.preferences.interests.map(
                              (interest) => (
                                <span key={interest}>{interest}</span>
                              )
                            )}
                          </div>
                        </div>
                      ) : null}
                      </section>
                    ) : null}

                    <section className="tripPlanSection">
                      <div
                        aria-label="Chọn chế độ xem lịch trình"
                        className="dayTabList"
                        onKeyDown={handleDayTabKeyDown}
                        role="tablist"
                      >
                        <button
                          aria-controls="plan-days-panel"
                          aria-selected={activePlanDay == null}
                          className={activePlanDay == null ? "active" : ""}
                          id="plan-day-tab-all"
                          onClick={() => {
                            setActivePlanDay(null);
                            setSelectedMapPlaceKey(null);
                            clearDayDirections();
                          }}
                          role="tab"
                          style={{ "--day-color": "#365f5a" } as CSSProperties}
                          tabIndex={activePlanDay == null ? 0 : -1}
                          type="button"
                        >
                          <span className="dayTabLabel">Tất cả</span>
                          <small>Toàn lịch trình</small>
                        </button>
                        {displayedPlan.days.map((day) => {
                          const dateKey = dateKeyForTripDay(
                            displayedStartDate,
                            day.day
                          );
                          const color = planDayColors.get(dateKey) ?? "#365f5a";
                          const isActive = day.day === activePlanDay;
                          const shortDate = shortDateLabelForTripDay(
                            displayedStartDate,
                            day.day
                          );
                          return (
                            <button
                              aria-controls="plan-days-panel"
                              aria-selected={isActive}
                              className={isActive ? "active" : ""}
                              id={`plan-day-tab-${day.day}`}
                              key={day.day}
                              onClick={() => {
                                setActivePlanDay(day.day);
                                setSelectedMapPlaceKey(null);
                                clearDayDirections();
                              }}
                              role="tab"
                              style={{ "--day-color": color } as CSSProperties}
                              tabIndex={isActive ? 0 : -1}
                              type="button"
                            >
                              <span className="dayTabLabel">
                                <span
                                  className="dayTabDot"
                                  aria-hidden="true"
                                />
                                Ngày {day.day}
                              </span>
                              {shortDate ? <small>{shortDate}</small> : null}
                            </button>
                          );
                        })}
                        <button
                          aria-controls="plan-days-panel"
                          aria-selected={
                            activePlanDay === UNSCHEDULED_PLAN_DAY
                          }
                          className={
                            activePlanDay === UNSCHEDULED_PLAN_DAY
                              ? "active dayTabUnscheduled"
                              : "dayTabUnscheduled"
                          }
                          id="plan-day-tab-unscheduled"
                          onClick={() => {
                            setActivePlanDay(UNSCHEDULED_PLAN_DAY);
                            setSelectedMapPlaceKey(null);
                            clearDayDirections();
                          }}
                          role="tab"
                          style={{ "--day-color": "#b56a3c" } as CSSProperties}
                          tabIndex={
                            activePlanDay === UNSCHEDULED_PLAN_DAY ? 0 : -1
                          }
                          type="button"
                        >
                          <span className="dayTabLabel">
                            <span className="dayTabDot" aria-hidden="true" />
                            Chưa xếp
                          </span>
                          {(displayedPlan.unscheduledPlaces?.length ?? 0) > 0 ? (
                            <small>
                              {displayedPlan.unscheduledPlaces?.length} địa điểm
                            </small>
                          ) : null}
                        </button>
                        <button
                          aria-controls="plan-days-panel"
                          aria-selected={activePlanDay === GROUP_PLAN_DAY}
                          className={activePlanDay === GROUP_PLAN_DAY ? "active dayTabGroup" : "dayTabGroup"}
                          id="plan-day-tab-group"
                          onClick={() => {
                            setActivePlanDay(GROUP_PLAN_DAY);
                            setSelectedMapPlaceKey(null);
                            clearDayDirections();
                          }}
                          role="tab"
                          style={{ "--day-color": "#7252a3" } as CSSProperties}
                          tabIndex={activePlanDay === GROUP_PLAN_DAY ? 0 : -1}
                          type="button"
                        >
                          <span className="dayTabLabel"><span className="dayTabDot" aria-hidden="true" />Nhóm</span>
                          <small>{3} công cụ</small>
                        </button>
                      </div>
                      <div className="itinerarySearch">
                        <label className="srOnly" htmlFor="itinerary-place-search">
                          Tìm địa điểm trong lịch trình hiện tại
                        </label>
                        <div className="itinerarySearchField">
                          <svg aria-hidden="true" viewBox="0 0 24 24">
                            <circle cx="11" cy="11" r="7" />
                            <path d="m16.5 16.5 4 4" />
                          </svg>
                          <input
                            aria-autocomplete="list"
                            aria-controls="itinerary-search-results"
                            aria-expanded={Boolean(itinerarySearchQuery.trim())}
                            autoComplete="off"
                            id="itinerary-place-search"
                            onChange={(event) =>
                              setItinerarySearchQuery(event.target.value)
                            }
                            placeholder="Tìm địa điểm trong lịch trình này"
                            role="combobox"
                            type="search"
                            value={itinerarySearchQuery}
                          />
                          {itinerarySearchQuery ? (
                            <button
                              aria-label="Xóa nội dung tìm kiếm"
                              onClick={() => setItinerarySearchQuery("")}
                              type="button"
                            >
                              ×
                            </button>
                          ) : null}
                        </div>
                        {itinerarySearchQuery.trim() ? (
                          <div
                            aria-label="Địa điểm trong lịch trình"
                            className="itinerarySearchResults"
                            id="itinerary-search-results"
                            role="listbox"
                          >
                            {itinerarySearchResults.length ? (
                              itinerarySearchResults.map((result) => (
                                <button
                                  aria-selected="false"
                                  key={result.key}
                                  onClick={() =>
                                    selectItinerarySearchResult(result)
                                  }
                                  role="option"
                                  type="button"
                                >
                                  <span>
                                    <strong>{result.item.name}</strong>
                                    <small>
                                      {result.item.address ||
                                        result.item.placeType ||
                                        "Địa điểm trong lịch trình"}
                                    </small>
                                  </span>
                                  <b>Ngày {result.day}</b>
                                </button>
                              ))
                            ) : (
                              <p role="status">
                                Không có địa điểm phù hợp trong lịch trình này.
                              </p>
                            )}
                          </div>
                        ) : null}
                      </div>
                      <button
                        aria-expanded={destinationDetailsOpen}
                        aria-haspopup="dialog"
                        className="destinationPreviewCard"
                        onClick={() => setDestinationDetailsOpen(true)}
                        type="button"
                      >
                        <strong>{displayedPlan.destination}</strong>
                        {destinationSummary ? (
                          <span className="destinationPreviewSummary">
                            {destinationSummary}
                          </span>
                        ) : null}
                        <span className="destinationPreviewAction">
                          Lịch sử · Điều cần biết
                          <svg aria-hidden="true" viewBox="0 0 24 24">
                            <path d="m9 6 6 6-6 6" />
                          </svg>
                        </span>
                      </button>
                      <div
                        aria-labelledby={
                          activePlanDay == null
                            ? "plan-day-tab-all"
                            : activePlanDay === UNSCHEDULED_PLAN_DAY
                              ? "plan-day-tab-unscheduled"
                              : activePlanDay === GROUP_PLAN_DAY
                                ? "plan-day-tab-group"
                              : `plan-day-tab-${activePlanDay}`
                        }
                        className="planDayPanels"
                        id="plan-days-panel"
                        role="tabpanel"
                      >
                        {displayedPlanDays.map((displayedPlanDay) => (
                          <article
                            className={`explorerDayCard ${
                              selectedMapRouteKey?.startsWith(
                                `day-${displayedPlanDay.day}-`
                              ) ||
                              selectedMapRouteKey?.startsWith(
                                `day-directions-${displayedPlanDay.day}-`
                              )
                                ? "has-map-route-selection"
                                : ""
                            }`}
                            key={displayedPlanDay.day}
                            style={
                              {
                                "--day-color":
                                  planDayColors.get(
                                    dateKeyForTripDay(
                                      displayedStartDate,
                                      displayedPlanDay.day
                                    )
                                  ) ?? "#365f5a",
                              } as CSSProperties
                            }
                          >
                            {activePlanDay == null ? (
                              <header className="dayCardHeading daySectionHeading">
                                <strong>Ngày {displayedPlanDay.day}</strong>
                              </header>
                            ) : null}
                            {directionsActive &&
                            activePlanDay === displayedPlanDay.day &&
                            dayDirectionLegs.length > 0 ? (
                              <div
                                aria-label={`Tuyến đến ${
                                  dayDirectionLegs[0]?.toPlace ??
                                  activeNavigationDestination?.name ??
                                  "địa điểm đã chọn"
                                }`}
                                className="dayNavigationChoices dayNavigationChoices--firstLeg"
                              >
                                {dayDirectionLegs
                                  .slice(0, 1)
                                  .map((leg, legIndex) => {
                                    const options = transportOptionsForLeg(leg);
                                    const selected = selectedTransportOption(
                                      leg,
                                      selectedDirectionOptionKeys[legIndex]
                                    );
                                    const directionRouteKey =
                                      isDrawableTransportRoute(selected)
                                        ? directionTransportRouteMapKey(
                                            displayedPlanDay.day,
                                            legIndex,
                                            selected
                                          )
                                        : null;
                                    if (options.length <= 1) {
                                      return (
                                        <div
                                          className={`dayNavigationLeg dayNavigationLeg--routeStrip ${
                                            selectedMapRouteKey ===
                                            directionRouteKey
                                              ? "is-map-route-selected"
                                              : ""
                                          }`}
                                          data-map-route-key={
                                            directionRouteKey ?? undefined
                                          }
                                          key={`${leg.fromPlace}-${leg.toPlace}-${legIndex}`}
                                        >
                                          <button
                                            className="dayNavigationLegButton dayNavigationLegButton--routeStrip"
                                            disabled={!directionRouteKey}
                                            onClick={
                                              directionRouteKey
                                                ? () =>
                                                    selectRouteFromItinerary(
                                                      directionRouteKey
                                                    )
                                                : undefined
                                            }
                                            type="button"
                                          >
                                            <span
                                              className="itineraryRouteIcon"
                                              aria-hidden="true"
                                            >
                                              <TransportModeIcon
                                                mode={selected.mode}
                                              />
                                            </span>
                                            <span className="dayNavigationLegCopy">
                                              <small>
                                                {formatDuration(
                                                  selected.estimatedDurationMinutes
                                                )}
                                                {" · "}
                                                {formatDistance(
                                                  selected.distanceMeters
                                                )}
                                              </small>
                                            </span>
                                          </button>
                                          {directionRouteKey ? (
                                            <button
                                              aria-label={
                                                selectedMapRouteKey ===
                                                directionRouteKey
                                                  ? `Huỷ làm nổi bật tuyến từ ${leg.fromPlace} đến ${leg.toPlace}`
                                                  : `Làm nổi bật tuyến từ ${leg.fromPlace} đến ${leg.toPlace} trên bản đồ`
                                              }
                                              aria-pressed={
                                                selectedMapRouteKey ===
                                                directionRouteKey
                                              }
                                              className="itineraryRouteMapButton"
                                              onClick={(event) =>
                                                handleItineraryRouteHighlight(
                                                  event,
                                                  directionRouteKey
                                                )
                                              }
                                              title={
                                                selectedMapRouteKey ===
                                                directionRouteKey
                                                  ? "Huỷ highlight"
                                                  : "Highlight trên bản đồ"
                                              }
                                              type="button"
                                            >
                                              <span aria-hidden="true">
                                                <MapPinIcon />
                                              </span>
                                              <span>
                                                {selectedMapRouteKey ===
                                                directionRouteKey
                                                  ? "Huỷ"
                                                  : "Route"}
                                              </span>
                                            </button>
                                          ) : null}
                                        </div>
                                      );
                                    }
                                    return (
                                      <details
                                        className={`dayNavigationLeg dayNavigationLeg--routeStrip ${
                                          selectedMapRouteKey ===
                                          directionRouteKey
                                            ? "is-map-route-selected"
                                            : ""
                                        }`}
                                        data-map-route-key={
                                          directionRouteKey ?? undefined
                                        }
                                        key={`${leg.fromPlace}-${leg.toPlace}-${legIndex}`}
                                      >
                                        <summary className="dayNavigationLegSummary--routeStrip">
                                          <span
                                            className="itineraryRouteIcon"
                                            aria-hidden="true"
                                          >
                                            <TransportModeIcon
                                              mode={selected.mode}
                                            />
                                          </span>
                                          <span className="dayNavigationLegCopy">
                                            <small>
                                              {formatDuration(
                                                selected.estimatedDurationMinutes
                                              )}
                                              {" · "}
                                              {formatDistance(
                                                selected.distanceMeters
                                              )}
                                            </small>
                                          </span>
                                          <ChevronDownIcon />
                                        </summary>
                                        {directionRouteKey ? (
                                          <button
                                            aria-label={
                                              selectedMapRouteKey ===
                                              directionRouteKey
                                                ? `Huỷ làm nổi bật tuyến từ ${leg.fromPlace} đến ${leg.toPlace}`
                                                : `Làm nổi bật tuyến từ ${leg.fromPlace} đến ${leg.toPlace} trên bản đồ`
                                            }
                                            aria-pressed={
                                              selectedMapRouteKey ===
                                              directionRouteKey
                                            }
                                            className="itineraryRouteMapButton"
                                            onClick={(event) =>
                                              handleItineraryRouteHighlight(
                                                event,
                                                directionRouteKey
                                              )
                                            }
                                            title={
                                              selectedMapRouteKey ===
                                              directionRouteKey
                                                ? "Huỷ highlight"
                                                : "Highlight trên bản đồ"
                                            }
                                            type="button"
                                          >
                                            <span aria-hidden="true">
                                              <MapPinIcon />
                                            </span>
                                            <span>
                                              {selectedMapRouteKey ===
                                              directionRouteKey
                                                ? "Huỷ"
                                                : "Route"}
                                            </span>
                                          </button>
                                        ) : null}
                                        <div className="itineraryRouteAlternatives">
                                          {options.map(
                                            (option, optionIndex) => {
                                              const matchingPlanLegIndex =
                                                displayedPlanDay.transportLegs.findIndex(
                                                  (planLeg) =>
                                                    transportLegsMatch(
                                                      planLeg,
                                                      leg
                                                    )
                                                );
                                              const matchingPlanLegKey =
                                                matchingPlanLegIndex >= 0
                                                  ? planLegSelectionKey(
                                                      displayedPlanDay.day,
                                                      matchingPlanLegIndex
                                                    )
                                                  : null;
                                              return (
                                                <TransportOptionCard
                                                  key={`${option.mode}-${option.source}-${optionIndex}`}
                                                  onSelect={() =>
                                                    void chooseDirectionOption(
                                                      legIndex,
                                                      option
                                                    )
                                                  }
                                                  option={option}
                                                  primary={optionIndex === 0}
                                                  saving={
                                                    matchingPlanLegKey !=
                                                      null &&
                                                    savingTransportOptionKey ===
                                                      matchingPlanLegKey
                                                  }
                                                  selected={
                                                    transportOptionSelectionKey(
                                                      selected
                                                    ) ===
                                                    transportOptionSelectionKey(
                                                      option
                                                    )
                                                  }
                                                />
                                              );
                                            }
                                          )}
                                        </div>
                                      </details>
                                    );
                                  })}
                              </div>
                            ) : null}
                            <div className="itineraryStops">
                              {reorderingDay === displayedPlanDay.day ? (
                                <p
                                  className="itineraryReorderStatus"
                                  role="status"
                                >
                                  Đang lưu thứ tự và cập nhật tuyến đường…
                                </p>
                              ) : null}
                              {displayedPlanDay.items.map((item, itemIndex) => {
                                const displayNotes = formatPlanNote(item.notes);
                                const notePresentation =
                                  planItemNotePresentation(item);
                                const sourceNotes = notePresentation.sourceNotes;
                                const personalNotes =
                                  notePresentation.personalText;
                                const activityNoteCount =
                                  sourceNotes.length + (personalNotes ? 1 : 0);
                                 const notePanelId = `activity-note-${displayedPlanDay.day}-${itemIndex}`;
                                 const quickActionKey = `${displayedPlanDay.day}:${item.itemId ?? itemIndex}`;
                                const displayItemName = itineraryDisplayName(
                                  item.name
                                );
                                const itinerarySearchKey =
                                  itinerarySearchResultKey(
                                    displayedPlanDay.day,
                                    itemIndex,
                                    item.itemId
                                  );
                                const isNoteEditorOpen = Boolean(
                                  noteEditor &&
                                    noteEditor.day === displayedPlanDay.day &&
                                    noteEditor.itemId ===
                                      (item.itemId ?? null) &&
                                    noteEditor.itemName === item.name
                                );
                                const mapKey = hasPlanItemCoordinates(item)
                                  ? planItemMapKey({
                                      day: displayedPlanDay.day,
                                      itemId: item.itemId,
                                      itemIndex,
                                      name: item.name,
                                    })
                                  : null;
                                const mapOrder = mapKey
                                  ? mapOrderByPlaceKey.get(mapKey)
                                  : undefined;
                                const transportLeg = transportLegAfterItem(
                                  displayedPlanDay,
                                  item,
                                  itemIndex
                                );
                                const transportLegIndex = transportLeg
                                  ? displayedPlanDay.transportLegs.indexOf(
                                      transportLeg
                                    )
                                  : -1;
                                const selectedTransportLeg =
                                  transportLeg && transportLegIndex >= 0
                                    ? selectedTransportOption(
                                        transportLeg,
                                        selectedPlanLegOptionKeys[
                                          planLegSelectionKey(
                                            displayedPlanDay.day,
                                            transportLegIndex
                                          )
                                        ]
                                      )
                                    : null;
                                const directionLegIndex = transportLeg
                                  ? dayDirectionLegs.findIndex((leg) =>
                                      transportLegsMatch(leg, transportLeg)
                                    )
                                  : -1;
                                const selectedDirectionLeg =
                                  directionLegIndex >= 0
                                    ? selectedTransportOption(
                                        dayDirectionLegs[directionLegIndex],
                                        selectedDirectionOptionKeys[
                                          directionLegIndex
                                        ]
                                      )
                                    : null;
                                const routeMapKey =
                                  selectedDirectionLeg &&
                                  directionLegIndex >= 0 &&
                                  activePlanDay === displayedPlanDay.day &&
                                  directionsActive &&
                                  isDrawableTransportRoute(selectedDirectionLeg)
                                    ? directionTransportRouteMapKey(
                                        displayedPlanDay.day,
                                        directionLegIndex,
                                        selectedDirectionLeg
                                      )
                                    : selectedTransportLeg &&
                                      transportLegIndex >= 0 &&
                                      isDrawableTransportRoute(
                                        selectedTransportLeg
                                      )
                                    ? planTransportRouteMapKey(
                                        displayedPlanDay.day,
                                        transportLegIndex,
                                        selectedTransportLeg
                                      )
                                    : null;
                                const transportLegOptions = transportLeg
                                  ? transportOptionsForLeg(transportLeg)
                                  : [];
                                const transportOptionsPanelKey =
                                  transportLegIndex >= 0
                                    ? planLegSelectionKey(
                                        displayedPlanDay.day,
                                        transportLegIndex
                                      )
                                    : `${displayedPlanDay.day}:${itemIndex}`;
                                const transportOptionsPanelId = `transport-options-${displayedPlanDay.day}-${itemIndex}`;
                                const transportOptionsExpanded = Boolean(
                                  expandedTransportOptionKeys[
                                    transportOptionsPanelKey
                                  ]
                                );
                                const timelineCategory =
                                  item.timelineCategory ?? "activity";
                                const displayedTimeWindow =
                                  formatItineraryTimeWindow(item.timeWindow);
                                const isNonActivity =
                                  timelineCategory === "break" ||
                                  item.placeType === "break" ||
                                  item.placeType === "free_time";
                                const isFoodStop =
                                  timelineCategory === "food" ||
                                  [item.placeType, ...(item.tags ?? [])].some(
                                    (value) => {
                                      const category =
                                        categoryFromPlaceType(value);
                                      return category === "food";
                                    }
                                  );
                                const sourceLabel = itinerarySourceLabel(
                                  item.sourceRefs ?? [],
                                  item.sourceProvider,
                                  item.source
                                );
                                const canReorder = Boolean(
                                  item.itemId && activeChatId && !mutatingItem
                                );
                                const placeImageUrls = (item.imageUrls ?? [])
                                  .filter(isDisplayableImageUrl)
                                  .map((url) => url.trim());
                                const placeImageUrl =
                                  placeImageUrls[0] ?? null;
                                const itineraryImageUrl =
                                  placeImageUrl ?? ITINERARY_NO_IMAGE_SRC;
                                const isDragging =
                                  draggedItemKey?.itemId === item.itemId;
                                const isDragTarget =
                                  dragOverItemId === item.itemId && !isDragging;
                                const itemDragHandle = null;
                                const itemNoteAction =
                                  activityNoteCount ||
                                  (item.itemId && activeChatId) ? (
                                    <button
                                      aria-controls={notePanelId}
                                      aria-expanded={isNoteEditorOpen}
                                      aria-label={
                                        isNoteEditorOpen
                                          ? `Đóng ghi chú cho ${displayItemName}`
                                          : activityNoteCount
                                          ? `Mở ${activityNoteCount} mục ghi chú cho ${displayItemName}`
                                          : `Thêm ghi chú cho ${displayItemName}`
                                      }
                                      className="itineraryActionButton itineraryNoteActionButton"
                                      onClick={(event) => {
                                        event.stopPropagation();
                                        setOpenQuickActionKey(null);
                                        setNoteEditor(
                                          isNoteEditorOpen
                                            ? null
                                            : {
                                                day: displayedPlanDay.day,
                                                itemId: item.itemId ?? null,
                                                itemName: item.name,
                                                sourceNotes,
                                                personalNotes:
                                                  personalNotes ?? "",
                                              }
                                        );
                                      }}
                                      title={
                                        activityNoteCount
                                          ? "Ghi chú hoạt động"
                                          : "Thêm ghi chú"
                                      }
                                      type="button"
                                    >
                                      <svg
                                        aria-hidden="true"
                                        className="itineraryNoteActionIcon"
                                        viewBox="0 0 24 24"
                                      >
                                        <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z" />
                                        <path d="M14 3v6h6M8 13h8M8 17h5" />
                                      </svg>
                                      <span className="itineraryNoteActionLabel">
                                        Ghi chú
                                      </span>
                                      {activityNoteCount ? (
                                        <span
                                          className="activityNotesButtonCount"
                                        >
                                          {activityNoteCount}
                                        </span>
                                      ) : null}
                                    </button>
                                  ) : null;
                                const itemMutationActions = null;
                                const itemInfoActions = null;
                                const itemManageActions =
                                  itemMutationActions ? (
                                    <div className="itineraryActions itineraryActions--rail itineraryActions--railManage">
                                      {itemMutationActions}
                                    </div>
                                  ) : null;
                                const itemSideRail =
                                  itemInfoActions || itemManageActions ? (
                                    <div className="itineraryPlaceDragRail">
                                      {itemInfoActions}
                                      {itemManageActions}
                                    </div>
                                  ) : null;
                                const itemNotePanel =
                                  isNoteEditorOpen && noteEditor ? (
                                    <form
                                      className="activityNotesInlinePanel"
                                      id={notePanelId}
                                      onSubmit={(event) => {
                                        if (!noteEditor.itemId) {
                                          event.preventDefault();
                                          setNoteEditor(null);
                                          return;
                                        }
                                        void handleSavePersonalNotes(
                                          event,
                                          noteEditor.day,
                                          noteEditor.itemId
                                        );
                                      }}
                                    >
                                      {noteEditor.sourceNotes.length ? (
                                        <div className="activityNotesReferences">
                                          {noteEditor.sourceNotes.map(
                                            (sourceNote, sourceNoteIndex) => (
                                              <section
                                                key={`${sourceNote.type}-${sourceNoteIndex}`}
                                              >
                                                <strong>{sourceNote.label}</strong>
                                                <p>{sourceNote.text}</p>
                                              </section>
                                            )
                                          )}
                                        </div>
                                      ) : null}
                                      <label
                                        htmlFor={`${notePanelId}-personal`}
                                      >
                                        Ghi chú của bạn
                                      </label>
                                      <textarea
                                        id={`${notePanelId}-personal`}
                                        name="personalNotes"
                                        onChange={(event) =>
                                          setNoteEditor({
                                            ...noteEditor,
                                            personalNotes: event.target.value,
                                          })
                                        }
                                        placeholder="Viết ghi chú cho hoạt động này…"
                                        readOnly={
                                          !noteEditor.itemId || !activeChatId
                                        }
                                        ref={noteTextareaRef}
                                        rows={4}
                                        value={noteEditor.personalNotes}
                                      />
                                      {noteEditor.itemId && activeChatId ? (
                                        <div className="activityNotesInlineActions">
                                          <button
                                            disabled={mutatingItem}
                                            type="submit"
                                          >
                                            {mutatingItem
                                              ? "Đang lưu…"
                                              : "Lưu ghi chú"}
                                          </button>
                                        </div>
                                      ) : null}
                                    </form>
                                  ) : null;
                                return (
                                  <Fragment
                                    key={
                                      item.itemId ??
                                      `${displayedPlanDay.day}-${itemIndex}`
                                    }
                                  >
                                    <div
                                      className={`itineraryItemDragWrapper ${
                                        isDragging ? "dragging" : ""
                                      } ${isDragTarget ? "dragTarget" : ""}`}
                                      draggable={canReorder}
                                      onDragEnd={() => {
                                        setDraggedItemKey(null);
                                        setDragOverItemId(null);
                                      }}
                                      onDragEnter={() => {
                                        if (
                                          draggedItemKey &&
                                          draggedItemKey.itemId !== item.itemId
                                        ) {
                                          setDragOverItemId(
                                            item.itemId ?? null
                                          );
                                        }
                                      }}
                                      onDragOver={(event) => {
                                        if (canReorder) event.preventDefault();
                                      }}
                                      onDragStart={(event) => {
                                        if (!item.itemId) return;
                                        event.dataTransfer.effectAllowed =
                                          "move";
                                        event.dataTransfer.setData(
                                          "text/plain",
                                          item.itemId
                                        );
                                        setDraggedItemKey({
                                          day: displayedPlanDay.day,
                                          itemId: item.itemId,
                                        });
                                      }}
                                      onDrop={(event) => {
                                        event.preventDefault();
                                        const draggedItemId =
                                          draggedItemKey?.itemId ??
                                          event.dataTransfer.getData(
                                            "text/plain"
                                          );
                                        if (
                                          draggedItemId &&
                                          draggedItemKey?.day ===
                                            displayedPlanDay.day &&
                                          draggedItemId !== item.itemId
                                        ) {
                                          const allItems =
                                            displayedPlanDay.items;
                                          const fromIndex = allItems.findIndex(
                                            (candidate) =>
                                              candidate.itemId === draggedItemId
                                          );
                                          if (fromIndex !== -1) {
                                            const reorderedItems = [
                                              ...allItems,
                                            ];
                                            const [movedItem] =
                                              reorderedItems.splice(
                                                fromIndex,
                                                1
                                              );
                                            reorderedItems.splice(
                                              itemIndex,
                                              0,
                                              movedItem
                                            );
                                            const newOrderedItemIds =
                                              reorderedItems
                                                .map(
                                                  (candidate) =>
                                                    candidate.itemId
                                                )
                                                .filter((id): id is string =>
                                                  Boolean(id)
                                                );
                                            void handleReorderItems(
                                              displayedPlanDay.day,
                                              newOrderedItemIds
                                            );
                                          }
                                        }
                                        setDraggedItemKey(null);
                                        setDragOverItemId(null);
                                      }}
                                    >
                                      {isNonActivity ? (
                                        <div className="itineraryBreakCard">
                                          <div className="itineraryBreakContent">
                                            <strong>{displayItemName}</strong>
                                            {displayNotes ? (
                                              <p>{displayNotes}</p>
                                            ) : null}
                                          </div>
                                          {canReorder ? (
                                            null
                                          ) : null}
                                        </div>
                                      ) : (
                                        <article
                                          className={`itineraryStop ${
                                            isFoodStop
                                              ? "itineraryStop--food"
                                              : "itineraryStop--activity"
                                          } ${transportLeg ? "hasRoute" : ""} ${
                                            selectedMapRoute &&
                                            (selectedMapRoute.fromPlace ===
                                              item.name ||
                                              selectedMapRoute.toPlace ===
                                                item.name)
                                              ? "is-map-route-endpoint"
                                              : ""
                                          }`}
                                        >
                                          <div
                                            aria-label={
                                              mapKey
                                                ? `Hiển thị ${displayItemName} trên bản đồ`
                                                : undefined
                                            }
                                            className={`itineraryPlaceCard itineraryPlaceCard--withImage ${
                                              itemSideRail
                                                ? "itineraryPlaceCard--withDrag"
                                                : ""
                                            } ${
                                              mapKey
                                                ? "itineraryPlaceCard--mapInteractive"
                                                : ""
                                            } ${
                                              mapKey &&
                                              selectedMapPlaceKey === mapKey
                                                ? "is-map-place-selected"
                                                : ""
                                            }`}
                                            data-map-place-key={
                                              mapKey ?? undefined
                                            }
                                            data-itinerary-search-key={
                                              itinerarySearchKey
                                            }
                                            onClick={(event) => {
                                              if (
                                                !mapKey ||
                                                isInteractiveItineraryTarget(
                                                  event.target,
                                                  event.currentTarget
                                                )
                                              )
                                                return;
                                              focusPlaceOnMap(mapKey);
                                            }}
                                            onKeyDown={(event) => {
                                              if (
                                                !mapKey ||
                                                isInteractiveItineraryTarget(
                                                  event.target,
                                                  event.currentTarget
                                                ) ||
                                                (event.key !== "Enter" &&
                                                  event.key !== " ")
                                              )
                                                return;
                                              event.preventDefault();
                                              focusPlaceOnMap(mapKey);
                                            }}
                                            role={mapKey ? "button" : undefined}
                                            tabIndex={mapKey ? 0 : undefined}
                                          >
                                            {itemSideRail}
                                            {mapOrder != null ? (
                                              <h3
                                                aria-hidden="true"
                                                className="itineraryPlaceOrder"
                                              >
                                                {mapOrder}
                                              </h3>
                                            ) : null}
                                            <div className="itineraryPlaceMedia">
                                              <div
                                                className={`itineraryPlaceImage ${
                                                  placeImageUrl
                                                    ? ""
                                                    : "itineraryPlaceImage--fallback"
                                                }`}
                                              >
                                                <img
                                                  alt={
                                                    placeImageUrl
                                                      ? `Ảnh ${displayItemName}`
                                                      : `Chưa có ảnh cho ${displayItemName}`
                                                  }
                                                  draggable={false}
                                                  loading={itemIndex < 3 ? "eager" : "lazy"}
                                                  referrerPolicy="no-referrer"
                                                  onError={(event) => {
                                                    const currentIndex = Number(
                                                      event.currentTarget.dataset.imageIndex ??
                                                        "0"
                                                    );
                                                    const nextImageUrl =
                                                      placeImageUrls[currentIndex + 1];

                                                    if (nextImageUrl) {
                                                      event.currentTarget.dataset.imageIndex =
                                                        String(currentIndex + 1);
                                                      event.currentTarget.src = nextImageUrl;
                                                      return;
                                                    }

                                                    if (
                                                      event.currentTarget.src.endsWith(
                                                        ITINERARY_NO_IMAGE_SRC
                                                      )
                                                    )
                                                      return;
                                                    event.currentTarget.src =
                                                      ITINERARY_NO_IMAGE_SRC;
                                                    event.currentTarget.alt = `Chưa có ảnh cho ${displayItemName}`;
                                                    event.currentTarget
                                                      .closest(
                                                        ".itineraryPlaceImage"
                                                      )
                                                      ?.classList.add(
                                                        "itineraryPlaceImage--fallback"
                                                      );
                                                  }}
                                                  data-image-index="0"
                                                  src={itineraryImageUrl}
                                                />
                                              </div>
                                            </div>
                                            <div className="itineraryPlaceContent">
                                              <header>
                                                <div className="itineraryPlaceMain">
                                                  <div className="itineraryPlaceTitle">
                                                    {mapKey ? (
                                                      <button
                                                        className="placeMapButton"
                                                        onClick={() =>
                                                          focusPlaceOnMap(
                                                            mapKey
                                                          )
                                                        }
                                                        aria-label={`Hiển thị ${displayItemName} trên bản đồ`}
                                                        type="button"
                                                      >
                                                        <strong>
                                                          {displayItemName}
                                                        </strong>
                                                      </button>
                                                    ) : (
                                                      <strong>
                                                        {displayItemName}
                                                      </strong>
                                                    )}
                                                  </div>
                                                  {item.rating != null ? (
                                                    <ItineraryReviewRating
                                                      onOpen={
                                                        setItineraryReviewPlace
                                                      }
                                                      place={{
                                                        placeId:
                                                          item.placeId ?? "",
                                                        name: displayItemName,
                                                        address: item.address,
                                                        rating: item.rating,
                                                        reviewCount:
                                                          item.reviewCount,
                                                        sourceLink:
                                                          item.sourceLink,
                                                      }}
                                                    />
                                                  ) : null}
                                                  {displayedTimeWindow ? (
                                                    <div
                                                      aria-label={
                                                        itineraryTimeWindowAriaLabel(
                                                          item.timeWindow
                                                        ) ?? undefined
                                                      }
                                                      className="itineraryScheduleBadge"
                                                    >
                                                      <svg
                                                        aria-hidden="true"
                                                        viewBox="0 0 24 24"
                                                      >
                                                        <circle cx="12" cy="12" r="8.5" />
                                                        <path d="M12 7.5v5l3.5 2" />
                                                      </svg>
                                                      <span>
                                                        {displayedTimeWindow}
                                                      </span>
                                                    </div>
                                                  ) : null}
                                                </div>
                                              </header>
                                                <div className="itineraryPlaceQuickActions">
                                                  {sourceLabel?.url ? (
                                                    <a
                                                      aria-label={`Mở link ${sourceLabel.text} của ${displayItemName}`}
                                                      className={`itinerarySourceIconLink itinerarySourceIconLink--${sourceLabel.provider}`}
                                                      href={sourceLabel.url}
                                                      rel="noreferrer"
                                                      target="_blank"
                                                      title={`Link ${
                                                        sourceLabel.text
                                                      }: ${
                                                        sourceLabel.displayUrl ??
                                                        sourceLabel.url
                                                      }`}
                                                    >
                                                      <SourceProviderIcon
                                                        provider={
                                                          sourceLabel.provider
                                                        }
                                                      />
                                                      <span>URL</span>
                                                    </a>
                                                  ) : null}
                                                  <span
                                                    aria-label={
                                                      isFoodStop
                                                        ? "Ăn uống"
                                                        : "Hoạt động tham quan"
                                                    }
                                                    className="itineraryTypeIcon"
                                                    role="img"
                                                    title={
                                                      isFoodStop
                                                        ? "Ăn uống"
                                                        : "Hoạt động tham quan"
                                                    }
                                                  >
                                                    {isFoodStop ? (
                                                      <svg viewBox="0 0 24 24">
                                                        <path d="M6 3v7M3.5 3v4.5A2.5 2.5 0 0 0 6 10a2.5 2.5 0 0 0 2.5-2.5V3M6 10v11" />
                                                        <path d="M15 3v18M15 3c3 1.1 4.5 3.7 4.5 7H15" />
                                                      </svg>
                                                    ) : (
                                                      <svg viewBox="0 0 24 24">
                                                        <circle cx="6" cy="6" r="2.5" />
                                                        <path d="M6 1v1M6 10v1M1 6h1M10 6h1M2.5 2.5l.7.7M8.8 8.8l.7.7M9.5 2.5l-.7.7M3.2 8.8l-.7.7" />
                                                        <path d="m2 21 6-9 4 5 2-3 8 7" />
                                                        <path d="M13 5c1-1 2-1 3 0 1-1 2-1 3 0M16 9c1-1 2-1 3 0 1-1 2-1 3 0" />
                                                      </svg>
                                                    )}
                                                  </span>
                                                  {item.itemId && activeChatId ? (
                                                    <div className="itineraryPlaceQuickActionMenu">
                                                      <button
                                                        aria-expanded={
                                                          openQuickActionKey ===
                                                          quickActionKey
                                                        }
                                                        aria-haspopup="menu"
                                                        aria-label={`Mở thao tác cho ${displayItemName}`}
                                                        className="itineraryQuickActionMenuButton"
                                                        onClick={(event) => {
                                                          event.stopPropagation();
                                                          setOpenQuickActionKey(
                                                            openQuickActionKey ===
                                                              quickActionKey
                                                              ? null
                                                              : quickActionKey
                                                          );
                                                        }}
                                                        title="Thao tác"
                                                        type="button"
                                                      >
                                                        <svg viewBox="0 0 24 24" aria-hidden="true">
                                                          <circle cx="5" cy="12" r="1.5" />
                                                          <circle cx="12" cy="12" r="1.5" />
                                                          <circle cx="19" cy="12" r="1.5" />
                                                        </svg>
                                                      </button>
                                                      {openQuickActionKey ===
                                                      quickActionKey ? (
                                                        <div
                                                          className="itineraryPlaceQuickActionPopup"
                                                          role="menu"
                                                        >
                                                          <>
                                                              <button
                                                                aria-label={`Sửa ${displayItemName}`}
                                                                className="itineraryActionButton"
                                                                onClick={() => {
                                                                  setOpenQuickActionKey(null);
                                                                  openItemEditor(
                                                                    displayedPlanDay.day,
                                                                    item
                                                                  );
                                                                }}
                                                                role="menuitem"
                                                                title="Sửa địa điểm"
                                                                type="button"
                                                              >
                                                                <svg viewBox="0 0 24 24">
                                                                  <path d="M13.5 6.5 17.5 10.5M4 20l4.2-1 10.9-10.9a2.8 2.8 0 0 0-4-4L4.2 15 4 20Z" />
                                                                </svg>
                                                              </button>
                                                              <button
                                                                aria-label={`Xóa ${displayItemName}`}
                                                                className="itineraryActionButton danger"
                                                                onClick={() => {
                                                                  setOpenQuickActionKey(null);
                                                                  handleDeleteItem(
                                                                    displayedPlanDay.day,
                                                                    item.itemId!
                                                                  );
                                                                }}
                                                                role="menuitem"
                                                                title="Xóa địa điểm"
                                                                type="button"
                                                              >
                                                                <svg viewBox="0 0 24 24">
                                                                  <path d="M4 7h16M9 7V4h6v3M18 7l-1 13H7L6 7M10 11v5M14 11v5" />
                                                                </svg>
                                                              </button>
                                                          </>
                                                        </div>
                                                      ) : null}
                                                    </div>
                                                  ) : null}
                                                </div>
                                              {itemNoteAction}
                                            </div>
                                          </div>
                                          {itemNotePanel}
                                        </article>
                                      )}
                                    </div>
                                    {transportLeg &&
                                    transportLegOptions.length > 0 ? (
                                      <div
                                        className={`itineraryRoute ${
                                          routeMapKey
                                            ? "has-map-route-link"
                                            : ""
                                        } ${
                                          routeMapKey &&
                                          selectedMapRouteKey === routeMapKey
                                            ? "is-map-route-selected"
                                            : ""
                                        }`}
                                        aria-label={`${transportModeLabel(
                                          selectedTransportLeg?.mode ??
                                            transportLeg.mode
                                        )}, từ ${transportLeg.fromPlace} đến ${
                                          transportLeg.toPlace
                                        }, khoảng ${formatDuration(
                                          selectedTransportLeg?.estimatedDurationMinutes ??
                                            transportLeg.estimatedDurationMinutes
                                        )}`}
                                        data-map-route-key={
                                          routeMapKey ?? undefined
                                        }
                                        role="group"
                                      >
                                        <div className="itineraryRouteToolbar">
                                          <div className="itineraryRouteLink">
                                            <span
                                              className="itineraryRouteIcon"
                                              aria-hidden="true"
                                            >
                                              <TransportModeIcon
                                                mode={
                                                  selectedTransportLeg?.mode ??
                                                  transportLeg.mode
                                                }
                                              />
                                            </span>
                                            <span className="itineraryRouteCopy">
                                              <small>
                                                {formatDuration(
                                                  selectedTransportLeg?.estimatedDurationMinutes ??
                                                    transportLeg.estimatedDurationMinutes
                                                )}
                                                {" · "}
                                                {formatDistance(
                                                  selectedTransportLeg?.distanceMeters ??
                                                    transportLeg.distanceMeters
                                                )}
                                              </small>
                                            </span>
                                          </div>
                                          {routeMapKey ? (
                                            <button
                                              aria-label={
                                                selectedMapRouteKey ===
                                                routeMapKey
                                                  ? `Huỷ làm nổi bật tuyến từ ${transportLeg.fromPlace} đến ${transportLeg.toPlace}`
                                                  : `Làm nổi bật tuyến từ ${transportLeg.fromPlace} đến ${transportLeg.toPlace} trên bản đồ`
                                              }
                                              aria-pressed={
                                                selectedMapRouteKey ===
                                                routeMapKey
                                              }
                                              className="itineraryRouteMapButton"
                                              onClick={(event) =>
                                                handleItineraryRouteHighlight(
                                                  event,
                                                  routeMapKey
                                                )
                                              }
                                              title={
                                                selectedMapRouteKey ===
                                                routeMapKey
                                                  ? "Huỷ highlight"
                                                  : "Highlight trên bản đồ"
                                              }
                                              type="button"
                                            >
                                              <span aria-hidden="true">
                                                <MapPinIcon />
                                              </span>
                                              <span>
                                                {selectedMapRouteKey ===
                                                routeMapKey
                                                  ? "Huỷ"
                                                  : "Route"}
                                              </span>
                                            </button>
                                          ) : null}
                                          {transportLegOptions.length > 1 ? (
                                            <button
                                              aria-controls={
                                                transportOptionsPanelId
                                              }
                                              aria-expanded={
                                                transportOptionsExpanded
                                              }
                                              className="itineraryRouteChoicesButton"
                                              onClick={() =>
                                                setExpandedTransportOptionKeys(
                                                  (current) => ({
                                                    ...current,
                                                    [transportOptionsPanelKey]:
                                                      !current[
                                                        transportOptionsPanelKey
                                                      ],
                                                  })
                                                )
                                              }
                                              type="button"
                                            >
                                              Các lựa chọn
                                              <ChevronDownIcon />
                                            </button>
                                          ) : null}
                                        </div>
                                        {transportLegOptions.length > 1 &&
                                        transportOptionsExpanded ? (
                                          <div
                                            className="itineraryRouteAlternatives"
                                            id={transportOptionsPanelId}
                                          >
                                            {transportLegOptions.map(
                                              (option, optionIndex) => (
                                                <TransportOptionCard
                                                  key={`${option.mode}-${option.source}-${optionIndex}`}
                                                  onSelect={
                                                    transportLegIndex >= 0
                                                      ? () =>
                                                          void choosePlanTransportOption(
                                                            displayedPlanDay.day,
                                                            transportLegIndex,
                                                            option
                                                          )
                                                      : undefined
                                                  }
                                                  option={option}
                                                  primary={optionIndex === 0}
                                                  saving={
                                                    savingTransportOptionKey ===
                                                    planLegSelectionKey(
                                                      displayedPlanDay.day,
                                                      transportLegIndex
                                                    )
                                                  }
                                                  selected={
                                                    selectedTransportLeg !=
                                                      null &&
                                                    transportOptionSelectionKey(
                                                      selectedTransportLeg
                                                    ) ===
                                                      transportOptionSelectionKey(
                                                        option
                                                      )
                                                  }
                                                />
                                              )
                                            )}
                                          </div>
                                        ) : null}
                                      </div>
                                    ) : transportLeg &&
                                      transportLegIndex >= 0 ? (
                                      <div
                                        className="itineraryRouteRetry"
                                        role="status"
                                      >
                                        <div>
                                          <strong>
                                            Không tính được tuyến phù hợp
                                          </strong>
                                          <small>
                                            Tính lại chặng từ {transportLeg.fromPlace} đến {transportLeg.toPlace}.
                                          </small>
                                          {transportLegRetryErrors[
                                            transportOptionsPanelKey
                                          ] ? (
                                            <span role="alert">
                                              {
                                                transportLegRetryErrors[
                                                  transportOptionsPanelKey
                                                ]
                                              }
                                            </span>
                                          ) : null}
                                        </div>
                                        <button
                                          disabled={
                                            retryingTransportLegKey ===
                                            transportOptionsPanelKey
                                          }
                                          onClick={(event) => {
                                            event.preventDefault();
                                            event.stopPropagation();
                                            void retryPlanTransportLeg(
                                              displayedPlanDay.day,
                                              transportLegIndex
                                            );
                                          }}
                                          type="button"
                                        >
                                          {retryingTransportLegKey ===
                                          transportOptionsPanelKey
                                            ? "Đang tính…"
                                            : "Thử lại"}
                                        </button>
                                      </div>
                                    ) : null}
                                  </Fragment>
                                );
                              })}
                            </div>
                            {activeChatId ? (
                              <button
                                className="itineraryAddButton"
                                onClick={() => {
                                  setAddingDay(displayedPlanDay.day);
                                  setAddName("");
                                  setAddPosition(
                                    plan?.days.find(
                                      (day) => day.day === displayedPlanDay.day
                                    )?.items.length ??
                                      displayedPlanDay.items.length
                                  );
                                  setAddNotes("");
                                  setSelectedSuggestion(null);
                                  setPlaceSuggestions([]);
                                  setAddSearchCompleted(false);
                                  setAddSearchFailed(false);
                                }}
                                type="button"
                              >
                                <svg viewBox="0 0 24 24">
                                  <line x1="12" y1="5" x2="12" y2="19" />
                                  <line x1="5" y1="12" x2="19" y2="12" />
                                </svg>
                                Thêm địa điểm cho Ngày {displayedPlanDay.day}
                              </button>
                            ) : null}
                          </article>
                        ))}
                        {activePlanDay === UNSCHEDULED_PLAN_DAY ||
                        (activePlanDay == null &&
                          (displayedPlan.unscheduledPlaces?.length ?? 0) > 0) ? (
                          <UnscheduledPlacesSection
                            candidateResolutionProgress={candidateResolutionProgress}
                            disabled={mutatingItem}
                            onConfirmCandidate={handleConfirmCandidateResolution}
                            onDismissPlace={handleDismissUnscheduledPlace}
                            onOpenReviews={setItineraryReviewPlace}
                            places={displayedPlan.unscheduledPlaces ?? []}
                          />
                        ) : null}
                        {activePlanDay === GROUP_PLAN_DAY ? (
                          <GroupPlanningPanel
                            chatId={activeChatId}
                            currentUserName={user?.fullName}
                            destination={displayedPlan.destination}
                          />
                        ) : null}
                      </div>
                    </section>
                  </div>
                ) : (
                  <div
                    aria-label={
                      loading ? "Đang tạo lịch trình" : "Chưa có lịch trình"
                    }
                    className="emptyPlan"
                    role="status"
                  >
                    <div className="explorerMascotCrew">
                      <Image
                        alt=""
                        aria-hidden="true"
                        className="explorerMascotArt"
                        height={1017}
                        priority
                        src="/images/explorer-crew-vietnam-v2-transparent.png"
                        width={1546}
                      />
                    </div>
                  </div>
                )}
              </section>

              <button
                aria-label={`Đổi chiều rộng lịch trình, hiện tại ${Math.round(
                  itineraryWidthPercent
                )}%`}
                aria-orientation="vertical"
                aria-valuemax={ITINERARY_MAX_PERCENT}
                aria-valuemin={ITINERARY_MIN_PERCENT}
                aria-valuenow={Math.round(itineraryWidthPercent)}
                className="itineraryResizeDivider"
                onKeyDown={resizeItineraryWithKeyboard}
                onPointerDown={beginItineraryResize}
                onPointerMove={(event) => {
                  if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                    updateItineraryWidth(event.clientX);
                  }
                }}
                onPointerUp={(event) => {
                  if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                    event.currentTarget.releasePointerCapture(event.pointerId);
                  }
                }}
                role="separator"
                title="Kéo để đổi chiều rộng lịch trình"
                type="button"
              >
                <span aria-hidden="true" />
              </button>

              <div
                aria-label="Lọc địa điểm trên bản đồ theo ngày"
                className="mobileMapDayTabs"
                role="tablist"
              >
                <button
                  aria-selected={activePlanDay == null}
                  className={activePlanDay == null ? "active" : ""}
                  onClick={() => {
                    setActivePlanDay(null);
                    setSelectedMapPlaceKey(null);
                    clearDayDirections();
                  }}
                  role="tab"
                  type="button"
                >
                  Tất cả
                </button>
                {displayedPlan?.days.map((day) => {
                  const dateKey = dateKeyForTripDay(displayedStartDate, day.day);
                  const color = planDayColors.get(dateKey) ?? "#365f5a";
                  return (
                    <button
                      aria-selected={activePlanDay === day.day}
                      className={activePlanDay === day.day ? "active" : ""}
                      key={`mobile-map-day-${day.day}`}
                      onClick={() => {
                        setActivePlanDay(day.day);
                        setSelectedMapPlaceKey(null);
                        clearDayDirections();
                      }}
                      role="tab"
                      style={{ "--day-color": color } as CSSProperties}
                      type="button"
                    >
                      <span aria-hidden="true" />
                      Ngày {day.day}
                    </button>
                  );
                })}
                <button
                  aria-selected={activePlanDay === UNSCHEDULED_PLAN_DAY}
                  className={
                    activePlanDay === UNSCHEDULED_PLAN_DAY
                      ? "active is-unscheduled"
                      : "is-unscheduled"
                  }
                  onClick={() => {
                    setActivePlanDay(UNSCHEDULED_PLAN_DAY);
                    setSelectedMapPlaceKey(null);
                    clearDayDirections();
                  }}
                  role="tab"
                  type="button"
                >
                  Chưa xếp
                </button>
              </div>

              <PlannerMap
                currentLocation={mapDirectionOrigin}
                navigationMode={
                  directionsActive
                    ? selectedDayDirectionLegs[0]?.mode ?? null
                    : null
                }
                dayColorKeys={planDayColorKeys}
                directionsActive={directionsActive}
                directionsBusy={directionsStatus === "routing"}
                directionsReady={directionsStatus === "ready"}
                directionsDay={activePlanDay}
                directionsEnabled={activeDayDirectionStops.length > 0}
                directionsSearchOpen={directionsSearchOpen}
                destinationOptions={directionDestinationOptions}
                destinationQuery={destinationQuery}
                destinationSearchBusy={false}
                destinationSuggestions={directionDestinationSuggestions}
                locationFocusRequest={locationFocusRequest}
                onChooseDestination={chooseDirectionDestination}
                onCancelDirections={clearDayDirections}
                onChooseOrigin={chooseDirectionOrigin}
                onCloseDirectionsSearch={closeDirectionsSearch}
                onDestinationQueryChange={updateDirectionDestinationQuery}
                routeFocusRequest={routeFocusRequest}
                locationBusy={locationStatus === "locating"}
                locationMessage={locationMessage}
                onLocate={recenterCurrentPosition}
                onOriginQueryChange={updateDirectionOriginQuery}
                onStartDirections={openDirectionsSearch}
                onSubmitDirections={submitDirectionSearch}
                onUseCurrentOrigin={chooseCurrentDirectionOrigin}
                originQuery={directionOriginQuery}
                originSearchBusy={searchingDirectionOrigin}
                originSuggestions={directionOriginSearchSuggestions}
                onSelect={selectPlaceFromMap}
                onSelectRoute={selectRouteFromMap}
                places={mapPlaces}
                routes={mapRoutes}
                selectedDirectionDestination={
                  selectedNavigationDestination
                    ? {
                        key:
                          selectedNavigationDestination.mapKey ??
                          `selected-${selectedNavigationDestination.latitude}-${selectedNavigationDestination.longitude}`,
                        name: selectedNavigationDestination.name,
                        detail: selectedNavigationDestination.address,
                        latitude: selectedNavigationDestination.latitude,
                        longitude: selectedNavigationDestination.longitude,
                        kind: selectedNavigationDestination.mapKey
                          ? "plan"
                          : "searched",
                      }
                    : null
                }
                selectedKey={selectedMapPlaceKey}
                selectedRouteKey={selectedMapRouteKey}
              />
            </section>
          )}
        </div>

        {destinationDetailsOpen && displayedPlan ? (
          <div
            aria-labelledby="destination-details-title"
            aria-modal="true"
            className="destinationDetailsModal"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget)
                setDestinationDetailsOpen(false);
            }}
            role="dialog"
          >
            <section className="destinationDetailsWindow">
              <header className="destinationDetailsHeader">
                <div>
                  <h2 id="destination-details-title">
                    {displayedPlan.destination}
                  </h2>
                </div>
                <button
                  aria-label="Đóng thông tin điểm đến"
                  onClick={() => setDestinationDetailsOpen(false)}
                  type="button"
                >
                  <svg aria-hidden="true" viewBox="0 0 24 24">
                    <path d="m7 7 10 10M17 7 7 17" />
                  </svg>
                </button>
              </header>
              <div className="destinationDetailsBody">
                <section
                  aria-labelledby="destination-history-title"
                  className="destinationDetailsSection destinationHistorySection"
                >
                  <header>
                    <span aria-hidden="true">01</span>
                    <div>
                      <h3 id="destination-history-title">Lịch sử</h3>
                    </div>
                  </header>
                  <div className="destinationDetailsNotes">
                    {destinationHistoryStories.length ? (
                      destinationHistoryStories.map(({ story, text }, index) => (
                        <article
                          key={`${story.ref ?? "destination-history"}-${index}`}
                        >
                          <p>
                            {text}
                            <DestinationSourceLink href={story.ref} />
                          </p>
                        </article>
                      ))
                    ) : (
                      <p className="destinationDetailsEmpty">
                        Chưa có nội dung lịch sử kèm nguồn.
                      </p>
                    )}
                  </div>
                </section>
                <section
                  aria-labelledby="destination-advice-title"
                  className="destinationDetailsSection destinationAdviceSection"
                >
                  <header>
                    <span aria-hidden="true">02</span>
                    <div>
                      <h3 id="destination-advice-title">Điều cần biết</h3>
                    </div>
                  </header>
                  <div className="destinationDetailsNotes">
                    {destinationAdviceStories.length ? (
                      destinationAdviceStories.map(({ story, text }, index) => (
                        <article
                          key={`${story.ref ?? story.type}-${index}`}
                        >
                          <p>
                            <strong>
                              {destinationNoteLabel(story.type, index)}.
                            </strong>{" "}
                            {text}
                            <DestinationSourceLink href={story.ref} />
                          </p>
                        </article>
                      ))
                    ) : (
                      <p className="destinationDetailsEmpty">
                        Chưa có lưu ý thực tế nào.
                      </p>
                    )}
                  </div>
                </section>
              </div>
            </section>
          </div>
        ) : null}

        {itineraryReviewPlace ? (
          <PlaceReviewsModal
            onClose={() => setItineraryReviewPlace(null)}
            place={itineraryReviewPlace}
          />
        ) : null}

        {editingItem ? (
          <div
            aria-labelledby="edit-place-title"
            aria-modal="true"
            className="itineraryMutationModal"
            onClick={() => setEditingItem(null)}
            role="dialog"
          >
            <form
              className="itineraryMutationForm editPlaceNotesWindow editPlaceWindow"
              onClick={(e) => e.stopPropagation()}
              onSubmit={handleSaveEditItem}
            >
              <header className="itineraryMutationHeader editPlaceNotesHeader">
                <div className="itineraryMutationHeading">
                  <div>
                    <h3 id="edit-place-title">Chỉnh sửa địa điểm</h3>
                  </div>
                </div>
                <button
                  aria-label="Đóng cửa sổ chỉnh sửa"
                  className="itineraryMutationClose"
                  onClick={() => setEditingItem(null)}
                  type="button"
                >
                  <svg aria-hidden="true" viewBox="0 0 24 24">
                    <path d="m7 7 10 10M17 7 7 17" />
                  </svg>
                </button>
              </header>
              <div className="itineraryMutationBody editPlaceNotesPaper">
                <div className="itineraryMutationField itinerarySearchContainer">
                  <label htmlFor="edit-place-search">
                    <span className="editPlaceSearchLabel">
                      Tìm và chọn địa điểm
                    </span>
                  </label>
                  <div className="itineraryMutationInputWrap editPlaceSearchControl">
                    <span className="editPlaceSearchIcon" aria-hidden="true">
                      <svg viewBox="0 0 24 24">
                        <circle cx="11" cy="11" r="6.5" />
                        <path d="m16 16 4 4" />
                      </svg>
                    </span>
                    <input
                      aria-autocomplete="list"
                      aria-controls="edit-place-suggestions"
                      aria-expanded={editPlaceSuggestions.length > 0}
                      autoComplete="off"
                      id="edit-place-search"
                      onChange={(e) => {
                        setEditingItem({
                          ...editingItem,
                          name: e.target.value,
                        });
                        setSelectedEditSuggestion(null);
                        setEditSearchCompleted(false);
                        setEditSearchFailed(false);
                      }}
                      placeholder="Nhập tên địa điểm để tìm"
                      required
                      role="combobox"
                      type="text"
                      value={editingItem.name}
                    />
                    {editingItem.name ? (
                      <button
                        aria-label="Xóa nội dung tìm kiếm"
                        className="editPlaceSearchClear"
                        onClick={(event) => {
                          setEditingItem({ ...editingItem, name: "" });
                          setSelectedEditSuggestion(null);
                          setEditPlaceSuggestions([]);
                          setEditSearchCompleted(false);
                          setEditSearchFailed(false);
                          event.currentTarget.parentElement
                            ?.querySelector("input")
                            ?.focus();
                        }}
                        type="button"
                      >
                        <svg aria-hidden="true" viewBox="0 0 24 24">
                          <path d="m8 8 8 8M16 8l-8 8" />
                        </svg>
                      </button>
                    ) : null}
                    <button
                      aria-label="Dùng vị trí hiện tại"
                      className={`editPlaceLocateButton${
                        placeLocationTarget === "edit" &&
                        locationStatus === "locating"
                          ? " isLocating"
                          : ""
                      }`}
                      disabled={locationStatus === "locating"}
                      onClick={() => useCurrentLocationForPlace("edit")}
                      title="Dùng vị trí hiện tại"
                      type="button"
                    >
                      <svg aria-hidden="true" viewBox="0 0 24 24">
                        <circle cx="12" cy="12" r="5" />
                        <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
                      </svg>
                    </button>
                  </div>
                  {placeLocationTarget === "edit" &&
                  locationStatus === "error" &&
                  locationError ? (
                    <span
                      className="itinerarySearchStatus isError"
                      role="alert"
                    >
                      {locationError}
                    </span>
                  ) : null}
                  {searchingEditSuggestions ? (
                    <span className="itinerarySearchStatus" role="status">
                      Đang tìm địa điểm…
                    </span>
                  ) : null}
                  {editPlaceSuggestions.length > 0 ? (
                    <div
                      className="itinerarySuggestionsDropdown"
                      id="edit-place-suggestions"
                      role="listbox"
                    >
                      {editPlaceSuggestions.map(
                        (suggestion, suggestionIndex) => (
                          <button
                            className="itinerarySuggestionItem"
                            key={
                              suggestion.placeId ||
                              `${suggestion.name}-${suggestionIndex}`
                            }
                            onClick={() => {
                              setEditingItem({
                                ...editingItem,
                                name: suggestion.name,
                              });
                              setSelectedEditSuggestion(suggestion);
                              setEditPlaceSuggestions([]);
                            }}
                            role="option"
                            type="button"
                          >
                            <strong>{suggestion.name}</strong>
                            {suggestion.address ? (
                              <span>{suggestion.address}</span>
                            ) : null}
                          </button>
                        )
                      )}
                    </div>
                  ) : null}
                </div>
                {!selectedEditSuggestion &&
                editSearchCompleted &&
                editSearchFailed ? (
                  <p className="itinerarySearchHint" role="alert">
                    Không thể tải dữ liệu Places lúc này. Vui lòng thử lại.
                  </p>
                ) : !selectedEditSuggestion &&
                  editSearchCompleted &&
                  editPlaceSuggestions.length === 0 ? (
                  <p className="itinerarySearchHint" role="status">
                    Không tìm thấy địa điểm phù hợp trong dữ liệu Places. Hãy
                    thử tên hoặc từ khóa khác.
                  </p>
                ) : !selectedEditSuggestion &&
                  editingItem.name.trim() !==
                    editingItem.originalName.trim() ? (
                  <p className="itinerarySearchHint">
                    Chọn một địa điểm trong gợi ý để cập nhật đúng vị trí trên
                    bản đồ.
                  </p>
                ) : null}
              </div>
              <div className="itineraryMutationActions">
                <button
                  className="cancel"
                  onClick={() => setEditingItem(null)}
                  type="button"
                >
                  Hủy
                </button>
                <button
                  className="submit"
                  disabled={
                    mutatingItem ||
                    (editingItem.name.trim() !==
                      editingItem.originalName.trim() &&
                      !selectedEditSuggestion)
                  }
                  type="submit"
                >
                  {mutatingItem ? "Đang lưu..." : "Lưu thay đổi"}
                </button>
              </div>
            </form>
          </div>
        ) : null}

        {addingDay != null ? (
          <div
            aria-labelledby="add-place-title"
            aria-modal="true"
            className="itineraryMutationModal"
            onClick={() => setAddingDay(null)}
            role="dialog"
          >
            <form
              className="itineraryMutationForm editPlaceNotesWindow addPlaceWindow"
              onClick={(e) => e.stopPropagation()}
              onSubmit={handleAddPlanItem}
            >
              <header className="itineraryMutationHeader editPlaceNotesHeader addPlaceHeader">
                <div className="itineraryMutationHeading">
                  <span className="addPlaceHeaderIcon" aria-hidden="true">
                    <svg viewBox="0 0 24 24">
                      <path d="M12 21s6-5.35 6-11a6 6 0 1 0-12 0c0 5.65 6 11 6 11Z" />
                      <path d="M12 7v6M9 10h6" />
                    </svg>
                  </span>
                  <div>
                    <div className="addPlaceTitleRow">
                      <h3 id="add-place-title">Thêm địa điểm</h3>
                      <span className="itineraryMutationEyebrow">
                        Ngày {addingDay}
                      </span>
                    </div>
                    <p>Tạo điểm dừng mới trong lịch trình của bạn</p>
                  </div>
                </div>
                <button
                  aria-label="Đóng cửa sổ thêm địa điểm"
                  className="itineraryMutationClose"
                  onClick={() => setAddingDay(null)}
                  type="button"
                >
                  <svg aria-hidden="true" viewBox="0 0 24 24">
                    <path d="m7 7 10 10M17 7 7 17" />
                  </svg>
                </button>
              </header>
              <div className="itineraryMutationBody editPlaceNotesPaper addPlacePaper">
                <div className="itineraryMutationField itinerarySearchContainer">
                  <label htmlFor="add-place-search">
                    <span className="editPlaceSearchLabel">Địa điểm</span>
                    <small className="addPlaceRequired">Bắt buộc</small>
                  </label>
                  <div className="itineraryMutationInputWrap editPlaceSearchControl">
                    <span className="editPlaceSearchIcon" aria-hidden="true">
                      <svg viewBox="0 0 24 24">
                        <circle cx="10.8" cy="10.8" r="6.8" />
                        <path d="m16 16 4.25 4.25" />
                      </svg>
                    </span>
                    <input
                      aria-autocomplete="list"
                      aria-controls="add-place-suggestions"
                      aria-describedby="add-place-search-help"
                      aria-expanded={placeSuggestions.length > 0}
                      autoComplete="off"
                      id="add-place-search"
                      onChange={(e) => {
                        setAddName(e.target.value);
                        setSelectedSuggestion(null);
                        setAddSearchCompleted(false);
                        setAddSearchFailed(false);
                      }}
                      placeholder="Tìm nhà hàng, điểm tham quan…"
                      required
                      role="combobox"
                      type="text"
                      value={addName}
                    />
                    {addName ? (
                      <button
                        aria-label="Xóa nội dung tìm kiếm"
                        className="editPlaceSearchClear"
                        onClick={(event) => {
                          setAddName("");
                          setSelectedSuggestion(null);
                          setPlaceSuggestions([]);
                          setAddSearchCompleted(false);
                          setAddSearchFailed(false);
                          event.currentTarget.parentElement
                            ?.querySelector("input")
                            ?.focus();
                        }}
                        type="button"
                      >
                        <svg aria-hidden="true" viewBox="0 0 24 24">
                          <path d="m8 8 8 8M16 8l-8 8" />
                        </svg>
                      </button>
                    ) : null}
                    <button
                      aria-label="Dùng vị trí hiện tại"
                      className={`editPlaceLocateButton${
                        placeLocationTarget === "add" &&
                        locationStatus === "locating"
                          ? " isLocating"
                          : ""
                      }`}
                      disabled={locationStatus === "locating"}
                      onClick={() => useCurrentLocationForPlace("add")}
                      title="Dùng vị trí hiện tại"
                      type="button"
                    >
                      <svg aria-hidden="true" viewBox="0 0 24 24">
                        <circle cx="12" cy="12" r="5" />
                        <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
                        <circle className="addPlaceLocateDot" cx="12" cy="12" r="1.5" />
                      </svg>
                    </button>
                  </div>
                  {placeLocationTarget === "add" &&
                  locationStatus === "error" &&
                  locationError ? (
                    <span
                      className="itinerarySearchStatus isError"
                      role="alert"
                    >
                      {locationError}
                    </span>
                  ) : null}
                  {searchingSuggestions ? (
                    <span className="itinerarySearchStatus" role="status">
                      Đang tìm địa điểm…
                    </span>
                  ) : null}
                  {placeSuggestions.length > 0 ? (
                    <div
                      className="itinerarySuggestionsDropdown"
                      id="add-place-suggestions"
                      role="listbox"
                    >
                      {placeSuggestions.map((suggestion, sIdx) => (
                        <button
                          className="itinerarySuggestionItem"
                          key={
                            suggestion.placeId || `${suggestion.name}-${sIdx}`
                          }
                          onClick={() => {
                            setAddName(suggestion.name);
                            setSelectedSuggestion(suggestion);
                            setPlaceSuggestions([]);
                            setAddSearchCompleted(false);
                            setAddSearchFailed(false);
                          }}
                          role="option"
                          type="button"
                        >
                          {suggestion.imageUrl ? (
                            <img
                              alt={suggestion.name}
                              className="suggestionThumbnail"
                              src={suggestion.imageUrl}
                            />
                          ) : (
                            <div className="suggestionThumbnailPlaceholder">
                              <svg viewBox="0 0 24 24" width="40" height="40">
                                <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" />
                              </svg>
                            </div>
                          )}
                          <div className="suggestionContent">
                            <strong>{suggestion.name}</strong>
                            <div className="suggestionMeta">
                              {suggestion.rating != null ? (
                                <span className="suggestionRating">
                                  <svg viewBox="0 0 24 24" width="14" height="14">
                                    <path
                                      d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"
                                      fill="#f59e0b"
                                    />
                                  </svg>
                                  {suggestion.rating.toFixed(1)}
                                </span>
                              ) : null}
                              {suggestion.reviewCount != null ? (
                                <span className="suggestionReviews">
                                  ({suggestion.reviewCount.toLocaleString("vi")} đánh giá)
                                </span>
                              ) : null}
                              {suggestion.placeType ? (
                                <span className="suggestionType">
                                  {suggestion.placeType}
                                </span>
                              ) : null}
                            </div>
                            {suggestion.address ? (
                              <span className="suggestionAddress">
                                {suggestion.address}
                              </span>
                            ) : null}
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>

                {selectedSuggestion ? (
                  <div
                    className="selectedPlaceBadge"
                    id="add-place-search-help"
                  >
                    <span className="selectedPlaceBadgeIcon" aria-hidden="true">
                      <svg viewBox="0 0 24 24">
                        <path d="m7 12 3 3 7-7" />
                      </svg>
                    </span>
                    <span>
                      <strong>Đã chọn vị trí</strong>
                      {selectedSuggestion.address || selectedSuggestion.name}
                    </span>
                  </div>
                ) : addSearchCompleted && addSearchFailed ? (
                  <p
                    className="itinerarySearchHint"
                    id="add-place-search-help"
                    role="alert"
                  >
                    Không thể tải dữ liệu Places lúc này. Vui lòng thử lại.
                  </p>
                ) : addSearchCompleted &&
                  addName.trim().length >= 2 &&
                  placeSuggestions.length === 0 ? (
                  <p
                    className="itinerarySearchHint"
                    id="add-place-search-help"
                    role="status"
                  >
                    Không tìm thấy địa điểm phù hợp trong dữ liệu Places. Hãy
                    thử tên hoặc từ khóa khác.
                  </p>
                ) : addName.trim() ? (
                  <p className="itinerarySearchHint" id="add-place-search-help">
                    Bạn phải chọn một kết quả trong danh sách để thêm đúng địa
                    điểm và vị trí bản đồ.
                  </p>
                ) : (
                  <p
                    className="itinerarySearchHint addPlaceSearchHelp"
                    id="add-place-search-help"
                  >
                    Chọn một kết quả gợi ý để đồng bộ đúng vị trí trên bản đồ.
                  </p>
                )}

                <div className="addPlaceDetails">
                  <div className="itineraryMutationField addPlacePositionField">
                    <label htmlFor="add-place-position">
                      Vị trí trong ngày
                    </label>
                    <div className="addPlaceSelectWrap">
                      <span aria-hidden="true" className="addPlaceFieldIcon">
                        <svg viewBox="0 0 24 24">
                          <path d="M6 6h12M6 18h12M12 15V9M9.5 11.5 12 9l2.5 2.5" />
                        </svg>
                      </span>
                      <select
                        id="add-place-position"
                        onChange={(event) =>
                          setAddPosition(Number(event.target.value))
                        }
                        value={addPosition}
                      >
                        <option value={0}>
                          {addingDayVisibleItems.length
                            ? `Đầu ngày — trước ${addingDayVisibleItems[0].name}`
                            : "Địa điểm đầu tiên trong ngày"}
                        </option>
                        {addingDayVisibleItems.map((item, itemIndex) => (
                          <option
                            key={item.itemId || `${item.name}-${itemIndex}`}
                            value={
                              itemIndex === addingDayVisibleItems.length - 1
                                ? addingPlanDay?.items.length ?? itemIndex + 1
                                : (addingPlanDay?.items.indexOf(item) ??
                                    itemIndex) + 1
                            }
                          >
                            {itemIndex === addingDayVisibleItems.length - 1
                              ? `Cuối ngày — sau ${item.name}`
                              : `Sau ${item.name}`}
                          </option>
                        ))}
                      </select>
                      <svg
                        aria-hidden="true"
                        className="addPlaceSelectChevron"
                        viewBox="0 0 24 24"
                      >
                        <path d="m7 10 5 5 5-5" />
                      </svg>
                    </div>
                    <small className="itineraryMutationHelper">
                      Địa điểm mới sẽ được chèn vào vị trí này trong lịch trình
                      Ngày {addingDay}.
                    </small>
                  </div>
                  <div className="itineraryMutationField addPlaceNotesField">
                    <label htmlFor="add-place-notes">
                      <span>Ghi chú</span>
                      <small>Tùy chọn</small>
                    </label>
                    <textarea
                      id="add-place-notes"
                      onChange={(e) => setAddNotes(e.target.value)}
                      placeholder="Ví dụ: Đến trước 8:00, thử món phở tái lăn…"
                      rows={3}
                      value={addNotes}
                    />
                  </div>
                  <div className="itineraryMutationField addPlaceTypeField">
                    <label htmlFor="add-place-type">Loại địa điểm</label>
                    <div className="addPlaceSelectWrap">
                      <span aria-hidden="true" className="addPlaceFieldIcon">
                        <svg viewBox="0 0 24 24">
                          <path d="M4.5 6.5v5.1a2 2 0 0 0 .59 1.41l6.9 6.9a2 2 0 0 0 2.82 0l5.1-5.1a2 2 0 0 0 0-2.82l-6.9-6.9a2 2 0 0 0-1.41-.59H6.5a2 2 0 0 0-2 2Z" />
                          <circle cx="9" cy="9" r="1.25" />
                        </svg>
                      </span>
                      <select
                        id="add-place-type"
                        onChange={(e) => setAddPlaceType(e.target.value)}
                        value={addPlaceType}
                      >
                        <option value="attraction">Tham quan / Vui chơi</option>
                        <option value="food">Ăn uống / Nhà hàng</option>
                        <option value="cafe">Cà phê / Giải khát</option>
                        <option value="hotel">Khách sạn / Lưu trú</option>
                      </select>
                      <svg
                        aria-hidden="true"
                        className="addPlaceSelectChevron"
                        viewBox="0 0 24 24"
                      >
                        <path d="m7 10 5 5 5-5" />
                      </svg>
                    </div>
                  </div>
                </div>
              </div>
              <div className="itineraryMutationActions addPlaceActions">
                <p aria-live="polite" className="addPlaceActionHint">
                  {selectedSuggestion
                    ? "Địa điểm đã sẵn sàng để thêm"
                    : "Hãy chọn một địa điểm từ kết quả tìm kiếm"}
                </p>
                <button
                  className="cancel"
                  onClick={() => {
                    setAddingDay(null);
                  }}
                  type="button"
                >
                  Hủy
                </button>
                <button
                  className="submit"
                  disabled={mutatingItem || !selectedSuggestion}
                  type="submit"
                >
                  {mutatingItem ? "Đang thêm..." : "Thêm vào lịch trình"}
                </button>
              </div>
            </form>
          </div>
        ) : null}
      </main>
    </>
  );
}
