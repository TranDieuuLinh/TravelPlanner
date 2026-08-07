"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "@/features/auth/components/AuthProvider";
import { mockExplorePosts } from "@/features/explore/demo";
import { APIError } from "@/shared/api/client";
import { searchListings } from "@/features/marketplace/api";
import { createCheckoutSession } from "@/features/orders/api";
import { getTravelGroups, joinTravelGroup } from "@/features/travel-groups/api";
import { getExplorePosts } from "@/features/profile/api";
import type { ListingSummary, ListingVersion } from "@/features/marketplace/types";
import type { ExplorePost } from "@/features/profile/types";
import type { TravelGroup } from "@/features/travel-groups/types";

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

function SearchIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="m16 16 4 4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  );
}

function MembersIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <circle cx="9" cy="8" r="3" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="17" cy="9" r="2.3" stroke="currentColor" strokeWidth="1.7" />
      <path d="M3.5 19c.5-3.5 2.3-5.3 5.5-5.3s5 1.8 5.5 5.3M14.4 14.2c3.2-.6 5.2 1 5.8 4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
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

type PromotionType = "video" | "post";
type TravelGroupFilter = "all" | "mine";

type ViewerItem = {
  id: string;
  type: PromotionType;
  mediaUrl: string;
  title: string;
  description: string;
  authorName: string;
  listing?: ListingSummary;
};

function getPromotionType(version: ListingVersion): PromotionType {
  const mediaUrl = version.mediaUrls?.[0] ?? "";
  return /\.(mp4|webm|ogg|mov|m4v)(?:[?#]|$)/i.test(mediaUrl) ? "video" : "post";
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
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const [cartIds, setCartIds] = useState<string[]>([]);
  const [cartOpen, setCartOpen] = useState(false);
  const [listings, setListings] = useState<ListingSummary[]>([]);
  const [listingCache, setListingCache] = useState<Record<string, ListingSummary>>({});
  const [reelQuery, setReelQuery] = useState("");
  const [listingQuery, setListingQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [travelGroups, setTravelGroups] = useState<TravelGroup[]>([]);
  const [groupQuery, setGroupQuery] = useState("");
  const [groupFilter, setGroupFilter] = useState<TravelGroupFilter>("all");
  const [groupsLoading, setGroupsLoading] = useState(true);
  const [groupsError, setGroupsError] = useState("");
  const [communityPosts, setCommunityPosts] = useState<ExplorePost[]>([]);
  const [communityLoading, setCommunityLoading] = useState(true);
  const [joiningGroupId, setJoiningGroupId] = useState<number | null>(null);
  const touchStartY = useRef<number | null>(null);
  const wheelLocked = useRef(false);

  useEffect(() => {
    const debounceId = window.setTimeout(() => {
      setListingQuery(reelQuery.trim());
    }, 300);
    return () => window.clearTimeout(debounceId);
  }, [reelQuery]);

  useEffect(() => {
    let cancelled = false;

    async function loadListings() {
      setLoading(true);
      setError("");
      try {
        const data = await searchListings({
          page: 1,
          pageSize: 12,
          query: listingQuery || undefined,
          sort: "newest",
        });
        if (!cancelled) {
          setListings(data.items);
          setListingCache((current) => {
            const next = { ...current };
            data.items.forEach((listing) => {
              next[listing.id] = listing;
            });
            return next;
          });
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof APIError ? err.message : "Không thể tải nội dung quảng bá.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadListings();
    return () => {
      cancelled = true;
    };
  }, [listingQuery, user]);

  useEffect(() => {
    let cancelled = false;

    async function loadTravelGroups() {
      setGroupsLoading(true);
      setGroupsError("");
      try {
        const data = await getTravelGroups();
        if (!cancelled) setTravelGroups(data.items);
      } catch (err) {
        if (!cancelled) {
          setGroupsError(err instanceof APIError ? err.message : "Không thể tải nhóm du lịch.");
        }
      } finally {
        if (!cancelled) setGroupsLoading(false);
      }
    }

    void loadTravelGroups();
    return () => {
      cancelled = true;
    };
  }, [user]);

  useEffect(() => {
    let cancelled = false;
    setCommunityLoading(true);
    void getExplorePosts()
      .then((posts) => {
        if (!cancelled) setCommunityPosts([...mockExplorePosts, ...posts]);
      })
      .catch(() => {
        if (!cancelled) setCommunityPosts(mockExplorePosts);
      })
      .finally(() => {
        if (!cancelled) setCommunityLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  useEffect(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem("travelplanner-promotion-cart") ?? "[]");
      if (Array.isArray(saved)) setCartIds(saved.filter((id): id is string => typeof id === "string"));
    } catch {
      setCartIds([]);
    }
  }, []);

  const reels = useMemo(
    () => listings.map((listing) => ({
      listing,
      stats: reelStats(listing.id),
      tags: buildLocationTags(listing.currentVersion),
      type: getPromotionType(listing.currentVersion),
    })),
    [listings]
  );

  const visibleReels = reels;

  const visibleCommunityPosts = useMemo(() => {
    const query = listingQuery.toLocaleLowerCase("vi");
    if (!query) return communityPosts;
    return communityPosts.filter((post) =>
      [post.caption, post.locationName, post.authorName]
        .some((value) => value.toLocaleLowerCase("vi").includes(query))
    );
  }, [communityPosts, listingQuery]);

  const visibleTravelGroups = useMemo(() => {
    const normalizedQuery = groupQuery.trim().toLocaleLowerCase("vi");
    return travelGroups.filter((group) => {
      if (groupFilter === "mine" && !group.isMember) return false;
      return !normalizedQuery
        || group.countryName.toLocaleLowerCase("vi").includes(normalizedQuery);
    });
  }, [groupFilter, groupQuery, travelGroups]);

  const cartListings = useMemo(
    () => cartIds.map((id) => listingCache[id]).filter((item): item is ListingSummary => Boolean(item)),
    [cartIds, listingCache]
  );

  const viewerItems = useMemo<ViewerItem[]>(() => {
    const communityItems = visibleCommunityPosts.map((post) => ({
      id: `community-${post.id}`,
      type: post.contentType === "reel" ? "video" as const : "post" as const,
      mediaUrl: post.mediaUrl,
      title: post.locationName,
      description: post.caption,
      authorName: post.authorName,
    }));
    const marketplaceItems = visibleReels.map(({ listing, type }) => ({
      id: `listing-${listing.id}`,
      type,
      mediaUrl: type === "video" ? listing.currentVersion.mediaUrls[0] : getCover(listing.currentVersion),
      title: listing.currentVersion.title,
      description: listing.currentVersion.description,
      authorName: listing.creator?.fullName || "Creator",
      listing,
    }));

    const mixedItems: ViewerItem[] = [];
    const itemCount = Math.max(communityItems.length, marketplaceItems.length);
    for (let index = 0; index < itemCount; index += 1) {
      if (communityItems[index]) mixedItems.push(communityItems[index]);
      if (marketplaceItems[index]) mixedItems.push(marketplaceItems[index]);
    }
    return mixedItems;
  }, [visibleCommunityPosts, visibleReels]);

  const activeViewer = viewerIndex === null ? null : viewerItems[viewerIndex];
  const viewerOpen = viewerIndex !== null;

  useEffect(() => {
    window.dispatchEvent(new CustomEvent("travelplanner:reel-viewer-change", {
      detail: { open: viewerOpen },
    }));

    return () => {
      if (viewerOpen) {
        window.dispatchEvent(new CustomEvent("travelplanner:reel-viewer-change", {
          detail: { open: false },
        }));
      }
    };
  }, [viewerOpen]);

  useEffect(() => {
    if (viewerIndex === null) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setViewerIndex(null);
      if (event.key === "ArrowDown") setViewerIndex((current) => current === null ? null : Math.min(current + 1, viewerItems.length - 1));
      if (event.key === "ArrowUp") setViewerIndex((current) => current === null ? null : Math.max(current - 1, 0));
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [viewerIndex, viewerItems.length]);

  function persistCart(nextIds: string[]) {
    setCartIds(nextIds);
    window.localStorage.setItem("travelplanner-promotion-cart", JSON.stringify(nextIds));
  }

  function toggleCart(planId: string) {
    const nextIds = cartIds.includes(planId)
      ? cartIds.filter((id) => id !== planId)
      : [...cartIds, planId];
    persistCart(nextIds);
  }

  function moveViewer(direction: -1 | 1) {
    setViewerIndex((current) => {
      if (current === null) return null;
      return Math.min(Math.max(current + direction, 0), viewerItems.length - 1);
    });
  }

  function openViewer(itemId: string) {
    const index = viewerItems.findIndex((item) => item.id === itemId);
    if (index >= 0) setViewerIndex(index);
  }

  function handleViewerWheel(event: React.WheelEvent) {
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

  async function handleJoinGroup(group: TravelGroup) {
    if (group.isMember) return;
    if (!user) {
      router.push("/login?next=/reels");
      return;
    }

    setJoiningGroupId(group.id);
    try {
      const membership = await joinTravelGroup(group.id);
      setTravelGroups((current) => current.map((item) => item.id === group.id
        ? { ...item, isMember: membership.isMember, memberCount: membership.memberCount }
        : item));
    } catch (err) {
      setGroupsError(err instanceof APIError ? err.message : "Chưa thể tham gia nhóm.");
    } finally {
      setJoiningGroupId(null);
    }
  }

  return (
    <main className="pageWidth reelsPage">
      <section aria-labelledby="travel-groups-title" className="travelGroupsSection">
        <div className="travelGroupsHeading">
          <div>
            <h2 id="travel-groups-title">Nhóm du lịch</h2>
          </div>
          <div className="travelGroupControls">
            <div aria-label="Lọc nhóm du lịch" className="travelGroupFilters" role="group">
              <button
                aria-pressed={groupFilter === "all"}
                className={groupFilter === "all" ? "active" : ""}
                onClick={() => setGroupFilter("all")}
                type="button"
              >
                Tất cả
              </button>
              <button
                aria-pressed={groupFilter === "mine"}
                className={groupFilter === "mine" ? "active" : ""}
                onClick={() => setGroupFilter("mine")}
                type="button"
              >
                Nhóm của tôi
              </button>
            </div>
            <label className="travelGroupSearch">
              <SearchIcon />
              <span className="srOnly">Tìm theo tên quốc gia</span>
              <input
                onChange={(event) => setGroupQuery(event.target.value)}
                placeholder="Tìm tên quốc gia..."
                type="search"
                value={groupQuery}
              />
            </label>
          </div>
        </div>

        {groupsError ? <p className="travelGroupsError" role="alert">{groupsError}</p> : null}

        {groupsLoading ? (
          <div aria-label="Đang tải nhóm du lịch" className="travelGroupsRail">
            {Array.from({ length: 5 }).map((_, index) => (
              <div aria-hidden="true" className="travelGroupCard travelGroupSkeleton" key={index} />
            ))}
          </div>
        ) : visibleTravelGroups.length ? (
          <div className="travelGroupsRail" tabIndex={0}>
            {visibleTravelGroups.map((group) => (
              <article className="travelGroupCard" key={group.id}>
                <div aria-hidden="true" className="travelGroupArt">
                  <img alt="" loading="lazy" src="/images/penguin-globe-logo.png" />
                </div>
                <div className="travelGroupShade" />
                <Link
                  aria-label={`Mở nhóm ${group.name}`}
                  className="travelGroupOpen"
                  href={`/groups/${group.id}`}
                />
                <span className="travelGroupPublic">Nhóm công khai</span>
                <div className="travelGroupInfo">
                  <h3>{group.countryName}</h3>
                  <div>
                    <span><MembersIcon /> {group.memberCount.toLocaleString("vi-VN")} thành viên</span>
                    <button
                      className={group.isMember ? "isMember" : ""}
                      disabled={group.isMember || joiningGroupId === group.id}
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleJoinGroup(group);
                      }}
                      type="button"
                    >
                      {joiningGroupId === group.id ? "Đang tham gia..." : group.isMember ? "✓ Thành viên" : "Tham gia"}
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="travelGroupsEmpty">
            {groupFilter === "mine" && !user ? (
              <>
                <span>Đăng nhập để xem các nhóm bạn đã tham gia.</span>
                <Link href="/login?next=/reels">Đăng nhập</Link>
              </>
            ) : groupFilter === "mine" ? (
              groupQuery.trim()
                ? `Không tìm thấy nhóm đã tham gia phù hợp với “${groupQuery}”.`
                : "Bạn chưa tham gia nhóm du lịch nào."
            ) : groupQuery.trim() ? (
              `Không tìm thấy quốc gia phù hợp với “${groupQuery}”.`
            ) : (
              "Chưa có nhóm du lịch công khai."
            )}
          </div>
        )}
      </section>

      <header className="reelsHeader">
        <h1>Khám phá</h1>
        <form
          className="reelSearch"
          onSubmit={(event) => {
            event.preventDefault();
            setListingQuery(reelQuery.trim());
          }}
          role="search"
        >
          <SearchIcon />
          <label className="srOnly" htmlFor="reel-search">Tìm kiếm reels</label>
          <input
            id="reel-search"
            onChange={(event) => setReelQuery(event.target.value)}
            placeholder="Tìm reels theo điểm đến, tiêu đề..."
            type="search"
            value={reelQuery}
          />
          {reelQuery ? (
            <button
              aria-label="Xóa nội dung tìm kiếm reels"
              onClick={() => {
                setReelQuery("");
                setListingQuery("");
              }}
              type="button"
            >
              ×
            </button>
          ) : null}
        </form>
      </header>

      {communityLoading ? (
        <section aria-label="Đang tải bài viết cộng đồng" className="communityExploreGrid communityExploreLoading">
          {Array.from({ length: 3 }).map((_, index) => <div className="communityExploreSkeleton" key={index} />)}
        </section>
      ) : visibleCommunityPosts.length ? (
        <section aria-labelledby="community-posts-title" className="communityExploreSection">
          <div className="communityExploreHeading">
            <div>
              <span>Cộng đồng TravelPlanner</span>
              <h2 id="community-posts-title">Khoảnh khắc mới nhất</h2>
            </div>
            {user ? <button onClick={() => router.push("/profile")} type="button">＋ Đăng bài</button> : null}
          </div>
          <div className="communityExploreGrid">
            {visibleCommunityPosts.map((post) => (
              <article className="communityExploreCard" key={post.id}>
                <div className="communityExploreMedia">
                  {post.contentType === "reel" ? (
                    <video loop muted playsInline preload="metadata" src={post.mediaUrl} />
                  ) : (
                    <img alt={post.caption} loading="lazy" src={post.mediaUrl} />
                  )}
                  <div className="communityExploreShade" />
                  <button
                    aria-label={`Mở ${post.contentType === "reel" ? "video" : "ảnh"} ${post.caption}`}
                    className="communityExploreOpen"
                    onClick={() => openViewer(`community-${post.id}`)}
                    type="button"
                  />
                  <span className={`reelContentType ${post.contentType === "reel" ? "video" : "post"}`}>
                    {post.contentType === "reel" ? "Reel" : "Bài post"}
                  </span>
                  <span className="communityLocationTag"><MapPinIcon /> {post.locationName}</span>
                  <div className="communityExploreCopy">
                    <div className="communityAuthor">
                      {post.authorAvatarUrl ? <img alt="" src={post.authorAvatarUrl} /> : <span>{post.authorName.charAt(0).toUpperCase()}</span>}
                      <strong>{post.authorName}</strong>
                    </div>
                    <p>{post.caption}</p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {loading ? (
        <div className="reelsGrid" aria-label="Đang tải nội dung quảng bá">
          {Array.from({ length: 6 }).map((_, index) => (
            <div aria-hidden="true" className="reelCard reelSkeleton" key={index}>
              <div className="reelSkeletonPoster" />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="exploreFeedback errorBanner" role="alert">
          <div>
            <strong>Chưa tải được nội dung quảng bá</strong>
            <span>{error}</span>
          </div>
          <Link href="/explore">Về Khám phá</Link>
        </div>
      ) : reels.length === 0 && listingQuery ? (
        <div className="emptyState reelSearchEmpty">
          <h2>Không tìm thấy reels phù hợp</h2>
          <p>Không có kết quả cho “{listingQuery}”. Hãy thử tên điểm đến, tiêu đề hoặc creator khác.</p>
          <button
            className="primaryBtn"
            onClick={() => {
              setReelQuery("");
              setListingQuery("");
            }}
            type="button"
          >
            Xóa tìm kiếm
          </button>
        </div>
      ) : reels.length === 0 ? (
        <div className="emptyState">
          <h2>Chưa có Plan để tạo nội dung quảng bá</h2>
          <p>Khi Marketplace có listing published, tab này sẽ tự lấy Plan và hiển thị dạng card dọc.</p>
          <Link className="primaryBtn" href="/explore">Xem Marketplace</Link>
        </div>
      ) : (
        <div className="reelsGrid">
          {visibleReels.map(({ listing, stats, tags, type }) => {
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

                  <span className={`reelContentType ${type}`}>{type === "video" ? "Video" : "Bài post"}</span>

                  <button
                    className="reelPlayButton"
                    onClick={() => openViewer(`listing-${listing.id}`)}
                    type="button"
                    aria-label={`${type === "video" ? "Xem video" : "Mở bài post"} ${version.title}`}
                  >
                    {type === "video" ? <PlayIcon /> : <span>↗</span>}
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
                        <button
                          className={cartIds.includes(listing.id) ? "inCart" : ""}
                          onClick={() => toggleCart(listing.id)}
                          type="button"
                        >
                          <CartIcon /> {cartIds.includes(listing.id) ? "Đã thêm" : "Thêm vào giỏ"}
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

      {cartIds.length ? (
        <button className="promotionCartButton" onClick={() => setCartOpen(true)} type="button">
          <CartIcon />
          <span>Giỏ Plan</span>
          <strong>{cartIds.length}</strong>
        </button>
      ) : null}

      {activeViewer ? createPortal((
        <div
          aria-label="Trình xem nội dung quảng bá"
          aria-modal="true"
          className="promotionViewer"
          onWheel={handleViewerWheel}
          onTouchEnd={handleTouchEnd}
          onTouchStart={(event) => {
            touchStartY.current = event.touches[0].clientY;
          }}
          role="dialog"
        >
          <button aria-label="Đóng trình xem" className="promotionViewerClose" onClick={() => setViewerIndex(null)} type="button">×</button>
          <button aria-label="Nội dung trước" className="promotionViewerNav previous" disabled={viewerIndex === 0} onClick={() => moveViewer(-1)} type="button">↑</button>
          <button aria-label="Nội dung tiếp theo" className="promotionViewerNav next" disabled={viewerIndex === viewerItems.length - 1} onClick={() => moveViewer(1)} type="button">↓</button>

          <article className="promotionViewerStage" key={activeViewer.id}>
            {activeViewer.type === "video" ? (
              <video autoPlay controls loop muted playsInline poster={activeViewer.listing ? getCover(activeViewer.listing.currentVersion) : undefined}>
                <source src={activeViewer.mediaUrl} />
              </video>
            ) : (
              <img alt={activeViewer.title} src={activeViewer.mediaUrl} />
            )}
            <div className="promotionViewerShade" />
            <span className={`reelContentType viewerType ${activeViewer.type}`}>
              {activeViewer.type === "video" ? "Video" : "Ảnh"}
            </span>
            <span className="promotionViewerCount">{(viewerIndex ?? 0) + 1} / {viewerItems.length}</span>
            <div className="promotionViewerCopy">
              <span>@{activeViewer.authorName}</span>
              <h2>{activeViewer.title}</h2>
              <p>{activeViewer.description}</p>
            </div>
            {activeViewer.listing ? <div className="promotionViewerCommerce">
              <div>
                <small>Plan đang bán</small>
                <strong>{vnd(activeViewer.listing.currentVersion.priceAmount, activeViewer.listing.currentVersion.priceCurrency)}</strong>
              </div>
              <button
                aria-label={cartIds.includes(activeViewer.listing.id) ? "Xóa Plan khỏi giỏ" : "Thêm Plan vào giỏ"}
                className={cartIds.includes(activeViewer.listing.id) ? "inCart" : ""}
                onClick={() => activeViewer.listing && toggleCart(activeViewer.listing.id)}
                type="button"
              >
                <CartIcon />
                {cartIds.includes(activeViewer.listing.id) ? "Đã thêm" : "Thêm"}
              </button>
              <button
                className="promotionViewerBuy"
                disabled={buyingId === activeViewer.listing.id}
                onClick={() => activeViewer.listing && void handleBuy(activeViewer.listing)}
                type="button"
              >
                {buyingId === activeViewer.listing.id ? "Đang mở…" : "Mua Plan"}
              </button>
              <Link href={`/listings/${activeViewer.listing.id}`}>Chi tiết</Link>
            </div> : null}
          </article>
          <span className="promotionViewerHint">Cuộn, vuốt hoặc dùng phím ↑ ↓ để xem tiếp</span>
        </div>
      ), document.body) : null}

      {cartOpen ? (
        <div aria-modal="true" className="promotionCartOverlay" role="dialog">
          <button aria-label="Đóng giỏ hàng" className="promotionCartBackdrop" onClick={() => setCartOpen(false)} type="button" />
          <aside className="promotionCartDrawer">
            <header>
              <div>
                <small>Marketplace</small>
                <h2>Giỏ Plan ({cartListings.length})</h2>
              </div>
              <button aria-label="Đóng giỏ hàng" onClick={() => setCartOpen(false)} type="button">×</button>
            </header>
            <div className="promotionCartItems">
              {cartListings.map((listing) => (
                <article key={listing.id}>
                  <img alt="" src={getCover(listing.currentVersion)} />
                  <div>
                    <strong>{listing.currentVersion.title}</strong>
                    <span>{vnd(listing.currentVersion.priceAmount, listing.currentVersion.priceCurrency)}</span>
                    <div>
                      <button onClick={() => persistCart(cartIds.filter((id) => id !== listing.id))} type="button">Xóa</button>
                      <button disabled={buyingId === listing.id} onClick={() => void handleBuy(listing)} type="button">
                        {buyingId === listing.id ? "Đang mở MoMo" : "Thanh toán"}
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
            <p>Checkout hiện xử lý từng Plan để mỗi đơn luôn gắn đúng một phiên bản đã xuất bản.</p>
          </aside>
        </div>
      ) : null}
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
