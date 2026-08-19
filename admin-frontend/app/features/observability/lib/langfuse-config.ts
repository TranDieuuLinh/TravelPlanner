export type LangfusePage = "overview" | "traces" | "observations" | "sessions" | "playground" | "datasets" | "evaluations";

export const LANGFUSE_PAGES: Array<{ id: LangfusePage; label: string; description: string }> = [
  { id: "overview", label: "Overview", description: "Tổng quan request gần nhất" },
  { id: "traces", label: "Requests", description: "Request agent và trạng thái xử lý" },
  { id: "observations", label: "Steps", description: "Chain, LLM, tool và input/output tool" },
  { id: "sessions", label: "Threads", description: "Gom request theo thread" }
];
