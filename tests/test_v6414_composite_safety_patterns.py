from clinical.text_safety_gate import evaluate_text_safety


def _eval(text: str):
    return evaluate_text_safety(text, [])


def test_airway_stridor_plus_drooling_is_p1_signal():
    r = _eval("Enfant qui bave, refuse d'avaler et fait un bruit aigu quand il inspire.")
    assert r.emergency is True
    assert 'severe_breathing' in r.triggered_codes


def test_dyspnea_at_rest_plus_speech_limitation_is_p1_signal():
    r = _eval("Je suis essoufflé même sans bouger et je ne peux dire que quelques mots à la fois.")
    assert r.emergency is True
    assert 'severe_breathing' in r.triggered_codes


def test_asthma_rescue_failure_plus_breathing_struggle_is_p1_signal():
    r = _eval("Asthmatique, l'inhalateur ne marche presque plus et je lutte pour respirer.")
    assert r.emergency is True
    assert 'severe_breathing' in r.triggered_codes


def test_pesticide_cholinergic_cluster_with_respiratory_danger_is_p1_signal():
    r = _eval("Après exposition à pesticide, je salive beaucoup, transpire, vomis et respire difficilement.")
    assert r.emergency is True
    assert 'poisoning' in r.triggered_codes
    assert 'severe_breathing' in r.triggered_codes


def test_muffled_voice_with_explicit_normal_breathing_is_not_p1_by_text_gate():
    r = _eval("Voix étouffée, forte douleur de gorge et fièvre mais respiration normale.")
    assert r.emergency is False


def test_hot_swollen_joint_with_fever_is_not_p1_by_text_gate_alone():
    r = _eval("Genou rouge, chaud, gonflé avec fièvre.")
    assert r.emergency is False


def test_isolated_dyspnea_does_not_trigger_new_composite_rule():
    r = _eval("Je suis un peu essoufflé quand je monte les escaliers mais je parle normalement au repos.")
    assert r.emergency is False


def test_isolated_pesticide_exposure_without_toxic_syndrome_is_not_p1():
    r = _eval("J'ai travaillé près d'un champ traité au pesticide mais je me sens bien et je respire normalement.")
    assert r.emergency is False
