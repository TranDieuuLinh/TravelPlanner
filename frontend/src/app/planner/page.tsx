"use client";

import { Suspense, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  runPlannerIntake,
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
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
    setError("");
    try {
      const result = await runPlannerIntake({
        rawRequest: text,
        images
      });
      const nextExploreResult = result.explore;
      setExploreResult(nextExploreResult);
      setPlan(result.plan);
      setSelectedMapPlaceKey(null);
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: `Explorer đã hiểu yêu cầu cho ${nextExploreResult.explorer.intent.destination}. Planner và Finder đã tạo lịch trình từ Explorer context cùng dữ liệu đã lưu.`
        }
      ]);
      setImages([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Có lỗi xảy ra.";
      setError(message);
      setMessages((current) => [...current, { id: Date.now() + 1, role: "assistant", text: message }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="plannerPage">
      <header className="plannerHeader pageWidth">
        <div><span className="eyebrow">AI Planner</span><h1>{exploreResult?.explorer.intent.destination ?? "Chatbot VSF"}</h1><p>Gửi prompt, URL hoặc screenshot để Explorer chuẩn hóa dữ liệu.</p></div>
        <div className="futureActions"><button disabled type="button">Mời thành viên</button><button disabled type="button">Chia sẻ</button></div>
      </header>

      <section className="plannerLayout pageWidth">
        <aside className="plannerChat panel">
          <div className="panelHeading"><span className="aiOrb">✦</span><div><strong>Trợ lý VSF</strong><small>Kết nối Planner API</small></div></div>
          <div className="chatMessages" aria-live="polite">
            {messages.map((message) => (
              <div className={`chatBubble ${message.role}`} key={message.id}>{message.text}</div>
            ))}
          </div>
          {error ? <p className="formError">{error}</p> : null}
          <form className="chatComposer" onSubmit={(event) => { event.preventDefault(); void sendMessage(); }}>
            <div className="composerBox">
              <textarea
                aria-label="Tin nhắn lập lịch trình"
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
          <small className="honestyNote">Explorer tự nhận biết prompt, URL hoặc ảnh theo nội dung bạn gửi.</small>
        </aside>

        <section className="itinerary panel">
          <div className="itineraryTop"><div><span className="eyebrow">Explorer</span><h2>{exploreResult ? "Dữ liệu đã trích xuất" : "Kết quả Explorer"}</h2></div><span className="statusPill">{exploreResult ? "ready" : "waiting"}</span></div>
          {exploreResult ? (
            <div className="exploreResult">
              <section>
                <h3>{exploreResult.explorer.intent.destination}</h3>
                <p>{exploreResult.explorer.tripSpec.days} ngày · {exploreResult.explorer.tripSpec.partySize} người · {exploreResult.explorer.intent.budgetLevel}</p>
                <p>{formatBudget(exploreResult.explorer)} · độ tin cậy {exploreResult.explorer.tripSpec.budget.confidence}</p>
                <div className="tagRow">
                  {exploreResult.explorer.intent.interests.map((interest) => <span key={interest}>{interest}</span>)}
                </div>
                <p className="mutedText">
                  {exploreResult.explorer.preferenceSnapshot.signals.length} tín hiệu sở thích trong intake ·{" "}
                  {exploreResult.explorer.preferenceSnapshot.effectiveProfile.observationCount} quan sát dài hạn
                </p>
              </section>
              <section>
                <h3>Workflow hiện tại</h3>
                <p className="workflowStep"><strong>1. Explorer</strong><span>Chuẩn hóa yêu cầu, URL và ảnh thành intent/trip spec.</span></p>
                <p className="workflowStep"><strong>2. Place intake</strong><span>Candidate được resolve và lưu nội bộ theo intakeId để giữ provenance.</span></p>
                <p className="workflowStep"><strong>3. Planner + Finder</strong><span>Tạo macro plan, xếp địa điểm đã lưu và kiểm tra kết quả.</span></p>
              </section>
              <section>
                <h3>Giả định Explorer</h3>
                {exploreResult.explorer.assumptions.length ? exploreResult.explorer.assumptions.map((assumption) => <p className="questionItem" key={assumption}>{assumption}</p>) : <p className="mutedText">Không có giả định bổ sung.</p>}
              </section>
              {plan ? (
                <section>
                  <h3>{plan.title}</h3>
                  {plan.days.map((day) => (
                    <article className="dayBlock" key={day.day}>
                      <strong>Ngày {day.day}: {day.theme}</strong>
                      {day.items.map((item, itemIndex) => (
                        <p key={`${day.day}-${itemIndex}`}>{item.timeWindow} · {item.name}</p>
                      ))}
                      {day.transportLegs.map((leg, legIndex) => (
                        <p className="mutedText" key={`leg-${day.day}-${legIndex}`}>
                          {leg.fromPlace} → {leg.toPlace} · {leg.estimatedDurationMinutes} phút · {leg.mode}
                        </p>
                      ))}
                    </article>
                  ))}
                </section>
              ) : null}
              <section>
                <h3>Câu hỏi còn thiếu</h3>
                {exploreResult.explorer.missingInfoQuestions.length ? exploreResult.explorer.missingInfoQuestions.map((question) => <p className="questionItem" key={question}>{question}</p>) : <p className="mutedText">Không có câu hỏi bổ sung.</p>}
              </section>
              <section>
                <h3>Intake</h3>
                <p className="mutedText">{exploreResult.intakeId}</p>
                <p className="mutedText">Place search data © OpenStreetMap contributors.</p>
              </section>
            </div>
          ) : (
            <div className="emptyPlan"><span>✦</span><h3>Bắt đầu bằng một yêu cầu</h3><p>Kết quả Explorer từ backend sẽ xuất hiện tại đây.</p></div>
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
