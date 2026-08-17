import io
import zipfile

import pytest
from fastapi import UploadFile

from app.services.track_b_smart_intake import inspect_organizer_package


def _zip_upload(name, members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for member_name, data in members.items():
            z.writestr(member_name, data)
    buf.seek(0)
    return UploadFile(filename=name, file=buf)


@pytest.mark.anyio
async def test_mapinfo_bundle_recognized():
    upload = _zip_upload("organizer.zip", {
        "urban/T1/Ndcdb_lot.TAB": b"tab",
        "urban/T1/Ndcdb_lot.DAT": b"dat",
        "urban/T1/Ndcdb_lot.MAP": b"map",
        "urban/T1/Ndcdb_lot.ID": b"id",
    })
    result = await inspect_organizer_package([upload])
    assert result["database_writes"] is False
    assert result["gis_bundle_recognition"] is True
    assert result["gis_bundle_count"] == 1
    bundle = result["gis_bundles"][0]
    assert bundle["format"] == "mapinfo_tab"
    assert bundle["complete"] is True
    assert bundle["missing_required_extensions"] == []
    assert all(
        x["classification"] == "gis_mapinfo_bundle_candidate"
        for x in result["items"]
    )


@pytest.mark.anyio
async def test_shapefile_bundle_recognized():
    upload = _zip_upload("organizer.zip", {
        "rural/T2/parcel.shp": b"shp",
        "rural/T2/parcel.shx": b"shx",
        "rural/T2/parcel.dbf": b"dbf",
        "rural/T2/parcel.prj": b"prj",
    })
    result = await inspect_organizer_package([upload])
    assert result["gis_bundle_count"] == 1
    bundle = result["gis_bundles"][0]
    assert bundle["format"] == "esri_shapefile"
    assert bundle["complete"] is True


@pytest.mark.anyio
async def test_incomplete_mapinfo_bundle_requires_confirmation():
    upload = _zip_upload("organizer.zip", {
        "urban/T1/broken.TAB": b"tab",
        "urban/T1/broken.DAT": b"dat",
    })
    result = await inspect_organizer_package([upload])
    assert result["gis_bundle_count"] == 1
    bundle = result["gis_bundles"][0]
    assert bundle["complete"] is False
    assert ".map" in bundle["missing_required_extensions"]
    assert ".id" in bundle["missing_required_extensions"]
    assert all(
        x["classification"] == "gis_bundle_incomplete"
        for x in result["items"]
    )


@pytest.mark.anyio
async def test_same_stem_different_folders_not_merged():
    upload = _zip_upload("organizer.zip", {
        "urban/T1/parcel.shp": b"a",
        "urban/T1/parcel.shx": b"a",
        "urban/T1/parcel.dbf": b"a",
        "rural/T2/parcel.shp": b"b",
        "rural/T2/parcel.shx": b"b",
        "rural/T2/parcel.dbf": b"b",
    })
    result = await inspect_organizer_package([upload])
    assert result["gis_bundle_count"] == 2
    assert all(x["complete"] for x in result["gis_bundles"])
