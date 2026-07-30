"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type {
  LayerGroup,
  Map as LeafletMap,
  Marker
} from "leaflet";
import { createDayColorMap } from "@/lib/day-colors";
import type { ExplorePlace } from "@/lib/plans";

export type PlannerMapPlace = ExplorePlace & {
  mapKey: string;
  mapOrder: number;
  dayColorKey: string;
  dayLabel: string;
};

export type PlannerMapRoute = {
  key: string;
  coordinates: [number, number][];
  verified: boolean;
  source: string;
  dayColorKey: string;
};

type PlannerMapProps = {
  places: PlannerMapPlace[];
  routes: PlannerMapRoute[];
  dayColorKeys?: string[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
};

const VIETNAM_CENTER: [number, number] = [16.2, 106.2];
const HERE_ROUTING_ATTRIBUTION = "Routing &copy; HERE";

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
  dayColorKeys = [],
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
    map.attributionControl.removeAttribution(HERE_ROUTING_ATTRIBUTION);

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
      const detail = document.createElement("span");
      detail.textContent = place.address || "Địa điểm do Explorer đề xuất";
      const day = document.createElement("small");
      day.textContent = place.dayLabel;
      popup.append(name, day, detail);
      if (place.notes) {
        const description = document.createElement("p");
        description.textContent = place.notes;
        popup.append(description);
      }
      marker.bindPopup(popup);
      marker.on("click", () => onSelect(place.mapKey));
      markersRef.current.set(place.mapKey, marker);
    });

    if (routes.length > 0 && routeLayerRef.current) {
      routes.forEach((route) => {
        leaflet
          .polyline(route.coordinates, {
            color: "rgba(255, 255, 255, .92)",
            dashArray: route.verified ? undefined : "8 9",
            opacity: 1,
            weight: 8
          })
          .addTo(routeLayerRef.current!);
        leaflet
          .polyline(route.coordinates, {
            color: dayColors.get(route.dayColorKey) ?? "#167c68",
            dashArray: route.verified ? undefined : "8 9",
            lineCap: "round",
            lineJoin: "round",
            opacity: 0.94,
            weight: 4.5
          })
          .addTo(routeLayerRef.current!);
      });
    }
    if (routes.some((route) => route.source.startsWith("here_"))) {
      map.attributionControl.addAttribution(HERE_ROUTING_ATTRIBUTION);
    }

    const signature = locatedPlaces
      .map((place) => `${place.mapKey}:${place.latitude}:${place.longitude}`)
      .join("|");
    if (signature !== lastPlacesSignatureRef.current) {
      fitPlaces();
      lastPlacesSignatureRef.current = signature;
    }
  }, [dayColors, locatedPlaces, mapReady, onSelect, routes, selectedKey]);

  useEffect(() => {
    if (!selectedKey || !mapReady) return;
    const marker = markersRef.current.get(selectedKey);
    const map = mapRef.current;
    if (!marker || !map) return;

    map.panTo(marker.getLatLng(), { animate: true });
    marker.openPopup();
  }, [mapReady, selectedKey]);

  function fitPlaces() {
    const leaflet = leafletRef.current;
    const map = mapRef.current;
    if (!leaflet || !map) return;

    if (locatedPlaces.length === 0) {
      map.setView(VIETNAM_CENTER, 5);
      return;
    }
    if (locatedPlaces.length === 1) {
      map.setView(
        [locatedPlaces[0].latitude, locatedPlaces[0].longitude],
        14
      );
      return;
    }

    const bounds = leaflet.latLngBounds(
      locatedPlaces.map((place) => [place.latitude, place.longitude])
    );
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
