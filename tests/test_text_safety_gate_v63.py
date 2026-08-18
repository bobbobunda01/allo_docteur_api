from clinical.text_safety_gate import evaluate_text_safety


def test_detects_fast_stroke_phrase():
    result = evaluate_text_safety(
        'Depuis une heure ma bouche est de travers, je parle difficilement et mon bras gauche est devenu très faible.',
        [],
    )
    assert result.emergency is True
    assert result.code == 'TEXT_STROKE_WARNING'


def test_simple_neck_pain_is_not_stroke():
    result = evaluate_text_safety('J ai mal au cou et à la tête.', [])
    assert result.emergency is False
