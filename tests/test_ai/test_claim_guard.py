from whatsapp_platform.infrastructure.ai.claim_guard import is_unbacked_finance_claim


def test_fabricated_budget_confirmation_is_flagged() -> None:
    assert is_unbacked_finance_claim("tambahkan buget Transportasi 220rb", "Ditambahkan: Rp220.000 untuk bulan ini.")


def test_plain_chat_not_flagged() -> None:
    assert not is_unbacked_finance_claim("halo apa kabar", "Berhasil! Kabar baik.")


def test_finance_question_without_claim_not_flagged() -> None:
    assert not is_unbacked_finance_claim("harga bensin berapa", "Sekitar Rp10.000 per liter.")
