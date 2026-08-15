"use client";

import "@/styles/global/groups.css";
import "@/styles/global/community.css";

import Image from "next/image";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useAuth } from "@/features/auth/components/AuthProvider";
import { APIError } from "@/shared/api/client";
import {
  createTravelGroupPost,
  getTravelGroup,
  joinTravelGroup,
} from "@/features/travel-groups/api";
import type { TravelGroupDetail, TravelGroupPost } from "@/features/travel-groups/types";

function MembersIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <circle cx="9" cy="8" r="3" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="17" cy="9" r="2.3" stroke="currentColor" strokeWidth="1.7" />
      <path d="M3.5 19c.5-3.5 2.3-5.3 5.5-5.3s5 1.8 5.5 5.3M14.4 14.2c3.2-.6 5.2 1 5.8 4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.7" />
      <path d="M3.5 12h17M12 3c2.2 2.4 3.3 5.4 3.3 9S14.2 18.6 12 21c-2.2-2.4-3.3-5.4-3.3-9S9.8 5.4 12 3Z" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

function formatPostTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Vừa đăng";
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function initials(name: string) {
  return name.trim().split(/\s+/).slice(-2).map((part) => part[0]).join("").toUpperCase();
}

export default function TravelGroupPage() {
  const params = useParams<{ groupId: string }>();
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const groupId = Number(params.groupId);
  const [detail, setDetail] = useState<TravelGroupDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [content, setContent] = useState("");
  const [posting, setPosting] = useState(false);
  const [joining, setJoining] = useState(false);
  const [composerError, setComposerError] = useState("");

  useEffect(() => {
    let cancelled = false;
    if (!Number.isInteger(groupId) || groupId < 1) {
      setError("Đường dẫn nhóm không hợp lệ.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError("");
    void getTravelGroup(groupId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof APIError ? err.message : "Không thể tải nhóm du lịch.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [groupId, user]);

  const remainingCharacters = useMemo(() => 2000 - content.length, [content.length]);

  async function handlePost(event: FormEvent) {
    event.preventDefault();
    const trimmed = content.trim();
    if (!user) {
      router.push(`/login?next=/groups/${groupId}`);
      return;
    }
    if (!trimmed) {
      setComposerError("Hãy viết một điều bạn muốn chia sẻ.");
      return;
    }

    setPosting(true);
    setComposerError("");
    try {
      const post = await createTravelGroupPost(groupId, trimmed);
      setDetail((current) => current ? {
        ...current,
        posts: [post, ...current.posts],
        totalPosts: current.totalPosts + 1,
      } : current);
      setContent("");
    } catch (err) {
      setComposerError(err instanceof APIError ? err.message : "Chưa thể đăng bài viết.");
    } finally {
      setPosting(false);
    }
  }

  async function handleJoin() {
    if (!user) {
      router.push(`/login?next=/groups/${groupId}`);
      return;
    }
    setJoining(true);
    try {
      const membership = await joinTravelGroup(groupId);
      setDetail((current) => current ? {
        ...current,
        group: {
          ...current.group,
          isMember: membership.isMember,
          memberCount: membership.memberCount,
        },
      } : current);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Chưa thể tham gia nhóm.");
    } finally {
      setJoining(false);
    }
  }

  if (loading || authLoading) {
    return <main className="pageWidth groupPage"><div className="groupPageLoading">Đang mở nhóm...</div></main>;
  }

  if (error || !detail) {
    return (
      <main className="pageWidth groupPage">
        <div className="groupPageError" role="alert">
          <Image alt="" height={112} src="/images/penguin-globe-logo.png" width={112} />
          <h1>Chưa mở được nhóm</h1>
          <p>{error || "Không tìm thấy nhóm du lịch."}</p>
          <Link href="/reels">Quay lại Khám phá</Link>
        </div>
      </main>
    );
  }

  const { group, posts, totalPosts } = detail;

  return (
    <main className="groupPage">
      <section className="groupHero">
        <div className="pageWidth groupHeroInner">
          <Link className="groupBackLink" href="/reels">← Nhóm du lịch</Link>
          <div className="groupHeroArt">
            <Image alt="Chim cánh cụt TravelPlanner ôm quả địa cầu" height={220} priority src="/images/penguin-globe-logo.png" width={220} />
          </div>
          <div className="groupHeroCopy">
            <span><GlobeIcon /> Nhóm công khai</span>
            <h1>{group.countryName}</h1>
            <p>{group.name} — nơi mọi người cùng chia sẻ câu hỏi, kinh nghiệm và khoảnh khắc du lịch.</p>
            <div className="groupHeroMeta">
              <span><MembersIcon /> {group.memberCount.toLocaleString("vi-VN")} thành viên</span>
              <span>{totalPosts.toLocaleString("vi-VN")} bài viết</span>
            </div>
          </div>
          <button
            className={group.isMember ? "groupJoinButton joined" : "groupJoinButton"}
            disabled={group.isMember || joining}
            onClick={() => void handleJoin()}
            type="button"
          >
            {joining ? "Đang tham gia..." : group.isMember ? "✓ Đã tham gia" : "Tham gia nhóm"}
          </button>
        </div>
      </section>

      <div className="pageWidth groupContentLayout">
        <section aria-label="Bảng tin nhóm" className="groupFeed">
          <form className="groupComposer" onSubmit={handlePost}>
            <div className="groupComposerTop">
              {user?.avatarUrl ? (
                <img alt="" className="groupAvatar image" src={user.avatarUrl} />
              ) : (
                <span aria-hidden="true" className="groupAvatar">{user ? initials(user.fullName) : "VS"}</span>
              )}
              <div>
                <strong>{user ? `Chào ${user.fullName}` : "Chia sẻ cùng cộng đồng"}</strong>
                <span>Mọi người trong cộng đồng đều có thể đăng bài.</span>
              </div>
            </div>
            {user ? (
              <>
                <textarea
                  aria-label="Nội dung bài viết"
                  maxLength={2000}
                  onChange={(event) => setContent(event.target.value)}
                  placeholder={`Bạn muốn chia sẻ gì về ${group.countryName}?`}
                  rows={4}
                  value={content}
                />
                <div className="groupComposerFooter">
                  <span className={remainingCharacters < 100 ? "nearLimit" : ""}>{remainingCharacters} ký tự</span>
                  <button disabled={posting || !content.trim()} type="submit">
                    {posting ? "Đang đăng..." : "Đăng bài"}
                  </button>
                </div>
              </>
            ) : (
              <Link className="groupLoginToPost" href={`/login?next=/groups/${groupId}`}>Đăng nhập để viết bài</Link>
            )}
            {composerError ? <p className="groupComposerError" role="alert">{composerError}</p> : null}
          </form>

          {posts.length ? (
            <div className="groupPostList">
              {posts.map((post: TravelGroupPost) => (
                <article className="groupPostCard" key={post.id}>
                  <header>
                    {post.author.avatarUrl ? (
                      <img alt="" className="groupAvatar image" src={post.author.avatarUrl} />
                    ) : (
                      <span aria-hidden="true" className="groupAvatar">{initials(post.author.fullName)}</span>
                    )}
                    <div>
                      <strong>{post.author.fullName}</strong>
                      <span>{formatPostTime(post.createdAt)} · <GlobeIcon /></span>
                    </div>
                  </header>
                  <p>{post.content}</p>
                </article>
              ))}
            </div>
          ) : (
            <div className="groupEmptyFeed">
              <Image alt="" height={118} src="/images/penguin-globe-logo.png" width={118} />
              <h2>Hãy bắt đầu cuộc trò chuyện</h2>
              <p>Chưa có bài viết nào trong nhóm này. Chia sẻ một câu hỏi hoặc kinh nghiệm đầu tiên nhé.</p>
            </div>
          )}
        </section>

        <aside className="groupAboutCard">
          <h2>Giới thiệu nhóm</h2>
          <p>Cộng đồng mở dành cho người quan tâm đến hành trình tại {group.countryName}.</p>
          <div><GlobeIcon /><span><strong>Công khai</strong><small>Bất kỳ ai cũng có thể xem bài viết.</small></span></div>
          <div><MembersIcon /><span><strong>Mọi người đều có thể đăng</strong><small>Đăng nhập để chia sẻ với cộng đồng.</small></span></div>
        </aside>
      </div>
    </main>
  );
}
