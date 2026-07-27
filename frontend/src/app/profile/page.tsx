"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth, type CreatorStatus } from "@/components/AuthProvider";
import { APIError } from "@/lib/api";
import { getUserFavorites } from "@/lib/marketplace";
import type { ListingSummary } from "@/types/marketplace";

const creatorStatusLabels: Record<CreatorStatus, string> = {
  none: "Chưa đăng ký",
  pending: "Đang chờ duyệt",
  verified: "Đã xác minh",
  rejected: "Cần gửi lại",
};

export default function ProfilePage() {
  const router = useRouter();
  const { loading, submitCreatorApplication, updateProfile, user } = useAuth();

  const [activeTab, setActiveTab] = useState<"profile" | "creator" | "favorites">("profile");

  const [fullName, setFullName] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [bio, setBio] = useState("");
  const [preferences, setPreferences] = useState("");
  const [portfolioUrls, setPortfolioUrls] = useState("");

  const [profileBusy, setProfileBusy] = useState(false);
  const [applicationBusy, setApplicationBusy] = useState(false);
  const [profileMessage, setProfileMessage] = useState("");
  const [applicationMessage, setApplicationMessage] = useState("");

  const [favorites, setFavorites] = useState<ListingSummary[]>([]);
  const [loadingFavs, setLoadingFavs] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login?next=/profile");
  }, [loading, router, user]);

  useEffect(() => {
    if (!user) return;
    setFullName(user.fullName);
    setAvatarUrl(user.avatarUrl ?? "");
    setBio(user.bio ?? "");
    setPreferences(user.travelPreferences.join(", "));
    setPortfolioUrls(user.creatorPortfolioUrls.join("\n"));
  }, [user]);

  useEffect(() => {
    if (activeTab === "favorites" && user) {
      setLoadingFavs(true);
      getUserFavorites()
        .then(setFavorites)
        .catch(() => setFavorites([]))
        .finally(() => setLoadingFavs(false));
    }
  }, [activeTab, user]);

  if (loading || !user) {
    return <div className="routeLoading">Đang tải hồ sơ...</div>;
  }

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
      setProfileMessage("Đã cập nhật hồ sơ thành công.");
    } catch (reason) {
      setProfileMessage(reason instanceof APIError ? reason.message : "Không thể lưu hồ sơ.");
    } finally {
      setProfileBusy(false);
    }
  }

  async function applyForCreator(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (bio.trim().length < 20) {
      setApplicationMessage("Mô tả giới thiệu phải có tối thiểu 20 ký tự.");
      return;
    }
    setApplicationBusy(true);
    setApplicationMessage("");
    try {
      await submitCreatorApplication(
        bio,
        portfolioUrls.split("\n").map((item) => item.trim()).filter(Boolean)
      );
      setApplicationMessage("Đã gửi yêu cầu đăng ký Creator. Vui lòng chờ admin duyệt.");
    } catch (reason) {
      setApplicationMessage(reason instanceof APIError ? reason.message : "Không thể gửi yêu cầu.");
    } finally {
      setApplicationBusy(false);
    }
  }

  const initial = user.fullName.charAt(0).toUpperCase();
  const canApply =
    user.role !== "admin" && user.role !== "creator" && ["none", "rejected"].includes(user.creatorStatus);

  return (
    <main className="pageWidth profilePage">
      {/* Sleek Profile Hero Banner */}
      <section className="profileHeroCard">
        <div className="profileHeroMain">
          {user.avatarUrl ? (
            <img alt={user.fullName} className="profileAvatarImg" src={user.avatarUrl} />
          ) : (
            <div className="profileAvatarFallback">{initial}</div>
          )}
          <div className="profileHeroInfo">
            <div className="profileTagRow">
              <span className={`roleBadge role-${user.role}`}>
                {user.role === "creator" ? "✦ Creator" : user.role === "admin" ? "🛡 Admin" : "Traveler"}
              </span>
              <span className={`statusBadge status-${user.status}`}>
                {user.status === "active" ? "Đang hoạt động" : user.status}
              </span>
            </div>
            <h1>{user.fullName}</h1>
            <p className="userEmail">{user.email}</p>
          </div>
        </div>

        <div className="profileHeroActions">
          {user.role === "creator" ? (
            <Link className="primaryBtn" href="/creator/listings">
              ✎ Vào Creator Studio
            </Link>
          ) : null}
          {user.role === "admin" ? (
            <Link className="primaryBtn adminBtn" href="/admin/listings">
              🛡 Trang Duyệt Admin
            </Link>
          ) : null}
          <Link className="secondaryBtn" href="/planner">
            ✦ Tạo plan mới
          </Link>
        </div>
      </section>

      {/* Tab Controls */}
      <nav className="profileTabNav">
        <button
          className={activeTab === "profile" ? "tabBtn active" : "tabBtn"}
          onClick={() => setActiveTab("profile")}
          type="button"
        >
          👤 Thông tin cá nhân
        </button>
        <button
          className={activeTab === "creator" ? "tabBtn active" : "tabBtn"}
          onClick={() => setActiveTab("creator")}
          type="button"
        >
          ✦ {user.role === "creator" ? "Hồ sơ Creator" : "Đăng ký Creator"}
        </button>
        <button
          className={activeTab === "favorites" ? "tabBtn active" : "tabBtn"}
          onClick={() => setActiveTab("favorites")}
          type="button"
        >
          ♥ Đã lưu yêu thích
        </button>
      </nav>

      {/* Tab Content Container */}
      <div className="profileTabContainer">
        {/* Tab 1: Profile Form */}
        {activeTab === "profile" ? (
          <section className="profileCardSection">
            <div className="sectionHeader">
              <h2>Thông tin cá nhân</h2>
              <p>Cập nhật thông tin hiển thị và sở thích du lịch của bạn.</p>
            </div>

            <form className="profileCompactForm" onSubmit={saveProfile}>
              <div className="formGrid2">
                <div>
                  <label htmlFor="profile-name">Họ và tên</label>
                  <input
                    autoComplete="name"
                    id="profile-name"
                    minLength={2}
                    onChange={(e) => setFullName(e.target.value)}
                    required
                    value={fullName}
                  />
                </div>
                <div>
                  <label htmlFor="profile-avatar">URL Ảnh đại diện</label>
                  <input
                    id="profile-avatar"
                    onChange={(e) => setAvatarUrl(e.target.value)}
                    placeholder="https://..."
                    type="url"
                    value={avatarUrl}
                  />
                </div>
              </div>

              <label htmlFor="profile-bio">Giới thiệu bản thân</label>
              <textarea
                id="profile-bio"
                maxLength={1000}
                onChange={(e) => setBio(e.target.value)}
                placeholder="Viết một vài dòng ngắn về phong cách du lịch của bạn..."
                rows={3}
                value={bio}
              />

              <label htmlFor="profile-preferences">Sở thích du lịch</label>
              <input
                id="profile-preferences"
                onChange={(e) => setPreferences(e.target.value)}
                placeholder="Ẩm thực, biển, mạo hiểm, chụp ảnh"
                value={preferences}
              />
              <span className="fieldHint">Phân tách các sở thích bằng dấu phẩy.</span>

              {profileMessage ? <div className="formAlertInfo">{profileMessage}</div> : null}

              <div className="formFooter">
                <button className="primaryBtn" disabled={profileBusy} type="submit">
                  {profileBusy ? "Đang lưu..." : "Lưu thay đổi"}
                </button>
              </div>
            </form>
          </section>
        ) : null}

        {/* Tab 2: Creator Application / Info */}
        {activeTab === "creator" ? (
          <section className="profileCardSection">
            <div className="creatorHeaderBox">
              <div>
                <h2>Hồ sơ Creator</h2>
                <p>Trở thành Creator để đóng gói và chia sẻ lịch trình lên Marketplace.</p>
              </div>
              <span className={`creatorStatusBadge status-${user.creatorStatus}`}>
                {creatorStatusLabels[user.creatorStatus]}
              </span>
            </div>

            {canApply ? (
              <form className="profileCompactForm" onSubmit={applyForCreator}>
                <div className="infoNotice">
                  💡 <strong>Yêu cầu đăng ký:</strong> Phần giới thiệu kinh nghiệm cần tối thiểu 20 ký tự. Mọi liên kết portfolio phải là URL đầy đủ (dạng <code>https://...</code>).
                </div>

                <label htmlFor="creator-bio">Giới thiệu kinh nghiệm Creator (*)</label>
                <textarea
                  id="creator-bio"
                  minLength={20}
                  onChange={(e) => setBio(e.target.value)}
                  placeholder="Chia sẻ kinh nghiệm đi lại, am hiểu địa phương hoặc phong cách lên lịch trình của bạn (tối thiểu 20 ký tự)..."
                  required
                  rows={4}
                  value={bio}
                />

                <label htmlFor="creator-portfolio">Liên kết Portfolio / Mạng xã hội</label>
                <textarea
                  id="creator-portfolio"
                  onChange={(e) => setPortfolioUrls(e.target.value)}
                  placeholder={"https://instagram.com/p/...\nhttps://facebook.com/..."}
                  rows={3}
                  value={portfolioUrls}
                />
                <span className="fieldHint">Nhập tối đa 5 đường dẫn URL công khai (mỗi dòng 1 URL).</span>

                {applicationMessage ? <div className="formAlertInfo">{applicationMessage}</div> : null}

                <div className="formFooter">
                  <button className="primaryBtn" disabled={applicationBusy} type="submit">
                    {applicationBusy ? "Đang gửi..." : "Gửi đăng ký Creator →"}
                  </button>
                </div>
              </form>
            ) : (
              <div className="creatorVerifiedBox">
                {user.role === "creator" ? (
                  <>
                    <div className="verifiedBadgeBig">✓ Tài khoản Creator đã xác minh</div>
                    <p>Bạn có thể truy cập <strong>Creator Studio</strong> để tạo listing, thiết lập giá và nộp duyệt bản hành trình.</p>
                    <Link className="primaryBtn" href="/creator/listings">
                      Vào Creator Studio →
                    </Link>
                  </>
                ) : (
                  <>
                    <div className="pendingBadgeBig">⏳ Yêu cầu của bạn đang chờ Admin duyệt</div>
                    <p>Ban quản trị đang xem xét hồ sơ của bạn. Quyền Creator sẽ được cập nhật tự động ngay sau khi duyệt.</p>
                  </>
                )}
              </div>
            )}
          </section>
        ) : null}

        {/* Tab 3: Favorites */}
        {activeTab === "favorites" ? (
          <section className="profileCardSection">
            <div className="sectionHeader">
              <h2>Lịch trình yêu thích đã lưu</h2>
              <p>Danh sách các chuyến đi bạn đã thả tim trên Marketplace.</p>
            </div>

            {loadingFavs ? (
              <div className="routeLoading">Đang tải danh sách yêu thích...</div>
            ) : favorites.length === 0 ? (
              <div className="emptyState">
                <h3>Chưa có chuyến đi yêu thích nào</h3>
                <p>Khám phá Marketplace và thả tim các lịch trình bạn yêu thích.</p>
                <Link className="secondaryBtn" href="/explore">
                  Khám phá ngay →
                </Link>
              </div>
            ) : (
              <div className="favGrid">
                {favorites.map((fav) => (
                  <article className="favCard" key={fav.id}>
                    <div className="favCardInfo">
                      <span className="badge category">{fav.currentVersion.category}</span>
                      <h3>{fav.currentVersion.title}</h3>
                      <p>{fav.currentVersion.destination} ({fav.currentVersion.durationDays} ngày)</p>
                      <strong>{fav.currentVersion.priceAmount.toLocaleString("vi-VN")} VND</strong>
                    </div>
                    <Link className="secondaryBtn" href={`/listings/${fav.id}`}>
                      Xem chuyến đi
                    </Link>
                  </article>
                ))}
              </div>
            )}
          </section>
        ) : null}
      </div>
    </main>
  );
}
