export type LangfusePage =
  | "overview"
  | "traces"
  | "observations"
  | "sessions"
  | "playground"
  | "datasets"
  | "evaluations";

export const LANGFUSE_BASE_URL =
  process.env.NEXT_PUBLIC_LANGFUSE_URL ?? "http://localhost:3005";

export const LANGFUSE_PATH_MAP: Record<LangfusePage, string> = {
  overview: "/",
  traces: "/",
  observations: "/",
  sessions: "/",
  playground: "/playground",
  datasets: "/datasets",
  evaluations: "/"
};

export function langfuseUrlFor(page: LangfusePage): string {
  return `${LANGFUSE_BASE_URL}${LANGFUSE_PATH_MAP[page]}`;
}

export const LANGFUSE_PAGES: Array<{
  id: LangfusePage;
  label: string;
  description: string;
}> = [
  {
    id: "overview",
    label: "Overview",
    description: "Tổng quan dữ liệu observability gần nhất"
  },
  {
    id: "traces",
    label: "Traces",
    description: "Truy vết từng lời gọi LLM, tool và stage"
  },
  {
    id: "observations",
    label: "Observations",
    description: "Xem span, generation và tool call"
  },
  {
    id: "sessions",
    label: "Sessions",
    description: "Gom các trace theo session người dùng"
  }
];
