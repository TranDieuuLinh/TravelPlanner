"use client";

import type { ReactNode } from "react";

import type {
  TransportLeg,
  TravelPlan,
  UnscheduledPlace,
} from "@/features/planner/api/plans";
import {
  MapPinIcon,
  TransportModeIcon,
} from "@/features/planner/components/PlannerIcons";
import { TransportFareInline } from "@/features/planner/components/TransportFareInline";
import { formatSourceNoteForDisplay } from "@/features/planner/lib/plan-note";
import { itinerarySourceUrls } from "@/features/planner/lib/source-provider";
import {
  formatDistance,
  formatDuration,
  transportModeLabel,
} from "@/features/planner/lib/planner-transport";
import {
  categoryFromPlaceType,
  itineraryDisplayName,
  itinerarySourceLabel,
  SourceProviderIcon,
} from "@/features/planner/lib/planner-formatters";

const ITINERARY_NO_IMAGE_SRC = "/images/penguin-no-image.png";

type Accommodation = NonNullable<TravelPlan["accommodation"]>;

function formatAccommodationPrice(amount: number, currency: string): string {
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function AccommodationItineraryCard({
  accommodation,
  mapKey,
  onFocusMap,
  onZoomMap,
  canManage,
  menuOpen,
  noteCount,
  noteOpen,
  notePanel,
  onDelete,
  onEdit,
  onToggleMenu,
  onToggleNote,
  selected,
}: {
  accommodation: Accommodation;
  mapKey: string;
  onFocusMap: (mapKey: string) => void;
  onZoomMap: (mapKey: string) => void;
  canManage: boolean;
  menuOpen: boolean;
  noteCount: number;
  noteOpen: boolean;
  notePanel?: ReactNode;
  onDelete: () => void;
  onEdit: () => void;
  onToggleMenu: () => void;
  onToggleNote: () => void;
  selected: boolean;
}) {
  return (
    <article className="itineraryStop itineraryStop--accommodation">
      <div
        aria-label={`Hiển thị nơi lưu trú ${accommodation.name} trên bản đồ`}
        className={`itineraryPlaceCard itineraryPlaceCard--withImage itineraryPlaceCard--mapInteractive ${
          selected ? "is-map-place-selected" : ""
        }`}
        data-map-place-key={mapKey}
        onClick={() => onFocusMap(mapKey)}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return;
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          onFocusMap(mapKey);
        }}
        role="button"
        tabIndex={0}
      >
        <div className="itineraryPlaceMedia">
          <div className="itineraryPlaceImage itineraryPlaceImage--fallback">
            <img
              alt={`Chưa có ảnh cho ${accommodation.name}`}
              draggable={false}
              src={ITINERARY_NO_IMAGE_SRC}
            />
          </div>
        </div>
        <div className="itineraryPlaceContent">
          <header>
            <div className="itineraryPlaceMain">
              <div className="itineraryPlaceTitle">
                <button
                  aria-label={`Hiển thị ${accommodation.name} trên bản đồ`}
                  className="placeMapButton"
                  onClick={(event) => {
                    event.stopPropagation();
                    onFocusMap(mapKey);
                  }}
                  onDoubleClick={(event) => {
                    event.stopPropagation();
                    onZoomMap(mapKey);
                  }}
                  title={`Nhấp đúp để phóng to ${accommodation.name} trên bản đồ`}
                  type="button"
                >
                  <strong>{accommodation.name}</strong>
                </button>
              </div>
              <div className="itineraryPriceBadge">
                <span>
                  {formatAccommodationPrice(
                    accommodation.pricePerNight,
                    accommodation.currency,
                  )}{" "}
                  / đêm
                </span>
              </div>
            </div>
          </header>
          <div className="itineraryPlaceQuickActions">
            <span
              aria-label="Nơi lưu trú"
              className="itineraryTypeIcon"
              role="img"
              title="Nơi lưu trú"
            >
              <svg viewBox="0 0 24 24">
                <path d="M5 21V4h14v17M3 21h18M9 21v-4h6v4" />
                <path d="M9 7v5M15 7v5M9 9.5h6" />
              </svg>
            </span>
            {canManage ? (
              <div className="itineraryPlaceQuickActionMenu">
                <button
                  aria-expanded={menuOpen}
                  aria-haspopup="menu"
                  aria-label={`Mở thao tác cho ${accommodation.name}`}
                  className="itineraryQuickActionMenuButton"
                  onClick={(event) => {
                    event.stopPropagation();
                    onToggleMenu();
                  }}
                  title="Thao tác"
                  type="button"
                >
                  <svg aria-hidden="true" viewBox="0 0 24 24">
                    <circle cx="5" cy="12" r="1.5" />
                    <circle cx="12" cy="12" r="1.5" />
                    <circle cx="19" cy="12" r="1.5" />
                  </svg>
                </button>
                {menuOpen ? (
                  <div className="itineraryPlaceQuickActionPopup" role="menu">
                    <button
                      aria-label={`Sửa ${accommodation.name}`}
                      className="itineraryActionButton"
                      onClick={(event) => {
                        event.stopPropagation();
                        onEdit();
                      }}
                      role="menuitem"
                      title="Sửa nơi lưu trú"
                      type="button"
                    >
                      <svg viewBox="0 0 24 24">
                        <path d="M13.5 6.5 17.5 10.5M4 20l4.2-1 10.9-10.9a2.8 2.8 0 0 0-4-4L4.2 15 4 20Z" />
                      </svg>
                    </button>
                    <button
                      aria-label={`Xóa ${accommodation.name}`}
                      className="itineraryActionButton danger"
                      onClick={(event) => {
                        event.stopPropagation();
                        onDelete();
                      }}
                      role="menuitem"
                      title="Xóa nơi lưu trú"
                      type="button"
                    >
                      <svg viewBox="0 0 24 24">
                        <path d="M4 7h16M9 7V4h6v3M18 7l-1 13H7L6 7M10 11v5M14 11v5" />
                      </svg>
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          {(canManage || noteCount > 0) ? (
            <button
              aria-expanded={noteOpen}
              aria-label={
                noteOpen
                  ? `Đóng ghi chú cho ${accommodation.name}`
                  : noteCount
                    ? `Mở ghi chú cho ${accommodation.name}`
                    : `Thêm ghi chú cho ${accommodation.name}`
              }
              className="itineraryActionButton itineraryNoteActionButton"
              onClick={(event) => {
                event.stopPropagation();
                onToggleNote();
              }}
              type="button"
            >
              <svg
                aria-hidden="true"
                className="itineraryNoteActionIcon"
                viewBox="0 0 24 24"
              >
                <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z" />
                <path d="M14 3v6h6M8 13h8M8 17h5" />
              </svg>
              <span className="itineraryNoteActionLabel">Ghi chú</span>
              {noteCount ? (
                <span className="activityNotesButtonCount">{noteCount}</span>
              ) : null}
            </button>
          ) : null}
        </div>
      </div>
      {notePanel}
    </article>
  );
}

export function AccommodationRouteStrip({
  leg,
  onToggle,
  routeKey,
  selected,
  travelerCount,
}: {
  leg: TransportLeg;
  onToggle: (routeKey: string) => void;
  routeKey: string | null;
  selected: boolean;
  travelerCount: number;
}) {
  return (
    <div
      aria-label={`${transportModeLabel(leg.mode)}, từ ${leg.fromPlace} đến ${leg.toPlace}, khoảng ${formatDuration(leg.estimatedDurationMinutes)}`}
      className={`itineraryRoute ${routeKey ? "has-map-route-link" : ""} ${
        selected ? "is-map-route-selected" : ""
      }`}
      data-map-route-key={routeKey ?? undefined}
      role="group"
    >
      <div className="itineraryRouteToolbar">
        <div className="itineraryRouteLink">
          <span className="itineraryRouteIcon" aria-hidden="true">
            <TransportModeIcon mode={leg.mode} />
          </span>
          <span className="itineraryRouteCopy">
            <small>
              {formatDuration(leg.estimatedDurationMinutes)} · {formatDistance(leg.distanceMeters)}
              <TransportFareInline
                option={leg}
                travelerCount={travelerCount}
              />
            </small>
          </span>
        </div>
        {routeKey ? (
          <button
            aria-label={
              selected
                ? `Huỷ làm nổi bật tuyến từ ${leg.fromPlace} đến ${leg.toPlace}`
                : `Làm nổi bật tuyến từ ${leg.fromPlace} đến ${leg.toPlace} trên bản đồ`
            }
            aria-pressed={selected}
            className="itineraryRouteMapButton"
            onClick={(event) => {
              event.stopPropagation();
              onToggle(routeKey);
            }}
            type="button"
          >
            <span aria-hidden="true"><MapPinIcon /></span>
            <span>{selected ? "Huỷ" : "Route"}</span>
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function UnscheduledPlacesSection({
  candidateResolutionProgress = {},
  disabled = false,
  onConfirmCandidate,
  onDismissPlace,
  places,
}: {
  candidateResolutionProgress?: Record<
    string,
    { key: string; status: "queued" | "resolving" }
  >;
  disabled?: boolean;
  onConfirmCandidate?: (place: UnscheduledPlace, matchRank: number) => void;
  onDismissPlace?: (place: UnscheduledPlace) => void;
  places: UnscheduledPlace[];
}) {
  const candidateQueueActive =
    Object.keys(candidateResolutionProgress).length > 0;

  if (places.length === 0) {
    return (
      <div className="unscheduledPlacesEmpty" role="status">
        Chưa có địa điểm chưa xếp
      </div>
    );
  }

  return (
    <article
      aria-labelledby="unscheduled-places-heading"
      className="explorerDayCard unscheduledPlacesSection"
    >
      <header className="dayCardHeading unscheduledPlacesHeading">
        <strong id="unscheduled-places-heading">Chưa xếp</strong>
      </header>
      <div className="itineraryStops unscheduledPlaceList">
          {places.map((place, index) => {
            const displayName = itineraryDisplayName(place.name);
            const sourceActivity = formatSourceNoteForDisplay(
              place.sourceActivity
            );
            const categories = [place.placeType, ...(place.tags ?? [])].filter(
              (value): value is string => Boolean(value)
            );
            const isFoodStop = categories.some((value) => {
              const category = categoryFromPlaceType(value);
              return category === "food";
            });
            const sourceLabel = itinerarySourceLabel(
              itinerarySourceUrls(place),
              place.sourceProvider,
              "selected_place"
            );
            return (
              <div
                className="itineraryItemDragWrapper"
                key={`${place.candidateId ?? place.placeId ?? place.name}-${index}`}
              >
                <article
                  className={`itineraryStop unscheduledPlaceStop ${
                    isFoodStop
                      ? "itineraryStop--food"
                      : "itineraryStop--activity"
                  }`}
                >
                  <div className="itineraryPlaceCard itineraryPlaceCard--withImage">
                    <div className="itineraryPlaceMedia">
                      <div className="itineraryPlaceImage itineraryPlaceImage--fallback">
                        <img
                          alt={`Chưa có ảnh cho ${displayName}`}
                          draggable={false}
                          loading="lazy"
                          src={ITINERARY_NO_IMAGE_SRC}
                        />
                      </div>
                    </div>
                    <div className="itineraryPlaceContent">
                      <header>
                        <div className="itineraryPlaceMain">
                          <div className="itineraryPlaceTitle">
                            <strong>{displayName}</strong>
                          </div>
                        </div>
                      </header>
                        <div className="itineraryPlaceQuickActions">
                          {sourceLabel?.url ? (
                            <a
                              aria-label={`Mở link ${sourceLabel.text} của ${displayName}`}
                              className={`itinerarySourceIconLink itinerarySourceIconLink--${sourceLabel.provider}`}
                              href={sourceLabel.url}
                              rel="noreferrer"
                              target="_blank"
                              title={`Link ${sourceLabel.text}: ${
                                sourceLabel.displayUrl ?? sourceLabel.url
                              }`}
                            >
                              <SourceProviderIcon
                                provider={sourceLabel.provider}
                              />
                              <span>URL</span>
                            </a>
                          ) : null}
                          <span
                            aria-label={
                              isFoodStop ? "Ăn uống" : "Hoạt động tham quan"
                            }
                            className="itineraryTypeIcon"
                            role="img"
                            title={
                              isFoodStop ? "Ăn uống" : "Hoạt động tham quan"
                            }
                          >
                            {isFoodStop ? (
                              <svg viewBox="0 0 24 24">
                                <path d="M6 3v7M3.5 3v4.5A2.5 2.5 0 0 0 6 10a2.5 2.5 0 0 0 2.5-2.5V3M6 10v11" />
                                <path d="M15 3v18M15 3c3 1.1 4.5 3.7 4.5 7H15" />
                              </svg>
                            ) : (
                              <svg viewBox="0 0 24 24">
                                <circle cx="6" cy="6" r="2.5" />
                                <path d="M6 1v1M6 10v1M1 6h1M10 6h1M2.5 2.5l.7.7M8.8 8.8l.7.7M9.5 2.5l-.7.7M3.2 8.8l-.7.7" />
                                <path d="m2 21 6-9 4 5 2-3 8 7" />
                                <path d="M13 5c1-1 2-1 3 0 1-1 2-1 3 0M16 9c1-1 2-1 3 0 1-1 2-1 3 0" />
                              </svg>
                            )}
                          </span>
                        </div>
                      {place.address ? (
                        <p className="unscheduledPlaceAddress">
                          {place.address}
                        </p>
                      ) : null}
                      <div className="itineraryPlaceHours unscheduledPlaceReason">
                        <span>Chưa xếp</span>
                        <strong>{place.reason}</strong>
                      </div>
                      {place.reasonCode === "identity_needs_review" &&
                      (place.topMatches?.length ?? 0) > 0 ? (
                        <div
                          aria-label={`Chọn địa điểm đúng cho ${displayName}`}
                          className="unscheduledMatchPicker"
                        >
                          <span>Kết quả cần xác nhận</span>
                          <div className="unscheduledMatchList">
                            {place.topMatches?.slice(0, 3).map((match) => {
                              const buttonKey = `${place.candidateId ?? ""}:${match.rank}`;
                              const resolutionProgress = place.candidateId
                                ? candidateResolutionProgress[place.candidateId]
                                : undefined;
                              const canChoose = Boolean(
                                onConfirmCandidate &&
                                place.candidateId &&
                                match.latitude != null &&
                                match.longitude != null
                              );
                              const handleChoice = onConfirmCandidate;
                              return (
                                <button
                                  className="unscheduledMatchButton"
                                  disabled={
                                    !canChoose ||
                                    Boolean(resolutionProgress) ||
                                    (disabled && !candidateQueueActive)
                                  }
                                  key={`${match.rank}-${match.name}`}
                                  onClick={() => {
                                    if (canChoose && handleChoice) {
                                      handleChoice(place, match.rank);
                                    }
                                  }}
                                  title={
                                    canChoose
                                      ? `Chọn ${match.name}`
                                      : "Kết quả này thiếu tọa độ"
                                  }
                                  type="button"
                                >
                                  <strong>
                                    {resolutionProgress?.key === buttonKey
                                      ? resolutionProgress.status === "queued"
                                        ? "Đã xếp hàng..."
                                        : "Đang chọn..."
                                      : match.name}
                                  </strong>
                                  {match.address ? (
                                    <small>{match.address}</small>
                                  ) : null}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ) : null}
                      {place.day != null || sourceActivity ? (
                        <p className="unscheduledPlaceContext">
                          {place.day != null
                            ? `Ưu tiên Ngày ${place.day}`
                            : null}
                          {place.day != null && sourceActivity
                            ? " · "
                            : null}
                          {sourceActivity}
                        </p>
                      ) : null}
                      {onDismissPlace ? (
                        <div className="unscheduledPlaceActions">
                          <button
                            className="unscheduledDismissButton"
                            disabled={disabled}
                            onClick={() => onDismissPlace(place)}
                            type="button"
                          >
                            Không thêm vào kế hoạch
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </article>
              </div>
            );
          })}
      </div>
    </article>
  );
}
