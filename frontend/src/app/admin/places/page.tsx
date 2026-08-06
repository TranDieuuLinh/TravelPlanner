"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { APIError } from "@/lib/api";
import {
  approvePlaceMerge,
  dismissPlaceMerge,
  getPlaceReviewGroups,
  type PlaceReviewGroup,
} from "@/lib/place-dedupe";

const PAGE_SIZE = 50;

const reasonLabels: Record<string, string> = {
  incompatible_place_type: "Loại địa điểm khác nhau",
  possible_branch_distance: "Có thể là chi nhánh khác",
  possible_branch_address: "Địa chỉ có thể là chi nhánh khác",
  unclassified_place_type: "Thiếu phân loại",
  same_name_but_too_far: "Cùng tên nhưng cách xa",
  generic_name: "Tên quá chung",
  no_shared_canonical_or_alias: "Không trùng tên/alias rõ ràng",
  address_match_needs_manual_review: "Địa chỉ giống/gần — cần xem thủ công",
  address_mismatch_needs_manual_review: "Địa chỉ khác — cần xem thủ công",
};

function displayReason(reason: string): string {
  return reasonLabels[reason] ?? reason.replaceAll("_", " ");
}

export default function AdminPlaceReviewPage() {
  const router = useRouter();
  const { loading: authLoading, user } = useAuth();
  const [groups, setGroups] = useState<PlaceReviewGroup[]>([]);
  const [groupCount, setGroupCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [canonicalIds, setCanonicalIds] = useState<Record<string, string>>({});
  const [savingGroupId, setSavingGroupId] = useState("");

  useEffect(() => {
    if (!authLoading && (!user || user.role !== "admin")) router.replace("/");
  }, [authLoading, router, user]);

  useEffect(() => {
    if (user?.role !== "admin") return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const response = await getPlaceReviewGroups({ limit: PAGE_SIZE, query });
        if (cancelled) return;
        setGroups(response.groups);
        setGroupCount(response.groupCount);
        setCanonicalIds(
          Object.fromEntries(
            response.groups.map((group) => [group.groupId, group.records[0]?.entityId ?? ""]),
          ),
        );
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof APIError ? err.message : "Không thể tải danh sách cần review.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, query ? 250 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, user]);

  async function loadMore() {
    setLoadingMore(true);
    setError("");
    try {
      const response = await getPlaceReviewGroups({
        offset: groups.length,
        limit: PAGE_SIZE,
        query,
      });
      setGroups((current) => [...current, ...response.groups]);
      setGroupCount(response.groupCount);
      setCanonicalIds((current) => ({
        ...current,
        ...Object.fromEntries(
          response.groups.map((group) => [group.groupId, group.records[0]?.entityId ?? ""]),
        ),
      }));
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Không thể tải thêm nhóm review.");
    } finally {
      setLoadingMore(false);
    }
  }

  async function decide(group: PlaceReviewGroup, decision: "merge" | "dismiss") {
    const canonicalId = canonicalIds[group.groupId] ?? group.records[0]?.entityId;
    if (decision === "merge" && !canonicalId) return;

    setSavingGroupId(group.groupId);
    setError("");
    setNotice("");
    setGroups((current) => current.filter((item) => item.groupId !== group.groupId));
    setGroupCount((current) => Math.max(0, current - 1));

    try {
      if (decision === "merge") {
        await approvePlaceMerge(group.groupId, canonicalId!);
        setNotice("Đã merge địa điểm và giữ các bản ghi phụ để truy vết.");
      } else {
        await dismissPlaceMerge(group.groupId);
        setNotice("Đã đánh dấu không merge và bỏ nhóm khỏi hàng chờ.");
      }
    } catch (err) {
      setGroups((current) => [group, ...current]);
      setGroupCount((current) => current + 1);
      setError(
        err instanceof APIError
          ? err.message
          : decision === "merge"
            ? "Không thể duyệt merge."
            : "Không thể đánh dấu không merge.",
      );
    } finally {
      setSavingGroupId("");
    }
  }

  if (authLoading || (loading && groups.length === 0 && !query)) {
    return <div className="routeLoading">Đang tải hàng chờ duyệt địa điểm...</div>;
  }

  return (
    <main className="pageWidth adminModerationPage placeReviewPage">
      <header className="pageHeader">
        <div>
          <span className="eyebrow">Quản trị Admin · Knowledge Graph</span>
          <h1>Duyệt merge địa điểm ({groupCount})</h1>
          <p>Chọn bản ghi chính rồi merge, hoặc bỏ qua ngay tại từng nhóm.</p>
        </div>
        <Link className="secondaryBtn" href="/admin/listings">← Duyệt listing</Link>
      </header>

      {error ? <div className="errorBanner">{error}</div> : null}
      {notice ? <div className="successBanner">{notice}</div> : null}

      <div className="placeReviewToolbar">
        <input
          aria-label="Tìm nhóm địa điểm"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Tìm theo tên hoặc địa chỉ..."
          value={query}
        />
        <span>{loading ? "Đang tìm..." : `${groups.length}/${groupCount} nhóm hiển thị`}</span>
      </div>

      {!loading && groups.length === 0 ? (
        <section className="emptyState"><h2>Không còn nhóm nào cần review</h2><p>Danh sách đã được xử lý hết.</p></section>
      ) : (
        <div className="placeReviewGrid">
          {groups.map((group) => (
            <article className="placeReviewCard" key={group.groupId}>
              <div className="placeReviewCardHeader">
                <div>
                  <span className="badge category">{group.records.length} bản ghi</span>
                  <span className="placeReviewReasons">
                    {group.reasonCodes.map(displayReason).join(" · ")}
                  </span>
                </div>
                <code>{group.groupId}</code>
              </div>
              <div className="placeReviewRecords">
                {group.records.map((record) => {
                  const selected = (canonicalIds[group.groupId] ?? group.records[0]?.entityId) === record.entityId;
                  return (
                    <label className={`placeReviewRecord ${selected ? "selected" : ""}`} key={record.entityId}>
                      <span className="placeReviewRecordTitle">
                        <input
                          checked={selected}
                          name={`canonical-${group.groupId}`}
                          onChange={() => setCanonicalIds((current) => ({ ...current, [group.groupId]: record.entityId }))}
                          type="radio"
                        />
                        <strong>{record.name}</strong>
                      </span>
                      <span>{record.placeType} · {record.category}</span>
                      <span>{record.address || "Chưa có địa chỉ"}</span>
                      <small>{record.entityId}</small>
                    </label>
                  );
                })}
              </div>
              <div className="placeReviewActions">
                <button
                  className="rejectBtn"
                  disabled={savingGroupId === group.groupId}
                  onClick={() => void decide(group, "dismiss")}
                  type="button"
                >
                  Không merge
                </button>
                <button
                  className="approveBtn"
                  disabled={savingGroupId === group.groupId}
                  onClick={() => void decide(group, "merge")}
                  type="button"
                >
                  Merge về bản ghi đã chọn
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      {groups.length < groupCount ? (
        <div className="placeReviewLoadMore">
          <button className="secondaryBtn" disabled={loadingMore} onClick={() => void loadMore()} type="button">
            {loadingMore ? "Đang tải..." : "Hiện thêm 50 nhóm"}
          </button>
        </div>
      ) : null}
    </main>
  );
}
