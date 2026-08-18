# AlloDocteur V6.2 — contexte africain structuré

Cette version conserve les 17 signes de sévérité déterministes et ajoute au
raisonnement LLM un contexte géographique explicite : pays, sous-région africaine,
région/province, zone de santé, milieu, saison et voyages récents.

Le backend **n'invente aucune maladie endémique ni alerte sanitaire**. Les champs
`endemic_conditions` et `active_health_alerts` restent vides tant qu'une source
autorisée et datée ne les alimente pas.

## Fichiers principaux modifiés

- `llm/prompts.py`
- `llm/triage_assessor.py`
- `domain/models.py`
- `cli/interactive.py`
- `app/settings.py`
- `geography/africa_context.py` (nouveau)

## Exécution

```bash
python -m cli.interactive --technical
```
