# AlloDocteur — Lot 5 indépendant

## But
Hold-out après V6.4.1.6. Ne pas utiliser ce lot pour modifier le moteur avant d'avoir enregistré les résultats initiaux.

## Taille
- 200 cas
- 100 domaines/sous-domaines
- 2 cas par domaine
- 50 P1 / 50 P2 / 50 P3 / 50 P4

## Règles d'analyse
Toujours publier séparément :
1. métriques globales ;
2. LLM-only ;
3. fallback-only ;
4. P1 sensitivity et specificity ;
5. matrice P1/P2/P3/P4 ;
6. spécialité acceptable ;
7. orientation ;
8. erreurs par domaine ;
9. timeout/fallback.

## Critère de sécurité
Un échec P1 en fallback ne doit jamais être masqué par la performance LLM-only.

IMPORTANT : ce fichier constitue un squelette de benchmark technique. Les gold labels et formulations cliniques doivent être relus/validés par un clinicien avant toute utilisation comme preuve de sécurité clinique.
