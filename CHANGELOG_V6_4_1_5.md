# V6.4.1.5 — Specialty Routing & Priority Calibration

## Objectif
Corriger les erreurs observées au Lot 4B sans modifier les garde-fous P1 de V6.4.1.4.

## Modifications
1. Découplage gravité / spécialité pour P1 : la spécialité LLM valide prime quand le LLM a réellement traité le cas ; le mapping déterministe reste le filet de sécurité et reste prioritaire en fallback.
2. Calibration contextuelle du routage : obstétrique, toxicité, ORL/dentaire, allergologie, vasculaire, urologie et néphrologie.
3. Calibration P2/P3/P4 : céphalée nouvelle inhabituelle, plaintes chroniques stables, plaintes bénignes/transitoires, oreille bouchée après baignade.
4. Cohérence renforcée entre priorité et orientation.

## Invariants
- Aucun changement des Composite Safety Patterns P1.
- Aucun changement du questionnaire.
- Aucun changement du schéma JSON public.
- Aucun changement du catalogue des spécialités.
