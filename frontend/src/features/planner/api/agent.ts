import { apiFetch } from "@/shared/api/client";

export type AgentInvokeRequest = {
  threadId: string;
  message: string;
  suppliedCandidates?: unknown[];
  existingItinerary?: unknown;
  editOperation?: unknown;
};

export type AgentInvokeResponse = {
  request_id: string;
  route: string;
  response: string;
  itinerary: unknown | null;
  clarification_question: string | null;
  warnings: string[];
};

/** Adapter for the current modular backend contract. */
export function invokeAgent(
  input: AgentInvokeRequest
): Promise<AgentInvokeResponse> {
  return apiFetch<AgentInvokeResponse>("/v1/agent/invoke", {
    method: "POST",
    body: JSON.stringify({
      thread_id: input.threadId,
      message: input.message,
      supplied_candidates: input.suppliedCandidates ?? [],
      existing_itinerary: input.existingItinerary,
      edit_operation: input.editOperation,
    }),
  });
}
