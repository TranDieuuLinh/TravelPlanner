"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  createPlanFromExplorer,
  exploreFullIntake,
  type ExplorerContext,
  type ExploreResponse,
  type PlaceCategory,
  type TravelPlan
} from "@/lib/plans";
import {
  PlannerMap,
  type PlannerMapPlace,
  type PlannerMapRoute
} from "@/components/PlannerMap";

type ChatMessage = {
  id: number;
  role: "assistant" | "user";
  text: string;
};

type WorkflowStage = "idle" | "exploring" | "planning" | "ready" | "failed";

type PlanProvenance = {
  totalPlaces: number;
  urlPlaces: number;
  plannerPlaces: number;
  otherPlaces: number;
};

type TripPlaceSummary = TravelPlan["days"][number]["items"][number] & {
  day: number;
  order: number;
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

function formatBudget(result: ExplorerContext): string {
  const budget = result.tripSpec.budget;
  const formatter = new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: budget.currency,
    maximumFractionDigits: 0
  });

  if (budget.minAmount != null && budget.maxAmount != null) {
    return `${formatter.format(budget.minAmount)} – ${formatter.format(budget.maxAmount)}`;
  }
  if (budget.targetAmount != null) {
    return `${budget.isHardCap ? "Tối đa " : "Khoảng "}${formatter.format(budget.targetAmount)}`;
  }
  if (budget.maxAmount != null) {
    return `${budget.isHardCap ? "Tối đa " : "Đến "}${formatter.format(budget.maxAmount)}`;
  }
  return "Chưa có số tiền ước tính";
}

export default function PlannerPage() {
  return <Suspense fallback={<div className="routeLoading">Đang mở AI Planner…</div>}><Planner /></Suspense>;
}

function Planner() {
  const params = useSearchParams();
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

  useEffect(() => {
    const messageList = messageListRef.current;
    if (messageList) {
      messageList.scrollTo({ top: messageList.scrollHeight, behavior: "smooth" });
    }
  }, [messages, workflowStage]);

  const planProvenance = useMemo<PlanProvenance | null>(() => {
    if (!plan) return null;
    const places = plan.days.flatMap((day) =>
      day.items.filter((item) => !isBreakPlanItem(item))
    );
    const urlPlaces = places.filter(isUrlPlanItem).length;
    const plannerPlaces = places.filter(
      (item) => !isUrlPlanItem(item) && item.source === "finder_suggestion"
    ).length;

    return {
      totalPlaces: places.length,
      urlPlaces,
      plannerPlaces,
      otherPlaces: places.length - urlPlaces - plannerPlaces
    };
  }, [plan]);
  const tripPlaces = useMemo<TripPlaceSummary[]>(() => {
    if (!plan) return [];
    const seen = new Set<string>();
    let order = 0;

    return plan.days.flatMap((day) =>
      day.items.flatMap((item) => {
        if (isBreakPlanItem(item)) return [];
        const key = item.name.trim().toLocaleLowerCase("vi");
        if (seen.has(key)) return [];
        seen.add(key);
        order += 1;
        return [{ ...item, day: day.day, order }];
      })
    );
  }, [plan]);
  const mapPlaces = useMemo<PlannerMapPlace[]>(() => {
    if (plan) {
      let order = 0;
      return plan.days.flatMap((day) =>
        day.items
          .filter((item) => item.latitude != null && item.longitude != null)
          .map((item, index) => {
            order += 1;
            return {
              name: item.name,
              category: categoryFromPlaceType(item.placeType),
              address: item.timeWindow,
              latitude: item.latitude ?? null,
              longitude: item.longitude ?? null,
              notes: item.notes,
              mapKey: `plan-${day.day}-${index}-${item.name}`,
              mapOrder: order
            };
          })
      );
    }
    return [];
  }, [plan]);
  const mapRoutes = useMemo<PlannerMapRoute[]>(() => {
    if (!plan) return [];
    return plan.days.flatMap((day) =>
      day.transportLegs
        .filter((leg) => leg.geometryCoordinates.length >= 2)
        .map((leg, index) => ({
          key: `day-${day.day}-leg-${index}`,
          coordinates: leg.geometryCoordinates,
          verified: leg.verified
        }))
    );
  }, [plan]);

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
    setWorkflowStage("exploring");
    setError("");
    try {
      const nextExploreResult = await exploreFullIntake({
        rawRequest: text,
        images
      });
      setExploreResult(nextExploreResult);
      setWorkflowStage("planning");
      const nextPlan = await createPlanFromExplorer({
        context: nextExploreResult.explorer,
        intakeId: nextExploreResult.intakeId,
        userId: nextExploreResult.userId,
        allowFinderSuggestions: nextExploreResult.allowFinderSuggestions
      });
      setPlan(nextPlan);
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
    }
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
      <header className="plannerHeader pageWidth">
        <div><span className="eyebrow">AI Planner</span><h1>{exploreResult?.explorer.intent.destination ?? "Chatbot VSF"}</h1><p>Gửi prompt, URL hoặc screenshot để Explorer chuẩn hóa dữ liệu.</p></div>
        <div className="futureActions">
          <button disabled={!exploreResult && messages.length === 1} onClick={resetWorkflow} type="button">Làm mới</button>
          <button disabled type="button">Chia sẻ</button>
        </div>
      </header>

      <section className="plannerLayout pageWidth">
        <aside aria-busy={loading} className="plannerChat panel">
          <div className="panelHeading">
            <span className="aiOrb">✦</span>
            <div>
              <strong>Trợ lý VSF</strong>
              <small>{loading ? "Đang xử lý yêu cầu…" : "Sẵn sàng nhận yêu cầu"}</small>
            </div>
            <span className={`assistantStatus ${loading ? "working" : ""}`} aria-hidden="true" />
          </div>
          <ol className="chatWorkflow" aria-label="Tiến trình tạo lịch trình">
            {workflowStages.map((stage, index) => {
              const state = workflowStateFor(stage.id);
              return (
                <li className={state} key={stage.id}>
                  <span>{state === "complete" ? "✓" : index + 1}</span>
                  <div><strong>{stage.label}</strong><small>{stage.description}</small></div>
                </li>
              );
            })}
          </ol>
          <div className="chatMessages" aria-live="polite" ref={messageListRef}>
            {messages.map((message) => (
              <div className={`chatBubble ${message.role}`} key={message.id}>{message.text}</div>
            ))}
            {loading ? (
              <div className="chatBubble assistant processingMessage" role="status">
                <span className="typingDots" aria-hidden="true"><i /><i /><i /></span>
                {workflowStage === "exploring"
                  ? "Explorer đang chuẩn hóa dữ liệu đầu vào"
                  : "Planner và Finder đang dựng lịch trình"}
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
                placeholder="Nhập yêu cầu hoặc dán URL vào đây..."
                rows={4}
                value={prompt}
              />
              <input
                accept="image/*"
                aria-label="Ảnh hoặc screenshot"
                className="composerFileInput"
                multiple
                onChange={(event) => setImages(Array.from(event.target.files ?? []))}
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
                    {images.length} ảnh
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
                ) : <small>Prompt · URL · Screenshot</small>}
              </div>
            </div>
            <button className="sendButton" disabled={loading || (!prompt.trim() && images.length === 0)} type="submit">
              {loading ? "Đang đọc..." : "Gửi"}
            </button>
          </form>
          <small className="honestyNote">Enter để gửi · Shift + Enter để xuống dòng. Mỗi lần gửi tạo một intake mới.</small>
        </aside>

        <section className="itinerary panel">
          <div className="itineraryTop">
            <div>
              <span className="eyebrow">Explorer</span>
              <h2>{exploreResult ? "Tổng quan chuyến đi" : "Kết quả Explorer"}</h2>
            </div>
            <span className={`statusPill ${workflowStage}`}>{workflowStageLabel(workflowStage)}</span>
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
                  <div><span>Ngân sách</span><strong>{budgetLevelLabel(exploreResult.explorer.intent.budgetLevel)}</strong></div>
                </div>
                <div className="budgetSummary">
                  <span className="budgetIcon" aria-hidden="true">₫</span>
                  <div><span>Mức chi dự kiến</span><strong>{formatBudget(exploreResult.explorer)}</strong></div>
                  <small>Độ tin cậy {confidenceLabel(exploreResult.explorer.tripSpec.budget.confidence)}</small>
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

              <div className={`finderNotice ${exploreResult.allowFinderSuggestions ? "" : "restricted"}`}>
                <span aria-hidden="true">{exploreResult.allowFinderSuggestions ? "✦" : "✓"}</span>
                <div>
                  <strong>{exploreResult.allowFinderSuggestions ? "Có thêm gợi ý phù hợp" : "Giữ đúng nguồn bạn gửi"}</strong>
                  <p>
                    {exploreResult.allowFinderSuggestions
                      ? "Ngoài các địa điểm từ nội dung của bạn, Planner có thể bổ sung điểm phù hợp để lịch trình trọn vẹn hơn."
                      : "Lịch trình chỉ dùng các địa điểm lấy từ URL hoặc ảnh bạn đã gửi."}
                  </p>
                </div>
              </div>

              {plan ? (
                <>
                  <section className="tripPlacesSection">
                    <div className="explorerSectionHeading">
                      <div>
                        <span className="sectionMicroTitle">Đã sắp xếp vào chuyến đi</span>
                        <h3>{tripPlaces.length} địa điểm</h3>
                      </div>
                      <span className="mapReadyBadge">Xem trên bản đồ →</span>
                    </div>
                    <div className="tripPlaceList">
                      {tripPlaces.map((item) => {
                        const sourceKind = planItemSourceKind(item);
                        return (
                          <article className="tripPlaceRow" key={`${item.day}-${item.order}-${item.name}`}>
                            <span className={`placeOrder category-${categoryFromPlaceType(item.placeType)}`}>{item.order}</span>
                            <div className="placeMain">
                              <strong>{item.name}</strong>
                              <span>Ngày {item.day} · {item.timeWindow} · {placeTypeLabel(item.placeType)}</span>
                            </div>
                            <span className={`sourceBadge ${sourceKind}`}>{planItemSourceLabel(sourceKind)}</span>
                          </article>
                        );
                      })}
                    </div>
                  </section>

                  <section className="tripPlanSection">
                    <div className="explorerSectionHeading">
                      <div>
                        <span className="sectionMicroTitle">Lịch trình gợi ý</span>
                        <h3>{plan.title}</h3>
                      </div>
                    </div>
                  {planProvenance ? (
                    <div className="planProvenance" aria-label="Nguồn địa điểm trong lịch trình">
                      <div>
                        <strong>{planProvenance.urlPlaces}</strong>
                        <span>Từ nguồn của bạn</span>
                      </div>
                      <div>
                        <strong>{planProvenance.plannerPlaces}</strong>
                        <span>VSF gợi ý thêm</span>
                      </div>
                      {planProvenance.otherPlaces > 0 ? (
                        <div>
                          <strong>{planProvenance.otherPlaces}</strong>
                          <span>Nguồn khác</span>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {plan.days.map((day) => (
                    <article className="explorerDayCard" key={day.day}>
                      <div className="dayCardHeading">
                        <span><small>Ngày</small>{day.day}</span>
                        <div><strong>{day.theme}</strong><small>{day.items.length} hoạt động</small></div>
                      </div>
                      <div className="dayTimeline">
                        {day.items.map((item, itemIndex) => {
                          const sourceKind = planItemSourceKind(item);
                          return (
                            <div className={`dayTimelineItem ${isBreakPlanItem(item) ? "break" : ""}`} key={`${day.day}-${itemIndex}`}>
                              <time>{item.timeWindow}</time>
                              <span className="dayTimelineDot" aria-hidden="true" />
                              <div>
                                <strong>{item.name}</strong>
                                {item.notes ? <p>{item.notes}</p> : null}
                                {!isBreakPlanItem(item) ? <span className={`sourceBadge ${sourceKind}`}>{planItemSourceLabel(sourceKind)}</span> : null}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      {day.transportLegs.length ? (
                        <details className="transportDetails">
                          <summary>{day.transportLegs.length} chặng di chuyển</summary>
                          {day.transportLegs.map((leg, legIndex) => (
                            <p key={`leg-${day.day}-${legIndex}`}>
                              {transportModeLabel(leg.mode)} · {leg.fromPlace} → {leg.toPlace} · {leg.estimatedDurationMinutes} phút
                            </p>
                          ))}
                        </details>
                      ) : null}
                    </article>
                  ))}
                  </section>
                </>
              ) : null}
              {exploreResult.explorer.missingInfoQuestions.length ? (
                <section className="clarificationSection">
                  <span className="sectionMicroTitle">Giúp lịch trình sát ý bạn hơn</span>
                  <h3>Mình cần hỏi thêm</h3>
                  {exploreResult.explorer.missingInfoQuestions.map((question) => (
                    <p className="questionItem" key={question}><span aria-hidden="true">?</span>{question}</p>
                  ))}
                </section>
              ) : null}
              {exploreResult.explorer.assumptions.length ? (
                <details className="explorerDetails">
                  <summary>Giả định và thông tin nguồn</summary>
                  <div>
                    {exploreResult.explorer.assumptions.map((assumption) => <p key={assumption}>{assumption}</p>)}
                    <p>Mã dữ liệu: {exploreResult.intakeId}</p>
                    <p>Place search data © OpenStreetMap contributors.</p>
                  </div>
                </details>
              ) : null}
            </div>
          ) : (
            <div className="emptyPlan"><span>⌖</span><h3>Chuyến đi của bạn bắt đầu ở đây</h3><p>Gửi điểm đến, URL hoặc ảnh. Explorer sẽ gom thông tin thành một bản tóm tắt dễ xem.</p></div>
          )}
        </section>

        <PlannerMap
          onSelect={setSelectedMapPlaceKey}
          places={mapPlaces}
          routes={mapRoutes}
          selectedKey={selectedMapPlaceKey}
        />
      </section>
    </main>
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

function isUrlPlanItem(item: TravelPlan["days"][number]["items"][number]): boolean {
  return (
    item.sourceOrder != null ||
    item.sourceRefs.some((sourceRef) => /^https?:\/\//i.test(sourceRef))
  );
}

function isBreakPlanItem(item: TravelPlan["days"][number]["items"][number]): boolean {
  const type = item.placeType.toLowerCase();
  return type.includes("break") || type.includes("free");
}

function planItemSourceKind(
  item: TravelPlan["days"][number]["items"][number]
): "url" | "planner" | "other" {
  if (isUrlPlanItem(item)) return "url";
  if (item.source === "finder_suggestion") return "planner";
  return "other";
}

function planItemSourceLabel(source: "url" | "planner" | "other"): string {
  if (source === "url") return "Nguồn của bạn";
  if (source === "planner") return "VSF gợi ý";
  return "Nguồn khác";
}

function workflowStageLabel(stage: WorkflowStage): string {
  const labels: Record<WorkflowStage, string> = {
    idle: "Chưa bắt đầu",
    exploring: "Đang đọc",
    planning: "Đang xếp lịch",
    ready: "Sẵn sàng",
    failed: "Cần thử lại"
  };
  return labels[stage];
}

function budgetLevelLabel(level: ExplorerContext["intent"]["budgetLevel"]): string {
  return { budget: "Tiết kiệm", medium: "Cân bằng", high: "Thoải mái" }[level];
}

function confidenceLabel(level: ExplorerContext["tripSpec"]["budget"]["confidence"]): string {
  return { low: "thấp", medium: "vừa", high: "cao" }[level];
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
  if (normalized.includes("bike") || normalized.includes("motor")) return "Xe máy";
  if (normalized.includes("car") || normalized.includes("taxi")) return "Ô tô";
  if (normalized.includes("bus")) return "Xe buýt";
  return mode;
}
