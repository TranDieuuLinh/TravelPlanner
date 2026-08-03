"use client";

import {
  Fragment,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties
} from "react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { PenguinMascot } from "@/components/PenguinMascot";
import { APIError } from "@/lib/api";
import {
  addTripChatItem,
  amendTripChat,
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
  type PlaceSuggestion,
  type ExplorerContext,
  type ExploreResponse,
  type PlaceCategory,
  type TransportOption,
  type TransportLeg,
  type TripChat,
  type TripChatSummary,
  type UrlImportJob,
  type TravelPlan
} from "@/lib/plans";
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
  type PlannerMapRoute
} from "@/components/PlannerMap";
import { createDayColorMap } from "@/lib/day-colors";
import {
  isAvailableTransportOption,
  isPublicTransitMode
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

type TripPlaceSummary = TravelPlan["days"][number]["items"][number] & {
  day: number;
  order: number;
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
  const [activePlanDay, setActivePlanDay] = useState<number | null>(null);
  const [currentLocation, setCurrentLocation] =
    useState<PlannerMapCurrentLocation | null>(null);
  const [dayDirectionLegs, setDayDirectionLegs] =
    useState<TransportLeg[]>([]);
  const [selectedDirectionModes, setSelectedDirectionModes] =
    useState<Record<number, string>>({});
  const [selectedPlanLegModes, setSelectedPlanLegModes] =
    useState<Record<string, string>>({});
  const [directionsActive, setDirectionsActive] = useState(false);
  const [directionsStatus, setDirectionsStatus] =
    useState<DirectionsStatus>("idle");
  const [directionsError, setDirectionsError] = useState("");
  const [locationFocusRequest, setLocationFocusRequest] = useState(0);
  const [locationStatus, setLocationStatus] =
    useState<LocationStatus>("idle");
  const [locationError, setLocationError] = useState("");
  const directionsPendingLocationRef = useRef(false);
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
      personalNotes: personalNotes || ""
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

  async function handleReorderItems(day: number, newOrderedItemIds: string[]) {
    if (!activeChatId || !plan) return;
    setMutatingItem(true);
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

      const newItems = rawNewItems;

      const newLegs: typeof d.transportLegs = [];
      const locatedItems = newItems.filter((it) => it.latitude != null && it.longitude != null);
      for (let i = 0; i < locatedItems.length - 1; i++) {
        const from = locatedItems[i];
        const to = locatedItems[i + 1];
        newLegs.push({
          fromItemId: from.itemId,
          toItemId: to.itemId,
          fromPlace: from.name,
          toPlace: to.name,
          mode: "ride_hailing",
          distanceMeters: 2000,
          estimatedDurationMinutes: 10,
          geometryCoordinates: [
            [from.latitude!, from.longitude!],
            [to.latitude!, to.longitude!]
          ],
          source: "geodesic_estimate",
          verified: false
        });
      }

      return { ...d, items: newItems, transportLegs: newLegs };
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
      if (!authLoading) {
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
        setMessages([{
          id: Date.now(),
          role: "assistant",
          text: "Nhập yêu cầu chuyến đi bằng một tin nhắn. Ví dụ: Đà Nẵng 3 ngày, ăn ngon, cà phê, đi chậm."
        }]);
      }
      return;
    }
    let cancelled = false;
    setActiveChatId(null);
    setChatRevision(0);
    setExploreResult(null);
    setPlan(null);
    void listTripChats()
      .then(async (chats) => {
        if (cancelled) return;
        setTripChats(chats);
        if (chats.length > 0 && !initialDestination) {
          const chat = await getTripChat(chats[0].id);
          if (!cancelled) applyTripChat(chat);
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Không thể tải lịch sử chuyến đi.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [authLoading, initialDestination, user?.id]);

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
    directionsPendingLocationRef.current = false;
    directionsRequestIdRef.current += 1;
    setDirectionsActive(false);
    setDayDirectionLegs([]);
    setSelectedDirectionModes({});
    setSelectedPlanLegModes({});
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
              timeWindow: `Ngày ${item.day} · ${item.timeWindow}`
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
  const activeDayDirectionStops = useMemo<
    Array<TripPlaceSummary & { latitude: number; longitude: number }>
  >(
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
  const mapRoutes = useMemo<PlannerMapRoute[]>(() => {
    if (!displayedPlan) return [];
    const startDate = displayedExploreResult?.explorer.tripSpec.startDate;
    const itineraryRoutes: PlannerMapRoute[] = directionsActive
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
                  coordinates: selected.geometryCoordinates,
                  verified: selected.verified,
                  source: selected.source,
                  dayColorKey: dateKeyForTripDay(startDate, day.day),
                  kind: "itinerary" as const,
                  segments: selected.details?.segments
                }];
              })
          );
    if (directionsActive && activePlanDay != null) {
      selectedDayDirectionLegs
        .filter(isDrawableTransportRoute)
        .forEach((leg, index) => {
          itineraryRoutes.push({
            key: `day-directions-${activePlanDay}-${index}-${leg.mode}`,
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
    selectedDayDirectionLegs
  ]);

  async function requestDayDirections(
    origin: PlannerMapCurrentLocation
  ) {
    if (activePlanDay == null || activeDayDirectionStops.length === 0) {
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
          longitude: origin.longitude
        },
        destinations: activeDayDirectionStops.map((item) => ({
          itemId: item.itemId ?? null,
          name: item.name,
          address: item.address ?? null,
          timeWindow: item.timeWindow,
          latitude: item.latitude,
          longitude: item.longitude
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
      return;
    }
    if (!window.isSecureContext) {
      setLocationStatus("error");
      setLocationError(
        "Định vị cần HTTPS hoặc localhost. Hãy mở ứng dụng qua kết nối an toàn."
      );
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
        setLocationFocusRequest((current) => current + 1);
        if (directionsPendingLocationRef.current) {
          directionsPendingLocationRef.current = false;
          void requestDayDirections(nextLocation);
        }
        setLocationStatus("ready");
      },
      (geolocationError) => {
        const directionsWereWaiting =
          directionsPendingLocationRef.current;
        directionsPendingLocationRef.current = false;
        setLocationStatus("error");
        setLocationError(geolocationErrorMessage(geolocationError));
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

  function startDayDirections() {
    if (activePlanDay == null || activeDayDirectionStops.length === 0) {
      setDirectionsStatus("error");
      setDirectionsError(
        "Chọn một ngày có địa điểm trước khi bắt đầu chỉ đường."
      );
      return;
    }
    setSelectedDirectionModes({});
    setDirectionsActive(true);
    if (currentLocation) {
      void requestDayDirections(currentLocation);
      return;
    }
    directionsPendingLocationRef.current = true;
    setDirectionsStatus("routing");
    locateCurrentPosition();
  }

  function clearDayDirections() {
    directionsPendingLocationRef.current = false;
    directionsRequestIdRef.current += 1;
    setDirectionsActive(false);
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

  const locationMessage = useMemo(() => {
    if (locationStatus === "locating") {
      return "Đang lấy vị trí từ thiết bị…";
    }
    if (locationStatus === "error") {
      return locationError;
    }
    if (directionsStatus === "routing" && activePlanDay != null) {
      return `Đang tính tuyến đề xuất cho ngày ${activePlanDay}…`;
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
      const totalMeters = selectedDayDirectionLegs.reduce(
        (total, leg) => total + leg.distanceMeters,
        0
      );
      const estimated = selectedDayDirectionLegs.some((leg) => !leg.verified)
        ? " · có chặng ước tính"
        : "";
      return `Tuyến ngày ${activePlanDay} · ${totalMinutes} phút · ${formatDistance(totalMeters)}${estimated}`;
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
        }
        let updated: TripChat | null = null;
        for (let attempt = 0; attempt < 3; attempt += 1) {
          try {
            updated = await amendTripChat({
              chatId,
              content: text,
              expectedRevision,
              images
            });
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
        if (!updated) throw new Error("Không thể cập nhật chat.");
        applyTripChat(updated);
        setWorkflowStage("ready");
        setSelectedMapPlaceKey(null);
        setImages([]);
        if (fileInputRef.current) fileInputRef.current.value = "";
        setTripChats(await listTripChats());
        return;
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
        allowFinderSuggestions: nextExploreResult.allowFinderSuggestions
      });
      setPlan(generation.plan);
      setWorkflowStage("ready");
      setSelectedMapPlaceKey(null);
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: nextExploreResult.allowFinderSuggestions
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

    const pastedImages = Array.from(event.clipboardData.items)
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .flatMap((item) => {
        const image = item.getAsFile();
        return image ? [image] : [];
      });

    if (pastedImages.length === 0) return;

    event.preventDefault();
    addImages(pastedImages);
  }

  function resetWorkflow() {
    setPrompt("");
    setImages([]);
    setExploreResult(null);
    setPlan(null);
    setSelectedMapPlaceKey(null);
    setWorkflowStage("idle");
    setError("");
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
    setActiveChatId(chat.id);
    setChatRevision(chat.revision);
    setPlan(chat.currentPlan);
    setExploreResult(
      chat.currentExplorer
        ? {
            intakeId: chat.currentIntakeId ?? "",
            userId: user ? String(user.id) : null,
            explorer: chat.currentExplorer,
            allowFinderSuggestions: true
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

        <section className="plannerLayout">
        <aside aria-busy={loading} className="plannerChat panel">
          <div className="panelHeading">
            <span className="aiOrb">
              <PenguinMascot className="assistantPenguin" priority size={64} variant="logo" />
            </span>
            <div>
              <strong>Trợ lý VSF</strong>
              <small>{loading ? "Đang xử lý yêu cầu…" : "Sẵn sàng nhận yêu cầu"}</small>
            </div>
            <span className={`assistantStatus ${loading ? "working" : ""}`} aria-label={loading ? "Đang xử lý" : "Đang trực tuyến"} />
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
          </div>
          <div className="chatMessages" aria-live="polite" ref={messageListRef}>
            {messages.map((message) => (
              <div className={`chatMessageRow ${message.role}`} key={message.id}>
                <div className={`chatBubble ${message.role}`}>{message.text}</div>
              </div>
            ))}
            {loading ? (
              <div className="chatMessageRow assistant">
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
          {!exploreResult && messages.length === 1 ? (
            <div className="promptSuggestions" aria-label="Yêu cầu mẫu">
              {promptSuggestions.map((suggestion) => (
                <button key={suggestion} onClick={() => setPrompt(suggestion)} type="button">
                  {suggestion}
                </button>
              ))}
            </div>
          ) : null}
          {error ? <p className="formError">{error}</p> : null}
          <form className="chatComposer" onSubmit={(event) => { event.preventDefault(); void sendMessage(); }}>
            <div className="composerBox">
              <textarea
                aria-label="Tin nhắn lập lịch trình"
                disabled={loading}
                onKeyDown={handleComposerKeyDown}
                onChange={(event) => setPrompt(event.target.value)}
                onPaste={handleComposerPaste}
                placeholder="Nhập yêu cầu, dán URL hoặc ảnh vào đây..."
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
                <button
                  aria-label="Đính kèm ảnh"
                  className="attachButton"
                  onClick={() => fileInputRef.current?.click()}
                  type="button"
                >
                  ＋ Ảnh
                </button>
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
                {!images.length ? (
                  <small>Prompt · URL · Ảnh OCR</small>
                ) : null}
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
        </aside>

        <section className="itinerary panel">
          <header className="panelHeading itineraryHeading">
            <span className="planHeaderIcon" aria-hidden="true">
              <Image
                alt=""
                height={52}
                src="/images/penguin-globe-logo.png"
                width={52}
              />
            </span>
            <div>
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
                    style={{ "--day-color": "#167c68" } as CSSProperties}
                    tabIndex={activePlanDay == null ? 0 : -1}
                    type="button"
                  >
                    <i aria-hidden="true">Tất cả</i>
                  </button>
                  {displayedPlan.days.map((day) => {
                    const dateKey = dateKeyForTripDay(
                      displayedExploreResult.explorer.tripSpec.startDate,
                      day.day
                    );
                    const color = planDayColors.get(dateKey) ?? "#167c68";
                    const isActive = day.day === activePlanDay;
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
                        <i aria-hidden="true">Ngày {day.day}</i>
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
                        ) ?? "#167c68"
                      } as CSSProperties}
                    >
                      <div className="dayCardHeading">
                        <strong>{displayedPlanDay.theme}</strong>
                      </div>
                      {activePlanDay === displayedPlanDay.day &&
                      currentLocation ? (
                        <div className="dayNavigationStart">
                          <span className="dayNavigationCurrentDot" aria-hidden="true" />
                          <div>
                            <strong>Vị trí của tôi</strong>
                            <small>Điểm bắt đầu tạm thời · không lưu vào lịch trình</small>
                          </div>
                        </div>
                      ) : null}
                      {directionsActive &&
                      activePlanDay === displayedPlanDay.day &&
                      dayDirectionLegs.length > 0 ? (
                        <div className="dayNavigationChoices">
                          <strong className="dayNavigationChoicesTitle">
                            Thứ tự lịch trình cố định · chọn cách đi từng chặng
                          </strong>
                          {dayDirectionLegs.map((leg, legIndex) => {
                            const options = transportOptionsForLeg(leg);
                            const selected = selectedTransportOption(
                              leg,
                              selectedDirectionModes[legIndex]
                            );
                            return (
                              <details
                                className="dayNavigationLeg"
                                key={`${leg.fromPlace}-${leg.toPlace}-${legIndex}`}
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
                          const transportLegOptions = transportLeg
                            ? transportOptionsForLeg(transportLeg)
                            : [];
                          const timelineCategory = item.timelineCategory ?? "activity";
                          const isNonActivity = (
                            timelineCategory === "break"
                            || item.placeType === "break"
                            || item.placeType === "free_time"
                          );
                          const placeCategory = categoryFromPlaceType(
                            item.tags?.[0] ?? item.placeType
                          );
                          const isFoodStop = placeCategory === "food" || placeCategory === "cafe";
                          const sourceLabel = itinerarySourceLabel(
                            item.sourceRefs ?? [],
                            item.sourceProvider,
                            item.source
                          );
                          const canReorder = Boolean(item.itemId && activeChatId && !mutatingItem);
                          const placeImageUrl = item.imageUrls?.find(isDisplayableImageUrl) ?? null;
                          const isDragging = draggedItemKey?.itemId === item.itemId;
                          const isDragTarget = dragOverItemId === item.itemId && !isDragging;
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
                                  className={`itineraryStop ${isFoodStop ? "itineraryStop--food" : ""} ${transportLeg ? "hasRoute" : ""}`}
                                >
                                  <span
                                    className="itineraryStopPin"
                                    aria-hidden="true"
                                  />
                                  <div className="itineraryPlaceCard">
                                    {placeImageUrl ? (
                                      <div
                                        className="itineraryPlaceImage"
                                      >
                                        <img
                                          alt={`Ảnh ${item.name}`}
                                          draggable={false}
                                          loading="lazy"
                                          src={placeImageUrl}
                                        />
                                      </div>
                                    ) : null}
                                    <div className="itineraryPlaceContent">
                                    <header>
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
                                      {item.itemId && activeChatId ? (
                                        <div className="itineraryActions">
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
                                            <svg viewBox="0 0 24 24"><circle cx="8" cy="7" r="1"/><circle cx="16" cy="7" r="1"/><circle cx="8" cy="12" r="1"/><circle cx="16" cy="12" r="1"/><circle cx="8" cy="17" r="1"/><circle cx="16" cy="17" r="1"/></svg>
                                          </button>
                                          <button
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
                                            <svg viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                                          </button>
                                          <button
                                            className="itineraryActionButton danger"
                                            onClick={() => handleDeleteItem(displayedPlanDay.day, item.itemId!)}
                                            title="Xóa địa điểm"
                                            type="button"
                                          >
                                            <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                                          </button>
                                        </div>
                                      ) : null}
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
                                    <span className="itineraryPlaceCategory">
                                      {placeTypeLabel(item.tags?.[0] ?? item.placeType)}
                                    </span>
                                    {item.rating != null ? (
                                      <div className="itineraryPlaceRating" aria-label={`Đánh giá ${item.rating} trên 5`}>
                                        <span aria-hidden="true">★</span>
                                        <strong>{item.rating.toFixed(1)}</strong>
                                        {item.reviewCount != null && item.reviewCount > 0 ? (
                                          <small>{formatCompactCount(item.reviewCount)} lượt đánh giá</small>
                                        ) : null}
                                      </div>
                                    ) : null}
                                    {activityNoteCount || (item.itemId && activeChatId) ? (
                                    <details className="activityNotesSection">
                                      <summary>
                                        <span>{activityNoteCount ? "Ghi chú hoạt động" : "Thêm ghi chú"}</span>
                                        <small>{activityNoteCount ? `${activityNoteCount} mục` : "Tùy chọn"}</small>
                                        <ChevronDownIcon />
                                      </summary>
                                      <div className="activityNotesContent">
                                        {sourceActivityNote ? (
                                          <section>
                                            <strong>Từ URL, OCR hoặc lời thoại</strong>
                                            <p>{sourceActivityNote}</p>
                                          </section>
                                        ) : null}
                                        {additionalContextNote ? (
                                          <section>
                                            <strong>Thông tin bổ sung</strong>
                                            <p>{additionalContextNote}</p>
                                          </section>
                                        ) : null}
                                        {personalNotes ? (
                                          <section className="activityPersonalNote">
                                            <strong>Ghi chú của bạn</strong>
                                            <p>{personalNotes}</p>
                                          </section>
                                        ) : null}
                                        {item.itemId && activeChatId ? (
                                          <form
                                            className="activityPersonalNoteForm"
                                            onSubmit={(event) => handleSavePersonalNotes(
                                              event,
                                              displayedPlanDay.day,
                                              item.itemId!
                                            )}
                                          >
                                            <label htmlFor={`personal-note-${item.itemId}`}>
                                              Ghi chú của bạn
                                            </label>
                                            <textarea
                                              defaultValue={personalNotes ?? ""}
                                              id={`personal-note-${item.itemId}`}
                                              key={`${item.itemId}-${personalNotes ?? ""}`}
                                              name="personalNotes"
                                              placeholder="Ví dụ: Ngồi ngoài trời, gọi món đặc trưng…"
                                              rows={2}
                                            />
                                            <button disabled={mutatingItem} type="submit">
                                              {mutatingItem
                                                ? "Đang lưu..."
                                                : personalNotes
                                                  ? "Lưu ghi chú"
                                                  : "Thêm ghi chú"}
                                            </button>
                                          </form>
                                        ) : null}
                                      </div>
                                    </details>
                                    ) : null}
                                    </div>
                                  </div>
                                </article>
                              )}
                              </div>
                              {transportLeg && transportLegOptions.length > 0 ? (
                                <div
                                  className="itineraryRoute"
                                  aria-label={`${transportModeLabel(selectedTransportLeg?.mode ?? transportLeg.mode)}, từ ${transportLeg.fromPlace} đến ${transportLeg.toPlace}, khoảng ${selectedTransportLeg?.estimatedDurationMinutes ?? transportLeg.estimatedDurationMinutes} phút`}
                                  role="group"
                                >
                                  <span className="itineraryRouteIcon" aria-hidden="true">
                                    <TransportModeIcon mode={selectedTransportLeg?.mode ?? transportLeg.mode} />
                                  </span>
                                  <span>
                                    {selectedTransportLeg?.estimatedDurationMinutes ?? transportLeg.estimatedDurationMinutes} phút
                                    {" · "}{formatDistance(selectedTransportLeg?.distanceMeters ?? transportLeg.distanceMeters)}
                                  </span>
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
          currentLocation={currentLocation}
          dayColorKeys={planDayColorKeys}
          directionsActive={directionsActive}
          directionsBusy={directionsStatus === "routing"}
          directionsDay={activePlanDay}
          directionsEnabled={activeDayDirectionStops.length > 0}
          locationFocusRequest={locationFocusRequest}
          locationBusy={
            locationStatus === "locating"
          }
          locationMessage={locationMessage}
          onLocate={locateCurrentPosition}
          onStartDirections={startDayDirections}
          onSelect={setSelectedMapPlaceKey}
          places={mapPlaces}
          routes={mapRoutes}
          selectedKey={selectedMapPlaceKey}
        />
        </section>
      </div>

      {editingItem ? (
        <div className="itineraryMutationModal" onClick={() => setEditingItem(null)}>
          <form
            className="itineraryMutationForm"
            onClick={(e) => e.stopPropagation()}
            onSubmit={handleSaveEditItem}
          >
            <h3>Sửa địa điểm (Ngày {editingItem.day})</h3>
            <div className="itineraryMutationField itinerarySearchContainer">
              <label>Tìm và chọn địa điểm *</label>
              <input
                aria-autocomplete="list"
                aria-controls="edit-place-suggestions"
                aria-expanded={editPlaceSuggestions.length > 0}
                autoComplete="off"
                onChange={(e) => {
                  setEditingItem({ ...editingItem, name: e.target.value });
                  setSelectedEditSuggestion(null);
                  setEditSearchCompleted(false);
                  setEditSearchFailed(false);
                }}
                placeholder="Nhập tên địa điểm để tìm trong dữ liệu Places"
                required
                role="combobox"
                type="text"
                value={editingItem.name}
              />
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
            {selectedEditSuggestion ? (
              <div className="selectedPlaceBadge">
                <span>✓ Đã chọn vị trí: {selectedEditSuggestion.address || selectedEditSuggestion.name}</span>
              </div>
            ) : editSearchCompleted && editSearchFailed ? (
              <p className="itinerarySearchHint" role="alert">
                Không thể tải dữ liệu Places lúc này. Vui lòng thử lại.
              </p>
            ) : editSearchCompleted && editPlaceSuggestions.length === 0 ? (
              <p className="itinerarySearchHint" role="status">
                Không tìm thấy địa điểm phù hợp trong dữ liệu Places. Hãy thử tên hoặc từ khóa khác.
              </p>
            ) : editingItem.name.trim() !== editingItem.originalName.trim() ? (
              <p className="itinerarySearchHint">Chọn một địa điểm trong gợi ý để cập nhật đúng vị trí trên bản đồ.</p>
            ) : null}
            <div className="itineraryMutationField">
              <label>Ghi chú trong lịch trình (không phải mô tả địa điểm)</label>
              <textarea
                onChange={(e) => setEditingItem({ ...editingItem, personalNotes: e.target.value })}
                placeholder="Ví dụ: Ngồi ngoài trời, gọi món đặc trưng…"
                rows={3}
                value={editingItem.personalNotes}
              />
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
        <div className="itineraryMutationModal" onClick={() => {
          setAddingDay(null);
        }}>
          <form
            className="itineraryMutationForm"
            onClick={(e) => e.stopPropagation()}
            onSubmit={handleAddPlanItem}
          >
            <h3>Thêm địa điểm vào Ngày {addingDay}</h3>
            <div className="itineraryMutationField itinerarySearchContainer">
              <label>Tìm và chọn địa điểm *</label>
              <input
                aria-autocomplete="list"
                aria-controls="add-place-suggestions"
                aria-expanded={placeSuggestions.length > 0}
                onChange={(e) => {
                  setAddName(e.target.value);
                  setSelectedSuggestion(null);
                  setAddSearchCompleted(false);
                  setAddSearchFailed(false);
                }}
                placeholder="Nhập tên địa điểm để tìm trong dữ liệu Places"
                required
                role="combobox"
                type="text"
                value={addName}
              />
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
                <span>✓ Đã chọn vị trí: {selectedSuggestion.address || selectedSuggestion.name}</span>
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
  const normalized = placeType.toLowerCase();
  if (normalized.includes("food") || normalized.includes("restaurant")) return "food";
  if (normalized.includes("cafe") || normalized.includes("coffee")) return "cafe";
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
    return "Bạn chưa cho phép truy cập vị trí. Hãy bật quyền vị trí cho trang này.";
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

function placeTypeLabel(placeType: string): string {
  const category = categoryFromPlaceType(placeType);
  const labels: Record<PlaceCategory, string> = {
    attraction: "Tham quan",
    food: "Ăn uống",
    cafe: "Cà phê",
    hotel: "Lưu trú",
    transport: "Di chuyển",
    free_time: "Nghỉ ngơi",
    nature: "Thiên nhiên",
    culture: "Văn hóa",
    shopping: "Mua sắm",
    nightlife: "Buổi tối",
    wellness: "Thư giãn",
    adventure: "Khám phá",
    beach: "Biển",
    family: "Gia đình",
    other: "Trải nghiệm"
  };
  return labels[category];
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
  if (normalized.includes("mixed")) return "Kết hợp";
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
  return [leg, ...(leg.alternatives ?? [])].filter(
    isAvailableTransportOption
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
