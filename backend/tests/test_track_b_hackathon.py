from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from app.core.config import get_settings
from app.services.track_b import (
    _index,
    _inspect_bytes,
    _normalize_band_name,
    _pixel_area_sqm,
    _write_change_artifacts,
)


def _raster_bytes(arrays: list[np.ndarray], descriptions: list[str] | None = None) -> bytes:
    height, width = arrays[0].shape
    profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": len(arrays),
        "dtype": "float32",
        "crs": "EPSG:32647",
        "transform": from_origin(500000, 400000, 10, 10),
        "nodata": -9999.0,
    }
    with MemoryFile() as mem:
        with mem.open(**profile) as ds:
            for i, array in enumerate(arrays, 1):
                ds.write(array.astype("float32"), i)
            if descriptions:
                ds.descriptions = tuple(descriptions)
        return mem.read()


def test_track_b_raster_inspection_preserves_geospatial_metadata():
    data = _raster_bytes([np.ones((5, 6)), np.ones((5, 6)) * 2], ["Red", "NIR"])
    result = _inspect_bytes(data)
    assert result.crs == "EPSG:32647"
    assert result.width == 6 and result.height == 5 and result.count == 2
    assert result.band_names == ["B04", "B08"]
    assert result.pixel_size == {"x": 10.0, "y": 10.0}


def test_track_b_normalizes_common_sentinel_band_aliases():
    assert _normalize_band_name("B4") == "B04"
    assert _normalize_band_name("red") == "B04"
    assert _normalize_band_name("nir") == "B08"
    assert _normalize_band_name("swir1") == "B11"


def test_track_b_projected_pixel_area_is_metric():
    meta = {
        "crs": rasterio.crs.CRS.from_epsg(32647),
        "transform": from_origin(500000, 400000, 10, 10),
        "bounds": rasterio.coords.BoundingBox(500000, 399900, 500100, 400000),
        "width": 10,
        "height": 10,
    }
    area, limitation = _pixel_area_sqm(meta)
    assert area == 100.0
    assert limitation is None


def test_track_b_change_artifacts_are_map_ready_wgs84(tmp_path, monkeypatch):
    monkeypatch.setenv("RASTER_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        mask = np.zeros((10, 10), dtype=bool)
        mask[2:5, 3:7] = True
        meta = {
            "crs": rasterio.crs.CRS.from_epsg(32647),
            "transform": from_origin(500000, 400000, 10, 10),
            "bounds": rasterio.coords.BoundingBox(500000, 399900, 500100, 400000),
            "width": 10,
            "height": 10,
        }
        import uuid
        project_id, analysis_id = uuid.uuid4(), uuid.uuid4()
        mask_name, geo_name, limitations = _write_change_artifacts(project_id, analysis_id, mask, meta)
        assert mask_name == "change_mask.tif" and geo_name == "change_regions.geojson"
        assert limitations == []
        geo = json.loads((tmp_path / "analysis" / str(project_id) / str(analysis_id) / geo_name).read_text())
        assert geo["type"] == "FeatureCollection"
        assert geo["features"]
        coords = geo["features"][0]["geometry"]["coordinates"]
        assert coords
    finally:
        get_settings.cache_clear()


def _write_single(path: Path, value: float, *, resolution: float, description: str) -> None:
    width = height = int(100 / resolution)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs="EPSG:32647",
        transform=from_origin(500000, 400000, resolution, resolution),
        nodata=-9999.0,
    ) as ds:
        ds.write(np.full((height, width), value, dtype="float32"), 1)
        ds.set_band_description(1, description)


def test_track_b_sentinel_mixed_resolution_indices_align(tmp_path, monkeypatch):
    monkeypatch.setenv("RASTER_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        b11 = tmp_path / "b11.tif"; b08 = tmp_path / "b08.tif"
        _write_single(b11, 0.6, resolution=20, description="B11")
        _write_single(b08, 0.2, resolution=10, description="B08")
        dataset = SimpleNamespace(
            band_names=["B11", "B08"],
            source_uri=None,
            provenance={"assets": {
                "B11": {"uri": "local://rasters/b11.tif"},
                "B08": {"uri": "local://rasters/b08.tif"},
            }},
        )
        result, meta = _index(dataset, "ndbi")
        assert result.shape == (5, 5)
        assert np.isfinite(result).all()
        assert np.allclose(result, 0.5, atol=1e-4)
        assert meta["width"] == 5
    finally:
        get_settings.cache_clear()


def test_track_b_api_surface_is_registered():
    from app.main import app
    paths = {route.path for route in app.routes}
    expected = {
        "/api/v1/projects/{project_id}/track-b/capabilities",
        "/api/v1/projects/{project_id}/track-b/datasets/upload",
        "/api/v1/projects/{project_id}/track-b/datasets/bundle",
        "/api/v1/projects/{project_id}/track-b/datasets/sentinel-archive",
        "/api/v1/projects/{project_id}/track-b/analyze",
        "/api/v1/projects/{project_id}/track-b/analyses/{analysis_id}/report",
    }
    assert expected <= paths


def test_track_b_infers_sentinel_acquisition_datetime_from_filename():
    from app.services.track_b import _infer_acquisition_datetime
    assert _infer_acquisition_datetime("T47NQD_20260815T023559_B04_10m.jp2") == "2026-08-15T02:35:59Z"
    assert _infer_acquisition_datetime("urban_20260701.tif") == "2026-07-01T00:00:00Z"


def test_track_b_ai_rejects_invented_numeric_claims():
    from app.services.track_b_ai import TrackBAIError, _validate_no_invented_numbers
    analysis = {
        "changed_percentage": 12.5,
        "changed_area_hectares": 4.2,
        "usable_coverage_percent": 95.0,
        "changed_pixel_count": 125,
        "valid_pixel_count": 1000,
        "mean_before": None,
        "mean_after": None,
        "before_datetime": "2026-01-01T00:00:00Z",
        "after_datetime": "2026-06-01T00:00:00Z",
    }
    grounded = {"executive_summary": "Measured change is 12.50% across 95.00% usable coverage.", "planner_problem": "Review measured change.", "insights": [], "next_actions": [], "caveats": []}
    _validate_no_invented_numbers(grounded, analysis)
    invented = {**grounded, "executive_summary": "Measured change is 12.50% and affects 77 hectares."}
    import pytest
    with pytest.raises(TrackBAIError):
        _validate_no_invented_numbers(invented, analysis)


def test_track_b_ai_json_contract_parser_accepts_plain_json():
    from app.services.track_b_ai import _parse_json
    payload = {"confidence": "high", "executive_summary": "Grounded.", "planner_problem": "Review change.", "insights": [], "next_actions": [], "caveats": []}
    assert _parse_json(json.dumps(payload)) == payload


def test_track_b_ai_api_surface_is_registered():
    from app.main import app
    paths = {route.path for route in app.routes}
    assert "/api/v1/projects/{project_id}/track-b/analyses/{analysis_id}/ai-interpret" in paths


def test_track_b_urban_rural_ai_api_surface_is_registered():
    from app.main import app
    paths = {route.path for route in app.routes}
    assert "/api/v1/projects/{project_id}/track-b/ai/urban-rural-compare" in paths


def test_track_b_urban_rural_comparison_rejects_invented_numbers():
    import pytest
    from app.services.track_b_ai import TrackBAIError, _validate_comparison_numbers
    urban = {"changed_percentage": 12.5, "changed_area_hectares": 4.2, "usable_coverage_percent": 95.0, "changed_pixel_count": 125, "valid_pixel_count": 1000}
    rural = {"changed_percentage": 8.0, "changed_area_hectares": 7.1, "usable_coverage_percent": 96.0, "changed_pixel_count": 80, "valid_pixel_count": 1000}
    grounded = {"strategic_summary": "Urban measured change is 12.50% while rural measured change is 8.00%.", "urban_priority": "Review urban change.", "rural_priority": "Review rural change.", "shared_planning_problem": "Prioritize verification.", "comparative_insights": [], "priority_actions": [], "caveats": []}
    _validate_comparison_numbers(grounded, urban, rural)
    invented = {**grounded, "urban_priority": "Inspect 44 priority zones."}
    with pytest.raises(TrackBAIError):
        _validate_comparison_numbers(invented, urban, rural)


def test_track_b_planner_decision_api_surface_is_registered():
    from app.main import app
    paths = {route.path for route in app.routes}
    assert "/api/v1/projects/{project_id}/track-b/analyses/{analysis_id}/decision-workspace" in paths


def test_track_b_planner_decision_rejects_invented_numbers():
    import pytest
    from app.services.track_b_ai import TrackBAIError, _validate_decision_numbers
    analysis = {
        "changed_percentage": 12.5,
        "changed_area_hectares": 4.2,
        "usable_coverage_percent": 95.0,
        "changed_pixel_count": 125,
        "valid_pixel_count": 1000,
        "mean_before": None,
        "mean_after": None,
        "before_datetime": "2026-01-01T00:00:00Z",
        "after_datetime": "2026-06-01T00:00:00Z",
    }
    grounded = {
        "decision_title": "Planner review required",
        "issue": "Measured change is 12.50%.",
        "planning_implication": "Prioritize verification of measured change.",
        "evidence_summary": "Usable coverage is 95.00%.",
        "recommended_actions": [{"action": "Inspect mapped change", "rationale": "The temporal result shows 12.50% measured change.", "evidence_refs": ["TEMPORAL_ANALYSIS"], "verification_needed": "Compare organizer evidence."}],
        "limitations": [],
    }
    _validate_decision_numbers(grounded, analysis)
    invented = {**grounded, "issue": "There are 44 illegal development zones."}
    with pytest.raises(TrackBAIError):
        _validate_decision_numbers(invented, analysis)



def test_track_b_planner_decision_builds_grounded_packet(tmp_path, monkeypatch):
    import uuid
    from types import SimpleNamespace
    from app.core.config import get_settings
    from app.services import track_b_ai

    project_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    folder = tmp_path / "analysis" / str(project_id) / str(analysis_id)
    folder.mkdir(parents=True)
    analysis = {
        "analysis_id": str(analysis_id),
        "location_type": "urban",
        "data_stage": "processed",
        "mode": "ndvi",
        "method": "ndvi_absolute_delta",
        "before_datetime": "2026-01-01T00:00:00Z",
        "after_datetime": "2026-06-01T00:00:00Z",
        "usable_coverage_percent": 95.0,
        "changed_pixel_count": 125,
        "valid_pixel_count": 1000,
        "changed_percentage": 12.5,
        "changed_area_hectares": 4.2,
        "mean_before": 0.4,
        "mean_after": 0.3,
        "limitations": ["Spectral change requires planner verification."],
        "evidence": [
            {"scope": "organizer_supplied_only", "role": "before", "id": "before"},
            {"scope": "organizer_supplied_only", "role": "after", "id": "after"},
            {"scope": "server_owned", "role": "site", "id": "site"},
        ],
    }
    (folder / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
    monkeypatch.setenv("RASTER_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    payload = {
        "confidence": "moderate",
        "priority": "elevated",
        "decision_title": "Verify measured temporal change",
        "issue": "Measured change is 12.50%.",
        "planning_implication": "The mapped change warrants planner review before escalation.",
        "evidence_summary": "Usable coverage is 95.00% and changed area is 4.20 hectares.",
        "recommended_actions": [
            {
                "action": "Inspect mapped change",
                "rationale": "The temporal analysis reports 12.50% measured change.",
                "evidence_refs": ["TEMPORAL_ANALYSIS", "SITE_GEOMETRY"],
                "verification_needed": "Compare organizer layers and conduct field verification.",
            }
        ],
        "evidence_refs": ["BEFORE_RASTER", "AFTER_RASTER", "SITE_GEOMETRY", "TEMPORAL_ANALYSIS"],
        "limitations": ["Spectral change requires planner verification."],
    }
    monkeypatch.setattr(
        track_b_ai,
        "generate_with_failover",
        lambda **kwargs: (SimpleNamespace(text=json.dumps(payload), provider="test-ai", model="grounded-model"), []),
    )
    try:
        result = track_b_ai.build_track_b_planner_decision(
            project_id=project_id,
            analysis_id=analysis_id,
            planner_question="What should the planner verify first?",
        )
        assert result["priority"] == "elevated"
        assert result["provider"] == "test-ai"
        assert result["planner_question"] == "What should the planner verify first?"
        assert (folder / "planner_decision.json").is_file()
    finally:
        get_settings.cache_clear()

def test_track_b_hackathon_workflow_api_surface_is_registered():
    from app.main import app
    paths = {route.path for route in app.routes}
    assert "/api/v1/projects/{project_id}/track-b/workflow/hackathon-run" in paths


def test_track_b_hackathon_pair_selector_requires_same_site_and_stage():
    import uuid
    from types import SimpleNamespace
    from datetime import datetime, timezone
    import pytest
    from app.services.track_b import TrackBError
    from app.services.track_b_workflow import _select_pair
    now = datetime.now(timezone.utc)
    site = uuid.uuid4()
    def ds(role, stage="raw", site_id=site):
        return SimpleNamespace(
            id=uuid.uuid4(), site_id=site_id, created_at=now, acquisition_datetime="2026-01-01T00:00:00Z",
            checksum_sha256="a" * 64, source_uri="file:///tmp/test-track-b.tif",
            provenance={"evidence_scope":"organizer_supplied_only","competition_track":"B","location_type":"urban","temporal_role":role,"data_stage":stage},
        )
    before, after = _select_pair([ds("before"), ds("after")], "urban")
    assert before.site_id == after.site_id == site
    with pytest.raises(TrackBError):
        _select_pair([ds("before"), ds("after", stage="processed")], "urban")



def test_track_b_readiness_api_surface_is_registered():
    from app.main import app
    paths = {route.path for route in app.routes}
    assert "/api/v1/projects/{project_id}/track-b/readiness" in paths


def test_track_b_pair_selector_rejects_synthetic_fixture():
    import uuid
    from types import SimpleNamespace
    from datetime import datetime, timezone
    import pytest
    from app.services.track_b import TrackBError
    from app.services.track_b_workflow import _select_pair

    now = datetime.now(timezone.utc)
    site = uuid.uuid4()

    def ds(role):
        return SimpleNamespace(
            id=uuid.uuid4(), site_id=site, created_at=now,
            acquisition_datetime="2026-01-01T00:00:00Z" if role == "before" else "2026-06-01T00:00:00Z",
            checksum_sha256="b" * 64, source_uri="file:///tmp/test-track-b-synthetic.tif",
            provenance={
                "evidence_scope": "organizer_supplied_only",
                "competition_track": "B",
                "synthetic_fixture": True,
                "location_type": "urban",
                "temporal_role": role,
                "data_stage": "raw",
            },
        )

    with pytest.raises(TrackBError):
        _select_pair([ds("before"), ds("after")], "urban")


def test_track_b_recommended_mode_prefers_ndvi():
    from types import SimpleNamespace
    from app.services.track_b_acceptance import _recommended_mode

    before = SimpleNamespace(band_names=["B04", "B08"], band_count=2, provenance={"data_stage":"raw"})
    after = SimpleNamespace(band_names=["B04", "B08"], band_count=2, provenance={"data_stage":"raw"})
    assert _recommended_mode(before, after) == "ndvi"


def test_track_b_openai_contract_accepts_grounded_rounding_and_list_markers():
    from app.services.track_b_ai import _validate_no_invented_numbers
    analysis = {
        "changed_percentage": 12.5, "changed_area_hectares": 4.2,
        "usable_coverage_percent": 95.0, "changed_pixel_count": 125,
        "valid_pixel_count": 1000, "mean_before": 0.469983, "mean_after": 0.401234,
        "before_datetime": "2026-01-01T00:00:00Z", "after_datetime": "2026-06-01T00:00:00Z",
    }
    payload = {
        "executive_summary": "Measured mean before is 0.46998.",
        "planner_problem": "Review measured change.", "insights": [],
        "next_actions": ["1. Inspect mapped change.", "2) Compare organizer evidence."], "caveats": [],
    }
    _validate_no_invented_numbers(payload, analysis)


def test_track_b_openai_contract_still_rejects_nonlist_numeric_claim():
    import pytest
    from app.services.track_b_ai import TrackBAIError, _validate_no_invented_numbers
    analysis = {
        "changed_percentage": 12.5, "changed_area_hectares": 4.2,
        "usable_coverage_percent": 95.0, "changed_pixel_count": 125,
        "valid_pixel_count": 1000, "mean_before": 0.469983, "mean_after": 0.401234,
        "before_datetime": "2026-01-01T00:00:00Z", "after_datetime": "2026-06-01T00:00:00Z",
    }
    payload = {
        "executive_summary": "Measured change is 12.50%.",
        "planner_problem": "Review measured change.", "insights": [],
        "next_actions": ["Inspect 2 unsupported priority zones."], "caveats": [],
    }
    with pytest.raises(TrackBAIError):
        _validate_no_invented_numbers(payload, analysis)


def test_track_b_openai_contract_canonicalizes_harmless_collection_shape_drift():
    from app.services.track_b_ai import _canonicalize_list_fields
    payload = {
        "priority_actions": "Inspect mapped change.", "caveats": None,
        "comparative_insights": {
            "title": "Review", "finding": "Measured change requires verification.",
            "planning_relevance": "Prioritize review.", "recommended_action": "Inspect mapped change.",
            "evidence_refs": ["URBAN_TEMPORAL_ANALYSIS"],
        },
    }
    _canonicalize_list_fields(payload, string_fields=("priority_actions", "caveats"), object_fields=("comparative_insights",))
    assert payload["priority_actions"] == ["Inspect mapped change."]
    assert payload["caveats"] == []
    assert isinstance(payload["comparative_insights"], list)


def test_track_b_numeric_allowlist_excludes_invented_zero_and_includes_grounded_rounding():
    from app.services.track_b_ai import _numeric_allowlist_block
    analysis = {
        "changed_percentage": 15.264892578125,
        "changed_area_hectares": 25.01,
        "usable_coverage_percent": 100.0,
        "changed_pixel_count": 2501,
        "valid_pixel_count": 16384,
        "mean_before": 0.4699769914150238,
        "mean_after": 0.3824801445007324,
        "before_datetime": "2026-01-15T00:00:00Z",
        "after_datetime": "2026-07-15T00:00:00Z",
    }
    block = _numeric_allowlist_block(analysis)
    assert "0.46998" in block
    tokens = block.split("ALLOWED_NUMERIC_TOKENS: ", 1)[1].split(", ")
    assert "0" not in tokens
    assert "2501" in tokens
    assert "25.01" in tokens
