from geography.africa_context import build_africa_context, infer_african_subregion


def test_infers_central_africa_for_drc():
    assert infer_african_subregion('RDC') == 'Afrique centrale'


def test_context_does_not_invent_diseases_or_alerts():
    context = build_africa_context(country='Sénégal', administrative_region='Dakar')
    assert context['african_subregion'] == "Afrique de l'Ouest"
    assert context['endemic_conditions'] == []
    assert context['active_health_alerts'] == []


def test_context_preserves_explicit_health_information():
    context = build_africa_context(
        country='Kenya',
        endemic_conditions=['Paludisme documenté dans la zone'],
        active_health_alerts=['Alerte officielle datée'],
        source_date='2026-08-04',
    )
    assert context['endemic_conditions'] == ['Paludisme documenté dans la zone']
    assert context['source_date'] == '2026-08-04'
