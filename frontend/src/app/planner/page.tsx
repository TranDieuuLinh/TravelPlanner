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
  type KeyboardEvent as ReactKeyboardEvent
} from "react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { PenguinMascot } from "@/components/PenguinMascot";
import { TripKickoffCard } from "@/components/TripKickoffCard";
import { APIError } from "@/lib/api";
import {
  addTripChatItem,
  calculateDayDirections,
  createTripChat,
  createPlanFromExplorer,
  deleteTripChat,
  enqueueTripChatImages,
  enqueueTripChatUrls,
  exploreFullIntake,
  getTripChat,
  listTripChats,
  removeTripChatItem,
  reorderTripChatItem,
  searchPlaces,
  updateTripChatItem,
  isSupervisorEnabled,
  setSupervisorEnabled,
  type PlaceSuggestion,
  type ExplorerContext,
  type ExploreResponse,
  type PlaceCategory,
  type TransportOption,
  type TransportLeg,
  type TripChat,
  type TripChatSummary,
  type UnscheduledPlace,
  type TripChatTurn,
  type UrlImportJob,
  type TravelPlan
} from "@/lib/plans";
import { useConversationTurn } from "@/lib/useConversationTurn";
import {
  enqueueGuestImageJobs,
  enqueueGuestUrlJobs,
  GUEST_URL_JOB_RESULT_EVENT,
  listGuestUrlJobs,
  type GuestUrlImportJob
} from "@/lib/guest-url-jobs";
import {
  PlannerMap,
  type PlannerMapCurrentLocation,
  type PlannerMapPlace,
  type PlannerMapRoute,
  type PlannerMapSearchPlace
} from "@/components/PlannerMap";
import { createDayColorMap } from "@/lib/day-colors";
import {
  isAvailableTransportOption,
  isPublicTransitMode,
  visibleTransportOptions
} from "@/lib/transport-options";
import { visiblePlanDays, visiblePlanItems } from "@/lib/visible-plan-days";
import { formatPlanNote } from "@/lib/plan-note";

type ChatMessage = {
  id: number | string;
  role: "assistant" | "user";
  text: string;
};

type WorkflowStage = "idle" | "exploring" | "planning" | "ready" | "failed";
type IntakeKind = "prompt" | "image" | "url";
type LocationStatus = "idle" | "locating" | "ready" | "error";
type DirectionsStatus = "idle" | "routing" | "ready" | "error";
type StartPointMode = "current" | "search";

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

const promptSuggestions = [
  "Đà Nẵng 3 ngày, 2 người, 6 triệu, thích ẩm thực và biển",
  "Đà Lạt 2 ngày, đi chậm, cà phê và thiên nhiên",
  "Hà Nội cuối tuần, ưu tiên món địa phương và văn hóa"
];

const URL_PATTERN = /https?:\/\/[^\s<>"']+/i;
const URL_PATTERN_GLOBAL = /https?:\/\/[^\s<>"']+/gi;
const SUPPORTED_IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/heic",
  "image/heif"
]);

function formatBudget(result: ExplorerContext): string {
  const budget = result.tripSpec.budget;
  const formatter = new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: budget.currency,
    maximumFractionDigits: 0
  });

  if (budget.targetAmount != null) {
    return `Khoảng ${formatter.format(budget.targetAmount)}`;
  }
  return "Chưa có số tiền ước tính";
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

export default function PlannerPage() {
  return <Suspense fallback={<div className="routeLoading">Đang mở AI Planner…</div>}><Planner /></Suspense>;
}

function Planner() {
  const params = useSearchParams();
  const { user, loading: authLoading } = useAuth();
  const initialDestination = params.get("destination") ?? "";
  const [prompt, setPrompt] = useState(initialDestination ? `Tạo lịch trình ${initialDestination} 3 ngày, ẩm thực và văn hóa địa phương` : "");
  const [urlInput, setUrlInput] = useState("");
  const [urlImportNotice, setUrlImportNotice] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messageListRef = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 1,
      role: "assistant",
      text: "Nhập yêu cầu chuyến đi bằng một tin nhắn. Ví dụ: Đà Nẵng 3 ngày, ăn ngon, cà phê, đi chậm."
    }
  ]);
  const [exploreResult, setExploreResult] = useState<ExploreResponse | null>(null);
  const [selectedMapPlaceKey, setSelectedMapPlaceKey] = useState<string | null>(null);
  const [selectedMapRouteKey, setSelectedMapRouteKey] = useState<string | null>(null);
  const [activePlanDay, setActivePlanDay] = useState<number | null>(null);
  const [currentLocation, setCurrentLocation] =
    useState<PlannerMapCurrentLocation | null>(null);
  const [startPointMode, setStartPointMode] =
    useState<StartPointMode>("current");
  const [startPointSearchOpen, setStartPointSearchOpen] = useState(false);
  const [startPointQuery, setStartPointQuery] = useState("");
  const [startPointSuggestions, setStartPointSuggestions] =
    useState<PlaceSuggestion[]>([]);
  const [selectedStartPoint, setSelectedStartPoint] =
    useState<PlaceSuggestion | null>(null);
  const [searchingStartPoint, setSearchingStartPoint] = useState(false);
  const [startPointSearchCompleted, setStartPointSearchCompleted] = useState(false);
  const [startPointSearchFailed, setStartPointSearchFailed] = useState(false);
  const [dayDirectionLegs, setDayDirectionLegs] =
    useState<TransportLeg[]>([]);
  const [navigationDestinationKey, setNavigationDestinationKey] =
    useState<string | null>(null);
  const [selectedDirectionModes, setSelectedDirectionModes] =
    useState<Record<number, string>>({});
  const [selectedPlanLegModes, setSelectedPlanLegModes] =
    useState<Record<string, string>>({});
  const [directionsActive, setDirectionsActive] = useState(false);
  const [directionsSearchOpen, setDirectionsSearchOpen] = useState(false);
  const [destinationQuery, setDestinationQuery] = useState("");
  const [destinationSuggestions, setDestinationSuggestions] =
    useState<PlaceSuggestion[]>([]);
  const [selectedNavigationDestination, setSelectedNavigationDestination] =
    useState<DirectionStop | null>(null);
  const [searchingDestination, setSearchingDestination] = useState(false);
  const [mapDestinationPickActive, setMapDestinationPickActive] = useState(false);
  const [directionsStatus, setDirectionsStatus] =
    useState<DirectionsStatus>("idle");
  const [directionsError, setDirectionsError] = useState("");
  const [locationFocusRequest, setLocationFocusRequest] = useState(0);
  const [routeFocusRequest, setRouteFocusRequest] = useState(0);
  const [locationStatus, setLocationStatus] =
    useState<LocationStatus>("idle");
  const [locationError, setLocationError] = useState("");
  const directionsPendingLocationRef = useRef(false);
  const directionsDestinationRef = useRef<DirectionStop | null>(null);
  const directionsRequestIdRef = useRef(0);
  const [plan, setPlan] = useState<TravelPlan | null>(null);
  const [workflowStage, setWorkflowStage] = useState<WorkflowStage>("idle");
  const [loading, setLoading] = useState(false);
  const [processingStartedAt, setProcessingStartedAt] = useState<number | null>(null);
  const [processingElapsed, setProcessingElapsed] = useState(0);
  const [queueingUrls, setQueueingUrls] = useState(false);
  const [error, setError] = useState("");
  const [intakeKind, setIntakeKind] = useState<IntakeKind>("prompt");
  const [tripChats, setTripChats] = useState<TripChatSummary[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [chatRevision, setChatRevision] = useState(0);
  const [deletingChatId, setDeletingChatId] = useState<string | null>(null);
  const [historyCollapsed, setHistoryCollapsed] = useState(true);
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [sourcePanelOpen, setSourcePanelOpen] = useState(false);
  const [showTripKickoff, setShowTripKickoff] = useState(true);
  const [plannerEntryResolved, setPlannerEntryResolved] = useState(false);

  useEffect(() => {
    if (!loading || processingStartedAt == null) return;
    const updateElapsed = () => {
      setProcessingElapsed(Math.max(0, Math.floor((Date.now() - processingStartedAt) / 1000)));
    };
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [loading, processingStartedAt]);

  useEffect(() => {
    async function handleUrlJobUpdate(event: Event) {
      const job = (event as CustomEvent<UrlImportJob>).detail;
      if (!job) return;
      if (job.chatId !== activeChatId) return;
      try {
        const chat = await getTripChat(job.chatId);
        if (chat.revision >= chatRevision) {
          applyTripChat(chat);
          setTripChats(await listTripChats());
        }
      } catch {
        // The global job panel retains the actionable failure state.
      }
    }
    window.addEventListener("vsf:url-job-update", handleUrlJobUpdate);
    return () => window.removeEventListener("vsf:url-job-update", handleUrlJobUpdate);
  }, [activeChatId, chatRevision]);

  useEffect(() => {
    const applyGuestResult = (job: GuestUrlImportJob) => {
      if (job.status !== "succeeded" || !job.result) return;
      setShowTripKickoff(false);
      setExploreResult(job.result.explore);
      setPlan(job.result.plan);
      setWorkflowStage("ready");
      setSelectedMapPlaceKey(null);
      setError("");
    };
    const handleGuestResult = (event: Event) => {
      applyGuestResult((event as CustomEvent<GuestUrlImportJob>).detail);
    };
    window.addEventListener(GUEST_URL_JOB_RESULT_EVENT, handleGuestResult);
    const latest = listGuestUrlJobs()
      .filter((job) => job.status === "succeeded" && job.result)
      .sort((left, right) => Date.parse(right.finishedAt ?? "") - Date.parse(left.finishedAt ?? ""))[0];
    if (latest) applyGuestResult(latest);
    return () => window.removeEventListener(GUEST_URL_JOB_RESULT_EVENT, handleGuestResult);
  }, []);

  const [editingItem, setEditingItem] = useState<{
    day: number;
    itemId: string;
    originalName: string;
    name: string;
    personalNotes: string;
    notesExpanded: boolean;
  } | null>(null);
  const [addingDay, setAddingDay] = useState<number | null>(null);
  const [addName, setAddName] = useState("");
  const [addPlaceType, setAddPlaceType] = useState("attraction");
  const [addNotes, setAddNotes] = useState("");
  const [placeSuggestions, setPlaceSuggestions] = useState<PlaceSuggestion[]>([]);
  const [selectedSuggestion, setSelectedSuggestion] = useState<PlaceSuggestion | null>(null);
  const [searchingSuggestions, setSearchingSuggestions] = useState(false);
  const [addSearchCompleted, setAddSearchCompleted] = useState(false);
  const [addSearchFailed, setAddSearchFailed] = useState(false);
  const [editPlaceSuggestions, setEditPlaceSuggestions] = useState<PlaceSuggestion[]>([]);
  const [selectedEditSuggestion, setSelectedEditSuggestion] = useState<PlaceSuggestion | null>(null);
  const [searchingEditSuggestions, setSearchingEditSuggestions] = useState(false);
  const [editSearchCompleted, setEditSearchCompleted] = useState(false);
  const [editSearchFailed, setEditSearchFailed] = useState(false);
  const [mutatingItem, setMutatingItem] = useState(false);
  const [noteEditor, setNoteEditor] = useState<{
    day: number;
    itemId: string | null;
    itemName: string;
    sourceNote: string | null;
    additionalContext: string | null;
    personalNotes: string;
  } | null>(null);

  useEffect(() => {
    if (!noteEditor) return;

    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && !mutatingItem) setNoteEditor(null);
    };
    window.addEventListener("keydown", closeOnEscape);

    return () => {
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [mutatingItem, noteEditor]);
  const [pendingTurn, setPendingTurn] = useState<TripChatTurn | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [supervisorToggle, setSupervisorToggle] = useState<boolean>(
    () => isSupervisorEnabled()
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const sync = () => setSupervisorToggle(isSupervisorEnabled());
    window.addEventListener("vsf:supervisor-toggle", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("vsf:supervisor-toggle", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const toggleSupervisor = useCallback(() => {
    const next = !isSupervisorEnabled();
    setSupervisorEnabled(next);
    setSupervisorToggle(next);
  }, []);

  const handleTurnTerminal = useCallback(
    async (result: { turn: TripChatTurn; outcome: string }) => {
      if (result.outcome === "awaiting_confirmation") {
        setPendingTurn(result.turn);
        return;
      }
      // completed / failed / cancelled: refetch the chat so plan state stays in sync.
      try {
        const fresh = await getTripChat(activeChatId ?? result.turn.chatId);
        applyTripChat(fresh);
        setTripChats(await listTripChats());
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : String(caught);
        setError(message);
      } finally {
        setWorkflowStage("ready");
        setSelectedMapPlaceKey(null);
        setImages([]);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [activeChatId]
  );

  const conversationTurn = useConversationTurn(handleTurnTerminal);

  const confirmPendingTurn = useCallback(async () => {
    if (!pendingTurn) return;
    setConfirmBusy(true);
    try {
      await conversationTurn.confirm({
        chatId: pendingTurn.chatId,
        turnId: pendingTurn.id
      });
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(message);
    } finally {
      setConfirmBusy(false);
      setPendingTurn(null);
    }
  }, [pendingTurn, conversationTurn]);

  const cancelPendingTurn = useCallback(async () => {
    if (!pendingTurn) return;
    setConfirmBusy(true);
    try {
      await conversationTurn.cancel({
        chatId: pendingTurn.chatId,
        turnId: pendingTurn.id
      });
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(message);
    } finally {
      setConfirmBusy(false);
      setPendingTurn(null);
    }
  }, [pendingTurn, conversationTurn]);

  function openItemEditor(
    day: number,
    item: TravelPlan["days"][number]["items"][number],
    personalNotes: string | null
  ) {
    if (!item.itemId || !activeChatId) return;
    setEditingItem({
      day,
      itemId: item.itemId,
      originalName: item.name,
      name: item.name,
      personalNotes: personalNotes || "",
      notesExpanded: Boolean(personalNotes)
    });
    setSelectedEditSuggestion(
      item.address || item.latitude != null || item.longitude != null || item.placeId
        ? {
            name: item.name,
            address: item.address,
            latitude: item.latitude,
            longitude: item.longitude,
            placeId: item.placeId
          }
        : null
    );
    setEditPlaceSuggestions([]);
  }

  useEffect(() => {
    if (!addName.trim() || addName.trim().length < 2 || selectedSuggestion?.name === addName) {
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
    const query = startPointQuery.trim();
    if (
      !startPointSearchOpen ||
      query.length < 2 ||
      selectedStartPoint?.name === query
    ) {
      setStartPointSuggestions([]);
      setSearchingStartPoint(false);
      setStartPointSearchCompleted(false);
      setStartPointSearchFailed(false);
      return;
    }

    let cancelled = false;
    setStartPointSearchCompleted(false);
    setStartPointSearchFailed(false);
    const timer = window.setTimeout(async () => {
      setSearchingStartPoint(true);
      try {
        const results = await searchPlaces(query, plan?.destination);
        if (!cancelled) {
          setStartPointSuggestions(
            results.filter(
              (suggestion) =>
                typeof suggestion.latitude === "number" &&
                typeof suggestion.longitude === "number"
            )
          );
        }
      } catch {
        if (!cancelled) {
          setStartPointSuggestions([]);
          setStartPointSearchFailed(true);
        }
      } finally {
        if (!cancelled) {
          setSearchingStartPoint(false);
          setStartPointSearchCompleted(true);
        }
      }
    }, 300);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [plan?.destination, selectedStartPoint, startPointQuery, startPointSearchOpen]);

  useEffect(() => {
    const query = destinationQuery.trim();
    if (
      !directionsSearchOpen ||
      query.length < 2 ||
      selectedNavigationDestination?.name === query
    ) {
      setDestinationSuggestions([]);
      setSearchingDestination(false);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setSearchingDestination(true);
      try {
        const results = await searchPlaces(query, plan?.destination);
        if (!cancelled) {
          setDestinationSuggestions(
            results.filter(
              (suggestion) =>
                typeof suggestion.latitude === "number" &&
                typeof suggestion.longitude === "number"
            )
          );
        }
      } catch {
        if (!cancelled) setDestinationSuggestions([]);
      } finally {
        if (!cancelled) setSearchingDestination(false);
      }
    }, 300);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [
    destinationQuery,
    directionsSearchOpen,
    plan?.destination,
    selectedNavigationDestination
  ]);

  useEffect(() => {
    const query = editingItem?.name.trim() ?? "";
    if (!editingItem || query.length < 2 || selectedEditSuggestion?.name === query) {
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
    if (!confirm("Bạn có chắc chắn muốn xóa địa điểm này khỏi lịch trình?")) return;
    const previousPlan = plan;
    setPlan({
      ...plan,
      days: plan.days.map((planDay) => planDay.day !== day
        ? planDay
        : {
            ...planDay,
            items: planDay.items.filter((item) => item.itemId !== itemId),
            transportLegs: planDay.transportLegs.filter(
              (leg) => leg.fromItemId !== itemId && leg.toItemId !== itemId
            )
          })
    });
    setMutatingItem(true);
    setError("");
    try {
      const updatedChat = await removeTripChatItem({
        chatId: activeChatId,
        expectedRevision: chatRevision,
        day,
        itemId
      });
      setChatRevision(updatedChat.revision);
      if (updatedChat.currentPlan) setPlan(updatedChat.currentPlan);
      setMessages(
        updatedChat.messages.map((m, idx) => ({
          id: m.id || idx,
          role: m.role as "assistant" | "user",
          text: m.content
        }))
      );
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
      editingItem.name.trim() !== editingItem.originalName.trim()
      && !selectedEditSuggestion
    ) return;
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
          personalNotes: editingItem.personalNotes
        }
      });
      setChatRevision(updatedChat.revision);
      if (updatedChat.currentPlan) setPlan(updatedChat.currentPlan);
      setMessages(
        updatedChat.messages.map((m, idx) => ({
          id: m.id || idx,
          role: m.role as "assistant" | "user",
          text: m.content
        }))
      );
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
        item: { personalNotes }
      });
      setChatRevision(updatedChat.revision);
      if (updatedChat.currentPlan) setPlan(updatedChat.currentPlan);
      setMessages(
        updatedChat.messages.map((message, index) => ({
          id: message.id || index,
          role: message.role as "assistant" | "user",
          text: message.content
        }))
      );
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
          personalNotes: addNotes.trim() || undefined,
          address: selectedSuggestion?.address || undefined,
          latitude: selectedSuggestion?.latitude ?? undefined,
          longitude: selectedSuggestion?.longitude ?? undefined
        }
      });
      setChatRevision(updatedChat.revision);
      if (updatedChat.currentPlan) setPlan(updatedChat.currentPlan);
      setMessages(
        updatedChat.messages.map((m, idx) => ({
          id: m.id || idx,
          role: m.role as "assistant" | "user",
          text: m.content
        }))
      );
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

  const [draggedItemKey, setDraggedItemKey] = useState<{ day: number; itemId: string } | null>(null);
  const [dragOverItemId, setDragOverItemId] = useState<string | null>(null);
  const [reorderingDay, setReorderingDay] = useState<number | null>(null);

  async function handleReorderItems(day: number, newOrderedItemIds: string[]) {
    if (!activeChatId || !plan) return;
    setMutatingItem(true);
    setReorderingDay(day);
    setError("");
    const previousPlan = plan;

    const updatedDays = plan.days.map((d) => {
      if (d.day !== day) return d;
      const itemsMap = new Map(d.items.map((it) => [it.itemId, it]));
      const rawNewItems = newOrderedItemIds
        .map((id) => itemsMap.get(id))
        .filter((it): it is typeof d.items[number] => Boolean(it));
      d.items.forEach((it) => {
        if (it.itemId && !newOrderedItemIds.includes(it.itemId)) {
          rawNewItems.push(it);
        }
      });

      return { ...d, items: rawNewItems, transportLegs: [] };
    });
    setPlan({ ...plan, days: updatedDays });

    try {
      const updatedChat = await reorderTripChatItem({
        chatId: activeChatId,
        expectedRevision: chatRevision,
        day,
        itemIds: newOrderedItemIds
      });
      setChatRevision(updatedChat.revision);
      if (updatedChat.currentPlan) setPlan(updatedChat.currentPlan);
    } catch (err: any) {
      setPlan(previousPlan);
      setError(err?.message || "Không thể sắp xếp lại vị trí địa điểm.");
    } finally {
      setMutatingItem(false);
      setReorderingDay(null);
    }
  }

  function handleMoveItemOrder(day: number, itemIndex: number, direction: "up" | "down") {
    const targetDayObj = plan?.days.find((d) => d.day === day);
    if (!targetDayObj) return;

    const items = [...targetDayObj.items];
    const targetIndex = direction === "up" ? itemIndex - 1 : itemIndex + 1;
    if (targetIndex < 0 || targetIndex >= items.length) return;

    const temp = items[itemIndex];
    items[itemIndex] = items[targetIndex];
    items[targetIndex] = temp;

    const itemIds = items.map((it) => it.itemId).filter((id): id is string => Boolean(id));
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
    if (authLoading || !user) {
      if (authLoading) {
        setPlannerEntryResolved(false);
      } else {
        setTripChats([]);
        setActiveChatId(null);
        setChatRevision(0);
        setExploreResult(null);
        setPlan(null);
        setCurrentLocation(null);
        setDayDirectionLegs([]);
        setSelectedDirectionModes({});
        setSelectedPlanLegModes({});
        setDirectionsActive(false);
        setDirectionsStatus("idle");
        setDirectionsError("");
        setLocationFocusRequest(0);
        directionsPendingLocationRef.current = false;
        directionsRequestIdRef.current += 1;
        setLocationStatus("idle");
        setLocationError("");
        setWorkflowStage("idle");
        setShowTripKickoff(true);
        setMessages([{
          id: Date.now(),
          role: "assistant",
          text: "Nhập yêu cầu chuyến đi bằng một tin nhắn. Ví dụ: Đà Nẵng 3 ngày, ăn ngon, cà phê, đi chậm."
        }]);
        setPlannerEntryResolved(true);
      }
      return;
    }
    let cancelled = false;
    setPlannerEntryResolved(false);
    setShowTripKickoff(false);
    setTripChats([]);
    setActiveChatId(null);
    setChatRevision(0);
    setExploreResult(null);
    setPlan(null);
    setMessages([{
      id: Date.now(),
      role: "assistant",
      text: "Nhập yêu cầu chuyến đi bằng một tin nhắn. Ví dụ: Đà Nẵng 3 ngày, ăn ngon, cà phê, đi chậm."
    }]);
    void listTripChats()
      .then(async (chats) => {
        if (cancelled) return;
        setTripChats(chats);
        if (chats.length > 0) {
          const chat = await getTripChat(chats[0].id);
          if (!cancelled) applyTripChat(chat);
        } else {
          setShowTripKickoff(true);
        }
        if (!cancelled) setPlannerEntryResolved(true);
      })
      .catch((caught) => {
        if (!cancelled) {
          setShowTripKickoff(false);
          setPlannerEntryResolved(true);
          setError(caught instanceof Error ? caught.message : "Không thể tải lịch sử chuyến đi.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [authLoading, user?.id]);

  useEffect(() => {
    return () => {
      directionsPendingLocationRef.current = false;
      directionsRequestIdRef.current += 1;
    };
  }, [user?.id]);

  useEffect(() => {
    const messageList = messageListRef.current;
    if (messageList) {
      messageList.scrollTo({ top: messageList.scrollHeight, behavior: "smooth" });
    }
  }, [messages, workflowStage]);

  const displayedExploreResult = exploreResult;
  const displayedPlan = useMemo(
    () => plan
      ? {
          ...plan,
          days: visiblePlanDays(
            plan.days.map((day) => ({
              ...day,
              items: visiblePlanItems(day.items)
            }))
          )
        }
      : null,
    [plan]
  );
  const planDayColorKeys = useMemo(() => {
    const startDate = displayedExploreResult?.explorer.tripSpec.startDate;
    return displayedPlan?.days.map(
      (day) => dateKeyForTripDay(startDate, day.day)
    ) ?? [];
  }, [displayedExploreResult?.explorer.tripSpec.startDate, displayedPlan]);
  const planDayColors = useMemo(
    () => createDayColorMap(planDayColorKeys),
    [planDayColorKeys]
  );
  const displayedPlanDays = useMemo(
    () => {
      if (!displayedPlan) return [];
      if (activePlanDay == null) return displayedPlan.days;
      return displayedPlan.days.filter((day) => day.day === activePlanDay);
    },
    [activePlanDay, displayedPlan]
  );

  useEffect(() => {
    setActivePlanDay((current) => {
      if (current == null) return displayedPlan?.days[0]?.day ?? null;
      if (displayedPlan?.days.some((day) => day.day === current)) return current;
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
    setDestinationQuery("");
    setDestinationSuggestions([]);
    setSelectedNavigationDestination(null);
    setMapDestinationPickActive(false);
    setDayDirectionLegs([]);
    setSelectedDirectionModes({});
    setDirectionsStatus("idle");
    setDirectionsError("");
    setNavigationDestinationKey(null);
    directionsDestinationRef.current = null;
  }, [activePlanDay]);

  useEffect(() => {
    directionsPendingLocationRef.current = false;
    directionsRequestIdRef.current += 1;
    setDirectionsActive(false);
    setDayDirectionLegs([]);
    setSelectedDirectionModes({});
    setSelectedPlanLegModes({});
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
        return [{
          ...item,
          day: day.day,
          order: dayOrder,
          mapKey: hasPlanItemCoordinates(item)
            ? planItemMapKey(day.day, itemIndex, item.name)
            : null
        }];
      });
    });
  }, [displayedPlan]);
  const mapPlaces = useMemo<PlannerMapPlace[]>(() => {
    const startDate = displayedExploreResult?.explorer.tripSpec.startDate;
    return tripPlaces
      .filter((item) => activePlanDay == null || item.day === activePlanDay)
      .flatMap((item) =>
        item.mapKey
          ? [{
              name: item.name,
              category: categoryFromPlaceType(item.placeType),
              address: item.address || `Ngày ${item.day}`,
              latitude: item.latitude ?? null,
              longitude: item.longitude ?? null,
              notes: item.notes,
              imageUrl: item.imageUrls?.find(isDisplayableImageUrl) ?? null,
              mapKey: item.mapKey,
              mapOrder: directionsActive
                ? directionItineraryOrder(dayDirectionLegs, item)
                  ?? item.order
                : item.order,
              dayColorKey: dateKeyForTripDay(startDate, item.day),
              dayLabel: dateLabelForTripDay(startDate, item.day),
              timeWindow: item.timeWindow
            }]
          : []
      );
  }, [
    activePlanDay,
    dayDirectionLegs,
    directionsActive,
    displayedExploreResult?.explorer.tripSpec.startDate,
    tripPlaces
  ]);
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
            } =>
              item.day === activePlanDay &&
              hasPlanItemCoordinates(item)
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
      selectedNavigationDestination
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
        kind: "plan"
      })),
    [activeDayDirectionStops]
  );
  const directionOriginSuggestions = useMemo<PlannerMapSearchPlace[]>(
    () =>
      startPointSuggestions.flatMap((suggestion, index) =>
        typeof suggestion.latitude === "number" &&
        typeof suggestion.longitude === "number"
          ? [{
              key: suggestion.placeId ?? `origin-${index}`,
              name: suggestion.name,
              detail: suggestion.address,
              latitude: suggestion.latitude,
              longitude: suggestion.longitude,
              kind: "searched" as const
            }]
          : []
      ),
    [startPointSuggestions]
  );
  const directionDestinationSuggestions = useMemo<PlannerMapSearchPlace[]>(
    () => {
      const query = destinationQuery.trim().toLocaleLowerCase("vi");
      const localMatches = directionDestinationOptions.filter((place) =>
        `${place.name} ${place.detail ?? ""}`.toLocaleLowerCase("vi").includes(query)
      );
      const searchedMatches = destinationSuggestions.flatMap((suggestion, index) =>
        typeof suggestion.latitude === "number" &&
        typeof suggestion.longitude === "number"
          ? [{
              key: suggestion.placeId ?? `destination-${index}`,
              name: suggestion.name,
              detail: suggestion.address,
              latitude: suggestion.latitude,
              longitude: suggestion.longitude,
              kind: "searched" as const
            }]
          : []
      );
      return [...localMatches, ...searchedMatches].filter(
        (place, index, all) =>
          all.findIndex(
            (candidate) =>
              candidate.latitude === place.latitude &&
              candidate.longitude === place.longitude
          ) === index
      );
    }, [destinationQuery, destinationSuggestions, directionDestinationOptions]
  );
  const activeDayItineraryRouteSummary = useMemo(() => {
    const day = displayedPlan?.days.find((item) => item.day === activePlanDay);
    if (!day) return { distanceMeters: 0, durationMinutes: 0 };
    return day.transportLegs.reduce(
      (total, leg, index) => {
        const selected = selectedTransportOption(
          leg,
          selectedPlanLegModes[planLegSelectionKey(day.day, index)]
        );
        return {
          distanceMeters: total.distanceMeters + selected.distanceMeters,
          durationMinutes:
            total.durationMinutes + selected.estimatedDurationMinutes
        };
      },
      { distanceMeters: 0, durationMinutes: 0 }
    );
  }, [activePlanDay, displayedPlan, selectedPlanLegModes]);
  const navigationOrigin = useMemo<PlannerMapCurrentLocation | null>(() => {
    if (
      startPointMode === "search" &&
      selectedStartPoint &&
      typeof selectedStartPoint.latitude === "number" &&
      typeof selectedStartPoint.longitude === "number"
    ) {
      return {
        latitude: selectedStartPoint.latitude,
        longitude: selectedStartPoint.longitude,
        accuracy: 0,
        heading: null,
        label: selectedStartPoint.name,
        detail: selectedStartPoint.address ?? "Điểm bắt đầu đã chọn",
        kind: "searched"
      };
    }
    if (startPointMode === "search") return null;
    return currentLocation
      ? {
          ...currentLocation,
          label: "Vị trí của tôi",
          kind: "device"
        }
      : null;
  }, [currentLocation, selectedStartPoint, startPointMode]);
  const selectedDayDirectionLegs = useMemo(
    () =>
      dayDirectionLegs.map((leg, index) =>
        selectedTransportOption(
          leg,
          selectedDirectionModes[index]
        )
      ),
    [dayDirectionLegs, selectedDirectionModes]
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
        startLeg.estimatedDurationMinutes
    };
  }, [
    activeDayDirectionStops,
    activeDayItineraryRouteSummary,
    dayDirectionLegs,
    selectedDayDirectionLegs
  ]);
  const mapRoutes = useMemo<PlannerMapRoute[]>(() => {
    if (!displayedPlan) return [];
    const startDate = displayedExploreResult?.explorer.tripSpec.startDate;
    const shouldUseDirectionRoutes =
      directionsActive && selectedDayDirectionLegs.length > 0;
    const itineraryRoutes: PlannerMapRoute[] = shouldUseDirectionRoutes
      ? []
      : displayedPlan.days
          .filter(
            (day) => activePlanDay == null || day.day === activePlanDay
          )
          .flatMap((day) =>
            day.transportLegs
              .flatMap((leg, index) => {
                const selected = selectedTransportOption(
                  leg,
                  selectedPlanLegModes[
                    planLegSelectionKey(day.day, index)
                  ]
                );
                if (!isDrawableTransportRoute(selected)) return [];
                return [{
                  key: `day-${day.day}-leg-${index}-${selected.mode}`,
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
                  segments: selected.details?.segments
                }];
              })
          );
    if (shouldUseDirectionRoutes && activePlanDay != null) {
      selectedDayDirectionLegs
        .filter(isDrawableTransportRoute)
        .forEach((leg, index) => {
          itineraryRoutes.push({
            key: `day-directions-${activePlanDay}-${index}-${leg.mode}`,
            mode: leg.mode,
            fromPlace: dayDirectionLegs[index]?.fromPlace ?? "Vị trí của tôi",
            toPlace: dayDirectionLegs[index]?.toPlace ?? "Điểm đến",
            distanceMeters: leg.distanceMeters,
            estimatedDurationMinutes: leg.estimatedDurationMinutes,
            coordinates: leg.geometryCoordinates,
            verified: leg.verified,
            source: leg.source,
            dayColorKey: dateKeyForTripDay(startDate, activePlanDay),
            kind: "current_location",
            segments: leg.details?.segments
          });
        });
    }
    return itineraryRoutes;
  }, [
    activePlanDay,
    directionsActive,
    displayedExploreResult?.explorer.tripSpec.startDate,
    displayedPlan,
    selectedPlanLegModes,
    dayDirectionLegs,
    selectedDayDirectionLegs
  ]);
  const selectedMapRoute = useMemo(
    () => mapRoutes.find((route) => route.key === selectedMapRouteKey) ?? null,
    [mapRoutes, selectedMapRouteKey]
  );

  async function requestDayDirections(
    origin: PlannerMapCurrentLocation,
    destination: DirectionStop | null = directionsDestinationRef.current
  ) {
    const destinations = destination
      ? [destination]
      : activeDayDirectionStops;
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
          name: origin.label
        },
        destinations: destinations.map((stop) => ({
          itemId: stop.itemId ?? null,
          name: stop.name,
          address: stop.address ?? null,
          latitude: stop.latitude,
          longitude: stop.longitude
        })),
        departureTime: new Date().toISOString()
      });
      if (requestId !== directionsRequestIdRef.current) return;
      setDayDirectionLegs(legs);
      const planDay = displayedPlan?.days.find(
        (day) => day.day === activePlanDay
      );
      if (planDay) {
        const synchronizedModes: Record<number, string> = {};
        legs.forEach((leg, navigationLegIndex) => {
          const planLegIndex = planDay.transportLegs.findIndex(
            (planLeg) => transportLegsMatch(planLeg, leg)
          );
          if (planLegIndex < 0) return;
          const selectedMode = selectedPlanLegModes[
            planLegSelectionKey(planDay.day, planLegIndex)
          ];
          if (selectedMode) {
            synchronizedModes[navigationLegIndex] = selectedMode;
          }
        });
        setSelectedDirectionModes(synchronizedModes);
      }
      setDirectionsStatus("ready");
      // Enter the navigation camera as soon as route geometry is available,
      // so the first directions click also applies the compass bearing.
      setLocationFocusRequest((current) => current + 1);
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
      setLocationStatus("error");
      setLocationError("Trình duyệt này không hỗ trợ định vị.");
      setStartPointMode("search");
      setStartPointSearchOpen(true);
      return;
    }
    if (!window.isSecureContext) {
      setLocationStatus("error");
      setLocationError(
        "Định vị cần HTTPS hoặc localhost. Hãy mở ứng dụng qua kết nối an toàn."
      );
      setStartPointMode("search");
      setStartPointSearchOpen(true);
      return;
    }

    setLocationStatus("locating");
    setLocationError("");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const nextLocation = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          heading:
            typeof position.coords.heading === "number"
              ? position.coords.heading
              : null
        };
        setCurrentLocation(nextLocation);
        setStartPointMode("current");
        setStartPointSearchOpen(false);
        setLocationFocusRequest((current) => current + 1);
        if (directionsPendingLocationRef.current) {
          directionsPendingLocationRef.current = false;
          void requestDayDirections({
            ...nextLocation,
            label: "Vị trí của tôi",
            kind: "device"
          }, directionsDestinationRef.current);
        }
        setLocationStatus("ready");
      },
      (geolocationError) => {
        const directionsWereWaiting =
          directionsPendingLocationRef.current;
        directionsPendingLocationRef.current = false;
        setLocationStatus("error");
        setLocationError(geolocationErrorMessage(geolocationError));
        setStartPointMode("search");
        setStartPointSearchOpen(true);
        if (directionsWereWaiting) {
          setDirectionsStatus("error");
          setDirectionsError(
            "Không thể bắt đầu chỉ đường khi chưa lấy được vị trí."
          );
        }
      },
      {
        enableHighAccuracy: true,
        timeout: 10_000,
        maximumAge: 5_000
      }
    );
  }

  function recenterCurrentPosition() {
    // getCurrentPosition is intentionally one-shot. A click refreshes the
    // device position and triggers exactly one camera move on success.
    locateCurrentPosition();
  }

  function startDayDirections(destination = activeNavigationDestination) {
    if (activePlanDay == null || !destination) {
      setDirectionsStatus("error");
      setDirectionsError(
        "Chọn một ngày có địa điểm trước khi bắt đầu chỉ đường."
      );
      return;
    }
    setNavigationDestinationKey(destination.mapKey);
    setSelectedNavigationDestination(destination);
    setDestinationQuery(destination.name);
    directionsDestinationRef.current = destination;
    setSelectedDirectionModes({});
    setDirectionsActive(true);
    if (navigationOrigin) {
      void requestDayDirections(navigationOrigin, destination);
      return;
    }
    directionsPendingLocationRef.current = true;
    setDirectionsStatus("routing");
    locateCurrentPosition();
  }

  function viewDayRoute() {
    setDirectionsActive(true);
    setNavigationDestinationKey(null);
    setSelectedNavigationDestination(null);
    directionsDestinationRef.current = null;
    setSelectedMapPlaceKey(null);
    setStartPointMode("current");
    setStartPointSearchOpen(false);
    setStartPointQuery("");
    setSelectedStartPoint(null);
    if (currentLocation) {
      void requestDayDirections({
        ...currentLocation,
        label: "Vị trí của tôi",
        kind: "device"
      }, null);
      return;
    }
    directionsPendingLocationRef.current = true;
    setDirectionsStatus("routing");
    locateCurrentPosition();
  }

  function openDirectionsSearch() {
    const initialDestination = activeNavigationDestination;
    setDirectionsSearchOpen(true);
    setMapDestinationPickActive(false);
    if (initialDestination && !selectedNavigationDestination) {
      setSelectedNavigationDestination(initialDestination);
      setDestinationQuery(initialDestination.name);
    }
  }

  function closeDirectionsSearch() {
    setDirectionsSearchOpen(false);
    setMapDestinationPickActive(false);
    setStartPointSearchOpen(false);
  }

  function chooseDirectionOrigin(place: PlannerMapSearchPlace) {
    chooseSearchedStartPoint({
      name: place.name,
      address: place.detail,
      latitude: place.latitude,
      longitude: place.longitude,
      placeId: place.key
    });
  }

  function updateDirectionDestinationQuery(value: string) {
    setDestinationQuery(value);
    setSelectedNavigationDestination(null);
    setNavigationDestinationKey(null);
    setMapDestinationPickActive(false);
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
      mapKey: place.kind === "plan" ? place.key : null
    };
    setSelectedNavigationDestination(destination);
    setNavigationDestinationKey(destination.mapKey);
    setDestinationQuery(place.name);
    setDestinationSuggestions([]);
    setMapDestinationPickActive(false);
    directionsDestinationRef.current = destination;
  }

  function submitDirectionSearch() {
    if (!selectedNavigationDestination) return;
    setDirectionsSearchOpen(false);
    setMapDestinationPickActive(false);
    startDayDirections(selectedNavigationDestination);
  }

  function chooseCurrentStartPoint() {
    setStartPointMode("current");
    setStartPointSearchOpen(false);
    setStartPointQuery("");
    setSelectedStartPoint(null);
    // Keep the permission request inside the click handler. Browsers may
    // suppress geolocation prompts that are triggered automatically on load.
    directionsPendingLocationRef.current = directionsActive;
    locateCurrentPosition();
  }

  function chooseSearchedStartPoint(suggestion: PlaceSuggestion) {
    if (
      typeof suggestion.latitude !== "number" ||
      typeof suggestion.longitude !== "number"
    ) return;
    const origin: PlannerMapCurrentLocation = {
      latitude: suggestion.latitude,
      longitude: suggestion.longitude,
      accuracy: 0,
      heading: null,
      label: suggestion.name,
      detail: suggestion.address ?? "Điểm bắt đầu đã chọn",
      kind: "searched"
    };
    setSelectedStartPoint(suggestion);
    setStartPointMode("search");
    setStartPointQuery(suggestion.name);
    setStartPointSuggestions([]);
    setStartPointSearchOpen(false);
    setLocationFocusRequest((current) => current + 1);
    if (directionsActive) void requestDayDirections(origin);
  }

  function updateStartPointQuery(value: string) {
    setStartPointMode("search");
    setStartPointQuery(value);
    setSelectedStartPoint(null);
    setStartPointSearchOpen(true);
    setLocationError("");
  }

  function clearDayDirections() {
    directionsPendingLocationRef.current = false;
    directionsRequestIdRef.current += 1;
    setDirectionsActive(false);
    setDirectionsSearchOpen(false);
    setMapDestinationPickActive(false);
    setDayDirectionLegs([]);
    setSelectedDirectionModes({});
    setDirectionsStatus("idle");
    setDirectionsError("");
  }

  function chooseDirectionOption(legIndex: number, mode: string) {
    setSelectedDirectionModes((current) => ({
      ...current,
      [legIndex]: mode
    }));
    const navigationLeg = dayDirectionLegs[legIndex];
    const selectedOption = navigationLeg
      ? selectedTransportOption(navigationLeg, mode)
      : null;
    if (
      selectedOption &&
      activePlanDay != null &&
      isDrawableTransportRoute(selectedOption)
    ) {
      focusRouteOnMap(
        `day-directions-${activePlanDay}-${legIndex}-${selectedOption.mode}`
      );
    }
    const planDay = displayedPlan?.days.find(
      (day) => day.day === activePlanDay
    );
    if (!navigationLeg || !planDay) return;
    const planLegIndex = planDay.transportLegs.findIndex(
      (leg) => transportLegsMatch(leg, navigationLeg)
    );
    if (planLegIndex >= 0) {
      setSelectedPlanLegModes((current) => ({
        ...current,
        [planLegSelectionKey(planDay.day, planLegIndex)]: mode
      }));
    }
  }

  function choosePlanTransportOption(
    day: number,
    legIndex: number,
    mode: string
  ) {
    setSelectedPlanLegModes((current) => ({
      ...current,
      [planLegSelectionKey(day, legIndex)]: mode
    }));
    const planLeg = displayedPlan?.days
      .find((planDay) => planDay.day === day)
      ?.transportLegs[legIndex];
    if (!planLeg) return;
    const selectedOption = selectedTransportOption(planLeg, mode);
    if (isDrawableTransportRoute(selectedOption)) {
      focusRouteOnMap(
        `day-${day}-leg-${legIndex}-${selectedOption.mode}`
      );
    } else {
      setSelectedMapRouteKey(null);
    }
    const navigationLegIndex = dayDirectionLegs.findIndex(
      (leg) => transportLegsMatch(leg, planLeg)
    );
    if (navigationLegIndex >= 0) {
      setSelectedDirectionModes((current) => ({
        ...current,
        [navigationLegIndex]: mode
      }));
    }
  }

  function focusRouteOnMap(routeKey: string) {
    if (selectedMapRouteKey === routeKey) {
      setSelectedMapRouteKey(null);
      return;
    }
    setSelectedMapPlaceKey(null);
    setSelectedMapRouteKey(routeKey);
    setRouteFocusRequest((current) => current + 1);
    window.requestAnimationFrame(() => {
      document.querySelector(".plannerMap")?.scrollIntoView({
        behavior: "smooth",
        block: "nearest"
      });
    });
  }

  const selectRouteFromMap = useCallback((routeKey: string) => {
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
      const focusTarget = matchingRoute?.querySelector<HTMLElement>(
        "button, summary"
      ) ?? matchingRoute;
      focusTarget?.focus({ preventScroll: true });
    });
  }, [selectedMapRouteKey]);

  function selectRouteFromItinerary(routeKey: string) {
    focusRouteOnMap(routeKey);
  }

  const selectPlaceFromMap = useCallback((mapKey: string) => {
    setSelectedMapRouteKey(null);
    setSelectedMapPlaceKey(mapKey);
  }, []);

  const locationMessage = useMemo(() => {
    if (directionsStatus === "routing" && activePlanDay != null) {
      return `Đang tính tuyến đường ngày ${activePlanDay}…`;
    }
    if (locationStatus === "locating") {
      return "Đang lấy vị trí từ thiết bị…";
    }
    if (locationStatus === "error") {
      return locationError;
    }
    if (directionsStatus === "error") return directionsError;
    if (
      directionsStatus === "ready" &&
      dayDirectionLegs.length > 0
    ) {
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
          minimumFractionDigits: totalDistanceMeters < 1000 ? 1 : 0
        }
      );
      return `⏱ ${totalMinutes} phút · ${totalKilometers} km`;
    }
    return null;
  }, [
    activePlanDay,
    dayDirectionLegs,
    directionsError,
    directionsStatus,
    locationError,
    locationStatus,
    selectedDayDirectionLegs
  ]);

  async function sendMessage() {
    const typedText = prompt.trim();
    if (!typedText && images.length === 0) {
      setError("Nhập yêu cầu, dán URL hoặc đính kèm ảnh trước khi gửi.");
      return;
    }
    const text = typedText || "Tạo lịch trình từ ảnh đính kèm.";
    const messageUrls = extractMessageUrls(text);

    if (messageUrls.length > 0) {
      setUrlInput(messageUrls.join("\n"));
      setSourcePanelOpen(true);
      setError("Hãy dùng ô Nhập URL để thêm nguồn; URL sẽ không xuất hiện như một tin nhắn chat.");
      return;
    }

    const attachmentSummary = images.length ? `📎 ${images.length} ảnh` : "";
    const userMessage: ChatMessage = {
      id: Date.now(),
      role: "user",
      text: [text, attachmentSummary].filter(Boolean).join("\n")
    };
    setMessages((current) => [...current, userMessage]);
    setPrompt("");
    if (!user && (messageUrls.length > 0 || images.length > 0)) {
      if (messageUrls.length > 0) enqueueGuestUrlJobs({ content: text, urls: messageUrls });
      if (images.length > 0) {
        enqueueGuestImageJobs({ content: text, images, urls: messageUrls });
      }
      setImages([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setError("");
      return;
    }
    if (user && (messageUrls.length > 0 || images.length > 0)) {
      setQueueingUrls(true);
      setError("");
      try {
        let chatId = activeChatId;
        let expectedRevision = chatRevision;
        if (!chatId) {
          const created = await createTripChat();
          chatId = created.id;
          expectedRevision = created.revision;
          setActiveChatId(chatId);
          setChatRevision(created.revision);
        }
        let queued = false;
        for (let attempt = 0; attempt < 3; attempt += 1) {
          try {
            if (messageUrls.length > 0) {
              await enqueueTripChatUrls({
                chatId,
                content: text,
                expectedRevision,
                urls: messageUrls
              });
            }
            if (images.length > 0) {
              await enqueueTripChatImages({
                chatId,
                content: text,
                expectedRevision,
                images
              });
            }
            queued = true;
            break;
          } catch (caught) {
            if (!(caught instanceof APIError) || caught.code !== "VERSION_CONFLICT" || attempt === 2) {
              throw caught;
            }
            const latest = await getTripChat(chatId);
            expectedRevision = latest.revision;
            applyTripChat(latest);
          }
        }
        if (!queued) throw new Error("Không thể thêm nguồn vào hàng chờ.");
        setImages([]);
        if (fileInputRef.current) fileInputRef.current.value = "";
        setTripChats(await listTripChats());
        window.dispatchEvent(new Event("vsf:url-job-enqueued"));
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : "Không thể thêm nguồn vào hàng chờ.";
        setError(message);
      } finally {
        setQueueingUrls(false);
      }
      return;
    }
    setLoading(true);
    setProcessingStartedAt(Date.now());
    setProcessingElapsed(0);
    setIntakeKind(URL_PATTERN.test(text) ? "url" : images.length > 0 ? "image" : "prompt");
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
          setActiveChatId(chatId);
          setChatRevision(created.revision);
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
              attachmentNames: images.map((image) => image.name)
            });
            setSelectedMapPlaceKey(null);
            setImages([]);
            if (fileInputRef.current) fileInputRef.current.value = "";
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
        images
      });
      setExploreResult(nextExploreResult);
      setWorkflowStage("planning");
      const generation = await createPlanFromExplorer({
        context: nextExploreResult.explorer,
        intakeId: nextExploreResult.intakeId,
        userId: nextExploreResult.userId,
        allowPlaceSuggestions: nextExploreResult.allowPlaceSuggestions
      });
      setPlan(generation.plan);
      setWorkflowStage("ready");
      setSelectedMapPlaceKey(null);
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: nextExploreResult.allowPlaceSuggestions
            ? `Explorer đã hiểu yêu cầu cho ${nextExploreResult.explorer.intent.destination}. Planner và Finder đã tạo lịch trình và có thể bổ sung địa điểm phù hợp.`
            : `Explorer đã hiểu yêu cầu cho ${nextExploreResult.explorer.intent.destination}. Lịch trình chỉ dùng địa điểm trích xuất từ URL hoặc ảnh; Planner và Finder không thêm địa điểm catalog.`
        }
      ]);
      setImages([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Có lỗi xảy ra.";
      setWorkflowStage("failed");
      setError(message);
      setMessages((current) => [...current, { id: Date.now() + 1, role: "assistant", text: message }]);
    } finally {
      setLoading(false);
      setProcessingStartedAt(null);
    }
  }

  async function importUrls() {
    const urls = extractMessageUrls(urlInput);
    if (urls.length === 0) {
      setError("Nhập ít nhất một URL bắt đầu bằng http:// hoặc https://.");
      setUrlImportNotice("");
      return;
    }
    if (urls.length > 20) {
      setError("Mỗi lần chỉ có thể thêm tối đa 20 URL.");
      setUrlImportNotice("");
      return;
    }

    setQueueingUrls(true);
    setError("");
    setUrlImportNotice("");
    const content = urls.length === 1
      ? "Tạo lịch trình từ URL đã nhập."
      : `Tạo lịch trình từ ${urls.length} URL đã nhập.`;

    try {
      if (!user) {
        enqueueGuestUrlJobs({ content, urls });
      } else {
        let chatId = activeChatId;
        let expectedRevision = chatRevision;
        if (!chatId) {
          const created = await createTripChat();
          chatId = created.id;
          expectedRevision = created.revision;
          setActiveChatId(chatId);
          setChatRevision(created.revision);
        }

        let queued = false;
        for (let attempt = 0; attempt < 3; attempt += 1) {
          try {
            await enqueueTripChatUrls({
              chatId,
              content,
              expectedRevision,
              urls
            });
            queued = true;
            break;
          } catch (caught) {
            if (!(caught instanceof APIError) || caught.code !== "VERSION_CONFLICT" || attempt === 2) {
              throw caught;
            }
            const latest = await getTripChat(chatId);
            expectedRevision = latest.revision;
            applyTripChat(latest);
          }
        }
        if (!queued) throw new Error("Không thể thêm URL vào hàng chờ.");
        setTripChats(await listTripChats());
        window.dispatchEvent(new Event("vsf:url-job-enqueued"));
      }

      setUrlInput("");
      setUrlImportNotice(`Đã thêm ${urls.length} URL vào hàng chờ xử lý.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không thể thêm URL vào hàng chờ.");
    } finally {
      setQueueingUrls(false);
    }
  }

  function addImages(nextImages: File[]) {
    if (nextImages.length === 0) return;

    const supportedImages = nextImages.filter((image) =>
      SUPPORTED_IMAGE_TYPES.has(image.type.toLowerCase())
    );

    if (supportedImages.length === 0) {
      setError("Ảnh phải có định dạng JPEG, PNG, WebP, HEIC hoặc HEIF.");
      return;
    }

    setImages((current) => [...current, ...supportedImages]);
    setError(
      supportedImages.length < nextImages.length
        ? "Một số tệp không phải định dạng ảnh được hỗ trợ nên đã bị bỏ qua."
        : ""
    );
  }

  function handleComposerPaste(event: React.ClipboardEvent<HTMLTextAreaElement>) {
    if (loading) return;

    const pastedUrls = extractMessageUrls(event.clipboardData.getData("text"));
    const pastedImages = Array.from(event.clipboardData.items)
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .flatMap((item) => {
        const image = item.getAsFile();
        return image ? [image] : [];
      });

    if (pastedImages.length === 0 && pastedUrls.length === 0) return;

    event.preventDefault();
    if (pastedImages.length > 0) addImages(pastedImages);
    if (pastedUrls.length > 0) {
      setUrlInput(pastedUrls.join("\n"));
      setSourcePanelOpen(true);
      setUrlImportNotice("");
      setError("URL đã được chuyển sang phần Nguồn tham khảo.");
    }
  }

  function resetWorkflow() {
    setPrompt("");
    setUrlInput("");
    setUrlImportNotice("");
    setSourcePanelOpen(false);
    setImages([]);
    setExploreResult(null);
    setPlan(null);
    setSelectedMapPlaceKey(null);
    setWorkflowStage("idle");
    setError("");
    setShowTripKickoff(true);
    setMessages([
      {
        id: Date.now(),
        role: "assistant",
        text: "Nhập yêu cầu chuyến đi bằng một tin nhắn. Ví dụ: Đà Nẵng 3 ngày, ăn ngon, cà phê, đi chậm."
      }
    ]);
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (user) {
      setActiveChatId(null);
      setChatRevision(0);
    }
  }

  async function openTripChat(chatId: string) {
    if (loading || chatId === activeChatId) return;
    setError("");
    try {
      applyTripChat(await getTripChat(chatId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không thể mở chuyến đi.");
    }
  }

  async function handleDeleteTripChat(chat: TripChatSummary) {
    if (loading || deletingChatId) return;
    if (!window.confirm(`Xóa toàn bộ lịch sử chat “${chat.title}”? Hành động này không thể hoàn tác.`)) {
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
      setError(caught instanceof Error ? caught.message : "Không thể xóa lịch sử chat.");
    } finally {
      setDeletingChatId(null);
    }
  }

  function applyTripChat(chat: TripChat) {
    setShowTripKickoff(false);
    setActiveChatId(chat.id);
    setChatRevision(chat.revision);
    setPlan(chat.currentPlan);
    setExploreResult(
      chat.currentExplorer
        ? {
            intakeId: chat.currentIntakeId ?? "",
            userId: user ? String(user.id) : null,
            explorer: chat.currentExplorer,
            allowPlaceSuggestions: true
          }
        : null
    );
    setMessages(
      chat.messages.length
        ? chat.messages.map((message) => ({
            id: message.id,
            role: message.role,
            text: [
              message.content,
              message.attachmentNames.length
                ? `📎 ${message.attachmentNames.length} ảnh`
                : ""
            ].filter(Boolean).join("\n")
          }))
        : [{
            id: `welcome-${chat.id}`,
            role: "assistant",
            text: "Hãy mô tả chuyến đi này. Những tin nhắn sau sẽ tiếp tục chỉnh sửa cùng một lịch trình."
          }]
    );
    setWorkflowStage(chat.currentPlan ? "ready" : "idle");
    setSelectedMapPlaceKey(null);
  }

  function handleComposerKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      if (!loading && !queueingUrls && (prompt.trim() || images.length > 0)) {
        void sendMessage();
      }
    }
  }

  return (
    <main className="plannerPage">
      <div className="plannerWorkspace pageWidth">
        {user && !historyCollapsed ? (
          <>
            <button
              aria-label="Đóng lịch sử chuyến đi"
              className="tripSidebarBackdrop"
              onClick={() => setHistoryCollapsed(true)}
              type="button"
            />
            <aside aria-label="Dự án chuyến đi" className="tripProjectSidebar">
            <div className="tripProjectSidebarHeader">
              <div className="tripProjectBrand">
                <PenguinMascot size={38} variant="logo" />
                <span>
                  <strong>VSF Planner</strong>
                  <small>Trip projects</small>
                </span>
              </div>
              <button
                aria-label="Đóng lịch sử chuyến đi"
                aria-expanded="true"
                className="tripSidebarToggle"
                onClick={() => setHistoryCollapsed(true)}
                title="Đóng sidebar"
                type="button"
              >
                <SidebarIcon collapsed={false} />
              </button>
            </div>

            <button
              className={`sidebarNewChat ${!activeChatId ? "active" : ""}`}
              disabled={loading}
              onClick={() => {
                resetWorkflow();
                setHistoryCollapsed(true);
              }}
              title="Chat mới"
              type="button"
            >
              <NewChatIcon />
              <span>Chat mới</span>
            </button>

            <div className="tripProjectList">
              <div className="tripProjectSectionTitle">
                <strong>Dự án</strong>
                <small>{tripChats.length}</small>
              </div>
              {tripChats.length ? (
                <nav aria-label="Lịch sử dự án chuyến đi">
                  {tripChats.map((chat) => (
                    <div
                      className={`tripProjectItem ${chat.id === activeChatId ? "active" : ""}`}
                      key={chat.id}
                    >
                      <button
                        aria-current={chat.id === activeChatId ? "page" : undefined}
                        className="tripProjectOpen"
                        disabled={loading || deletingChatId === chat.id}
                        onClick={() => {
                          setHistoryCollapsed(true);
                          void openTripChat(chat.id);
                        }}
                        title={chat.title}
                        type="button"
                      >
                        <ProjectIcon />
                        <span>
                          <strong>{chat.title}</strong>
                          <small>
                            {chat.destination || "Chưa chọn điểm đến"}
                            {chat.revision ? ` · Bản ${chat.revision}` : ""}
                          </small>
                        </span>
                      </button>
                      <button
                        aria-label={`Xóa lịch sử chat ${chat.title}`}
                        className="tripProjectDelete"
                        disabled={loading || deletingChatId !== null}
                        onClick={() => void handleDeleteTripChat(chat)}
                        title="Xóa lịch sử chat"
                        type="button"
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  ))}
                </nav>
              ) : (
                <p className="tripProjectEmpty">Chưa có dự án. Bắt đầu bằng một yêu cầu chuyến đi mới.</p>
              )}
            </div>
            </aside>
          </>
        ) : null}

        {!plannerEntryResolved ? (
          <div className="routeLoading">Đang mở chuyến đi gần nhất…</div>
        ) : showTripKickoff ? (
          <section aria-labelledby="trip-kickoff-title" className="plannerKickoffStage">
            <TripKickoffCard
              initialDestination={initialDestination}
              onContinue={(message) => {
                setShowTripKickoff(false);
                if (message) setPrompt(message);
              }}
              onSkip={() => setShowTripKickoff(false)}
            />
          </section>
        ) : (
        <section className="plannerLayout">
        <aside
          aria-busy={loading}
          aria-label="Trợ lý lập kế hoạch VSF"
          className={`plannerChat panel ${chatCollapsed ? "is-collapsed" : ""}`}
        >
          <div className="panelHeading">
            <div className="plannerChatTitle">
              <strong>Trợ lý VSF</strong>
              <small>
                {loading
                  ? "Đang xử lý yêu cầu…"
                  : workflowStage === "ready"
                    ? "Lịch trình sẵn sàng để chỉnh sửa"
                    : workflowStage === "failed"
                      ? "Cần bạn kiểm tra và thử lại"
                      : "Cùng bạn xây dựng chuyến đi"}
              </small>
            </div>
            <span className={`assistantStatus ${loading ? "working" : ""}`} aria-label={loading ? "Đang xử lý" : "Đang trực tuyến"} />
            <button
              aria-controls="planner-chat-content"
              aria-expanded={!chatCollapsed}
              aria-label={chatCollapsed ? "Mở trợ lý VSF" : "Thu gọn trợ lý VSF"}
              className="plannerChatToggle"
              onClick={() => setChatCollapsed((collapsed) => !collapsed)}
              title={chatCollapsed ? "Mở trợ lý" : "Thu gọn trợ lý"}
              type="button"
            >
              {chatCollapsed ? (
                <span className="chatLauncherArtwork">
                  <PenguinMascot className="chatTogglePenguin" size={84} variant="chatSpeaking" />
                  <svg aria-hidden="true" className="speechBubbleIcon" viewBox="0 0 24 24">
                    <path d="M5.25 4.75h13.5A2.25 2.25 0 0 1 21 7v8.5a2.25 2.25 0 0 1-2.25 2.25H11l-4.75 3v-3h-1A2.25 2.25 0 0 1 3 15.5V7a2.25 2.25 0 0 1 2.25-2.25Z" />
                    <circle cx="8" cy="11.25" r="1" />
                    <circle cx="12" cy="11.25" r="1" />
                    <circle cx="16" cy="11.25" r="1" />
                  </svg>
                </span>
              ) : (
                <svg aria-hidden="true" viewBox="0 0 24 24">
                  <path d="m7 7 10 10M17 7 7 17" />
                </svg>
              )}
            </button>
          </div>
          <div className="plannerChatContent" id="planner-chat-content">
          <div className="chatMessages" aria-live="polite" ref={messageListRef}>
            {messages.map((message) => (
              <div className={`chatMessageRow ${message.role}`} key={message.id}>
                {message.role === "assistant" ? (
                  <span className="chatMessageAvatar">
                    <PenguinMascot size={44} variant="hi" />
                  </span>
                ) : null}
                <div className={`chatBubble ${message.role}`}>{message.text}</div>
              </div>
            ))}
            {loading ? (
              <div className="chatMessageRow assistant">
                <span className="chatMessageAvatar">
                  <PenguinMascot size={44} variant="hi" />
                </span>
                <div className="chatBubble assistant processingMessage" role="status">
                  <div className="processingMessageTitle">
                    <span className="typingDots" aria-hidden="true"><i /><i /><i /></span>
                    <strong>
                      {processingActivity(workflowStage, intakeKind, processingElapsed)}
                    </strong>
                    <b className="processingElapsed">{elapsedLabel(processingElapsed)}</b>
                  </div>
                  <span>{processingDescription(workflowStage, intakeKind)}</span>
                  {workflowStage === "exploring" && intakeKind === "url" ? (
                    <small>Video dài hoặc nguồn phản hồi chậm có thể cần thêm thời gian.</small>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
          {!showTripKickoff && !exploreResult && messages.length === 1 ? (
            <div className="promptSuggestions" aria-label="Yêu cầu mẫu">
              {promptSuggestions.map((suggestion) => (
                <button key={suggestion} onClick={() => setPrompt(suggestion)} type="button">
                  {suggestion}
                </button>
              ))}
            </div>
          ) : null}
          {error ? <p className="formError">{error}</p> : null}
          {!showTripKickoff ? (
          <form className="chatComposer" onSubmit={(event) => { event.preventDefault(); void sendMessage(); }}>
            {sourcePanelOpen ? (
              <div className="urlImporter">
                <button
                  aria-label="Đóng phần nhập nguồn tham khảo"
                  className="urlImporterClose"
                  onClick={() => setSourcePanelOpen(false)}
                  type="button"
                >
                  ×
                </button>
                <label className="srOnly" htmlFor="planner-url-input">URL video hoặc bài viết</label>
                <div className="urlImporterRow">
                  <input
                    autoCapitalize="none"
                    autoComplete="url"
                    disabled={loading || queueingUrls}
                    id="planner-url-input"
                    inputMode="url"
                    onChange={(event) => {
                      setUrlInput(event.target.value);
                      setUrlImportNotice("");
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        if (!loading && !queueingUrls) void importUrls();
                      }
                    }}
                    placeholder="Dán URL TikTok, Reel hoặc bài viết…"
                    type="text"
                    value={urlInput}
                  />
                  <button
                    className="urlImportButton"
                    disabled={loading || queueingUrls || !urlInput.trim()}
                    onClick={() => void importUrls()}
                    type="button"
                  >
                    {queueingUrls ? "Đang thêm…" : "Nhập URL"}
                  </button>
                </div>
                {urlImportNotice ? <small className="urlImportNotice" role="status">{urlImportNotice}</small> : null}
              </div>
            ) : null}
            <div className="composerBox">
              <textarea
                aria-label="Tin nhắn lập lịch trình"
                disabled={loading}
                onKeyDown={handleComposerKeyDown}
                onChange={(event) => setPrompt(event.target.value)}
                onPaste={handleComposerPaste}
                placeholder={plan
                  ? "Ví dụ: Đổi buổi chiều ngày 2 sang hoạt động trong nhà…"
                  : "Mô tả điểm đến, số ngày, ngân sách và sở thích…"}
                rows={2}
                value={prompt}
              />
              <input
                accept="image/*"
                aria-label="Ảnh hoặc screenshot"
                className="composerFileInput"
                multiple
                onChange={(event) => {
                  addImages(Array.from(event.target.files ?? []));
                  event.target.value = "";
                }}
                ref={fileInputRef}
                type="file"
              />
              <div className="composerToolbar">
                <div className="composerSourceActions" aria-label="Thêm nguồn tham khảo">
                  <button
                    aria-expanded={sourcePanelOpen}
                    aria-label="Thêm URL video hoặc bài viết"
                    className={`sourceActionButton ${sourcePanelOpen ? "active" : ""}`}
                    onClick={() => setSourcePanelOpen((open) => !open)}
                    type="button"
                  >
                    <svg aria-hidden="true" viewBox="0 0 24 24">
                      <path d="M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1" />
                      <path d="M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1.1-1.1" />
                    </svg>
                    <span>URL</span>
                  </button>
                  <button
                    aria-label="Đính kèm ảnh để đọc nội dung"
                    className="sourceActionButton"
                    onClick={() => fileInputRef.current?.click()}
                    type="button"
                  >
                    <svg aria-hidden="true" viewBox="0 0 24 24">
                      <rect height="16" rx="3" width="18" x="3" y="4" />
                      <circle cx="9" cy="10" r="2" />
                      <path d="m5 18 4.5-4.5 3 3 2-2L19 19" />
                    </svg>
                    <span>Ảnh</span>
                  </button>
                </div>
                {images.length ? (
                  <span className="attachmentChip">
                    {images.length} ảnh · OCR
                    <button
                      aria-label="Bỏ ảnh đã chọn"
                      onClick={() => {
                        setImages([]);
                        if (fileInputRef.current) fileInputRef.current.value = "";
                      }}
                      type="button"
                    >
                      ×
                    </button>
                  </span>
                ) : null}
                {!images.length ? <small className="composerHint">Thêm nguồn nếu bạn có</small> : null}
                <button
                  aria-label={loading ? "Đang xử lý yêu cầu" : queueingUrls ? "Đang thêm URL vào hàng chờ" : "Gửi yêu cầu"}
                  className="sendButton"
                  disabled={loading || queueingUrls || (!prompt.trim() && images.length === 0)}
                  type="submit"
                >
                  <svg aria-hidden="true" viewBox="0 0 24 24">
                    <path d="M12 20V5" />
                    <path d="m5.5 11.5 6.5-6.5 6.5 6.5" />
                  </svg>
                </button>
              </div>
            </div>
          </form>
          ) : null}
          </div>
        </aside>

        <section className="itinerary panel">
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
              <strong>Kế hoạch chi tiết</strong>
              {loading || displayedPlan ? (
                <small>
                  {loading
                    ? "Đang chuẩn bị lịch trình của bạn…"
                    : displayedExploreResult
                      ? `${displayedExploreResult.explorer.intent.destination} · ${displayedPlan?.days.length} ngày`
                      : `${displayedPlan?.days.length} ngày · Lịch trình theo từng điểm đến`}
                </small>
              ) : null}
            </div>
            {user ? (
              <button
                aria-expanded={!historyCollapsed}
                aria-label="Mở lịch sử chuyến đi"
                className="plannerSidebarLauncher"
                onClick={() => setHistoryCollapsed(false)}
                title="Mở sidebar"
                type="button"
              >
                <MenuIcon />
              </button>
            ) : null}
            <button
              type="button"
              data-testid="supervisor-toggle"
              data-supervisor-enabled={supervisorToggle ? "true" : "false"}
              className={`supervisorToggle ${supervisorToggle ? "on" : "off"}`}
              aria-pressed={supervisorToggle}
              aria-label={
                supervisorToggle
                  ? "Tắt supervisor (roll back về luồng cũ)"
                  : "Bật supervisor (luồng mới có confirm)"
              }
              onClick={toggleSupervisor}
              title={
                supervisorToggle
                  ? "Supervisor đang bật — click để tắt khi cần rollback"
                  : "Supervisor đang tắt — click để bật lại"
              }
            >
              <span className="supervisorToggleDot" aria-hidden="true" />
              Supervisor {supervisorToggle ? "ON" : "OFF"}
            </button>
          </header>
          {displayedPlan && displayedExploreResult ? (
            <div className="exploreResult">
              <section className="tripSummaryCard">
                <div className="tripSummaryIntro">
                  <span className="destinationPin" aria-hidden="true">⌖</span>
                  <div>
                    <span className="tripSummaryLabel">Điểm đến của bạn</span>
                    <h3>{displayedExploreResult.explorer.intent.destination}</h3>
                    <p>{displayedExploreResult.explorer.intent.travelStyle} · Nhịp độ {paceLabel(displayedExploreResult.explorer.intent.pace)}</p>
                  </div>
                </div>
                <div className="tripQuickFacts" aria-label="Thông tin chuyến đi">
                  <div><span>Ngày có lịch trình</span><strong>{displayedPlan.days.length} ngày</strong></div>
                  <div><span>Nhóm đi</span><strong>{displayedExploreResult.explorer.tripSpec.partySize} người</strong></div>
                  <div><span>Mức ngân sách</span><strong>{budgetLevelLabel(displayedExploreResult.explorer.tripSpec.budget.level)}</strong></div>
                </div>
                <div className="budgetSummary">
                  <span className="budgetIcon" aria-hidden="true">₫</span>
                  <div><span>Mức chi dự kiến</span><strong>{formatBudget(displayedExploreResult.explorer)}</strong></div>
                </div>
                {displayedExploreResult.explorer.intent.interests.length ? (
                  <div className="interestGroup">
                    <span className="sectionMicroTitle">Bạn muốn trải nghiệm</span>
                    <div className="tagRow">
                      {displayedExploreResult.explorer.intent.interests.map((interest) => <span key={interest}>{interest}</span>)}
                    </div>
                  </div>
                ) : null}
              </section>

              <section className="tripPlanSection">
                <div
                  aria-label="Chọn ngày trong lịch trình"
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
                      displayedExploreResult.explorer.tripSpec.startDate,
                      day.day
                    );
                    const color = planDayColors.get(dateKey) ?? "#365f5a";
                    const isActive = day.day === activePlanDay;
                    const shortDate = shortDateLabelForTripDay(
                      displayedExploreResult.explorer.tripSpec.startDate,
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
                          <span className="dayTabDot" aria-hidden="true" />
                          Ngày {day.day}
                        </span>
                        {shortDate ? <small>{shortDate}</small> : null}
                      </button>
                    );
                  })}
                </div>
                <div
                  aria-labelledby={
                    activePlanDay == null
                      ? "plan-day-tab-all"
                      : `plan-day-tab-${activePlanDay}`
                  }
                  className="planDayPanels"
                  id="plan-days-panel"
                  role="tabpanel"
                >
                  {displayedPlanDays.map((displayedPlanDay) => (
                    <article
                      className="explorerDayCard"
                      key={displayedPlanDay.day}
                      style={{
                        "--day-color": planDayColors.get(
                          dateKeyForTripDay(
                            displayedExploreResult.explorer.tripSpec.startDate,
                            displayedPlanDay.day
                          )
                        ) ?? "#365f5a"
                      } as CSSProperties}
                    >
                      {activePlanDay === displayedPlanDay.day ? (
                        <div
                          className={`dayNavigationStart ${navigationOrigin ? "isSelected" : "isPending"}`}
                        >
                          <div className="dayNavigationStartHeader">
                            <span className="dayNavigationStartEyebrow">
                              Điểm bắt đầu · Ngày {displayedPlanDay.day}
                            </span>
                            {navigationOrigin?.detail ? (
                              <small>{navigationOrigin.detail}</small>
                            ) : !navigationOrigin ? (
                              <small>
                                {locationStatus === "locating"
                                  ? "Đang xin quyền và xác định vị trí của bạn…"
                                  : "Dùng vị trí hiện tại hoặc tìm một địa điểm khác"}
                              </small>
                            ) : null}
                          </div>
                          <div className="dayNavigationStartSearch">
                            <div
                              className={`dayNavigationStartField ${startPointMode === "current" ? "isCurrent" : "isSearch"}`}
                            >
                              <span className="dayNavigationStartFieldIcon" aria-hidden="true">
                                {startPointMode === "current" ? "◎" : "⌕"}
                              </span>
                              <input
                                aria-autocomplete="list"
                                aria-controls={`start-point-suggestions-${displayedPlanDay.day}`}
                                aria-expanded={startPointSuggestions.length > 0}
                                aria-label="Tìm điểm bắt đầu"
                                autoComplete="off"
                                id={`start-point-search-${displayedPlanDay.day}`}
                                onChange={(event) => updateStartPointQuery(event.target.value)}
                                onFocus={(event) => {
                                  setStartPointSearchOpen(true);
                                  if (startPointMode === "current") event.currentTarget.select();
                                }}
                                placeholder={
                                  locationStatus === "locating"
                                    ? "Đang xác định vị trí hiện tại…"
                                    : "Tìm khách sạn, ga tàu, sân bay…"
                                }
                                role="combobox"
                                type="search"
                                value={
                                  startPointMode === "current" && currentLocation
                                    ? "Vị trí hiện tại"
                                    : startPointQuery
                                }
                              />
                              {searchingStartPoint ? (
                                <span
                                  aria-label="Đang tìm địa điểm"
                                  className="dayNavigationStartSpinner"
                                  role="status"
                                />
                              ) : null}
                              <button
                                aria-label="Dùng vị trí hiện tại"
                                className="dayNavigationUseCurrentButton"
                                disabled={locationStatus === "locating"}
                                onClick={chooseCurrentStartPoint}
                                title="Dùng vị trí hiện tại"
                                type="button"
                              >
                                <span aria-hidden="true">⌖</span>
                              </button>
                            </div>
                            {startPointSearchOpen ? (
                              <>
                              {startPointSuggestions.length > 0 ? (
                                <div
                                  className="dayNavigationStartSuggestions"
                                  id={`start-point-suggestions-${displayedPlanDay.day}`}
                                  role="listbox"
                                >
                                  {startPointSuggestions.map((suggestion, suggestionIndex) => (
                                    <button
                                      key={suggestion.placeId || `${suggestion.name}-${suggestionIndex}`}
                                      onClick={() => chooseSearchedStartPoint(suggestion)}
                                      role="option"
                                      type="button"
                                    >
                                      <strong>{suggestion.name}</strong>
                                      {suggestion.address ? <small>{suggestion.address}</small> : null}
                                    </button>
                                  ))}
                                </div>
                              ) : null}
                              {!searchingStartPoint &&
                              startPointSearchCompleted &&
                              startPointSuggestions.length === 0 ? (
                                <small role={startPointSearchFailed ? "alert" : "status"}>
                                  {startPointSearchFailed
                                    ? "Không thể tải dữ liệu địa điểm. Vui lòng thử lại."
                                    : "Không tìm thấy địa điểm phù hợp."}
                                </small>
                              ) : null}
                              </>
                            ) : null}
                            {locationStatus === "error" && locationError ? (
                              <small role="alert">
                                {locationError} Bạn vẫn có thể tìm địa điểm khác.
                              </small>
                            ) : null}
                          </div>
                        </div>
                      ) : null}
                      {directionsActive &&
                      activePlanDay === displayedPlanDay.day &&
                      dayDirectionLegs.length > 0 ? (
                        <div
                          aria-label={`Chỉ đường từ ${navigationOrigin?.label ?? "điểm bắt đầu"} đến ${activeNavigationDestination?.name ?? "địa điểm đầu tiên"}`}
                          className="dayNavigationChoices dayNavigationChoices--firstLeg"
                        >
                          {dayDirectionLegs.slice(0, 1).map((leg, legIndex) => {
                            const options = transportOptionsForLeg(leg);
                            const selected = selectedTransportOption(
                              leg,
                              selectedDirectionModes[legIndex]
                            );
                            const directionRouteKey = isDrawableTransportRoute(selected)
                              ? `day-directions-${displayedPlanDay.day}-${legIndex}-${selected.mode}`
                              : null;
                            return (
                              <details
                                className={`dayNavigationLeg ${selectedMapRouteKey === directionRouteKey ? "is-map-route-selected" : ""}`}
                                data-map-route-key={directionRouteKey ?? undefined}
                                key={`${leg.fromPlace}-${leg.toPlace}-${legIndex}`}
                                onClick={directionRouteKey
                                  ? (event) => {
                                      if (!(event.target as Element).closest("summary")) return;
                                      selectRouteFromItinerary(directionRouteKey);
                                    }
                                  : undefined}
                              >
                                <summary>
                                  <span className="itineraryRouteIcon" aria-hidden="true">
                                    <TransportModeIcon mode={selected.mode} />
                                  </span>
                                  <span>
                                    <b>{leg.fromPlace}</b>
                                    {" → "}
                                    <b>{leg.toPlace}</b>
                                  </span>
                                  <small>
                                    {transportModeLabel(selected.mode)}
                                    {" · "}
                                    {selected.estimatedDurationMinutes} phút
                                  </small>
                                  <ChevronDownIcon />
                                </summary>
                                <div className="itineraryRouteAlternatives">
                                  {options.map((option, optionIndex) => (
                                    <TransportOptionCard
                                      fromPlace={leg.fromPlace}
                                      key={`${option.mode}-${option.source}-${optionIndex}`}
                                      onSelect={() =>
                                        chooseDirectionOption(
                                          legIndex,
                                          option.mode
                                        )
                                      }
                                      option={option}
                                      primary={optionIndex === 0}
                                      selected={
                                        selected.mode === option.mode
                                      }
                                      toPlace={leg.toPlace}
                                    />
                                  ))}
                                </div>
                              </details>
                            );
                          })}
                        </div>
                      ) : null}
                      <div className="itineraryStops">
                        {reorderingDay === displayedPlanDay.day ? (
                          <p className="itineraryReorderStatus" role="status">
                            Đang lưu thứ tự và cập nhật tuyến đường…
                          </p>
                        ) : null}
                        {displayedPlanDay.items.map((item, itemIndex) => {
                          const displayNotes = formatPlanNote(item.notes);
                          const sourceActivityNote = formatPlanNote(item.sourceActivity);
                          const personalNotes = formatPlanNote(item.personalNotes);
                          const hasUrlEvidence = (item.sourceRefs ?? []).some(
                            (sourceRef) => sourceRef.startsWith("http://")
                              || sourceRef.startsWith("https://")
                          );
                          const additionalContextNote = (
                            displayNotes
                            && !hasUrlEvidence
                            && !sourceActivityNote
                          ) ? displayNotes : null;
                          const activityNoteCount = [
                            sourceActivityNote,
                            additionalContextNote,
                            personalNotes
                          ].filter(Boolean).length;
                          const notePanelId = `activity-note-${displayedPlanDay.day}-${itemIndex}`;
                          const isNoteEditorOpen = Boolean(
                            noteEditor
                            && noteEditor.day === displayedPlanDay.day
                            && noteEditor.itemId === (item.itemId ?? null)
                            && noteEditor.itemName === item.name
                          );
                          const mapKey = hasPlanItemCoordinates(item)
                            ? planItemMapKey(displayedPlanDay.day, itemIndex, item.name)
                            : null;
                          const transportLeg = transportLegAfterItem(displayedPlanDay, item, itemIndex);
                          const transportLegIndex = transportLeg
                            ? displayedPlanDay.transportLegs.indexOf(
                                transportLeg
                              )
                            : -1;
                          const selectedTransportLeg =
                            transportLeg && transportLegIndex >= 0
                              ? selectedTransportOption(
                                  transportLeg,
                                  selectedPlanLegModes[
                                    planLegSelectionKey(
                                      displayedPlanDay.day,
                                      transportLegIndex
                                    )
                                  ]
                                )
                              : null;
                          const routeMapKey =
                            selectedTransportLeg && transportLegIndex >= 0 &&
                            isDrawableTransportRoute(selectedTransportLeg)
                              ? `day-${displayedPlanDay.day}-leg-${transportLegIndex}-${selectedTransportLeg.mode}`
                              : null;
                          const transportLegOptions = transportLeg
                            ? transportOptionsForLeg(transportLeg)
                            : [];
                          const timelineCategory = item.timelineCategory ?? "activity";
                          const isNonActivity = (
                            timelineCategory === "break"
                            || item.placeType === "break"
                            || item.placeType === "free_time"
                          );
                          const isFoodStop = timelineCategory === "food" || [
                            item.placeType,
                            ...(item.tags ?? [])
                          ].some((value) => {
                            const category = categoryFromPlaceType(value);
                            return category === "food" || category === "cafe";
                          });
                          const sourceLabel = itinerarySourceLabel(
                            item.sourceRefs ?? [],
                            item.sourceProvider,
                            item.source
                          );
                          const canReorder = Boolean(item.itemId && activeChatId && !mutatingItem);
                          const placeImageUrl = item.imageUrls?.find(isDisplayableImageUrl) ?? null;
                          const isDragging = draggedItemKey?.itemId === item.itemId;
                          const isDragTarget = dragOverItemId === item.itemId && !isDragging;
                          const itemActions = item.itemId && activeChatId ? (
                            <div
                              className={`itineraryActions itineraryActions--cardTop ${placeImageUrl ? "itineraryActions--imageOverlay" : ""}`}
                            >
                              <button
                                aria-label={`Kéo ${item.name} để đổi vị trí. Dùng phím mũi tên lên hoặc xuống để di chuyển.`}
                                className="itineraryDragHandle"
                                draggable={canReorder}
                                onKeyDown={(event) => {
                                  if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
                                  event.preventDefault();
                                  handleMoveItemOrder(
                                    displayedPlanDay.day,
                                    itemIndex,
                                    event.key === "ArrowUp" ? "up" : "down"
                                  );
                                }}
                                title="Kéo để đổi vị trí"
                                type="button"
                              >
                                <svg viewBox="0 0 24 24"><circle cx="9" cy="7" r="1.25"/><circle cx="15" cy="7" r="1.25"/><circle cx="9" cy="12" r="1.25"/><circle cx="15" cy="12" r="1.25"/><circle cx="9" cy="17" r="1.25"/><circle cx="15" cy="17" r="1.25"/></svg>
                              </button>
                              <button
                                aria-label={`Sửa ${item.name}`}
                                className="itineraryActionButton"
                                onClick={() => {
                                  openItemEditor(
                                    displayedPlanDay.day,
                                    item,
                                    personalNotes
                                  );
                                }}
                                title="Sửa địa điểm"
                                type="button"
                              >
                                <svg viewBox="0 0 24 24"><path d="M13.5 6.5 17.5 10.5M4 20l4.2-1 10.9-10.9a2.8 2.8 0 0 0-4-4L4.2 15 4 20Z"/></svg>
                              </button>
                              <button
                                aria-label={`Xóa ${item.name}`}
                                className="itineraryActionButton danger"
                                onClick={() => handleDeleteItem(displayedPlanDay.day, item.itemId!)}
                                title="Xóa địa điểm"
                                type="button"
                              >
                                <svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M18 7l-1 13H7L6 7M10 11v5M14 11v5"/></svg>
                              </button>
                            </div>
                          ) : null;
                          return (
                            <Fragment key={item.itemId ?? `${displayedPlanDay.day}-${itemIndex}`}>
                              <div
                                className={`itineraryItemDragWrapper ${isDragging ? "dragging" : ""} ${isDragTarget ? "dragTarget" : ""}`}
                                draggable={canReorder}
                                onDragEnd={() => {
                                  setDraggedItemKey(null);
                                  setDragOverItemId(null);
                                }}
                                onDragEnter={() => {
                                  if (draggedItemKey && draggedItemKey.itemId !== item.itemId) {
                                    setDragOverItemId(item.itemId ?? null);
                                  }
                                }}
                                onDragOver={(event) => {
                                  if (canReorder) event.preventDefault();
                                }}
                                onDragStart={(event) => {
                                  if (!item.itemId) return;
                                  event.dataTransfer.effectAllowed = "move";
                                  event.dataTransfer.setData("text/plain", item.itemId);
                                  setDraggedItemKey({ day: displayedPlanDay.day, itemId: item.itemId });
                                }}
                                onDrop={(event) => {
                                  event.preventDefault();
                                  const draggedItemId = draggedItemKey?.itemId
                                    ?? event.dataTransfer.getData("text/plain");
                                  if (
                                    draggedItemId
                                    && draggedItemKey?.day === displayedPlanDay.day
                                    && draggedItemId !== item.itemId
                                  ) {
                                    const allItems = displayedPlanDay.items;
                                    const fromIndex = allItems.findIndex(
                                      (candidate) => candidate.itemId === draggedItemId
                                    );
                                    if (fromIndex !== -1) {
                                      const reorderedItems = [...allItems];
                                      const [movedItem] = reorderedItems.splice(fromIndex, 1);
                                      reorderedItems.splice(itemIndex, 0, movedItem);
                                      const newOrderedItemIds = reorderedItems
                                        .map((candidate) => candidate.itemId)
                                        .filter((id): id is string => Boolean(id));
                                      void handleReorderItems(displayedPlanDay.day, newOrderedItemIds);
                                    }
                                  }
                                  setDraggedItemKey(null);
                                  setDragOverItemId(null);
                                }}
                              >
                              {isNonActivity ? (
                                <div className="itineraryBreakCard">
                                  <div className="itineraryBreakContent">
                                    <strong>{item.name}</strong>
                                    {displayNotes ? <p>{displayNotes}</p> : null}
                                  </div>
                                  {canReorder ? (
                                    <button
                                      aria-label={`Kéo ${item.name} để đổi vị trí. Dùng phím mũi tên lên hoặc xuống để di chuyển.`}
                                      className="itineraryDragHandle"
                                      draggable
                                      onKeyDown={(event) => {
                                        if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
                                        event.preventDefault();
                                        handleMoveItemOrder(
                                          displayedPlanDay.day,
                                          itemIndex,
                                          event.key === "ArrowUp" ? "up" : "down"
                                        );
                                      }}
                                      title="Kéo để đổi vị trí"
                                      type="button"
                                    >
                                      <svg viewBox="0 0 24 24"><circle cx="8" cy="7" r="1"/><circle cx="16" cy="7" r="1"/><circle cx="8" cy="12" r="1"/><circle cx="16" cy="12" r="1"/><circle cx="8" cy="17" r="1"/><circle cx="16" cy="17" r="1"/></svg>
                                    </button>
                                  ) : null}
                                </div>
                              ) : (
                                <article
                                  className={`itineraryStop ${isFoodStop ? "itineraryStop--food" : "itineraryStop--activity"} ${transportLeg ? "hasRoute" : ""} ${selectedMapRoute && (selectedMapRoute.fromPlace === item.name || selectedMapRoute.toPlace === item.name) ? "is-map-route-endpoint" : ""}`}
                                >
                                  <span
                                    className="itineraryStopPin"
                                    aria-hidden="true"
                                  />
                                  <div
                                    className={`itineraryPlaceCard ${placeImageUrl ? "itineraryPlaceCard--withImage" : ""}`}
                                  >
                                    {placeImageUrl ? (
                                      <div className="itineraryPlaceMedia">
                                        {itemActions}
                                        <div className="itineraryPlaceImage">
                                          <img
                                            alt={`Ảnh ${item.name}`}
                                            draggable={false}
                                            loading="lazy"
                                            src={placeImageUrl}
                                          />
                                        </div>
                                      </div>
                                    ) : null}
                                    <div className="itineraryPlaceContent">
                                    {!placeImageUrl ? itemActions : null}
                                    <header>
                                      <div className="itineraryPlaceMain">
                                        <div className="itineraryPlaceTitle">
                                          {mapKey ? (
                                            <button
                                              className="placeMapButton"
                                              onClick={() => {
                                                setSelectedMapPlaceKey(mapKey);
                                                window.requestAnimationFrame(() => {
                                                  document.querySelector(".plannerMap")?.scrollIntoView({
                                                    behavior: "smooth",
                                                    block: "nearest"
                                                  });
                                                });
                                              }}
                                              aria-label={`Hiển thị ${item.name} trên bản đồ`}
                                              type="button"
                                            >
                                              <strong>{item.name}</strong>
                                            </button>
                                          ) : <strong>{item.name}</strong>}
                                        </div>
                                      </div>
                                      <span
                                        aria-label={isFoodStop ? "Ăn uống" : "Hoạt động tham quan"}
                                        className="itineraryTypeIcon"
                                        role="img"
                                        title={isFoodStop ? "Ăn uống" : "Hoạt động tham quan"}
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
                                    </header>
                                    {sourceLabel ? (
                                      <div className="itineraryPlaceTags">
                                        <span
                                          className={`itinerarySourceTag itinerarySourceTag--${sourceLabel.kind}`}
                                        >
                                          {sourceLabel.url ? (
                                            <>
                                              <a
                                                href={sourceLabel.url}
                                                rel="noreferrer"
                                                target="_blank"
                                                title={sourceLabel.url}
                                              >
                                                {sourceLabel.text}
                                              </a>
                                              {sourceLabel.providerSuffix}
                                            </>
                                          ) : sourceLabel.text}
                                        </span>
                                      </div>
                                    ) : null}
                                    {item.rating != null ? (
                                      <div className="itineraryPlaceRating" aria-label={`Đánh giá ${item.rating} trên 5`}>
                                        <span aria-hidden="true">★</span>
                                        <strong>{item.rating.toFixed(1)}</strong>
                                        {item.reviewCount != null && item.reviewCount > 0 ? (
                                          <small>{formatCompactCount(item.reviewCount)} lượt đánh giá</small>
                                        ) : null}
                                      </div>
                                    ) : null}
                                    {typeof item.latitude === "number" &&
                                    typeof item.longitude === "number" ? (
                                      <button
                                        className="itineraryNavigateButton"
                                        onClick={() => {
                                          const destination = activeDayDirectionStops.find(
                                            (stop) => stop.mapKey === mapKey
                                          );
                                          if (destination) startDayDirections(destination);
                                        }}
                                        type="button"
                                      >
                                        <svg aria-hidden="true" viewBox="0 0 24 24">
                                          <path d="m12 3 9 9-9 9-9-9 9-9Z" />
                                          <path d="M8 12h7M13 9l3 3-3 3" />
                                        </svg>
                                        Chỉ đường đến đây
                                      </button>
                                    ) : null}
                                    {activityNoteCount || (item.itemId && activeChatId) ? (
                                      <div className={`activityNotesDropdown ${isNoteEditorOpen ? "isOpen" : ""}`}>
                                        <button
                                          aria-controls={notePanelId}
                                          aria-expanded={isNoteEditorOpen}
                                          className="activityNotesTrigger"
                                          onClick={() => setNoteEditor(isNoteEditorOpen ? null : {
                                            day: displayedPlanDay.day,
                                            itemId: item.itemId ?? null,
                                            itemName: item.name,
                                            sourceNote: sourceActivityNote,
                                            additionalContext: additionalContextNote,
                                            personalNotes: personalNotes ?? ""
                                          })}
                                          type="button"
                                        >
                                          <span className="activityNotesTitle">
                                            <span className="activityNotesIcon" aria-hidden="true">
                                              <svg viewBox="0 0 24 24">
                                                <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z" />
                                                <path d="M14 3v6h6M8 13h8M8 17h5" />
                                              </svg>
                                            </span>
                                            {activityNoteCount ? "Ghi chú hoạt động" : "Thêm ghi chú"}
                                          </span>
                                          <span className="activityNotesCount">
                                            {activityNoteCount ? `${activityNoteCount} mục` : null}
                                          </span>
                                          <svg className="activityNotesChevron" aria-hidden="true" viewBox="0 0 24 24">
                                            <path d="m9 18 6-6-6-6" />
                                          </svg>
                                        </button>
                                        {isNoteEditorOpen && noteEditor ? (
                                          <form
                                            className="activityNotesInlinePanel"
                                            id={notePanelId}
                                            onSubmit={(event) => {
                                              if (!noteEditor.itemId) {
                                                event.preventDefault();
                                                setNoteEditor(null);
                                                return;
                                              }
                                              void handleSavePersonalNotes(event, noteEditor.day, noteEditor.itemId);
                                            }}
                                          >
                                            {noteEditor.sourceNote || noteEditor.additionalContext ? (
                                              <div className="activityNotesReferences">
                                                {noteEditor.sourceNote ? (
                                                  <section>
                                                    <strong>Từ nguồn tham khảo</strong>
                                                    <p>{noteEditor.sourceNote}</p>
                                                  </section>
                                                ) : null}
                                                {noteEditor.additionalContext ? (
                                                  <section>
                                                    <strong>Thông tin bổ sung</strong>
                                                    <p>{noteEditor.additionalContext}</p>
                                                  </section>
                                                ) : null}
                                              </div>
                                            ) : null}
                                            <label htmlFor={`${notePanelId}-personal`}>Ghi chú của bạn</label>
                                            <textarea
                                              autoFocus
                                              id={`${notePanelId}-personal`}
                                              name="personalNotes"
                                              onChange={(event) => setNoteEditor({
                                                ...noteEditor,
                                                personalNotes: event.target.value
                                              })}
                                              placeholder="Viết ghi chú cho hoạt động này…"
                                              readOnly={!noteEditor.itemId || !activeChatId}
                                              rows={4}
                                              value={noteEditor.personalNotes}
                                            />
                                            {noteEditor.itemId && activeChatId ? (
                                              <div className="activityNotesInlineActions">
                                                <span>Nhấn Esc để đóng</span>
                                                <button disabled={mutatingItem} type="submit">
                                                  {mutatingItem ? "Đang lưu…" : "Lưu ghi chú"}
                                                </button>
                                              </div>
                                            ) : null}
                                          </form>
                                        ) : null}
                                      </div>
                                    ) : null}
                                    </div>
                                  </div>
                                </article>
                              )}
                              </div>
                              {transportLeg && transportLegOptions.length > 0 ? (
                                <div
                                  className={`itineraryRoute ${routeMapKey ? "has-map-route-link" : ""} ${routeMapKey && selectedMapRouteKey === routeMapKey ? "is-map-route-selected" : ""}`}
                                  aria-label={`${transportModeLabel(selectedTransportLeg?.mode ?? transportLeg.mode)}, từ ${transportLeg.fromPlace} đến ${transportLeg.toPlace}, khoảng ${selectedTransportLeg?.estimatedDurationMinutes ?? transportLeg.estimatedDurationMinutes} phút`}
                                  data-map-route-key={routeMapKey ?? undefined}
                                  role="group"
                                >
                                  {routeMapKey ? (
                                    <button
                                      aria-pressed={selectedMapRouteKey === routeMapKey}
                                      className="itineraryRouteLink"
                                      onClick={() => selectRouteFromItinerary(routeMapKey)}
                                      type="button"
                                    >
                                      <span className="itineraryRouteIcon" aria-hidden="true">
                                        <TransportModeIcon mode={selectedTransportLeg?.mode ?? transportLeg.mode} />
                                      </span>
                                      <span className="itineraryRouteCopy">
                                        <strong>{transportLeg.fromPlace} → {transportLeg.toPlace}</strong>
                                        <small>
                                          {selectedTransportLeg?.estimatedDurationMinutes ?? transportLeg.estimatedDurationMinutes} phút
                                          {" · "}{formatDistance(selectedTransportLeg?.distanceMeters ?? transportLeg.distanceMeters)}
                                        </small>
                                      </span>
                                    </button>
                                  ) : (
                                    <>
                                      <span className="itineraryRouteIcon" aria-hidden="true">
                                        <TransportModeIcon mode={selectedTransportLeg?.mode ?? transportLeg.mode} />
                                      </span>
                                      <span>
                                        {selectedTransportLeg?.estimatedDurationMinutes ?? transportLeg.estimatedDurationMinutes} phút
                                        {" · "}{formatDistance(selectedTransportLeg?.distanceMeters ?? transportLeg.distanceMeters)}
                                      </span>
                                    </>
                                  )}
                                  {transportLegOptions.length > 1 ? (
                                    <details className="itineraryRouteDetails">
                                      <summary>
                                        Các lựa chọn
                                        <ChevronDownIcon />
                                      </summary>
                                      <div className="itineraryRouteAlternatives">
                                        {transportLegOptions.map((option, optionIndex) => (
                                          <TransportOptionCard
                                            fromPlace={transportLeg.fromPlace}
                                            key={`${option.mode}-${option.source}-${optionIndex}`}
                                            onSelect={
                                              transportLegIndex >= 0
                                                ? () =>
                                                    choosePlanTransportOption(
                                                      displayedPlanDay.day,
                                                      transportLegIndex,
                                                      option.mode
                                                    )
                                                : undefined
                                            }
                                            option={option}
                                            primary={optionIndex === 0}
                                            selected={
                                              selectedTransportLeg?.mode ===
                                              option.mode
                                            }
                                            toPlace={transportLeg.toPlace}
                                          />
                                        ))}
                                      </div>
                                    </details>
                                  ) : null}
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
                            setAddNotes("");
                            setSelectedSuggestion(null);
                            setPlaceSuggestions([]);
                            setAddSearchCompleted(false);
                            setAddSearchFailed(false);
                          }}
                          type="button"
                        >
                          <svg viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                          Thêm địa điểm cho Ngày {displayedPlanDay.day}
                        </button>
                      ) : null}
                    </article>
                  ))}
                </div>
              </section>
            </div>

          ) : (
            <div
              aria-label={loading ? "Đang tạo lịch trình" : "Chưa có lịch trình"}
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

        <PlannerMap
          currentLocation={navigationOrigin}
          dayColorKeys={planDayColorKeys}
          directionsActive={directionsActive}
          directionsBusy={directionsStatus === "routing"}
          directionsDay={activePlanDay}
          directionsEnabled={activeDayDirectionStops.length > 0}
          directionsSearchOpen={directionsSearchOpen}
          destinationOptions={directionDestinationOptions}
          destinationQuery={destinationQuery}
          destinationSearchBusy={searchingDestination}
          destinationSuggestions={directionDestinationSuggestions}
          locationFocusRequest={locationFocusRequest}
          mapDestinationPickActive={mapDestinationPickActive}
          onChooseDestination={chooseDirectionDestination}
          onChooseMapDestination={chooseDirectionDestination}
          onCancelDirections={clearDayDirections}
          onChooseOrigin={chooseDirectionOrigin}
          onCloseDirectionsSearch={closeDirectionsSearch}
          onDestinationQueryChange={updateDirectionDestinationQuery}
          routeFocusRequest={routeFocusRequest}
          locationBusy={
            locationStatus === "locating"
          }
          locationMessage={locationMessage}
          onLocate={recenterCurrentPosition}
          onOriginQueryChange={updateStartPointQuery}
          onStartDirections={openDirectionsSearch}
          onSubmitDirections={submitDirectionSearch}
          onToggleMapDestinationPick={() =>
            setMapDestinationPickActive((current) => !current)
          }
          onUseCurrentOrigin={chooseCurrentStartPoint}
          onViewDayRoute={viewDayRoute}
          originQuery={
            startPointMode === "current" && currentLocation
              ? "Vị trí hiện tại"
              : startPointQuery
          }
          originSearchBusy={searchingStartPoint}
          originSuggestions={directionOriginSuggestions}
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
                  kind: selectedNavigationDestination.mapKey ? "plan" : "searched"
                }
              : null
          }
          selectedKey={selectedMapPlaceKey}
          selectedRouteKey={selectedMapRouteKey}
        />
        </section>
        )}
      </div>

      {editingItem ? (
        <div
          aria-labelledby="edit-place-title"
          aria-modal="true"
          className="itineraryMutationModal"
          onClick={() => setEditingItem(null)}
          role="dialog"
        >
          <form
            className="itineraryMutationForm editPlaceNotesWindow"
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
                <span className="editPlaceSearchLabel">Tìm và chọn địa điểm</span>
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
                    setEditingItem({ ...editingItem, name: e.target.value });
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
                      event.currentTarget.parentElement?.querySelector("input")?.focus();
                    }}
                    type="button"
                  >
                    <svg aria-hidden="true" viewBox="0 0 24 24">
                      <path d="m8 8 8 8M16 8l-8 8" />
                    </svg>
                  </button>
                ) : null}
              </div>
              {searchingEditSuggestions ? (
                <span className="itinerarySearchStatus" role="status">
                  Đang tìm địa điểm…
                </span>
              ) : null}
              {editPlaceSuggestions.length > 0 ? (
                <div className="itinerarySuggestionsDropdown" id="edit-place-suggestions" role="listbox">
                  {editPlaceSuggestions.map((suggestion, suggestionIndex) => (
                    <button
                      className="itinerarySuggestionItem"
                      key={suggestion.placeId || `${suggestion.name}-${suggestionIndex}`}
                      onClick={() => {
                        setEditingItem({ ...editingItem, name: suggestion.name });
                        setSelectedEditSuggestion(suggestion);
                        setEditPlaceSuggestions([]);
                      }}
                      role="option"
                      type="button"
                    >
                      <strong>{suggestion.name}</strong>
                      {suggestion.address ? <span>{suggestion.address}</span> : null}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
            {!selectedEditSuggestion && editSearchCompleted && editSearchFailed ? (
              <p className="itinerarySearchHint" role="alert">
                Không thể tải dữ liệu Places lúc này. Vui lòng thử lại.
              </p>
            ) : !selectedEditSuggestion && editSearchCompleted && editPlaceSuggestions.length === 0 ? (
              <p className="itinerarySearchHint" role="status">
                Không tìm thấy địa điểm phù hợp trong dữ liệu Places. Hãy thử tên hoặc từ khóa khác.
              </p>
            ) : !selectedEditSuggestion && editingItem.name.trim() !== editingItem.originalName.trim() ? (
              <p className="itinerarySearchHint">Chọn một địa điểm trong gợi ý để cập nhật đúng vị trí trên bản đồ.</p>
            ) : null}
            {editingItem.notesExpanded ? (
              <div className="itineraryMutationField editPlaceNotesField">
                <label htmlFor="edit-place-notes">
                  <span className="editPlaceSearchLabel">Ghi chú</span>
                </label>
                <textarea
                  autoFocus={!editingItem.personalNotes}
                  id="edit-place-notes"
                  onChange={(event) => setEditingItem({
                    ...editingItem,
                    personalNotes: event.target.value
                  })}
                  placeholder="Viết ghi chú cho địa điểm này…"
                  rows={4}
                  value={editingItem.personalNotes}
                />
              </div>
            ) : (
              <button
                aria-controls="edit-place-notes"
                aria-expanded="false"
                className="editPlaceAddNotes"
                onClick={() => setEditingItem({ ...editingItem, notesExpanded: true })}
                type="button"
              >
                <svg aria-hidden="true" viewBox="0 0 24 24">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                Thêm ghi chú
              </button>
            )}
            </div>
            <div className="itineraryMutationActions">
              <button className="cancel" onClick={() => setEditingItem(null)} type="button">
                Hủy
              </button>
              <button
                className="submit"
                disabled={
                  mutatingItem
                  || (editingItem.name.trim() !== editingItem.originalName.trim() && !selectedEditSuggestion)
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
            className="itineraryMutationForm editPlaceNotesWindow"
            onClick={(e) => e.stopPropagation()}
            onSubmit={handleAddPlanItem}
          >
            <header className="itineraryMutationHeader editPlaceNotesHeader">
              <div className="itineraryMutationHeading">
                <span className="itineraryMutationEyebrow">Ngày {addingDay}</span>
                <div>
                  <h3 id="add-place-title">Thêm địa điểm</h3>
                  <p>Chọn một điểm dừng mới cho lịch trình của bạn.</p>
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
            <div className="itineraryMutationBody editPlaceNotesPaper">
            <div className="itineraryMutationField itinerarySearchContainer">
              <label htmlFor="add-place-search">
                <span className="editPlaceSearchLabel">Tìm và chọn địa điểm <span aria-hidden="true">*</span></span>
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
                  aria-controls="add-place-suggestions"
                  aria-expanded={placeSuggestions.length > 0}
                  autoComplete="off"
                  id="add-place-search"
                  onChange={(e) => {
                    setAddName(e.target.value);
                    setSelectedSuggestion(null);
                    setAddSearchCompleted(false);
                    setAddSearchFailed(false);
                  }}
                  placeholder="Nhập tên địa điểm để tìm"
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
                      event.currentTarget.parentElement?.querySelector("input")?.focus();
                    }}
                    type="button"
                  >
                    <svg aria-hidden="true" viewBox="0 0 24 24">
                      <path d="m8 8 8 8M16 8l-8 8" />
                    </svg>
                  </button>
                ) : null}
              </div>
              {searchingSuggestions ? (
                <span className="itinerarySearchStatus" role="status">
                  Đang tìm địa điểm…
                </span>
              ) : null}
              {placeSuggestions.length > 0 ? (
                <div className="itinerarySuggestionsDropdown" id="add-place-suggestions" role="listbox">
                  {placeSuggestions.map((suggestion, sIdx) => (
                    <button
                      className="itinerarySuggestionItem"
                      key={suggestion.placeId || `${suggestion.name}-${sIdx}`}
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
                      <strong>{suggestion.name}</strong>
                      {suggestion.address ? <span>{suggestion.address}</span> : null}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            {selectedSuggestion ? (
              <div className="selectedPlaceBadge">
                <span className="selectedPlaceBadgeIcon" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d="m7 12 3 3 7-7" /></svg>
                </span>
                <span><strong>Đã chọn vị trí</strong>{selectedSuggestion.address || selectedSuggestion.name}</span>
              </div>
            ) : addSearchCompleted && addSearchFailed ? (
              <p className="itinerarySearchHint" role="alert">
                Không thể tải dữ liệu Places lúc này. Vui lòng thử lại.
              </p>
            ) : addSearchCompleted && addName.trim().length >= 2 && placeSuggestions.length === 0 ? (
              <p className="itinerarySearchHint" role="status">
                Không tìm thấy địa điểm phù hợp trong dữ liệu Places. Hãy thử tên hoặc từ khóa khác.
              </p>
            ) : addName.trim() ? (
              <p className="itinerarySearchHint">
                Bạn phải chọn một kết quả trong danh sách để thêm đúng địa điểm và vị trí bản đồ.
              </p>
            ) : null}

            <div className="itineraryMutationField">
              <label>Loại địa điểm</label>
              <select
                onChange={(e) => setAddPlaceType(e.target.value)}
                value={addPlaceType}
              >
                <option value="attraction">Tham quan / Vui chơi</option>
                <option value="food">Ăn uống / Nhà hàng</option>
                <option value="cafe">Cà phê / Giải khát</option>
                <option value="hotel">Khách sạn / Lưu trú</option>
              </select>
            </div>
            <div className="itineraryMutationField">
              <label>Ghi chú (Tùy chọn)</label>
              <textarea
                onChange={(e) => setAddNotes(e.target.value)}
                placeholder="Ví dụ: Ăn bát phở tái lăn"
                rows={2}
                value={addNotes}
              />
            </div>
            </div>
            <div className="itineraryMutationActions">
              <button className="cancel" onClick={() => {
                setAddingDay(null);
              }} type="button">
                Hủy
              </button>
              <button className="submit" disabled={mutatingItem || !selectedSuggestion} type="submit">
                {mutatingItem ? "Đang thêm..." : "Thêm vào lịch trình"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
      {pendingTurn ? (
        <div
          className="confirm-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-turn-title"
          data-testid="confirm-turn-modal"
        >
          <div className="confirm-modal">
            <h2 id="confirm-turn-title">Xác nhận thay đổi lịch trình</h2>
            <p className="confirm-modal-hint">
              Supervisor đề xuất thay đổi có phạm vi lớn. Xác nhận để áp dụng hoặc hủy để giữ lịch trình hiện tại.
            </p>
            <ul className="confirm-modal-blocks">
              {pendingTurn.assistantBlocks.map((block, index) => {
                const summary = typeof block?.summary === "string" ? block.summary : null;
                const text = typeof block?.text === "string" ? block.text : null;
                const content = summary ?? text ?? JSON.stringify(block);
                return <li key={`${pendingTurn.id}-${index}`}>{content}</li>;
              })}
            </ul>
            <div className="confirm-modal-actions">
              <button
                type="button"
                onClick={cancelPendingTurn}
                disabled={confirmBusy}
                className="ghost"
              >
                Hủy
              </button>
              <button
                type="button"
                onClick={confirmPendingTurn}
                disabled={confirmBusy}
                className="submit"
              >
                {confirmBusy ? "Đang áp dụng..." : "Xác nhận"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}

function SidebarIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <rect height="18" rx="3" width="18" x="3" y="3" />
      <path d="M9 3v18" />
      {collapsed ? <path d="m13 9 3 3-3 3" /> : <path d="m16 9-3 3 3 3" />}
    </svg>
  );
}

function MenuIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M4 6h16" />
      <path d="M4 12h16" />
      <path d="M4 18h16" />
    </svg>
  );
}

function NewChatIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M12 20H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h7" />
      <path d="m16 3 5 5-9 9-4 1 1-4z" />
    </svg>
  );
}

function ProjectIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5" />
    </svg>
  );
}

function categoryFromPlaceType(placeType: string): PlaceCategory {
  const normalized = placeType
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  if (
    normalized.includes("food")
    || normalized.includes("restaurant")
    || normalized.includes("an uong")
    || normalized.includes("am thuc")
    || normalized.includes("nha hang")
  ) return "food";
  if (
    normalized.includes("cafe")
    || normalized.includes("coffee")
    || normalized.includes("ca phe")
    || normalized.includes("giai khat")
  ) return "cafe";
  if (normalized.includes("hotel") || normalized.includes("accommodation") || normalized.includes("lodging")) return "hotel";
  if (normalized.includes("transport") || normalized.includes("station") || normalized.includes("transit")) return "transport";
  if (normalized.includes("break") || normalized.includes("free")) return "free_time";
  if (normalized.includes("museum") || normalized.includes("culture") || normalized.includes("temple") || normalized.includes("heritage")) return "culture";
  if (normalized.includes("nature") || normalized.includes("park") || normalized.includes("garden")) return "nature";
  if (normalized.includes("shop") || normalized.includes("market")) return "shopping";
  if (normalized.includes("night") || normalized.includes("bar")) return "nightlife";
  if (normalized.includes("wellness") || normalized.includes("spa")) return "wellness";
  if (normalized.includes("adventure") || normalized.includes("hiking")) return "adventure";
  if (normalized.includes("beach")) return "beach";
  if (normalized.includes("family") || normalized.includes("zoo")) return "family";
  if (normalized.includes("attraction") || normalized.includes("visit") || normalized.includes("place")) return "attraction";
  return "other";
}

function hasPlanItemCoordinates(
  item: TravelPlan["days"][number]["items"][number]
): item is TravelPlan["days"][number]["items"][number] & {
  latitude: number;
  longitude: number;
} {
  return (
    typeof item.latitude === "number" &&
    Number.isFinite(item.latitude) &&
    item.latitude >= -90 &&
    item.latitude <= 90 &&
    typeof item.longitude === "number" &&
    Number.isFinite(item.longitude) &&
    item.longitude >= -180 &&
    item.longitude <= 180
  );
}

function planItemMapKey(day: number, itemIndex: number, name: string): string {
  return `plan-${day}-${itemIndex}-${name}`;
}

function dateKeyForTripDay(
  startDate: string | null | undefined,
  day: number
): string {
  if (!startDate || !/^\d{4}-\d{2}-\d{2}$/.test(startDate)) {
    return `day-${day}`;
  }

  const date = new Date(`${startDate}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return `day-${day}`;
  date.setUTCDate(date.getUTCDate() + day - 1);
  return date.toISOString().slice(0, 10);
}

function handleDayTabKeyDown(
  event: ReactKeyboardEvent<HTMLDivElement>
): void {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
    return;
  }

  const tabs = Array.from(
    event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')
  );
  const currentIndex = tabs.indexOf(document.activeElement as HTMLButtonElement);
  if (currentIndex < 0) return;

  event.preventDefault();
  const nextIndex = event.key === "Home"
    ? 0
    : event.key === "End"
      ? tabs.length - 1
      : (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
  tabs[nextIndex]?.focus();
  tabs[nextIndex]?.click();
}

function dateLabelForTripDay(
  startDate: string | null | undefined,
  day: number
): string {
  const dateKey = dateKeyForTripDay(startDate, day);
  if (dateKey.startsWith("day-")) return `Ngày ${day}`;

  const [year, month, date] = dateKey.split("-");
  return `Ngày ${day} · ${date}/${month}/${year}`;
}

function shortDateLabelForTripDay(
  startDate: string | null | undefined,
  day: number
): string | null {
  const dateKey = dateKeyForTripDay(startDate, day);
  if (dateKey.startsWith("day-")) return null;

  const [, month, date] = dateKey.split("-");
  return `${date}/${month}`;
}

function processingDescription(stage: WorkflowStage, intakeKind: IntakeKind): string {
  if (stage === "planning") {
    return "Đang tạo khung chuyến đi, xếp địa điểm và kiểm tra lịch trình.";
  }
  if (intakeKind === "image") {
    return "Đang đọc nội dung ảnh, nhận diện địa điểm và chuẩn hóa yêu cầu.";
  }
  return "Đang hiểu điểm đến, thời lượng, ngân sách, sở thích và ràng buộc.";
}

function processingActivity(
  stage: WorkflowStage,
  intakeKind: IntakeKind,
  elapsed: number
): string {
  if (stage === "planning") {
    if (elapsed < 6) return "Đang tạo khung chuyến đi theo từng ngày";
    if (elapsed < 14) return "Đang xếp địa điểm, bữa ăn và thời gian nghỉ";
    if (elapsed < 24) return "Đang tính các chặng di chuyển";
    return "Đang kiểm tra lịch trình và các ràng buộc";
  }

  if (intakeKind === "image") {
    if (elapsed < 7) return "Đang đọc nội dung trong ảnh";
    if (elapsed < 18) return "Đang nhận diện địa điểm và hoạt động";
    return "Đang chuẩn hóa thông tin chuyến đi";
  }

  if (intakeKind === "url") {
    if (elapsed < 6) return "Đang kiểm tra nguồn và chuẩn bị nội dung";
    if (elapsed < 16) return "Đang đọc nội dung có thể truy cập";
    if (elapsed < 30) return "Đang trích xuất địa điểm và ngữ cảnh";
    return "Đang đối chiếu và xác định địa điểm";
  }

  if (elapsed < 5) return "Đang hiểu điểm đến và thời lượng";
  if (elapsed < 12) return "Đang đọc ngân sách, sở thích và nhịp độ";
  return "Đang chuẩn hóa yêu cầu và ràng buộc";
}

function elapsedLabel(totalSeconds: number): string {
  if (totalSeconds < 60) return `${totalSeconds} giây`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes} phút ${seconds.toString().padStart(2, "0")} giây`;
}

function budgetLevelLabel(level: ExplorerContext["tripSpec"]["budget"]["level"]): string {
  return { low: "Thấp", medium: "Trung bình", high: "Cao" }[level];
}

function geolocationErrorMessage(error: GeolocationPositionError): string {
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

function itinerarySourceLabel(
  sourceRefs: string[],
  sourceProvider: string | null | undefined,
  source: string
): {
  kind: "url" | "finder" | "selected";
  text: string;
  url?: string;
  providerSuffix?: string;
} | null {
  const providerSuffix = sourceProvider
    ? ` · ${sourceProvider.toUpperCase()}`
    : "";
  for (const sourceRef of sourceRefs) {
    if (!sourceRef.startsWith("http://")
      && !sourceRef.startsWith("https://")) {
      continue;
    }
    return {
      kind: "url",
      text: sourceLinkLabel(sourceRef),
      url: sourceRef,
      providerSuffix
    };
  }
  if (source === "finder_suggestion" || source === "finder") {
    return {
      kind: "finder",
      text: "Finder gợi ý"
    };
  }
  if (source === "selected_place") {
    return {
      kind: "selected",
      text: "Địa điểm đã chọn"
    };
  }
  return null;
}

function sourceLinkLabel(sourceUrl: string): string {
  try {
    const hostname = new URL(sourceUrl).hostname.toLowerCase();
    if (hostname === "youtu.be" || hostname === "youtube.com"
      || hostname.endsWith(".youtube.com")) {
      return "YouTube";
    }
    if (hostname === "tiktok.com" || hostname.endsWith(".tiktok.com")) {
      return "TikTok";
    }
    return hostname.replace(/^www\./, "");
  } catch {
    return sourceUrl;
  }
}

function paceLabel(pace: string): string {
  const normalized = pace.toLowerCase();
  if (normalized.includes("slow")) return "thư thả";
  if (normalized.includes("fast")) return "nhanh";
  if (normalized.includes("balance")) return "vừa phải";
  return pace;
}

function isDisplayableImageUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

function formatCompactCount(value: number): string {
  return new Intl.NumberFormat("vi-VN", { notation: "compact" }).format(value);
}

function transportModeLabel(mode: string): string {
  const normalized = mode.toLowerCase();
  if (normalized.includes("walk")) return "Đi bộ";
  if (normalized.includes("public") || normalized.includes("transit")) {
    return "Phương tiện công cộng";
  }
  if (normalized.includes("bike") || normalized.includes("motor")) return "Xe máy";
  if (normalized.includes("ride") || normalized.includes("hailing")) return "Xe công nghệ";
  if (normalized.includes("car") || normalized.includes("taxi")) return "Ô tô";
  if (normalized.includes("bus")) return "Xe buýt";
  if (normalized.includes("train")) return "Tàu hỏa";
  if (normalized.includes("flight") || normalized.includes("plane")) return "Máy bay";
  if (normalized.includes("mixed")) return "Phương tiện chưa xác định";
  if (normalized.includes("unknown")) return "Chưa xác định";
  return mode;
}

function transportLegAfterItem(
  day: TravelPlan["days"][number],
  item: TravelPlan["days"][number]["items"][number],
  itemIndex: number
) {
  const nextItem = day.items[itemIndex + 1];
  const exactLeg = day.transportLegs.find((leg) => {
    const startsAtItem = item.itemId && leg.fromItemId
      ? item.itemId === leg.fromItemId
      : item.name.trim().toLocaleLowerCase("vi") === leg.fromPlace.trim().toLocaleLowerCase("vi");
    if (!startsAtItem || !nextItem) return false;
    return nextItem.itemId && leg.toItemId
      ? nextItem.itemId === leg.toItemId
      : nextItem.name.trim().toLocaleLowerCase("vi") === leg.toPlace.trim().toLocaleLowerCase("vi");
  });

  if (exactLeg) return exactLeg;
  return day.transportLegs.find((leg) =>
    item.itemId && leg.fromItemId
      ? item.itemId === leg.fromItemId
      : item.name.trim().toLocaleLowerCase("vi") === leg.fromPlace.trim().toLocaleLowerCase("vi")
  );
}

function transportOptionsForLeg(
  leg: TransportLeg
): TransportOption[] {
  return visibleTransportOptions(
    [leg, ...(leg.alternatives ?? [])],
    leg.distanceMeters
  );
}

function planLegSelectionKey(day: number, legIndex: number): string {
  return `${day}:${legIndex}`;
}

function transportLegsMatch(
  left: TransportLeg,
  right: TransportLeg
): boolean {
  const sameFrom =
    left.fromItemId && right.fromItemId
      ? left.fromItemId === right.fromItemId
      : left.fromPlace.trim().toLocaleLowerCase("vi") ===
        right.fromPlace.trim().toLocaleLowerCase("vi");
  const sameTo =
    left.toItemId && right.toItemId
      ? left.toItemId === right.toItemId
      : left.toPlace.trim().toLocaleLowerCase("vi") ===
        right.toPlace.trim().toLocaleLowerCase("vi");
  return sameFrom && sameTo;
}

function directionItineraryOrder(
  legs: TransportLeg[],
  item: TravelPlan["days"][number]["items"][number]
): number | null {
  const index = legs.findIndex((leg) =>
    item.itemId && leg.toItemId
      ? item.itemId === leg.toItemId
      : item.name.trim().toLocaleLowerCase("vi") ===
        leg.toPlace.trim().toLocaleLowerCase("vi")
  );
  return index >= 0 ? index + 1 : null;
}

function selectedTransportOption(
  leg: TransportLeg,
  selectedMode?: string
): TransportOption {
  const options = transportOptionsForLeg(leg);
  return (
    options.find((option) => option.mode === selectedMode)
    ?? options[0]
    ?? leg
  );
}

function isDevelopmentTransitFixture(option: TransportOption): boolean {
  return (
    option.source === "opentripplanner_transit"
    && option.details?.scheduleStatus === "development_shifted_2018"
  );
}

function isDrawableTransportRoute(
  option: TransportOption
): boolean {
  return (
    option.geometryCoordinates.length >= 2
    && isAvailableTransportOption(option)
  );
}

function formatDistance(distanceMeters: number): string {
  if (distanceMeters < 1000) {
    return `${Math.max(0, Math.round(distanceMeters))} m`;
  }
  return `${(distanceMeters / 1000).toLocaleString("vi-VN", {
    maximumFractionDigits: 1
  })} km`;
}

function TransportModeIcon({ mode }: { mode: string }) {
  const normalized = mode.toLowerCase();

  if (normalized.includes("walk")) {
    return (
      <svg viewBox="0 0 24 24">
        <circle cx="13" cy="4" r="2" />
        <path d="m10 21 2-6-3-3 2-5 4 3 3 1M12 15l4 6M9 12l-4 3" />
      </svg>
    );
  }

  if (normalized.includes("bike") || normalized.includes("motor")) {
    return (
      <svg viewBox="0 0 24 24">
        <circle cx="6" cy="17" r="3" />
        <circle cx="18" cy="17" r="3" />
        <path d="m6 17 4-7 3 7m-3-7h5l3 7M8 7h3" />
      </svg>
    );
  }

  if (
    normalized.includes("bus") ||
    normalized.includes("public") ||
    normalized.includes("transit")
  ) {
    return (
      <svg viewBox="0 0 24 24">
        <rect x="5" y="3" width="14" height="16" rx="3" />
        <path d="M7 12h10M8 19v2m8-2v2" />
        <circle cx="9" cy="16" r="1" />
        <circle cx="15" cy="16" r="1" />
      </svg>
    );
  }

  if (normalized.includes("train")) {
    return (
      <svg viewBox="0 0 24 24">
        <rect x="6" y="3" width="12" height="15" rx="3" />
        <path d="M8 10h8M9 21l3-3 3 3" />
        <circle cx="9" cy="14" r="1" />
        <circle cx="15" cy="14" r="1" />
      </svg>
    );
  }

  if (normalized.includes("flight") || normalized.includes("plane")) {
    return (
      <svg viewBox="0 0 24 24">
        <path d="m3 15 18-9-7 14-3-6zM11 14l-4-3" />
      </svg>
    );
  }

  if (normalized.includes("mixed") || normalized.includes("unknown")) {
    return (
      <svg viewBox="0 0 24 24">
        <circle cx="6" cy="17" r="2" />
        <circle cx="18" cy="7" r="2" />
        <path d="M8 17c5 0 3-10 8-10M12 5l2 2-2 2" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24">
      <path d="m5 11 2-5h10l2 5" />
      <path d="M4 12a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v5H4zM6 17v2m12-2v2" />
      <circle cx="8" cy="14" r="1" />
      <circle cx="16" cy="14" r="1" />
    </svg>
  );
}

function TransportOptionCard({
  option,
  fromPlace,
  toPlace,
  primary = false,
  selected = false,
  onSelect
}: {
  option: TransportOption;
  fromPlace: string;
  toPlace: string;
  primary?: boolean;
  selected?: boolean;
  onSelect?: () => void;
}) {
  const lines = option.details?.lines ?? [];
  const segments = option.details?.segments ?? [];
  const lineLabel = transportLineLabel(lines);
  const content = (
    <>
      <span className="transportOptionKind">
        {primary ? "Tuyến đề xuất" : "Lựa chọn khác"}
      </span>
      <div className="transportOptionHeading">
        <span className="transportOptionInlineIcon" aria-hidden="true">
          <TransportModeIcon mode={option.mode} />
        </span>
        <strong>{transportModeLabel(option.mode)}</strong>
        <span className="transportDuration">
          <ClockIcon />
          {option.estimatedDurationMinutes} phút
        </span>
      </div>
      <p>
        <span>{fromPlace}</span>
        <b aria-hidden="true">→</b>
        <span>{toPlace}</span>
      </p>
      {isPublicTransitMode(option.mode) && lineLabel && segments.length === 0 ? (
        <small>{lineLabel}</small>
      ) : null}
      {option.source === "opentripplanner_transit" && segments.length > 0 ? (
        <ol className="transportSegments" aria-label="Các chặng của hành trình">
          {segments.map((segment, index) => {
            const segmentLine = segment.line
              ? transportLineLabel([segment.line])
              : null;
            return (
              <li className="transportSegment" key={`${segment.mode}-${index}`}>
                <span className="transportSegmentIcon" aria-hidden="true">
                  <TransportModeIcon mode={segment.mode} />
                </span>
                <div>
                  <strong>{transportModeLabel(segment.mode)}</strong>
                  <p>
                    <span title={segment.fromPlace}>
                      {transportSegmentPlaceLabel(
                        segment.fromPlace,
                        segment.mode,
                        "from"
                      )}
                    </span>
                    <b aria-hidden="true">→</b>
                    <span title={segment.toPlace}>
                      {transportSegmentPlaceLabel(
                        segment.toPlace,
                        segment.mode,
                        "to"
                      )}
                    </span>
                  </p>
                  <small>
                    {segmentLine ? `${segmentLine} · ` : ""}
                    {segment.estimatedDurationMinutes} phút · {formatDistance(segment.distanceMeters)}
                  </small>
                </div>
              </li>
            );
          })}
        </ol>
      ) : null}
      {isDevelopmentTransitFixture(option) ? (
        <small>Lịch development: giờ chạy cũ 2018 được dịch ngày</small>
      ) : null}
      {!option.verified && !isDevelopmentTransitFixture(option) ? (
        <small>Tuyến ước tính</small>
      ) : null}
    </>
  );
  const className = [
    "transportOptionCard",
    primary ? "primary" : "alternative",
    selected ? "is-selected" : ""
  ].join(" ");
  if (onSelect) {
    return (
      <button
        aria-pressed={selected}
        className={className}
        onClick={onSelect}
        type="button"
      >
        {content}
      </button>
    );
  }
  return <article className={className}>{content}</article>;
}

function transportLineLabel(lines: string[]): string | null {
  if (lines.length === 0) return null;
  if (lines.every((line) => /^route_\d+_\d+$/i.test(line.trim()))) {
    return "Tuyến xe buýt";
  }
  return `Tuyến ${lines.join(", ")}`;
}

function transportSegmentPlaceLabel(
  place: string,
  mode: string,
  endpoint: "from" | "to"
): string {
  if (!/^stop[_-]/i.test(place.trim())) return place;
  const isBus = mode.toLowerCase().includes("bus");
  if (isBus) {
    return endpoint === "from" ? "Trạm lên xe buýt" : "Trạm xuống xe buýt";
  }
  return endpoint === "to" ? "Trạm lên xe buýt" : "Trạm xuống xe buýt";
}

function CloseIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m7 10 5 5 5-5" />
    </svg>
  );
}
