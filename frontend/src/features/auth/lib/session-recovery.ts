export type AuthLoadFailureAction = "retry" | "clear-session" | "throw";

export function authLoadFailureAction(status?: number): AuthLoadFailureAction {
  if (status === 0) return "retry";
  if (status === 401 || status === 403) return "clear-session";
  return "throw";
}
