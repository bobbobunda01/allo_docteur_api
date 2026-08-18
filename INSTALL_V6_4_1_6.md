# Installation V6.4.1.6

Patch sur V6.4.1.5 : remplacer `clinical/specialty.py`, `llm/prompts.py`, `services/triage_service.py`, `VERSION`; ajouter le nouveau test et le changelog.

Validation :
```bash
python -m pytest -q
```

Régression :
```bash
export OPENAI_MODEL="gpt-5-mini"
python test_batch_04b.py
```
