"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  deleteUrlImportJob,
  listTripChatPlannerRuns,
  listUrlImportJobs,
  reprocessUrlImportJob,
  retryUrlImportJob,
  type ExplorerTimingReport,
  type ExplorerTimingStage,
  type PlanTimingReport,
  type PlanTimingStage,
  type TripChatTurn,
  type UrlImportJob
} from "@/features/planner/api/plans";
import {
  deleteGuestUrlJob,
  GUEST_URL_JOBS_EVENT,
  listGuestUrlJobs,
  reprocessGuestUrlJob,
  retryGuestUrlJob,
  type GuestUrlImportJob
} from "@/features/planner/lib/guest-url-jobs";
import { urlPlaceCountLabel } from "@/features/planner/lib/url-place-count";

const TERMINAL = new Set(["succeeded", "failed"]);
const ACTIVE = new Set(["queued", "running"]);
const ACTIVE_TURN = new Set(["queued", "classifying", "executing"]);
type DisplayJob = UrlImportJob | GuestUrlImportJob;

function isGuestJob(job: DisplayJob): job is GuestUrlImportJob {
  return "storage" in job && job.storage === "guest-memory";
}

function sourceLabel(value: string) {
  try {
    const url = new URL(value);
    const path = url.pathname === "/" ? "" : url.pathname;
    const compact = `${url.hostname.replace(/^www\./, "")}${path}`;
    return compact.length > 48 ? `${compact.slice(0, 45)}…` : compact;
  } catch {
    return "URL đã nhập";
  }
}

function jobSourceLabel(job: DisplayJob) {
  if (!job.url && job.sourceLabel) return job.sourceLabel;
  if (job.sourceType === "image") {
    const label = job.sourceLabel || "Ảnh OCR";
    return label.length > 48 ? `${label.slice(0, 45)}…` : label;
  }
  return sourceLabel(job.url);
}

function elapsedSeconds(job: DisplayJob, now: number) {
  if (!job.startedAt) return 0;
  const startedAt = job.startedAt;
  const finishedAt = job.finishedAt ? Date.parse(job.finishedAt) : now;
  const startedAtMs = Date.parse(startedAt);
  if (!Number.isFinite(startedAtMs) || !Number.isFinite(finishedAt)) return 0;
  return Math.max(0, Math.floor((finishedAt - startedAtMs) / 1000));
}

function elapsedLabel(totalSeconds: number) {
  if (totalSeconds < 60) return `${totalSeconds} giây`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes} phút ${seconds.toString().padStart(2, "0")} giây`;
}

function timingLabel(totalSeconds: number) {
  return totalSeconds < 10
    ? `${totalSeconds.toFixed(2)} giây`
    : `${totalSeconds.toFixed(1)} giây`;
}

function preciseElapsedLabel(totalSeconds: number) {
  const normalized = Math.max(0, totalSeconds);
  if (normalized < 60) return timingLabel(normalized);
  const minutes = Math.floor(normalized / 60);
  const seconds = normalized - minutes * 60;
  return `${minutes} phút ${seconds.toFixed(seconds < 10 ? 1 : 0).padStart(seconds < 10 ? 4 : 2, "0")} giây`;
}

function detailLabel(value: string | number | boolean | null) {
  if (typeof value === "boolean") return value ? "Có" : "Không";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return value ?? "—";
}

const DETAIL_LABELS: Record<string, string> = {
  candidateCount: "Candidate",
  selectedPlaceCount: "Địa điểm đầu vào",
  requestedDays: "Số ngày yêu cầu",
  tripThemeCount: "Chủ đề chuyến đi",
  scheduledDayCount: "Số ngày đã xếp",
  itemCount: "Hoạt động",
  unscheduledCount: "Chưa xếp",
  issueCount: "Vấn đề",
  status: "Trạng thái",
  urlCount: "URL",
  dataSource: "Công cụ / dữ liệu"
};

function detailKeyLabel(key: string) {
  return DETAIL_LABELS[key] ?? key;
}

function runningActivity(job: DisplayJob, elapsed: number) {
  const isPlanning = isPlanningJob(job);

  if (isPlanning) {
    if (elapsed < 6) return "Đang tạo khung chuyến đi theo từng ngày";
    if (elapsed < 14) return "Đang xếp địa điểm, bữa ăn và thời gian nghỉ";
    if (elapsed < 24) return "Đang tính các chặng di chuyển giữa địa điểm";
    return "Đang kiểm tra xung đột, ngân sách và ràng buộc";
  }

  if (job.sourceType === "image") {
    if (elapsed < 6) return "Đang kiểm tra ảnh và chuẩn bị OCR";
    if (elapsed < 18) return "Đang đọc chữ, biển hiệu và ngữ cảnh trong ảnh";
    if (elapsed < 30) return "Đang trích xuất địa điểm từ bằng chứng OCR";
    return "Đang đối chiếu, gộp trùng và xác định địa điểm";
  }

  if (job.forceRefresh && elapsed < 6) return "Đang làm mới dữ liệu nguồn";
  if (elapsed < 6) return "Đang kiểm tra URL và chuẩn bị nội dung";
  if (elapsed < 16) return "Đang đọc metadata, caption hoặc transcript có thể truy cập";
  if (elapsed < 30) return "Đang trích xuất địa điểm và ngữ cảnh du lịch";
  return "Đang đối chiếu, gộp trùng và xác định địa điểm";
}

function isPlanningJob(job: DisplayJob) {
  return job.phase === "planning";
}

function turnTiming<T>(turn: TripChatTurn, key: "explorerTiming" | "plannerTiming") {
  const value = turn.resultSummary[key];
  return value && typeof value === "object" ? value as T : null;
}

function progressStage(job: DisplayJob) {
  if (job.status === "queued") return { step: 1, label: "Chuẩn bị" };
  return isPlanningJob(job)
    ? { step: 3, label: "Lập kế hoạch" }
    : { step: 2, label: "Khám phá" };
}

function statusLabel(job: DisplayJob, now: number) {
  if (job.status === "running") {
    const elapsed = elapsedSeconds(job, now);
    const stage = progressStage(job);
    return `Bước ${stage.step}/3 · ${stage.label} · ${runningActivity(job, elapsed)} · ${elapsedLabel(elapsed)}`;
  }
  if (job.status === "queued") {
    const position = job.queuePosition ? ` · vị trí #${job.queuePosition}` : "";
    return `Đang chờ đến lượt${position}`;
  }
  if (job.status === "succeeded") {
    return `${job.forceRefresh ? "Đã phân tích lại" : "Đã hoàn tất"} · ${elapsedLabel(elapsedSeconds(job, now))}`;
  }
  return `Cần thử lại · ${elapsedLabel(elapsedSeconds(job, now))}`;
}

function TimingStages({
  stages,
  totalSeconds
}: {
  stages: Array<ExplorerTimingStage | PlanTimingStage>;
  totalSeconds?: number;
}) {
  if (stages.length === 0) return null;
  return (
    <section className="backgroundJobTimingGroup">
      <ol>
        {stages.map((stage, index) => {
          const details = Object.entries(stage.details ?? {});
          return (
            <li key={stage.key}>
              <span className="backgroundJobTimingStepIndex">{index + 1}</span>
              <span className="backgroundJobTimingStepCopy">
                <span>{stage.label}</span>
                {details.length ? (
                  <small>
                    {details.map(([key, value]) => `${detailKeyLabel(key)}: ${detailLabel(value)}`).join(" · ")}
                  </small>
                ) : null}
                {"subStages" in stage && stage.subStages?.length ? (
                  <span className="backgroundJobTimingSubsteps">
                    {stage.subStages.map((substage) => (
                      <span key={`${stage.key}-${substage.key}`}>
                        <span>{substage.label}</span>
                        <b>{timingLabel(Math.max(0, substage.durationSeconds))}</b>
                      </span>
                    ))}
                  </span>
                ) : null}
              </span>
              <span className="backgroundJobTimingDuration">
                <b>{timingLabel(Math.max(0, stage.durationSeconds))}</b>
                {totalSeconds ? (
                  <small>{Math.round((Math.max(0, stage.durationSeconds) / totalSeconds) * 100)}%</small>
                ) : null}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}


const PROVIDER_LABELS: Record<string, string> = {
  shared_cache: "Shared place cache",
  cache: "Place cache",
  database: "Knowledge Graph DB",
  knowledge_graph: "Knowledge Graph DB",
  google_maps_scraper: "Google Maps · Playwright",
  provisional: "Provisional",
  unknown: "Không xác định"
};

function providerLabel(provider: string) {
  return PROVIDER_LABELS[provider] ?? provider.replaceAll("_", " ");
}

function cacheStatusLabel(status: string | undefined) {
  if (status === "hit") return "Hit · dùng dữ liệu đã lưu";
  if (status === "miss") return "Miss · trích xuất mới";
  if (status === "bypassed") return "Bypassed · buộc trích xuất lại";
  return "Không xác định";
}

function ProviderResults({
  processed,
  resolved
}: {
  processed: Record<string, number> | undefined;
  resolved: Record<string, number> | undefined;
}) {
  const providers = Array.from(new Set([
    ...Object.keys(processed ?? {}),
    ...Object.keys(resolved ?? {})
  ]));
  if (!providers.length) return null;
  return (
    <section className="backgroundJobProviderSection">
      <strong>Nguồn xác định địa điểm</strong>
      <dl className="backgroundJobProviders">
        {providers.map((provider) => {
          const processedCount = processed?.[provider] ?? 0;
          const resolvedCount = resolved?.[provider] ?? 0;
          return (
            <div className={resolvedCount > 0 ? "resolved" : "unresolved"} key={provider}>
              <dt>{providerLabel(provider)}</dt>
              <dd><b>{resolvedCount}</b> xác định được · {processedCount} đã kiểm tra</dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}

function ProviderAttempts({
  attempts
}: {
  attempts: NonNullable<ExplorerTimingReport["providerAttempts"]> | undefined;
}) {
  if (!attempts?.length) return null;
  return (
    <details className="backgroundJobProviderAttempts">
      <summary>{attempts.length} lần đối chiếu địa điểm</summary>
      <div className="backgroundJobProviderAttemptList">
        {attempts.map((attempt, index) => {
          const isKnowledgeGraph =
            attempt.provider === "knowledge_graph" || attempt.provider === "database";
          const lookupCount = isKnowledgeGraph
            ? attempt.attemptedQueries?.length ?? 0
            : attempt.aliasQueryCount;
          return (
            <div key={`${attempt.candidate}-${attempt.provider}-${index}`}>
              <div className="backgroundJobAttemptHeader">
                <strong>{attempt.candidate}</strong>
                <span>{providerLabel(attempt.provider)}</span>
              </div>
              <div className="backgroundJobAttemptMeta">
                <span><b>Tra cứu</b> {lookupCount} {isKnowledgeGraph ? "tên" : "truy vấn"}</span>
                <span><b>Chờ</b> {timingLabel(attempt.queueWaitSeconds)}</span>
                <span><b>Chạy</b> {timingLabel(attempt.executionSeconds)}</span>
                <span><b>Kết quả</b> {attempt.outcome === "resolved" || attempt.outcome === "cache_hit"
                  ? attempt.outcome === "cache_hit" ? "đã dùng cache" : "đã xác định"
                  : attempt.rejectionReason ?? attempt.outcome}</span>
              </div>
              {attempt.attemptedQueries?.length ? (
                <div className="backgroundJobAttemptQueries">
                  <b>Tên tìm kiếm</b>
                  <span>{attempt.attemptedQueries.join(" · ")}</span>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </details>
  );
}

function JobTimingDetails({
  explorer,
  planner,
  running,
  elapsed,
  sourceUrl
}: {
  explorer: ExplorerTimingReport | null;
  planner: PlanTimingReport | null;
  running: boolean;
  elapsed: number;
  sourceUrl: string;
}) {
  if (!explorer && !planner && !running) return null;
  const completedTotalSeconds = (explorer?.totalSeconds ?? 0) + (planner?.totalSeconds ?? 0);
  const visibleTotalSeconds = completedTotalSeconds > 0 ? completedTotalSeconds : elapsed;

  return (
    <div className="backgroundJobTiming">
      {visibleTotalSeconds > 0 ? (
        <header className="backgroundJobTimingTotal">
          <span>Tổng thời gian</span>
          <strong>{preciseElapsedLabel(visibleTotalSeconds)}</strong>
        </header>
      ) : null}
      <ol className="backgroundJobPipeline">
      {explorer ? (
        <li className="backgroundJobPipelineStep">
          <span className="backgroundJobPipelineIndex">1</span>
          <section>
            <header>
              <span>
                <strong>Tìm và xác định địa điểm</strong>
                <small>{urlPlaceCountLabel(explorer)} · {Math.max(0, explorer.candidateCount - explorer.resolvedCount)} cần kiểm tra</small>
              </span>
              <b>{preciseElapsedLabel(explorer.totalSeconds)}</b>
            </header>
            <details className="backgroundJobStepDetails">
              <summary>Xem chi tiết và thời gian</summary>
              <div>
                <TimingStages stages={explorer.stages} totalSeconds={explorer.totalSeconds} />
                <ProviderResults processed={explorer.providerCounts} resolved={explorer.resolvedProviderCounts} />
                <ProviderAttempts attempts={explorer.providerAttempts} />
                {explorer.sources.map((source) => (
                  <section className="backgroundJobSourceTiming" key={`${source.sourceIndex}-${source.platform}`}>
                    <header>
                      <strong>Nguồn {source.sourceIndex} · {source.platform}</strong>
                      <b>{preciseElapsedLabel(source.totalSeconds)}</b>
                    </header>
                    <small>{sourceLabel(sourceUrl)} · Cache {cacheStatusLabel(source.cacheStatus)}</small>
                    <small>
                      {source.sampledFrames} frame · {source.speechSource?.startsWith("youtube_captions") ? "Caption" : "STT"} {source.speechStatus}
                      {` · Vision ${source.visionStatus} · ${source.extractedPlaceCount} kết quả thô`}
                    </small>
                    {source.expectedPlaceCount != null ? (
                      <small>Coverage {source.extractedPlaceCount}/{source.expectedPlaceCount}{source.extractionCoverage != null ? ` · ${Math.round(source.extractionCoverage * 100)}%` : ""}</small>
                    ) : null}
                    <TimingStages stages={source.stages} totalSeconds={source.totalSeconds} />
                  </section>
                ))}
              </div>
            </details>
          </section>
        </li>
      ) : running ? (
        <li className="backgroundJobPipelineStep running">
          <span className="backgroundJobPipelineIndex">1</span>
          <section><header><span><strong>Đang tìm địa điểm</strong><small>Trích xuất và đối chiếu nguồn</small></span><b>{elapsedLabel(elapsed)}</b></header></section>
        </li>
      ) : null}
      {planner ? (
        <li className="backgroundJobPipelineStep">
          <span className="backgroundJobPipelineIndex">2</span>
          <section>
            <header>
              <span>
                <strong>{planner.status === "running" ? "Đang tạo lịch trình" : "Tạo và kiểm tra lịch trình"}</strong>
                <small>{planner.dayCount} ngày · {planner.itemCount} hoạt động · {planner.unscheduledCount} chưa xếp · {planner.warningCount} cảnh báo</small>
              </span>
              <b>{preciseElapsedLabel(planner.totalSeconds)}</b>
            </header>
            <details className="backgroundJobStepDetails">
              <summary>Xem chi tiết và thời gian</summary>
              <div><TimingStages stages={planner.stages} totalSeconds={planner.totalSeconds} /></div>
            </details>
          </section>
        </li>
      ) : running && explorer ? (
        <li className="backgroundJobPipelineStep running">
          <span className="backgroundJobPipelineIndex">2</span>
          <section><header><span><strong>Đang tạo lịch trình</strong><small>Xếp tuyến và kiểm tra tính khả thi</small></span><b>{elapsedLabel(Math.max(0, elapsed - explorer.totalSeconds))}</b></header></section>
        </li>
      ) : null}
      </ol>
    </div>
  );
}

export function BackgroundUrlJobs({
  authenticated,
  enabled,
  placement = "topbar"
}: {
  authenticated: boolean;
  enabled: boolean;
  placement?: "topbar" | "planner-chat";
}) {
  const router = useRouter();
  const [serverJobs, setServerJobs] = useState<UrlImportJob[]>([]);
  const [plannerRuns, setPlannerRuns] = useState<TripChatTurn[]>([]);
  const [guestJobs, setGuestJobs] = useState<GuestUrlImportJob[]>(() => listGuestUrlJobs());
  const [now, setNow] = useState(() => Date.now());
  const [panelOpen, setPanelOpen] = useState(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ jobId: string; message: string } | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const statusesRef = useRef<Map<string, string>>(new Map());

  useEffect(() => {
    const handleGuestJobs = (event: Event) => {
      const nextJobs = (event as CustomEvent<GuestUrlImportJob[]>).detail;
      const resolvedJobs = Array.isArray(nextJobs) ? nextJobs : listGuestUrlJobs();
      setGuestJobs(resolvedJobs);
    };
    window.addEventListener(GUEST_URL_JOBS_EVENT, handleGuestJobs);
    setGuestJobs(listGuestUrlJobs());
    return () => window.removeEventListener(GUEST_URL_JOBS_EVENT, handleGuestJobs);
  }, []);

  const jobs = useMemo<DisplayJob[]>(
    () => [...guestJobs, ...serverJobs].sort(
      (left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt)
    ),
    [guestJobs, serverJobs]
  );
  const activeTurns = plannerRuns.filter((turn) => ACTIVE_TURN.has(turn.status));
  const savedPlannerRuns = plannerRuns.filter((turn) => !ACTIVE_TURN.has(turn.status));

  useEffect(() => {
    if (!enabled || (!activeTurns.length && !jobs.some((job) => ACTIVE.has(job.status)))) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [activeTurns.length, enabled, jobs]);

  useEffect(() => {
    if (!enabled || !authenticated) {
      setServerJobs([]);
      setPlannerRuns([]);
      statusesRef.current.clear();
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function refresh() {
      try {
        const [response, turns] = await Promise.all([
          listUrlImportJobs(),
          listTripChatPlannerRuns()
        ]);
        if (cancelled) return;
        const previous = statusesRef.current;
        for (const job of response.jobs) {
          const oldStatus = previous.get(job.id);
          if (oldStatus && oldStatus !== job.status && TERMINAL.has(job.status)) {
            window.dispatchEvent(new CustomEvent("travelplanner:url-job-update", { detail: job }));
          }
        }
        statusesRef.current = new Map(response.jobs.map((job) => [job.id, job.status]));
        setServerJobs(response.jobs);
        setPlannerRuns(turns);
        window.dispatchEvent(new CustomEvent("travelplanner:url-jobs-snapshot", {
          detail: response.jobs
        }));
        window.dispatchEvent(new CustomEvent("travelplanner:active-turns-snapshot", {
          detail: turns
        }));
        const hasActive = turns.some((turn) => ACTIVE_TURN.has(turn.status))
          || response.jobs.some((job) => !TERMINAL.has(job.status));
        timer = setTimeout(refresh, hasActive ? 1800 : 8000);
      } catch {
        if (!cancelled) timer = setTimeout(refresh, 8000);
      }
    }

    const refreshNow = (event: Event) => {
      const enqueuedJobs = (event as CustomEvent<UrlImportJob[]>).detail;
      if (Array.isArray(enqueuedJobs)) {
        for (const job of enqueuedJobs) {
          statusesRef.current.set(job.id, job.status);
        }
      }
      if (timer) clearTimeout(timer);
      void refresh();
    };
    window.addEventListener("travelplanner:url-job-enqueued", refreshNow);
    void refresh();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      window.removeEventListener("travelplanner:url-job-enqueued", refreshNow);
    };
  }, [authenticated, enabled]);

  // Keep completed jobs visible while timing diagnostics are being tested.
  // They disappear only when the user explicitly deletes them.
  const visibleJobs = jobs.slice(0, 12);
  const runningJobs = visibleJobs.filter((job) => job.status === "running");
  const running = runningJobs.length;
  const queued = visibleJobs.filter((job) => job.status === "queued").length;
  const failed = visibleJobs.filter((job) => job.status === "failed").length
    + savedPlannerRuns.filter((turn) => turn.status === "failed").length;
  const ready = visibleJobs.filter((job) => job.status === "succeeded").length
    + savedPlannerRuns.filter((turn) => turn.status === "completed").length;
  if (!enabled || (visibleJobs.length === 0 && plannerRuns.length === 0)) return null;

  const primaryRunningJob = runningJobs[0];
  const primaryStage = primaryRunningJob ? progressStage(primaryRunningJob) : null;
  const primaryTurn = activeTurns[0];
  const turnStage = primaryTurn
    ? primaryTurn.status === "queued"
      ? { step: 1, label: "Chuẩn bị" }
      : primaryTurn.status === "classifying"
        ? { step: 2, label: "Khám phá" }
        : { step: 3, label: "Lập kế hoạch" }
    : null;
  const activeCount = running + queued + activeTurns.length;
  if (placement === "planner-chat" && activeCount === 0) return null;

  const primaryElapsed = primaryTurn
    ? Math.max(0, Math.floor((now - Date.parse(primaryTurn.createdAt)) / 1000))
    : primaryRunningJob
      ? elapsedSeconds(primaryRunningJob, now)
      : 0;

  const summary = activeCount
    ? `${activeCount > 1 ? `${activeCount} tác vụ · ` : ""}Bước ${turnStage?.step ?? primaryStage?.step ?? 1}/3 · ${turnStage?.label ?? primaryStage?.label ?? "Chuẩn bị"} · ${elapsedLabel(primaryElapsed)}`
    : ready
      ? ready > 1
        ? `${ready} plan đã sẵn sàng`
        : "Plan đã sẵn sàng"
      : `${failed} tác vụ thất bại`;

  async function runAgain(job: DisplayJob) {
    setRetryingId(job.id);
    setActionError(null);
    try {
      if (isGuestJob(job)) {
        if (job.status === "failed") retryGuestUrlJob(job.id);
        else reprocessGuestUrlJob(job.id);
      } else {
        const updated = job.status === "failed"
          ? await retryUrlImportJob(job.id)
          : await reprocessUrlImportJob(job.id);
        setServerJobs((current) => job.status === "failed"
          ? current.map((item) => item.id === updated.id ? updated : item)
          : [updated, ...current]);
        router.push(`/planner?chatId=${encodeURIComponent(updated.chatId)}`);
        window.dispatchEvent(new CustomEvent("travelplanner:url-job-enqueued", {
          detail: [updated]
        }));
      }
    } catch (caught) {
      setActionError({
        jobId: job.id,
        message: caught instanceof Error ? caught.message : "Không thể chạy lại tác vụ nguồn."
      });
    } finally {
      setRetryingId(null);
    }
  }

  function openJobChat(job: DisplayJob) {
    if (!isGuestJob(job)) {
      router.push(`/planner?chatId=${encodeURIComponent(job.chatId)}`);
    }
  }

  async function removeJob(job: DisplayJob) {
    setDeletingId(job.id);
    try {
      if (isGuestJob(job)) {
        deleteGuestUrlJob(job.id);
      } else {
        await deleteUrlImportJob(job.id);
        setServerJobs((current) => current.filter((item) => item.id !== job.id));
        statusesRef.current.delete(job.id);
      }
    } catch {
      // The job may have completed just before the stop/delete request.
    } finally {
      setDeletingId(null);
      if (!isGuestJob(job)) window.dispatchEvent(new Event("travelplanner:url-job-enqueued"));
    }
  }

  return (
    <div
      aria-live="polite"
      className={`backgroundJobsDock ${
        placement === "planner-chat" ? "backgroundJobsDock--planner-chat" : ""
      }`}
    >
      <details
        className="backgroundJobsPanel"
        onToggle={(event) => setPanelOpen(event.currentTarget.open)}
        open={panelOpen}
      >
        <summary aria-label={summary} title={summary}>
          <span className={activeCount ? "backgroundJobPulse" : "backgroundJobIcon"} aria-hidden="true" />
          <strong>{summary}</strong>
          <span className="backgroundJobsChevron" aria-hidden="true">⌄</span>
        </summary>
        <div className="backgroundJobsList">
          <div className="backgroundJobsListHeader">
            <strong>
              {activeCount
                ? "Chuyến đi đang được xử lý"
                : ready
                  ? "Lịch trình đã sẵn sàng"
                  : "Nguồn xử lý thất bại"}
            </strong>
          </div>
          {activeTurns.map((turn) => {
            const stage = turn.status === "queued"
              ? { step: 1, label: "Chuẩn bị" }
              : turn.status === "classifying"
                ? { step: 2, label: "Khám phá" }
                : { step: 3, label: "Lập kế hoạch" };
            const elapsed = Math.max(0, Math.floor((now - Date.parse(turn.createdAt)) / 1000));
            const explorerTiming = turnTiming<ExplorerTimingReport>(turn, "explorerTiming");
            const plannerTiming = turnTiming<PlanTimingReport>(turn, "plannerTiming");
            return (
              <details className="backgroundJobRow running" key={`turn-${turn.id}`}>
                <summary className="backgroundTurnSummary">
                  <span className="backgroundJobState" aria-hidden="true" />
                  <span className="backgroundJobCopy">
                    <strong>AI Planner</strong>
                    <small>Bước {stage.step}/3 · {stage.label} · {elapsedLabel(elapsed)}</small>
                  </span>
                  <span className="backgroundJobRowChevron" aria-hidden="true">⌄</span>
                </summary>
                <div className="backgroundJobDetails">
                  <JobTimingDetails
                    explorer={explorerTiming}
                    planner={plannerTiming}
                    running
                    elapsed={elapsed}
                    sourceUrl=""
                  />
                </div>
              </details>
            );
          })}
          {savedPlannerRuns.map((turn) => {
            const explorerTiming = turnTiming<ExplorerTimingReport>(turn, "explorerTiming");
            const plannerTiming = turnTiming<PlanTimingReport>(turn, "plannerTiming");
            const measuredSeconds = (explorerTiming?.totalSeconds ?? 0) + (plannerTiming?.totalSeconds ?? 0);
            return (
              <details
                className={`backgroundJobRow ${turn.status === "completed" ? "succeeded" : "failed"}`}
                key={`turn-${turn.id}`}
              >
                <summary>
                  <span className="backgroundJobState" aria-hidden="true">
                    {turn.status === "completed" ? "✓" : "!"}
                  </span>
                  <span className="backgroundJobCopy">
                    <strong>AI Planner · Raw prompt</strong>
                    <small>
                      {turn.status === "completed" ? "Đã hoàn tất" : "Cần thử lại"}
                      {measuredSeconds > 0 ? ` · ${preciseElapsedLabel(measuredSeconds)}` : ""}
                    </small>
                  </span>
                  <span className="backgroundJobRowChevron" aria-hidden="true">⌄</span>
                </summary>
                <div className="backgroundJobDetails">
                  <JobTimingDetails
                    explorer={explorerTiming}
                    planner={plannerTiming}
                    running={false}
                    elapsed={measuredSeconds}
                    sourceUrl=""
                  />
                  <div className="backgroundJobActions">
                    <button
                      onClick={() => router.push(`/planner?chatId=${encodeURIComponent(turn.chatId)}`)}
                      type="button"
                    >
                      Mở chat chuyến đi
                    </button>
                  </div>
                </div>
              </details>
            );
          })}
          {visibleJobs.map((job) => {
            return (
              <details className={`backgroundJobRow ${job.status}`} key={job.id}>
                <summary>
                  <span className="backgroundJobState" aria-hidden="true">
                    {job.status === "succeeded" ? "✓" : job.status === "failed" ? "!" : job.status === "queued" ? "…" : ""}
                  </span>
                  <span className="backgroundJobCopy">
                    <strong title={job.sourceLabel}>{jobSourceLabel(job)}</strong>
                    <small>{statusLabel(job, now)}</small>
                  </span>
                  <span className="backgroundJobRowChevron" aria-hidden="true">⌄</span>
                </summary>
                <div className="backgroundJobDetails">
                  <div className="backgroundJobMeta">
                    <span><small>Lần chạy</small><strong>{job.attemptCount}</strong></span>
                  </div>
                  <JobTimingDetails
                    explorer={job.explorerTiming}
                    planner={job.plannerTiming}
                    running={job.status === "running"}
                    elapsed={elapsedSeconds(job, now)}
                    sourceUrl={job.url}
                  />
                  {job.status === "failed" && job.errorMessage ? (
                    <p className="backgroundJobError">{job.errorMessage}</p>
                  ) : null}
                  {actionError?.jobId === job.id ? (
                    <p className="backgroundJobError">{actionError.message}</p>
                  ) : null}
                  <div className="backgroundJobActions">
                    {!isGuestJob(job) ? (
                      <button
                        onClick={() => openJobChat(job)}
                        type="button"
                      >
                        Mở chat chuyến đi
                      </button>
                    ) : null}
                    {TERMINAL.has(job.status) ? (
                      <button
                        disabled={retryingId === job.id}
                        onClick={() => void runAgain(job)}
                        title={job.status === "failed"
                          ? "Tác vụ lỗi sẽ chạy lại toàn bộ từ đầu"
                          : job.sourceType === "image"
                            ? "Chạy lại OCR từ ảnh gốc, resolve và Planner"
                            : "Chạy lại toàn bộ từ media, STT/OCR, resolve đến Planner"
                        }
                        type="button"
                      >
                        {retryingId === job.id
                          ? "Đang thêm…"
                          : job.sourceType === "image"
                            ? "Chạy lại OCR + plan"
                            : "Trích xuất lại + cập nhật plan"}
                      </button>
                    ) : null}
                    <button
                      className="backgroundJobDelete"
                      disabled={deletingId === job.id}
                      onClick={() => void removeJob(job)}
                      type="button"
                    >
                      {deletingId === job.id
                        ? "Đang xóa…"
                        : job.status === "running"
                          ? "Dừng tác vụ"
                          : job.status === "queued"
                            ? "Xóa khỏi hàng chờ"
                            : "Xóa tác vụ"}
                    </button>
                  </div>
                </div>
              </details>
            );
          })}
        </div>
      </details>
    </div>
  );
}
