"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type {
  Feature,
  FeatureCollection,
  MultiPolygon,
  Polygon,
  Position,
} from "geojson";
import type {
  GeoJSON as LeafletGeoJSON,
  Map as LeafletMap,
  Path,
} from "leaflet";
import type { VisitedPlace } from "@/types/profile";

type CountryProperties = {
  iso_a3: string;
  name: string;
};

type CountryGeometry = Polygon | MultiPolygon;
type CountryFeature = Feature<CountryGeometry, CountryProperties>;
type CountryCollection = FeatureCollection<CountryGeometry, CountryProperties>;

export type CountryFootprint = {
  code: string;
  name: string;
  status: "unvisited" | "planned" | "visited";
  places: VisitedPlace[];
  visitCount: number;
};

type ProfileVisitedMapProps = {
  places: VisitedPlace[];
  plannedCountryNames?: string[];
  selectedCountryCode: string | null;
  onSelect: (code: string) => void;
  onSummariesChange?: (summaries: CountryFootprint[]) => void;
};

const BOUNDARY_URL = "/data/world-countries.geojson";
const WORLD_BOUNDS: [[number, number], [number, number]] = [
  [-58, -180],
  [84, 180],
];
const EMPTY_NAMES: string[] = [];

function normalizeCountryName(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function pointIsInRing([longitude, latitude]: Position, ring: Position[]) {
  if (
    !Number.isFinite(longitude) ||
    !Number.isFinite(latitude) ||
    ring.length < 3 ||
    !ring.every(
      (position) =>
        Array.isArray(position) &&
        Number.isFinite(position[0]) &&
        Number.isFinite(position[1]),
    )
  ) {
    return false;
  }

  let inside = false;
  for (let index = 0, previous = ring.length - 1; index < ring.length; previous = index++) {
    const [currentLongitude, currentLatitude] = ring[index];
    const [previousLongitude, previousLatitude] = ring[previous];
    const intersects =
      currentLatitude > latitude !== previousLatitude > latitude &&
      longitude <
        ((previousLongitude - currentLongitude) * (latitude - currentLatitude)) /
          (previousLatitude - currentLatitude) +
          currentLongitude;
    if (intersects) inside = !inside;
  }
  return inside;
}

function pointIsInFeature(point: Position, feature: CountryFeature) {
  const polygons =
    feature.geometry.type === "Polygon"
      ? [feature.geometry.coordinates]
      : feature.geometry.coordinates;

  return polygons.some((polygon) => {
    const [outerRing, ...holes] = polygon;
    return pointIsInRing(point, outerRing) && !holes.some((hole) => pointIsInRing(point, hole));
  });
}

function getCountryStyle(summary: CountryFootprint, selected: boolean) {
  if (summary.status === "visited") {
    const fillColor =
      summary.visitCount >= 3 ? "#0f5d50" : summary.visitCount === 2 ? "#21836e" : "#38a58c";
    return {
      className: `footprintCountry is-visited${selected ? " is-selected" : ""}`,
      color: selected ? "#ffffff" : "#ffffff",
      dashArray: undefined,
      fillColor,
      fillOpacity: 0.94,
      opacity: 1,
      weight: selected ? 2.4 : 1.1,
    };
  }
  if (summary.status === "planned") {
    return {
      className: `footprintCountry is-planned${selected ? " is-selected" : ""}`,
      color: "#167c68",
      dashArray: "5 5",
      fillColor: "#eef3f1",
      fillOpacity: 0.88,
      opacity: 1,
      weight: selected ? 2.8 : 1.8,
    };
  }
  return {
    className: `footprintCountry is-unvisited${selected ? " is-selected" : ""}`,
    color: selected ? "#167c68" : "#ffffff",
    dashArray: undefined,
    fillColor: selected ? "#dce7e3" : "#e8edeb",
    fillOpacity: 0.92,
    opacity: 1,
    weight: selected ? 2.4 : 1,
  };
}

function makeTooltip(summary: CountryFootprint) {
  const tooltip = document.createElement("div");
  tooltip.className = "footprintTooltip";
  const title = document.createElement("strong");
  title.textContent = summary.name;
  const detail = document.createElement("span");
  detail.textContent =
    summary.status === "visited"
      ? `${summary.visitCount} lần ghé · ${summary.places.length} địa điểm`
      : summary.status === "planned"
        ? "Đang lên kế hoạch"
        : "Chưa có dấu chân";
  tooltip.append(title, detail);
  return tooltip;
}

export function ProfileVisitedMap({
  places,
  plannedCountryNames = EMPTY_NAMES,
  selectedCountryCode,
  onSelect,
  onSummariesChange,
}: ProfileVisitedMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const countryLayerRef = useRef<LeafletGeoJSON | null>(null);
  const fittedRef = useRef(false);
  const [boundaries, setBoundaries] = useState<CountryCollection | null>(null);
  const [mapError, setMapError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch(BOUNDARY_URL, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("BOUNDARY_LOAD_FAILED");
        return response.json() as Promise<CountryCollection>;
      })
      .then(setBoundaries)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setMapError(true);
      });
    return () => controller.abort();
  }, []);

  const summaries = useMemo(() => {
    if (!boundaries) return [];
    const plannedNames = new Set(plannedCountryNames.map(normalizeCountryName));
    return boundaries.features.map((feature) => {
      const countryPlaces = places.filter((place) =>
        pointIsInFeature([place.longitude, place.latitude], feature),
      );
      const visitCount = new Set(countryPlaces.map((place) => place.visitedAt)).size;
      const status: CountryFootprint["status"] =
        countryPlaces.length > 0
          ? "visited"
          : plannedNames.has(normalizeCountryName(feature.properties.name))
            ? "planned"
            : "unvisited";
      return {
        code: feature.properties.iso_a3,
        name: feature.properties.name,
        status,
        places: countryPlaces,
        visitCount,
      };
    });
  }, [boundaries, places, plannedCountryNames]);

  useEffect(() => {
    onSummariesChange?.(summaries);
  }, [onSummariesChange, summaries]);

  useEffect(() => {
    let disposed = false;

    async function createMap() {
      if (!containerRef.current || mapRef.current) return;
      const leaflet = await import("leaflet");
      if (disposed || !containerRef.current) return;
      mapRef.current = leaflet.map(containerRef.current, {
        attributionControl: false,
        boxZoom: false,
        doubleClickZoom: false,
        dragging: false,
        keyboard: false,
        scrollWheelZoom: false,
        touchZoom: false,
        zoomControl: false,
      });
      mapRef.current.fitBounds(WORLD_BOUNDS, { animate: false, padding: [24, 24] });
    }

    void createMap();
    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
      countryLayerRef.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function drawCountries() {
      if (!boundaries || summaries.length === 0) return;
      const map = mapRef.current;
      if (!map) {
        window.setTimeout(() => {
          if (!cancelled) void drawCountries();
        }, 40);
        return;
      }

      const leaflet = await import("leaflet");
      if (cancelled) return;
      countryLayerRef.current?.removeFrom(map);

      const summaryByCode = new Map(summaries.map((summary) => [summary.code, summary]));
      const layer = leaflet.geoJSON(boundaries, {
        style: (feature) => {
          const code = (feature?.properties as CountryProperties | undefined)?.iso_a3 ?? "";
          const summary = summaryByCode.get(code);
          return summary
            ? getCountryStyle(summary, code === selectedCountryCode)
            : getCountryStyle(
                { code, name: "", status: "unvisited", places: [], visitCount: 0 },
                false,
              );
        },
        onEachFeature: (feature, featureLayer) => {
          const code = (feature.properties as CountryProperties).iso_a3;
          const summary = summaryByCode.get(code);
          if (!summary) return;
          const path = featureLayer as Path;
          path.bindTooltip(makeTooltip(summary), {
            className: "footprintLeafletTooltip",
            direction: "top",
            opacity: 1,
            sticky: true,
          });
          path.on({
            click: () => onSelect(code),
            mouseout: () => path.setStyle(getCountryStyle(summary, code === selectedCountryCode)),
            mouseover: () => {
              path.bringToFront();
              path.setStyle({
                color: "#fff8e7",
                fillOpacity: 1,
                weight: 2.8,
              });
            },
          });
        },
      }).addTo(map);

      countryLayerRef.current = layer;
      if (!fittedRef.current) {
        map.fitBounds(layer.getBounds(), { animate: false, padding: [18, 18] });
        fittedRef.current = true;
      }
    }

    void drawCountries();
    return () => {
      cancelled = true;
    };
  }, [boundaries, onSelect, selectedCountryCode, summaries]);

  return (
    <div className="profileMapShell">
      <div
        aria-label="Bản đồ thế giới hiển thị các quốc gia đã ghé thăm"
        className="profileMapCanvas"
        ref={containerRef}
        role="img"
      />
      {!boundaries && !mapError ? <span className="profileMapStatus">Đang mở bản đồ...</span> : null}
      {mapError ? <span className="profileMapStatus is-error">Không thể tải ranh giới bản đồ.</span> : null}
    </div>
  );
}
