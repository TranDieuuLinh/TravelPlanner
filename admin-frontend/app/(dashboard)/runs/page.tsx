"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  APIError,
  PlanningRunDetail,
  PlanningRunSummary,
  getRun,
  listRuns,
} from "../../../lib/api";
import {
  STAGES,
  STATUSES,
  StageInspector,
  durationLabel,
  formatDate,
  statusLabel,
} from "../../components/shared";

export default function RunsPage() {
  const [runs, setRuns] = useState<PlanningRunSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<PlanningRunDetail | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [stage, setStage] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeStageId, setActiveStageId] = useState<string | null>(null);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await listRuns({ query, status, stage });
      setRuns(result.items);
      setTotal(result.total);
      if (!selected && result.items[0]) {
        setDetailLoading(true);
        try {
          setSelected(await getRun(result.items[0].id));
        } finally {
          setDetailLoading(false);
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không tải được run.");
    } finally {
      setLoading(false);
    }
  }, [query, selected, stage, status]);

  useEffect(() => {
    const timer = window.setTimeout(loadRuns, 250);
    return () => window.clearTimeout(timer);
  }, [loadRuns]);

  const metrics = useMemo(() => {
    const failed = runs.filter((run) => run.status === "failed").length;
    const running = runs.filter((run) => run.status === "running").length;
    const durations = runs
      .map((run) =>
        run.completedAt
          ? new Date(run.completedAt).getTime() - new Date(run.createdAt).getTime()
          : 0
      )
      .filter(Boolean);
    return {
      failed,
      running,
      successRate: runs.length
        ? Math.round(((runs.length - failed) / runs.length) * 100)
        : 0,
      median: durations.length
        ? durations.sort((a, b) => a - b)[Math.floor(durations.length / 2)]
        : 0
    };
  }, [runs]);

  async function selectRun(runId: string) {
    setDetailLoading(true);
    setError("");
    try {
      setSelected(await getRun(runId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không tải được chi tiết.");
    } finally {
      setDetailLoading(false);
    }
  }

  const currentStageList = selected?.stages || [];
  const currentActiveStageId = 
    (activeStageId && currentStageList.some(s => s.id === activeStageId))
      ? activeStageId 
      : currentStageList[0]?.id;
  const currentActiveStage = currentStageList.find(s => s.id === currentActiveStageId);

  return (
    <>
      <header className="topbar">
        <div>
          <p className="eyebrow">Operational intelligence</p>
          <h1>Planning runs</h1>
        </div>
        <button type="button" className="refreshButton" onClick={loadRuns}>
          ↻ Làm mới
        </button>
      </header>

      <section className="metricGrid" aria-label="Planning run metrics">
        <article>
          <span>Tổng run</span>
          <strong>{total}</strong>
          <small>Trong bộ lọc hiện tại</small>
        </article>
        <article>
          <span>Tỷ lệ hoàn tất</span>
          <strong>{metrics.successRate}%</strong>
          <small>{metrics.failed} run thất bại</small>
        </article>
        <article>
          <span>Đang xử lý</span>
          <strong>{metrics.running}</strong>
          <small>Luồng chưa đóng</small>
        </article>
        <article>
          <span>Thời gian trung vị</span>
          <strong>{durationLabel(metrics.median)}</strong>
          <small>Explorer đến Checker</small>
        </article>
      </section>

      <section className="controlBar">
        <label className="searchField">
          <span>⌕</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Tìm destination, run ID, intake ID…"
          />
        </label>
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">Mọi trạng thái</option>
          {STATUSES.map((value) => (
            <option value={value} key={value}>
              {statusLabel(value)}
            </option>
          ))}
        </select>
        <select value={stage} onChange={(event) => setStage(event.target.value)}>
          <option value="">Mọi stage</option>
          {STAGES.map((value) => (
            <option value={value} key={value}>
              {value}
            </option>
          ))}
        </select>
      </section>

      {error && <div className="pageError">{error}</div>}

      <section className="dataLayout" id="runs">
        <div className="runList">
          <header>
            <span>{total} runs</span>
            {loading && <small>Đang đồng bộ…</small>}
          </header>
          {!loading && runs.length === 0 && (
            <div className="emptyState">
              <b>Chưa có planning run</b>
              <p>Run mới sẽ xuất hiện sau khi Explorer hoặc Planner được gọi.</p>
            </div>
          )}
          {runs.map((run) => (
            <button
              type="button"
              key={run.id}
              onClick={() => selectRun(run.id)}
              className={selected?.id === run.id ? "runCard active" : "runCard"}
            >
              <div className="runCardTop">
                <span className={`status status-${run.status}`}>
                  {statusLabel(run.status)}
                </span>
                <time>{formatDate(run.createdAt)}</time>
              </div>
              <h3>{run.destination}</h3>
              <p>
                {run.source.replaceAll("_", " ")} · {run.stageCount} stage
              </p>
              <div className="runRoute" aria-label="Run stages">
                {["explorer", "planner", "finder", "checker"].map((item, index) => (
                  <span
                    key={item}
                    className={index < run.stageCount ? "done" : ""}
                    title={item}
                  />
                ))}
              </div>
              <code>{run.id.slice(0, 8)}</code>
            </button>
          ))}
        </div>

        <div className="detailPane">
          {detailLoading && <div className="detailLoading">Đang mở run…</div>}
          {!detailLoading && selected && (
            <>
              <header className="detailHeader">
                <div>
                  <p className="eyebrow">
                    Run {selected.id.slice(0, 8)}
                  </p>
                  <h2>{selected.destination}</h2>
                  <p>
                    {selected.source.replaceAll("_", " ")} ·{" "}
                    {formatDate(selected.createdAt)}
                  </p>
                </div>
                <span className={`status status-${selected.status}`}>
                  {statusLabel(selected.status)}
                </span>
              </header>
              <div className="runFacts">
                <span>
                  <small>Intake</small>
                  <code>{selected.intakeId?.slice(0, 12) ?? "Không có"}</code>
                </span>
                <span>
                  <small>User</small>
                  <b>{selected.userId ?? "Ẩn danh"}</b>
                </span>
                <span>
                  <small>Stage cuối</small>
                  <b>{selected.currentStage ?? "—"}</b>
                </span>
                <span>
                  <small>Warnings</small>
                  <b>{String(selected.summary.warningCount ?? 0)}</b>
                </span>
              </div>
              {selected.errorMessage && (
                <div className="runError">
                  <b>{selected.errorCode ?? "Run failed"}</b>
                  <p>{selected.errorMessage}</p>
                </div>
              )}
              <div className="stageStack">
                <div className="tabList" role="tablist">
                  {selected.stages.map((runStage) => (
                    <button
                      key={runStage.id}
                      type="button"
                      className={runStage.id === currentActiveStageId ? "active" : ""}
                      onClick={() => setActiveStageId(runStage.id)}
                      role="tab"
                      aria-selected={runStage.id === currentActiveStageId}
                    >
                      0{runStage.sequence}. {runStage.stage}
                    </button>
                  ))}
                </div>
                {currentActiveStage && (
                  <StageInspector key={currentActiveStage.id} stage={currentActiveStage} />
                )}
              </div>
            </>
          )}
          {!detailLoading && !selected && (
            <div className="detailEmpty">
              <b>Chọn một run để điều tra</b>
              <p>Input và output đã redaction sẽ xuất hiện tại đây.</p>
            </div>
          )}
        </div>
      </section>
    </>
  );
}
