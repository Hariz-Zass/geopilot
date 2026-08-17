from pathlib import Path
import shutil

def test_phase2a_contract_present():
    s=Path("/app/app/services/track_b_smart_import.py").read_text()
    a=Path("/app/app/api/v1/track_b.py").read_text()
    assert "SMART_ORGANIZER_PHASE2A" in s
    assert "/organizer-intake/prepare" in a
    assert "database_writes" in s
    assert "migration_required" in s

def test_gdal_runtime_available():
    assert shutil.which("ogr2ogr")
    assert shutil.which("ogrinfo")

def test_conversion_is_epsg4326_normalized():
    s=Path("/app/app/services/track_b_smart_import.py").read_text()
    assert '"-t_srs","EPSG:4326"' in s
