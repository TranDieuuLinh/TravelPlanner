"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { createPlan, type TravelPlan } from "@/lib/plans";

export default function PlannerPage() {
  return <Suspense fallback={<div className="routeLoading">Đang mở AI Planner…</div>}><Planner /></Suspense>;
}

function Planner() {
  const params = useSearchParams();
  const [destination, setDestination] = useState(params.get("destination") ?? "");
  const [days, setDays] = useState(3);
  const [interests, setInterests] = useState("ẩm thực, văn hóa địa phương");
  const [plan, setPlan] = useState<TravelPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function generate() {
    if (!destination.trim()) {
      setError("Hãy nhập điểm đến trước.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      setPlan(await createPlan({ destination: destination.trim(), days, interests: interests.split(",").map((item) => item.trim()).filter(Boolean) }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Có lỗi xảy ra.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="plannerPage">
      <header className="plannerHeader pageWidth">
        <div><span className="eyebrow">AI Planner</span><h1>{destination || "Chuyến đi mới"}</h1><p>Lập lịch trình có cấu trúc từ sở thích của bạn.</p></div>
        <div className="futureActions"><button disabled type="button">Mời thành viên</button><button disabled type="button">Chia sẻ</button></div>
      </header>

      <section className="plannerLayout pageWidth">
        <aside className="plannerSetup panel">
          <div className="panelHeading"><span className="aiOrb">✦</span><div><strong>Trợ lý VSF</strong><small>Kết nối Planner API</small></div></div>
          <div className="assistantMessage">Bạn muốn đi đâu? Mình sẽ tạo lịch trình theo từng ngày và kiểm tra tính khả thi cơ bản.</div>
          <label>Điểm đến<input onChange={(event) => setDestination(event.target.value)} placeholder="Đà Nẵng, Hà Giang..." value={destination} /></label>
          <div className="formSplit">
            <label>Số ngày<input max={30} min={1} onChange={(event) => setDays(Number(event.target.value))} type="number" value={days} /></label>
            <label>Ngân sách<select defaultValue="balanced" disabled><option value="balanced">Cân bằng</option></select></label>
          </div>
          <label>Sở thích<textarea onChange={(event) => setInterests(event.target.value)} rows={3} value={interests} /></label>
          {error ? <p className="formError">{error}</p> : null}
          <button className="generateButton" disabled={loading} onClick={generate} type="button">{loading ? "Đang tạo lịch trình…" : "✦ Tạo lịch trình"}</button>
          <small className="honestyNote">AI hiện dùng StubLLM và plan được lưu trong bộ nhớ backend.</small>
        </aside>

        <section className="itinerary panel">
          <div className="itineraryTop"><div><span className="eyebrow">Lịch trình</span><h2>{plan?.title ?? "Plan của bạn"}</h2></div><span className="statusPill">{plan ? plan.kind : "Chưa tạo"}</span></div>
          {plan ? (
            <div className="daysList">
              {plan.days.map((day) => (
                <article className="dayBlock" key={day.day}>
                  <div className="dayNumber"><span>Ngày</span><strong>{day.day}</strong></div>
                  <div className="dayContent"><h3>{day.theme}</h3>{day.items.map((item, index) => <div className="timelineItem" key={`${day.day}-${index}`}><span className="timelineDot" /><div><small>{item.timeWindow}</small><strong>{item.name}</strong><p>{item.notes || item.placeType}</p></div></div>)}</div>
                </article>
              ))}
            </div>
          ) : (
            <div className="emptyPlan"><span>✦</span><h3>Bắt đầu bằng một điểm đến</h3><p>Plan được tạo từ backend thật sẽ xuất hiện tại đây.</p></div>
          )}
        </section>

        <aside className="mapPanel panel">
          <div className="mapToolbar"><strong>Bản đồ hành trình</strong><span>Demo</span></div>
          <div className="fakeMap">
            <div className="mapRoad one" /><div className="mapRoad two" /><div className="mapWater" />
            {[1, 2, 3, 4].map((item) => <span className={`mapPin pin${item}`} key={item}>{item}</span>)}
            <p>Chưa kết nối map provider</p>
          </div>
          <button className="routeButton" disabled type="button">Tối ưu tuyến đường · Sắp tới</button>
        </aside>
      </section>
    </main>
  );
}
