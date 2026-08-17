from pathlib import Path

def test_v133_static_contract():
    text = Path("/app/app/services/track_b_smart_intake.py").read_text()
    assert "SMART_ORGANIZER_FORMAT_COVERAGE_V1_3_3" in text
    assert '_mapinfo_optional = {".ind"}' in text
    assert "gis_geopackage_candidate" in text
    assert "organizer_auxiliary_ignored" in text

def test_ind_optional_contract():
    text = Path("/app/app/services/track_b_smart_intake.py").read_text()
    assert '_mapinfo_required = {".tab", ".dat", ".map", ".id"}' in text
    assert '_mapinfo_optional = {".ind"}' in text
