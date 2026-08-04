"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type {
  AttributionControl,
  Map as MapLibreMap,
  MapLayerMouseEvent,
  Marker
} from "maplibre-gl";
import { createDayColorMap } from "@/lib/day-colors";
import { routeForwardBearing } from "@/lib/map-navigation";
import { formatPlanNote } from "@/lib/plan-note";
import type { ExplorePlace } from "@/lib/plans";

export type PlannerMapPlace = ExplorePlace & {
  mapKey: string;
  mapOrder: number;
  dayColorKey: string;
  dayLabel: string;
  timeWindow: string;
  imageUrl?: string | null;
};

export type PlannerMapRoute = {
  key: string;
  mode: string;
  fromPlace: string;
  toPlace: string;
  distanceMeters: number;
  estimatedDurationMinutes: number;
  coordinates: [number, number][];
  verified: boolean;
  source: string;
  dayColorKey: string;
  kind?: "itinerary" | "current_location";
  segments?: Array<{
    mode: string;
    fromPlace: string;
    toPlace: string;
    distanceMeters: number;
    estimatedDurationMinutes: number;
    geometryCoordinates: [number, number][];
    line?: string | null;
    headsign?: string | null;
  }>;
};

export type PlannerMapCurrentLocation = {
  latitude: number;
  longitude: number;
  accuracy: number;
  heading?: number | null;
  label?: string;
  detail?: string;
  kind?: "device" | "searched";
};

export type PlannerMapSearchPlace = {
  key: string;
  name: string;
  detail?: string | null;
  latitude: number;
  longitude: number;
  kind: "plan" | "searched" | "map";
};

type PlannerMapProps = {
  places: PlannerMapPlace[];
  routes: PlannerMapRoute[];
  currentLocation: PlannerMapCurrentLocation | null;
  directionsActive: boolean;
  directionsBusy: boolean;
  directionsSearchOpen: boolean;
  directionsDay: number | null;
  directionsEnabled: boolean;
  originQuery: string;
  originSuggestions: PlannerMapSearchPlace[];
  originSearchBusy: boolean;
  destinationQuery: string;
  destinationSuggestions: PlannerMapSearchPlace[];
  destinationOptions: PlannerMapSearchPlace[];
  destinationSearchBusy: boolean;
  selectedDirectionDestination: PlannerMapSearchPlace | null;
  mapDestinationPickActive: boolean;
  locationFocusRequest: number;
  routeFocusRequest: number;
  dayColorKeys?: string[];
  locationBusy: boolean;
  locationMessage: string | null;
  onLocate: () => void;
  onStartDirections: () => void;
  onSubmitDirections: () => void;
  onCloseDirectionsSearch: () => void;
  onOriginQueryChange: (value: string) => void;
  onChooseOrigin: (place: PlannerMapSearchPlace) => void;
  onUseCurrentOrigin: () => void;
  onDestinationQueryChange: (value: string) => void;
  onChooseDestination: (place: PlannerMapSearchPlace) => void;
  onToggleMapDestinationPick: () => void;
  onChooseMapDestination: (place: PlannerMapSearchPlace) => void;
  onViewDayRoute: () => void;
  onCancelDirections: () => void;
  selectedKey: string | null;
  selectedRouteKey: string | null;
  onSelect: (key: string) => void;
  onSelectRoute: (key: string) => void;
};

const VIETNAM_CENTER: [number, number] = [106.2, 16.2];
const DEFAULT_MAP_STYLE = "https://tiles.openfreemap.org/styles/bright";
const MAP_STYLE_URL =
  process.env.NEXT_PUBLIC_PLANNER_MAP_STYLE_URL ?? DEFAULT_MAP_STYLE;
const MAP_LAND_COLOR = "#f6f5f5";
const MAP_WATER_COLOR = "#8fdaed";
const MAP_WATER_LINE_COLOR = "#64bed3";
const MAP_PARK_COLOR = "#d3f8e1";
const MAP_BUILDING_COLOR = "#eeeeee";
const MAP_BOUNDARY_COLOR = "#cbd8e0";
const MAP_RAIL_COLOR = "#aab8c0";
const MAP_ROAD_COLOR = "#ffffff";
const MAP_TEXT_COLOR = "#45545c";
const MAP_ROUTE_COLOR = "#075fa7";
const MAP_WALK_ROUTE_COLOR = "#697a80";
const MAP_TRANSIT_ROUTE_COLOR = "#167c68";
const OSM_ATTRIBUTION =
  '<a href="https://www.openstreetmap.org/copyright" title="OpenStreetMap contributors and copyright">© OpenStreetMap</a>';
const VALHALLA_ROUTING_ATTRIBUTION =
  '<a href="https://valhalla.github.io/valhalla/">Valhalla routing</a>';
const OTP_ROUTING_ATTRIBUTION =
  'Transit by <a href="https://www.opentripplanner.org/">OpenTripPlanner</a>';

type MapRouteMode = "walk" | "car" | "transit" | "bike" | "unknown";

function mapRouteMode(mode: string): MapRouteMode {
  const normalized = mode.toLowerCase();
  if (normalized.includes("walk") || normalized.includes("pedestrian")) {
    return "walk";
  }
  if (
    normalized.includes("car") ||
    normalized.includes("auto") ||
    normalized.includes("taxi")
  ) {
    return "car";
  }
  if (normalized.includes("bike") || normalized.includes("motor")) {
    return "bike";
  }
  if (
    ["bus", "train", "public", "transit"].some((token) =>
      normalized.includes(token)
    )
  ) {
    return "transit";
  }
  return "unknown";
}

function mapRouteModeDetails(
  mode: string
): { icon: string; label: string } | null {
  switch (mapRouteMode(mode)) {
    case "walk":
      return { icon: "🚶", label: "Đi bộ" };
    case "car":
      return { icon: "🚗", label: "Ô tô" };
    case "bike":
      return { icon: "🛵", label: "Xe máy" };
    case "transit":
      return { icon: "🚌", label: "Phương tiện công cộng" };
    default:
      return null;
  }
}

function createCurrentLocationModeIcon(
  mode: MapRouteMode
): SVGSVGElement | null {
  if (mode !== "car" && mode !== "walk") return null;

  const svgNamespace = "http://www.w3.org/2000/svg";
  const icon = document.createElementNS(svgNamespace, "svg");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("viewBox", "0 0 24 24");

  if (mode === "walk") {
    const head = document.createElementNS(svgNamespace, "circle");
    head.setAttribute("cx", "13");
    head.setAttribute("cy", "4");
    head.setAttribute("r", "2");
    const body = document.createElementNS(svgNamespace, "path");
    body.setAttribute("d", "m10 21 2-6-3-3 2-5 4 3 3 1M12 15l4 6M9 12l-4 3");
    icon.append(head, body);
    return icon;
  }

  const roof = document.createElementNS(svgNamespace, "path");
  roof.setAttribute("d", "m5 11 2-5h10l2 5");
  const body = document.createElementNS(svgNamespace, "path");
  body.setAttribute("d", "M4 12a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v5H4zM6 17v2m12-2v2");
  const leftWheel = document.createElementNS(svgNamespace, "circle");
  leftWheel.setAttribute("cx", "8");
  leftWheel.setAttribute("cy", "14");
  leftWheel.setAttribute("r", "1");
  const rightWheel = document.createElementNS(svgNamespace, "circle");
  rightWheel.setAttribute("cx", "16");
  rightWheel.setAttribute("cy", "14");
  rightWheel.setAttribute("r", "1");
  icon.append(roof, body, leftWheel, rightWheel);
  return icon;
}

function formatRouteDistance(distanceMeters: number): string {
  if (distanceMeters < 1000) return `${Math.max(0, Math.round(distanceMeters))} m`;
  return `${(distanceMeters / 1000).toLocaleString("vi-VN", {
    maximumFractionDigits: 1
  })} km`;
}

function formatRouteDuration(durationMinutes: number): string {
  const roundedMinutes = Math.max(1, Math.round(durationMinutes));
  if (roundedMinutes < 60) return `${roundedMinutes} phút`;
  const hours = Math.floor(roundedMinutes / 60);
  const minutes = roundedMinutes % 60;
  return minutes > 0 ? `${hours} giờ ${minutes} phút` : `${hours} giờ`;
}

function routeMidpoint(
  coordinates: [number, number][]
): [number, number] | null {
  if (coordinates.length < 2) return null;
  const lengths = coordinates.slice(1).map((coordinate, index) => {
    const previous = coordinates[index];
    return Math.hypot(
      coordinate[0] - previous[0],
      coordinate[1] - previous[1]
    );
  });
  const totalLength = lengths.reduce((total, length) => total + length, 0);
  if (totalLength === 0) return coordinates[0];

  const targetLength = totalLength / 2;
  let traversed = 0;
  for (let index = 0; index < lengths.length; index += 1) {
    const segmentLength = lengths[index];
    if (traversed + segmentLength >= targetLength) {
      const ratio = (targetLength - traversed) / segmentLength;
      const start = coordinates[index];
      const end = coordinates[index + 1];
      return [
        start[0] + (end[0] - start[0]) * ratio,
        start[1] + (end[1] - start[1]) * ratio
      ];
    }
    traversed += segmentLength;
  }
  return coordinates.at(-1) ?? null;
}

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

function applyCleanPlannerStyle(map: MapLibreMap) {
  const hiddenPoiPattern =
    /poi|amenity|shop|restaurant|cafe|bar|hotel|lodging|tourism|attraction|hospital|school|college|airport|aeroway|transit|railway|bus|ferry/i;

  map.getStyle().layers.forEach((layer) => {
    const sourceLayer =
      "source-layer" in layer ? String(layer["source-layer"] ?? "") : "";
    const layerKey = `${layer.id} ${sourceLayer}`;

    try {
      if (layer.type === "background") {
        map.setPaintProperty(layer.id, "background-color", MAP_LAND_COLOR);
        return;
      }

      if (layer.type === "symbol") {
        if (hiddenPoiPattern.test(layerKey)) {
          map.setLayoutProperty(layer.id, "visibility", "none");
          return;
        }
        map.setPaintProperty(layer.id, "icon-opacity", 0);
        map.setPaintProperty(layer.id, "text-color", MAP_TEXT_COLOR);
        map.setPaintProperty(layer.id, "text-halo-color", "#ffffff");
        map.setPaintProperty(layer.id, "text-halo-width", 1.5);
        map.setPaintProperty(layer.id, "text-opacity", 1);
        return;
      }

      if (layer.type === "fill") {
        if (/water/i.test(layerKey)) {
          map.setPaintProperty(layer.id, "fill-color", MAP_WATER_COLOR);
          map.setPaintProperty(layer.id, "fill-opacity", 1);
        } else if (/park|grass|wood|forest|landcover|landuse/i.test(layerKey)) {
          map.setPaintProperty(layer.id, "fill-color", MAP_PARK_COLOR);
          map.setPaintProperty(layer.id, "fill-opacity", 0.96);
        } else if (/building/i.test(layerKey)) {
          map.setPaintProperty(layer.id, "fill-color", MAP_BUILDING_COLOR);
          map.setPaintProperty(layer.id, "fill-opacity", 0.94);
        } else {
          map.setPaintProperty(layer.id, "fill-color", MAP_LAND_COLOR);
        }
        return;
      }

      if (layer.type === "line") {
        if (/road|street|path|highway|tunnel|bridge/i.test(layerKey)) {
          map.setPaintProperty(layer.id, "line-color", MAP_ROAD_COLOR);
          map.setPaintProperty(layer.id, "line-opacity", 1);
        } else if (/water/i.test(layerKey)) {
          map.setPaintProperty(layer.id, "line-color", MAP_WATER_LINE_COLOR);
          map.setPaintProperty(layer.id, "line-opacity", 1);
        } else if (/boundary/i.test(layerKey)) {
          map.setPaintProperty(layer.id, "line-color", MAP_BOUNDARY_COLOR);
          map.setPaintProperty(layer.id, "line-opacity", 0.9);
        } else if (/rail/i.test(layerKey)) {
          map.setPaintProperty(layer.id, "line-color", MAP_RAIL_COLOR);
          map.setPaintProperty(layer.id, "line-opacity", 0.86);
        } else {
          map.setPaintProperty(layer.id, "line-color", MAP_LAND_COLOR);
        }
        return;
      }

      if (layer.type === "circle") {
        map.setPaintProperty(layer.id, "circle-color", MAP_ROUTE_COLOR);
        map.setPaintProperty(layer.id, "circle-stroke-color", "#ffffff");
        return;
      }

      if (layer.type === "fill-extrusion") {
        map.setPaintProperty(layer.id, "fill-extrusion-color", MAP_LAND_COLOR);
      }
    } catch {
      // Third-party styles can omit optional paint properties. Keep the rest
      // of the clean style usable when one layer cannot be adjusted.
    }
  });
}

function createAccuracyPolygon(
  longitude: number,
  latitude: number,
  radiusMeters: number
) {
  const earthRadius = 6_378_137;
  const latitudeRadians = (latitude * Math.PI) / 180;
  const longitudeRadians = (longitude * Math.PI) / 180;
  const angularDistance = Math.max(radiusMeters, 8) / earthRadius;
  const coordinates: [number, number][] = [];

  for (let step = 0; step <= 48; step += 1) {
    const bearing = (step / 48) * Math.PI * 2;
    const pointLatitude = Math.asin(
      Math.sin(latitudeRadians) * Math.cos(angularDistance) +
        Math.cos(latitudeRadians) *
          Math.sin(angularDistance) *
          Math.cos(bearing)
    );
    const pointLongitude =
      longitudeRadians +
      Math.atan2(
        Math.sin(bearing) *
          Math.sin(angularDistance) *
          Math.cos(latitudeRadians),
        Math.cos(angularDistance) -
          Math.sin(latitudeRadians) * Math.sin(pointLatitude)
      );
    coordinates.push([
      (pointLongitude * 180) / Math.PI,
      (pointLatitude * 180) / Math.PI
    ]);
  }

  return coordinates;
}

export function PlannerMap({
  places,
  routes,
  currentLocation,
  directionsActive,
  directionsBusy,
  directionsSearchOpen,
  directionsDay,
  directionsEnabled,
  originQuery,
  originSuggestions,
  originSearchBusy,
  destinationQuery,
  destinationSuggestions,
  destinationOptions,
  destinationSearchBusy,
  selectedDirectionDestination,
  mapDestinationPickActive,
  locationFocusRequest,
  routeFocusRequest,
  dayColorKeys = [],
  locationBusy,
  locationMessage,
  onLocate,
  onStartDirections,
  onSubmitDirections,
  onCloseDirectionsSearch,
  onOriginQueryChange,
  onChooseOrigin,
  onUseCurrentOrigin,
  onDestinationQueryChange,
  onChooseDestination,
  onToggleMapDestinationPick,
  onChooseMapDestination,
  onViewDayRoute,
  onCancelDirections,
  selectedKey,
  selectedRouteKey,
  onSelect,
  onSelectRoute
}: PlannerMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const maplibreRef = useRef<typeof import("maplibre-gl") | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const routesRef = useRef(routes);
  const markersRef = useRef(new Map<string, Marker>());
  const dynamicMarkersRef = useRef<Marker[]>([]);
  const dynamicLayerIdsRef = useRef<string[]>([]);
  const dynamicSourceIdsRef = useRef<string[]>([]);
  const attributionControlRef = useRef<AttributionControl | null>(null);
  const lastPlacesSignatureRef = useRef("");
  const lastCurrentRouteSignatureRef = useRef("");
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  routesRef.current = routes;

  useEffect(() => {
    if (!directionsActive) return;
    const previousBodyOverflow = document.body.style.overflow;
    const previousRootOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousRootOverflow;
    };
  }, [directionsActive]);

  useEffect(() => {
    if (!mapReady) return;
    const resizeFrame = window.requestAnimationFrame(() => {
      mapRef.current?.resize();
    });
    return () => window.cancelAnimationFrame(resizeFrame);
  }, [directionsActive, mapReady]);

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
    let styleLoaded = false;

    async function initializeMap() {
      if (!containerRef.current || mapRef.current) return;

      const maplibre = await import("maplibre-gl");
      if (disposed || !containerRef.current) return;

      maplibreRef.current = maplibre;
      const map = new maplibre.Map({
        attributionControl: false,
        center: VIETNAM_CENTER,
        container: containerRef.current,
        maxZoom: 19,
        style: MAP_STYLE_URL,
        zoom: 4.7
      });

      map.addControl(
        new maplibre.NavigationControl({ showCompass: false }),
        "top-right"
      );
      const attributionControl = new maplibre.AttributionControl({
        compact: true,
        customAttribution: OSM_ATTRIBUTION
      });
      map.addControl(attributionControl, "bottom-right");
      map
        .getContainer()
        .querySelector(".maplibregl-ctrl-attrib.maplibregl-compact-show")
        ?.classList.remove("maplibregl-compact-show");
      attributionControlRef.current = attributionControl;
      map.on("error", () => {
        if (!styleLoaded && !disposed) {
          setMapError("Không tải được kiểu bản đồ. Vui lòng thử lại sau.");
        }
      });
      map.once("load", () => {
        if (disposed) return;
        styleLoaded = true;
        applyCleanPlannerStyle(map);
        setMapError(null);
        setMapReady(true);
      });

      mapRef.current = map;
    }

    void initializeMap();

    return () => {
      disposed = true;
      dynamicMarkersRef.current.forEach((marker) => marker.remove());
      dynamicMarkersRef.current = [];
      markersRef.current.clear();
      mapRef.current?.remove();
      mapRef.current = null;
      maplibreRef.current = null;
      attributionControlRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !mapDestinationPickActive) return;

    const choosePoint = (event: MapLayerMouseEvent) => {
      onChooseMapDestination({
        key: `map-${event.lngLat.lat.toFixed(6)}-${event.lngLat.lng.toFixed(6)}`,
        name: "Điểm đã chọn trên bản đồ",
        detail: `${event.lngLat.lat.toFixed(5)}, ${event.lngLat.lng.toFixed(5)}`,
        latitude: event.lngLat.lat,
        longitude: event.lngLat.lng,
        kind: "map"
      });
    };
    map.getCanvas().style.cursor = "crosshair";
    map.on("click", choosePoint);
    return () => {
      map.off("click", choosePoint);
      map.getCanvas().style.cursor = "";
    };
  }, [mapDestinationPickActive, mapReady, onChooseMapDestination]);

  useEffect(() => {
    const maplibre = maplibreRef.current;
    const map = mapRef.current;
    if (!mapReady || !maplibre || !map) return;

    dynamicMarkersRef.current.forEach((marker) => marker.remove());
    dynamicMarkersRef.current = [];
    markersRef.current.clear();
    [...dynamicLayerIdsRef.current].reverse().forEach((layerId) => {
      if (map.getLayer(layerId)) map.removeLayer(layerId);
    });
    dynamicLayerIdsRef.current = [];
    dynamicSourceIdsRef.current.forEach((sourceId) => {
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    });
    dynamicSourceIdsRef.current = [];
    if (attributionControlRef.current) {
      map.removeControl(attributionControlRef.current);
      attributionControlRef.current = null;
    }

    const placePopupWidth = Math.min(
      320,
      Math.max(220, map.getContainer().clientWidth - 72)
    );

    locatedPlaces.forEach((place) => {
      const isSelected = place.mapKey === selectedKey;
      const markerColor = dayColors.get(place.dayColorKey) ?? MAP_ROUTE_COLOR;
      const element = document.createElement("button");
      element.className = [
        "candidateMapMarker",
        isSelected ? "is-selected" : ""
      ]
        .filter(Boolean)
        .join(" ");
      element.type = "button";
      element.title = place.name;
      element.setAttribute("aria-label", `${place.mapOrder}. ${place.name}`);
      const pin = document.createElement("span");
      pin.style.setProperty("--marker-color", markerColor);
      const order = document.createElement("b");
      order.textContent = String(place.mapOrder);
      pin.append(order);
      element.append(pin);

      const popupContent = document.createElement("div");
      popupContent.className = "candidateMapPopup";
      const name = document.createElement("strong");
      name.textContent = `${place.mapOrder}. ${place.name}`;
      const day = document.createElement("small");
      day.textContent = place.dayLabel;
      const time = document.createElement("span");
      time.textContent = place.timeWindow;
      const address = document.createElement("span");
      address.className = "candidateMapPopupAddress";
      address.textContent = place.address || "Chưa có địa chỉ";
      popupContent.append(name, day, time, address);
      if (place.imageUrl) {
        const photo = document.createElement("img");
        photo.className = "candidateMapPopupPhoto";
        photo.alt = `Ảnh ${place.name}`;
        photo.loading = "lazy";
        photo.src = place.imageUrl;
        popupContent.append(photo);
      }
      const displayNotes = formatPlanNote(place.notes);
      if (displayNotes) {
        const description = document.createElement("p");
        description.textContent = displayNotes;
        popupContent.append(description);
      }

      const popup = new maplibre.Popup({
        anchor: "center",
        className: "candidateMapPopupShell",
        maxWidth: `${placePopupWidth}px`,
        offset: 0
      }).setDOMContent(popupContent);
      popup.on("open", () => {
        map.easeTo({
          center: [place.longitude, place.latitude],
          duration: 400
        });
      });
      const marker = new maplibre.Marker({ anchor: "bottom", element })
        .setLngLat([place.longitude, place.latitude])
        .setPopup(popup)
        .addTo(map);
      element.addEventListener("click", () => onSelect(place.mapKey));
      markersRef.current.set(place.mapKey, marker);
      dynamicMarkersRef.current.push(marker);
    });

    if (currentLocation) {
      const activeLocationRoute = routes.find(
        (route) => route.kind === "current_location"
      );
      const activeLocationMode = activeLocationRoute
        ? mapRouteMode(activeLocationRoute.mode)
        : "unknown";
      const activeLocationModeDetails = activeLocationRoute
        ? mapRouteModeDetails(activeLocationRoute.mode)
        : null;
      const accuracySourceId = "vsf-current-location-accuracy";
      const accuracyFillId = "vsf-current-location-accuracy-fill";
      const accuracyOutlineId = "vsf-current-location-accuracy-outline";
      if (currentLocation.accuracy > 0) {
        map.addSource(accuracySourceId, {
          type: "geojson",
          data: {
            type: "Feature",
            properties: {},
            geometry: {
              type: "Polygon",
              coordinates: [
                createAccuracyPolygon(
                  currentLocation.longitude,
                  currentLocation.latitude,
                  currentLocation.accuracy
                )
              ]
            }
          }
        });
        map.addLayer({
          id: accuracyFillId,
          type: "fill",
          source: accuracySourceId,
          paint: { "fill-color": MAP_ROUTE_COLOR, "fill-opacity": 0.08 }
        });
        map.addLayer({
          id: accuracyOutlineId,
          type: "line",
          source: accuracySourceId,
          paint: {
            "line-color": MAP_ROUTE_COLOR,
            "line-opacity": 0.32,
            "line-width": 1
          }
        });
        dynamicSourceIdsRef.current.push(accuracySourceId);
        dynamicLayerIdsRef.current.push(accuracyFillId, accuracyOutlineId);
      }

      const element = document.createElement("button");
      element.className = [
        "currentLocationMarker",
        activeLocationMode === "car" || activeLocationMode === "walk"
          ? `mode-${activeLocationMode}`
          : ""
      ].filter(Boolean).join(" ");
      element.type = "button";
      const locationLabel = currentLocation.label ?? "Vị trí của bạn";
      const accessibleLocationLabel = activeLocationModeDetails
        ? `${locationLabel} · ${activeLocationModeDetails.label}`
        : locationLabel;
      element.title = accessibleLocationLabel;
      element.setAttribute("aria-label", accessibleLocationLabel);
      const markerBody = document.createElement("span");
      const modeIcon = createCurrentLocationModeIcon(activeLocationMode);
      if (modeIcon) {
        markerBody.className = "has-travel-mode";
        markerBody.append(modeIcon);
      } else {
        const markerCore = document.createElement("i");
        if (typeof currentLocation.heading === "number") {
          markerBody.className = "has-heading";
          markerBody.style.setProperty(
            "--location-heading",
            `${currentLocation.heading}deg`
          );
        }
        markerBody.append(markerCore);
      }
      element.append(markerBody);
      const popupContent = document.createElement("div");
      popupContent.className = "candidateMapPopup";
      const name = document.createElement("strong");
      name.textContent = currentLocation.label ?? "Vị trí của bạn";
      popupContent.append(name);
      if (currentLocation.detail) {
        const detail = document.createElement("span");
        detail.textContent = currentLocation.detail;
        popupContent.append(detail);
      }
      const marker = new maplibre.Marker({ element })
        .setLngLat([currentLocation.longitude, currentLocation.latitude])
        .setPopup(
          new maplibre.Popup({ offset: 22 }).setDOMContent(popupContent)
        )
        .addTo(map);
      dynamicMarkersRef.current.push(marker);
    }

    if (
      selectedDirectionDestination &&
      selectedDirectionDestination.kind !== "plan"
    ) {
      const element = document.createElement("div");
      element.className = "directionDestinationMarker";
      element.setAttribute("aria-label", selectedDirectionDestination.name);
      element.innerHTML = "<span><b>B</b></span>";
      const popupContent = document.createElement("div");
      popupContent.className = "candidateMapPopup";
      const name = document.createElement("strong");
      name.textContent = selectedDirectionDestination.name;
      popupContent.append(name);
      if (selectedDirectionDestination.detail) {
        const detail = document.createElement("span");
        detail.textContent = selectedDirectionDestination.detail;
        popupContent.append(detail);
      }
      const marker = new maplibre.Marker({ anchor: "bottom", element })
        .setLngLat([
          selectedDirectionDestination.longitude,
          selectedDirectionDestination.latitude
        ])
        .setPopup(new maplibre.Popup({ offset: 18 }).setDOMContent(popupContent))
        .addTo(map);
      dynamicMarkersRef.current.push(marker);
    }

    const addTransitStopMarker = (
      coordinate: [number, number],
      label: string,
      kind: "boarding" | "alighting"
    ) => {
      const element = document.createElement("div");
      element.className = `transitStopMarker ${kind}`;
      element.setAttribute("aria-hidden", "true");
      const body = document.createElement("span");
      const dot = document.createElement("i");
      dot.setAttribute("aria-hidden", "true");
      body.append(dot, label);
      element.append(body);
      const marker = new maplibre.Marker({ element })
        .setLngLat([coordinate[1], coordinate[0]])
        .addTo(map);
      dynamicMarkersRef.current.push(marker);
    };

    const addRouteModeMarker = (
      coordinates: [number, number][],
      routeKey: string,
      routeDetails: {
        mode: string;
        fromPlace: string;
        toPlace: string;
        distanceMeters: number;
        estimatedDurationMinutes: number;
        line?: string | null;
        headsign?: string | null;
      }
    ) => {
      const midpoint = routeMidpoint(coordinates);
      if (!midpoint) return;
      const modeKind = mapRouteMode(routeDetails.mode);
      const details = mapRouteModeDetails(routeDetails.mode);
      if (!details) return;
      const element = document.createElement("button");
      element.className = [
        "mapRouteModeBadge",
        `mode-${modeKind}`,
        selectedRouteKey === routeKey ? "is-selected" : ""
      ].filter(Boolean).join(" ");
      element.type = "button";
      element.setAttribute(
        "aria-pressed",
        String(selectedRouteKey === routeKey)
      );
      element.title = `Xem chặng ${routeDetails.fromPlace} đến ${routeDetails.toPlace}`;
      element.setAttribute(
        "aria-label",
        `${details.label} từ ${routeDetails.fromPlace} đến ${routeDetails.toPlace}, ${formatRouteDuration(routeDetails.estimatedDurationMinutes)}`
      );
      const icon = document.createElement("span");
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = details.icon;
      const label = document.createElement("strong");
      label.textContent = details.label;
      element.append(icon, label);

      const popupContent = document.createElement("div");
      popupContent.className = "mapRoutePopup";
      const heading = document.createElement("strong");
      heading.textContent = details.label;
      const endpoints = document.createElement("div");
      endpoints.className = "mapRoutePopupEndpoints";
      const from = document.createElement("span");
      from.dataset.marker = "A";
      from.textContent = routeDetails.fromPlace;
      const to = document.createElement("span");
      to.dataset.marker = "B";
      to.textContent = routeDetails.toPlace;
      endpoints.append(from, to);
      const metrics = document.createElement("div");
      metrics.className = "mapRoutePopupMetrics";
      const duration = document.createElement("b");
      duration.textContent = formatRouteDuration(
        routeDetails.estimatedDurationMinutes
      );
      const distance = document.createElement("span");
      distance.textContent = formatRouteDistance(routeDetails.distanceMeters);
      metrics.append(duration, distance);
      popupContent.append(heading, endpoints, metrics);
      if (routeDetails.line || routeDetails.headsign) {
        const transitDetail = document.createElement("small");
        transitDetail.textContent = [
          routeDetails.line ? `Tuyến ${routeDetails.line}` : null,
          routeDetails.headsign ? `hướng ${routeDetails.headsign}` : null
        ]
          .filter(Boolean)
          .join(" · ");
        popupContent.append(transitDetail);
      }

      const marker = new maplibre.Marker({ anchor: "center", element })
        .setLngLat([midpoint[1], midpoint[0]])
        .setPopup(
          new maplibre.Popup({
            className: "mapRoutePopupShell",
            closeButton: true,
            maxWidth: "300px",
            offset: 24
          }).setDOMContent(popupContent)
        )
        .addTo(map);
      element.addEventListener("click", () => onSelectRoute(routeKey));
      dynamicMarkersRef.current.push(marker);
    };

    const drawableRoutes = routes.flatMap((route) => {
      const isCurrentLocationRoute = route.kind === "current_location";
      const routeColor = isCurrentLocationRoute
        ? MAP_ROUTE_COLOR
        : dayColors.get(route.dayColorKey) ?? MAP_ROUTE_COLOR;
      const transitSegments =
        route.source === "opentripplanner_transit"
          ? (route.segments ?? []).filter(
              (segment) => segment.geometryCoordinates.length >= 2
            )
          : [];
      const paths =
        transitSegments.length > 0
          ? transitSegments.map((segment) => ({
              coordinates: segment.geometryCoordinates,
              mode: segment.mode,
              fromPlace: segment.fromPlace,
              toPlace: segment.toPlace,
              distanceMeters: segment.distanceMeters,
              estimatedDurationMinutes: segment.estimatedDurationMinutes,
              line: segment.line,
              headsign: segment.headsign
            }))
          : [{
              coordinates: route.coordinates,
              mode: route.mode,
              fromPlace: route.fromPlace,
              toPlace: route.toPlace,
              distanceMeters: route.distanceMeters,
              estimatedDurationMinutes: route.estimatedDurationMinutes
            }];

      return paths
        .filter((path) => path.coordinates.length >= 2)
        .map((path, routePathIndex) => ({
          ...path,
          key: `${route.key}:${routePathIndex}`,
          route,
          routeColor
        }));
    });
    const routeInteractions: Array<{
      layerId: string;
      click: (event: MapLayerMouseEvent) => void;
      enter: () => void;
      leave: () => void;
    }> = [];
    drawableRoutes.forEach((path, pathIndex) => {
      if (path.coordinates.length < 2) return;
      const modeKind = mapRouteMode(path.mode);
      const isWalk = modeKind === "walk";
      const isTransit = modeKind === "transit";
      const isSelected = selectedRouteKey === path.route.key;
      const hasRouteSelection = Boolean(selectedRouteKey);
      const sourceId = `vsf-route-${pathIndex}`;
      const casingId = `${sourceId}-casing`;
      const lineId = `${sourceId}-line`;
      const hitAreaId = `${sourceId}-hit-area`;
      const dashArray = isWalk
        ? [0.8, 1.8]
        : path.route.verified || isTransit
          ? undefined
          : [1.5, 1.7];
      const lineColor = isWalk
        ? MAP_WALK_ROUTE_COLOR
        : isTransit
          ? MAP_TRANSIT_ROUTE_COLOR
          : path.routeColor;
      map.addSource(sourceId, {
        type: "geojson",
        data: {
          type: "Feature",
          properties: {},
          geometry: {
            type: "LineString",
            coordinates: path.coordinates.map(([latitude, longitude]) => [
              longitude,
              latitude
            ])
          }
        }
      });
      map.addLayer({
        id: casingId,
        type: "line",
        source: sourceId,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "rgba(255, 255, 255, 0.94)",
          "line-opacity": hasRouteSelection && !isSelected ? 0.42 : 1,
          "line-width": isSelected ? 13 : isWalk ? 7 : 9,
          ...(dashArray ? { "line-dasharray": dashArray } : {})
        }
      });
      map.addLayer({
        id: lineId,
        type: "line",
        source: sourceId,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": lineColor,
          "line-opacity": hasRouteSelection && !isSelected ? 0.3 : 0.96,
          "line-width": isSelected ? 8 : isWalk ? 3.5 : 5.5,
          ...(dashArray ? { "line-dasharray": dashArray } : {})
        }
      });
      map.addLayer({
        id: hitAreaId,
        type: "line",
        source: sourceId,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#000000",
          "line-opacity": 0.01,
          "line-width": 22
        }
      });
      const click = (event: MapLayerMouseEvent) => {
        event.originalEvent.stopPropagation();
        onSelectRoute(path.route.key);
      };
      const enter = () => {
        map.getCanvas().style.cursor = "pointer";
      };
      const leave = () => {
        map.getCanvas().style.cursor = "";
      };
      map.on("click", hitAreaId, click);
      map.on("mouseenter", hitAreaId, enter);
      map.on("mouseleave", hitAreaId, leave);
      routeInteractions.push({ layerId: hitAreaId, click, enter, leave });
      dynamicSourceIdsRef.current.push(sourceId);
      dynamicLayerIdsRef.current.push(casingId, lineId, hitAreaId);
      if (!isWalk && !isTransit) {
        addRouteModeMarker(path.coordinates, path.route.key, path);
      }
    });

    routes.forEach((route) => {
      const transitSegments =
        route.source === "opentripplanner_transit"
          ? (route.segments ?? []).filter(
              (segment) => segment.geometryCoordinates.length >= 2
            )
          : [];
      const busSegments = transitSegments.filter((segment) =>
        ["bus", "transit", "public"].some((token) =>
          segment.mode.toLowerCase().includes(token)
        )
      );
      const boardingPoint = busSegments[0]?.geometryCoordinates[0];
      const alightingPoint = busSegments.at(-1)?.geometryCoordinates.at(-1);
      if (boardingPoint) addTransitStopMarker(boardingPoint, "Lên xe", "boarding");
      if (alightingPoint) addTransitStopMarker(alightingPoint, "Xuống xe", "alighting");
    });

    const routingAttributions: string[] = [];
    if (routes.some((route) => route.source === "valhalla_routing")) {
      routingAttributions.push(VALHALLA_ROUTING_ATTRIBUTION);
    }
    if (routes.some((route) => route.source === "opentripplanner_transit")) {
      routingAttributions.push(OTP_ROUTING_ATTRIBUTION);
    }
    const attributionControl = new maplibre.AttributionControl({
      compact: true,
      customAttribution: [OSM_ATTRIBUTION, ...routingAttributions]
    });
    map.addControl(attributionControl, "bottom-right");
    map
      .getContainer()
      .querySelector(".maplibregl-ctrl-attrib.maplibregl-compact-show")
      ?.classList.remove("maplibregl-compact-show");
    attributionControlRef.current = attributionControl;

    const currentLocationRoutes = routes.filter(
      (route) => route.kind === "current_location"
    );
    const currentRouteSignature = currentLocationRoutes
      .map((route) =>
        [
          route.key,
          route.coordinates.length,
          route.coordinates[0]?.join(","),
          route.coordinates.at(-1)?.join(",")
        ].join(":")
      )
      .join("|");
    const shouldFrameNewRoute =
      currentLocationRoutes.length > 0 &&
      currentRouteSignature !== lastCurrentRouteSignatureRef.current;
    if (shouldFrameNewRoute) {
      const bounds = new maplibre.LngLatBounds();
      currentLocationRoutes.forEach((route) =>
        route.coordinates.forEach(([latitude, longitude]) =>
          bounds.extend([longitude, latitude])
        )
      );
      if (!bounds.isEmpty()) {
        map.fitBounds(bounds, {
          duration: 500,
          maxZoom: 15,
          padding: { bottom: 110, left: 52, right: 52, top: 72 }
        });
      }
    }
    lastCurrentRouteSignatureRef.current = currentRouteSignature;

    const signature = locatedPlaces
      .map((place) => `${place.mapKey}:${place.latitude}:${place.longitude}`)
      .join("|");
    if (!shouldFrameNewRoute && signature !== lastPlacesSignatureRef.current) {
      fitPlaces();
      lastPlacesSignatureRef.current = signature;
    }

    return () => {
      if (mapRef.current !== map) return;
      routeInteractions.forEach(({ layerId, click, enter, leave }) => {
        map.off("click", layerId, click);
        map.off("mouseenter", layerId, enter);
        map.off("mouseleave", layerId, leave);
      });
      map.getCanvas().style.cursor = "";
    };
  }, [
    currentLocation,
    dayColors,
    locatedPlaces,
    mapReady,
    onSelect,
    onSelectRoute,
    routes,
    selectedDirectionDestination,
    selectedKey,
    selectedRouteKey
  ]);

  useEffect(() => {
    if (!selectedKey || !mapReady) return;
    const marker = markersRef.current.get(selectedKey);
    const map = mapRef.current;
    if (!marker || !map) return;

    map.easeTo({ center: marker.getLngLat(), duration: 400 });
    if (!marker.getPopup()?.isOpen()) marker.togglePopup();
  }, [mapReady, selectedKey]);

  useEffect(() => {
    if (routeFocusRequest <= 0 || !selectedRouteKey || !mapReady) return;
    const maplibre = maplibreRef.current;
    const map = mapRef.current;
    const selectedRoute = routes.find(
      (route) => route.key === selectedRouteKey
    );
    if (!maplibre || !map || !selectedRoute || selectedRoute.coordinates.length < 2) {
      return;
    }
    const bounds = new maplibre.LngLatBounds();
    selectedRoute.coordinates.forEach(([latitude, longitude]) => {
      bounds.extend([longitude, latitude]);
    });
    if (bounds.isEmpty()) return;
    map.fitBounds(bounds, {
      duration: 650,
      maxZoom: 17,
      padding: { bottom: 96, left: 64, right: 64, top: 96 }
    });
  }, [mapReady, routeFocusRequest, routes, selectedRouteKey]);

  useEffect(() => {
    if (locationFocusRequest <= 0 || !currentLocation || !mapReady) return;
    focusCurrentLocation();
  }, [currentLocation, locationFocusRequest, mapReady]);

  function focusCurrentLocation() {
    const map = mapRef.current;
    if (!map || !currentLocation) return;
    const directionRoute = routesRef.current.find(
      (route) => route.kind === "current_location" && route.coordinates.length >= 2
    );
    const routeBearing = directionRoute
      ? routeForwardBearing(
          [currentLocation.latitude, currentLocation.longitude],
          directionRoute.coordinates
        )
      : null;
    const deviceHeading =
      typeof currentLocation.heading === "number" &&
      Number.isFinite(currentLocation.heading)
        ? currentLocation.heading
        : null;

    map.flyTo({
      bearing: routeBearing ?? deviceHeading ?? map.getBearing(),
      center: [currentLocation.longitude, currentLocation.latitude],
      duration: 900,
      essential: true,
      offset: [0, Math.round(map.getContainer().clientHeight * 0.18)],
      pitch: 55,
      zoom: Math.max(map.getZoom(), 17.25)
    });
  }

  function fitPlaces(includeCurrentLocation = true) {
    const maplibre = maplibreRef.current;
    const map = mapRef.current;
    if (!maplibre || !map) return;

    const coordinates: [number, number][] = locatedPlaces.map((place) => [
      place.longitude,
      place.latitude
    ]);
    if (includeCurrentLocation && currentLocation) {
      coordinates.push([currentLocation.longitude, currentLocation.latitude]);
    }
    if (coordinates.length === 0) {
      map.easeTo({
        bearing: 0,
        center: VIETNAM_CENTER,
        duration: 500,
        pitch: 0,
        zoom: 4.7
      });
      return;
    }
    if (coordinates.length === 1) {
      map.easeTo({
        bearing: 0,
        center: coordinates[0],
        duration: 500,
        pitch: 0,
        zoom: 14
      });
      return;
    }

    const bounds = coordinates.reduce(
      (result, coordinate) => result.extend(coordinate),
      new maplibre.LngLatBounds(coordinates[0], coordinates[0])
    );
    map.fitBounds(bounds, {
      bearing: 0,
      duration: 500,
      maxZoom: 15,
      padding: 52,
      pitch: 0
    });
  }

  return (
    <section
      aria-label={directionsActive ? "Bản đồ chỉ đường toàn màn hình" : "Bản đồ địa điểm đề xuất"}
      className={`plannerMap panel${directionsActive ? " isNavigationMode" : ""}`}
    >
      <div className="plannerMapCanvasWrap">
        <div className="plannerMapCanvas" ref={containerRef} />
        <div className="mapTravelControls">
          {!directionsActive && directionsSearchOpen ? (
            <div className="mapDirectionsSearchPanel" role="dialog" aria-label="Tìm đường giữa hai địa điểm">
              <div className="mapDirectionsSearchHeader">
                <strong>Tìm đường</strong>
                <button aria-label="Đóng tìm đường" onClick={onCloseDirectionsSearch} type="button">×</button>
              </div>
              <div className="mapDirectionsSearchFields">
                <div className="mapDirectionsSearchField" data-marker="A">
                  <input
                    aria-label="Điểm đi"
                    autoComplete="off"
                    onChange={(event) => onOriginQueryChange(event.target.value)}
                    placeholder="Vị trí hiện tại hoặc điểm đi"
                    type="search"
                    value={originQuery}
                  />
                  <button disabled={locationBusy} onClick={onUseCurrentOrigin} title="Dùng vị trí hiện tại" type="button">⌖</button>
                  {originSearchBusy ? <span className="mapDirectionsSearchSpinner" aria-label="Đang tìm điểm đi" /> : null}
                  {originSuggestions.length > 0 ? (
                    <div className="mapDirectionsSearchSuggestions" role="listbox">
                      {originSuggestions.map((place) => (
                        <button key={place.key} onClick={() => onChooseOrigin(place)} role="option" type="button">
                          <strong>{place.name}</strong>
                          {place.detail ? <small>{place.detail}</small> : null}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="mapDirectionsSearchField" data-marker="B">
                  <input
                    aria-label="Điểm đến"
                    autoComplete="off"
                    onChange={(event) => onDestinationQueryChange(event.target.value)}
                    placeholder="Point 1, địa điểm khác hoặc chọn trên bản đồ"
                    type="search"
                    value={destinationQuery}
                  />
                  {destinationSearchBusy ? <span className="mapDirectionsSearchSpinner" aria-label="Đang tìm điểm đến" /> : null}
                  {destinationQuery.trim().length === 0 || destinationSuggestions.length > 0 ? (
                    <div className="mapDirectionsSearchSuggestions mapDirectionsSearchSuggestions--destination" role="listbox">
                      {(destinationQuery.trim().length > 0 ? destinationSuggestions : destinationOptions).map((place) => (
                        <button key={place.key} onClick={() => onChooseDestination(place)} role="option" type="button">
                          <strong>{place.name}</strong>
                          {place.detail ? <small>{place.detail}</small> : null}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="mapDirectionsSearchActions">
                <button
                  aria-pressed={mapDestinationPickActive}
                  className={mapDestinationPickActive ? "isActive" : ""}
                  onClick={onToggleMapDestinationPick}
                  type="button"
                >
                  {mapDestinationPickActive ? "Chạm một điểm trên bản đồ…" : "Chọn điểm trên bản đồ"}
                </button>
                <button
                  className="mapDirectionsSearchSubmit"
                  disabled={!currentLocation || !selectedDirectionDestination || directionsBusy}
                  onClick={onSubmitDirections}
                  type="button"
                >
                  {directionsBusy ? "Đang tính…" : "Xem đường đi"}
                </button>
              </div>
            </div>
          ) : null}
          {!directionsActive && directionsDay != null ? (
            <div className="mapDirectionsToolbar">
              <div
                aria-label={`Lựa chọn lộ trình cho ngày ${directionsDay}`}
                className="mapDirectionsControl"
              >
                <button
                  className="mapDirectionsButton mapDirectionsButton--overview"
                  disabled={!directionsEnabled || directionsBusy}
                  onClick={onViewDayRoute}
                  type="button"
                >
                  <FitMapIcon />
                  <span>
                    <strong>{`Xem lộ trình ngày ${directionsDay}`}</strong>
                  </span>
                </button>
                <button
                  className="mapDirectionsButton mapDirectionsButton--navigate"
                  disabled={!directionsEnabled || directionsBusy}
                  onClick={() => onStartDirections()}
                  type="button"
                >
                  <DirectionsIcon />
                  <span>
                    {directionsBusy
                      ? "Đang tính…"
                      : "Tìm đường"}
                  </span>
                </button>
              </div>
            </div>
          ) : null}
          {locationMessage ? (
            <div className={`mapLocationStatusRow${directionsActive ? " isDirectionsActive" : ""}`}>
              {directionsActive && currentLocation?.kind === "device" ? (
                <button
                  aria-label="Căn bản đồ theo vị trí và hướng tuyến đường"
                  className="mapLocationButton"
                  disabled={locationBusy}
                  onClick={onLocate}
                  title="Căn theo vị trí và hướng tuyến đường"
                  type="button"
                >
                  <CompassIcon />
                  <span>{locationBusy ? "Đang định vị…" : "La bàn"}</span>
                </button>
              ) : null}
              <div
                aria-live="polite"
                className={`mapLocationStatus${locationMessage.startsWith("⏱") ? " isTimer" : ""}${directionsBusy ? " isRouting" : ""}`}
                role="status"
              >
                {directionsBusy ? <span className="mapRoutingSpinner" aria-hidden="true" /> : null}
                <span>{locationMessage}</span>
              </div>
              {directionsActive ? (
                <button
                  className="mapDirectionsCancelButton"
                  onClick={onCancelDirections}
                  type="button"
                >
                  Huỷ
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
        {mapError ? (
          <div className="mapLoadError" role="alert">
            {mapError}
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

function CompassIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="9" />
      <path d="m15.5 8.5-2.2 4.8-4.8 2.2 2.2-4.8z" />
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2" />
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
