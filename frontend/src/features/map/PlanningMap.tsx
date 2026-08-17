import { useEffect, useRef, useState } from "react";

import {
  Map as MapLibreMap,
  NavigationControl,
  setWorkerUrl,
  type GeoJSONSource,
  type StyleSpecification,
} from "maplibre-gl";

import mapLibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";

import type { SiteResponse } from "../../lib/api/sites";
import {
  geometryBounds,
  siteFeatureCollection,
} from "./geometry";

setWorkerUrl(mapLibreWorkerUrl);

const SOURCE_ID = "active-site";
const FILL_LAYER_ID = "active-site-fill";
const LINE_LAYER_ID = "active-site-outline";

const BASEMAP_STYLE: StyleSpecification = {
  version: 8,

  sources: {
    osm: {
      type: "raster",
      tiles: [
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: "© OpenStreetMap contributors",
    },
  },

  layers: [
    {
      id: "osm-basemap",
      type: "raster",
      source: "osm",
      minzoom: 0,
      maxzoom: 22,
    },
  ],
};

export type PlanningMapProps = {
  site: SiteResponse;
};

type MapState =
  | "initializing"
  | "ready"
  | "degraded";

function applySite(
  map: MapLibreMap,
  site: SiteResponse,
): void {
  const data = siteFeatureCollection(site);

  const existing = map.getSource(
    SOURCE_ID,
  ) as GeoJSONSource | undefined;

  if (existing) {
    existing.setData(data);
  } else {
    map.addSource(SOURCE_ID, {
      type: "geojson",
      data,
    });

    map.addLayer({
      id: FILL_LAYER_ID,
      type: "fill",
      source: SOURCE_ID,
      paint: {
        "fill-color": "#2563eb",
        "fill-opacity": 0.18,
      },
    });

    map.addLayer({
      id: LINE_LAYER_ID,
      type: "line",
      source: SOURCE_ID,
      paint: {
        "line-color": "#1d4ed8",
        "line-width": 3,
      },
    });
  }

  map.fitBounds(
    geometryBounds(site.geometry),
    {
      padding: 56,
      maxZoom: 17,
      duration: 0,
    },
  );
}

export function PlanningMap({
  site,
}: PlanningMapProps) {
  const containerRef =
    useRef<HTMLDivElement | null>(null);

  const mapRef =
    useRef<MapLibreMap | null>(null);

  const [state, setState] =
    useState<MapState>("initializing");

  const [message, setMessage] =
    useState<string>();

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    let disposed = false;
    let siteApplied = false;
    let map: MapLibreMap;

    try {
      map = new MapLibreMap({
        container: containerRef.current,

        style: BASEMAP_STYLE,

        center: [101.7, 3.0],
        zoom: 8,

        attributionControl: {},
      });

      mapRef.current = map;

      map.addControl(
        new NavigationControl({
          showCompass: true,
        }),
        "top-right",
      );

      map.once("load", () => {
        if (disposed) {
          return;
        }

        try {
          applySite(map, site);

          siteApplied = true;

          setState("ready");
        } catch (error) {
          setState("degraded");

          setMessage(
            error instanceof Error
              ? error.message
              : "Active Site geometry could not be displayed.",
          );
        }
      });

      map.on("error", (event) => {
        if (
          disposed ||
          siteApplied
        ) {
          return;
        }

        setState("degraded");

        setMessage(
          event.error?.message ||
            "The map renderer or basemap is unavailable.",
        );
      });
    } catch (error) {
      setState("degraded");

      setMessage(
        error instanceof Error
          ? error.message
          : "The map renderer is unavailable.",
      );

      return;
    }

    return () => {
      disposed = true;

      map.remove();

      mapRef.current = null;
    };
  }, [
    site.id,
    site.geometry_hash,
    site.geometry_revision,
  ]);

  return (
    <section
      className="planning-map-shell"
      aria-label="Active Site map"
    >
      <div className="map-context-bar">
        <div>
          <span className="map-context-label">
            Active Site
          </span>

          <strong>{site.name}</strong>
        </div>

        <div
          className="map-provenance"
          aria-label="Geometry identity"
        >
          <span>
            Revision{" "}
            {site.geometry_revision}
          </span>

          <code>
            {site.geometry_hash.slice(
              0,
              12,
            )}
            ...
          </code>
        </div>
      </div>

      {state === "initializing" && (
        <p
          className="map-status"
          role="status"
        >
          Initializing map...
        </p>
      )}

      {state === "degraded" && (
        <div
          className="map-degraded"
          role="alert"
        >
          <strong>
            Map unavailable
          </strong>

          <p>
            {message ??
              "The active Site remains available as server evidence, but map rendering is degraded."}
          </p>
        </div>
      )}

      <div
        ref={containerRef}
        className="planning-map"
        data-map-state={state}
      />
    </section>
  );
}