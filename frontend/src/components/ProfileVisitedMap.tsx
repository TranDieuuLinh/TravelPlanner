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

type ProvinceProperties = {
  code: string;
  name: string;
  fullName: string;
};

type ProvinceGeometry = Polygon | MultiPolygon;
type ProvinceFeature = Feature<ProvinceGeometry, ProvinceProperties>;
type ProvinceCollection = FeatureCollection<ProvinceGeometry, ProvinceProperties>;

export type ProvinceFootprint = {
  code: string;
  name: string;
  status: "unvisited" | "planned" | "visited";
  places: VisitedPlace[];
  visitCount: number;
};

type ProfileVisitedMapProps = {
  places: VisitedPlace[];
  plannedProvinceNames?: string[];
  selectedProvinceCode: string | null;
  onSelect: (code: string) => void;
  onSummariesChange?: (summaries: ProvinceFootprint[]) => void;
};

const BOUNDARY_URL = "/data/vietnam-provinces.geojson";
const VIETNAM_BOUNDS: [[number, number], [number, number]] = [
  [8.15, 102.1],
  [23.45, 110.2],
];
const EMPTY_NAMES: string[] = [];

const LEGACY_PROVINCE_NAMES: Record<string, string> = {
  "ha giang": "tuyen quang",
  "yen bai": "lao cai",
  "bac kan": "thai nguyen",
  "vinh phuc": "phu tho",
  "hoa binh": "phu tho",
  "bac giang": "bac ninh",
  "thai binh": "hung yen",
  "hai duong": "hai phong",
  "ha nam": "ninh binh",
  "nam dinh": "ninh binh",
  "quang binh": "quang tri",
  "quang nam": "da nang",
  "kon tum": "quang ngai",
  "binh dinh": "gia lai",
  "ninh thuan": "khanh hoa",
  "phu yen": "dak lak",
  "dak nong": "lam dong",
  "binh thuan": "lam dong",
  "binh phuoc": "dong nai",
  "binh duong": "ho chi minh",
  "ba ria - vung tau": "ho chi minh",
  "ba ria vung tau": "ho chi minh",
  "long an": "tay ninh",
  "tien giang": "dong thap",
  "ben tre": "vinh long",
  "tra vinh": "vinh long",
  "kien giang": "an giang",
  "soc trang": "can tho",
  "hau giang": "can tho",
  "bac lieu": "ca mau",
};

function normalizeProvinceName(value: string) {
  const normalized = value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/^(tinh|thanh pho|tp)\s+/i, "")
    .trim()
    .toLowerCase();
  return LEGACY_PROVINCE_NAMES[normalized] ?? normalized;
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

function pointIsInFeature(point: Position, feature: ProvinceFeature) {
  const polygons =
    feature.geometry.type === "Polygon"
      ? [feature.geometry.coordinates]
      : feature.geometry.coordinates;

  return polygons.some((polygon) => {
    const [outerRing, ...holes] = polygon;
    return pointIsInRing(point, outerRing) && !holes.some((hole) => pointIsInRing(point, hole));
  });
}

function getProvinceStyle(summary: ProvinceFootprint, selected: boolean) {
  if (summary.status === "visited") {
    const fillColor =
      summary.visitCount >= 3 ? "#0f5d50" : summary.visitCount === 2 ? "#21836e" : "#38a58c";
    return {
      className: `footprintProvince is-visited${selected ? " is-selected" : ""}`,
      color: selected ? "#fff7df" : "#ffffff",
      dashArray: undefined,
      fillColor,
      fillOpacity: 0.94,
      opacity: 1,
      weight: selected ? 2.4 : 1.1,
    };
  }
  if (summary.status === "planned") {
    return {
      className: `footprintProvince is-planned${selected ? " is-selected" : ""}`,
      color: "#167c68",
      dashArray: "5 5",
      fillColor: "#eef3f1",
      fillOpacity: 0.88,
      opacity: 1,
      weight: selected ? 2.8 : 1.8,
    };
  }
  return {
    className: `footprintProvince is-unvisited${selected ? " is-selected" : ""}`,
    color: selected ? "#167c68" : "#ffffff",
    dashArray: undefined,
    fillColor: selected ? "#dce7e3" : "#e8edeb",
    fillOpacity: 0.92,
    opacity: 1,
    weight: selected ? 2.4 : 1,
  };
}

function makeTooltip(summary: ProvinceFootprint) {
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
  plannedProvinceNames = EMPTY_NAMES,
  selectedProvinceCode,
  onSelect,
  onSummariesChange,
}: ProfileVisitedMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const provinceLayerRef = useRef<LeafletGeoJSON | null>(null);
  const fittedRef = useRef(false);
  const [boundaries, setBoundaries] = useState<ProvinceCollection | null>(null);
  const [mapError, setMapError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch(BOUNDARY_URL, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("BOUNDARY_LOAD_FAILED");
        return response.json() as Promise<ProvinceCollection>;
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
    const plannedNames = new Set(plannedProvinceNames.map(normalizeProvinceName));
    return boundaries.features.map((feature) => {
      const provincePlaces = places.filter((place) =>
        pointIsInFeature([place.longitude, place.latitude], feature),
      );
      const visitCount = new Set(provincePlaces.map((place) => place.visitedAt)).size;
      const status: ProvinceFootprint["status"] =
        provincePlaces.length > 0
          ? "visited"
          : plannedNames.has(normalizeProvinceName(feature.properties.name))
            ? "planned"
            : "unvisited";
      return {
        code: feature.properties.code,
        name: feature.properties.name,
        status,
        places: provincePlaces,
        visitCount,
      };
    });
  }, [boundaries, places, plannedProvinceNames]);

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
      mapRef.current.fitBounds(VIETNAM_BOUNDS, { animate: false, padding: [18, 18] });
    }

    void createMap();
    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
      provinceLayerRef.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function drawProvinces() {
      if (!boundaries || summaries.length === 0) return;
      const map = mapRef.current;
      if (!map) {
        window.setTimeout(() => {
          if (!cancelled) void drawProvinces();
        }, 40);
        return;
      }

      const leaflet = await import("leaflet");
      if (cancelled) return;
      provinceLayerRef.current?.removeFrom(map);

      const summaryByCode = new Map(summaries.map((summary) => [summary.code, summary]));
      const layer = leaflet.geoJSON(boundaries, {
        style: (feature) => {
          const code = (feature?.properties as ProvinceProperties | undefined)?.code ?? "";
          const summary = summaryByCode.get(code);
          return summary
            ? getProvinceStyle(summary, code === selectedProvinceCode)
            : getProvinceStyle(
                { code, name: "", status: "unvisited", places: [], visitCount: 0 },
                false,
              );
        },
        onEachFeature: (feature, featureLayer) => {
          const code = (feature.properties as ProvinceProperties).code;
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
            mouseout: () => path.setStyle(getProvinceStyle(summary, code === selectedProvinceCode)),
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

      provinceLayerRef.current = layer;
      if (!fittedRef.current) {
        map.fitBounds(layer.getBounds(), { animate: false, padding: [18, 18] });
        fittedRef.current = true;
      }
    }

    void drawProvinces();
    return () => {
      cancelled = true;
    };
  }, [boundaries, onSelect, selectedProvinceCode, summaries]);

  return (
    <div className="profileMapShell">
      <div
        aria-label="Bản đồ Dấu chân Việt Nam theo 34 tỉnh, thành"
        className="profileMapCanvas"
        ref={containerRef}
        role="img"
      />
      {!boundaries && !mapError ? <span className="profileMapStatus">Đang mở bản đồ...</span> : null}
      {mapError ? <span className="profileMapStatus is-error">Không thể tải ranh giới bản đồ.</span> : null}
    </div>
  );
}
