from pathlib import Path

from app.db.base import Base
from app.models.policy_criterion import PolicyCriterion


def test_policy_criterion_metadata_contract():
    table = PolicyCriterion.__table__
    assert table.name == "policy_criteria"
    assert {"project_id", "policy_reference_id", "value_type", "operator", "source_evidence_text"} <= set(table.c.keys())
    assert "policy_criteria" in Base.metadata.tables


def test_policy_criterion_migration_is_0012_and_revises_0011():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "0012_policy_criterion_domain.py"
    text = path.read_text()
    assert 'revision: str = "0012"' in text
    assert 'down_revision: Union[str, None] = "0011"' in text
    assert '"policy_criteria"' in text
    assert "uq_policy_criteria_project_code" in text
    assert "policy_criterion_payload_shape_valid" in text
