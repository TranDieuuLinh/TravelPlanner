import type { Map as MapLibreMap } from "maplibre-gl";
import type { PlannerMapPlace } from "@/features/planner/components/PlannerMap";
import {
  isCarMode,
  isPublicTransitMode,
  isWalkingMode,
} from "@/features/planner/lib/transport-options";

export const VIETNAM_CENTER: [number, number] = [106.2, 16.2];
// The bright style contains numeric vector-tile filters that are evaluated
// against nullable OpenMapTiles properties and produce noisy MapLibre worker
// errors ("Expected value to be of type number, but found null"). Positron
// uses the same OpenFreeMap source without those unsafe filters.
export const DEFAULT_MAP_STYLE = "https://tiles.openfreemap.org/styles/positron";
export const MAP_STYLE_URL =
  process.env.NEXT_PUBLIC_PLANNER_MAP_STYLE_URL ?? DEFAULT_MAP_STYLE;
export const MAP_LAND_COLOR = "#f6f5f5";
export const MAP_WATER_COLOR = "#8fdaed";
export const MAP_WATER_LINE_COLOR = "#64bed3";
export const MAP_PARK_COLOR = "#d3f8e1";
export const MAP_BUILDING_COLOR = "#eeeeee";
export const MAP_BOUNDARY_COLOR = "#cbd8e0";
export const MAP_RAIL_COLOR = "#aab8c0";
export const MAP_ROAD_COLOR = "#ffffff";
export const MAP_TEXT_COLOR = "#45545c";
export const MAP_ROUTE_COLOR = "#075fa7";
export const MAP_WALK_ROUTE_COLOR = "#697a80";
export const MAP_TRANSIT_ROUTE_COLOR = "#167c68";
export const OSM_ATTRIBUTION =
  '<a href="https://www.openstreetmap.org/copyright" title="OpenStreetMap contributors and copyright">© OpenStreetMap</a>';
export const VALHALLA_ROUTING_ATTRIBUTION =
  '<a href="https://valhalla.github.io/valhalla/">Valhalla routing</a>';
export const OTP_ROUTING_ATTRIBUTION =
  'Transit by <a href="https://www.opentripplanner.org/">OpenTripPlanner</a>';
export const MAP_MAX_MOUSE_PITCH = 60;
export const MAP_DOUBLE_CLICK_ZOOM = 18;
export const MAP_CONTROL_PAN_PIXELS = 160;
export const MAP_CONTROL_ROTATE_DEGREES = 30;
export const MAP_KEYBOARD_ROTATE_DEGREES = 8;
export const MAP_KEYBOARD_PITCH_DEGREES = 4;
export const CURRENT_LOCATION_HEADING_TIP_OFFSET_PIXELS = 10;

export type MapRouteMode = "walk" | "car" | "transit" | "bike" | "unknown";

export function mapRouteMode(mode: string): MapRouteMode {
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

export function hasCoordinates(
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

export function hasRouteCoordinates(
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

export function browserSupportsWebGL(): boolean {
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

export function normalizeBearing(value: number): number {
  return ((value % 360) + 360) % 360;
}

export function clampPitch(value: number): number {
  return Math.min(MAP_MAX_MOUSE_PITCH, Math.max(0, value));
}

export function rotateMapBy(map: MapLibreMap, degrees: number) {
  map.easeTo({
    bearing: normalizeBearing(map.getBearing() + degrees),
    duration: 240,
    essential: true
  });
}

export function pitchMapBy(map: MapLibreMap, degrees: number) {
  map.easeTo({
    duration: 120,
    essential: true,
    pitch: clampPitch(map.getPitch() + degrees)
  });
}

export function panMapBy(map: MapLibreMap, x: number, y: number) {
  map.panBy([x, y], {
    duration: 240,
    essential: true
  });
}

export function zoomMapClose(
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

export function currentLocationMarkerOffset(heading: number | null | undefined) {
  if (typeof heading !== "number" || !Number.isFinite(heading)) return undefined;

  const radians = (heading * Math.PI) / 180;
  return [
    -Math.sin(radians) * CURRENT_LOCATION_HEADING_TIP_OFFSET_PIXELS,
    Math.cos(radians) * CURRENT_LOCATION_HEADING_TIP_OFFSET_PIXELS
  ] as [number, number];
}

export function createNavigationModeIcon(
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

export function applyCleanPlannerStyle(map: MapLibreMap) {
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

export function createAccuracyPolygon(
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
