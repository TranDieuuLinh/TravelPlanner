import { useState } from "react";

import type {
  SubplaceGroup,
  SubplaceSummary,
} from "@/features/planner/api/place-search";
import { formatPlannerMoney } from "@/features/planner/lib/planner-budget";

const PREVIEW_LIMIT = 3;
const NO_IMAGE_SRC = "/images/penguin-no-image.png";

export function subplaceMapKey(placeId: string): string {
  return `subplace:${placeId}`;
}

function PinIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" />
      <circle cx="12" cy="10" r="2.5" />
    </svg>
  );
}

function formatDuration(minutes?: number | null) {
  if (!minutes) return null;
  if (minutes < 60) return `${minutes} phút`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours} giờ ${remainder} phút` : `${hours} giờ`;
}

export function PlannerSubplacePreview({
  group,
  parentName,
  onOpen,
}: {
  group: SubplaceGroup;
  parentName: string;
  onOpen: () => void;
}) {
  if (group.items.length === 0) return null;
  const previewItems = group.items.slice(0, PREVIEW_LIMIT);
  const remainingCount = Math.max(0, group.totalCount - previewItems.length);

  return (
    <section
      aria-label={`Các điểm bên trong ${parentName}`}
      className="itinerarySubplacesPreview"
    >
      <button className="itinerarySubplacesHeading" onClick={onOpen} type="button">
        <span>
          <PinIcon />
          <strong>{group.totalCount} điểm bên trong</strong>
        </span>
        <small>Xem tất cả</small>
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path d="m9 5 7 7-7 7" />
        </svg>
      </button>
      <div className="itinerarySubplacesCompactList">
        {previewItems.map((subplace) => (
          <button key={subplace.placeId} onClick={onOpen} type="button">
            <span aria-hidden="true" />
            <strong>{subplace.name}</strong>
          </button>
        ))}
        {remainingCount > 0 ? (
          <button className="is-more" onClick={onOpen} type="button">
            <span aria-hidden="true" />
            <strong>+{remainingCount} điểm khác</strong>
          </button>
        ) : null}
      </div>
    </section>
  );
}

function ActivityIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="6" cy="6" r="2.5" />
      <path d="M6 1v1M6 10v1M1 6h1M10 6h1M2.5 2.5l.7.7M8.8 8.8l.7.7M9.5 2.5l-.7.7M3.2 8.8l-.7.7" />
      <path d="m2 21 6-9 4 5 2-3 8 7" />
      <path d="M13 5c1-1 2-1 3 0 1-1 2-1 3 0M16 9c1-1 2-1 3 0 1-1 2-1 3 0" />
    </svg>
  );
}

function NoteIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M6 3h9l3 3v15H6Z" />
      <path d="M14 3v4h4M9 12h6M9 16h5" />
    </svg>
  );
}

function SubplaceCard({
  index,
  parentName,
  selected,
  subplace,
  expanded,
  onToggleDetails,
  onSelect,
}: {
  index: number;
  parentName: string;
  selected: boolean;
  subplace: SubplaceSummary;
  expanded: boolean;
  onToggleDetails: () => void;
  onSelect: () => void;
}) {
  const duration = formatDuration(subplace.durationMinutes);
  const hasCoordinates =
    typeof subplace.latitude === "number" &&
    typeof subplace.longitude === "number";
  const hasGeminiNote = Boolean(
    subplace.note &&
      subplace.noteSource === "gemini" &&
      subplace.noteActivityItemIds?.length
  );

  return (
    <article
      aria-label={`Hiển thị ${subplace.name}, bên trong ${parentName}, trên bản đồ`}
      className={`itinerarySubplaceCard itineraryPlaceCard itineraryPlaceCard--withImage ${
        selected ? "is-map-place-selected" : ""
      }`}
      onClick={hasCoordinates ? onSelect : undefined}
    >
      <h3 aria-hidden="true" className="itineraryPlaceOrder">
        {index + 1}
      </h3>
      <div className="itineraryPlaceMedia">
        <div
          className={`itineraryPlaceImage ${
            subplace.imageUrl ? "" : "itineraryPlaceImage--fallback"
          }`}
        >
          <img
            alt={subplace.imageUrl ? `Ảnh ${subplace.name}` : `Chưa có ảnh cho ${subplace.name}`}
            draggable={false}
            loading={index < 3 ? "eager" : "lazy"}
            onError={(event) => {
              if (event.currentTarget.src.endsWith(NO_IMAGE_SRC)) return;
              event.currentTarget.src = NO_IMAGE_SRC;
              event.currentTarget.alt = `Chưa có ảnh cho ${subplace.name}`;
              event.currentTarget
                .closest(".itineraryPlaceImage")
                ?.classList.add("itineraryPlaceImage--fallback");
            }}
            referrerPolicy="no-referrer"
            src={subplace.imageUrl ?? NO_IMAGE_SRC}
          />
        </div>
      </div>
      <div className="itineraryPlaceContent">
        <header>
          <div className="itineraryPlaceMain">
            <div className="itineraryPlaceTitle">
              <button
                className="placeMapButton"
                disabled={!hasCoordinates}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect();
                }}
                type="button"
              >
                <strong>{subplace.name}</strong>
              </button>
            </div>
            <div className="itineraryPlaceMetrics">
              {subplace.costPerPerson != null ? (
                <span className="itineraryPriceBadge">
                  {subplace.costPerPerson <= 0
                    ? "Miễn phí"
                    : formatPlannerMoney(subplace.costPerPerson, "VND")}
                  {subplace.costPerPerson > 0 ? <small>/ người</small> : null}
                </span>
              ) : null}
              {duration ? <span className="itinerarySubplaceMetric">{duration}</span> : null}
              {subplace.rating != null ? (
                <span className="itinerarySubplaceRating">
                  ★ {subplace.rating.toFixed(1)}
                  {subplace.reviewCount ? ` (${subplace.reviewCount.toLocaleString("vi-VN")})` : ""}
                </span>
              ) : null}
            </div>
          </div>
        </header>
        {subplace.address ? (
          <div className="itinerarySubplaceAddress">
            <span>{subplace.address}</span>
          </div>
        ) : null}
        {hasGeminiNote ? (
          <button
            aria-expanded={expanded}
            className="itinerarySubplaceNoteButton"
            onClick={(event) => {
              event.stopPropagation();
              onToggleDetails();
            }}
            type="button"
          >
            <NoteIcon />
            <span>Ghi chú</span>
            <small>1</small>
          </button>
        ) : null}
        {expanded && hasGeminiNote ? (
          <div className="itinerarySubplaceDetails">
            <strong>Gợi ý tại điểm bên trong</strong>
            <p>{subplace.note}</p>
          </div>
        ) : null}
      </div>
      <div className="itinerarySubplaceCardActions">
        {hasGeminiNote ? (
          <button
            aria-label={`Xem ghi chú Gemini cho ${subplace.name}`}
            aria-expanded={expanded}
            onClick={(event) => {
              event.stopPropagation();
              onToggleDetails();
            }}
            type="button"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <circle cx="5" cy="12" r="1.5" />
              <circle cx="12" cy="12" r="1.5" />
              <circle cx="19" cy="12" r="1.5" />
            </svg>
          </button>
        ) : null}
        <span aria-label="Điểm tham quan" className="itineraryTypeIcon" role="img">
          <ActivityIcon />
        </span>
      </div>
    </article>
  );
}

export function PlannerSubplaceFocus({
  group,
  parentName,
  selectedMapKey,
  onBack,
  onSelect,
}: {
  group: SubplaceGroup;
  parentName: string;
  selectedMapKey: string | null;
  onBack: () => void;
  onSelect: (subplace: SubplaceSummary) => void;
}) {
  const [expandedPlaceId, setExpandedPlaceId] = useState<string | null>(null);

  return (
    <section className="itinerarySubplaceFocus" aria-label={`Điểm bên trong ${parentName}`}>
      <header>
        <button aria-label={`Quay lại ${parentName}`} onClick={onBack} type="button">
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="m15 18-6-6 6-6" />
          </svg>
        </button>
        <div>
          <small>Điểm bên trong</small>
          <strong>{parentName}</strong>
        </div>
        <span>{group.totalCount}</span>
      </header>
      <div className="itinerarySubplaceFocusList">
        {group.items.map((subplace, index) => (
          <SubplaceCard
            expanded={expandedPlaceId === subplace.placeId}
            index={index}
            key={subplace.placeId}
            onToggleDetails={() =>
              setExpandedPlaceId((current) =>
                current === subplace.placeId ? null : subplace.placeId
              )
            }
            onSelect={() => onSelect(subplace)}
            parentName={parentName}
            selected={selectedMapKey === subplaceMapKey(subplace.placeId)}
            subplace={subplace}
          />
        ))}
      </div>
    </section>
  );
}
