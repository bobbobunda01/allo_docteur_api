# Installation V6.4.1.5

## Patch sur V6.4.1.4
Remplacer :
- `clinical/specialty.py`
- `llm/prompts.py`
- `services/triage_service.py`

Ajouter :
- `tests/test_v6415_specialty_priority_calibration.py`
- `CHANGELOG_V6_4_1_5.md`

Remplacer également `VERSION`.

## Vérification
```bash
python -m pytest -q
```
Résultat attendu : `67 passed`.

## Régression clinique
```bash
export OPENAI_MODEL="gpt-5-mini"
python test_batch_04b.py
```
Comparer P1 sensitivity/specificity, spécialité P1 LLM-only, P2->P3, P3->P2/P4 et P4->P3.
