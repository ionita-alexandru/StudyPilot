# Vérifier StudyPilot

## Travail courant

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py test
node --test tests/ui.cjs
```

Le profil courant vérifie les comportements qu'on veut protéger à chaque changement.
Il utilise des données d'essai et simule les réponses des fournisseurs IA.

| Ce que l'on vérifie | Pourquoi cela compte | Exemples de tests |
| --- | --- | --- |
| Reprise d'un import ou d'un plan après une interruption | L'étudiant ne recommence pas tout et les travaux déjà validés restent disponibles. | `test_upload_service.py`, `test_course_planner.py` |
| Références et couverture avant publication | Une fiche rattachée à une source inexistante ou un lot qui laisse des passages sans décision doit être refusé. | `test_study_guide.py` |
| Verdicts de l'assistant et contexte actif | Un calcul vérifiable peut être contrôlé, une réponse ambiguë garde son incertitude et le chat suit la notion choisie. | `test_learning_tutor.py`, `test_chat_api.py` |
| Rendu des fiches, du code et des formules | Une formule reste entière, le code garde sa syntaxe et le HTML du contenu est affiché comme texte. | `test_card_presentation.py`, `test_presentation_quality.py` |
| Limite d'utilisation du fournisseur | Un refus de quota arrête le traitement au lieu de consommer de nouvelles tentatives. | `test_quota_stop.py` |
| Parcours et bilan de révision | Le planning respecte le temps annoncé et chaque fiche compte une fois dans le bilan. | `ui.cjs` |

## Avant livraison d'un changement du générateur

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py test --full
```

Ce profil ajoute les cas historiques de récupération des sources, de migration des caches, de limites de débit et les intégrations avec les PDF locaux. La découverte directe `python -m unittest discover -s tests` exécute la même suite complète.

Deux exemples montrent pourquoi des tests historiques se ressemblent. Un refus de
quota doit arrêter les requêtes HTTP, interrompre la recherche de preuves et
empêcher le démarrage du cours suivant. Ces trois erreurs se produiraient à des
endroits différents. Pour l’inventaire d’un cours, un autre groupe de tests vérifie
que la réponse a la forme attendue, que les preuves viennent du document et que
l’application indique au générateur quoi corriger après un rejet.

### Quand un test est ignoré

Le lanceur affiche le nom et la raison de chaque saut, y compris en mode court.
Les sauts restants concernent des ressources locales hors Git. Ils couvrent les
frontières de chapitres d'un PDF CSS précis, des régressions de récupération et
de validation de ses fiches, ou la pertinence du découpage et des sources sur des
PDF de mathématiques. Une copie publique peut exécuter les scénarios reproductibles
et signaler ces intégrations comme ignorées si leurs fichiers sont absents.

Une dépendance obligatoire manquante, comme Flask, doit faire échouer la suite.
Lorsqu'un comportement général se vérifie sur un PDF d'essai, utiliser ce PDF.
La validation d'un plan continu et la reprise d'un plan sauvegardé utilisent
ainsi des PDF créés par les tests. Le résumé indique les tests exécutés et les sauts.

## Évaluation réelle, séparée des tests

`evaluer_import.py` appelle réellement le fournisseur configuré et utilise les mêmes fonctions d'import et de génération que l'application. Il exige `--live`, un répertoire `STUDYPILOT_DATA_DIR` isolé et impose un budget d'appels et de durée. Le budget est partagé équitablement entre les cas sélectionnés. Les checkpoints permettent une reprise ; les données personnelles et les fiches éditoriales ne sont pas utilisées. Le schéma de la collection reste contrôlé même en cas d'interruption.

```powershell
$env:STUDYPILOT_DATA_DIR = 'C:\StudyPilotProject\StudyPilot_Archives\evaluation'
# Définir le fournisseur, le modèle et la clé dans l'environnement du terminal.
.\.venv\Scripts\python.exe -X utf8 evaluer_import.py --corpus 'C:\chemin\corpus' --output 'C:\chemin\rapport.json' --live --max-calls 60 --minutes 12
```

Le rapport distingue `ready`, `partial`, `interrupted`, les appels employés et les cas non tentés. Un état `ready` doit encore être confronté au PDF : fidélité, couverture des notions, absence de redondance, clarté des explications, rendu des formules et du code. Le nombre de fiches n'est pas une note de qualité. Les supports synthétiques sont décrits dans `fixtures/generalisation.json` ; aucun résultat IA attendu n'y est préécrit.

## Entretien de la suite

Chaque test doit protéger un comportement ou un risque distinct. Regrouper les variantes d'une même règle avec `subTest`, sans effacer leurs assertions. Éviter les tests qui figent seulement un nom de champ interne ou reproduisent le code testé. Une régression historique se conserve si le bug peut revenir ; son nom décrit désormais le comportement, sans numéro de version.

Le manifeste `docs/reorganisation_tests.json` documente la réorganisation historique. Les variantes regroupées restent exercées et chaque échec d'un `subTest` indique le cas concerné.
