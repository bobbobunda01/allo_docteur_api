from clinical.text_safety_gate import evaluate_text_safety


def _p1(text: str) -> bool:
    return evaluate_text_safety(text, []).emergency


def test_cvb_confusion_variant():
    assert _p1('Brusque confusion sans raison connue')


def test_cvb_breathing_typo_variant():
    assert _p1("J'arrive plu a respiré correctement")


def test_cvb_neck_variant():
    assert _p1("J'ai de la fièvre et mon cou est devenu très raide")


def test_cvb_bleeding_typo_variant():
    assert _p1('Je saigne bokou sa sarrete pa')


def test_cvb_board_abdomen_variants():
    assert _p1('Mon ventre ne se laisse plus toucher tellement il est dur et douloureux')
    assert _p1('Ventre dur kom planche douleur tres forte')


def test_negated_neck_stiffness_not_p1():
    assert not _p1('Fièvre récente sans raideur de nuque ni confusion')


def test_mild_rash_with_fever_not_automatic_p1():
    assert not _p1('Fièvre et quelques boutons mais état général conservé')


def test_explicit_suicide_negation_not_p1():
    assert not _p1('Aucune envie de mourir ni de me suicider, je cherche seulement un psychologue')
