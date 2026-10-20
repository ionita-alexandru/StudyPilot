# Skills et sous-agents pour StudyPilot

Mis en place et essayés le 20 octobre 2026. Ce sont des aides au développement
dans Codex, pas des agents ajoutés au chatbot de StudyPilot. Ils ne nécessitent
aucun nouvel appel au fournisseur de l'application.

## Ce qui est installé dans le dépôt

| Outil | Utilité | Quand le demander |
| --- | --- | --- |
| `$studypilot-change` | Repérer les fichiers utiles, reproduire et vérifier un changement | Correction ou amélioration de StudyPilot |
| `$studypilot-source-review` | Comparer une fiche aux passages fournis | Vérifier fidélité, conditions, exemples ou source absente |
| `studypilot_reviewer` | Revue indépendante de code, tests ou documentation | Une question précise mérite un second regard |
| `studypilot_source_auditor` | Revue indépendante d'un petit dossier source/candidat | Une comparaison pédagogique mérite un second regard |

Un **skill** est une procédure réutilisable : instructions dans `SKILL.md`,
et ressources lues seulement si nécessaires. Il guide l'agent qui travaille déjà.
Un **sous-agent** est un autre agent chargé d'une mission délimitée, qui renvoie
son résultat à l'agent principal. Il consomme aussi du contexte et des tokens.
Le sous-agent peut appliquer le skill : les deux objets ne sont pas équivalents.

Les skills sont dans `.agents/skills/`. Les rôles sont dans `.codex/agents/`.
Les TOML n'imposent ni modèle ni effort de raisonnement ; ils héritent du parent.
La lecture seule est une instruction de rôle, pas une sandbox indépendante.
Les autorisations restent celles du parent.

Le catalogue de skills est chargé par l'hôte. Si un nom n'apparaît pas encore,
ouvrir une nouvelle conversation du projet ou demander explicitement la lecture
du chemin de son `SKILL.md`. Ne pas confondre un fichier présent avec son
chargement automatique effectivement observé.

## Première utilisation, avec le candidat aux commandes

Copier l'une de ces demandes dans la conversation du projet :

```text
Utilise $studypilot-change pour me montrer où le chat sélectionne ses sources.
Ne modifie rien. Explique le trajet et indique un test utile.
```

```text
Utilise $studypilot-source-review sur les cas synthétiques de
.agents/skills/studypilot-source-review/references/practice.json.
Avant la revue, laisse-moi proposer mon verdict sur le premier cas.
```

Pour déléguer explicitement :

```text
Confie au sous-agent studypilot_source_auditor la comparaison de cette fiche
avec ces passages. Lecture seule, pas d'API ni de cours supplémentaires.
Rassemble ses conclusions et vérifie-les avec moi.
```

Fournir la fiche, le passage et l'objectif dans la même demande. Exemple :
« vérifier que les conditions de la formule sont conservées ».
Une tâche ne justifie pas nécessairement plusieurs agents.

## Ce qui a été essayé ici

Deux sous-agents indépendants ont reçu des missions courtes sans l'historique
complet de la conversation. Chacun a lu les instructions du rôle et le skill
depuis les fichiers. Ce test vérifie leur usage par chargement explicite ; il
ne prouve pas la sélection automatique des noms de rôle par le client.

**Revue des tests.** Le premier a comparé `tests/README.md`, `tests/run.py` et
`tests/ui.cjs`, suivi le relais de commande dans `manage.py`, puis exécuté :

```powershell
.\.venv\Scripts\python.exe -X utf8 tests/run.py
node --test tests/ui.cjs
```

Résultat : 123 tests Python courants réussis et 8 tests JavaScript réussis.
La documentation annonçait encore 117 et 6. L'agent principal a confirmé le
constat et remplacé les comptes figés par une lecture du résumé de commande.
Le code applicatif n'a pas été modifié. Ni `--full` ni évaluation IA réelle.

**Revue pédagogique.** Le second a traité trois cas synthétiques, sans lire
`data/`, sans lancer StudyPilot et sans génération réelle :

| Cas | Conclusion vérifiée par l'agent principal |
| --- | --- |
| Somme géométrique annoncée pour tout `q` | À corriger : conserver `q != 1`, `n` entier naturel et le cas `q = 1` fourni par la source |
| Reformulation de `return` et `print` | Étayée pour l'objectif de distinction renvoi/affichage |
| Durée du cache sans source | Non vérifiable ; demander le passage manquant |

Ces candidats sont des exemples d'exercice, pas des erreurs mesurées dans les
fiches actuelles. Le résultat ne valide ni toutes les matières ni toute l'application.
La validation structurelle des deux skills, le parsing des deux TOML et
l'existence des 38 chemins de la carte ont aussi été contrôlés.

## Contexte et coût : ce que l'on sait

- Les deux `SKILL.md` contiennent respectivement 263 et 256 mots à cette date.
  Ce sont des tailles de texte, pas des mesures de tokens facturés.
- Leur description permet une sélection ciblée ; le corps et les références
  ne doivent être chargés que lorsque la tâche le nécessite.
- La carte des fichiers évite de repartir d'une exploration générale ; elle
  n'exonère pas de suivre une dépendance pertinente et doit rester à jour.
- Les rôles visent un retour bref et ne délèguent pas à nouveau. Pas d'essaim
  automatique, pas de duplication de toute la conversation dans chaque mission.
- Un sous-agent supplémentaire peut augmenter le coût total même s'il réduit
  le temps d'attente ou le contexte du principal. Aucun pourcentage d'économie,
  tarif ou gain de qualité général n'a été mesuré ici.

Pour mesurer un gain, comparer des tâches équivalentes avec même modèle et même
critère de réussite, avec/sans le dispositif. Relever tokens si le client les
expose, temps et erreurs/révisions nécessaires. Une réponse plus courte ne suffit
pas à prouver une économie totale. Pour une petite correction évidente, l'agent
principal seul est souvent le choix le plus simple.

## Recherche et choix

Sources consultées le 20 octobre 2026 ; instructions locales originales, sans
copie ni exécution des scripts des dépôts tiers.

| Source | Ce qui a servi au choix |
| --- | --- |
| [OpenAI Skills sur GitHub](https://github.com/openai/skills) | Catalogue de référence ; pas d'installation en bloc |
| [Skill Creator d'Anthropic sur GitHub](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) | Ressources chargées à la demande et essai sur des requêtes concrètes |
| [Superpowers : tâches parallèles indépendantes](https://github.com/obra/superpowers/blob/main/skills/dispatching-parallel-agents/SKILL.md) | Missions étroites, contraintes et retour explicite ; pas de délégation pour étapes dépendantes |
| [Documentation officielle des skills](https://learn.chatgpt.com/docs/build-skills) | Format, chargement progressif et emplacement `.agents/skills` |
| [Documentation officielle des sous-agents](https://learn.chatgpt.com/docs/agent-configuration/subagents) | Rôles TOML du projet et héritage des permissions/configurations |

Deux skills propres au dépôt ont été préférés à un paquet générique complet :
ils réutilisent les commandes et les règles réelles de StudyPilot sans imposer
un autre workflow au projet. Ce choix est adapté à ce premier essai ; aucune
supériorité universelle sur les sources étudiées n'est prétendue.

La préparation d'entretien personnelle reste hors du dépôt public. Le PDF n'est
pas modifié par cette livraison. On y ajoutera l'expérience seulement après
compréhension et usage par le candidat.
