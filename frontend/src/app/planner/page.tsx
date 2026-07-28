"use client";

import { Suspense, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { exploreFullIntake, type ExplorerContext, type ExploreResponse } from "@/lib/plans";

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function sendMessage() {
    const text = prompt.trim();
    if (!text) {
      setError("Nhập yêu cầu hoặc dán URL trước khi gửi. Ảnh là nội dung bổ sung.");
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
    setLoading(true);
    setError("");
    try {
      const nextExploreResult = await exploreFullIntake({
        rawRequest: text,
        images
      });
      setExploreResult(nextExploreResult);
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: `Explorer đã hiểu yêu cầu cho ${nextExploreResult.explorer.intent.destination}. Các địa điểm trích xuất đã được lưu nội bộ cho Finder.`
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
            <button className="sendButton" disabled={loading || !prompt.trim()} type="submit">
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
              </section>
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
      </section>
    </main>
  );
}
