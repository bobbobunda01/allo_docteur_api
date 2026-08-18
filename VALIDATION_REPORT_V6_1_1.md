# Rapport de validation — AlloDocteur V6.1.1

## Corrections

- Budget de sortie OpenAI porté à 1200 tokens.
- Effort de raisonnement réglé sur `minimal`.
- Verbosité de sortie réglée sur `low`.
- Schéma Structured Outputs réduit à 7 champs.
- Prompt limité à 45 mots de synthèse, 2 hypothèses, 3 raisons, 2 actions et 4 signes d'aggravation.
- Journalisation de `input_tokens`, `output_tokens`, `reasoning_tokens` et `total_tokens`.
- Les champs techniques supprimés du schéma LLM sont complétés par le backend.

## Vérifications exécutées

- Compilation de tous les fichiers Python : réussie.
- Tests automatisés : 29 réussis.
- Simulation complète du CLI en mode fallback : réussie.
- Affichage patient et JSON API : vérifiés.

## Configuration recommandée

```env
OPENAI_MAX_OUTPUT_TOKENS=1200
OPENAI_REASONING_EFFORT=minimal
OPENAI_TEXT_VERBOSITY=low
OPENAI_READ_TIMEOUT_SECONDS=30
OPENAI_MAX_RETRIES=0
```
