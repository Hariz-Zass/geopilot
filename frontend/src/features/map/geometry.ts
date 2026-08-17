import type {
  MultiPolygonGeometry,
  SiteResponse,
} from "../../lib/api/sites";

export type MapBounds = [[number, number], [number, number]];

export type SiteFeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    id: string;
    properties: {
      site_id: string;
      project_id: string;
      name: string;
      geometry_hash: string;
      geometry_revision: number;
    };
    geometry: MultiPolygonGeometry;
  }>;
};

export function geometryBounds(
  geometry: MultiPolygonGeometry,
): MapBounds {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;

  for (const polygon of geometry.coordinates) {
    for (const ring of polygon) {
      for (const position of ring) {
        const longitude = position[0];
        const latitude = position[1];

        if (
          longitude === undefined ||
          latitude === undefined ||
          !Number.isFinite(longitude) ||
          !Number.isFinite(latitude)
        ) {
          throw new Error(
            "server Site geometry contains invalid coordinates",
          );
        }

        west = Math.min(west, longitude);
        south = Math.min(south, latitude);
        east = Math.max(east, longitude);
        north = Math.max(north, latitude);
      }
    }
  }

  if (![west, south, east, north].every(Number.isFinite)) {
    throw new Error("server Site geometry is empty");
  }

  return [
    [west, south],
    [east, north],
  ];
}

export function siteFeatureCollection(
  site: SiteResponse,
): SiteFeatureCollection {
  if (!site.is_active || site.is_archived) {
    throw new Error(
      "only the server-designated active Site may be rendered as active context",
    );
  }

  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: site.id,
        properties: {
          site_id: site.id,
          project_id: site.project_id,
          name: site.name,
          geometry_hash: site.geometry_hash,
          geometry_revision: site.geometry_revision,
        },
        geometry: site.geometry,
      },
    ],
  };
}