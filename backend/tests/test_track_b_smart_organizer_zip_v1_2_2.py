from __future__ import annotations
import asyncio, io, json, zipfile
from fastapi import UploadFile
from app.services.track_b_smart_intake import inspect_organizer_package

def up(n,d): return UploadFile(filename=n,file=io.BytesIO(d))
def run(files): return asyncio.run(inspect_organizer_package(files))
def z(entries):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as a:
        for n,d in entries.items(): a.writestr(n,d)
    return b.getvalue()

def test_mixed_zip():
    geo=json.dumps({"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[101,3],[101.1,3],[101.1,3.1],[101,3]]]}}]}).encode()
    r=run([up("Organizer.zip",z({
        "Urban/Planning/urban_zoning.geojson":geo,
        "Documents/RT.pdf":b"%PDF-1.4",
        "metadata.csv":b"name,date\nx,y\n",
        "notes.xyz":b"x",
    }))])
    classes={x["classification"] for x in r["items"]}
    assert r["archive_expansion"] is True
    assert r["database_writes"] is False
    assert {"planning_spatial_candidate","planning_document_candidate","metadata_helper","unsupported"} <= classes

def test_path_hints():
    r=run([up("Organizer.zip",z({"Urban/T1/urban_T1_B04.jp2":b"not-raster"}))])
    x=r["items"][0]
    assert x["location_type"]=="urban"
    assert x["temporal_role"]=="before"
    assert x["band_name"]=="B04"

def test_zip_slip_blocked():
    r=run([up("Organizer.zip",z({"../evil.pdf":b"x"}))])
    assert r["items"][0]["classification"]=="unsafe_archive_path"

def test_nested_zip():
    inner=z({"Documents/GPP.pdf":b"%PDF-1.4"})
    outer=z({"nested/materials.zip":inner})
    r=run([up("Organizer.zip",outer)])
    assert any(x["classification"]=="planning_document_candidate" for x in r["items"])
