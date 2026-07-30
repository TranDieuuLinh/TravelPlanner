"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { APIError } from "@/lib/api";
import { searchListings } from "@/lib/marketplace";
import { createCheckoutSession } from "@/lib/orders";
import type { ListingSummary, ListingVersion } from "@/types/marketplace";

const categoryLabels: Record<string, string> = {
  budget: "Tiết kiệm",
  balanced: "Cân bằng",
  comfortable: "Thoải mái",
  food: "Ẩm thực",
  nature: "Thiên nhiên",
  family: "Gia đình",
  "creator-picks": "Creator chọn",
};

function PlayIcon() {
  return (
    <svg aria-hidden="true" fill="currentColor" viewBox="0 0 20 20">
      <path d="M6.3 4.7v10.6c0 .8.9 1.2 1.5.8l7.4-5.3a1 1 0 0 0 0-1.6L7.8 3.9c-.6-.4-1.5 0-1.5.8Z" />
    </svg>
  );
}

function HeartIcon({ filled = false }: { filled?: boolean }) {
  return (
    <svg aria-hidden="true" fill={filled ? "currentColor" : "none"} viewBox="0 0 24 24">
      <path d="M20.8 4.7a5.6 5.6 0 0 0-7.9 0L12 5.6l-.9-.9a5.6 5.6 0 0 0-7.9 7.9l.9.9L12 21.4l7.9-7.9.9-.9a5.6 5.6 0 0 0 0-7.9Z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

function EyeIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function ShareIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d="M18 8a3 3 0 1 0-2.7-4.3A3 3 0 0 0 18 8ZM6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6ZM18 16a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z" stroke="currentColor" strokeWidth="1.7" />
      <path d="m8.7 16.4 6.6-3.8M15.3 11.4 8.7 7.6" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}

function CartIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d="M4 5h2l2.3 10.5a2 2 0 0 0 2 1.5h6.9a2 2 0 0 0 1.9-1.4L21 9H7.2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
      <circle cx="10" cy="20" r="1.3" fill="currentColor" />
      <circle cx="18" cy="20" r="1.3" fill="currentColor" />
    </svg>
  );
}

function BadgeCheckIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d="m12 2.8 2.2 1.7 2.8-.2 1 2.6 2.4 1.5-.8 2.7.8 2.7-2.4 1.5-1 2.6-2.8-.2L12 21.2l-2.2-1.7-2.8.2-1-2.6-2.4-1.5.8-2.7-.8-2.7L6 6.9l1-2.6 2.8.2L12 2.8Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      <path d="m8.7 12.2 2 2 4.7-5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

function MapPinIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d="M12 21s6.5-5.5 6.5-11A6.5 6.5 0 0 0 5.5 10C5.5 15.5 12 21 12 21Z" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="10" r="2.2" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function vnd(amount: number, currency: string) {
  try {
    return new Intl.NumberFormat("vi-VN", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${amount.toLocaleString("vi-VN")} ${currency}`;
  }
}

function compactNumber(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}K`;
  return value.toLocaleString("vi-VN");
}

function numericSeed(id: string) {
  return Array.from(id).reduce((total, char) => total + char.charCodeAt(0), 0);
}

function reelStats(id: string) {
  const seed = numericSeed(id);
  return {
    likes: 5200 + (seed % 19000),
    views: 42000 + (seed % 360000),
  };
}

function getCover(version: ListingVersion) {
  return version.mediaUrls?.[0] || "https://images.unsplash.com/photo-1528127269322-539801943592?auto=format&fit=crop&w=900&q=80";
}

function buildLocationTags(version: ListingVersion) {
  const fromDays = version.previewSnapshot?.daySummaries?.slice(0, 3).map((day, index) => ({
    name: day.theme || `${version.destination} ngày ${day.day}`,
    time: `00:${String(8 + index * 11).padStart(2, "0")}`,
  })) ?? [];

  if (fromDays.length) return fromDays;
  return [
    { name: version.destination, time: "00:05" },
    { name: categoryLabels[version.category] ?? version.category, time: "00:18" },
  ];
}

export default function ReelsPage() {
  const router = useRouter();
  const { user } = useAuth();

  const [liked, setLiked] = useState<Record<string, boolean>>({});
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [buyingId, setBuyingId] = useState<string | null>(null);
  const [listings, setListings] = useState<ListingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadListings() {
      setLoading(true);
      setError("");
      try {
        const data = await searchListings({ page: 1, pageSize: 12, sort: "newest" });
        if (!cancelled) setListings(data.items);
      } catch (err) {
        if (!cancelled) setError(err instanceof APIError ? err.message : "Không thể tải video quảng bá.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadListings();
    return () => {
      cancelled = true;
    };
  }, [user]);

  const reels = useMemo(
    () => listings.map((listing) => ({ listing, stats: reelStats(listing.id), tags: buildLocationTags(listing.currentVersion) })),
    [listings]
  );

  async function handleBuy(plan: ListingSummary) {
    if (!user) {
      router.push("/login?next=/reels");
      return;
    }

    setBuyingId(plan.id);
    try {
      const session = await createCheckoutSession(plan.id, plan.currentVersion.id);
      if (session.paymentUrl) window.location.href = session.paymentUrl;
    } catch (err) {
      alert(err instanceof APIError ? err.message : "Không thể khởi tạo phiên thanh toán MoMo.");
      setBuyingId(null);
    }
  }

  async function handleShare(plan: ListingSummary) {
    const url = `${window.location.origin}/listings/${plan.id}`;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      window.prompt("Link Plan", url);
    }
  }

  return (
    <main className="pageWidth reelsPage">
      <header className="reelsHeader">
        <span><PlayIcon /> Travel Reels Marketplace</span>
        <h1>Video quảng bá gắn Plan</h1>
        <p>
          Mỗi video là một trải nghiệm thật của Creator. Bấm vào địa điểm trên video để xem vị trí
          tương ứng trong lịch trình, và mua Plan ngay không cần rời trình phát.
        </p>
      </header>

      {loading ? (
        <div className="reelsGrid" aria-label="Đang tải video quảng bá">
          {Array.from({ length: 6 }).map((_, index) => (
            <div aria-hidden="true" className="reelCard reelSkeleton" key={index}>
              <div className="reelSkeletonPoster" />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="exploreFeedback errorBanner" role="alert">
          <div>
            <strong>Chưa tải được video quảng bá</strong>
            <span>{error}</span>
          </div>
          <Link href="/explore">Về Khám phá</Link>
        </div>
      ) : reels.length === 0 ? (
        <div className="emptyState">
          <h2>Chưa có Plan để dựng video quảng bá</h2>
          <p>Khi Marketplace có listing published, tab này sẽ tự lấy Plan và hiển thị dạng video card.</p>
          <Link className="primaryBtn" href="/explore">Xem Marketplace</Link>
        </div>
      ) : (
        <div className="reelsGrid">
          {reels.map(({ listing, stats, tags }) => {
            const version = listing.currentVersion;
            const creatorName = listing.creator?.fullName || "Creator";
            const cover = getCover(version);
            const likes = stats.likes + (liked[listing.id] ? 1 : 0);
            const activeForThisCard = activeTag && tags.some((tag) => tag.name === activeTag);

            return (
              <article className="reelCard" key={listing.id}>
                <div className="reelPoster">
                  <img alt={version.title} loading="lazy" src={cover} />
                  <div className="reelShade" />

                  <button className="reelPlayButton" type="button" aria-label={`Phát video ${version.title}`}>
                    <PlayIcon />
                  </button>

                  <div className="reelActions" aria-label="Tương tác video">
                    <ActionButton
                      active={liked[listing.id]}
                      icon={<HeartIcon filled={liked[listing.id]} />}
                      label={compactNumber(likes)}
                      onClick={() => setLiked((current) => ({ ...current, [listing.id]: !current[listing.id] }))}
                    />
                    <ActionButton icon={<EyeIcon />} label={compactNumber(stats.views)} />
                    <ActionButton icon={<ShareIcon />} label="Chia sẻ" onClick={() => void handleShare(listing)} />
                  </div>

                  <div className="reelTags">
                    {tags.map((tag) => (
                      <button
                        className={activeTag === tag.name ? "active" : ""}
                        key={`${listing.id}-${tag.name}`}
                        onClick={() => setActiveTag(activeTag === tag.name ? null : tag.name)}
                        type="button"
                      >
                        <MapPinIcon /> {tag.name} · {tag.time}
                      </button>
                    ))}
                  </div>

                  <div className="reelCaption">
                    <p className="reelTitle">{version.title}</p>
                    <p className="reelText">{version.description}</p>

                    <div className="reelPlanPanel">
                      <div className="reelCreator">
                        {creatorName}
                        <BadgeCheckIcon />
                      </div>
                      <Link className="reelPlanTitle" href={`/listings/${listing.id}`}>{version.title}</Link>
                      <div className="reelPlanFooter">
                        <span>{vnd(version.priceAmount, version.priceCurrency)}</span>
                        <button disabled={buyingId === listing.id} onClick={() => void handleBuy(listing)} type="button">
                          <CartIcon /> {buyingId === listing.id ? "Đang mở MoMo" : "Mua ngay Plan"}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {activeForThisCard ? (
                  <div className="reelActiveNote">
                    <MapPinIcon />
                    <span><strong>{activeTag}</strong> đang được làm nổi bật trong lịch trình đính kèm.</span>
                    <Link href={`/listings/${listing.id}`}>Xem lịch trình</Link>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </main>
  );
}

function ActionButton({
  active = false,
  icon,
  label,
  onClick,
}: {
  active?: boolean;
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
}) {
  return (
    <button className={active ? "reelAction active" : "reelAction"} onClick={onClick} type="button">
      <span>{icon}</span>
      <small>{label}</small>
    </button>
  );
}
