from __future__ import annotations

import argparse
import json
import uuid

from sqlalchemy import select, text

from app.db import get_session_factory
from app.models.project import Project
from app.models.user import User
from app.schemas.gis_feature import GISFeatureCollectionRequest
from app.services.gis_features import list_gis_features, delete_gis_feature
from app.services.gis_layers import delete_gis_layer
from app.services.isolation import SiteState
from app.services.planning_spatial_evidence import (
    PlanningSpatialEvidenceImportRequest,
    import_planning_spatial_evidence,
)
from app.services.site_applicability import resolve_site_applicability


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synthetic, cleanup-safe end-to-end acceptance fixture for Planning Spatial Evidence V1."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--site-id", required=True)
    args = parser.parse_args()

    project_id = uuid.UUID(args.project_id)
    site_id = uuid.UUID(args.site_id)

    SessionFactory = get_session_factory()
    with SessionFactory() as session:
        project = session.scalar(select(Project).where(Project.id == project_id))
        if project is None:
            raise SystemExit("PROJECT_NOT_FOUND")
        if project.is_archived:
            raise SystemExit("PROJECT_ARCHIVED")

        owner = session.scalar(select(User).where(User.id == project.owner_id))
        if owner is None:
            raise SystemExit("OWNER_NOT_FOUND")

        row = session.execute(
            text(
                """
                SELECT
                    s.id,
                    s.project_id,
                    s.is_active,
                    s.is_archived,
                    ST_AsGeoJSON(s.geometry)::json AS geometry
                FROM sites s
                WHERE s.id = :site_id
                  AND s.project_id = :project_id
                """
            ),
            {"site_id": site_id, "project_id": project_id},
        ).mappings().one_or_none()

        if row is None:
            raise SystemExit("SITE_NOT_FOUND")
        if row["is_archived"]:
            raise SystemExit("SITE_ARCHIVED")

        geometry = row["geometry"]
        if geometry["type"] not in {"Polygon", "MultiPolygon"}:
            raise SystemExit(f"UNSUPPORTED_SITE_GEOMETRY_{geometry['type']}")

        fixture = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "synthetic-site-overlap-1",
                    "properties": {
                        "fixture": True,
                        "fixture_kind": "planning_spatial_evidence_acceptance",
                        "classification": "SYNTHETIC_ACCEPTANCE_ONLY",
                    },
                    "geometry": geometry,
                }
            ],
        }

        request = PlanningSpatialEvidenceImportRequest(
            layer_name="SYNTHETIC TEST — Planning Spatial Evidence Acceptance",
            description=(
                "Temporary synthetic acceptance fixture generated from the selected Site geometry. "
                "Not authoritative planning evidence and must not persist after this test."
            ),
            applicability_role="land_use",
            authority="GeoPilot QA Fixture",
            jurisdiction="TEST_ONLY",
            source_title="Synthetic Site-Overlap Acceptance Fixture",
            source_kind="upload",
            source_name="synthetic_site_overlap_acceptance.geojson",
            source_crs="EPSG:4326",
            provenance_extra={
                "source_status": "synthetic_test",
                "authoritative": False,
                "test_only": True,
                "do_not_use_for_planning_conclusion": True,
            },
            geojson=fixture,
        )

        layer_id = None
        try:
            result = import_planning_spatial_evidence(
                session,
                owner=owner,
                project_id=project_id,
                request=request,
            )
            layer_id = result.layer.id

            matches, limitations = resolve_site_applicability(
                session,
                owner=owner,
                project_id=project_id,
                site_id=site_id,
                site_state=SiteState.AVAILABLE,
            )

            fixture_matches = [m for m in matches if m.layer_id == layer_id]

            print("=" * 88)
            print("PLANNING SPATIAL EVIDENCE ACCEPTANCE FIXTURE")
            print("=" * 88)
            print("project_id=", project_id)
            print("site_id=", site_id)
            print("layer_id=", layer_id)
            print("feature_count=", result.feature_count)
            print("checksum_sha256=", result.checksum_sha256)
            print("fixture_match_count=", len(fixture_matches))
            print("limitations=", limitations)

            if len(fixture_matches) != 1:
                raise RuntimeError(
                    f"Expected exactly 1 fixture applicability match, got {len(fixture_matches)}"
                )

            match = fixture_matches[0]
            print("applicability_role=", match.applicability_role)
            print("site_overlap_percent=", match.site_overlap_percent)
            print("intersection_area_sqm=", match.intersection_area_sqm)
            print("site_area_sqm=", match.site_area_sqm)
            print("properties=", json.dumps(match.properties, ensure_ascii=False))

            if match.applicability_role != "land_use":
                raise RuntimeError("Unexpected applicability role.")
            if match.site_overlap_percent < 99.99:
                raise RuntimeError(
                    f"Synthetic site-overlap fixture expected ~100% overlap, got {match.site_overlap_percent}"
                )
            if not match.properties.get("fixture"):
                raise RuntimeError("Fixture marker missing from returned evidence.")

            print("acceptance_result=PASS")
            return 0
        finally:
            if layer_id is not None:
                # Explicit cleanup: feature(s) first, then layer.
                try:
                    features = list_gis_features(
                        session,
                        owner=owner,
                        project_id=project_id,
                        layer_id=layer_id,
                        include_archived=True,
                    )
                    for feature in features:
                        delete_gis_feature(
                            session,
                            owner=owner,
                            project_id=project_id,
                            layer_id=layer_id,
                            feature_id=feature.id,
                        )
                    delete_gis_layer(
                        session,
                        owner=owner,
                        project_id=project_id,
                        layer_id=layer_id,
                    )
                    print("cleanup=PASS")
                except Exception as cleanup_exc:
                    print("cleanup=FAIL", type(cleanup_exc).__name__, str(cleanup_exc))
                    raise


if __name__ == "__main__":
    raise SystemExit(main())
