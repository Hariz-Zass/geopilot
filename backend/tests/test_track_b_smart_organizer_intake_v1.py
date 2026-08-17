from __future__ import annotations

import asyncio
import io
import json

from fastapi import UploadFile

from app.services.track_b_smart_intake import inspect_organizer_package


def up(name: str, data: bytes):
    return UploadFile(filename=name, file=io.BytesIO(data))


def inspect(files):
    return asyncio.run(inspect_organizer_package(files))


def test_pdf_candidate_no_db_write():
    r = inspect([up("RT_Kuala_Terengganu.pdf", b"%PDF-1.4\nfake")])
    assert r["database_writes"] is False
    assert r["items"][0]["classification"] == "planning_document_candidate"


def test_polygon_geojson_candidate():
    p = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[101, 3], [101.1, 3], [101.1, 3.1], [101, 3]]],
            },
        }],
    }
    r = inspect([up("urban_zoning.geojson", json.dumps(p).encode())])
    x = r["items"][0]
    assert x["classification"] == "planning_spatial_candidate"
    assert x["location_type"] == "urban"
    assert x["suggested_applicability_role"] == "zoning"


def test_csv_helper():
    r = inspect([up("metadata.csv", b"name,date\nscene,2026-01-01\n")])
    assert r["items"][0]["classification"] == "metadata_helper"
    assert r["items"][0]["metadata"]["columns"] == ["name", "date"]


def test_unknown_safe():
    r = inspect([up("notes.xyz", b"x")])
    assert r["items"][0]["classification"] == "unsupported"
    assert r["database_writes"] is False


def test_filename_hints_survive_invalid_raster():
    r = inspect([up("urban_T1_B04.jp2", b"not-a-raster")])
    x = r["items"][0]
    assert x["classification"] == "invalid_raster"
    assert x["location_type"] == "urban"
    assert x["temporal_role"] == "before"
    assert x["band_name"] == "B04"

