from pathlib import Path


def test_dispatcher_manifest_lookup_uses_existing_analysis_artifact():
    text = Path("app/api/v1/track_b.py").read_text(encoding="utf-8-sig")
    assert "get_track_b_analysis_manifest" not in text
    assert "import json" in text
    assert 'artifact_path(' in text
    assert '"analysis.json"' in text
    assert "json.loads(" in text
    assert "TRACKB_PLANNING_QUESTION_DISPATCHER_V1" in text
    assert '"documents.search" in route.tools' in text
