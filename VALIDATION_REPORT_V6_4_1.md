# AlloDocteur V6.4.1 — Safety Hardening Validation Report

## Objet

V6.4.1 corrige les insuffisances mises en évidence par le Clinical Validation Benchmark CVB-1000 de V6.4, sans modifier le questionnaire public, les priorités P1–P4 ni le rôle du LLM pour le raisonnement clinique riche.

## Corrections principales

- Extension du Clinical Text Safety Gate aux paraphrases, fautes fréquentes et formulations naturelles observées dans le CVB-1000.
- Renforcement de la détection de : confusion aiguë, déshydratation sévère, abdomen rigide douloureux, intoxication, hémorragie, détresse respiratoire, diarrhée sévère avec impossibilité de boire, AVC, traumatisme et brûlure.
- Gestion plus stricte des négations locales.
- `fièvre + raideur de nuque` devient un concept composite : une fièvre positive et un signe méningé positif sont requis.
- `fièvre + éruption` exige désormais un caractère étendu/marqué ou une forte fièvre ; « quelques boutons avec état général conservé » n'est plus automatiquement P1.
- Les règles pédiatriques et obstétricales utilisent elles aussi la détection positive avec négation locale.
- Le LLM reste inchangé dans son rôle : raisonnement clinique, différentiel prudent, spécialité, P2/P3/P4, contradictions, incertitude et contexte épidémiologique.

## Tests automatisés

- Pytest : **51/51 réussis**.
- Les tests historiques V6.4 restent tous verts.
- De nouveaux tests de régression couvrent les formulations responsables des faux négatifs/faux positifs CVB-1000.

## CVB-1000 original

Le même corpus ayant révélé la faiblesse initiale a été relancé après correction :

- Sensibilité P1 : **100,0 %** (500/500)
- Sous-triage P1 : **0,0 %**
- Spécificité P1 : **99,2 %** (496/500)
- Sur-triage P1 : **0,8 %**

Les 4 faux positifs restants provenaient tous d'une fuite d'étiquette du générateur : la plainte commençait par « Dans le contexte de traumatisme crânien: ... », ce qui introduisait artificiellement le nom d'un red flag dans le texte patient.

## CVB-1000 Clean

Une copie du corpus a été produite en supprimant uniquement le préfixe artificiel « Dans le contexte de <domaine>: » tout en conservant symptômes, profils patients, contexte épidémiologique et étiquettes attendues.

Résultats :

- Sensibilité P1 : **100,0 %** (500/500)
- Spécificité P1 : **100,0 %** (500/500)
- Sous-triage : **0,0 %**
- Sur-triage : **0,0 %**
- LLM utilisé : **0 cas**, faute de clé OpenAI dans l'environnement de validation.

## Interprétation indispensable

Ces résultats constituent des **tests de régression logicielle**, pas une mesure indépendante de performance clinique. Le CVB-1000 a servi à identifier les défauts puis à guider les corrections ; il ne doit donc pas être utilisé comme unique preuve de généralisation.

Avant toute mise en production clinique, il reste nécessaire de :

1. faire relire et annoter le Gold Standard par plusieurs cliniciens ;
2. créer un benchmark hold-out gelé, jamais utilisé pour modifier les règles ;
3. évaluer séparément la performance du LLM avec une clé/API réelle ;
4. réaliser une validation prospective sur cas représentatifs réels ou rétrospectifs dé-identifiés ;
5. évaluer la robustesse multilingue et les formulations locales africaines.

## Conclusion

V6.4.1 corrige les erreurs reproductibles du CVB-1000 et restaure une couche P1 locale beaucoup plus robuste. Elle doit être considérée comme une **version de durcissement technique candidate à une nouvelle validation indépendante**, et non comme un dispositif médical validé.
