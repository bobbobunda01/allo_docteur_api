# V6.4.1.2 — LLM Specialty Routing

- Le LLM devient source principale de la spécialité pour P2/P3/P4.
- Le backend valide la spécialité mais ne force plus Médecin généraliste pour P3/P4.
- Médecin généraliste reste le fallback si la spécialité LLM est invalide/absente.
- Le routage P1 et les règles de sécurité restent inchangés.
