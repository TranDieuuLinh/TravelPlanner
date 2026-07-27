"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { marketPlans, type MarketPlan } from "@/data/demo";

const filters = ["Tất cả", "Ẩm thực", "Thiên nhiên", "Biển", "Tiết kiệm"];

export default function ExplorePage() {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("Tất cả");
  const [selected, setSelected] = useState<MarketPlan | null>(null);
  const [saved, setSaved] = useState<number[]>([]);

  const visiblePlans = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("vi");
    return marketPlans.filter((plan) => {
      const matchFilter = filter === "Tất cả" || plan.tag === filter;
      const matchQuery = !needle || `${plan.title} ${plan.place} ${plan.creator}`.toLocaleLowerCase("vi").includes(needle);
      return matchFilter && matchQuery;
    });
  }, [filter, query]);

  function toggleSaved(id: number) {
    setSaved((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  return (
    <main>
      <section className="exploreHero">
        <div className="pageWidth heroGrid">
          <div>
            <span className="eyebrow light">Marketplace du lịch</span>
            <h1>Đi đâu tiếp theo?</h1>
            <p>Khám phá plan từ creator địa phương, rồi dùng AI để biến nó thành chuyến đi của riêng bạn.</p>
          </div>
          <div className="heroSearch">
            <span>⌕</span>
            <input aria-label="Tìm plan" onChange={(event) => setQuery(event.target.value)} placeholder="Tìm Đà Nẵng, food tour, biển..." value={query} />
            <button type="button">Tìm kiếm</button>
          </div>
        </div>
      </section>

      <section className="pageWidth exploreContent">
        <div className="filterRow" aria-label="Bộ lọc">
          <div>
            {filters.map((item) => (
              <button className={filter === item ? "filter active" : "filter"} key={item} onClick={() => setFilter(item)} type="button">{item}</button>
            ))}
          </div>
          <span className="demoLabel">Listing và giá đang là dữ liệu demo</span>
        </div>

        <div className="sectionTitle">
          <div><span className="eyebrow">Gợi ý cho bạn</span><h2>{visiblePlans.length} hành trình đáng thử</h2></div>
          <Link href="/planner">Tạo plan mới <span>→</span></Link>
        </div>

        <div className="planGrid">
          {visiblePlans.map((plan) => (
            <article className="planCard" key={plan.id}>
              <button className={`planCover ${plan.tone}`} onClick={() => setSelected(plan)} type="button">
                <span className="planTag">{plan.tag}</span>
                <span className="coverPlace">{plan.place}</span>
                <span className="coverDays">{plan.days} ngày</span>
              </button>
              <div className="planInfo">
                <div className="creatorLine"><span className="creatorAvatar">{plan.creator.charAt(0)}</span><span>{plan.creator}</span><span className="verified">✓</span><span className="rating">★ {plan.rating}</span></div>
                <button className="planTitle" onClick={() => setSelected(plan)} type="button">{plan.title}</button>
                <p>{plan.summary}</p>
                <div className="planMeta"><span>{plan.saves} lượt lưu</span><strong>{plan.price}</strong></div>
                <div className="cardActions">
                  <button className={saved.includes(plan.id) ? "saveButton saved" : "saveButton"} onClick={() => toggleSaved(plan.id)} type="button">{saved.includes(plan.id) ? "♥ Đã lưu" : "♡ Lưu"}</button>
                  <button className="viewButton" onClick={() => setSelected(plan)} type="button">Xem plan</button>
                </div>
              </div>
            </article>
          ))}
        </div>

        <section className="creatorCallout">
          <div><span className="eyebrow light">Dành cho creator</span><h2>Chia sẻ hành trình.<br />Tạo thêm giá trị.</h2></div>
          <div><p>Biến trải nghiệm thật thành plan có cấu trúc và quản lý listing trong hồ sơ Creator.</p><Link href="/profile?mode=creator">Mở Creator Studio →</Link></div>
        </section>
      </section>

      {selected ? (
        <div className="modalBackdrop" onMouseDown={() => setSelected(null)} role="presentation">
          <section aria-modal="true" className="planModal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
            <button aria-label="Đóng" className="modalClose" onClick={() => setSelected(null)} type="button">×</button>
            <div className={`modalCover ${selected.tone}`}><span>{selected.place}</span><strong>{selected.days} ngày</strong></div>
            <div className="modalBody">
              <span className="eyebrow">{selected.tag}</span>
              <h2>{selected.title}</h2>
              <p>{selected.summary}</p>
              <div className="modalFacts"><div><span>Creator</span><strong>{selected.creator}</strong></div><div><span>Đánh giá</span><strong>★ {selected.rating}</strong></div><div><span>Giá demo</span><strong>{selected.price}</strong></div></div>
              <div className="modalActions">
                <button disabled type="button">Thanh toán chưa triển khai</button>
                <Link href={`/planner?destination=${encodeURIComponent(selected.place)}&source=marketplace`}>Dùng trong AI Planner →</Link>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}
