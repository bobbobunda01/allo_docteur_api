from clinical.text_safety_gate import evaluate_text_safety


def test_chest_pressure_with_dyspnea_is_p1_text_signal():
    result = evaluate_text_safety(
        "J'ai comme un poids sur la poitrine et je respire difficilement depuis ce matin",
        ['Essoufflement'],
    )
    assert result.emergency is True
    assert result.code == 'TEXT_CHEST_PRESSURE_WITH_DYSPNEA'


def test_simple_headache_is_not_text_p1():
    result = evaluate_text_safety("J'ai mal à la tête depuis ce matin", ['Maux de tête'])
    assert result.emergency is False
