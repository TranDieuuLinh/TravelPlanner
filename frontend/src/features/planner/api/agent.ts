import { apiFetch } from "@/shared/api/client";
import {
  plannerOutputToTravelPlan,
  type ItineraryPlannerOutput,
} from "@/features/planner/lib/planner-output";
import type { TravelPlan } from "@/features/planner/api/plans";
import type { TripChatSource } from "@/features/planner/api/plans";
import type { AnswerBlock } from "@/features/planner/lib/answer-blocks";

export type AgentImageInput = {
  fileName: string;
  mimeType: string;
  dataBase64?: string | null;
  ocrText?: string | null;
};

export type AgentInvokeRequest = {
  threadId: string;
  message?: string | null;
  urls?: string[];
  images?: AgentImageInput[];
  forceRefresh?: boolean;
  existingItinerary?: unknown;
  editOperation?: unknown;
  signal?: AbortSignal;
};

export type AgentInvokeResponse = {
  requestId: string;
  route: string;
  response: string;
  itinerary: unknown | null;
  plannerOutput: ItineraryPlannerOutput | null;
  clarificationQuestion: string | null;
  warnings: string[];
  contentBlocks: AnswerBlock[];
  sources: TripChatSource[];
  suggestions: Array<{
    field: string;
    label: string;
    value: string | number;
    currency?: string;
  }>;
};

/** Adapter for the current modular backend contract. */
export function invokeAgent(
  input: AgentInvokeRequest
): Promise<AgentInvokeResponse> {
  return apiFetch<AgentInvokeResponse>("/v1/agent/invoke", {
    method: "POST",
    body: JSON.stringify({
      threadId: input.threadId,
      message: input.message,
      urls: input.urls ?? [],
      images: input.images ?? [],
      forceRefresh: input.forceRefresh ?? false,
      existingItinerary: input.existingItinerary,
      editOperation: input.editOperation,
    }),
    signal: input.signal,
  });
}

export async function fileToAgentImage(file: File): Promise<AgentImageInput> {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("Không thể đọc ảnh."));
    reader.readAsDataURL(file);
  });
  return {
    fileName: file.name,
    mimeType: file.type || "application/octet-stream",
    dataBase64: dataUrl.slice(dataUrl.indexOf(",") + 1),
  };
}

export async function invokeAgentPlan(input: AgentInvokeRequest): Promise<{
  plan: TravelPlan;
  response: AgentInvokeResponse;
}> {
  const response = await invokeAgent(input);
  const plan = plannerOutputToTravelPlan(response.plannerOutput, {
    id: `agent-${response.requestId}`,
  });
  if (!plan) {
    throw new Error(
      response.clarificationQuestion
        ?? response.response
        ?? "Planner chưa tạo được lịch trình.",
    );
  }
  return { plan, response };
}
