from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_policy_reference_migration_remains_in_chain_and_follows_0010():
    root=Path(__file__).resolve().parents[1]
    cfg=Config(str(root/"alembic.ini")); cfg.set_main_option("script_location",str(root/"alembic"))
    script=ScriptDirectory.from_config(cfg)
    assert script.get_current_head() is not None
    rev=script.get_revision("0011")
    assert rev is not None and rev.down_revision=="0010"
    assert script.get_revision(script.get_current_head()) is not None


def test_policy_reference_migration_contains_lineage_and_review_guards():
    root=Path(__file__).resolve().parents[1]
    text=(root/"alembic"/"versions"/"0011_policy_reference_workflow.py").read_text()
    for token in (
        '"policy_references"',
        'document_chunk_id',
        'version_checksum_sha256',
        'source_wording',
        'representation_state',
        'review_state',
        'applicability_status',
        'reviewed_by_user_id',
        'policy_reference_final_review_consistency',
    ):
        assert token in text
