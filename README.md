# StudyPilot

Dépôt public : [ionita-alexandru/StudyPilot](https://github.com/ionita-alexandru/StudyPilot).
Les sources, ressources de l'interface et tests sont versionnés. Les PDF importés,
cours générés, conversations, caches et clés API restent locaux : un nouveau clone
démarre sans cours. Les chiffres et captures des bilans décrivent l'installation
de développement, pas des cours fournis avec le dépôt.

Chaque modification terminée et vérifiée fait l'objet d'un commit et d'un push.
Les [consignes de livraison](AGENTS.md) et les [priorités](docs/PRIORITES.md)
précisent ce fonctionnement ; aucune synchronisation en arrière-plan n'est installée.

Le parcours du cours regroupe **Apprendre**, **Mes documents** et **Ma progression**.
Le catalogue se déplie à la demande ; le chat peut être agrandi sans perdre la
discussion ni le brouillon. Les anciennes adresses restent accessibles.

La session propose désormais **Guidé**, **Express** et **Libre**, un programme
compatible avec le temps disponible, le rappel sans regarder et la reprise en pause.
**Mes documents** permet d’ajouter un PDF complémentaire avec son rôle et son périmètre.
Le [guide d’utilisation et les limites](docs/GUIDAGE_ET_COMPLEMENTS.md) détaille ce lot.

Le [bilan du parcours pédagogique du 18 octobre](docs/PARCOURS_PEDAGOGIQUE_2026-10-18.md) décrit les exercices persistants, les corrections contrôlées, la progression commune et le parcours Découvrir.

La [relecture et le nettoyage du 16 octobre 2026](docs/RELECTURE_ET_NETTOYAGE.md) détaillent les corrections des fiches, les vérifications et les archives récupérables.

Le [bilan du générateur commun et des tests](docs/GENERATEUR_ET_TESTS.md) distingue les améliorations livrées des limites révélées par les nouveaux supports d'évaluation.

StudyPilot est un assistant local de révision qui transforme un PDF de cours en un parcours structuré :

`PDF → plan et aperçus → sélection des notions et fiches courtes → contrôle → révision et chat`

Les trois cours existants proposent **74 fiches essentielles** (au lieu de 116),
avec les exemples, exercices et développements accessibles à la demande. Leurs
contenus originaux sont conservés. Chaque fiche ouvre une discussion sur sa notion.

Le [bilan des fiches courtes et du chat](docs/FICHES_COURTES_LIVRAISON.md) décrit
le parcours commun aux futurs PDF, les vérifications et les limites observées.

## Principes du projet

- Le PDF reste la source de référence.
- Les pages physiques du PDF sont conservées dans les sources.
- Aucun quota arbitraire de parties, notions ou fiches.
- Les données actives d'un cours sont regroupées par `course_id`.
- Les appels Gemma, Gemini et Ollama passent par un client IA unique.
- Les objets persistants sont versionnés avec `schema_version`.
- Une étape du pipeline peut être testée et relancée sans recalculer tout le projet.

## Architecture

```text
StudyPilot/
├── app.py                  # routes Flask
├── manage.py               # commandes développeur
├── src/
│   ├── ai/
│   │   └── client.py       # interface commune aux fournisseurs IA
│   ├── courses/
│   │   ├── service.py      # orchestration d'un cours
│   │   ├── planner.py      # construction du plan
│   │   ├── plan_manager.py # cycle de vie des plans
│   │   ├── plan_review.py
│   │   └── plan_boundaries.py
│   ├── models/             # schémas Pydantic
│   ├── pdf/
│   │   ├── ocr.py
│   │   ├── search.py
│   │   └── structure.py
│   ├── storage/
│   │   ├── course_repository.py
│   │   └── repository.py
│   ├── config.py
│   ├── part_study.py
│   └── upload_service.py
├── data/
│   ├── pdfs/               # PDF locaux
│   ├── courses/            # données canoniques par course_id
│   └── plans/              # espace de travail des plans
├── templates/
├── static/
└── tests/
```

Pour un cours actif :

```text
data/courses/<course_id>/
├── course.json
├── plan.json
├── document_sources.json # extraction PDF/OCR réutilisable
├── study_guide.json      # fiches essentielles, ressources, sources et diagnostics
├── guide_work.json       # lots déjà contrôlés, repris sans nouvel appel
├── conversations/        # discussions et exercices, liés à la version du guide
├── feedback/             # signalements locaux liés à une fiche et sa version
├── inventory.json        # ancienne collection, si présente
├── pedagogy.json         # anciens contrôles, si présents
├── cards.json            # ancienne collection, si présente
├── reviewed_cards.json    # fiches éditoriales, si disponibles
└── reviewed_coverage.json # liens entre fiches éditoriales et pages
```

## Installation locale

Python 3.12 recommandé.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Le lanceur principal utilise le fournisseur Google Gemma. Définir `GEMINI_API_KEY`
dans le terminal, puis lancer l'application sans enregistrer la clé dans un fichier :

```powershell
.\.venv\Scripts\python.exe -X utf8 lancer_studypilot.py
```

L'application est accessible sur `http://127.0.0.1:5000`. Sans clé, les fiches
existantes restent consultables ; le chat et la génération nécessitent l'API.
Le lanceur utilise `gemma-4-26b-a4b-it`, sauf configuration explicite différente.

Gemini Flash est disponible en option. L’[essai limité du 20 octobre](docs/ESSAI_IA_2026-10-20.md)
confirme l’accès à la génération, sans gain de qualité démontré sur les trois cas
simples comparés ; Gemma reste donc le choix par défaut. Le script manuel
`evaluer_assistants.py` permet de reproduire ce contrôle avec un projet gratuit
confirmé. Il n’est jamais lancé par la suite de tests.

Pour les commandes de diagnostic et de génération exécutées directement, définir
aussi le fournisseur et le modèle dans le même terminal :

```powershell
$env:STUDYPILOT_AI_PROVIDER = "gemma"
$env:STUDYPILOT_MODEL = "gemma-4-26b-a4b-it"
```

Le fournisseur Ollama reste configurable dans `src/config.py` ou avec
`STUDYPILOT_AI_PROVIDER` et `STUDYPILOT_MODEL`.

## Vérification

```powershell
python manage.py doctor
python manage.py test
python manage.py test --full
python manage.py storage status
python verifier_fiches.py
```

Les codes de sortie des commandes de traitement distinguent : `0` (succès),
`2` (incomplet), `3` (quota ou arrêt IA bloquant) et `4` (panne temporaire).
Les scripts de reprise passent au cours suivant après une panne temporaire et
conservent les checkpoints. Ils s'arrêtent sur un quota.

Les anciens installateurs, journaux, diagnostics et sauvegardes ont été sortis du
projet dans `../StudyPilot_Archives/nettoyage_20261016/`. Le manifeste de déplacement
et le bilan de relecture se trouvent dans `docs/`.

## Commandes développeur

```powershell
python manage.py plan status --course "CSS"
python manage.py plan prepare --course "mon cours"
python manage.py plan overviews --course "mon cours"
python manage.py plan publish --course "mon cours"
python manage.py storage status
python reprendre_cours.py --diagnostic-only
python terminer_cours.py --status-only
```

`reprendre_cours.py --course IDENTIFIANT` reprend un cours ;
`terminer_cours.py --minutes 30 --course-minutes 10` organise des passes bornées.
Consulter leur aide avant de lancer des traitements IA réels.

Les tests JavaScript de logique se lancent avec `node --test tests/ui.cjs`.

`manage.py test` lance le profil courant ; `--full` ajoute les régressions spécialisées et les contrôles sur les PDF locaux. Le [guide des tests](tests/README.md) distingue ces tests sans réseau de l’évaluation réelle du générateur.

Les imports conservent leur suivi dans `data/imports/`. La page d’import permet de reprendre un traitement interrompu après un redémarrage. Les étapes déjà validées sont réutilisées.

Les nouveaux aperçus comportent un résumé bref, des objectifs concrets et les notions à maîtriser. Pour mettre à niveau les anciens sans reconstruire leurs fiches :

```powershell
python manage.py refresh-overviews --course "mon cours"
```

La campagne `evaluer_import.py` exige un espace `STUDYPILOT_DATA_DIR` isolé, `--live` et des budgets. Un import techniquement terminé ne garantit pas à lui seul la qualité pédagogique sur tout document.
