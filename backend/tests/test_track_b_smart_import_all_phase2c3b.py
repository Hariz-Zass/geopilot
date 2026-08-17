from pathlib import Path
import inspect

from app.services import track_b_smart_import_all as svc


def test_exactly_one_commit_boundary():
    source = inspect.getsource(svc.execute_persistent_import_all)
    assert source.count("session.commit()") == 1
    assert source.count("session.rollback()") == 1


def test_zero_candidate_fallback_forbidden():
    source = inspect.getsource(svc.execute_persistent_import_all)
    assert "blocked_no_import_candidates" in source
    assert "No organizer GIS dataset spatially intersects" in source


def test_role_confirmation_required():
    source = inspect.getsource(svc.execute_persistent_import_all)
    assert "requires an explicit confirmed data/applicability role" in source


def test_invalid_geometry_requires_explicit_override():
    source = inspect.getsource(svc.execute_persistent_import_all)
    assert "allow_invalid_geometry_skip" in source
    assert "explicitly allow invalid geometry skip" in source


def test_transactional_foundations_reused():
    source = Path("/app/app/services/track_b_smart_import_all.py").read_text()
    assert "create_competition_site_uncommitted" in source
    assert "create_gis_layer_uncommitted" in source
    assert "ingest_features_uncommitted" in source


def test_sample_independent():
    source = Path("/app/app/services/track_b_smart_import_all.py").read_text().casefold()
    for token in ("shah alam", "terengganu", "ndcdb", "g08032202", "semp_tapak"):
        assert token not in source
