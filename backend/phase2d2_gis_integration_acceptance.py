import asyncio
import io
import uuid

from fastapi import UploadFile
from sqlalchemy import select, func

from app.db import get_session_factory
from app.models.user import User
from app.models.project import Project
from app.models.site import Site
from app.models.gis_layer import GISLayer
from app.models.gis_feature import GISFeature

from app.services.track_b_smart_import_all import (
    ImportAllRequest,
    execute_persistent_import_all,
)
from app.services.site_applicability import resolve_site_applicability
from app.services.gis_analysis import (
    calculate_site_area,
    calculate_feature_overlap,
    find_nearest_features,
)

SITE_NAME = "PHASE2D2 GIS INTEGRATION ACCEPTANCE"
SOURCE_REF = "phase2d2://temporary-acceptance"

geojson = b'''{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "phase2d2-a",
      "properties": {
        "land_use": "Residential",
        "acceptance_fixture": true
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [101.7000,3.0000],
          [101.7060,3.0000],
          [101.7060,3.0060],
          [101.7000,3.0060],
          [101.7000,3.0000]
        ]]
      }
    },
    {
      "type": "Feature",
      "id": "phase2d2-b",
      "properties": {
        "land_use": "Commercial",
        "acceptance_fixture": true
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [101.7060,3.0000],
          [101.7120,3.0000],
          [101.7120,3.0060],
          [101.7060,3.0060],
          [101.7060,3.0000]
        ]]
      }
    }
  ]
}'''

site_geometry = {
    "type": "Polygon",
    "coordinates": [[
        [101.7020, 3.0010],
        [101.7100, 3.0010],
        [101.7100, 3.0050],
        [101.7020, 3.0050],
        [101.7020, 3.0010],
    ]],
}


async def main():
    session = get_session_factory()()

    created_site_id = None
    created_layer_ids = []

    try:
        print("========================================")
        print("PHASE 2D.2 GIS INTEGRATION ACCEPTANCE")
        print("========================================")

        owner = session.scalar(
            select(User).order_by(User.created_at.asc())
        )
        if owner is None:
            raise RuntimeError("No user found.")

        project = session.scalar(
            select(Project)
            .where(Project.owner_id == owner.id)
            .order_by(Project.created_at.asc())
        )
        if project is None:
            raise RuntimeError("No project found for owner.")

        print("owner_id =", owner.id)
        print("project_id =", project.id)

        before_sites = session.scalar(
            select(func.count()).select_from(Site)
        )
        before_layers = session.scalar(
            select(func.count()).select_from(GISLayer)
        )
        before_features = session.scalar(
            select(func.count()).select_from(GISFeature)
        )

        print("")
        print("BEFORE =", {
            "sites": before_sites,
            "layers": before_layers,
            "features": before_features,
        })

        upload = UploadFile(
            filename="phase2d2_land_use.geojson",
            file=io.BytesIO(geojson),
        )

        logical_name = "phase2d2_land_use:PHASE2D2_LAND_USE"

        request = ImportAllRequest(
            site_name=SITE_NAME,
            site_geometry=site_geometry,
            site_source_ref=SOURCE_REF,
            user_confirmed=True,
            role_assignments={
                logical_name: "land_use",
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
                "Smart Organizer import did not commit."
            )

        created_site_id = uuid.UUID(result["site_id"])
        created_layer_ids = [
            uuid.UUID(item["layer_id"])
            for item in result["imported_layers"]
            if item.get("layer_created")
        ]

        if len(result["imported_layers"]) != 1:
            raise RuntimeError(
                "Expected exactly one imported layer."
            )

        layer_id = uuid.UUID(
            result["imported_layers"][0]["layer_id"]
        )

        features = list(
            session.scalars(
                select(GISFeature)
                .where(
                    GISFeature.project_id == project.id,
                    GISFeature.layer_id == layer_id,
                    GISFeature.is_archived.is_(False),
                )
                .order_by(GISFeature.created_at.asc())
            )
        )

        if len(features) != 2:
            raise RuntimeError(
                f"Expected 2 imported features, got {len(features)}."
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

        if not applicability:
            raise RuntimeError(
                "Imported land_use layer was not consumable by "
                "site applicability."
            )

        if not all(
            item.applicability_role == "land_use"
            for item in applicability
        ):
            raise RuntimeError(
                "Unexpected applicability role."
            )

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

        overlap = calculate_feature_overlap(
            session,
            owner=owner,
            project_id=project.id,
            site_id=created_site_id,
            layer_id=layer_id,
            feature_id=features[0].id,
        )

        print("")
        print("OVERLAP_INTERSECTS =", overlap.intersects)
        print(
            "OVERLAP_SITE_PERCENT =",
            overlap.site_overlap_percent,
        )

        if not overlap.intersects:
            raise RuntimeError(
                "Imported GIS feature did not intersect Site."
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
                "Nearest analysis did not consume both imported features."
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
            if created_layer_ids:
                session.query(GISLayer).filter(
                    GISLayer.id.in_(created_layer_ids)
                ).delete(synchronize_session=False)

            if created_site_id is not None:
                session.query(Site).filter(
                    Site.id == created_site_id,
                    Site.name == SITE_NAME,
                ).delete(synchronize_session=False)

            session.commit()

            after_sites = session.scalar(
                select(func.count()).select_from(Site)
            )
            after_layers = session.scalar(
                select(func.count()).select_from(GISLayer)
            )
            after_features = session.scalar(
                select(func.count()).select_from(GISFeature)
            )

            print("AFTER_CLEANUP =", {
                "sites": after_sites,
                "layers": after_layers,
                "features": after_features,
            })

            if (
                after_sites != before_sites
                or after_layers != before_layers
                or after_features != before_features
            ):
                raise RuntimeError(
                    "Cleanup did not restore baseline counts."
                )

            print("PHASE2D2_CLEANUP = PASS")

        except Exception:
            session.rollback()
            print("PHASE2D2_CLEANUP = FAILED")
            raise

        finally:
            session.close()


asyncio.run(main())

