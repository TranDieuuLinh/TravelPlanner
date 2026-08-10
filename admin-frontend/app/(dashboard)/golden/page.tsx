"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";
import {
  APIError,
  GoldenCase,
  GoldenCaseExecution,
  PlanningRunDetail,
  getRun,
  listGoldenCases,
  runGoldenCase,
  updateGoldenCaseInput
} from "../../../lib/api/golden";
import {
  JsonPanel,
  StageInspector,
  durationLabel,
  statusLabel
} from "../../components/shared";

export default function GoldenPage() {
  const [cases, setCases] = useState<GoldenCase[]>([]);
  const [modules, setModules] = useState<string[]>([]);
  const [module, setModule] = useState("");
  const [selectedCase, setSelectedCase] = useState<GoldenCase | null>(null);
  const [execution, setExecution] = useState<GoldenCaseExecution | null>(null);
  const [runningCaseId, setRunningCaseId] = useState("");
  const [runError, setRunError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [editingInput, setEditingInput] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [saveError, setSaveError] = useState("");
  const [showDiff, setShowDiff] = useState(true);
  const [runDetail, setRunDetail] = useState<PlanningRunDetail | null>(null);
  const [loadingTrace, setLoadingTrace] = useState(false);
  const router = useRouter();

  const handleUnauthorized = () => {
    router.push("/login");
  };

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
          handleUnauthorized();
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
  }, [module]);

  async function executeCase() {
    if (!selectedCase) return;
    setRunningCaseId(selectedCase.id);
    setRunError("");
    setExecution(null);
    try {
      const res = await runGoldenCase(selectedCase.id);
      setExecution(res);
      if (res?.runId) {
        setLoadingTrace(true);
        try {
          const detail = await getRun(res.runId);
          setRunDetail(detail);
        } catch {
          // Ignore trace load error if any
        } finally {
          setLoadingTrace(false);
        }
      }
    } catch (caught) {
      if (caught instanceof APIError && caught.status === 401) {
        handleUnauthorized();
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
    setRunDetail(null);
    setRunError("");
    setEditingInput(false);
    setSaveError("");
  }

  async function handleSaveInput() {
    if (!selectedCase) return;
    setSaveError("");
    let parsedInput: unknown;
    try {
      parsedInput = JSON.parse(inputValue);
    } catch (e) {
      setSaveError("JSON không hợp lệ.");
      return;
    }

    try {
      const updatedCase = await updateGoldenCaseInput(selectedCase.id, parsedInput);
      setCases((prev) =>
        prev.map((c) => (c.id === updatedCase.id ? updatedCase : c))
      );
      setSelectedCase(updatedCase);
      setEditingInput(false);
    } catch (caught) {
      if (caught instanceof APIError && caught.status === 401) {
        handleUnauthorized();
        return;
      }
      setSaveError(
        caught instanceof Error ? caught.message : "Không lưu được input."
      );
    }
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
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <select value={module} onChange={(event) => setModule(event.target.value)}>
            <option value="">Tất cả module</option>
            {modules.map((item) => (
              <option value={item} key={item}>
                {item}
              </option>
            ))}
          </select>
          <select
            value={selectedCase?.id || ""}
            onChange={(e) => {
              const item = cases.find(c => c.id === e.target.value);
              if (item) chooseCase(item);
            }}
          >
            <option value="" disabled>Chọn test case</option>
            {cases.map((item) => (
              <option value={item.id} key={item.id}>
                {item.id} - {item.scenarioName}
              </option>
            ))}
          </select>
        </div>
      </header>
      <div style={{ marginTop: '24px' }}>
        {loadError && <div className="runCaseError">{loadError}</div>}
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
              <div className="goldenInputCol">
                <div className="goldenInputHeader" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <b>Input</b>
                  {!editingInput ? (
                    <button type="button" onClick={() => {
                      setInputValue(JSON.stringify(selectedCase.input, null, 2));
                      setEditingInput(true);
                      setSaveError("");
                    }} style={{ background: 'transparent', border: 'none', color: 'var(--muted)', cursor: 'pointer', padding: '0', fontSize: '14px' }} title="Edit Input">
                      ✏️ Edit
                    </button>
                  ) : (
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button type="button" onClick={() => setEditingInput(false)} style={{ background: 'transparent', border: '1px solid var(--line)', color: 'var(--text)', padding: '4px 8px', borderRadius: '4px', fontSize: '12px' }}>Cancel</button>
                      <button type="button" onClick={handleSaveInput} style={{ background: 'var(--lime)', border: 'none', color: '#13200c', padding: '4px 12px', borderRadius: '4px', fontSize: '12px', fontWeight: 'bold' }}>Save</button>
                    </div>
                  )}
                </div>
                {saveError && <div className="runCaseError" style={{ marginBottom: '8px' }}>{saveError}</div>}
                {!editingInput ? (
                  <JsonPanel value={selectedCase.input} />
                ) : (
                  <textarea
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    style={{ width: '100%', height: '400px', fontFamily: 'monospace', fontSize: '13px', padding: '12px', border: '1px solid var(--border)', borderRadius: '4px', backgroundColor: 'var(--bg-panel)', color: 'var(--text)' }}
                  />
                )}
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
                  <div>
                    <code style={{ marginRight: '10px' }}>run {execution.runId.slice(0, 8)}</code>
                    <a
                      href={`/runs?query=${execution.runId}`}
                      target="_blank"
                      rel="noreferrer"
                      style={{ fontSize: '0.68rem', color: 'var(--lime)', textDecoration: 'none', border: '1px solid var(--line)', padding: '3px 8px', borderRadius: '4px' }}
                    >
                      🔗 Mở trong /runs ↗
                    </a>
                  </div>
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
                    <div className="executionCompareHeader" style={{ display: 'flex', justifyContent: 'flex-end', padding: '0 12px', marginTop: '12px' }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.7rem', color: 'var(--muted)', cursor: 'pointer' }}>
                        <input type="checkbox" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} />
                        Hiển thị Diff (Golden vs Actual)
                      </label>
                    </div>
                    {showDiff ? (
                      <div style={{ padding: '12px', borderTop: '1px solid var(--line)', marginTop: '8px' }}>
                        <b style={{ display: 'block', marginBottom: '8px', color: '#b8cbc5', fontFamily: 'var(--mono)', fontSize: '0.62rem', textTransform: 'uppercase' }}>Diff: Golden (Left) vs Actual (Right)</b>
                        <div style={{ borderRadius: '8px', overflow: 'hidden', border: '1px solid var(--line)', fontSize: '12px' }}>
                          <ReactDiffViewer
                            oldValue={JSON.stringify(selectedCase.goldenOutput, null, 2)}
                            newValue={JSON.stringify(execution.actualOutput, null, 2)}
                            splitView={true}
                            useDarkTheme={true}
                            compareMethod={DiffMethod.WORDS}
                            styles={{
                              variables: {
                                dark: {
                                  diffViewerBackground: '#0b1715',
                                  diffViewerTitleBackground: '#07100f',
                                  diffViewerColor: '#a8cabe',
                                  addedBackground: 'rgba(103, 232, 189, 0.1)',
                                  addedColor: 'var(--mint)',
                                  removedBackground: 'rgba(255, 116, 108, 0.1)',
                                  removedColor: 'var(--red)',
                                  wordAddedBackground: 'rgba(103, 232, 189, 0.3)',
                                  wordRemovedBackground: 'rgba(255, 116, 108, 0.3)',
                                  emptyLineBackground: '#0b1715',
                                  gutterBackground: '#07100f',
                                  gutterBackgroundDark: '#07100f',
                                  highlightBackground: 'rgba(184, 241, 91, 0.1)',
                                  highlightGutterBackground: 'rgba(184, 241, 91, 0.2)',
                                  codeFoldGutterBackground: '#07100f',
                                  codeFoldBackground: '#0b1715',
                                }
                              }
                            }}
                          />
                        </div>
                      </div>
                    ) : (
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
                    )}
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

                {/* Trace Log Section */}
                <div className="traceLogSection" style={{ margin: '14px', paddingTop: '14px', borderTop: '1px solid var(--line)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <b style={{ color: 'var(--mint)', fontFamily: 'var(--mono)', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      ⚡ Trace Log & Stage Inspector {runDetail ? `(${runDetail.stages.length} stage)` : ''}
                    </b>
                    {loadingTrace && <span style={{ fontSize: '0.68rem', color: 'var(--muted)' }}>Đang tải trace log...</span>}
                  </div>
                  {runDetail && runDetail.stages.length > 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {runDetail.stages.map((stg) => (
                        <StageInspector key={stg.id} stage={stg} />
                      ))}
                    </div>
                  ) : (
                    !loadingTrace && <p style={{ fontSize: '0.7rem', color: 'var(--muted)', margin: 0 }}>Không tìm thấy thông tin stage trace.</p>
                  )}
                </div>
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
