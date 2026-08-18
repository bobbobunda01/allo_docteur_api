# AlloDocteur — Lot 4B

Version cible : V6.4.1.4 — Composite Safety Patterns

150 cas hold-out :
- 50 P1
- 40 P2
- 35 P3
- 25 P4

Le rapport sépare :
- overall
- llm_only
- fallback_only

Exécution :
```bash
export OPENAI_MODEL="gpt-5-mini"
python test_batch_04b.py
```

Sorties :
- batch_04b_gpt5mini_results.json
- batch_04b_gpt5mini_results.csv
- batch_04b_gpt5mini_summary.json
- batch_04b_p1_false_negatives.json
- batch_04b_priority_errors.json
