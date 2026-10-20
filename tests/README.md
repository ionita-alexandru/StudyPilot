# Vérifier StudyPilot

## Travail courant

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py test
node --test tests/ui.cjs
```

Le résumé de chaque commande indique le nombre de tests effectivement exécutés et leur résultat ; ce nombre évolue avec la suite et n'est pas figé ici. Les scénarios de `test_study_guide.py` couvrent le nouveau parcours sans appel IA : références, couverture, correction bornée, reprise, contexte conversationnel, exemple sans génération, calculs contrôlés, budget et préservation des originaux. Les contrôles du tuteur couvrent aussi les verdicts, exercices et réponses ambiguës.

La suite courante sélectionne les risques communs : stockage, import, navigation, contrats IA, sources inventées, omissions, fiches, transcription des formules et reprise après interruption. Les réponses de génération sont simulées ; aucun résultat pédagogique réel n'est prétendu.

## Avant livraison d'un changement du générateur

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py test --full
```

Ce profil ajoute les cas historiques de récupération des sources, de migration des caches, de limites de débit et les intégrations avec les PDF locaux. Les cas liés à ces PDF ne prouvent pas la généralisation à d'autres disciplines. La découverte directe `python -m unittest discover -s tests` conserve la même suite complète.

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

Le manifeste `docs/reorganisation_tests.json` justifie chaque retrait et renommage. Les variantes mathématiques regroupées sont toujours exercées. La suite complète reste disponible : le profil courant n'est pas présenté comme la suppression des autres scénarios.
