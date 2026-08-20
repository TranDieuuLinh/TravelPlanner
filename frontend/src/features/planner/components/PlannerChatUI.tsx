"use client";

import {
  forwardRef,
  useState,
  type ClipboardEventHandler,
  type FormEventHandler,
  type KeyboardEventHandler,
  type PointerEventHandler,
  type PointerEvent as ReactPointerEvent,
  type Ref,
} from "react";
import { createPortal } from "react-dom";
import { PenguinMascot } from "@/components/PenguinMascot";
import { SourceProviderIcon } from "@/features/planner/lib/planner-formatters";
import { MarkdownMessage } from "@/features/planner/components/MarkdownMessage";
import { AnswerBlockRenderer } from "@/features/planner/components/AnswerBlockRenderer";
import type { TripChatSource } from "@/features/planner/api/plans";
import type { AnswerBlock } from "@/features/planner/lib/answer-blocks";
import {
  sourceProviderKind,
  type SourceProviderKind,
} from "@/features/planner/lib/source-provider";

function sourceProviderKindForUrl(url: string): SourceProviderKind {
  return sourceProviderKind(url, undefined) ?? "url";
}

function sourceProviderLabelForUrl(url: string): string {
  const provider = sourceProviderKindForUrl(url);
  if (provider === "youtube") return "YouTube";
  if (provider === "tiktok") return "TikTok";
  if (provider === "instagram") return "Instagram";
  return "Website";
}

export type PlannerChatMessage = {
  id: number | string;
  role: "assistant" | "user";
  text: string;
  sources?: TripChatSource[];
  contentBlocks?: AnswerBlock[];
  streaming?: boolean;
  suggestions?: Array<{ field: string; label: string; value: string | number; currency?: string }>;
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
        <strong id={titleId}>Trợ lý TravelPlanner</strong>
        <small>{status}</small>
      </div>
      <span
        aria-label={loading ? "Đang xử lý" : "Đang trực tuyến"}
        className={`assistantStatus ${loading ? "working" : ""}`}
      />
      <button
        aria-controls={contentId}
        aria-expanded={!collapsed}
        aria-label={collapsed ? "Mở trợ lý TravelPlanner" : "Thu gọn trợ lý TravelPlanner"}
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
  { messages, onSuggestionSelect }: { messages: PlannerChatMessage[]; onSuggestionSelect?: (value: string) => void },
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
          <div className={`chatBubble ${message.role}`}>
            {message.role === "assistant" ? (
              message.contentBlocks?.length ? (
                <AnswerBlockRenderer
                  blocks={message.contentBlocks}
                  sources={message.sources ?? []}
                />
              ) : (
                <MarkdownMessage
                  content={message.text}
                  sources={message.sources ?? []}
                  streaming={message.streaming}
                />
              )
            ) : (
              message.text
            )}
            {message.role === "assistant" && message.suggestions?.length ? (
              <div className="chatSuggestionList" role="group" aria-label="Gợi ý lựa chọn">
                {message.suggestions.map((suggestion) => (
                  <button
                    className="chatSuggestionButton"
                    key={`${suggestion.field}:${suggestion.value}`}
                    onClick={() => onSuggestionSelect?.(String(suggestion.value))}
                    type="button"
                  >
                    {suggestion.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
});

type PlannerChatComposerProps = {
  disabled?: boolean;
  onPromptChange: (value: string) => void;
  onPromptKeyDown?: KeyboardEventHandler<HTMLTextAreaElement>;
  onPromptPaste?: ClipboardEventHandler<HTMLTextAreaElement>;
  onSubmit: FormEventHandler<HTMLFormElement>;
  onRemoveUrl: (url: string) => void;
  prompt: string;
  promptPlaceholder: string;
  promptRef?: Ref<HTMLTextAreaElement>;
  queueingUrls?: boolean;
  urls: string[];
};

export function PlannerChatComposer({
  disabled = false,
  onPromptChange,
  onPromptKeyDown,
  onPromptPaste,
  onSubmit,
  onRemoveUrl,
  prompt,
  promptPlaceholder,
  promptRef,
  queueingUrls = false,
  urls,
}: PlannerChatComposerProps) {
  const busy = disabled || queueingUrls;
  const [hoveredUrl, setHoveredUrl] = useState<{
    left: number;
    top: number;
    url: string;
  } | null>(null);

  function showUrlTooltip(
    event: ReactPointerEvent<HTMLDivElement>,
    url: string
  ) {
    const bounds = event.currentTarget.getBoundingClientRect();
    setHoveredUrl({
      left: Math.min(bounds.left, window.innerWidth - 380),
      top: bounds.top - 8,
      url,
    });
  }

  return (
    <div className="plannerEntryComposer">
      <form className="chatComposer" onSubmit={onSubmit}>
        <div className="composerBox">
          {urls.length > 0 ? (
            <div aria-label="URL tham khảo đã thêm" className="urlChipList" role="list">
              {urls.map((url) => (
                <div
                  className="urlChip"
                  key={url}
                  onPointerEnter={(event) => showUrlTooltip(event, url)}
                  onPointerLeave={() => setHoveredUrl(null)}
                  role="listitem"
                >
                  <span
                    aria-label={sourceProviderLabelForUrl(url)}
                    className={`urlChipIcon urlChipIcon--${sourceProviderKindForUrl(url)}`}
                    role="img"
                  >
                    <SourceProviderIcon provider={sourceProviderKindForUrl(url)} />
                  </span>
                  <button
                    aria-label={`Xóa URL ${url}`}
                    className="urlChipRemove"
                    disabled={busy}
                    onClick={() => onRemoveUrl(url)}
                    type="button"
                  >×</button>
                </div>
              ))}
            </div>
          ) : null}
          <textarea
            aria-label="Tin nhắn lập lịch trình"
            disabled={disabled}
            onChange={(event) => onPromptChange(event.target.value)}
            onKeyDown={onPromptKeyDown}
            onPaste={onPromptPaste}
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
                    : urls.length > 0
                      ? "Gửi yêu cầu và URL"
                      : "Gửi yêu cầu"
              }
              className="sendButton"
              disabled={busy || (!prompt.trim() && urls.length === 0)}
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
      {hoveredUrl && typeof document !== "undefined"
        ? createPortal(
            <div
              className="urlChipTooltip urlChipTooltip--portal"
              role="tooltip"
              style={{ left: hoveredUrl.left, top: hoveredUrl.top }}
            >
              {hoveredUrl.url}
            </div>,
            document.body
          )
        : null}
    </div>
  );
}
