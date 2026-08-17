from pathlib import Path
import inspect

from app.services import track_b_smart_transactional_gis as svc


def test_never_commits_or_rolls_back():
    source = Path("/app/app/services/track_b_smart_transactional_gis.py").read_text()
    assert "session.commit" not in source
    assert "session.rollback" not in source
    assert "session.flush()" in source


def test_layer_duplicate_contract():
    source = inspect.getsource(svc.create_gis_layer_uncommitted)
    assert "GISLayer.project_id == project.id" in source
    assert "GISLayer.source_checksum_sha256 == request.source_checksum_sha256" in source
    assert "applicability_role" in Path("/app/app/services/track_b_smart_transactional_gis.py").read_text()


def test_feature_duplicate_contract():
    source = inspect.getsource(svc.ingest_features_uncommitted)
    assert "source_feature_id" in source
    assert "geometry_hash" in source
    assert "duplicate_count" in source


def test_existing_domain_helpers_reused():
    source = Path("/app/app/services/track_b_smart_transactional_gis.py").read_text()
    assert "geometry_to_ewkt" in source
    assert "geometry_digest" in source
    assert "GISFeatureCreateRequest" in source
    assert "GISLayerCreateRequest" in source


def test_sample_independent():
    source = Path("/app/app/services/track_b_smart_transactional_gis.py").read_text().casefold()
    for token in ("shah alam", "terengganu", "ndcdb", "g08032202", "semp_tapak"):
        assert token not in source
