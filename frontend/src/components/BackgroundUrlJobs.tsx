"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  deleteUrlImportJob,
  listUrlImportJobs,
  reprocessUrlImportJob,
  retryUrlImportJob,
  type ExplorerTimingReport,
  type ExplorerTimingStage,
  type PlanTimingReport,
  type PlanTimingStage,
  type UrlImportJob
} from "@/lib/plans";
import {
  deleteGuestUrlJob,
  GUEST_URL_JOBS_EVENT,
  listGuestUrlJobs,
  reprocessGuestUrlJob,
  retryGuestUrlJob,
  type GuestUrlImportJob
} from "@/lib/guest-url-jobs";

const TERMINAL = new Set(["succeeded", "failed"]);
const ACTIVE = new Set(["queued", "running"]);
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

function detailLabel(value: string | number | boolean | null) {
  if (typeof value === "boolean") return value ? "Có" : "Không";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return value ?? "—";
}

function statusLabel(job: DisplayJob, now: number) {
  if (job.status === "running") {
    const action = isGuestJob(job) && job.phase === "planning"
      ? "Planner + Finder đang tạo lịch trình"
      : job.forceRefresh
        ? "Explorer đang phân tích lại video"
        : isGuestJob(job)
          ? "Explorer đang trích xuất nội dung và địa điểm"
          : "Explorer → Planner + Finder đang xử lý";
    return `${action} · ${elapsedLabel(elapsedSeconds(job, now))}`;
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
  label,
  stages
}: {
  label: string;
  stages: Array<ExplorerTimingStage | PlanTimingStage>;
}) {
  if (stages.length === 0) return null;
  return (
    <section className="backgroundJobTimingGroup">
      <strong>{label}</strong>
      <ol>
        {stages.map((stage, index) => {
          const details = Object.entries(stage.details ?? {});
          return (
            <li key={`${label}-${stage.key}`}>
              <span className="backgroundJobTimingStepIndex">{index + 1}</span>
              <span className="backgroundJobTimingStepCopy">
                <span>{stage.label}</span>
                {details.length ? (
                  <small>
                    {details.map(([key, value]) => `${key}: ${detailLabel(value)}`).join(" · ")}
                  </small>
                ) : null}
              </span>
              <b>{timingLabel(Math.max(0, stage.durationSeconds))}</b>
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
  database: "Places DB",
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
      <summary>Chi tiết từng lần resolve ({attempts.length})</summary>
      <div className="backgroundJobProviderAttemptList">
        {attempts.map((attempt, index) => (
          <div key={`${attempt.candidate}-${attempt.provider}-${index}`}>
            <strong>{attempt.candidate}</strong>
            <span>{providerLabel(attempt.provider)}</span>
            <span>{attempt.aliasQueryCount} query</span>
            <span>chờ {timingLabel(attempt.queueWaitSeconds)}</span>
            <span>chạy {timingLabel(attempt.executionSeconds)}</span>
            <span>
              {attempt.outcome === "resolved" || attempt.outcome === "cache_hit"
                ? "đã xác định"
                : attempt.rejectionReason ?? attempt.outcome}
            </span>
          </div>
        ))}
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

  return (
    <div className="backgroundJobTiming">
      {explorer ? (
        <section className="backgroundJobTimingSummary">
          <header>
            <strong>Kết quả địa điểm</strong>
            <b>{timingLabel(explorer.totalSeconds)}</b>
          </header>
          <div className="backgroundJobTimingChips">
            <span>
              Đã xác định {explorer.resolvedCount} trên {explorer.candidateCount} địa điểm
            </span>
            {explorer.candidateCount > explorer.resolvedCount ? (
              <span>{explorer.candidateCount - explorer.resolvedCount} cần kiểm tra thêm</span>
            ) : null}
          </div>
          <ProviderResults
            processed={explorer.providerCounts}
            resolved={explorer.resolvedProviderCounts}
          />
          <ProviderAttempts attempts={explorer.providerAttempts} />
          <TimingStages label="Các bước Explorer" stages={explorer.stages} />
          {explorer.sources.map((source) => (
            <section
              className="backgroundJobSourceTiming"
              key={`${source.sourceIndex}-${source.platform}`}
            >
              <header>
                <strong>URL {source.sourceIndex} · {source.platform}</strong>
                <b>{timingLabel(source.totalSeconds)}</b>
              </header>
              <small>
                Cache URL {sourceLabel(sourceUrl)}: {cacheStatusLabel(source.cacheStatus)}
                {` · tra trong ${timingLabel(source.cacheLookupSeconds ?? 0)}`}
              </small>
              <small>
                {source.sampledFrames} frame · STT {source.speechStatus}
                {` · ${source.sttChunkCount ?? 1} STT chunk`}
                {` · Vision ${source.visionStatus}`}
                {source.cacheStatus === "hit"
                  ? ` · ${source.extractedPlaceCount} bản ghi extraction từ cache`
                  : ` · ${source.extractedPlaceCount} kết quả extraction thô`}
              </small>
              {source.cacheStatus === "hit" ? (
                <small>
                  Provider bên dưới là nguồn gốc của snapshot đã resolve; không
                  đồng nghĩa provider đã được gọi lại trong lượt này.
                </small>
              ) : null}
              {source.sttAudioDurationSeconds != null || source.sttChunkDurationSeconds?.length ? (
                <small>
                  Audio {source.sttAudioDurationSeconds == null ? "—" : timingLabel(source.sttAudioDurationSeconds)}
                  {source.sttChunkDurationSeconds?.length
                    ? ` · chunk ${source.sttChunkDurationSeconds.map(timingLabel).join(", ")}`
                    : ""}
                  {` · ${source.sttChunkRetryCount ?? 0} retry`}
                </small>
              ) : null}
              <ProviderResults
                processed={source.providerCounts}
                resolved={source.resolvedProviderCounts}
              />
              <TimingStages label="Chi tiết URL" stages={source.stages} />
            </section>
          ))}
        </section>
      ) : running ? (
        <section className="backgroundJobTimingSummary backgroundJobTimingPending">
          <header>
            <strong>Đang tìm và xác định địa điểm</strong>
            <b>{elapsedLabel(elapsed)}</b>
          </header>
        </section>
      ) : null}
      {planner ? (
        <section className="backgroundJobTimingSummary">
          <header>
            <strong>Planner + Finder</strong>
            <b>{timingLabel(planner.totalSeconds)}</b>
          </header>
          <div className="backgroundJobTimingChips">
            <span>{planner.dayCount} ngày</span>
            <span>{planner.itemCount} item</span>
            <span>{planner.transportLegCount} chặng</span>
            <span>{planner.unscheduledCount} chưa xếp</span>
            <span>{planner.warningCount} cảnh báo</span>
          </div>
          <TimingStages label="Các bước Planner + Finder" stages={planner.stages} />
        </section>
      ) : null}
    </div>
  );
}

export function BackgroundUrlJobs({
  authenticated,
  enabled
}: {
  authenticated: boolean;
  enabled: boolean;
}) {
  const [serverJobs, setServerJobs] = useState<UrlImportJob[]>([]);
  const [guestJobs, setGuestJobs] = useState<GuestUrlImportJob[]>(() => listGuestUrlJobs());
  const [now, setNow] = useState(() => Date.now());
  const [panelOpen, setPanelOpen] = useState(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ jobId: string; message: string } | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [clearingFinished, setClearingFinished] = useState(false);
  const statusesRef = useRef<Map<string, string>>(new Map());

  useEffect(() => {
    const handleGuestJobs = (event: Event) => {
      const nextJobs = (event as CustomEvent<GuestUrlImportJob[]>).detail;
      setGuestJobs(Array.isArray(nextJobs) ? nextJobs : listGuestUrlJobs());
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

  useEffect(() => {
    if (!enabled || !jobs.some((job) => ACTIVE.has(job.status))) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [enabled, jobs]);

  useEffect(() => {
    if (!enabled || !authenticated) {
      setServerJobs([]);
      statusesRef.current.clear();
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function refresh() {
      try {
        const response = await listUrlImportJobs();
        if (cancelled) return;
        const previous = statusesRef.current;
        for (const job of response.jobs) {
          const oldStatus = previous.get(job.id);
          if (oldStatus && oldStatus !== job.status && TERMINAL.has(job.status)) {
            window.dispatchEvent(new CustomEvent("vsf:url-job-update", { detail: job }));
          }
        }
        statusesRef.current = new Map(response.jobs.map((job) => [job.id, job.status]));
        setServerJobs(response.jobs);
        window.dispatchEvent(new CustomEvent("vsf:url-jobs-snapshot", {
          detail: response.jobs
        }));
        const hasActive = response.jobs.some((job) => !TERMINAL.has(job.status));
        timer = setTimeout(refresh, hasActive ? 1800 : 8000);
      } catch {
        if (!cancelled) timer = setTimeout(refresh, 8000);
      }
    }

    const refreshNow = () => {
      if (timer) clearTimeout(timer);
      void refresh();
    };
    window.addEventListener("vsf:url-job-enqueued", refreshNow);
    void refresh();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      window.removeEventListener("vsf:url-job-enqueued", refreshNow);
    };
  }, [authenticated, enabled]);

  const visibleJobs = jobs.slice(0, 12);
  const running = jobs.filter((job) => job.status === "running").length;
  const queued = jobs.filter((job) => job.status === "queued").length;
  const finished = jobs.filter((job) => TERMINAL.has(job.status));
  if (!enabled || visibleJobs.length === 0) return null;

  const summary = running || queued
    ? `${running ? `${running} đang xử lý` : ""}${running && queued ? " · " : ""}${queued ? `${queued} đang chờ` : ""}`
    : `${jobs.length} tác vụ URL`;

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
        window.dispatchEvent(new Event("vsf:url-job-enqueued"));
      }
    } catch (caught) {
      setActionError({
        jobId: job.id,
        message: caught instanceof Error ? caught.message : "Không thể chạy lại tác vụ URL."
      });
    } finally {
      setRetryingId(null);
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
      if (!isGuestJob(job)) window.dispatchEvent(new Event("vsf:url-job-enqueued"));
    }
  }

  async function clearFinishedJobs() {
    setClearingFinished(true);
    try {
      const serverFinished = finished.filter((job): job is UrlImportJob => !isGuestJob(job));
      finished.filter(isGuestJob).forEach((job) => deleteGuestUrlJob(job.id));

      const results = await Promise.allSettled(
        serverFinished.map((job) => deleteUrlImportJob(job.id))
      );
      const deletedIds = new Set(
        serverFinished
          .filter((_, index) => results[index]?.status === "fulfilled")
          .map((job) => job.id)
      );
      if (deletedIds.size > 0) {
        setServerJobs((current) => current.filter((job) => !deletedIds.has(job.id)));
        deletedIds.forEach((id) => statusesRef.current.delete(id));
        window.dispatchEvent(new Event("vsf:url-job-enqueued"));
      }
    } finally {
      setClearingFinished(false);
    }
  }

  return (
    <div className="backgroundJobsDock">
      <details
        className="backgroundJobsPanel"
        onToggle={(event) => setPanelOpen(event.currentTarget.open)}
        open={panelOpen}
      >
        <summary aria-label={summary} title={summary}>
          <span className={running || queued ? "backgroundJobPulse" : "backgroundJobIcon"} aria-hidden="true" />
          <strong>{summary}</strong>
          <span className="backgroundJobsChevron" aria-hidden="true">⌄</span>
        </summary>
        <div className="backgroundJobsList" aria-live="polite">
          <div className="backgroundJobsListHeader">
            <strong>Tác vụ URL gần đây</strong>
            {finished.length > 0 ? (
              <button
                disabled={clearingFinished}
                onClick={() => void clearFinishedJobs()}
                type="button"
              >
                {clearingFinished ? "Đang xóa…" : `Xóa đã xong (${finished.length})`}
              </button>
            ) : null}
          </div>
          {visibleJobs.map((job) => {
            return (
              <details className={`backgroundJobRow ${job.status}`} key={job.id}>
                <summary>
                  <span className="backgroundJobState" aria-hidden="true">
                    {job.status === "succeeded" ? "✓" : job.status === "failed" ? "!" : job.status === "queued" ? "…" : ""}
                  </span>
                  <span className="backgroundJobCopy">
                    <strong title={job.url}>{sourceLabel(job.url)}</strong>
                    <small>{statusLabel(job, now)}</small>
                  </span>
                  <span className="backgroundJobRowChevron" aria-hidden="true">⌄</span>
                </summary>
                <div className="backgroundJobDetails">
                  <div className="backgroundJobMeta">
                    <span>
                      <small>Địa điểm đã xác định</small>
                      <strong>
                        {job.explorerTiming
                          ? job.explorerTiming.candidateCount > 0
                            ? `${job.explorerTiming.resolvedCount} trên ${job.explorerTiming.candidateCount} địa điểm`
                            : "Chưa tìm thấy địa điểm"
                          : job.status === "running"
                            ? "Đang tìm kiếm…"
                            : job.status === "queued"
                              ? "Chưa bắt đầu"
                              : "Chưa có kết quả"}
                      </strong>
                    </span>
                    <span>
                      <small>Thời gian xử lý</small>
                      <strong>{job.startedAt ? elapsedLabel(elapsedSeconds(job, now)) : "Chưa bắt đầu"}</strong>
                    </span>
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
                    {TERMINAL.has(job.status) ? (
                      <button
                        disabled={retryingId === job.id}
                        onClick={() => void runAgain(job)}
                        title={job.status === "failed"
                          ? "Tác vụ lỗi sẽ chạy lại toàn bộ từ đầu"
                          : "Dùng extraction cache hợp lệ rồi chạy lại dedupe, resolve và Planner"
                        }
                        type="button"
                      >
                        {retryingId === job.id ? "Đang thêm…" : "Chạy lại"}
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
