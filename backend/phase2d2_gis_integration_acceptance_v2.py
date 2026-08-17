from __future__ import annotations

import asyncio
import io
import json
import pathlib
import shutil
import subprocess
import tempfile
import uuid

from fastapi import UploadFile
from sqlalchemy import func, select

from app.db import get_session_factory
from app.models.gis_feature import GISFeature
from app.models.gis_layer import GISLayer
from app.models.project import Project
from app.models.site import Site
from app.models.user import User
from app.services.gis_analysis import (
    calculate_feature_overlap,
    calculate_site_area,
    find_nearest_features,
)
from app.services.site_applicability import resolve_site_applicability
from app.services.track_b_smart_import_all import (
    ImportAllRequest,
    execute_persistent_import_all,
)

SITE_NAME = "PHASE2D2 GIS INTEGRATION ACCEPTANCE"
SOURCE_REF = "phase2d2://temporary-acceptance"
LOGICAL_NAME = "phase2d2_land_use:PHASE2D2_LAND_USE"

SITE_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [101.7020, 3.0010],
        [101.7100, 3.0010],
        [101.7100, 3.0050],
        [101.7020, 3.0050],
        [101.7020, 3.0010],
    ]],
}

FEATURE_COLLECTION = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": "phase2d2-a",
            "properties": {
                "fixture_key": "phase2d2-a",
                "land_use": "Residential",
                "acceptance_fixture": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [101.7000, 3.0000],
                    [101.7060, 3.0000],
                    [101.7060, 3.0060],
                    [101.7000, 3.0060],
                    [101.7000, 3.0000],
                ]],
            },
        },
        {
            "type": "Feature",
            "id": "phase2d2-b",
            "properties": {
                "fixture_key": "phase2d2-b",
                "land_use": "Commercial",
                "acceptance_fixture": True,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [101.7060, 3.0000],
                    [101.7120, 3.0000],
                    [101.7120, 3.0060],
                    [101.7060, 3.0060],
                    [101.7060, 3.0000],
                ]],
            },
        },
    ],
}


def counts(session):
    return {
        "sites": session.scalar(select(func.count()).select_from(Site)),
        "layers": session.scalar(select(func.count()).select_from(GISLayer)),
        "features": session.scalar(select(func.count()).select_from(GISFeature)),
    }


def build_gpkg() -> tuple[pathlib.Path, pathlib.Path]:
    root = pathlib.Path(tempfile.mkdtemp(prefix="phase2d2_gis_"))
    geojson_path = root / "phase2d2_land_use.geojson"
    gpkg_path = root / "phase2d2_land_use.gpkg"

    geojson_path.write_text(
        json.dumps(FEATURE_COLLECTION),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "ogr2ogr",
            "-f",
            "GPKG",
            str(gpkg_path),
            str(geojson_path),
            "-nln",
            "PHASE2D2_LAND_USE",
        ],
        text=True,
        capture_output=True,
    )

    print("ogr2ogr_exit =", result.returncode)
    if result.stdout.strip():
        print("ogr2ogr_stdout =", result.stdout.strip())
    if result.stderr.strip():
        print("ogr2ogr_stderr =", result.stderr.strip())

    if result.returncode != 0 or not gpkg_path.exists():
        raise RuntimeError("Unable to build Phase 2D.2 GeoPackage fixture.")

    return root, gpkg_path


async def main():
    session = get_session_factory()()

    created_site_id: uuid.UUID | None = None
    created_layer_ids: list[uuid.UUID] = []
    fixture_root: pathlib.Path | None = None
    baseline = None

    try:
        print("========================================")
        print("PHASE 2D.2 GIS INTEGRATION ACCEPTANCE V2")
        print("GPKG SMART ORGANIZER PATH")
        print("========================================")

        project = session.scalar(
            select(Project)
            .where(Project.is_archived.is_(False))
            .order_by(Project.created_at.asc())
        )
        if project is None:
            raise RuntimeError("No non-archived project found.")

        owner = session.get(User, project.owner_id)
        if owner is None:
            raise RuntimeError("Project owner not found.")

        print("owner_id =", owner.id)
        print("project_id =", project.id)

        baseline = counts(session)
        print("")
        print("BEFORE =", baseline)

        if baseline["layers"] != 0 or baseline["features"] != 0:
            raise RuntimeError(
                "Baseline GIS is not empty. STOP to avoid touching non-acceptance GIS."
            )

        fixture_root, gpkg_path = build_gpkg()

        with gpkg_path.open("rb") as handle:
            upload = UploadFile(
                filename="phase2d2_land_use.gpkg",
                file=handle,
            )

            request = ImportAllRequest(
                site_name=SITE_NAME,
                site_geometry=SITE_GEOMETRY,
                site_source_ref=SOURCE_REF,
                user_confirmed=True,
                role_assignments={
                    LOGICAL_NAME: "land_use",
                },
                allow_invalid_geometry_skip=False,
                execute_persistent=True,
            )

            result = await execute_persistent_import_all(
                session,
                owner=owner,
                project_id=project.id,
                files=[upload],
                request=request,
            )

        print("")
        print("IMPORT_RESULT =", result)

        if result.get("status") != "committed":
            raise RuntimeError(
                f"Smart Organizer import did not commit: {result}"
            )

        created_site_id = uuid.UUID(result["site_id"])
        created_layer_ids = [
            uuid.UUID(item["layer_id"])
            for item in result.get("imported_layers", [])
            if item.get("layer_created")
        ]

        imported_layers = result.get("imported_layers", [])
        if len(imported_layers) != 1:
            raise RuntimeError(
                f"Expected one imported layer, got {len(imported_layers)}."
            )

        layer_id = uuid.UUID(imported_layers[0]["layer_id"])

        features = list(
            session.scalars(
                select(GISFeature)
                .where(
                    GISFeature.project_id == project.id,
                    GISFeature.layer_id == layer_id,
                    GISFeature.is_archived.is_(False),
                )
                .order_by(GISFeature.created_at.asc(), GISFeature.id.asc())
            )
        )

        if len(features) != 2:
            raise RuntimeError(
                f"Expected 2 imported GIS features, got {len(features)}."
            )

        fixture_keys = {
            (feature.properties or {}).get("fixture_key")
            for feature in features
        }
        if fixture_keys != {"phase2d2-a", "phase2d2-b"}:
            raise RuntimeError(
                f"Unexpected imported fixture identities: {fixture_keys}"
            )

        print("")
        print("NATIVE_GIS_READ = PASS")
        print("layer_id =", layer_id)
        print("feature_count =", len(features))

        applicability, limitations = resolve_site_applicability(
            session,
            owner=owner,
            project_id=project.id,
            site_id=created_site_id,
        )

        print("")
        print("APPLICABILITY_MATCHES =", len(applicability))
        print("APPLICABILITY_LIMITATIONS =", limitations)

        if len(applicability) != 2:
            raise RuntimeError(
                f"Expected 2 site applicability matches, got {len(applicability)}."
            )

        if any(
            item.applicability_role != "land_use"
            for item in applicability
        ):
            raise RuntimeError("Unexpected applicability role.")

        print("SITE_APPLICABILITY = PASS")

        area = calculate_site_area(
            session,
            owner=owner,
            project_id=project.id,
            site_id=created_site_id,
        )

        print("")
        print("SITE_AREA_HECTARES =", area.area_hectares)

        if area.area_hectares <= 0:
            raise RuntimeError("Invalid site area.")

        print("GIS_SITE_AREA = PASS")

        overlap_results = []
        for feature in features:
            overlap = calculate_feature_overlap(
                session,
                owner=owner,
                project_id=project.id,
                site_id=created_site_id,
                layer_id=layer_id,
                feature_id=feature.id,
            )
            overlap_results.append(overlap)
            if not overlap.intersects or overlap.intersection_area_sqm <= 0:
                raise RuntimeError(
                    f"Feature {feature.id} did not produce positive-area overlap."
                )

        print("")
        print(
            "OVERLAP_SITE_PERCENTS =",
            [item.site_overlap_percent for item in overlap_results],
        )
        print("GIS_OVERLAP = PASS")

        nearest = find_nearest_features(
            session,
            owner=owner,
            project_id=project.id,
            site_id=created_site_id,
            layer_id=layer_id,
            limit=5,
        )

        print("")
        print("NEAREST_COUNT =", len(nearest.items))

        if len(nearest.items) != 2:
            raise RuntimeError(
                f"Nearest analysis expected 2 features, got {len(nearest.items)}."
            )

        print("GIS_NEAREST = PASS")

        print("")
        print("========================================")
        print("PHASE2D2_INTEGRATION_ACCEPTANCE = PASS")
        print("========================================")

    finally:
        print("")
        print("=== CONTROLLED CLEANUP ===")

        try:
            session.rollback()

            # Re-query acceptance-only records by deterministic provenance/name.
            acceptance_layers = list(
                session.scalars(
                    select(GISLayer).where(
                        GISLayer.provenance["site_source_ref"].as_string() == SOURCE_REF
                    )
                )
            )

            for layer in acceptance_layers:
                session.delete(layer)
            session.flush()

            acceptance_sites = list(
                session.scalars(
                    select(Site).where(Site.name == SITE_NAME)
                )
            )
            for site in acceptance_sites:
                session.delete(site)

            session.commit()

            after = counts(session)
            print("AFTER_CLEANUP =", after)

            if baseline is not None and after != baseline:
                raise RuntimeError(
                    f"Cleanup did not restore baseline. before={baseline}, after={after}"
                )

            remaining_acceptance_layers = session.scalar(
                select(func.count())
                .select_from(GISLayer)
                .where(
                    GISLayer.provenance["site_source_ref"].as_string() == SOURCE_REF
                )
            )
            remaining_acceptance_sites = session.scalar(
                select(func.count())
                .select_from(Site)
                .where(Site.name == SITE_NAME)
            )

            if remaining_acceptance_layers != 0 or remaining_acceptance_sites != 0:
                raise RuntimeError("Acceptance fixture records remain after cleanup.")

            print("PHASE2D2_CLEANUP = PASS")

        except Exception:
            session.rollback()
            print("PHASE2D2_CLEANUP = FAILED")
            raise

        finally:
            session.close()
            if fixture_root is not None and fixture_root.exists():
                shutil.rmtree(fixture_root, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
