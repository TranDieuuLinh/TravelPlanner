"use client";

import type { TransportOption } from "@/features/planner/api/plans";
import {
  formatDistance,
  formatDuration,
  isDevelopmentTransitFixture,
  transportModeLabel,
} from "@/features/planner/lib/planner-transport";
import {
  isPublicTransitMode,
  isWalkingMode,
} from "@/features/planner/lib/transport-options";

export function SidebarIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <rect height="18" rx="3" width="18" x="3" y="3" />
      <path d="M9 3v18" />
      {collapsed ? <path d="m13 9 3 3-3 3" /> : <path d="m16 9-3 3 3 3" />}
    </svg>
  );
}

export function HistoryMenuButton({
  className = "",
  onClick,
}: {
  className?: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-label="Mở toàn bộ lịch sử chat"
      className={`plannerHistoryMenu ${className}`.trim()}
      onClick={onClick}
      title="Lịch sử chat"
      type="button"
    >
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M4 6h16M4 12h16M4 18h16" />
      </svg>
    </button>
  );
}

export function NewChatIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M12 20H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h7" />
      <path d="m16 3 5 5-9 9-4 1 1-4z" />
    </svg>
  );
}

export function TrashIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5" />
    </svg>
  );
}

export function TransportModeIcon({ mode }: { mode: string }) {
  const normalized = mode.toLowerCase();

  if (isWalkingMode(mode)) {
    return (
      <svg viewBox="0 0 24 24">
        <circle cx="13" cy="4" r="2" />
        <path d="m10 21 2-6-3-3 2-5 4 3 3 1M12 15l4 6M9 12l-4 3" />
      </svg>
    );
  }

  if (normalized.includes("bike") || normalized.includes("motor")) {
    return (
      <svg viewBox="0 0 24 24">
        <circle cx="6" cy="17" r="3" />
        <circle cx="18" cy="17" r="3" />
        <path d="m6 17 4-7 3 7m-3-7h5l3 7M8 7h3" />
      </svg>
    );
  }

  if (isPublicTransitMode(mode)) {
    return (
      <svg viewBox="0 0 24 24">
        <rect x="5" y="3" width="14" height="16" rx="3" />
        <path d="M7 12h10M8 19v2m8-2v2" />
        <circle cx="9" cy="16" r="1" />
        <circle cx="15" cy="16" r="1" />
      </svg>
    );
  }

  if (normalized.includes("train")) {
    return (
      <svg viewBox="0 0 24 24">
        <rect x="6" y="3" width="12" height="15" rx="3" />
        <path d="M8 10h8M9 21l3-3 3 3" />
        <circle cx="9" cy="14" r="1" />
        <circle cx="15" cy="14" r="1" />
      </svg>
    );
  }

  if (normalized.includes("flight") || normalized.includes("plane")) {
    return (
      <svg viewBox="0 0 24 24">
        <path d="m3 15 18-9-7 14-3-6zM11 14l-4-3" />
      </svg>
    );
  }

  if (normalized.includes("mixed") || normalized.includes("unknown")) {
    return (
      <svg viewBox="0 0 24 24">
        <circle cx="6" cy="17" r="2" />
        <circle cx="18" cy="7" r="2" />
        <path d="M8 17c5 0 3-10 8-10M12 5l2 2-2 2" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24">
      <path d="m5 11 2-5h10l2 5" />
      <path d="M4 12a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v5H4zM6 17v2m12-2v2" />
      <circle cx="8" cy="14" r="1" />
      <circle cx="16" cy="14" r="1" />
    </svg>
  );
}

export function TransportOptionCard({
  option,
  primary = false,
  selected = false,
  saving = false,
  onSelect,
}: {
  option: TransportOption;
  primary?: boolean;
  selected?: boolean;
  saving?: boolean;
  onSelect?: () => void;
}) {
  const lines = option.details?.lines ?? [];
  const segments = option.details?.segments ?? [];
  const lineLabel = transportLineLabel(lines);
  const content = (
    <>
      <span className="transportOptionKind">
        {primary ? "Tuyến đề xuất" : "Lựa chọn khác"}
      </span>
      <div className="transportOptionHeading">
        <span className="transportOptionInlineIcon" aria-hidden="true">
          <TransportModeIcon mode={option.mode} />
        </span>
        <strong>{transportModeLabel(option.mode)}</strong>
        {isPublicTransitMode(option.mode) ? (
          <span className="transportLineBadge">
            Xe buýt{lineLabel ? ` · ${lineLabel}` : ""}
          </span>
        ) : null}
        <span className="transportDuration">
          <ClockIcon />
          {formatDuration(option.estimatedDurationMinutes)}
        </span>
      </div>
      {isPublicTransitMode(option.mode) &&
      lineLabel &&
      segments.length === 0 ? (
        <small>{lineLabel}</small>
      ) : null}
      {option.source === "opentripplanner_transit" && segments.length > 0 ? (
        <ol className="transportSegments" aria-label="Các chặng của hành trình">
          {segments.map((segment, index) => {
            const segmentLine = segment.line
              ? transportLineLabel([segment.line])
              : null;
            return (
              <li className="transportSegment" key={`${segment.mode}-${index}`}>
                <span className="transportSegmentIcon" aria-hidden="true">
                  <TransportModeIcon mode={segment.mode} />
                </span>
                <div>
                  <strong>{transportModeLabel(segment.mode)}</strong>
                  <p>
                    <span title={segment.fromPlace}>
                      {transportSegmentPlaceLabel(
                        segment.fromPlace,
                        segment.mode,
                        "from"
                      )}
                    </span>
                    <b aria-hidden="true">→</b>
                    <span title={segment.toPlace}>
                      {transportSegmentPlaceLabel(
                        segment.toPlace,
                        segment.mode,
                        "to"
                      )}
                    </span>
                  </p>
                  <small>
                    {segmentLine ? `${segmentLine} · ` : ""}
                    {formatDuration(segment.estimatedDurationMinutes)} ·{" "}
                    {formatDistance(segment.distanceMeters)}
                  </small>
                </div>
              </li>
            );
          })}
        </ol>
      ) : null}
      {!option.verified && !isDevelopmentTransitFixture(option) ? (
        <small>Tuyến ước tính</small>
      ) : null}
      {selected && saving ? (
        <small role="status">Đang lưu lựa chọn...</small>
      ) : null}
    </>
  );
  const className = [
    "transportOptionCard",
    primary ? "primary" : "alternative",
    selected ? "is-selected" : "",
  ].join(" ");
  if (onSelect) {
    return (
      <button
        aria-pressed={selected}
        className={className}
        onClick={onSelect}
        type="button"
      >
        {content}
      </button>
    );
  }
  return <article className={className}>{content}</article>;
}

export function transportLineLabel(lines: string[]): string | null {
  if (lines.length === 0) return null;
  if (lines.every((line) => /^route_\d+_\d+$/i.test(line.trim()))) {
    return "Tuyến xe buýt";
  }
  return `Tuyến ${lines.join(", ")}`;
}

export function transportSegmentPlaceLabel(
  place: string,
  mode: string,
  endpoint: "from" | "to"
): string {
  if (!/^stop[_-]/i.test(place.trim())) return place;
  const isBus = mode.toLowerCase().includes("bus");
  if (isBus) {
    return endpoint === "from" ? "Trạm lên xe buýt" : "Trạm xuống xe buýt";
  }
  return endpoint === "to" ? "Trạm lên xe buýt" : "Trạm xuống xe buýt";
}

export function CloseIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

export function ClockIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

export function MapPinIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 21s7-5.4 7-12a7 7 0 0 0-14 0c0 6.6 7 12 7 12Z" />
      <circle cx="12" cy="9" r="2.5" />
    </svg>
  );
}

export function ChevronDownIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m7 10 5 5 5-5" />
    </svg>
  );
}
