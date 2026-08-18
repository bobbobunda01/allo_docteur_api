# AlloDocteur — Lot 6 Clinical Validation Benchmark

## Composition
- 300 cas synthétiques
- 100 domaines/sous-domaines
- 3 cas par domaine
- distribution des priorités attendues : {'P1': 50, 'P2': 99, 'P3': 89, 'P4': 62}

## Différence essentielle avec Lot 5
Le Lot 6 ne considère plus toute différence de niveau comme une erreur clinique.

Chaque cas contient :
- `expected_priority` : niveau préféré ;
- `acceptable_priorities` : niveaux encore médicalement acceptables dans ce scénario ;
- `accepted_specialties` : plusieurs filières acceptables ;
- `clinical_rationale` : justification courte du Gold ;
- `validation_status=synthetic_gold_requires_clinician_review`.

Le runner calcule :
- strict priority accuracy ;
- clinical priority acceptability ;
- P1 sensitivity / specificity ;
- dangerous undertriage rate ;
- specialty acceptability ;
- orientation accuracy ;
- métriques LLM-only et fallback-only.

## Erreur dangereuse
Le runner marque `dangerous_undertriage=true` lorsque :
1. un P1 attendu sort en P2/P3/P4 ; ou
2. le système sous-trie de deux niveaux ou plus.

## Exécution
Copier `test_batch_06.py` et `batch_06_cases.json` à la racine de V6.4.1.6 :

```bash
export OPENAI_MODEL="gpt-5-mini"
python test_batch_06.py
```

## Fichiers générés
- `batch_06_gpt5mini_results.json`
- `batch_06_gpt5mini_results.csv`
- `batch_06_gpt5mini_summary.json`
- `batch_06_p1_false_negatives.json`
- `batch_06_dangerous_errors.json`
- `batch_06_priority_errors.json`

## Critères proposés avant gel d'une version
À interpréter après revue clinique :
- P1 sensitivity >= 95 %
- P1 specificity >= 90 %
- dangerous undertriage rate < 2 %
- clinical priority acceptability >= 90 %
- aucun P1 -> P3/P4
- specialty acceptability >= 85 % sur LLM-only

## Important
Ce benchmark est un outil d'ingénierie et de pré-validation. Les Gold Standards
sont synthétiques et doivent être revus par un ou plusieurs cliniciens avant
d'être utilisés comme preuve de sécurité clinique ou comme base d'une mise en production.
