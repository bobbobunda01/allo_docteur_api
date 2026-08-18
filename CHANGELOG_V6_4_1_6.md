# AlloDocteur V6.4.1.6 — P3/P4 Semantic Alignment

- P3 = consultation médicale/spécialisée programmée réellement recommandée.
- P4 = conseils/autosurveillance, sans consultation actuellement requise.
- Si le LLM renvoie P4 mais recommande explicitement une consultation actuelle dans `orientation`, le backend corrige uniquement P4 -> P3.
- Les recours conditionnels (« si persistance », « si aggravation ») restent compatibles avec P4.
- Un P4 spécialisé n'affiche plus automatiquement « Consultation programmée en ... ».
- La Safety P1, la logique P2, le questionnaire et le catalogue des spécialités restent inchangés.
- Traçabilité : `metadata.semantic_priority_adjustment_p4_to_p3`.
