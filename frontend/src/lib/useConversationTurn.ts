"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  TERMINAL_TURN_STATUSES,
  TripChatTurn,
  TurnStatus,
  amendTripChat,
  cancelTripChatTurn,
  confirmTripChatTurn,
  createTripChatTurn,
  executeTripChatTurn,
  getTripChatTurn,
  isSupervisorEnabled,
  type TripChat,
} from "@/lib/plans";

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 180_000;

type SubmitTurnOptions = {
  chatId: string;
  content: string;
  expectedRevision: number;
  clientTurnId?: string;
  attachmentNames?: string[];
};

export type SubmitTurnResult = {
  turn: TripChatTurn;
  outcome: "completed" | "awaiting_confirmation" | "failed" | "cancelled";
};

type SubmitTurnState = {
  status: TurnStatus | "idle";
  turn: TripChatTurn | null;
  error: string | null;
};

const INITIAL_STATE: SubmitTurnState = {
  status: "idle",
  turn: null,
  error: null,
};

/**
 * Drives the conversational-planner supervisor (turn ⇒ execute ⇒ poll).
 *
 * The hook owns the polling loop and exposes a single `submitTurn` action.
 * When the supervisor decides the change is broad, it returns
 * `awaiting_confirmation`; the caller can then call `confirm` or `cancel`.
 *
 * The flow is disabled by the `SUPERVISOR_ENABLED` import in `@/lib/plans`.
 * Flipping that constant to ``false`` short-circuits every call, so a
 * frontend operator can roll back to the legacy ``amendTripChat`` request
 * without touching the rest of the app.
 */
export function useConversationTurn(
  onTerminal?: (result: SubmitTurnResult) => void,
) {
  const [state, setState] = useState<SubmitTurnState>(INITIAL_STATE);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const deadlineRef = useRef<number | null>(null);
  const completedRef = useRef(false);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    deadlineRef.current = null;
  }, []);

  const finish = useCallback(
    (turn: TripChatTurn) => {
      if (completedRef.current) return;
      completedRef.current = true;
      stopPolling();
      setState({ status: turn.status, turn, error: null });
      const outcome: SubmitTurnResult["outcome"] =
        turn.status === "awaiting_confirmation"
          ? "awaiting_confirmation"
          : turn.status === "failed"
            ? "failed"
            : turn.status === "cancelled"
              ? "cancelled"
              : "completed";
      onTerminal?.({ turn, outcome });
    },
    [onTerminal, stopPolling],
  );

  const poll = useCallback(
    async (chatId: string, turnId: string) => {
      try {
        const turn = await getTripChatTurn({ chatId, turnId });
        setState({ status: turn.status, turn, error: null });
        if (TERMINAL_TURN_STATUSES.has(turn.status)) {
          finish(turn);
        }
      } catch (error) {
        stopPolling();
        setState((prev) => ({
          status: prev.status,
          turn: prev.turn,
          error: error instanceof Error ? error.message : String(error),
        }));
      }
    },
    [finish, stopPolling],
  );

  const startPolling = useCallback(
    (chatId: string, turnId: string) => {
      stopPolling();
      completedRef.current = false;
      deadlineRef.current = Date.now() + POLL_TIMEOUT_MS;
      pollRef.current = setInterval(() => {
        if (
          deadlineRef.current !== null &&
          Date.now() > deadlineRef.current
        ) {
          stopPolling();
          setState((prev) => ({
            status: "failed",
            turn: prev.turn,
            error:
              "Lượt xử lý mất quá nhiều thời gian. Hãy tải lại chat trước khi thử lại.",
          }));
          return;
        }
        void poll(chatId, turnId);
      }, POLL_INTERVAL_MS);
    },
    [poll, stopPolling],
  );

  useEffect(() => stopPolling, [stopPolling]);

  const submitTurn = useCallback(
    async (input: SubmitTurnOptions): Promise<SubmitTurnResult> => {
      if (!isSupervisorEnabled()) {
        // Kill-switch flipped by operator: fall back to the legacy amend
        // endpoint. Backend still routes through the same service layer so
        // data shape is consistent; UI just doesn't get the supervisor
        // confirmation step.
        const chat = await amendTripChat({
          chatId: input.chatId,
          content: input.content,
          expectedRevision: input.expectedRevision,
        });
        const synthetic = synthTurnFromChat(chat, input);
        finish(synthetic);
        return { turn: synthetic, outcome: "completed" };
      }
      completedRef.current = false;
      setState({ status: "queued", turn: null, error: null });
      const created = await createTripChatTurn({
        chatId: input.chatId,
        content: input.content,
        expectedRevision: input.expectedRevision,
        clientTurnId: input.clientTurnId,
        attachmentNames: input.attachmentNames,
      });
      setState({ status: created.status, turn: created, error: null });
      if (TERMINAL_TURN_STATUSES.has(created.status)) {
        finish(created);
        return { turn: created, outcome: resultOutcome(created.status) };
      }
      const executed = await executeTripChatTurn({
        chatId: input.chatId,
        turnId: created.id,
      });
      startPolling(input.chatId, created.id);
      // Optimistically return whatever the first execute call produced.
      if (TERMINAL_TURN_STATUSES.has(executed.status)) {
        finish(executed);
        return { turn: executed, outcome: resultOutcome(executed.status) };
      }
      setState({ status: executed.status, turn: executed, error: null });
      return { turn: executed, outcome: "awaiting_confirmation" };
    },
    [finish, startPolling],
  );

  const resumeTurn = useCallback(
    async (turn: TripChatTurn) => {
      completedRef.current = false;
      setState({ status: turn.status, turn, error: null });
      if (TERMINAL_TURN_STATUSES.has(turn.status)) {
        finish(turn);
        return turn;
      }
      if (turn.status === "queued") {
        const executed = await executeTripChatTurn({
          chatId: turn.chatId,
          turnId: turn.id,
        });
        setState({ status: executed.status, turn: executed, error: null });
        if (TERMINAL_TURN_STATUSES.has(executed.status)) {
          finish(executed);
          return executed;
        }
      }
      startPolling(turn.chatId, turn.id);
      return turn;
    },
    [finish, startPolling],
  );

  const confirm = useCallback(
    async (input: { chatId: string; turnId: string }) => {
      const turn = await confirmTripChatTurn(input);
      startPolling(input.chatId, input.turnId);
      setState({ status: turn.status, turn, error: null });
      if (TERMINAL_TURN_STATUSES.has(turn.status)) {
        finish(turn);
      }
      return turn;
    },
    [finish, startPolling],
  );

  const cancel = useCallback(
    async (input: { chatId: string; turnId: string }) => {
      const turn = await cancelTripChatTurn(input);
      stopPolling();
      setState({ status: turn.status, turn, error: null });
      return turn;
    },
    [stopPolling],
  );

  const reset = useCallback(() => {
    stopPolling();
    completedRef.current = false;
    setState(INITIAL_STATE);
  }, [stopPolling]);

  return {
    ...state,
    submitTurn,
    resumeTurn,
    confirm,
    cancel,
    reset,
  };
}

function resultOutcome(
  status: TurnStatus,
): SubmitTurnResult["outcome"] {
  if (status === "awaiting_confirmation") return "awaiting_confirmation";
  if (status === "failed") return "failed";
  if (status === "cancelled") return "cancelled";
  return "completed";
}

function synthTurnFromChat(
  chat: TripChat,
  input: SubmitTurnOptions,
): TripChatTurn {
  const now = chat.updatedAt;
  return {
    id: `legacy-${chat.id}-${chat.revision}`,
    chatId: chat.id,
    clientTurnId: input.clientTurnId ?? `legacy-${chat.revision}`,
    status: "completed",
    content: input.content,
    attachmentNames: input.attachmentNames ?? [],
    baseRevision: input.expectedRevision,
    intent: null,
    confidence: null,
    requiresConfirmation: false,
    proposedOperations: [],
    assistantBlocks: [
      {
        type: "planDiff",
        beforeRevision: input.expectedRevision,
        afterRevision: chat.revision,
        affectedDays: [],
        undoAvailable: chat.revision > 1,
      },
    ],
    resultSummary: { planRevision: chat.revision },
    errorCode: null,
    errorMessage: null,
    createdAt: now,
    updatedAt: now,
    planRevision: chat.revision,
  };
}
