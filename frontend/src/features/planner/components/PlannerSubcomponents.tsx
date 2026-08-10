"use client";

import type { UnscheduledPlace } from "@/features/planner/api/plans";
import type { PlaceReviewsModalPlace } from "@/features/planner/components/PlaceReviewsModal";
import { formatSourceNoteForDisplay } from "@/features/planner/lib/plan-note";
import {
  categoryFromPlaceType,
  formatCompactCount,
  itineraryDisplayName,
  itinerarySourceLabel,
  SourceProviderIcon,
} from "@/features/planner/lib/planner-formatters";

const ITINERARY_NO_IMAGE_SRC = "/images/penguin-no-image.png";

export function ItineraryReviewRating({
  onOpen,
  place,
}: {
  onOpen?: (place: PlaceReviewsModalPlace) => void;
  place: PlaceReviewsModalPlace;
}) {
  const content = (
    <>
      <span aria-hidden="true">★</span>
      <strong>{place.rating?.toFixed(1)}</strong>
      {place.reviewCount != null && place.reviewCount > 0 ? (
        <small>
          {formatCompactCount(place.reviewCount)} lượt đánh giá
        </small>
      ) : null}
    </>
  );

  if (place.placeId && onOpen) {
    return (
      <button
        aria-label={`Đọc đánh giá của ${place.name}`}
        className="itineraryPlaceRating"
        onClick={(event) => {
          event.stopPropagation();
          onOpen(place);
        }}
        title="Đọc đánh giá"
        type="button"
      >
        {content}
      </button>
    );
  }

  return (
    <div
      aria-label={`Đánh giá ${place.rating ?? 0} trên 5`}
      className="itineraryPlaceRating"
    >
      {content}
    </div>
  );
}

export function UnscheduledPlacesSection({
  candidateResolutionProgress = {},
  disabled = false,
  onConfirmCandidate,
  onDismissPlace,
  onOpenReviews,
  places,
}: {
  candidateResolutionProgress?: Record<
    string,
    { key: string; status: "queued" | "resolving" }
  >;
  disabled?: boolean;
  onConfirmCandidate?: (place: UnscheduledPlace, matchRank: number) => void;
  onDismissPlace?: (place: UnscheduledPlace) => void;
  onOpenReviews?: (place: PlaceReviewsModalPlace) => void;
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
              place.sourceRefs ?? [],
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
                          {place.rating != null ? (
                            <ItineraryReviewRating
                              onOpen={onOpenReviews}
                              place={{
                                placeId: place.placeId ?? "",
                                name: displayName,
                                rating: place.rating,
                                reviewCount: place.reviewCount,
                              }}
                            />
                          ) : null}
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
