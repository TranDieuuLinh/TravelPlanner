"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type {
  AttributionControl,
  Map as MapLibreMap,
  MapLayerMouseEvent,
  Marker
} from "maplibre-gl";
import { createDayColorMap } from "@/features/planner/lib/day-colors";
import { routeForwardBearing } from "@/features/planner/lib/map-navigation";
import { planItemNotePresentation } from "@/features/planner/lib/plan-note";
import {
  isCarMode,
  isPublicTransitMode,
  isWalkingMode
} from "@/features/planner/lib/transport-options";
import type { ExplorePlace } from "@/features/planner/api/plans";
import { PlaceReviewsModal } from "@/features/planner/components/PlaceReviewsModal";

export type PlannerMapPlace = ExplorePlace & {
  destination: string;
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
  navigationMode: string | null;
  directionsActive: boolean;
  directionsBusy: boolean;
  directionsReady: boolean;
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
const MAP_MAX_MOUSE_PITCH = 60;
const MAP_DOUBLE_CLICK_ZOOM = 18;
const MAP_CONTROL_PAN_PIXELS = 160;
const MAP_CONTROL_ROTATE_DEGREES = 30;
const MAP_KEYBOARD_ROTATE_DEGREES = 8;
const MAP_KEYBOARD_PITCH_DEGREES = 4;
const CURRENT_LOCATION_HEADING_TIP_OFFSET_PIXELS = 10;

type MapRouteMode = "walk" | "car" | "transit" | "bike" | "unknown";

function mapRouteMode(mode: string): MapRouteMode {
  const normalized = mode.toLowerCase();
  if (isWalkingMode(mode)) {
    return "walk";
  }
  if (isCarMode(mode)) {
    return "car";
  }
  if (normalized.includes("bike") || normalized.includes("motor")) {
    return "bike";
  }
  if (isPublicTransitMode(mode)) {
    return "transit";
  }
  return "unknown";
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

function hasRouteCoordinates(
  coordinates: unknown
): coordinates is [number, number][] {
  return (
    Array.isArray(coordinates) &&
    coordinates.every(
      (coordinate) =>
        Array.isArray(coordinate) &&
        coordinate.length >= 2 &&
        typeof coordinate[0] === "number" &&
        Number.isFinite(coordinate[0]) &&
        typeof coordinate[1] === "number" &&
        Number.isFinite(coordinate[1])
    )
  );
}

function browserSupportsWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    const options = {
      alpha: true,
      antialias: true,
      failIfMajorPerformanceCaveat: false,
      powerPreference: "default",
    } as WebGLContextAttributes;
    return Boolean(
      canvas.getContext("webgl2", options) ||
        canvas.getContext("webgl", options)
    );
  } catch {
    return false;
  }
}

function normalizeBearing(value: number): number {
  return ((value % 360) + 360) % 360;
}

function clampPitch(value: number): number {
  return Math.min(MAP_MAX_MOUSE_PITCH, Math.max(0, value));
}

function rotateMapBy(map: MapLibreMap, degrees: number) {
  map.easeTo({
    bearing: normalizeBearing(map.getBearing() + degrees),
    duration: 240,
    essential: true
  });
}

function pitchMapBy(map: MapLibreMap, degrees: number) {
  map.easeTo({
    duration: 120,
    essential: true,
    pitch: clampPitch(map.getPitch() + degrees)
  });
}

function panMapBy(map: MapLibreMap, x: number, y: number) {
  map.panBy([x, y], {
    duration: 240,
    essential: true
  });
}

function zoomMapClose(
  map: MapLibreMap,
  center: [number, number]
) {
  map.easeTo({
    center,
    duration: 650,
    essential: true,
    zoom: Math.max(map.getZoom(), MAP_DOUBLE_CLICK_ZOOM)
  });
}

function currentLocationMarkerOffset(heading: number | null | undefined) {
  if (typeof heading !== "number" || !Number.isFinite(heading)) return undefined;

  const radians = (heading * Math.PI) / 180;
  return [
    -Math.sin(radians) * CURRENT_LOCATION_HEADING_TIP_OFFSET_PIXELS,
    Math.cos(radians) * CURRENT_LOCATION_HEADING_TIP_OFFSET_PIXELS
  ] as [number, number];
}

function createNavigationModeIcon(
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
    body.setAttribute(
      "d",
      "m10 21 2-6-3-3 2-5 4 3 3 1M12 15l4 6M9 12l-4 3"
    );
    icon.append(head, body);
    return icon;
  }

  const roof = document.createElementNS(svgNamespace, "path");
  roof.setAttribute("d", "m5 11 2-5h10l2 5");
  const body = document.createElementNS(svgNamespace, "path");
  body.setAttribute(
    "d",
    "M4 12a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v5H4zM6 17v2m12-2v2"
  );
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
  navigationMode,
  directionsActive,
  directionsBusy,
  directionsReady,
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
  const previousDirectionsActiveRef = useRef(directionsActive);
  const handledLocationFocusRequestRef = useRef(0);
  const lastMarkerClickRef = useRef<{
    at: number;
    clientX: number;
    clientY: number;
  } | null>(null);
  const panDragRef = useRef<{
    pointerId: number;
    buttonMask: number;
    lastX: number;
    lastY: number;
  } | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [mapDragging, setMapDragging] = useState(false);
  const [reviewPlace, setReviewPlace] = useState<PlannerMapPlace | null>(null);

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
    let initAttempted = false;

    async function initializeMap() {
      if (!containerRef.current || mapRef.current || initAttempted) return;
      initAttempted = true;

      if (!browserSupportsWebGL()) {
        setMapError(
          "Trình duyệt này chưa hỗ trợ WebGL. Bạn vẫn có thể xem lịch trình trong danh sách."
        );
        return;
      }

      let maplibre: typeof import("maplibre-gl");
      try {
        maplibre = await import("maplibre-gl");
      } catch {
        if (!disposed) {
          setMapError("Không thể tải thư viện bản đồ. Vui lòng tải lại trang.");
        }
        return;
      }
      if (disposed || !containerRef.current) return;

      maplibreRef.current = maplibre;
      let map: MapLibreMap;
      try {
        map = new maplibre.Map({
          attributionControl: false,
          center: VIETNAM_CENTER,
          container: containerRef.current,
          doubleClickZoom: false,
          dragPan: true,
          dragRotate: false,
          keyboard: false,
          maxZoom: 19,
          pitchWithRotate: true,
          style: MAP_STYLE_URL,
          touchPitch: true,
          zoom: 4.7,
        });
      } catch {
        if (!disposed) {
          setMapError(
            "Không thể khởi tạo bản đồ trên trình duyệt này. Bạn vẫn có thể xem lịch trình và địa điểm trong danh sách."
          );
        }
        maplibreRef.current = null;
        return;
      }

      map.addControl(
        new maplibre.NavigationControl({ showCompass: true }),
        "top-right"
      );
      map.touchZoomRotate.enableRotation();
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
    if (!mapReady || !map) return;

    const canvas = map.getCanvas();
    const mapContainer = map.getContainer();
    mapContainer.tabIndex = 0;
    mapContainer.setAttribute(
      "aria-label",
      "Bản đồ. Nhấp đúp để phóng to gần. Dùng A hoặc D để xoay 360, W hoặc S để nghiêng, phím mũi tên để di chuyển."
    );
    map.dragPan.enable();

    const stopMousePan = (event?: PointerEvent) => {
      const drag = panDragRef.current;
      if (!drag) return;
      if (event && event.pointerId !== drag.pointerId) return;
      if (canvas.hasPointerCapture(drag.pointerId)) {
        canvas.releasePointerCapture(drag.pointerId);
      }
      panDragRef.current = null;
      setMapDragging(false);
    };

    const startMousePan = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") return;
      if (event.button !== 2) return;
      event.preventDefault();
      event.stopPropagation();
      map.stop();
      panDragRef.current = {
        pointerId: event.pointerId,
        buttonMask: event.button === 2 ? 2 : 1,
        lastX: event.clientX,
        lastY: event.clientY
      };
      canvas.setPointerCapture(event.pointerId);
      setMapDragging(true);
    };
    const panMapWithMouse = (event: PointerEvent) => {
      const drag = panDragRef.current;
      if (!drag || event.pointerId !== drag.pointerId) return;
      event.preventDefault();
      event.stopPropagation();
      if ((event.buttons & drag.buttonMask) === 0) {
        stopMousePan(event);
        return;
      }
      const movementX = event.clientX - drag.lastX;
      const movementY = event.clientY - drag.lastY;
      drag.lastX = event.clientX;
      drag.lastY = event.clientY;
      map.panBy([movementX, movementY], {
        animate: false,
        duration: 0,
        essential: true
      });
    };
    const stopMousePanByButton = (event: PointerEvent) => {
      if (event.button !== 2) return;
      stopMousePan(event);
    };
    const preventContextMenu = (event: MouseEvent) => {
      event.preventDefault();
    };
    const focusMapForKeyboard = () => {
      mapContainer.focus({ preventScroll: true });
    };
    const zoomCloseOnDoubleClick = (event: MapLayerMouseEvent) => {
      event.preventDefault();
      zoomMapClose(map, [event.lngLat.lng, event.lngLat.lat]);
    };
    const moveWithKeyboard = (event: KeyboardEvent) => {
      if (
        event.target instanceof HTMLElement &&
        ["BUTTON", "INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)
      ) {
        return;
      }

      if (event.shiftKey && event.key === "ArrowLeft") {
        event.preventDefault();
        rotateMapBy(map, -MAP_CONTROL_ROTATE_DEGREES);
        return;
      }
      if (event.shiftKey && event.key === "ArrowRight") {
        event.preventDefault();
        rotateMapBy(map, MAP_CONTROL_ROTATE_DEGREES);
        return;
      }

      const key = event.key.toLowerCase();
      if (key === "a") {
        event.preventDefault();
        rotateMapBy(map, -MAP_KEYBOARD_ROTATE_DEGREES);
      } else if (key === "d") {
        event.preventDefault();
        rotateMapBy(map, MAP_KEYBOARD_ROTATE_DEGREES);
      } else if (key === "w") {
        event.preventDefault();
        pitchMapBy(map, MAP_KEYBOARD_PITCH_DEGREES);
      } else if (key === "s") {
        event.preventDefault();
        pitchMapBy(map, -MAP_KEYBOARD_PITCH_DEGREES);
      } else if (key === "r") {
        event.preventDefault();
        map.easeTo({
          bearing: 0,
          duration: 240,
          essential: true,
          pitch: 0
        });
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        panMapBy(map, -MAP_CONTROL_PAN_PIXELS, 0);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        panMapBy(map, MAP_CONTROL_PAN_PIXELS, 0);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        panMapBy(map, 0, -MAP_CONTROL_PAN_PIXELS);
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        panMapBy(map, 0, MAP_CONTROL_PAN_PIXELS);
      }
    };

    canvas.addEventListener("pointerdown", startMousePan, { capture: true });
    canvas.addEventListener("pointerdown", focusMapForKeyboard);
    canvas.addEventListener("pointermove", panMapWithMouse);
    canvas.addEventListener("pointerup", stopMousePan);
    canvas.addEventListener("pointercancel", stopMousePan);
    canvas.addEventListener("lostpointercapture", stopMousePan);
    canvas.addEventListener("contextmenu", preventContextMenu);
    mapContainer.addEventListener("keydown", moveWithKeyboard);
    document.addEventListener("pointerup", stopMousePanByButton);
    map.on("dblclick", zoomCloseOnDoubleClick);

    return () => {
      canvas.removeEventListener("pointerdown", startMousePan, { capture: true });
      canvas.removeEventListener("pointerdown", focusMapForKeyboard);
      canvas.removeEventListener("pointermove", panMapWithMouse);
      canvas.removeEventListener("pointerup", stopMousePan);
      canvas.removeEventListener("pointercancel", stopMousePan);
      canvas.removeEventListener("lostpointercapture", stopMousePan);
      canvas.removeEventListener("contextmenu", preventContextMenu);
      mapContainer.removeEventListener("keydown", moveWithKeyboard);
      document.removeEventListener("pointerup", stopMousePanByButton);
      map.off("dblclick", zoomCloseOnDoubleClick);
      stopMousePan();
      map.dragPan.enable();
    };
  }, [mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;

    const compassButton = map
      .getContainer()
      .querySelector<HTMLButtonElement>(".maplibregl-ctrl-compass");
    if (!compassButton) return;

    const defaultTitle = compassButton.getAttribute("title");
    const defaultAriaLabel = compassButton.getAttribute("aria-label");
    compassButton.title = "Định vị, phóng to và chuyển sang góc nhìn POV";
    compassButton.setAttribute(
      "aria-label",
      "Định vị vị trí hiện tại, phóng to và chuyển bản đồ sang góc nhìn POV"
    );
    compassButton.disabled = locationBusy;

    const locateFromCompass = (event: MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      onLocate();
    };

    compassButton.addEventListener("click", locateFromCompass, {
      capture: true
    });
    return () => {
      compassButton.removeEventListener("click", locateFromCompass, {
        capture: true
      });
      compassButton.disabled = false;
      compassButton.title = defaultTitle ?? "Reset bearing to north";
      if (defaultAriaLabel) {
        compassButton.setAttribute("aria-label", defaultAriaLabel);
      } else {
        compassButton.removeAttribute("aria-label");
      }
    };
  }, [locationBusy, mapReady, onLocate]);

  useEffect(() => {
    const maplibre = maplibreRef.current;
    const map = mapRef.current;
    if (
      !mapReady ||
      !maplibre ||
      !map ||
      mapRef.current !== map ||
      !map.isStyleLoaded()
    ) return;

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
      element.title = `${place.name}. Nhấp để xem, nhấp đúp để phóng to`;
      element.setAttribute("aria-label", `${place.mapOrder}. ${place.name}`);
      const pin = document.createElement("span");
      pin.style.setProperty("--marker-color", markerColor);
      const order = document.createElement("b");
      order.textContent = String(place.mapOrder);
      pin.append(order);
      element.append(pin);

      const popupContent = document.createElement("article");
      popupContent.className = "candidateMapPopup candidateMapPopup--place";
      const header = document.createElement("header");
      header.className = "candidateMapPopupHeader";
      const destination = document.createElement("span");
      destination.className = "candidateMapPopupDestination";
      destination.textContent = place.destination;
      const name = document.createElement("h3");
      name.className = "candidateMapPopupTitle";
      name.textContent = `${place.mapOrder}. ${place.name}`;
      const meta = document.createElement("div");
      meta.className = "candidateMapPopupMeta";
      if (place.rating != null) {
        const canShowStoredReviews = Boolean(place.placeId);
        const rating = document.createElement(
          canShowStoredReviews ? "button" : place.sourceLink ? "a" : "span"
        );
        rating.className = "candidateMapPopupRating";
        rating.textContent = `★ ${place.rating.toFixed(1)}${
          place.reviewCount ? ` · ${formatCompactCount(place.reviewCount)} lượt đánh giá` : ""
        }`;
        if (canShowStoredReviews && rating instanceof HTMLButtonElement) {
          rating.type = "button";
          rating.title = "Đọc đánh giá";
          rating.setAttribute("aria-label", `Đọc đánh giá của ${place.name}`);
          rating.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            setReviewPlace(place);
          });
        } else if (place.sourceLink && rating instanceof HTMLAnchorElement) {
          rating.href = place.sourceLink;
          rating.target = "_blank";
          rating.rel = "noreferrer";
          rating.title = "Mở đánh giá trên Google Maps";
        }
        meta.append(rating);
      }
      header.append(destination, name, meta);

      const details = document.createElement("div");
      details.className = "candidateMapPopupDetails";
      const openingHours = formatOpeningHoursForDay(place.openingHours, place.dayLabel);
      const openingHoursSchedule = formatOpeningHoursSchedule(place.openingHours);
      const activeOpeningDay = dayIndexFromVietnameseLabel(place.dayLabel);
      const hours = document.createElement("details");
      hours.className = "candidateMapPopupHours";
      const hoursSummary = document.createElement("summary");
      const hoursLabel = document.createElement("span");
      hoursLabel.className = "candidateMapPopupHoursLabel";
      hoursLabel.textContent = "Giờ mở cửa";
      const hoursValue = document.createElement("strong");
      hoursValue.textContent = openingHours ?? "Chưa có dữ liệu";
      const hoursChevron = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "svg"
      );
      hoursChevron.classList.add("candidateMapPopupHoursChevron");
      hoursChevron.setAttribute("aria-hidden", "true");
      hoursChevron.setAttribute("viewBox", "0 0 24 24");
      const hoursChevronPath = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "path"
      );
      hoursChevronPath.setAttribute("d", "m7 10 5 5 5-5");
      hoursChevron.append(hoursChevronPath);
      hoursSummary.append(hoursLabel, hoursValue, hoursChevron);
      hours.append(hoursSummary);
      if (openingHoursSchedule.length > 0) {
        const schedule = document.createElement("div");
        schedule.className = "candidateMapPopupHoursSchedule";
        openingHoursSchedule.forEach((entry) => {
          const row = document.createElement("div");
          if (entry.dayOfWeek === activeOpeningDay) {
            row.className = "isActiveDay";
          }
          const label = document.createElement("span");
          label.textContent = entry.label;
          const value = document.createElement("strong");
          value.textContent = entry.value;
          row.append(label, value);
          schedule.append(row);
        });
        hours.append(schedule);
      } else {
        hoursSummary.setAttribute("aria-disabled", "true");
        hours.addEventListener("toggle", () => {
          if (hours.open) hours.open = false;
        });
      }
      const address = document.createElement("span");
      address.className = "candidateMapPopupAddress";
      address.textContent = place.address || "Chưa có địa chỉ";
      details.append(address, hours);

      if (place.imageUrl) {
        const media = document.createElement("div");
        media.className = "candidateMapPopupMedia";
        const photo = document.createElement("img");
        photo.className = "candidateMapPopupPhoto";
        photo.alt = `Ảnh ${place.name}`;
        photo.loading = "lazy";
        photo.src = place.imageUrl;
        photo.addEventListener("error", () => media.remove());
        media.append(photo);
        popupContent.append(media);
      }
      popupContent.append(header, details);

      const notePresentation = planItemNotePresentation(place);
      if (notePresentation.sourceNotes.length || notePresentation.personalText) {
        const notes = document.createElement("section");
        notes.className = "candidateMapPopupNotes";
        for (const sourceNote of notePresentation.sourceNotes) {
          const notesLabel = document.createElement("small");
          notesLabel.textContent = sourceNote.label;
          const description = document.createElement("p");
          description.textContent = sourceNote.text;
          notes.append(notesLabel, description);
        }
        if (notePresentation.personalText) {
          const personalLabel = document.createElement("small");
          personalLabel.textContent = "Ghi chú của bạn";
          const personal = document.createElement("p");
          personal.textContent = notePresentation.personalText;
          notes.append(personalLabel, personal);
        }
        popupContent.append(notes);
      }

      const popup = new maplibre.Popup({
        // Keep the selected marker visible below the card instead of covering it.
        anchor: "bottom",
        className: "candidateMapPopupShell",
        maxWidth: `${placePopupWidth}px`,
        // Leave room for the marker itself (the popup tip is intentionally hidden).
        offset: 38
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
      element.addEventListener("click", (event) => {
        const previousClick = lastMarkerClickRef.current;
        const isDoubleClick = Boolean(
          previousClick &&
          event.timeStamp - previousClick.at <= 400 &&
          Math.hypot(
            event.clientX - previousClick.clientX,
            event.clientY - previousClick.clientY
          ) <= 8
        );
        lastMarkerClickRef.current = isDoubleClick
          ? null
          : {
              at: event.timeStamp,
              clientX: event.clientX,
              clientY: event.clientY
            };
        onSelect(place.mapKey);
        if (isDoubleClick) {
          event.preventDefault();
          event.stopPropagation();
          zoomMapClose(map, [place.longitude, place.latitude]);
        }
      });
      markersRef.current.set(place.mapKey, marker);
      dynamicMarkersRef.current.push(marker);
    });

    if (currentLocation) {
      const activeNavigationMode = directionsActive
        ? mapRouteMode(navigationMode ?? "")
        : "unknown";
      const navigationModeLabel = activeNavigationMode === "car"
        ? "Ô tô"
        : activeNavigationMode === "walk"
          ? "Đi bộ"
          : null;
      const accuracySourceId = "travelplanner-current-location-accuracy";
      const accuracyFillId = "travelplanner-current-location-accuracy-fill";
      const accuracyOutlineId = "travelplanner-current-location-accuracy-outline";
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
        navigationModeLabel ? `mode-${activeNavigationMode}` : ""
      ].filter(Boolean).join(" ");
      element.type = "button";
      const locationLabel = currentLocation.label ?? "Vị trí của bạn";
      const accessibleLocationLabel = navigationModeLabel
        ? `${locationLabel} · ${navigationModeLabel}`
        : locationLabel;
      element.title = accessibleLocationLabel;
      element.setAttribute("aria-label", accessibleLocationLabel);
      const markerBody = document.createElement("span");
      const modeIcon = createNavigationModeIcon(activeNavigationMode);
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
      const marker = new maplibre.Marker({
        element,
        offset: modeIcon
          ? undefined
          : currentLocationMarkerOffset(currentLocation.heading)
      })
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

    const drawableRoutes = routes.flatMap((route) => {
      const isCurrentLocationRoute = route.kind === "current_location";
      const routeColor = isCurrentLocationRoute
        ? MAP_ROUTE_COLOR
        : dayColors.get(route.dayColorKey) ?? MAP_ROUTE_COLOR;
      const transitSegments =
        route.source === "opentripplanner_transit"
          ? (route.segments ?? []).filter(
              (segment) =>
                hasRouteCoordinates(segment.geometryCoordinates) &&
                segment.geometryCoordinates.length >= 2
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
        .filter(
          (path) =>
            hasRouteCoordinates(path.coordinates) &&
            path.coordinates.length >= 2
        )
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
    const orderedDrawableRoutes = [...drawableRoutes].sort((left, right) => {
      const leftSelected = selectedRouteKey === left.route.key;
      const rightSelected = selectedRouteKey === right.route.key;
      if (leftSelected === rightSelected) return 0;
      return leftSelected ? 1 : -1;
    });
    orderedDrawableRoutes.forEach((path, pathIndex) => {
      if (path.coordinates.length < 2) return;
      const modeKind = mapRouteMode(path.mode);
      const isWalk = modeKind === "walk";
      const isTransit = modeKind === "transit";
      const isSelected = selectedRouteKey === path.route.key;
      const hasRouteSelection = Boolean(selectedRouteKey);
      const sourceId = `travelplanner-route-${pathIndex}`;
      const casingId = `${sourceId}-casing`;
      const lineId = `${sourceId}-line`;
      const hitAreaId = `${sourceId}-hit-area`;
      const dashArray = isWalk
        ? [0.35, 1.75]
        : undefined;
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
          "line-color": isSelected
            ? "rgba(255, 255, 255, 1)"
            : "rgba(255, 255, 255, 0.94)",
          "line-opacity": hasRouteSelection && !isSelected ? 0.62 : 1,
          "line-width": isSelected ? (isWalk ? 10 : 13) : isWalk ? 7 : 9,
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
          "line-opacity": hasRouteSelection && !isSelected ? 0.46 : 0.98,
          "line-width": isSelected ? (isWalk ? 5.5 : 7.5) : isWalk ? 3.5 : 5.5,
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
    directionsActive,
    locatedPlaces,
    mapReady,
    navigationMode,
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
    if (!directionsSearchOpen || !directionsReady || !mapReady) return;
    const maplibre = maplibreRef.current;
    const map = mapRef.current;
    const previewRoute = routes.find((route) => route.kind === "current_location");
    if (!maplibre || !map || !previewRoute || previewRoute.coordinates.length < 2) {
      return;
    }

    const bounds = new maplibre.LngLatBounds();
    previewRoute.coordinates.forEach(([latitude, longitude]) => {
      bounds.extend([longitude, latitude]);
    });
    if (currentLocation) {
      bounds.extend([currentLocation.longitude, currentLocation.latitude]);
    }
    if (selectedDirectionDestination) {
      bounds.extend([
        selectedDirectionDestination.longitude,
        selectedDirectionDestination.latitude
      ]);
    }
    if (bounds.isEmpty()) return;
    map.fitBounds(bounds, {
      bearing: 0,
      duration: 550,
      maxZoom: 15,
      padding: { bottom: 250, left: 56, right: 56, top: 76 },
      pitch: 0
    });
  }, [
    currentLocation,
    directionsReady,
    directionsSearchOpen,
    mapReady,
    routes,
    selectedDirectionDestination
  ]);

  useEffect(() => {
    if (locationFocusRequest === 0) {
      handledLocationFocusRequestRef.current = 0;
      return;
    }
    if (
      locationFocusRequest <= handledLocationFocusRequestRef.current ||
      !currentLocation ||
      !mapReady
    ) return;
    handledLocationFocusRequestRef.current = locationFocusRequest;
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
      bearing: deviceHeading ?? routeBearing ?? map.getBearing(),
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

  useEffect(() => {
    const wasActive = previousDirectionsActiveRef.current;
    previousDirectionsActiveRef.current = directionsActive;
    if (!mapReady || !wasActive || directionsActive || directionsSearchOpen) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      const maplibre = maplibreRef.current;
      const map = mapRef.current;
      const previewRoute = routes.find((route) => route.kind === "current_location");
      if (
        directionsReady &&
        maplibre &&
        map &&
        previewRoute &&
        previewRoute.coordinates.length >= 2
      ) {
        const bounds = new maplibre.LngLatBounds();
        previewRoute.coordinates.forEach(([latitude, longitude]) => {
          bounds.extend([longitude, latitude]);
        });
        if (currentLocation) {
          bounds.extend([currentLocation.longitude, currentLocation.latitude]);
        }
        if (selectedDirectionDestination) {
          bounds.extend([
            selectedDirectionDestination.longitude,
            selectedDirectionDestination.latitude
          ]);
        }
        map.fitBounds(bounds, {
          bearing: 0,
          duration: 550,
          maxZoom: 15,
          padding: { bottom: 250, left: 56, right: 56, top: 76 },
          pitch: 0
        });
        return;
      }
      fitPlaces(false);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [
    currentLocation,
    directionsActive,
    directionsReady,
    directionsSearchOpen,
    locatedPlaces,
    mapReady,
    routes,
    selectedDirectionDestination
  ]);

  const hasDeviceLocation = currentLocation?.kind === "device";
  const showLocationControls =
    Boolean(locationMessage) || directionsActive;
  const activeNavigationRoute = directionsActive
    ? routes.find((route) => route.kind === "current_location") ?? null
    : null;
  const directionPreviewRoute = routes.find(
    (route) => route.kind === "current_location"
  ) ?? null;
  const hasDirectionEndpoints = Boolean(
    currentLocation && selectedDirectionDestination
  );
  const canStartDirections =
    directionsSearchOpen && hasDirectionEndpoints && directionsReady && !directionsBusy;

  return (
    <section
      aria-label={directionsActive ? "Bản đồ chỉ đường toàn màn hình" : "Bản đồ địa điểm đề xuất"}
      className={[
        "plannerMap panel",
        directionsActive ? "isNavigationMode" : "",
        mapDragging ? "isDragging" : ""
      ].filter(Boolean).join(" ")}
    >
      <div className="plannerMapCanvasWrap">
        <div className="plannerMapCanvas" ref={containerRef} />
        <div className="mapTravelControls">
          {!directionsActive && directionsSearchOpen ? (
            <div className="mapDirectionsSearchPanel" role="dialog" aria-label="Tìm đường giữa hai địa điểm">
              <div className="mapDirectionsSearchHeader">
                <div>
                  <span className="mapDirectionsSearchEyebrow">ĐƯỜNG ĐI NHANH</span>
                  <strong>Tìm đường</strong>
                </div>
                <button aria-label="Đóng tìm đường" className="mapDirectionsClose" onClick={onCloseDirectionsSearch} type="button">
                  <CloseIcon />
                </button>
              </div>
              <div className="mapDirectionsSearchFields">
                <div className="mapDirectionsSearchField" data-marker="A">
                  <label htmlFor="directions-origin">Điểm đi</label>
                  <input
                    id="directions-origin"
                    autoComplete="off"
                    onChange={(event) => onOriginQueryChange(event.target.value)}
                    placeholder="Vị trí hiện tại hoặc tìm địa điểm"
                    type="search"
                    value={originQuery}
                  />
                  <button aria-label="Dùng vị trí hiện tại" className="mapDirectionsUseLocation" disabled={locationBusy} onClick={onUseCurrentOrigin} title="Dùng vị trí hiện tại" type="button">
                    <CompassIcon />
                  </button>
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
                  <label className="mapDirectionsDestinationLabel" htmlFor="directions-destination">
                    <span>Điểm đến</span>
                    {directionPreviewRoute ? (
                      <span className="mapRouteSummaryBadge mapRouteSummaryBadge--inForm" aria-label={`Khoảng cách ${formatMapDistance(directionPreviewRoute.distanceMeters)}`}>
                        {formatMapDistance(directionPreviewRoute.distanceMeters)}
                      </span>
                    ) : null}
                  </label>
                  <input
                    id="directions-destination"
                    autoComplete="off"
                    onChange={(event) => onDestinationQueryChange(event.target.value)}
                    placeholder="Tìm điểm đến trong lịch trình"
                    type="search"
                    value={destinationQuery}
                  />
                  {destinationSearchBusy ? <span className="mapDirectionsSearchSpinner" aria-label="Đang tìm điểm đến" /> : null}
                  {!selectedDirectionDestination && (destinationQuery.trim().length === 0 || destinationSuggestions.length > 0) ? (
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
              <button
                className="mapDirectionsFormSubmit"
                disabled={!canStartDirections}
                onClick={onSubmitDirections}
                type="button"
              >
                <DirectionsIcon />
                <span>{directionsBusy ? "Đang tìm tuyến…" : "Bắt đầu"}</span>
              </button>
            </div>
          ) : null}
          {!directionsActive && !directionsSearchOpen && directionsDay != null ? (
            <div className="mapDirectionsToolbar">
              <div
                aria-label={`Chỉ đường cho ngày ${directionsDay}`}
                className="mapDirectionsControl mapDirectionsControl--navigateOnly"
              >
                <button
                  className="mapDirectionsButton mapDirectionsButton--navigate"
                  disabled={!directionsEnabled || directionsBusy}
                  onClick={() => onStartDirections()}
                  type="button"
                >
                  <DirectionsIcon />
                  <span>
                    {directionsBusy ? "Đang tìm tuyến…" : "Tìm đường"}
                  </span>
                </button>
              </div>
            </div>
          ) : null}
          {showLocationControls ? (
            directionsActive ? (
              <div className="mapNavigationSheet" role="region" aria-label="Điều khiển dẫn đường">
                <span className="mapNavigationSheetHandle" aria-hidden="true" />
                <div className="mapNavigationSheetMain">
                  <span className="mapNavigationSheetEyebrow">ĐANG DẪN ĐƯỜNG</span>
                  <strong aria-live="polite">
                    {directionsBusy ? "Đang tìm tuyến…" : locationMessage ?? "Đang chuẩn bị tuyến…"}
                  </strong>
                  <small>
                    {activeNavigationRoute
                      ? `${mapNavigationModeLabel(activeNavigationRoute.mode)} · ${formatMapDistance(activeNavigationRoute.distanceMeters)}`
                      : "Tuyến đến điểm trong lịch trình"}
                  </small>
                </div>
                <div className="mapNavigationSheetActions">
                  {hasDeviceLocation ? (
                    <button
                      aria-label="Căn bản đồ theo vị trí và hướng tuyến đường"
                      className="mapLocationButton"
                      disabled={locationBusy}
                      onClick={onLocate}
                      title="Căn theo vị trí và hướng tuyến đường"
                      type="button"
                    >
                      <CompassIcon />
                      <span>{locationBusy ? "Đang định vị…" : "Căn bản đồ"}</span>
                    </button>
                  ) : null}
                  <button
                    className="mapDirectionsCancelButton"
                    onClick={onCancelDirections}
                    type="button"
                  >
                    <CloseIcon />
                    <span>Thoát</span>
                  </button>
                </div>
              </div>
            ) : (
              <div className="mapLocationStatusRow">
                {locationMessage && !locationMessage.startsWith("⏱") ? (
                  <div
                    aria-live="polite"
                    className={`mapLocationStatus${locationMessage.startsWith("⏱") ? " isTimer" : ""}${directionsBusy ? " isRouting" : ""}`}
                    role="status"
                  >
                    {directionsBusy ? <span className="mapRoutingSpinner" aria-hidden="true" /> : null}
                    <span>{locationMessage}</span>
                  </div>
                ) : null}
              </div>
            )
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
      {reviewPlace?.placeId ? (
        <PlaceReviewsModal
          onClose={() => setReviewPlace(null)}
          place={{
            placeId: reviewPlace.placeId,
            name: reviewPlace.name,
            address: reviewPlace.address,
            rating: reviewPlace.rating,
            reviewCount: reviewPlace.reviewCount,
            sourceLink: reviewPlace.sourceLink,
          }}
        />
      ) : null}
    </section>
  );
}

function formatCompactCount(value: number): string {
  if (value >= 1_000_000) return `${Number((value / 1_000_000).toFixed(1))}M`;
  if (value >= 1000) return `${Number((value / 1000).toFixed(1))}N`;
  return String(value);
}

function formatMapDistance(distanceMeters: number): string {
  if (!Number.isFinite(distanceMeters) || distanceMeters <= 0) return "Khoảng cách đang cập nhật";
  return distanceMeters >= 1000
    ? `${(distanceMeters / 1000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} km`
    : `${Math.round(distanceMeters).toLocaleString("vi-VN")} m`;
}

function mapNavigationModeLabel(mode: string): string {
  if (isWalkingMode(mode)) return "Đi bộ";
  if (isPublicTransitMode(mode)) return "Phương tiện công cộng";
  if (isCarMode(mode)) return "Ô tô";
  return "Tuyến đường";
}

function formatOpeningHoursForDay(
  openingHours: ExplorePlace["openingHours"],
  dayLabel: string
): string | null {
  if (!openingHours?.length) return null;
  const dayIndex = dayIndexFromVietnameseLabel(dayLabel);
  const entry = openingHours.find((candidate) => (
    dayIndex != null && openingHourDayNumber(candidate) === dayIndex
  ));
  if (!entry) return formatOpeningHoursSummary(openingHours);
  if (entry?.is24Hours) return "Mở cửa 24 giờ";
  return formatOpeningHourSlots(entry);
}

function formatOpeningHoursSchedule(
  openingHours: ExplorePlace["openingHours"]
): Array<{ dayOfWeek: number | null; label: string; value: string }> {
  if (!openingHours?.length) return [];

  return openingHours
    .map((entry) => {
      const dayOfWeek = openingHourDayNumber(entry);
      const value = entry.is24Hours
        ? "Mở cửa 24 giờ"
        : formatOpeningHourSlots(entry);
      if (!value) return null;
      return {
        dayOfWeek,
        label:
          (dayOfWeek != null && FULL_OPENING_HOUR_DAY_LABELS[dayOfWeek]) ||
          entry.dayName?.trim() ||
          "Ngày khác",
        value
      };
    })
    .filter(
      (
        entry
      ): entry is { dayOfWeek: number | null; label: string; value: string } =>
        entry != null
    )
    .sort(
      (left, right) =>
        (left.dayOfWeek ?? Number.MAX_SAFE_INTEGER) -
        (right.dayOfWeek ?? Number.MAX_SAFE_INTEGER)
    );
}

const FULL_OPENING_HOUR_DAY_LABELS: Record<number, string> = {
  1: "Thứ Hai",
  2: "Thứ Ba",
  3: "Thứ Tư",
  4: "Thứ Năm",
  5: "Thứ Sáu",
  6: "Thứ Bảy",
  7: "Chủ Nhật"
};

function formatOpeningHoursSummary(
  openingHours: NonNullable<ExplorePlace["openingHours"]>
): string | null {
  const normalized = openingHours
    .map((entry) => ({
      label: openingHourDayLabel(entry.dayName),
      value: entry.is24Hours ? "Mở cửa 24 giờ" : formatOpeningHourSlots(entry)
    }))
    .filter((entry): entry is { label: string | null; value: string } => Boolean(entry.value));
  if (normalized.length === 0) return null;
  const uniqueValues = new Set(normalized.map((entry) => entry.value));
  if (uniqueValues.size === 1) return normalized[0].value;
  return normalized
    .slice(0, 3)
    .map((entry) => entry.label ? `${entry.label}: ${entry.value}` : entry.value)
    .join("; ");
}

function formatOpeningHourSlots(
  entry: NonNullable<ExplorePlace["openingHours"]>[number]
): string | null {
  const rawSlots = entry.rawTimeSlots?.trim();
  if (rawSlots) return rawSlots;

  const openTime = entry.openTime?.trim();
  const closeTime = entry.closeTime?.trim();
  if (openTime && closeTime) return `${openTime}–${closeTime}`;
  return openTime || closeTime || null;
}

function openingHourDayLabel(value?: string | null): string | null {
  const normalized = value?.trim().toLowerCase();
  if (!normalized) return null;
  const labels: Record<string, string> = {
    monday: "T2",
    tuesday: "T3",
    wednesday: "T4",
    thursday: "T5",
    friday: "T6",
    saturday: "T7",
    sunday: "CN"
  };
  return labels[normalized] ?? value?.trim() ?? null;
}

function openingHourDayNumber(
  entry: NonNullable<ExplorePlace["openingHours"]>[number]
): number | null {
  if (
    entry.dayOfWeek != null &&
    entry.dayOfWeek >= 1 &&
    entry.dayOfWeek <= 7
  ) {
    return entry.dayOfWeek;
  }

  const normalized = entry.dayName
    ?.trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
  if (!normalized) return null;
  const dayNumbers: Record<string, number> = {
    monday: 1,
    "thu hai": 1,
    "thu 2": 1,
    t2: 1,
    tuesday: 2,
    "thu ba": 2,
    "thu 3": 2,
    t3: 2,
    wednesday: 3,
    "thu tu": 3,
    "thu 4": 3,
    t4: 3,
    thursday: 4,
    "thu nam": 4,
    "thu 5": 4,
    t5: 4,
    friday: 5,
    "thu sau": 5,
    "thu 6": 5,
    t6: 5,
    saturday: 6,
    "thu bay": 6,
    "thu 7": 6,
    t7: 6,
    sunday: 7,
    "chu nhat": 7,
    cn: 7
  };
  return dayNumbers[normalized] ?? null;
}

function dayIndexFromVietnameseLabel(value: string): number | null {
  const normalized = value.toLowerCase();
  if (normalized.includes("thứ hai")) return 1;
  if (normalized.includes("thứ ba")) return 2;
  if (normalized.includes("thứ tư")) return 3;
  if (normalized.includes("thứ năm")) return 4;
  if (normalized.includes("thứ sáu")) return 5;
  if (normalized.includes("thứ bảy")) return 6;
  if (normalized.includes("chủ nhật")) return 7;
  const dateMatch = value.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (dateMatch) {
    const date = new Date(
      Number(dateMatch[3]),
      Number(dateMatch[2]) - 1,
      Number(dateMatch[1])
    );
    const jsDay = date.getDay();
    return jsDay === 0 ? 7 : jsDay;
  }
  const currentDay = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Ho_Chi_Minh",
    weekday: "long"
  }).format(new Date());
  return openingHourDayNumber({ dayName: currentDay });
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

function CloseIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="m7 7 10 10M17 7 7 17" />
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
