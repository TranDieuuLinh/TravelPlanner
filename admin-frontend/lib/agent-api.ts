import { backendFetch } from "./backend-client";

export type AdminAgentInvokeRequest = {
  threadId: string;
  message: string;
  suppliedCandidates?: unknown[];
  existingItinerary?: unknown;
  editOperation?: unknown;
};

export type AdminAgentInvokeResponse = {
  request_id: string;
  route: string;
  response: string;
  itinerary: unknown | null;
  clarification_question: string | null;
  warnings: string[];
};

/** Minimal adapter used by admin diagnostics against the new backend. */
export async function invokeAgent(
  input: AdminAgentInvokeRequest
): Promise<AdminAgentInvokeResponse> {
  return backendFetch<AdminAgentInvokeResponse>("/v1/agent/invoke", {
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
