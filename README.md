# Lot 5 — AlloDocteur V6.4.1.6

Le runner reprend directement la logique de `test_batch_04b.py` fournie par l'utilisateur :
- chargement `.env`;
- `IntakeAnswers.model_validate(case["input"])`;
- `TriageService`;
- métriques overall / llm_only / fallback_only;
- sensibilité et spécificité P1;
- matrice de confusion;
- résultats par priorité;
- fichiers séparés des faux négatifs P1 et erreurs de priorité.

## Exécution
Placez `test_batch_05.py` et `batch_05_cases.json` à la racine du projet V6.4.1.6.

```bash
export OPENAI_MODEL="gpt-5-mini"
python test_batch_05.py
```

## Important
Ce benchmark est destiné à l'évaluation technique du moteur. Les gold labels synthétiques doivent être relus et validés par un clinicien avant d'être utilisés comme preuve de sécurité clinique ou pour une décision de mise en production.
