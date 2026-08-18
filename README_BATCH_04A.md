# AlloDocteur — Evaluation Batch 04A

Version cible : V6.4.1.2 — LLM Specialty Routing

Composition :
- 50 P1
- 25 P2
- 15 P3
- 10 P4

Nouveauté majeure :
le runner attribue une cause probable aux faux négatifs P1 afin d'identifier
si l'échec vient du Safety local, du LLM, du fallback ou de la fusion.

Exécution :
1. Copier `test_batch_04a.py` et `batch_04a_cases.json` à la racine du projet.
2. Vérifier OPENAI_API_KEY.
3. Lancer :

```bash
export OPENAI_MODEL="gpt-5-mini"
python test_batch_04a.py
```

Sorties :
- batch_04a_gpt5mini_results.json
- batch_04a_gpt5mini_results.csv
- batch_04a_gpt5mini_summary.json
- batch_04a_p1_false_negatives.json

Cibles :
- Sensibilité P1 >= 95 %
- Aucun P1 classé P3/P4
- Spécificité P1 >= 90 %
- Priorité globale >= 90 %
- Spécialité acceptable >= 90 %

La baseline ChatGPT-as-LLM est une baseline de calibration, non une validation clinique indépendante.
