"""Salah ketik 'buget' tetap harus memilih tool budget (bukan chat tanpa tool)."""

import pytest

from whatsapp_platform.infrastructure.ai.tool_policy import _select_finance_tools


@pytest.mark.parametrize("text", [
    "tambahkan buget transportasi 220rb",
    "tambahkan budget transportasi 220rb",
    "set bujet makan 1jt",
])
def test_budget_spelling_variants_select_budget_tools(text: str) -> None:
    names = {t.name for t in _select_finance_tools(text.lower())}
    assert "finance_create_budget" in names
