"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  deleteUrlImportJob,
  listActiveTripChatTurns,
  listUrlImportJobs,
  reprocessUrlImportJob,
  retryUrlImportJob,
  type ExplorerTimingReport,
  type ExplorerTimingStage,
  type PlanTimingReport,
  type PlanTimingStage,
  type TripChatTurn,
  type UrlImportJob
} from "@/lib/plans";
import { urlPlaceCountLabel } from "@/lib/url-place-count";

const TERMINAL = new Set(["succeeded", "failed"]);
const ACTIVE = new Set(["queued", "running"]);
type DisplayJob = UrlImportJob;

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
                    {details.map(([key, value]) => `${detailKeyLabel(key)}: ${detailLabel(value)}`).join(" · ")}
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
    <details className="backgroundJobProviderAttempts" open>
      <summary>Chi tiết từng lần resolve ({attempts.length})</summary>
      <div className="backgroundJobProviderAttemptList">
        {attempts.map((attempt, index) => (
          <div key={`${attempt.candidate}-${attempt.provider}-${index}`}>
            <strong>{attempt.candidate}</strong>
            <span>{providerLabel(attempt.provider)}</span>
            <span>{attempt.aliasQueryCount} keyword</span>
            {attempt.attemptedQueries?.length ? (
              <span>Keyword: {attempt.attemptedQueries.join(" · ")}</span>
            ) : null}
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
              {urlPlaceCountLabel(explorer)}
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
                {source.sampledFrames} frame · {source.speechSource === "shared_url_cache"
                  ? "Extraction cache"
                  : source.speechSource?.startsWith("youtube_captions")
                    ? "YouTube caption"
                    : "STT"} {source.speechStatus}
                {!source.speechSource?.startsWith("youtube_captions")
                  && source.speechSource !== "shared_url_cache"
                  ? ` · ${source.sttChunkCount ?? 1} STT chunk`
                  : ""}
                {` · Vision ${source.visionStatus}`}
                {source.cacheStatus === "hit"
                  ? ` · ${source.extractedPlaceCount} bản ghi extraction từ cache`
                  : ` · ${source.extractedPlaceCount} kết quả extraction thô`}
              </small>
              {source.expectedPlaceCount != null ? (
                <small>
                  Coverage {source.extractedPlaceCount}/{source.expectedPlaceCount}
                  {source.extractionCoverage != null
                    ? ` · ${Math.round(source.extractionCoverage * 100)}%`
                    : ""}
                  {source.coverageStatus ? ` · ${source.coverageStatus}` : ""}
                </small>
              ) : null}
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
          <small>
            Explorer đang chạy URL extraction → gộp candidate → Knowledge Graph
            Top-K theo tên/alias → Google Maps Playwright khi KG không đủ tin cậy
            → lưu PostgreSQL.
            Keyword và timer chính xác của từng lượt sẽ hiện ngay khi resolve xong.
          </small>
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
      ) : running && explorer ? (
        <section className="backgroundJobTimingSummary backgroundJobTimingPending">
          <header>
            <strong>Planner + Finder đang chạy</strong>
            <b>{elapsedLabel(Math.max(0, elapsed - explorer.totalSeconds))}</b>
          </header>
          <small>
            TripThemePlanner (Knowledge Graph DB + LLM) → PlaceSelector
            (Knowledge Graph DB + rules) → dựng plan → kiểm tra tính khả thi. Timer từng
            bước sẽ được giữ lại tại đây sau khi hoàn tất.
          </small>
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
  const [activeTurns, setActiveTurns] = useState<TripChatTurn[]>([]);
  const [now, setNow] = useState(() => Date.now());
  const [panelOpen, setPanelOpen] = useState(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ jobId: string; message: string } | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const statusesRef = useRef<Map<string, string>>(new Map());
  const jobs = useMemo<DisplayJob[]>(
    () => [...serverJobs].sort(
      (left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt)
    ),
    [serverJobs]
  );

  useEffect(() => {
    if (!enabled || (!activeTurns.length && !jobs.some((job) => ACTIVE.has(job.status)))) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [activeTurns.length, enabled, jobs]);

  useEffect(() => {
    if (!enabled || !authenticated) {
      setServerJobs([]);
      setActiveTurns([]);
      statusesRef.current.clear();
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function refresh() {
      try {
        const [response, turns] = await Promise.all([
          listUrlImportJobs(),
          listActiveTripChatTurns()
        ]);
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
        setActiveTurns(turns);
        window.dispatchEvent(new CustomEvent("vsf:url-jobs-snapshot", {
          detail: response.jobs
        }));
        window.dispatchEvent(new CustomEvent("vsf:active-turns-snapshot", {
          detail: turns
        }));
        const hasActive = turns.length > 0 || response.jobs.some((job) => !TERMINAL.has(job.status));
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

  // Keep completed jobs visible while timing diagnostics are being tested.
  // They disappear only when the user explicitly deletes them.
  const visibleJobs = jobs.slice(0, 12);
  const runningJobs = visibleJobs.filter((job) => job.status === "running");
  const running = runningJobs.length;
  const queued = visibleJobs.filter((job) => job.status === "queued").length;
  const failed = visibleJobs.filter((job) => job.status === "failed").length;
  const ready = visibleJobs.filter((job) => job.status === "succeeded").length;
  if (!enabled || (visibleJobs.length === 0 && activeTurns.length === 0)) return null;

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
      const updated = job.status === "failed"
        ? await retryUrlImportJob(job.id)
        : await reprocessUrlImportJob(job.id);
      setServerJobs((current) => job.status === "failed"
        ? current.map((item) => item.id === updated.id ? updated : item)
        : [updated, ...current]);
      window.dispatchEvent(new Event("vsf:url-job-enqueued"));
    } catch (caught) {
      setActionError({
        jobId: job.id,
        message: caught instanceof Error ? caught.message : "Không thể chạy lại tác vụ nguồn."
      });
    } finally {
      setRetryingId(null);
    }
  }

  async function removeJob(job: DisplayJob) {
    setDeletingId(job.id);
    try {
      await deleteUrlImportJob(job.id);
      setServerJobs((current) => current.filter((item) => item.id !== job.id));
      statusesRef.current.delete(job.id);
    } catch {
      // The job may have completed just before the stop/delete request.
    } finally {
      setDeletingId(null);
      window.dispatchEvent(new Event("vsf:url-job-enqueued"));
    }
  }

  return (
    <div aria-live="polite" className="backgroundJobsDock">
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
            return (
              <div className="backgroundJobRow running" key={`turn-${turn.id}`}>
                <div className="backgroundTurnSummary">
                  <span className="backgroundJobState" aria-hidden="true" />
                  <span className="backgroundJobCopy">
                    <strong>AI Planner</strong>
                    <small>Bước {stage.step}/3 · {stage.label} · {elapsedLabel(elapsed)}</small>
                  </span>
                  <Link className="backgroundJobOpenChat" href={`/planner?chatId=${encodeURIComponent(turn.chatId)}`}>
                    Quay lại chuyến đi
                  </Link>
                </div>
              </div>
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
                    <span>
                      <small>Địa điểm duy nhất từ nguồn</small>
                      <strong>
                        {job.explorerTiming
                          ? urlPlaceCountLabel(job.explorerTiming)
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
                    <Link
                      className="backgroundJobOpenChat"
                      href={
                        `/planner?chatId=${encodeURIComponent(job.chatId)}`
                      }
                    >
                      {job.status === "succeeded"
                        ? "Xem lịch trình"
                        : "Quay lại chuyến đi"}
                    </Link>
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
