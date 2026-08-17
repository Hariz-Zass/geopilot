from decimal import Decimal
from types import SimpleNamespace
from app.services.compliance_engine import _evaluate_numeric, _eq_text

def test_numeric_operators():
    assert _evaluate_numeric('gte', Decimal('30'), Decimal('30'), None, None) is True
    assert _evaluate_numeric('lt', Decimal('5'), Decimal('4'), None, None) is False
    assert _evaluate_numeric('between', Decimal('5'), None, Decimal('1'), Decimal('10')) is True

def test_text_comparison_is_casefolded():
    assert _eq_text('Residential ', 'residential')
