"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type {
  LayerGroup,
  Map as LeafletMap,
  Marker
} from "leaflet";
import { createDayColorMap } from "@/lib/day-colors";
import { formatPlanNote } from "@/lib/plan-note";
import type { ExplorePlace } from "@/lib/plans";

export type PlannerMapPlace = ExplorePlace & {
  mapKey: string;
  mapOrder: number;
  dayColorKey: string;
  dayLabel: string;
  timeWindow: string;
};

export type PlannerMapRoute = {
  key: string;
  coordinates: [number, number][];
  verified: boolean;
  source: string;
  dayColorKey: string;
  kind?: "itinerary" | "current_location";
  segments?: Array<{
    mode: string;
    geometryCoordinates: [number, number][];
  }>;
};

export type PlannerMapCurrentLocation = {
  latitude: number;
  longitude: number;
  accuracy: number;
  heading?: number | null;
};

type PlannerMapProps = {
  places: PlannerMapPlace[];
  routes: PlannerMapRoute[];
  currentLocation: PlannerMapCurrentLocation | null;
  directionsActive: boolean;
  directionsBusy: boolean;
  directionsDay: number | null;
  directionsEnabled: boolean;
  locationFocusRequest: number;
  dayColorKeys?: string[];
  locationBusy: boolean;
  locationMessage: string | null;
  onLocate: () => void;
  onStartDirections: () => void;
  selectedKey: string | null;
  onSelect: (key: string) => void;
};

const VIETNAM_CENTER: [number, number] = [16.2, 106.2];
const VALHALLA_ROUTING_ATTRIBUTION =
  'Routing by <a href="https://valhalla.github.io/valhalla/">Valhalla</a>';
const OTP_ROUTING_ATTRIBUTION =
  'Transit by <a href="https://www.opentripplanner.org/">OpenTripPlanner</a>';

function hasCoordinates(
  place: PlannerMapPlace
): place is PlannerMapPlace & { latitude: number; longitude: number } {
  return (
    typeof place.latitude === "number" &&
    Number.isFinite(place.latitude) &&
    place.latitude >= -90 &&
    place.latitude <= 90 &&
    typeof place.longitude === "number" &&
    Number.isFinite(place.longitude) &&
    place.longitude >= -180 &&
    place.longitude <= 180
  );
}

export function PlannerMap({
  places,
  routes,
  currentLocation,
  directionsActive,
  directionsBusy,
  directionsDay,
  directionsEnabled,
  locationFocusRequest,
  dayColorKeys = [],
  locationBusy,
  locationMessage,
  onLocate,
  onStartDirections,
  selectedKey,
  onSelect
}: PlannerMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const markerLayerRef = useRef<LayerGroup | null>(null);
  const routeLayerRef = useRef<LayerGroup | null>(null);
  const markersRef = useRef(new Map<string, Marker>());
  const lastPlacesSignatureRef = useRef("");
  const lastCurrentRouteSignatureRef = useRef("");
  const [mapReady, setMapReady] = useState(false);

  const locatedPlaces = useMemo(() => places.filter(hasCoordinates), [places]);
  const dayColors = useMemo(
    () =>
      createDayColorMap([
        ...dayColorKeys,
        ...locatedPlaces.map((place) => place.dayColorKey),
        ...routes.map((route) => route.dayColorKey)
      ]),
    [dayColorKeys, locatedPlaces, routes]
  );
  useEffect(() => {
    let disposed = false;

    async function initializeMap() {
      if (!containerRef.current || mapRef.current) return;

      const leaflet = await import("leaflet");
      if (disposed || !containerRef.current) return;

      leafletRef.current = leaflet;
      const map = leaflet
        .map(containerRef.current, {
          attributionControl: true,
          zoomControl: false
        })
        .setView(VIETNAM_CENTER, 5);

      leaflet.control.zoom({ position: "topright" }).addTo(map);

      leaflet
        .tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution:
            '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
          maxZoom: 19
        })
        .addTo(map);

      markerLayerRef.current = leaflet.layerGroup().addTo(map);
      mapRef.current = map;
      setMapReady(true);
    }

    void initializeMap();

    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
      markerLayerRef.current = null;
      routeLayerRef.current = null;
      markersRef.current.clear();
      leafletRef.current = null;
    };
  }, []);

  useEffect(() => {
    const leaflet = leafletRef.current;
    const map = mapRef.current;
    const markerLayer = markerLayerRef.current;
    if (!mapReady || !leaflet || !map || !markerLayer) return;

    markerLayer.clearLayers();
    markersRef.current.clear();
    routeLayerRef.current?.remove();
    routeLayerRef.current = leaflet.layerGroup().addTo(map);
    map.attributionControl.removeAttribution(
      VALHALLA_ROUTING_ATTRIBUTION
    );
    map.attributionControl.removeAttribution(OTP_ROUTING_ATTRIBUTION);

    locatedPlaces.forEach((place) => {
      const isSelected = place.mapKey === selectedKey;
      const markerColor = dayColors.get(place.dayColorKey) ?? "#167c68";
      const icon = leaflet.divIcon({
        className: [
          "candidateMapMarker",
          isSelected ? "is-selected" : ""
        ]
          .filter(Boolean)
          .join(" "),
        html: `<span style="--marker-color: ${markerColor}"><b>${place.mapOrder}</b></span>`,
        iconAnchor: [21, 48],
        iconSize: [42, 48],
        popupAnchor: [0, -43]
      });

      const marker = leaflet
        .marker([place.latitude, place.longitude], {
          icon,
          keyboard: true,
          title: place.name
        })
        .addTo(markerLayer);

      const popup = document.createElement("div");
      popup.className = "candidateMapPopup";
      const name = document.createElement("strong");
      name.textContent = `${place.mapOrder}. ${place.name}`;
      const day = document.createElement("small");
      day.textContent = place.dayLabel;
      const time = document.createElement("span");
      time.textContent = place.timeWindow;
      const address = document.createElement("span");
      address.className = "candidateMapPopupAddress";
      address.textContent = place.address || "Chưa có địa chỉ";
      popup.append(name, day, time, address);
      const displayNotes = formatPlanNote(place.notes);
      if (displayNotes) {
        const description = document.createElement("p");
        description.textContent = displayNotes;
        popup.append(description);
      }
      marker.bindPopup(popup);
      marker.on("click", () => onSelect(place.mapKey));
      markersRef.current.set(place.mapKey, marker);
    });

    if (currentLocation) {
      leaflet
        .circle(
          [currentLocation.latitude, currentLocation.longitude],
          {
            className: "currentLocationAccuracy",
            color: "#1769aa",
            fillColor: "#4f9bd5",
            fillOpacity: 0.1,
            opacity: 0.32,
            radius: Math.max(currentLocation.accuracy, 8),
            weight: 1
          }
        )
        .addTo(markerLayer);
      const currentIcon = leaflet.divIcon({
        className: "currentLocationMarker",
        html:
          typeof currentLocation.heading === "number"
            ? `<span class="has-heading" style="--location-heading: ${currentLocation.heading}deg"><i></i></span>`
            : "<span><i></i></span>",
        iconAnchor: [18, 18],
        iconSize: [36, 36],
        popupAnchor: [0, -18]
      });
      const currentMarker = leaflet
        .marker(
          [currentLocation.latitude, currentLocation.longitude],
          {
            icon: currentIcon,
            keyboard: true,
            title: "Vị trí của bạn",
            zIndexOffset: 1200
          }
        )
        .addTo(markerLayer);
      const popup = document.createElement("div");
      popup.className = "candidateMapPopup";
      const name = document.createElement("strong");
      name.textContent = "Vị trí của bạn";
      const detail = document.createElement("span");
      detail.textContent = `Độ chính xác khoảng ${Math.round(currentLocation.accuracy)} m`;
      popup.append(name, detail);
      currentMarker.bindPopup(popup);
    }

    const addTransitStopMarker = (
      coordinate: [number, number],
      label: string,
      kind: "boarding" | "alighting"
    ) => {
      const icon = leaflet.divIcon({
        className: `transitStopMarker ${kind}`,
        html: `<span><i aria-hidden="true"></i>${label}</span>`,
        iconAnchor: [12, 12],
        iconSize: [24, 24]
      });
      leaflet
        .marker(coordinate, { icon, keyboard: false, title: label })
        .addTo(routeLayerRef.current!);
    };

    if (routes.length > 0 && routeLayerRef.current) {
      routes.forEach((route) => {
        const isCurrentLocationRoute = route.kind === "current_location";
        const routeColor = isCurrentLocationRoute
          ? "#1769aa"
          : dayColors.get(route.dayColorKey) ?? "#167c68";
        const transitSegments = route.source === "opentripplanner_transit"
          ? (route.segments ?? []).filter(
              (segment) => segment.geometryCoordinates.length >= 2
            )
          : [];
        const paths = transitSegments.length > 0
          ? transitSegments.map((segment) => ({
              coordinates: segment.geometryCoordinates,
              mode: segment.mode
            }))
          : [{ coordinates: route.coordinates, mode: "" }];

        paths.forEach((path) => {
          const isWalk = path.mode.toLowerCase().includes("walk");
          const color = isWalk ? "#63727a" : routeColor;
          const dashArray = transitSegments.length > 0
            ? (isWalk ? "3 7" : undefined)
            : (route.verified ? undefined : "8 9");
          leaflet
            .polyline(path.coordinates, {
              color: "rgba(255, 255, 255, .94)",
              dashArray,
              opacity: 1,
              weight: isWalk ? 7 : 9
            })
            .addTo(routeLayerRef.current!);
          leaflet
            .polyline(path.coordinates, {
              color,
              dashArray,
              lineCap: "round",
              lineJoin: "round",
              opacity: 0.96,
              weight: isWalk ? 3.5 : 5.5
            })
            .addTo(routeLayerRef.current!);
        });

        const busSegments = transitSegments.filter((segment) =>
          ["bus", "transit", "public"].some((token) =>
            segment.mode.toLowerCase().includes(token)
          )
        );
        const boardingPoint = busSegments[0]?.geometryCoordinates[0];
        const alightingPoint = busSegments.at(-1)?.geometryCoordinates.at(-1);
        if (boardingPoint) {
          addTransitStopMarker(boardingPoint, "Lên xe", "boarding");
        }
        if (alightingPoint) {
          addTransitStopMarker(alightingPoint, "Xuống xe", "alighting");
        }
      });
    }

    if (routes.some((route) => route.source === "valhalla_routing")) {
      map.attributionControl.addAttribution(
        VALHALLA_ROUTING_ATTRIBUTION
      );
    }
    if (
      routes.some(
        (route) => route.source === "opentripplanner_transit"
      )
    ) {
      map.attributionControl.addAttribution(OTP_ROUTING_ATTRIBUTION);
    }

    const currentLocationRoutes = routes.filter(
      (route) => route.kind === "current_location"
    );
    const currentRouteSignature = currentLocationRoutes
      .map((route) => [
        route.key,
        route.coordinates.length,
        route.coordinates[0]?.join(","),
        route.coordinates.at(-1)?.join(",")
      ].join(":"))
      .join("|");
    const shouldFrameNewRoute =
      currentLocationRoutes.length > 0 &&
      currentRouteSignature !== lastCurrentRouteSignatureRef.current;
    if (shouldFrameNewRoute) {
      const routeBounds = leaflet.latLngBounds(
        currentLocationRoutes.flatMap((route) => route.coordinates)
      );
      map.fitBounds(routeBounds, {
        animate: true,
        maxZoom: 15,
        paddingBottomRight: [52, 110],
        paddingTopLeft: [52, 72]
      });
    }
    lastCurrentRouteSignatureRef.current = currentRouteSignature;

    const signature = locatedPlaces
      .map((place) => `${place.mapKey}:${place.latitude}:${place.longitude}`)
      .join("|");
    if (!shouldFrameNewRoute && signature !== lastPlacesSignatureRef.current) {
      fitPlaces();
      lastPlacesSignatureRef.current = signature;
    }
  }, [
    currentLocation,
    dayColors,
    locatedPlaces,
    mapReady,
    onSelect,
    routes,
    selectedKey
  ]);

  useEffect(() => {
    if (!selectedKey || !mapReady) return;
    const marker = markersRef.current.get(selectedKey);
    const map = mapRef.current;
    if (!marker || !map) return;

    map.panTo(marker.getLatLng(), { animate: true });
    marker.openPopup();
  }, [mapReady, selectedKey]);

  useEffect(() => {
    if (
      locationFocusRequest <= 0 ||
      !currentLocation ||
      !mapReady
    ) {
      return;
    }
    focusCurrentLocation();
  }, [currentLocation, locationFocusRequest, mapReady]);

  function focusCurrentLocation() {
    const map = mapRef.current;
    if (!map || !currentLocation) return;
    map.setView(
      [currentLocation.latitude, currentLocation.longitude],
      Math.max(map.getZoom(), 16),
      { animate: true }
    );
  }

  function fitPlaces() {
    const leaflet = leafletRef.current;
    const map = mapRef.current;
    if (!leaflet || !map) return;

    const coordinates: [number, number][] = locatedPlaces.map(
      (place) => [place.latitude, place.longitude]
    );
    if (currentLocation) {
      coordinates.push([
        currentLocation.latitude,
        currentLocation.longitude
      ]);
    }
    if (coordinates.length === 0) {
      map.setView(VIETNAM_CENTER, 5);
      return;
    }
    if (coordinates.length === 1) {
      map.setView(coordinates[0], 14);
      return;
    }

    const bounds = leaflet.latLngBounds(coordinates);
    map.fitBounds(bounds, { padding: [52, 52], maxZoom: 15 });
  }

  return (
    <section className="plannerMap panel" aria-label="Bản đồ địa điểm đề xuất">
      <div className="plannerMapCanvasWrap">
        <div className="plannerMapCanvas" ref={containerRef} />
        {locatedPlaces.length > 0 ? (
          <button
            aria-label="Hiển thị toàn bộ địa điểm trên bản đồ"
            className="mapFitButton"
            onClick={fitPlaces}
            type="button"
          >
            <FitMapIcon />
            <span>Vừa khung</span>
          </button>
        ) : null}
        <button
          aria-label="Định vị và hướng camera theo vị trí hiện tại"
          className="mapLocationButton"
          disabled={locationBusy}
          onClick={onLocate}
          type="button"
        >
          <LocateIcon />
          <span>
            {locationBusy
              ? "Đang định vị…"
              : currentLocation
                ? "Định vị lại"
                : "Vị trí của tôi"}
          </span>
        </button>
        {directionsDay != null ? (
          <div
            aria-label={`Chỉ đường cho ngày ${directionsDay}`}
            className="mapDirectionsControl"
          >
            <button
              className="mapDirectionsButton"
              disabled={!directionsEnabled || directionsBusy}
              onClick={onStartDirections}
              type="button"
            >
              <DirectionsIcon />
              <span>
                {directionsBusy
                  ? "Đang tính…"
                  : directionsActive
                    ? `Tính lại ngày ${directionsDay}`
                    : `Chỉ đường ngày ${directionsDay}`}
              </span>
            </button>
          </div>
        ) : null}
        {locationMessage ? (
          <div className="mapLocationStatus" role="status">
            {locationMessage}
          </div>
        ) : null}
        {places.length > 0 && locatedPlaces.length === 0 ? (
          <div className="mapEmptyNotice">
            <strong>Chưa có tọa độ để đặt marker</strong>
            <span>
              Các địa điểm đề xuất vẫn được giữ trong danh sách để xác minh vị
              trí.
            </span>
          </div>
        ) : null}
      </div>

    </section>
  );
}

function FitMapIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" />
    </svg>
  );
}

function LocateIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="4" />
      <circle cx="12" cy="12" r="8" />
      <path d="M12 2v2m0 16v2M2 12h2m16 0h2" />
    </svg>
  );
}

function DirectionsIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="m12 3 9 9-9 9-9-9z" />
      <path d="M8 12h7m-3-3 3 3-3 3" />
    </svg>
  );
}
