"use client";

import { useEffect, useRef, useState } from "react";

type PlannerDiscoveryPanelProps = {
  planning?: boolean;
};

const discoveryItems = [
  {
    title: "Một sáng thật chậm ở Hội An",
    location: "Hội An · Quảng Nam",
    kind: "Reel",
    image: "https://images.unsplash.com/photo-1559592413-7cec4d0cae2b?auto=format&fit=crop&w=900&q=82",
    media: "https://videos.pexels.com/video-files/3015510/3015510-hd_1920_1080_24fps.mp4"
  },
  {
    title: "Những món nhất định phải thử ở Hà Nội",
    location: "Phố cổ · Hà Nội",
    kind: "Bài viết",
    image: "https://images.unsplash.com/photo-1509030450996-dd1a26dda07a?auto=format&fit=crop&w=900&q=82",
    media: "https://images.unsplash.com/photo-1509030450996-dd1a26dda07a?auto=format&fit=crop&w=1400&q=88"
  },
  {
    title: "Săn mây trên cung đường Hà Giang",
    location: "Mèo Vạc · Hà Giang",
    kind: "Reel",
    image: "https://images.unsplash.com/photo-1528127269322-539801943592?auto=format&fit=crop&w=900&q=82",
    media: "https://videos.pexels.com/video-files/2169880/2169880-hd_1920_1080_30fps.mp4"
  },
  {
    title: "Cuối tuần xanh ở Ninh Bình",
    location: "Tràng An · Ninh Bình",
    kind: "Bài viết",
    image: "https://images.unsplash.com/photo-1521993117367-b7f70ccd029d?auto=format&fit=crop&w=900&q=82",
    media: "https://images.unsplash.com/photo-1521993117367-b7f70ccd029d?auto=format&fit=crop&w=1400&q=88"
  },
  {
    title: "Đà Lạt qua những quán cà phê nhỏ",
    location: "Đà Lạt · Lâm Đồng",
    kind: "Reel",
    image: "https://images.unsplash.com/photo-1518005020951-eccb494ad742?auto=format&fit=crop&w=900&q=82",
    media: "https://videos.pexels.com/video-files/3571264/3571264-hd_1920_1080_30fps.mp4"
  },
  {
    title: "Một ngày đi dọc bán đảo Sơn Trà",
    location: "Sơn Trà · Đà Nẵng",
    kind: "Bài viết",
    image: "https://images.unsplash.com/photo-1557750255-c76072a7aad1?auto=format&fit=crop&w=900&q=82",
    media: "https://images.unsplash.com/photo-1557750255-c76072a7aad1?auto=format&fit=crop&w=1400&q=88"
  }
];

export function PlannerDiscoveryPanel({ planning = false }: PlannerDiscoveryPanelProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [saved, setSaved] = useState<Record<number, boolean>>({});
  const touchStartY = useRef<number | null>(null);
  const wheelLocked = useRef(false);
  const activeItem = activeIndex === null ? null : discoveryItems[activeIndex];

  function moveViewer(direction: -1 | 1) {
    setActiveIndex((current) => current === null
      ? null
      : Math.min(Math.max(current + direction, 0), discoveryItems.length - 1));
  }

  useEffect(() => {
    if (activeIndex === null) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setActiveIndex(null);
      if (event.key === "ArrowDown") moveViewer(1);
      if (event.key === "ArrowUp") moveViewer(-1);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [activeIndex]);

  function handleWheel(event: React.WheelEvent) {
    if (Math.abs(event.deltaY) < 24 || wheelLocked.current) return;
    wheelLocked.current = true;
    moveViewer(event.deltaY > 0 ? 1 : -1);
    window.setTimeout(() => {
      wheelLocked.current = false;
    }, 420);
  }

  function handleTouchEnd(event: React.TouchEvent) {
    if (touchStartY.current === null) return;
    const distance = touchStartY.current - event.changedTouches[0].clientY;
    if (Math.abs(distance) > 50) moveViewer(distance > 0 ? 1 : -1);
    touchStartY.current = null;
  }

  return (
    <aside aria-label="Khám phá cảm hứng du lịch" className="plannerDiscovery">
      <header className="plannerDiscoveryHeader">
        <div>
          <span>{planning ? "Trong lúc chờ" : "Dành cho bạn"}</span>
          <h2>Khám phá</h2>
        </div>
        <button type="button">Xem tất cả</button>
      </header>

      {planning ? (
        <div className="plannerDiscoveryNotice" role="status">
          <span className="plannerDiscoveryNoticeDot" />
          Planner đang chạy nền. Bạn có thể xem tiếp và rời trang này bất kỳ lúc nào.
        </div>
      ) : null}

      <div className="plannerDiscoveryGrid">
        {discoveryItems.map((item, index) => (
          <article
            aria-label={`Mở ${item.kind} ${item.title}`}
            className={`plannerDiscoveryCard ${index === 0 ? "featured" : ""}`}
            key={item.title}
            onClick={() => setActiveIndex(index)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setActiveIndex(index);
              }
            }}
            role="button"
            tabIndex={0}
          >
            <img alt="" loading={index < 2 ? "eager" : "lazy"} src={item.image} />
            <div className="plannerDiscoveryShade" />
            <div className="plannerDiscoveryCardTop">
              <span className="plannerDiscoveryKind">
                {item.kind === "Reel" ? <i aria-hidden="true">▶</i> : <i aria-hidden="true">▤</i>}
                {item.kind}
              </span>
              <button
                aria-label={`${saved[index] ? "Bỏ lưu" : "Lưu"} ${item.title}`}
                className={saved[index] ? "saved" : ""}
                onClick={(event) => {
                  event.stopPropagation();
                  setSaved((current) => ({ ...current, [index]: !current[index] }));
                }}
                type="button"
              >
                {saved[index] ? "♥" : "♡"}
              </button>
            </div>
            <div className="plannerDiscoveryCopy">
              <h3>{item.title}</h3>
              <p><span aria-hidden="true">⌖</span>{item.location}</p>
            </div>
          </article>
        ))}
      </div>

      {activeItem ? (
        <div
          aria-label="Feed cảm hứng du lịch"
          aria-modal="true"
          className="promotionViewer plannerDiscoveryViewer"
          onTouchEnd={handleTouchEnd}
          onTouchStart={(event) => {
            touchStartY.current = event.touches[0].clientY;
          }}
          onWheel={handleWheel}
          role="dialog"
        >
          <button aria-label="Đóng feed" className="promotionViewerClose" onClick={() => setActiveIndex(null)} type="button">×</button>
          <button aria-label="Nội dung trước" className="promotionViewerNav previous" disabled={activeIndex === 0} onClick={() => moveViewer(-1)} type="button">↑</button>
          <button aria-label="Nội dung tiếp theo" className="promotionViewerNav next" disabled={activeIndex === discoveryItems.length - 1} onClick={() => moveViewer(1)} type="button">↓</button>

          <article className="promotionViewerStage" key={activeItem.title}>
            {activeItem.kind === "Reel" ? (
              <video autoPlay controls loop muted playsInline poster={activeItem.image} src={activeItem.media} />
            ) : (
              <img alt={activeItem.title} src={activeItem.media} />
            )}
            <div className="promotionViewerShade" />
            <span className={`reelContentType viewerType ${activeItem.kind === "Reel" ? "video" : "post"}`}>
              {activeItem.kind === "Reel" ? "Video" : "Ảnh"}
            </span>
            <span className="promotionViewerCount">{(activeIndex ?? 0) + 1} / {discoveryItems.length}</span>
            <div className="promotionViewerCopy">
              <span>{activeItem.location}</span>
              <h2>{activeItem.title}</h2>
              <p>Vuốt hoặc cuộn dọc để tiếp tục khám phá.</p>
            </div>
          </article>
          <span className="promotionViewerHint">Cuộn, vuốt hoặc dùng phím ↑ ↓ để xem tiếp</span>
        </div>
      ) : null}
    </aside>
  );
}
