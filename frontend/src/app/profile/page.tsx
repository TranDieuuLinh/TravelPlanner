"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useAuth } from "@/components/AuthProvider";
import { PenguinMascot } from "@/components/PenguinMascot";
import {
  type CountryFootprint,
  ProfileVisitedMap,
} from "@/components/ProfileVisitedMap";
import { APIError } from "@/lib/api";
import { getPurchasedPlans, getUserFavorites } from "@/lib/marketplace";
import { getProfileShowcase } from "@/lib/users";
import type { BuyerPlan, ListingSummary } from "@/types/marketplace";
import type { ProfileShowcase } from "@/types/profile";

type ProfileTab = "achievements" | "posts" | "saved" | "purchased";

const emptyShowcase: ProfileShowcase = { visitedPlaces: [], posts: [] };

export default function ProfilePage() {
  const router = useRouter();
  const { loading, submitCreatorApplication, updateProfile, user } = useAuth();
  const [activeTab, setActiveTab] = useState<ProfileTab>("achievements");
  const [showcase, setShowcase] = useState<ProfileShowcase>(emptyShowcase);
  const [favorites, setFavorites] = useState<ListingSummary[]>([]);
  const [purchased, setPurchased] = useState<BuyerPlan[]>([]);
  const [contentBusy, setContentBusy] = useState(true);
  const [selectedCountryCode, setSelectedCountryCode] = useState<string | null>(null);
  const [countryFootprints, setCountryFootprints] = useState<CountryFootprint[]>([]);
  const [editing, setEditing] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileMessage, setProfileMessage] = useState("");
  const [creatorPanelOpen, setCreatorPanelOpen] = useState(false);
  const [creatorBusy, setCreatorBusy] = useState(false);
  const [creatorMessage, setCreatorMessage] = useState("");
  const [portfolioUrls, setPortfolioUrls] = useState("");
  const [fullName, setFullName] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [bio, setBio] = useState("");
  const [preferences, setPreferences] = useState("");

  useEffect(() => {
    if (!loading && !user) router.replace("/login?next=/profile");
  }, [loading, router, user]);

  useEffect(() => {
    if (!user) return;
    setFullName(user.fullName);
    setAvatarUrl(user.avatarUrl ?? "");
    setBio(user.bio ?? "");
    setPreferences(user.travelPreferences.join(", "));
  }, [user]);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    setContentBusy(true);
    Promise.allSettled([
      getProfileShowcase(),
      getUserFavorites(),
      getPurchasedPlans(),
    ]).then(([showcaseResult, favoriteResult, purchasedResult]) => {
      if (cancelled) return;
      setShowcase(showcaseResult.status === "fulfilled" ? showcaseResult.value : emptyShowcase);
      setFavorites(favoriteResult.status === "fulfilled" ? favoriteResult.value : []);
      setPurchased(purchasedResult.status === "fulfilled" ? purchasedResult.value : []);
      setContentBusy(false);
    });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const selectCountry = useCallback((code: string) => setSelectedCountryCode(code), []);
  const updateCountryFootprints = useCallback((summaries: CountryFootprint[]) => {
    setCountryFootprints(summaries);
    setSelectedCountryCode((current) => {
      if (current && summaries.some((country) => country.code === current)) return current;
      return summaries.find((country) => country.status === "visited")?.code ?? null;
    });
  }, []);
  const unlockedAchievements = useMemo(
    () => getFootprintAchievements(countryFootprints),
    [countryFootprints],
  );

  if (loading || !user) return <div className="routeLoading">Đang tải hồ sơ...</div>;

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProfileBusy(true);
    setProfileMessage("");
    try {
      await updateProfile({
        fullName,
        avatarUrl: avatarUrl.trim() || null,
        bio: bio.trim() || null,
        travelPreferences: preferences.split(",").map((item) => item.trim()).filter(Boolean),
      });
      setProfileMessage("Đã cập nhật hồ sơ.");
      setEditing(false);
    } catch (reason) {
      setProfileMessage(reason instanceof APIError ? reason.message : "Không thể lưu hồ sơ.");
    } finally {
      setProfileBusy(false);
    }
  }

  async function applyForCreator(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (bio.trim().length < 20) {
      setCreatorMessage("Phần giới thiệu kinh nghiệm cần tối thiểu 20 ký tự.");
      return;
    }
    setCreatorBusy(true);
    setCreatorMessage("");
    try {
      await submitCreatorApplication(
        bio,
        portfolioUrls.split("\n").map((url) => url.trim()).filter(Boolean),
      );
      setCreatorMessage("Đã gửi hồ sơ Creator. Vui lòng chờ quản trị viên duyệt.");
    } catch (reason) {
      setCreatorMessage(reason instanceof APIError ? reason.message : "Không thể gửi hồ sơ Creator.");
    } finally {
      setCreatorBusy(false);
    }
  }

  const initial = user.fullName.charAt(0).toUpperCase();
  const canApplyForCreator =
    user.role !== "admin" &&
    user.role !== "creator" &&
    ["none", "rejected"].includes(user.creatorStatus);

  return (
    <main className="pageWidth instagramProfilePage">
      <section className="instagramProfileHeader">
        <div className="instagramAvatarRing">
          {user.avatarUrl ? (
            <img alt={user.fullName} src={user.avatarUrl} />
          ) : (
            <span>{initial}</span>
          )}
        </div>

        <div className="instagramProfileMeta">
          <div className="instagramProfileTitle">
            <h1>{user.fullName}</h1>
            <button className="profileEditButton" onClick={() => setEditing((value) => !value)} type="button">
              Chỉnh sửa hồ sơ
            </button>
            <Link className="profileCreateButton" href="/planner">Tạo plan</Link>
            {user.role === "creator" ? (
              <Link className="profileUtilityLink" href="/creator/listings/new">Đăng bài viết</Link>
            ) : null}
            {user.role === "admin" ? (
              <Link className="profileUtilityLink" href="/admin/listings">Quản trị</Link>
            ) : null}
            {canApplyForCreator ? (
              <button className="profileUtilityLink" onClick={() => setCreatorPanelOpen((value) => !value)} type="button">
                Đăng ký Creator
              </button>
            ) : null}
          </div>

          <div className="instagramStats" aria-label="Thống kê hồ sơ">
            <div><strong>{showcase.visitedPlaces.length}</strong><span>địa điểm đã đi</span></div>
            <div><strong>{showcase.posts.length}</strong><span>bài viết</span></div>
            <div><strong>{favorites.length}</strong><span>đã lưu</span></div>
            <div><strong>{purchased.length}</strong><span>đã mua</span></div>
          </div>

          <div className="instagramBio">
            <strong>{user.role === "creator" ? "Travel Creator" : "Traveler"}</strong>
            <p>{user.bio || "Ghi lại những nơi đã đi và những hành trình muốn khám phá."}</p>
          </div>
        </div>
      </section>

      {editing ? (
        <section className="instagramEditPanel">
          <div>
            <h2>Chỉnh sửa hồ sơ</h2>
            <p>Thông tin này được hiển thị trên trang cá nhân của bạn.</p>
          </div>
          <form onSubmit={saveProfile}>
            <label htmlFor="profile-name">Họ và tên</label>
            <input id="profile-name" minLength={2} onChange={(event) => setFullName(event.target.value)} required value={fullName} />
            <label htmlFor="profile-avatar">URL ảnh đại diện</label>
            <input id="profile-avatar" onChange={(event) => setAvatarUrl(event.target.value)} placeholder="https://..." type="url" value={avatarUrl} />
            <label htmlFor="profile-bio">Giới thiệu</label>
            <textarea id="profile-bio" maxLength={1000} onChange={(event) => setBio(event.target.value)} rows={3} value={bio} />
            <label htmlFor="profile-preferences">Sở thích du lịch</label>
            <input id="profile-preferences" onChange={(event) => setPreferences(event.target.value)} value={preferences} />
            {profileMessage ? <p className="profileFormMessage">{profileMessage}</p> : null}
            <div className="instagramEditActions">
              <button className="profileEditButton" onClick={() => setEditing(false)} type="button">Hủy</button>
              <button className="profileCreateButton" disabled={profileBusy} type="submit">
                {profileBusy ? "Đang lưu..." : "Lưu thay đổi"}
              </button>
            </div>
          </form>
        </section>
      ) : null}

      {creatorPanelOpen && canApplyForCreator ? (
        <section className="instagramCreatorPanel">
          <div>
            <span className="eyebrow">Creator</span>
            <h2>Chia sẻ hành trình của bạn</h2>
            <p>Đăng ký để đóng gói và xuất bản plan trên Marketplace.</p>
          </div>
          <form onSubmit={applyForCreator}>
            <label htmlFor="creator-bio">Kinh nghiệm du lịch</label>
            <textarea id="creator-bio" minLength={20} onChange={(event) => setBio(event.target.value)} required rows={3} value={bio} />
            <label htmlFor="creator-links">Portfolio / mạng xã hội</label>
            <textarea id="creator-links" onChange={(event) => setPortfolioUrls(event.target.value)} placeholder={"https://instagram.com/...\nhttps://facebook.com/..."} rows={2} value={portfolioUrls} />
            {creatorMessage ? <p>{creatorMessage}</p> : null}
            <button className="profileCreateButton" disabled={creatorBusy} type="submit">
              {creatorBusy ? "Đang gửi..." : "Gửi đăng ký"}
            </button>
          </form>
        </section>
      ) : null}

      <nav className="instagramTabs" aria-label="Nội dung hồ sơ">
        <button className={activeTab === "achievements" ? "active" : ""} onClick={() => setActiveTab("achievements")} type="button">
          <span aria-hidden="true">⌖</span> Thành tựu
        </button>
        <button className={activeTab === "posts" ? "active" : ""} onClick={() => setActiveTab("posts")} type="button">
          <span aria-hidden="true">▦</span> Bài viết
        </button>
        <button className={activeTab === "saved" ? "active" : ""} onClick={() => setActiveTab("saved")} type="button">
          <span aria-hidden="true">♡</span> Đã lưu
        </button>
        <button className={activeTab === "purchased" ? "active" : ""} onClick={() => setActiveTab("purchased")} type="button">
          <span aria-hidden="true">◇</span> Đã mua
        </button>
      </nav>

      {contentBusy ? <div className="routeLoading">Đang tải hành trình của bạn...</div> : null}

      {!contentBusy && activeTab === "achievements" ? (
        <section className="achievementPanel">
          <div className="achievementMapLayout">
            <ProfileVisitedMap
              onSelect={selectCountry}
              onSummariesChange={updateCountryFootprints}
              places={showcase.visitedPlaces}
              selectedCountryCode={selectedCountryCode}
            />
          </div>

          <section className="footprintAchievements" aria-labelledby="footprint-achievement-title">
            <div className="footprintSectionHeading">
              <div>
                <span className="eyebrow">Cột mốc</span>
                <h3 id="footprint-achievement-title">Thành tựu hành trình</h3>
              </div>
              <span>
                {unlockedAchievements.filter((achievement) => achievement.unlocked).length}/
                {unlockedAchievements.length} đã mở khóa
              </span>
            </div>
            <div className="footprintBadgeGrid">
              {unlockedAchievements.map((achievement) => (
                <article className={achievement.unlocked ? "is-unlocked" : "is-locked"} key={achievement.title}>
                  <span aria-hidden="true" className="footprintBadgeIcon">{achievement.icon}</span>
                  <div>
                    <strong>{achievement.title}</strong>
                    <p>{achievement.description}</p>
                    <small>{achievement.unlocked ? "Đã mở khóa" : achievement.progress}</small>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </section>
      ) : null}

      {!contentBusy && activeTab === "posts" ? (
        showcase.posts.length === 0 ? (
          <EmptyProfileState title="Chưa có bài viết" description="Những khoảnh khắc du lịch bạn chia sẻ sẽ xuất hiện tại đây." />
        ) : (
          <section className="instagramPostGrid" aria-label="Bài viết đã đăng">
            {showcase.posts.map((post) => (
              <article className="instagramPostCard" key={post.id}>
                <img alt={post.locationName || post.caption} src={post.mediaUrl} />
                <div className="instagramPostOverlay">
                  {post.locationName ? <strong>⌖ {post.locationName}</strong> : null}
                  <p>{post.caption}</p>
                </div>
              </article>
            ))}
          </section>
        )
      ) : null}

      {!contentBusy && activeTab === "saved" ? (
        favorites.length === 0 ? (
          <EmptyProfileState title="Chưa lưu hành trình nào" description="Thả tim một plan trong Khám phá để xem lại tại đây." linkLabel="Đi tới Khám phá" />
        ) : (
          <MarketplaceProfileGrid items={favorites} />
        )
      ) : null}

      {!contentBusy && activeTab === "purchased" ? (
        purchased.length === 0 ? (
          <EmptyProfileState title="Chưa mua hành trình nào" description="Plan bạn mua từ Khám phá sẽ được giữ riêng tại đây để tiếp tục cá nhân hóa." linkLabel="Khám phá plan" />
        ) : (
          <section className="purchasedPlanGrid">
            {purchased.map((plan) => (
              <article key={plan.entitlementId}>
                <span className="purchasedPlanBadge">Đã sở hữu</span>
                <div>
                  <small>{plan.destination} · {plan.durationDays} ngày</small>
                  <h3>{plan.title}</h3>
                  <p>Mua ngày {new Date(plan.createdAt).toLocaleDateString("vi-VN")}</p>
                </div>
                <Link href={`/listings/${plan.marketplacePlanId}`}>Xem plan →</Link>
              </article>
            ))}
          </section>
        )
      ) : null}
    </main>
  );
}

function getFootprintAchievements(countries: CountryFootprint[]) {
  const visitedNames = new Set(
    countries
      .filter((country) => country.status === "visited")
      .map((country) => country.name),
  );
  const visitedCount = visitedNames.size;

  return [
    {
      title: "Chuyến đi đầu tiên",
      description: "Hoàn thành chuyến đầu tiên có liên kết với Planner.",
      icon: "✦",
      unlocked: false,
      progress: "Chưa có chuyến hoàn thành từ Planner",
    },
    {
      title: "Khám phá 3 quốc gia",
      description: "Để lại dấu chân tại ba quốc gia.",
      icon: "3",
      unlocked: visitedCount >= 3,
      progress: `${Math.min(visitedCount, 3)}/3 quốc gia`,
    },
    {
      title: "Nhà thám hiểm",
      description: "Khám phá mười quốc gia trên bản đồ thế giới.",
      icon: "10",
      unlocked: visitedCount >= 10,
      progress: `${Math.min(visitedCount, 10)}/10 quốc gia`,
    },
    {
      title: "Công dân toàn cầu",
      description: "Khám phá hai mươi lăm quốc gia.",
      icon: "25",
      unlocked: visitedCount >= 25,
      progress: `${Math.min(visitedCount, 25)}/25 quốc gia`,
    },
    {
      title: "Vòng quanh thế giới",
      description: "Để lại dấu chân tại năm mươi quốc gia.",
      icon: "◎",
      unlocked: visitedCount >= 50,
      progress: `${Math.min(visitedCount, 50)}/50 quốc gia`,
    },
  ];
}

function EmptyProfileState({
  title,
  description,
  linkLabel,
}: {
  title: string;
  description: string;
  linkLabel?: string;
}) {
  return (
    <section className="instagramEmptyState">
      <PenguinMascot size={128} variant="search" />
      <h2>{title}</h2>
      <p>{description}</p>
      {linkLabel ? <Link href="/explore">{linkLabel} →</Link> : null}
    </section>
  );
}

function MarketplaceProfileGrid({ items }: { items: ListingSummary[] }) {
  return (
    <section className="profileMarketplaceGrid">
      {items.map((item) => {
        const image = item.currentVersion.mediaUrls[0];
        return (
          <article key={item.id}>
            {image ? <img alt={item.currentVersion.title} src={image} /> : <div className="profileListingPlaceholder">VSF</div>}
            <div>
              <small>{item.currentVersion.destination} · {item.currentVersion.durationDays} ngày</small>
              <h3>{item.currentVersion.title}</h3>
              <strong>{item.currentVersion.priceAmount.toLocaleString("vi-VN")} {item.currentVersion.priceCurrency}</strong>
              <Link href={`/listings/${item.id}`}>Xem hành trình →</Link>
            </div>
          </article>
        );
      })}
    </section>
  );
}
