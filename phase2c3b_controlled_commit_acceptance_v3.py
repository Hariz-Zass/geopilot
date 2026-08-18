from __future__ import annotations

import asyncio
import json
import pathlib
import shutil
import subprocess
import traceback
import uuid
import zipfile

from fastapi import UploadFile
from sqlalchemy import func, select

from app.db import get_session_factory
from app.models.gis_feature import GISFeature
from app.models.gis_layer import GISLayer
from app.models.project import Project
from app.models.site import Site
from app.models.user import User
from app.services.track_b_smart_import_all import (
    ImportAllRequest,
    execute_persistent_import_all,
)

# PHASE2C3B_CONTROLLED_COMMIT_ACCEPTANCE_V3
# Important repair:
# Do NOT assume GeoPackage conversion preserves GeoJSON top-level Feature.id
# as GISFeature.source_feature_id. If source IDs are absent, GeoPilot's accepted
# duplicate contract falls back to geometry_hash.

SITE_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [101.5000, 3.0500],
        [101.5100, 3.0500],
        [101.5100, 3.0600],
        [101.5000, 3.0600],
        [101.5000, 3.0500],
    ]],
}

SOURCE_REF = "phase2c3b_controlled_commit_acceptance_v3"
FIXTURE_ROOT = pathlib.Path("/tmp/phase2c3b_acceptance_v3")
FIXTURE_ZIP = FIXTURE_ROOT / "organizer_fixture.zip"


def section(title: str) -> None:
    print("")
    print("=" * 76)
    print(title)
    print("=" * 76)


def counts(db):
    return {
        "sites": db.scalar(select(func.count()).select_from(Site)),
        "layers": db.scalar(select(func.count()).select_from(GISLayer)),
        "features": db.scalar(select(func.count()).select_from(GISFeature)),
    }


def build_fixture() -> None:
    if FIXTURE_ROOT.exists():
        shutil.rmtree(FIXTURE_ROOT)
    FIXTURE_ROOT.mkdir(parents=True)

    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "A1",
                "properties": {
                    "fixture_key": "A1",
                    "landuse": "residential",
                    "fixture": True,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [101.5002, 3.0502],
                        [101.5040, 3.0502],
                        [101.5040, 3.0540],
                        [101.5002, 3.0540],
                        [101.5002, 3.0502],
                    ]],
                },
            },
            {
                "type": "Feature",
                "id": "A2",
                "properties": {
                    "fixture_key": "A2",
                    "landuse": "commercial",
                    "fixture": True,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [101.5060, 3.0560],
                        [101.5090, 3.0560],
                        [101.5090, 3.0590],
                        [101.5060, 3.0590],
                        [101.5060, 3.0560],
                    ]],
                },
            },
            {
                "type": "Feature",
                "id": "OUTSIDE",
                "properties": {
                    "fixture_key": "OUTSIDE",
                    "landuse": "industrial",
                    "fixture": True,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [102.0000, 4.0000],
                        [102.0100, 4.0000],
                        [102.0100, 4.0100],
                        [102.0000, 4.0100],
                        [102.0000, 4.0000],
                    ]],
                },
            },
        ],
    }

    source = FIXTURE_ROOT / "fixture.geojson"
    source.write_text(json.dumps(geojson), encoding="utf-8")

    gpkg = FIXTURE_ROOT / "organizer_fixture.gpkg"
    proc = subprocess.run(
        [
            "ogr2ogr",
            "-f", "GPKG",
            str(gpkg),
            str(source),
            "-nln", "LAND_USE_FIXTURE",
        ],
        text=True,
        capture_output=True,
    )
    print("ogr2ogr_exit=", proc.returncode)
    if proc.stdout:
        print("ogr2ogr_stdout=", proc.stdout.strip())
    if proc.stderr:
        print("ogr2ogr_stderr=", proc.stderr.strip())
    assert proc.returncode == 0, proc.stderr

    with zipfile.ZipFile(FIXTURE_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(gpkg, gpkg.name)

    print("fixture_format=GeoPackage")
    print("fixture_layer=LAND_USE_FIXTURE")
    print("fixture_crs=EPSG:4326")
    print("source_features=3")
    print("expected_intersecting=2")
    print("expected_outside=1")
    print("confirmed_role=land_use")


async def call_import(db, owner, project, fixture_name: str):
    with FIXTURE_ZIP.open("rb") as handle:
        upload = UploadFile(filename="organizer_fixture.zip", file=handle)
        return await execute_persistent_import_all(
            db,
            owner=owner,
            project_id=project.id,
            files=[upload],
            request=ImportAllRequest(
                site_name=fixture_name,
                site_geometry=SITE_GEOMETRY,
                site_source_ref=SOURCE_REF,
                user_confirmed=True,
                role_assignments={
                    "organizer_fixture:LAND_USE_FIXTURE": "land_use",
                },
                allow_invalid_geometry_skip=False,
                execute_persistent=True,
            ),
        )


async def run() -> int:
    db = get_session_factory()()
    fixture_name = "PHASE2C3B COMMIT FIXTURE V3 " + uuid.uuid4().hex[:8]
    baseline = {}
    baseline_active = {}
    created_site_id = None
    created_layer_ids = []

    try:
        section("A. PREFLIGHT / BASELINE")
        project = db.scalar(
            select(Project)
            .where(Project.is_archived.is_(False))
            .order_by(Project.created_at.asc())
        )
        assert project is not None, "No non-archived project available."

        owner = db.get(User, project.owner_id)
        assert owner is not None, "Project owner missing."

        baseline = counts(db)
        for site in db.scalars(select(Site).where(Site.project_id == project.id)):
            baseline_active[str(site.id)] = bool(site.is_active)

        print("project_id=", project.id)
        print("owner_id=", owner.id)
        print("baseline_sites=", baseline["sites"])
        print("baseline_layers=", baseline["layers"])
        print("baseline_features=", baseline["features"])
        print("baseline_site_active_entries=", len(baseline_active))

        section("B. SYNTHETIC ACCEPTANCE FIXTURE")
        build_fixture()

        section("C. FIRST REAL PERSISTENT COMMIT")
        first = await call_import(db, owner, project, fixture_name)
        print(json.dumps(first, indent=2, ensure_ascii=False))

        assert first["status"] == "committed"
        assert first["database_writes"] is True
        assert first["committed"] is True
        assert first["site_created"] is True
        assert first["site_duplicate_reused"] is False
        assert first["layers_created"] == 1
        assert first["layers_reused"] == 0
        assert first["features_created"] == 2
        assert first["features_duplicates_skipped"] == 0

        created_site_id = uuid.UUID(first["site_id"])
        created_layer_ids = [
            uuid.UUID(item["layer_id"]) for item in first["imported_layers"]
        ]

        site = db.get(Site, created_site_id)
        assert site is not None
        assert site.is_active is True
        assert site.is_archived is False

        assert len(created_layer_ids) == 1
        layer = db.get(GISLayer, created_layer_ids[0])
        assert layer is not None

        provenance = layer.provenance or {}
        print("layer_provenance=", json.dumps(provenance, sort_keys=True))
        assert provenance.get("applicability_role") == "land_use"
        assert provenance.get("competition_track") == "B"
        assert provenance.get("confirmed_site_id") == str(created_site_id)
        assert provenance.get("site_source_ref") == SOURCE_REF

        features = list(
            db.scalars(
                select(GISFeature)
                .where(GISFeature.layer_id == layer.id)
                .order_by(GISFeature.created_at.asc(), GISFeature.id.asc())
            )
        )
        assert len(features) == 2

        # V3 FIX:
        # GeoPackage drivers may not preserve GeoJSON top-level Feature.id.
        # Verify semantic fixture properties and geometry hashes instead of
        # sorting possibly-None source_feature_id values.
        fixture_keys = sorted(
            str((feature.properties or {}).get("fixture_key"))
            for feature in features
        )
        landuses = sorted(
            str((feature.properties or {}).get("landuse"))
            for feature in features
        )
        geometry_hashes = [feature.geometry_hash for feature in features]

        print("persisted_source_feature_ids=", [
            feature.source_feature_id for feature in features
        ])
        print("persisted_fixture_keys=", fixture_keys)
        print("persisted_landuses=", landuses)
        print("persisted_geometry_hashes=", geometry_hashes)

        assert fixture_keys == ["A1", "A2"], fixture_keys
        assert landuses == ["commercial", "residential"], landuses
        assert "OUTSIDE" not in fixture_keys
        assert "industrial" not in landuses
        assert all(isinstance(value, str) and len(value) == 64 for value in geometry_hashes)
        assert len(set(geometry_hashes)) == 2

        print("first_commit_status=PASS")
        print("site_created=1")
        print("layers_created=1")
        print("features_created=2")
        print("outside_feature_imported=0")
        print("planning_role_provenance=PASS")
        print("feature_identity_verification=PROPERTIES_PLUS_GEOMETRY_HASH")

        section("D. SECOND EXECUTION / DUPLICATE + REUSE")
        second = await call_import(db, owner, project, fixture_name)
        print(json.dumps(second, indent=2, ensure_ascii=False))

        assert second["status"] == "committed"
        assert second["site_created"] is False
        assert second["site_duplicate_reused"] is True
        assert second["layers_created"] == 0
        assert second["layers_reused"] == 1
        assert second["features_created"] == 0
        assert second["features_duplicates_skipped"] == 2

        feature_count_after_second = db.scalar(
            select(func.count())
            .select_from(GISFeature)
            .where(GISFeature.layer_id == layer.id)
        )
        assert feature_count_after_second == 2

        print("second_run_site_reused=PASS")
        print("second_run_layer_reused=PASS")
        print("second_run_feature_duplicates_skipped=2")
        print("second_run_feature_count_stable=PASS")

        section("E. ACCEPTANCE VERDICT BEFORE CLEANUP")
        print("controlled_commit_engine_verification=PASS")

        return 0

    except Exception as exc:
        section("E. ACCEPTANCE FAILURE")
        print("BLOCKER=", repr(exc))
        traceback.print_exc()
        return 1

    finally:
        section("F. CLEANUP / BASELINE RESTORATION")
        try:
            db.rollback()

            # Delete every acceptance layer by deterministic provenance/source ref.
            fixture_layers = list(
                db.scalars(
                    select(GISLayer).where(
                        GISLayer.provenance["site_source_ref"].as_string() == SOURCE_REF
                    )
                )
            )
            for layer in fixture_layers:
                db.delete(layer)
            db.flush()

            fixture_sites = list(
                db.scalars(
                    select(Site).where(
                        Site.name.like("PHASE2C3B COMMIT FIXTURE V3 %")
                    )
                )
            )
            for site in fixture_sites:
                db.delete(site)
            db.flush()

            for site_id, active in baseline_active.items():
                original = db.get(Site, uuid.UUID(site_id))
                if original is not None:
                    original.is_active = active

            db.commit()

            after = counts(db)
            acceptance_site_remaining = db.scalar(
                select(func.count())
                .select_from(Site)
                .where(Site.name.like("PHASE2C3B COMMIT FIXTURE V3 %"))
            )
            acceptance_layers_remaining = db.scalar(
                select(func.count())
                .select_from(GISLayer)
                .where(
                    GISLayer.provenance["site_source_ref"].as_string() == SOURCE_REF
                )
            )

            print("baseline_sites=", baseline.get("sites"))
            print("after_sites=", after["sites"])
            print("baseline_layers=", baseline.get("layers"))
            print("after_layers=", after["layers"])
            print("baseline_features=", baseline.get("features"))
            print("after_features=", after["features"])
            print("acceptance_site_remaining=", acceptance_site_remaining)
            print("acceptance_layers_remaining=", acceptance_layers_remaining)

            assert after == baseline, (baseline, after)
            assert acceptance_site_remaining == 0
            assert acceptance_layers_remaining == 0

            restored = {
                str(site.id): bool(site.is_active)
                for site in db.scalars(
                    select(Site).where(Site.project_id == project.id)
                )
            }
            for site_id, active in baseline_active.items():
                assert restored.get(site_id) == active

            print("site_active_states_restored=PASS")
            print("baseline_restoration=PASS")

        except Exception:
            print("cleanup_error=TRUE")
            traceback.print_exc()
            db.rollback()
            raise
        finally:
            try:
                if FIXTURE_ROOT.exists():
                    shutil.rmtree(FIXTURE_ROOT)
                print("fixture_file_cleanup=PASS")
            finally:
                db.close()


if __name__ == "__main__":
    exit_code = asyncio.run(run())
    if exit_code == 0:
        print("")
        print("=" * 76)
        print("G. PYTHON ACCEPTANCE VERDICT")
        print("=" * 76)
        print("PHASE 2C.3B CONTROLLED COMMIT ACCEPTANCE: PASS")
    raise SystemExit(exit_code)
