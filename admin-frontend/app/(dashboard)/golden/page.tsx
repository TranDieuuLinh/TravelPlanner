"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  APIError,
  GoldenCase,
  GoldenCaseExecution,
  listGoldenCases,
  runGoldenCase,
  updateGoldenCaseInput
} from "../../../lib/api";
import {
  JsonPanel,
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
      setExecution(await runGoldenCase(selectedCase.id));
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
              <div className="goldenInputCol">
                <div className="goldenInputHeader" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <b>Input</b>
                  {!editingInput ? (
                    <button type="button" onClick={() => {
                      setInputValue(JSON.stringify(selectedCase.input, null, 2));
                      setEditingInput(true);
                      setSaveError("");
                    }}>Edit</button>
                  ) : (
                    <div>
                      <button type="button" onClick={() => setEditingInput(false)} style={{ marginRight: '8px' }}>Cancel</button>
                      <button type="button" onClick={handleSaveInput}>Save</button>
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
