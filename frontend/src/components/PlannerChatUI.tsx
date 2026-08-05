"use client";

import {
  forwardRef,
  type ClipboardEventHandler,
  type FormEventHandler,
  type KeyboardEventHandler,
  type PointerEventHandler,
  type Ref,
} from "react";
import { PenguinMascot } from "@/components/PenguinMascot";

export type PlannerChatMessage = {
  id: number | string;
  role: "assistant" | "user";
  text: string;
};

type PlannerChatHeaderProps = {
  collapsed?: boolean;
  contentId: string;
  loading?: boolean;
  onToggle: () => void;
  status: string;
  titleId?: string;
  moveHandleProps?: {
    onKeyDown?: KeyboardEventHandler<HTMLButtonElement>;
    onPointerCancel?: PointerEventHandler<HTMLButtonElement>;
    onPointerDown?: PointerEventHandler<HTMLButtonElement>;
    onPointerMove?: PointerEventHandler<HTMLButtonElement>;
    onPointerUp?: PointerEventHandler<HTMLButtonElement>;
  };
};

export function PlannerChatHeader({
  collapsed = false,
  contentId,
  loading = false,
  moveHandleProps,
  onToggle,
  status,
  titleId,
}: PlannerChatHeaderProps) {
  return (
    <div className="panelHeading">
      <button
        aria-label="Di chuyển cửa sổ chat; dùng phím mũi tên hoặc kéo"
        className="plannerChatMoveHandle"
        title="Kéo để di chuyển chat"
        type="button"
        {...moveHandleProps}
      >
        <svg aria-hidden="true" viewBox="0 0 18 18">
          <circle cx="5" cy="5" r="1.2" />
          <circle cx="13" cy="5" r="1.2" />
          <circle cx="5" cy="13" r="1.2" />
          <circle cx="13" cy="13" r="1.2" />
        </svg>
      </button>
      <div className="plannerChatTitle">
        <strong id={titleId}>Trợ lý VSF</strong>
        <small>{status}</small>
      </div>
      <span
        aria-label={loading ? "Đang xử lý" : "Đang trực tuyến"}
        className={`assistantStatus ${loading ? "working" : ""}`}
      />
      <button
        aria-controls={contentId}
        aria-expanded={!collapsed}
        aria-label={collapsed ? "Mở trợ lý VSF" : "Thu gọn trợ lý VSF"}
        className="plannerChatToggle"
        {...(collapsed ? moveHandleProps : {})}
        onClick={onToggle}
        title={collapsed ? "Mở trợ lý" : "Thu gọn trợ lý"}
        type="button"
      >
        {collapsed ? (
          <>
            <span className="chatLauncherArtwork">
              <PenguinMascot
                className="chatTogglePenguin"
                size={84}
                variant="curious"
              />
              <svg
                aria-hidden="true"
                className="speechBubbleIcon"
                viewBox="0 0 24 24"
              >
                <path d="M5.25 4.75h13.5A2.25 2.25 0 0 1 21 7v8.5a2.25 2.25 0 0 1-2.25 2.25H11l-4.75 3v-3h-1A2.25 2.25 0 0 1 3 15.5V7a2.25 2.25 0 0 1 2.25-2.25Z" />
                <circle cx="8" cy="11.25" r="1" />
                <circle cx="12" cy="11.25" r="1" />
                <circle cx="16" cy="11.25" r="1" />
              </svg>
            </span>
            <span className="plannerChatLauncherLabel">Hỏi Planner</span>
          </>
        ) : (
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="m7 7 10 10M17 7 7 17" />
          </svg>
        )}
      </button>
    </div>
  );
}

export const PlannerChatMessages = forwardRef(function PlannerChatMessages(
  { messages }: { messages: PlannerChatMessage[] },
  ref: Ref<HTMLDivElement>
) {
  return (
    <div className="chatMessages" aria-live="polite" ref={ref}>
      {messages.map((message) => (
        <div className={`chatMessageRow ${message.role}`} key={message.id}>
          {message.role === "assistant" ? (
            <span className="chatMessageAvatar">
              <PenguinMascot size={44} variant="curious" />
            </span>
          ) : null}
          <div className={`chatBubble ${message.role}`}>{message.text}</div>
        </div>
      ))}
    </div>
  );
});

type PlannerChatComposerProps = {
  disabled?: boolean;
  onPromptChange: (value: string) => void;
  onPromptKeyDown?: KeyboardEventHandler<HTMLTextAreaElement>;
  onSubmit: FormEventHandler<HTMLFormElement>;
  onUrlChange: (value: string) => void;
  onUrlPaste?: ClipboardEventHandler<HTMLTextAreaElement>;
  prompt: string;
  promptPlaceholder: string;
  promptRef?: Ref<HTMLTextAreaElement>;
  queueingUrls?: boolean;
  urlError?: string;
  urlInput: string;
  urlRef?: Ref<HTMLTextAreaElement>;
};

export function PlannerChatComposer({
  disabled = false,
  onPromptChange,
  onPromptKeyDown,
  onSubmit,
  onUrlChange,
  onUrlPaste,
  prompt,
  promptPlaceholder,
  promptRef,
  queueingUrls = false,
  urlError = "",
  urlInput,
  urlRef,
}: PlannerChatComposerProps) {
  const busy = disabled || queueingUrls;
  return (
    <div className="plannerEntryComposer">
      <div
        aria-label="Nhập URL tham khảo"
        className="urlImportDock"
        role="group"
      >
        <div className={`urlImportControl ${urlError ? "has-error" : ""}`}>
          <span className="urlImportControlIcon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1" />
              <path d="M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1.1-1.1" />
            </svg>
          </span>
          <textarea
            aria-describedby={urlError ? "url-import-error" : undefined}
            aria-invalid={Boolean(urlError)}
            aria-label="Dán các URL nguồn, mỗi URL một dòng"
            disabled={busy}
            inputMode="url"
            onChange={(event) => onUrlChange(event.target.value)}
            onPaste={onUrlPaste}
            placeholder="Dán link TikTok, YouTube, Instagram,…"
            ref={urlRef}
            rows={Math.min(4, Math.max(1, urlInput.split("\n").length))}
            value={urlInput}
          />
        </div>
        {urlError ? (
          <small className="urlImportError" id="url-import-error" role="alert">
            {urlError}
          </small>
        ) : null}
      </div>
      <form className="chatComposer" onSubmit={onSubmit}>
        <div className="composerBox">
          <textarea
            aria-label="Tin nhắn lập lịch trình"
            disabled={disabled}
            onChange={(event) => onPromptChange(event.target.value)}
            onKeyDown={onPromptKeyDown}
            placeholder={promptPlaceholder}
            ref={promptRef}
            rows={2}
            value={prompt}
          />
          <div className="composerToolbar">
            <button
              aria-label={
                disabled
                  ? "Đang xử lý yêu cầu"
                  : queueingUrls
                    ? "Đang thêm URL vào hàng chờ"
                    : urlInput.trim()
                      ? "Gửi yêu cầu và URL"
                      : "Gửi yêu cầu"
              }
              className="sendButton"
              disabled={busy || (!prompt.trim() && !urlInput.trim())}
              type="submit"
            >
              <svg aria-hidden="true" viewBox="0 0 24 24">
                <path d="M12 20V5" />
                <path d="m5.5 11.5 6.5-6.5 6.5 6.5" />
              </svg>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
