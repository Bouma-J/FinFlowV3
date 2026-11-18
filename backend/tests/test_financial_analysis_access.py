"""L'auteur modifie ou supprime son analyse seulement avant soumission, ou après un retour."""
from types import SimpleNamespace

from apps.credits.access import can_edit_financial_analysis


def _analysis(status, author_id=1):
    return SimpleNamespace(
        created_by_id=author_id,
        application=SimpleNamespace(status=status),
    )


def test_author_changes_an_analysis_before_submission_or_after_return():
    author = SimpleNamespace(id=1, is_authenticated=True)
    colleague = SimpleNamespace(id=2, is_authenticated=True)

    assert can_edit_financial_analysis(_analysis("DRAFT"), author)
    assert can_edit_financial_analysis(_analysis("RETURNED"), author)
    assert not can_edit_financial_analysis(_analysis("SUBMITTED"), author)
    assert not can_edit_financial_analysis(_analysis("IN_APPROVAL"), author)
    assert not can_edit_financial_analysis(_analysis("APPROVED"), author)
    assert not can_edit_financial_analysis(_analysis("DRAFT"), colleague)
    assert not can_edit_financial_analysis(_analysis("RETURNED"), colleague)
    assert not can_edit_financial_analysis(_analysis("DRAFT"), None)
