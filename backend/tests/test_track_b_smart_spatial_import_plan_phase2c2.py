from pathlib import Path
import inspect

from app.services import track_b_smart_spatial_import_plan as svc


def test_phase2c2_is_plan_only():
    source = Path("/app/app/services/track_b_smart_spatial_import_plan.py").read_text()
    assert '"database_writes": False' in source
    assert '"persistent_write_authorized": False' in source
    assert "session.commit" not in source
    assert "session.add(" not in source


def test_decisions_are_explicit():
    source = inspect.getsource(svc.build_spatial_import_plan)
    for token in (
        "SKIP_EMPTY",
        "REVIEW_INVALID_GEOMETRY",
        "SKIP_NO_OVERLAP",
        "IMPORT_CANDIDATE",
    ):
        assert token in source


def test_role_confirmation_blocks_persistent_import():
    source = inspect.getsource(svc.build_spatial_import_plan)
    assert '"role_confirmation_required": decision == "IMPORT_CANDIDATE"' in source
    assert '"applicability_role": None' in source


def test_sample_independent():
    source = Path("/app/app/services/track_b_smart_spatial_import_plan.py").read_text().casefold()
    assert "shah alam" not in source
    assert "terengganu" not in source
    assert "ndcdb" not in source
    assert "g08032202" not in source
    assert "semp_tapak" not in source
