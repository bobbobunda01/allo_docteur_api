# Installation du correctif V6.3 — Fusion des signes de sévérité

Copier les fichiers en conservant exactement les chemins suivants à la racine du projet :

- `llm/schemas.py`
- `llm/prompts.py`
- `llm/triage_assessor.py`
- `domain/models.py`
- `services/triage_service.py`
- `clinical/text_safety_gate.py`
- `llm/fallback.py`
- `tests/test_llm_severity_fusion.py`
- `tests/test_text_safety_gate_v63.py`

Avant remplacement, sauvegarder les fichiers existants.

```bash
cp llm/schemas.py llm/schemas.py.bak
cp llm/prompts.py llm/prompts.py.bak
cp llm/triage_assessor.py llm/triage_assessor.py.bak
cp domain/models.py domain/models.py.bak
cp services/triage_service.py services/triage_service.py.bak
cp clinical/text_safety_gate.py clinical/text_safety_gate.py.bak
cp llm/fallback.py llm/fallback.py.bak
```

Puis vérifier :

```bash
python -m compileall app api audit cli clinical domain geography intake llm services
pytest -q
python -m cli.interactive --technical
```

Le résultat technique d'un cas AVC contradictoire doit contenir :

- `priority: P1`
- `severity_signs_triggered: ["stroke_signs"]`
- `severity_override_applied: true`
- une source `free_text_local_gate` ou `free_text_llm`
