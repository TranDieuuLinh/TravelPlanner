"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState
} from "react";
import {
  APIError,
  AdminUser,
  GoldenCase,
  GoldenCaseExecution,
  PlanningRunDetail,
  PlanningRunStage,
  PlanningRunSummary,
  getRun,
  listGoldenCases,
  listRuns,
  login,
  logout,
  runGoldenCase
} from "../lib/api";

const STAGES = ["explorer", "planner", "finder", "checker", "workflow"];
const STATUSES = ["running", "completed", "blocked", "failed", "passed", "draft"];

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(value));
}

function durationLabel(milliseconds: number | null): string {
  if (milliseconds === null) return "—";
  if (milliseconds < 1_000) return `${milliseconds} ms`;
  return `${(milliseconds / 1_000).toFixed(milliseconds < 10_000 ? 1 : 0)} s`;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    completed: "Hoàn tất",
    running: "Đang chạy",
    failed: "Thất bại",
    blocked: "Bị chặn",
    passed: "Đạt",
    warning: "Cảnh báo",
    draft: "Bản nháp"
  };
  return labels[status] ?? status;
}

function JsonPanel({ value }: { value: unknown }) {
  return (
    <pre className="jsonPanel">
      <code>{JSON.stringify(value, null, 2)}</code>
    </pre>
  );
}

function LoginScreen({
  onSignedIn
}: {
  onSignedIn: (user: AdminUser) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onSignedIn(await login(email, password));
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Không thể đăng nhập."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="loginPage">
      <section className="loginStory">
        <div className="brandMark">VSF</div>
        <p className="eyebrow">Planning control</p>
        <h1>Nhìn xuyên suốt từng quyết định của lịch trình.</h1>
        <p className="loginLead">
          Một bề mặt vận hành riêng cho Explorer, Planner, Finder và Checker —
          đủ chi tiết để điều tra, đủ an toàn để không phơi dữ liệu thô.
        </p>
        <div className="signalStrip" aria-label="Các stage được quan sát">
          {["Explorer", "Planner", "Finder", "Checker"].map((stage, index) => (
            <span key={stage}>
              <b>0{index + 1}</b>
              {stage}
            </span>
          ))}
        </div>
      </section>
      <section className="loginPanel">
        <form onSubmit={submit} className="loginCard">
          <p className="eyebrow">Khu vực hạn chế</p>
          <h2>Đăng nhập quản trị</h2>
          <p>Dùng tài khoản VSF có role admin.</p>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              placeholder="admin@vsf.travel"
              required
            />
          </label>
          <label>
            Mật khẩu
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              placeholder="••••••••••••"
              required
            />
          </label>
          {error && <div className="formError">{error}</div>}
          <button type="submit" disabled={busy}>
            {busy ? "Đang xác thực…" : "Vào Planning Control"}
          </button>
          <small>
            Input nhạy cảm, media và toàn bộ prompt không được lưu trong console.
          </small>
        </form>
      </section>
    </main>
  );
}

function StageInspector({
  stage
}: {
  stage: PlanningRunStage;
}) {
  const [tab, setTab] = useState<"input" | "output" | "metadata" | "error">(
    stage.status === "failed" ? "error" : "output"
  );
  const tabs = [
    ["input", "Input"],
    ["output", "Output"],
    ["metadata", "Metadata"],
    ["error", "Lỗi"]
  ] as const;

  return (
    <section className="stageInspector">
      <header>
        <div>
          <span className="stageNumber">0{stage.sequence}</span>
          <div>
            <h3>{stage.stage}</h3>
            <p>{formatDate(stage.createdAt)}</p>
          </div>
        </div>
        <div className="stageMeta">
          <span className={`status status-${stage.status}`}>
            {statusLabel(stage.status)}
          </span>
          <b>{durationLabel(stage.durationMs)}</b>
        </div>
      </header>
      <div className="tabList" role="tablist" aria-label={`${stage.stage} data`}>
        {tabs.map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={tab === key ? "active" : ""}
            onClick={() => setTab(key)}
            role="tab"
            aria-selected={tab === key}
          >
            {label}
          </button>
        ))}
      </div>
      <JsonPanel value={stage[tab]} />
    </section>
  );
}

function GoldenLibrary({
  onUnauthorized
}: {
  onUnauthorized: () => void;
}) {
  const [cases, setCases] = useState<GoldenCase[]>([]);
  const [modules, setModules] = useState<string[]>([]);
  const [module, setModule] = useState("");
  const [selectedCase, setSelectedCase] = useState<GoldenCase | null>(null);
  const [execution, setExecution] = useState<GoldenCaseExecution | null>(null);
  const [runningCaseId, setRunningCaseId] = useState("");
  const [runError, setRunError] = useState("");
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let active = true;
    setLoadError("");
    listGoldenCases(module)
      .then((result) => {
        if (!active) return;
        setCases(result.items);
        setModules(result.modules);
        setSelectedCase((current) => {
          if (current && result.items.some((item) => item.id === current.id)) {
            return current;
          }
          return result.items[0] ?? null;
        });
      })
      .catch((caught) => {
        if (!active) return;
        if (caught instanceof APIError && caught.status === 401) {
          onUnauthorized();
          return;
        }
        setLoadError(
          caught instanceof Error
            ? caught.message
            : "Không tải được golden dataset."
        );
      });
    return () => {
      active = false;
    };
  }, [module, onUnauthorized]);

  async function executeCase() {
    if (!selectedCase) return;
    setRunningCaseId(selectedCase.id);
    setRunError("");
    setExecution(null);
    try {
      setExecution(await runGoldenCase(selectedCase.id));
    } catch (caught) {
      if (caught instanceof APIError && caught.status === 401) {
        onUnauthorized();
        return;
      }
      setRunError(
        caught instanceof Error ? caught.message : "Không chạy được golden case."
      );
    } finally {
      setRunningCaseId("");
    }
  }

  function chooseCase(item: GoldenCase) {
    setSelectedCase(item);
    setExecution(null);
    setRunError("");
  }

  return (
    <section className="goldenSection" id="golden">
      <header>
        <div>
          <p className="eyebrow">Ground truth library</p>
          <h2>Golden dataset</h2>
          <p>
            Bộ case Hà Nội mẫu để đối chiếu input, output và assertion của từng module.
          </p>
        </div>
        <select value={module} onChange={(event) => setModule(event.target.value)}>
          <option value="">Tất cả module</option>
          {modules.map((item) => (
            <option value={item} key={item}>
              {item}
            </option>
          ))}
        </select>
      </header>
      <div className="goldenLayout">
        <div className="goldenList">
          {loadError && <div className="runCaseError">{loadError}</div>}
          {cases.map((item) => (
            <button
              type="button"
              key={item.id}
              onClick={() => chooseCase(item)}
              className={selectedCase?.id === item.id ? "active" : ""}
            >
              <span className="goldenCaseMeta">
                <em>{item.id}</em>
                <i className={`validation validation-${item.validation.status}`}>
                  {item.validation.status}
                </i>
              </span>
              <b>{item.scenarioName}</b>
              <small>{item.module} · {item.category}</small>
            </button>
          ))}
        </div>
        {selectedCase && (
          <article className="goldenDetail">
            <div className="goldenTitle">
              <span>{selectedCase.id}</span>
              <div>
                <h3>{selectedCase.scenarioName}</h3>
                <p>{selectedCase.scenarioPurpose}</p>
              </div>
              <button
                type="button"
                className="runCaseButton"
                onClick={executeCase}
                disabled={runningCaseId === selectedCase.id}
              >
                {runningCaseId === selectedCase.id
                  ? "Đang chạy module…"
                  : "▶ Run case"}
              </button>
            </div>
            <div className="goldenCompare">
              <div>
                <b>Input</b>
                <JsonPanel value={selectedCase.input} />
              </div>
              <div>
                <b>Golden output</b>
                <JsonPanel value={selectedCase.goldenOutput} />
              </div>
            </div>
            {runError && <div className="runCaseError">{runError}</div>}
            {execution && (
              <section
                className={`executionResult execution-${execution.status}`}
              >
                <header>
                  <div>
                    <b>Actual module execution</b>
                    <span>
                      {statusLabel(execution.status)} ·{" "}
                      {durationLabel(execution.durationMs)}
                    </span>
                  </div>
                  <code>run {execution.runId.slice(0, 8)}</code>
                </header>
                {execution.adaptations.length > 0 && (
                  <div className="adaptationList">
                    <b>Input adaptations</b>
                    {execution.adaptations.map((adaptation) => (
                      <p key={adaptation}>↳ {adaptation}</p>
                    ))}
                  </div>
                )}
                {execution.error ? (
                  <div className="executionError">
                    <b>{execution.error.code}</b>
                    <p>{execution.error.message}</p>
                    {execution.error.details.length > 0 && (
                      <JsonPanel value={execution.error.details} />
                    )}
                  </div>
                ) : (
                  <>
                    <div className="executionCompare">
                      <div>
                        <b>Effective input</b>
                        <JsonPanel value={execution.effectiveInput} />
                      </div>
                      <div>
                        <b>Actual output</b>
                        <JsonPanel value={execution.actualOutput} />
                      </div>
                    </div>
                    {execution.comparison && (
                      <div className="comparisonSummary">
                        <b>
                          {execution.comparison.matchesGoldenProjection
                            ? "Khớp golden projection"
                            : `${execution.comparison.mismatchCount} điểm không khớp`}
                        </b>
                        <span>
                          {execution.comparison.matchedFieldCount} field khớp
                        </span>
                        {!execution.comparison.matchesGoldenProjection && (
                          <JsonPanel
                            value={execution.comparison.mismatches}
                          />
                        )}
                      </div>
                    )}
                  </>
                )}
              </section>
            )}
            <div className="assertionList">
              <b>Assertions</b>
              {selectedCase.assertions.map((assertion) => (
                <p key={assertion}>✓ {assertion}</p>
              ))}
            </div>
            <div
              className={`validationReport validation-${selectedCase.validation.status}`}
            >
              <b>
                Contract check: {selectedCase.validation.status} ·{" "}
                {selectedCase.validation.errorCount} lỗi ·{" "}
                {selectedCase.validation.warningCount} cảnh báo
              </b>
              {selectedCase.validation.issues.map((issue) => (
                <p key={`${issue.path}-${issue.message}`}>
                  <code>{issue.path}</code> — {issue.message}
                </p>
              ))}
            </div>
          </article>
        )}
      </div>
    </section>
  );
}

function Dashboard({
  user,
  onSignedOut
}: {
  user: AdminUser | null;
  onSignedOut: () => void;
}) {
  const [runs, setRuns] = useState<PlanningRunSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<PlanningRunDetail | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [stage, setStage] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

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
      if (caught instanceof APIError && caught.status === 401) {
        onSignedOut();
        return;
      }
      setError(caught instanceof Error ? caught.message : "Không tải được run.");
    } finally {
      setLoading(false);
    }
  }, [onSignedOut, query, selected, stage, status]);

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

  async function signOut() {
    try {
      await logout();
    } finally {
      onSignedOut();
    }
  }

  return (
    <main className="appShell">
      <aside className="sidebar">
        <div className="sidebarBrand">
          <span>VSF</span>
          <div>
            <b>Planning</b>
            <small>Control room</small>
          </div>
        </div>
        <nav>
          <a className="active" href="#runs">
            <span>⌁</span> Planning runs
          </a>
          <a href="#privacy">
            <span>◈</span> Data policy
          </a>
          <a href="#golden">
            <span>◇</span> Golden dataset
          </a>
        </nav>
        <div className="sidebarFoot">
          <div className="adminAvatar">{user?.fullName?.slice(0, 1) ?? "A"}</div>
          <div>
            <b>{user?.fullName ?? "VSF Admin"}</b>
            <small>{user?.email ?? "Authenticated session"}</small>
          </div>
          <button type="button" onClick={signOut} aria-label="Đăng xuất">
            ↗
          </button>
        </div>
      </aside>

      <section className="workspace">
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
                  {selected.stages.map((runStage) => (
                    <StageInspector key={runStage.id} stage={runStage} />
                  ))}
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

        <GoldenLibrary onUnauthorized={onSignedOut} />

        <footer id="privacy">
          <b>Privacy by design</b>
          <p>
            Console chỉ hiển thị snapshot có cấu trúc. Raw request được thay bằng
            số ký tự; query string URL, media bytes, secret và toàn bộ prompt bị loại.
          </p>
        </footer>
      </section>
    </main>
  );
}

export default function Home() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [user, setUser] = useState<AdminUser | null>(null);

  useEffect(() => {
    listRuns({})
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false));
  }, []);

  if (authenticated === null) {
    return (
      <main className="bootScreen">
        <div className="bootMark">VSF</div>
        <p>Đang xác thực Planning Control…</p>
      </main>
    );
  }
  if (!authenticated) {
    return (
      <LoginScreen
        onSignedIn={(signedInUser) => {
          setUser(signedInUser);
          setAuthenticated(true);
        }}
      />
    );
  }
  return (
    <Dashboard
      user={user}
      onSignedOut={() => {
        setUser(null);
        setAuthenticated(false);
      }}
    />
  );
}
