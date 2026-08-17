"use client";

import type { ReactNode } from "react";
import type { TripChatSource } from "@/features/planner/api/plans";
import { InteractiveEntityLink } from "@/features/planner/components/MarkdownMessage";
import {
  citationSources,
  highlightSegments,
  inlineSpanText,
  type AnswerBlock,
} from "@/features/planner/lib/answer-blocks";

type BlockRecord = AnswerBlock & Record<string, unknown>;

function record(value: unknown): BlockRecord | null {
  return value && typeof value === "object" ? value as BlockRecord : null;
}

function InlineText({
  text,
  spans,
  highlights = [],
}: {
  text: string;
  spans?: unknown;
  highlights?: unknown;
}) {
  const spanText = inlineSpanText(spans);
  if (!spanText || spanText !== text || !Array.isArray(spans)) {
    return (
      <>
        {highlightSegments(text, highlights).map((segment, index) => (
          segment.highlighted ? (
            <mark className="answerHighlight" key={`${segment.text}-${index}`}>{segment.text}</mark>
          ) : (
            <span key={`${segment.text}-${index}`}>{segment.text}</span>
          )
        ))}
      </>
    );
  }
  return (
    <>
      {spans.flatMap((span: unknown, index: number) => {
        const item = record(span);
        if (!item || typeof item.text !== "string") return [];
        if (item.type === "entity" && typeof item.entityId === "string") {
          return [
            <InteractiveEntityLink entityId={item.entityId} key={`${item.entityId}-${index}`}>
              {item.text}
            </InteractiveEntityLink>,
          ];
        }
        return [<span key={`${item.text}-${index}`}>{item.text}</span>];
      })}
    </>
  );
}

function Citations({ sourceIds, sources }: { sourceIds: unknown; sources: TripChatSource[] }) {
  return (
    <span className="answerCitations" aria-label="Nguồn tham khảo">
      {citationSources(sourceIds, sources).map((source) => {
        const number = sources.findIndex((item) => item.sourceId === source.sourceId) + 1;
        return (
          <a
            className="messageCitation"
            href={source.url}
            key={source.sourceId}
            rel="noreferrer"
            target="_blank"
          >
            [{number}]
          </a>
        );
      })}
    </span>
  );
}

function BlockTitle({ title }: { title: unknown }) {
  return typeof title === "string" && title.trim() ? <h3>{title}</h3> : null;
}

function renderBlock(block: BlockRecord, sources: TripChatSource[]): ReactNode {
  const sourceIds = block.sourceIds;
  switch (block.type) {
    case "paragraph":
      return <p><InlineText text={String(block.text ?? "")} spans={block.inlineSpans} /><Citations sourceIds={sourceIds} sources={sources} /></p>;
    case "factList":
      return (
        <section className="answerFactList">
          <BlockTitle title={block.title} />
          <ul>
            {Array.isArray(block.items) ? block.items.map((rawItem, index) => {
              const item = record(rawItem);
              if (!item) return null;
              return (
                <li key={`${String(item.label)}-${index}`}>
                  <strong>{String(item.label ?? "Thông tin")}:</strong>{" "}
                  <InlineText text={String(item.text ?? "")} spans={item.inlineSpans} highlights={item.highlights} />
                  <Citations sourceIds={item.sourceIds} sources={sources} />
                </li>
              );
            }) : null}
          </ul>
        </section>
      );
    case "verse": {
      const lines = Array.isArray(block.lines) ? block.lines.map(String) : [];
      const text = lines.join("\n");
      return (
        <section className="answerVerse">
          <BlockTitle title={block.title} />
          {typeof block.author === "string" && block.author ? <small>{block.author}</small> : null}
          <div className="answerVerseLines"><InlineText text={text} spans={block.inlineSpans} /></div>
          <Citations sourceIds={sourceIds} sources={sources} />
        </section>
      );
    }
    case "quote":
      return <blockquote><InlineText text={String(block.text ?? "")} spans={block.inlineSpans} />{block.attribution ? <cite>— {String(block.attribution)}</cite> : null}<Citations sourceIds={sourceIds} sources={sources} /></blockquote>;
    case "recommendations":
      return <section className="answerRecommendations"><BlockTitle title={block.title} /><ul>{Array.isArray(block.items) ? block.items.map((rawItem, index) => { const item = record(rawItem); const text = `${String(item?.name ?? "Gợi ý")}: ${String(item?.reason ?? "")}`; return item ? <li key={`${String(item.name)}-${index}`}><InlineText text={text} spans={item.inlineSpans} /><Citations sourceIds={item.sourceIds} sources={sources} /></li> : null; }) : null}</ul></section>;
    case "steps":
      return <section className="answerSteps"><BlockTitle title={block.title} /><ol>{Array.isArray(block.items) ? block.items.map((rawItem, index) => { const item = record(rawItem); return item ? <li key={index}><InlineText text={String(item.text ?? "")} spans={item.inlineSpans} /><Citations sourceIds={item.sourceIds} sources={sources} /></li> : null; }) : null}</ol></section>;
    case "comparison":
      return <section className="answerComparison"><BlockTitle title={block.title} /><div className="answerComparisonGrid">{Array.isArray(block.options) ? block.options.map((rawOption, index) => { const option = record(rawOption); if (!option) return null; const pros = Array.isArray(option.pros) ? option.pros.map(String).join(", ") : "—"; const cons = Array.isArray(option.cons) ? option.cons.map(String).join(", ") : "—"; const text = `${String(option.name ?? "Lựa chọn")}: Ưu: ${pros}; Lưu ý: ${cons}`; return <article key={`${String(option.name)}-${index}`}><InlineText text={text} spans={option.inlineSpans} /><Citations sourceIds={option.sourceIds} sources={sources} /></article>; }) : null}</div></section>;
    case "notice":
      return <aside className={`answerNotice ${String(block.severity ?? "info")}`}><InlineText text={String(block.text ?? "")} spans={block.inlineSpans} /><Citations sourceIds={sourceIds} sources={sources} /></aside>;
    default:
      return null;
  }
}

export function AnswerBlockRenderer({
  blocks,
  sources = [],
}: {
  blocks: AnswerBlock[];
  sources?: TripChatSource[];
}) {
  return <div className="answerBlockRenderer">{blocks.map((rawBlock, index) => { const block = record(rawBlock); return block ? <div className="answerBlock" key={`${block.type}-${index}`}>{renderBlock(block, sources)}</div> : null; })}</div>;
}
