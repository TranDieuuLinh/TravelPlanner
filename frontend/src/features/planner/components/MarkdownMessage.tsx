"use client";

import {
  useEffect,
  useRef,
  useState,
  type ComponentPropsWithoutRef,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { apiFetch } from "@/shared/api/client";
import type { TripChatSource } from "@/features/planner/api/plans";
import {
  createEntityPreviewLoader,
  entityPreviewPath,
  LEGACY_ENTITY_HREF,
  legacyEntityPreviewPath,
  parseEntityId,
  type EntityPreview,
} from "@/features/planner/lib/markdown-entity";

type EntityLinkProps = ComponentPropsWithoutRef<"a"> & {
  children?: ReactNode;
};

type PreviewState = {
  label: string;
  left: number;
  top: number;
  data: EntityPreview | null;
  loading: boolean;
  error: boolean;
};

const markdownSchema = {
  ...defaultSchema,
  protocols: {
    ...defaultSchema.protocols,
    href: [...(defaultSchema.protocols?.href ?? []), "travel-entity"],
  },
};

const entityPreviewLoader = createEntityPreviewLoader((entityId) =>
  apiFetch<EntityPreview>(entityPreviewPath(entityId)),
);

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
  if (state.error) {
    return <div className="entityHoverCard entityHoverCardLoading">Không tải được thông tin entity.</div>;
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

function MarkdownAnchor({ children, href, ...props }: EntityLinkProps) {
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

export function InteractiveEntityLink({
  children,
  entityId,
}: {
  children?: ReactNode;
  entityId: string | null;
}) {
  const label = labelFromChildren(children);
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [detail, setDetail] = useState<EntityPreview | null>(null);
  const closeTimer = useRef<number | null>(null);

  async function fetchPreview(): Promise<EntityPreview> {
    if (entityId) return entityPreviewLoader.load(entityId);
    return apiFetch<EntityPreview>(legacyEntityPreviewPath(label));
  }

  function markPreviewLoading(position: { left: number; top: number }) {
    setPreview((current) => ({
      label,
      ...position,
      data: current?.data ?? null,
      loading: true,
      error: false,
    }));
  }

  function showPreview(event: ReactMouseEvent<HTMLButtonElement>) {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
    markPreviewLoading(previewPosition(event.clientX, event.clientY));
    void fetchPreview()
      .then((data) => {
        setPreview((current) => current ? { ...current, data, loading: false, error: false } : null);
      })
      .catch(() => {
        setPreview((current) => current ? { ...current, loading: false, error: true } : null);
      });
  }

  async function openDetail(event?: ReactMouseEvent<HTMLButtonElement>) {
    if (event) {
      if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
      markPreviewLoading(previewPosition(event.clientX, event.clientY));
    }
    try {
      const data = preview?.data ?? await fetchPreview();
      setPreview((current) => current ? { ...current, data, loading: false, error: false } : current);
      setDetail(data);
    } catch {
      setPreview((current) => current ? { ...current, loading: false, error: true } : current);
    }
  }

  return (
    <>
      <button
        aria-label={`Xem thông tin về ${label}`}
        className="entityMention"
        onClick={(event) => {
          event.preventDefault();
          void openDetail(event);
        }}
        onMouseEnter={showPreview}
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
              <EntityPreviewCard state={preview} onClick={() => void openDetail()} />
            </div>,
            document.body,
          )
        : null}
      {detail ? <EntityDetailDialog data={detail} onClose={() => setDetail(null)} /> : null}
    </>
  );
}

function EntityLink({ children, href, ...props }: EntityLinkProps) {
  const entityId = parseEntityId(typeof href === "string" ? href : undefined);
  const isEntityLink = entityId !== null || href === LEGACY_ENTITY_HREF;
  if (!isEntityLink || typeof href !== "string") {
    return <MarkdownAnchor href={href} {...props}>{children}</MarkdownAnchor>;
  }
  return <InteractiveEntityLink entityId={entityId}>{children}</InteractiveEntityLink>;
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
      if (!sourceUrl || !/^https?:\/\//i.test(sourceUrl)) return match;
      return `[${number}](<${sourceUrl}>)`;
    },
  );
  return (
    <div className="markdownMessage">
      <ReactMarkdown
        components={{ a: (props) => <EntityLink {...props} /> }}
        rehypePlugins={[[rehypeSanitize, markdownSchema]]}
        remarkPlugins={[remarkGfm]}
      >
        {citationContent}
      </ReactMarkdown>
    </div>
  );
}
