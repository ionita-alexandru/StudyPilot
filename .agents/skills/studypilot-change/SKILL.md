---
name: studypilot-change
description: "Repérer le code et les tests utiles pour corriger ou améliorer StudyPilot, puis vérifier le comportement modifié."
---

# Changement ciblé StudyPilot

Appliquer les consignes AGENTS.md du dépôt ; ce skill ne les remplace pas.

1. Formuler le comportement attendu et le symptôme observé. Vérifier le diff local.
2. Lire seulement la ligne pertinente de [la carte](references/code-map.md), puis rechercher le symbole avec `rg -n` et lire son voisinage. La carte est un point de départ, pas un graphe exhaustif.
3. Reproduire le problème avec un cas minimal. Pour une correction logicielle, protéger le comportement utile ; éviter les assertions qui figent uniquement le texte ou une implémentation.
4. Modifier le minimum nécessaire. Lancer les tests ciblés, puis les contrôles requis par le changement. Le profil courant est `tests/run.py` ; `--full` couvre aussi les régressions historiques/PDF locaux. Utiliser `.venv` et `-X utf8` sous Windows. Les tests courants ne doivent pas appeler un fournisseur réel.
5. Rapporter : changement, preuve observée et limite restante. Compter les tests depuis leur sortie, jamais depuis un chiffre figé en documentation. Suivre la livraison Git prévue dans AGENTS.md.

## Contexte et délégation

Ne pas relire tout le dépôt ou tout l'historique. Élargir si les appels ou les résultats le nécessitent ; ne pas sacrifier une dépendance utile pour réduire le contexte.
Pour une revue indépendante justifiée, utiliser le rôle `studypilot_reviewer` sous `.codex/agents/`, avec la question, les chemins concernés et les contraintes. Une tâche courte ou des étapes dépendantes restent dans l'agent principal. Un agent supplémentaire consomme aussi des tokens ; ne pas le lancer systématiquement.
