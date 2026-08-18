# AlloDocteur V6.4 — Clinical & Epidemiological Safety

V6.4 renforce la sécurité clinique sans modifier le questionnaire existant ni la structure publique principale de l'API.

## Principes

1. **Le questionnaire existant est conservé** : aucune nouvelle question obligatoire n'est imposée au patient.
2. **Le LLM reste le moteur de raisonnement clinique** pour les cas non arrêtés en P1 : synthèse, P2/P3/P4, spécialité, hypothèses prudentes, contradictions, contexte épidémiologique et incertitude.
3. **La sécurité vitale ne dépend pas du LLM** : questionnaire + Clinical Text Safety V2 + Population Safety peuvent imposer P1 localement.
4. **L'épidémiologie module le risque, jamais le diagnostic** : seules les alertes explicitement fournies et datées sont utilisées. Les alertes anciennes (>30 jours) ne relèvent pas la priorité.
5. **Mode dégradé conservateur** : si le LLM est indisponible, un danger local reste P1 ; sinon le fallback applique P2 + revue humaine plutôt que de rassurer artificiellement.

## Nouveaux modules

- `clinical/text_safety_gate.py` — concepts cliniques, variantes lexicales et négations.
- `clinical/population_safety_gate.py` — pédiatrie, grossesse et prudence gériatrique.
- `clinical/epidemiology_safety_gate.py` — alertes sanitaires fournies, datation, compatibilité symptomatique et précautions de contrôle de l'infection.
- `llm/fallback.py` — fallback safety-only conservateur.
- `llm/schemas.py` — contrat V6.4 : incertitude, revue humaine, notes épidémiologiques et précautions infection-control.

## Architecture

```text
Questionnaire inchangé
        |
        +--> Severity Gate --------------------+
        |                                      |
Texte --> Clinical Text Safety V2 ------------+----> P1 immédiat si danger
        |                                      |
Patient -> Population Safety -----------------+
        |
        +--> Epidemiology Safety (plancher P2 / revue)
        |
        +--> LLM Clinical Reasoning (P2/P3/P4 + détection secondaire P1)
                         |
                         v
                   Safety Fusion
```

## Tests

- Suite pytest : **43 tests réussis**.
- Stress-test transversal : **110 domaines médicaux**.
- Red flags locaux : **110/110 détectés** dans le corpus de stress contrôlé.
- Fallback P1 : **110/110** pour ces mêmes red flags explicites.

Ces résultats démontrent la couverture logicielle du corpus de test, **pas une sensibilité clinique réelle de 100 % dans la population**. Une validation par cliniciens, des scénarios indépendants et une évaluation prospective restent indispensables avant usage médical réel.

## Lancement

Les commandes restent celles de V6.3. Exemple :

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Le fichier `.env` conserve les paramètres OpenAI existants. Le LLM peut être désactivé pour tester le mode dégradé.

---

## Patch V6.4.1 — Safety Hardening

La version courante du package est **6.4.1**. Le questionnaire et l'API publique restent compatibles avec V6.4. Le patch renforce uniquement les garde-fous déterministes autour du LLM à partir des erreurs observées dans CVB-1000.

Pour lancer les tests :

```bash
pytest -q
```

Pour relancer le benchmark clean :

```bash
PYTHONPATH=. python scripts/clinical_benchmark_1000.py benchmark/allodocteur_cvb_1000_clean.jsonl
```

Les résultats de validation se trouvent dans `benchmark_results_v641/` et `benchmark_results_v641_clean/`.
