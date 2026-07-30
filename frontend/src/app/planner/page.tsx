"use client";

import { Fragment, Suspense, useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { PenguinMascot } from "@/components/PenguinMascot";
import {
  amendTripChat,
  createTripChat,
  createPlanFromExplorer,
  exploreFullIntake,
  getTripChat,
  listTripChats,
  type ExplorerContext,
  type ExploreResponse,
  type PlaceCategory,
  type TransportOption,
  type TripChat,
  type TripChatSummary,
  type TravelPlan
} from "@/lib/plans";
import {
  PlannerMap,
  type PlannerMapPlace,
  type PlannerMapRoute
} from "@/components/PlannerMap";

type ChatMessage = {
  id: number | string;
  role: "assistant" | "user";
  text: string;
};

type WorkflowStage = "idle" | "exploring" | "planning" | "ready" | "failed";
type TimedWorkflowStage = Extract<WorkflowStage, "exploring" | "planning">;
type IntakeKind = "prompt" | "image" | "url";

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

const workflowStages: Array<{
  id: "exploring" | "planning" | "ready";
  label: string;
  description: string;
}> = [
  { id: "exploring", label: "Explorer", description: "Đọc prompt, URL hoặc ảnh" },
  { id: "planning", label: "Planner + Finder", description: "Tạo và xếp lịch trình" },
  { id: "ready", label: "Kết quả", description: "Hiển thị plan và nguồn dữ liệu" }
];

const URL_PATTERN = /https?:\/\/[^\s]+/i;
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
  const [plan, setPlan] = useState<TravelPlan | null>(null);
  const [workflowStage, setWorkflowStage] = useState<WorkflowStage>("idle");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [intakeKind, setIntakeKind] = useState<IntakeKind>("prompt");
  const [stageStartedAt, setStageStartedAt] = useState<number | null>(null);
  const [stageElapsedSeconds, setStageElapsedSeconds] = useState(0);
  const [stageDurations, setStageDurations] = useState<
    Partial<Record<TimedWorkflowStage, number>>
  >({});
  const [tripChats, setTripChats] = useState<TripChatSummary[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [chatRevision, setChatRevision] = useState(0);
  const [historyCollapsed, setHistoryCollapsed] = useState(true);

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
    const messageList = messageListRef.current;
    if (messageList) {
      messageList.scrollTo({ top: messageList.scrollHeight, behavior: "smooth" });
    }
  }, [messages, workflowStage]);

  useEffect(() => {
    if (!loading || stageStartedAt == null) return;
    const updateElapsed = () => {
      setStageElapsedSeconds(Math.max(0, Math.floor((Date.now() - stageStartedAt) / 1000)));
    };
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [loading, stageStartedAt]);

  const tripPlaces = useMemo<TripPlaceSummary[]>(() => {
    if (!plan) return [];
    const seen = new Set<string>();
    let order = 0;

    return plan.days.flatMap((day) =>
      day.items.flatMap((item, itemIndex) => {
        if (isBreakPlanItem(item)) return [];
        const key = item.name.trim().toLocaleLowerCase("vi");
        if (seen.has(key)) return [];
        seen.add(key);
        order += 1;
        return [{
          ...item,
          day: day.day,
          order,
          mapKey: hasPlanItemCoordinates(item)
            ? planItemMapKey(day.day, itemIndex, item.name)
            : null
        }];
      })
    );
  }, [plan]);
  const mapPlaces = useMemo<PlannerMapPlace[]>(() => {
    const startDate = exploreResult?.explorer.tripSpec.startDate;
    return tripPlaces.flatMap((item) =>
      item.mapKey
        ? [{
            name: item.name,
            category: categoryFromPlaceType(item.placeType),
            address: item.address || `Ngày ${item.day} · ${item.timeWindow}`,
            latitude: item.latitude ?? null,
            longitude: item.longitude ?? null,
            notes: item.notes,
            mapKey: item.mapKey,
            mapOrder: item.order,
            dayColorKey: dateKeyForTripDay(startDate, item.day),
            dayLabel: dateLabelForTripDay(startDate, item.day)
          }]
        : []
    );
  }, [exploreResult?.explorer.tripSpec.startDate, tripPlaces]);
  const mapRoutes = useMemo<PlannerMapRoute[]>(() => {
    if (!plan) return [];
    const startDate = exploreResult?.explorer.tripSpec.startDate;
    return plan.days.flatMap((day) =>
      day.transportLegs
        .filter((leg) => leg.geometryCoordinates.length >= 2)
        .map((leg, index) => ({
          key: `day-${day.day}-leg-${index}`,
          coordinates: leg.geometryCoordinates,
          verified: leg.verified,
          source: leg.source,
          dayColorKey: dateKeyForTripDay(startDate, day.day)
        }))
    );
  }, [exploreResult?.explorer.tripSpec.startDate, plan]);

  async function sendMessage() {
    const typedText = prompt.trim();
    if (!typedText && images.length === 0) {
      setError("Nhập yêu cầu, dán URL hoặc đính kèm ảnh trước khi gửi.");
      return;
    }
    const text = typedText || "Tạo lịch trình từ ảnh đính kèm.";

    const attachmentSummary = images.length ? `📎 ${images.length} ảnh` : "";
    const userMessage: ChatMessage = {
      id: Date.now(),
      role: "user",
      text: [text, attachmentSummary].filter(Boolean).join("\n")
    };
    setMessages((current) => [...current, userMessage]);
    setPrompt("");
    setLoading(true);
    setIntakeKind(URL_PATTERN.test(text) ? "url" : images.length > 0 ? "image" : "prompt");
    setStageDurations({});
    const exploringStartedAt = Date.now();
    setStageStartedAt(exploringStartedAt);
    setStageElapsedSeconds(0);
    setWorkflowStage("exploring");
    setError("");
    let activeStage: TimedWorkflowStage = "exploring";
    let activeStageStartedAt = exploringStartedAt;
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
        const updated = await amendTripChat({
          chatId,
          content: text,
          expectedRevision,
          images
        });
        applyTripChat(updated);
        setStageDurations({
          exploring: Math.max(0, Math.round((Date.now() - exploringStartedAt) / 1000)),
          planning: 0
        });
        setWorkflowStage("ready");
        setStageStartedAt(null);
        setStageElapsedSeconds(0);
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
      setStageDurations({
        exploring: Math.max(0, Math.round((Date.now() - exploringStartedAt) / 1000))
      });
      setExploreResult(nextExploreResult);
      const planningStartedAt = Date.now();
      activeStage = "planning";
      activeStageStartedAt = planningStartedAt;
      setStageStartedAt(planningStartedAt);
      setStageElapsedSeconds(0);
      setWorkflowStage("planning");
      const nextPlan = await createPlanFromExplorer({
        context: nextExploreResult.explorer,
        intakeId: nextExploreResult.intakeId,
        userId: nextExploreResult.userId,
        allowFinderSuggestions: nextExploreResult.allowFinderSuggestions
      });
      setStageDurations((current) => ({
        ...current,
        planning: Math.max(0, Math.round((Date.now() - planningStartedAt) / 1000))
      }));
      setPlan(nextPlan);
      setWorkflowStage("ready");
      setStageStartedAt(null);
      setStageElapsedSeconds(0);
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
      setStageDurations((current) => ({
        ...current,
        [activeStage]: Math.max(0, Math.round((Date.now() - activeStageStartedAt) / 1000))
      }));
      setWorkflowStage("failed");
      setStageStartedAt(null);
      setError(message);
      setMessages((current) => [...current, { id: Date.now() + 1, role: "assistant", text: message }]);
    } finally {
      setLoading(false);
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
    setStageStartedAt(null);
    setStageElapsedSeconds(0);
    setStageDurations({});
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

  function applyTripChat(chat: TripChat) {
    setActiveChatId(chat.id);
    setChatRevision(chat.revision);
    setPlan(chat.currentPlan);
    setExploreResult(
      chat.currentExplorer
        ? {
            intakeId: "",
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
      if (!loading && (prompt.trim() || images.length > 0)) {
        void sendMessage();
      }
    }
  }

  function workflowStateFor(stageId: "exploring" | "planning" | "ready") {
    const order = ["exploring", "planning", "ready"] as const;
    if (workflowStage === "failed") return "failed";
    if (workflowStage === "idle") return "waiting";
    const currentIndex = order.indexOf(workflowStage);
    const stageIndex = order.indexOf(stageId);
    if (stageIndex < currentIndex || workflowStage === "ready") return "complete";
    if (stageIndex === currentIndex) return "active";
    return "waiting";
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
                    <button
                      aria-current={chat.id === activeChatId ? "page" : undefined}
                      className={chat.id === activeChatId ? "active" : ""}
                      disabled={loading}
                      key={chat.id}
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
            ) : (
              <span className="aiOrb">
                <PenguinMascot className="assistantPenguin" priority size={64} variant="logo" />
              </span>
            )}
            <div>
              <strong>Trợ lý VSF</strong>
              <small>{loading ? "Đang xử lý yêu cầu…" : "Sẵn sàng nhận yêu cầu"}</small>
            </div>
            {!user ? (
              <button
                aria-label="Làm mới Planner"
                className="resetWorkflowButton"
                disabled={loading || (!exploreResult && messages.length === 1)}
                onClick={resetWorkflow}
                type="button"
              >
                <span aria-hidden="true">↻</span> Làm mới
              </button>
            ) : null}
            <span className={`assistantStatus ${loading ? "working" : ""}`} aria-label={loading ? "Đang xử lý" : "Đang trực tuyến"} />
          </div>
          <ol className="chatWorkflow" aria-label="Tiến trình tạo lịch trình">
            {workflowStages.map((stage, index) => {
              const state = workflowStateFor(stage.id);
              const duration = stage.id === "ready"
                ? null
                : state === "active"
                  ? stageElapsedSeconds
                  : stageDurations[stage.id];
              return (
                <li className={state} key={stage.id}>
                  <span>{state === "complete" ? "✓" : index + 1}</span>
                  <div>
                    <strong>{stage.label}</strong>
                    <small>
                      {duration == null
                        ? stage.description
                        : `${state === "active" ? "Đang chạy" : "Hoàn tất"} · ${formatElapsedTime(duration)}`}
                    </small>
                  </div>
                </li>
              );
            })}
          </ol>
          <div className="chatMessages" aria-live="polite" ref={messageListRef}>
            {messages.map((message) => (
              <div className={`chatMessageRow ${message.role}`} key={message.id}>
                {message.role === "assistant" ? (
                  <PenguinMascot className="chatPenguinAvatar" size={40} variant="chat" />
                ) : null}
                <div className={`chatBubble ${message.role}`}>{message.text}</div>
              </div>
            ))}
            {loading ? (
              <div className="chatMessageRow assistant">
                <PenguinMascot className="chatPenguinAvatar" size={40} variant="chat" />
                <div className="chatBubble assistant processingMessage" role="status">
                  <div className="processingMessageTitle">
                    <span className="typingDots" aria-hidden="true"><i /><i /><i /></span>
                    <strong>
                      {workflowStage === "exploring"
                        ? "Explorer đang chuẩn hóa dữ liệu"
                        : "Planner và Finder đang dựng lịch trình"}
                    </strong>
                  </div>
                  {workflowStage !== "exploring" || intakeKind !== "url" ? (
                    <span>{processingDescription(workflowStage, intakeKind)}</span>
                  ) : null}
                  <small>
                    Đã xử lý {formatElapsedTime(stageElapsedSeconds)}
                    {stageElapsedSeconds >= 20 && workflowStage === "exploring" && intakeKind === "url"
                      ? " · Video dài hoặc nguồn phản hồi chậm có thể cần thêm thời gian."
                      : ""}
                  </small>
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
                ) : <small>Prompt · URL · Dán ảnh để OCR</small>}
                <button
                  aria-label={loading ? "Đang xử lý yêu cầu" : "Gửi yêu cầu"}
                  className="sendButton"
                  disabled={loading || (!prompt.trim() && images.length === 0)}
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
          <div className="itineraryTop">
            <div>
              <span className="eyebrow">Explorer</span>
              <h2>{exploreResult ? "Tổng quan chuyến đi" : "Kết quả Explorer"}</h2>
            </div>
          </div>
          {exploreResult ? (
            <div className="exploreResult">
              <section className="tripSummaryCard">
                <div className="tripSummaryIntro">
                  <span className="destinationPin" aria-hidden="true">⌖</span>
                  <div>
                    <span className="tripSummaryLabel">Điểm đến của bạn</span>
                    <h3>{exploreResult.explorer.intent.destination}</h3>
                    <p>{exploreResult.explorer.intent.travelStyle} · Nhịp độ {paceLabel(exploreResult.explorer.intent.pace)}</p>
                  </div>
                </div>
                <div className="tripQuickFacts" aria-label="Thông tin chuyến đi">
                  <div><span>Thời lượng</span><strong>{exploreResult.explorer.tripSpec.days} ngày</strong></div>
                  <div><span>Nhóm đi</span><strong>{exploreResult.explorer.tripSpec.partySize} người</strong></div>
                  <div><span>Mức ngân sách</span><strong>{budgetLevelLabel(exploreResult.explorer.tripSpec.budget.level)}</strong></div>
                </div>
                <div className="budgetSummary">
                  <span className="budgetIcon" aria-hidden="true">₫</span>
                  <div><span>Mức chi dự kiến</span><strong>{formatBudget(exploreResult.explorer)}</strong></div>
                </div>
                {exploreResult.explorer.intent.interests.length ? (
                  <div className="interestGroup">
                    <span className="sectionMicroTitle">Bạn muốn trải nghiệm</span>
                    <div className="tagRow">
                      {exploreResult.explorer.intent.interests.map((interest) => <span key={interest}>{interest}</span>)}
                    </div>
                  </div>
                ) : null}
              </section>

              {plan ? (
                <>
                  <section className="tripPlanSection">
                  {plan.days.map((day) => (
                    <article className="explorerDayCard" key={day.day}>
                      <div className="dayCardHeading">
                        <span><small>Ngày</small>{day.day}</span>
                        <div><strong>{day.theme}</strong><small>{day.items.length} hoạt động</small></div>
                      </div>
                      <div className="dayTimeline">
                        {day.items.map((item, itemIndex) => {
                          const mapKey = hasPlanItemCoordinates(item)
                            ? planItemMapKey(day.day, itemIndex, item.name)
                            : null;
                          const transportLeg = transportLegAfterItem(day, item, itemIndex);
                          return (
                            <Fragment key={`${day.day}-${itemIndex}`}>
                              <div className={`dayTimelineItem ${isBreakPlanItem(item) ? "break" : ""}`}>
                                <time>{item.timeWindow}</time>
                                <span className="dayTimelineDot" aria-hidden="true" />
                                <div>
                                  {!isBreakPlanItem(item) && mapKey ? (
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
                                  {item.notes ? <p>{item.notes}</p> : null}
                                </div>
                              </div>
                              {transportLeg ? (
                                <div
                                  className="timelineTransportLeg"
                                  aria-label={`${transportModeLabel(transportLeg.mode)}, từ ${transportLeg.fromPlace} đến ${transportLeg.toPlace}, khoảng ${transportLeg.estimatedDurationMinutes} phút`}
                                  role="group"
                                >
                                  <span aria-hidden="true" />
                                  <span className="transportModeIcon" aria-hidden="true">
                                    <TransportModeIcon mode={transportLeg.mode} />
                                  </span>
                                  <div className="transportOptionGrid">
                                    <TransportOptionCard
                                      fromPlace={transportLeg.fromPlace}
                                      option={transportLeg}
                                      primary
                                      toPlace={transportLeg.toPlace}
                                    />
                                    {(transportLeg.alternatives ?? []).map((option) => (
                                      <TransportOptionCard
                                        fromPlace={transportLeg.fromPlace}
                                        key={`${option.mode}-${option.source}`}
                                        option={option}
                                        toPlace={transportLeg.toPlace}
                                      />
                                    ))}
                                  </div>
                                </div>
                              ) : null}
                            </Fragment>
                          );
                        })}
                      </div>
                    </article>
                  ))}
                  </section>
                </>
              ) : null}
            </div>
          ) : (
            <div className="emptyPlan">
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
          onSelect={setSelectedMapPlaceKey}
          places={mapPlaces}
          routes={mapRoutes}
          selectedKey={selectedMapPlaceKey}
        />
        </section>
      </div>
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

function categoryFromPlaceType(placeType: string): PlaceCategory {
  const normalized = placeType.toLowerCase();
  if (normalized.includes("food") || normalized.includes("restaurant")) return "food";
  if (normalized.includes("cafe") || normalized.includes("coffee")) return "cafe";
  if (normalized.includes("hotel")) return "hotel";
  if (normalized.includes("transport")) return "transport";
  if (normalized.includes("break") || normalized.includes("free")) return "free_time";
  if (normalized.includes("attraction") || normalized.includes("visit") || normalized.includes("place")) return "attraction";
  return "other";
}

function isBreakPlanItem(item: TravelPlan["days"][number]["items"][number]): boolean {
  const type = item.placeType.toLowerCase();
  return type.includes("break") || type.includes("free");
}

function hasPlanItemCoordinates(
  item: TravelPlan["days"][number]["items"][number]
): boolean {
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

function formatElapsedTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) return `${seconds} giây`;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
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

function budgetLevelLabel(level: ExplorerContext["tripSpec"]["budget"]["level"]): string {
  return { low: "Thấp", medium: "Trung bình", high: "Cao" }[level];
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
  primary = false
}: {
  option: TransportOption;
  fromPlace: string;
  toPlace: string;
  primary?: boolean;
}) {
  const lines = option.details?.lines ?? [];
  return (
    <article className={`transportOptionCard ${primary ? "primary" : "backup"}`}>
      <span className="transportOptionKind">
        {primary ? "Đề xuất" : "Phương án dự phòng"}
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
      {option.source === "here_transit_v8" && lines.length ? (
        <small>Tuyến {lines.join(", ")}</small>
      ) : null}
    </article>
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
