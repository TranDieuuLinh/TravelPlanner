"use client";

import { useState } from "react";
import type { PlanningRunStage } from "../../lib/api/planning-runs";

export const STAGES = ["explorer", "planner", "finder", "checker", "workflow"];
export const STATUSES = ["running", "completed", "blocked", "failed", "passed", "draft"];

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(value));
}

export function durationLabel(milliseconds: number | null): string {
  if (milliseconds === null) return "—";
  if (milliseconds < 1_000) return `${milliseconds} ms`;
  return `${(milliseconds / 1_000).toFixed(milliseconds < 10_000 ? 1 : 0)} s`;
}

export function statusLabel(status: string): string {
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

export function JsonPanel({ value }: { value: unknown }) {
  return (
    <pre className="jsonPanel">
      <code>{JSON.stringify(value, null, 2)}</code>
    </pre>
  );
}

export function StageInspector({
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
            onClick={() => setTab(key as any)}
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
