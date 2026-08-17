from pathlib import Path
import inspect

from app.services import track_b_smart_transactional_site as svc


def test_service_never_commits():
    source = inspect.getsource(svc.create_competition_site_uncommitted)
    assert "session.commit" not in source
    assert "session.flush()" in source


def test_duplicate_guard_uses_project_and_geometry_hash():
    source = inspect.getsource(svc.create_competition_site_uncommitted)
    assert "Site.project_id == project.id" in source
    assert "Site.geometry_hash == digest" in source
    assert "Site.is_archived.is_(False)" in source


def test_active_lifecycle_is_preserved():
    source = inspect.getsource(svc.create_competition_site_uncommitted)
    assert "Site.is_active.is_(True)" in source
    assert ".values(is_active=False)" in source


def test_no_migration_or_new_site_model():
    source = Path("/app/app/services/track_b_smart_transactional_site.py").read_text()
    assert "op.create_table" not in source
    assert "class Site(" not in source
