"use client";

import { useEffect, useRef, useState, type ComponentPropsWithoutRef, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { apiFetch } from "@/shared/api/client";
import type { TripChatSource } from "@/features/planner/api/plans";

type EntityPreview = {
  id: string;
  name: string;
  entityType: string;
  description?: string | null;
  imageUrl?: string | null;
  details: Record<string, string>;
};

type EntityLinkProps = ComponentPropsWithoutRef<"a"> & {
  children?: ReactNode;
};

type PreviewState = {
  label: string;
  left: number;
  top: number;
  data: EntityPreview | null;
  loading: boolean;
};

const markdownSchema = {
  ...defaultSchema,
  protocols: {
    ...defaultSchema.protocols,
    href: [...(defaultSchema.protocols?.href ?? []), "travel-entity"],
  },
};

function labelFromChildren(children: ReactNode): string {
  return String(children ?? "").replace(/\s+/g, " ").trim();
}

function previewPosition(clientX: number, clientY: number) {
  const width = 320;
  const height = 260;
  return {
    left: Math.max(8, Math.min(clientX + 16, window.innerWidth - width - 8)),
    top: clientY + height + 12 > window.innerHeight
      ? Math.max(8, clientY - height - 12)
      : clientY + 14,
  };
}

function EntityPreviewCard({
  state,
  onClick,
}: {
  state: PreviewState;
  onClick: () => void;
}) {
  if (state.loading) {
    return <div className="entityHoverCard entityHoverCardLoading">Đang tải thông tin…</div>;
  }
  if (!state.data) {
    return <div className="entityHoverCard">Chưa có thông tin chi tiết cho {state.label}.</div>;
  }
  const { data } = state;
  return (
    <button className="entityHoverCard" onClick={onClick} type="button">
      {data.imageUrl ? (
        <img alt={data.name} className="entityHoverImage" src={data.imageUrl} />
      ) : null}
      <span className="entityHoverBody">
        <strong>{data.name}</strong>
        <small>{data.description || "Xem thông tin chi tiết"}</small>
      </span>
      <span className="entityHoverHint">Nhấn để xem thêm</span>
    </button>
  );
}

function EntityDetailDialog({
  data,
  onClose,
}: {
  data: EntityPreview;
  onClose: () => void;
}) {
  return createPortal(
    <div className="entityDialogBackdrop" onClick={onClose} role="presentation">
      <section
        aria-label={`Thông tin về ${data.name}`}
        className="entityDialog"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <button aria-label="Đóng thông tin" className="entityDialogClose" onClick={onClose} type="button">
          ×
        </button>
        {data.imageUrl ? <img alt={data.name} className="entityDialogImage" src={data.imageUrl} /> : null}
        <div className="entityDialogContent">
          <small>{data.entityType}</small>
          <h3>{data.name}</h3>
          {data.description ? <p>{data.description}</p> : null}
          <dl>
            {Object.entries(data.details)
              .filter(([key]) => !["description", "story", "image"].includes(key))
              .slice(0, 6)
              .map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
          </dl>
        </div>
      </section>
    </div>,
    document.body,
  );
}

function EntityLink({ children, href, ...props }: EntityLinkProps) {
  const isEntityLink = href === "travel-entity://entity";
  const label = labelFromChildren(children);
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [detail, setDetail] = useState<EntityPreview | null>(null);
  const closeTimer = useRef<number | null>(null);

  if (!isEntityLink) {
    const isExternalSource = typeof href === "string" && /^https?:\/\//i.test(href);
    return (
      <a
        {...props}
        className={`${props.className ?? ""}${isExternalSource ? " citationSource" : ""}`.trim()}
        href={href}
        rel="noreferrer"
        target="_blank"
      >
        {children}
      </a>
    );
  }

  async function loadPreview(event: ReactMouseEvent<HTMLButtonElement>) {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
    const position = previewPosition(event.clientX, event.clientY);
    setPreview({ label, ...position, data: null, loading: true });
    try {
      const data = await apiFetch<EntityPreview>(
        `/v1/knowledge-graph/entity-preview?name=${encodeURIComponent(label)}`,
      );
      setPreview((current) => current ? { ...current, data, loading: false } : null);
    } catch {
      setPreview((current) => current ? { ...current, data: null, loading: false } : null);
    }
  }

  return (
    <>
      <button
        aria-label={`Xem thông tin về ${label}`}
        className="entityMention"
        onClick={(event) => {
          event.preventDefault();
          if (preview?.data) setDetail(preview.data);
        }}
        onMouseEnter={(event) => void loadPreview(event)}
        onMouseLeave={() => {
          closeTimer.current = window.setTimeout(() => setPreview(null), 180);
        }}
        type="button"
      >
        {children}
      </button>
      {preview && typeof document !== "undefined"
        ? createPortal(
            <div
              className="entityHoverPortal"
              onMouseEnter={() => {
                if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
              }}
              onMouseLeave={() => setPreview(null)}
              style={{ left: preview.left, top: preview.top }}
            >
              <EntityPreviewCard state={preview} onClick={() => preview.data && setDetail(preview.data)} />
            </div>,
            document.body,
          )
        : null}
      {detail ? <EntityDetailDialog data={detail} onClose={() => setDetail(null)} /> : null}
    </>
  );
}

export function MarkdownMessage({
  content,
  sources = [],
  streaming = false,
}: {
  content: string;
  sources?: TripChatSource[];
  streaming?: boolean;
}) {
  const [visibleContent, setVisibleContent] = useState(streaming ? "" : content);

  useEffect(() => {
    if (!streaming) {
      setVisibleContent(content);
      return;
    }
    setVisibleContent("");
    let cursor = 0;
    const timer = window.setInterval(() => {
      cursor = Math.min(content.length, cursor + 2);
      setVisibleContent(content.slice(0, cursor));
      if (cursor >= content.length) window.clearInterval(timer);
    }, 16);
    return () => window.clearInterval(timer);
  }, [content, streaming]);

  const citationContent = visibleContent.replace(
    /\[(\d+)\](?!\()/g,
    (match, number: string) => {
      const source = sources[Number(number) - 1];
      const sourceUrl = source?.url?.trim();
      if (!sourceUrl || !/^https?:\/\//i.test(sourceUrl)) {
        return match;
      }
      // Angle brackets keep URLs containing query strings or parentheses
      // intact in Markdown's link destination parser.
      return `[${number}](<${sourceUrl}>)`;
    },
  );
  return (
    <div className="markdownMessage">
      <ReactMarkdown
        components={{
          a: (props) => <EntityLink {...props} />,
        }}
        rehypePlugins={[[rehypeSanitize, markdownSchema]]}
        remarkPlugins={[remarkGfm]}
      >
        {citationContent}
      </ReactMarkdown>
    </div>
  );
}
