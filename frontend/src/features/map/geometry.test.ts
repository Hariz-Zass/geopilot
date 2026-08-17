import { describe, expect, it } from "vitest";

import type { SiteResponse } from "../../lib/api/sites";
import {
  geometryBounds,
  siteFeatureCollection,
} from "./geometry";

const site: SiteResponse = {
  id: "site-1",
  project_id: "project-1",
  name: "Target Site",
  geometry: {
    type: "MultiPolygon",
    coordinates: [
      [
        [
          [101.7, 3.0],
          [101.72, 3.0],
          [101.72, 3.02],
          [101.7, 3.02],
          [101.7, 3.0],
        ],
      ],
    ],
  },
  geometry_hash: "a".repeat(64),
  geometry_revision: 3,
  is_active: true,
  is_archived: false,
  created_at: "2026-08-14T00:00:00Z",
  updated_at: "2026-08-14T00:00:00Z",
};

describe("planning map geometry", () => {
  it("derives viewport bounds without changing server geometry", () => {
    expect(geometryBounds(site.geometry)).toEqual([
      [101.7, 3.0],
      [101.72, 3.02],
    ]);
  });

  it("preserves exact server geometry identity in the map feature", () => {
    const collection = siteFeatureCollection(site);
    const feature = collection.features[0];

    expect(feature).toBeDefined();

    if (!feature) {
      throw new Error("expected active Site feature");
    }

    expect(feature.geometry).toBe(site.geometry);
    expect(feature.properties.geometry_hash).toBe(
      site.geometry_hash,
    );
    expect(feature.properties.geometry_revision).toBe(3);
  });

  it("refuses inactive server context", () => {
    expect(() =>
      siteFeatureCollection({
        ...site,
        is_active: false,
      }),
    ).toThrow(/server-designated active Site/);
  });
});