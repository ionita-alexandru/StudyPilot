# Points d'entrée StudyPilot

Lire la ligne utile, vérifier les symboles avec `rg -n`, puis suivre les appels.
Les fichiers peuvent évoluer ; ne pas déduire une couverture complète de cette liste.

| Sujet | Code de départ | Tests de départ |
| --- | --- | --- |
| Chat, contexte, exercice | `src/tutor.py`, `src/part_study.py`, `src/learning_tutor.py` | `tests/test_chat_api.py`, `tests/test_learning_tutor.py`, `tests/test_part_study.py` |
| Génération, sources | `src/courses/guide_generation.py`, `src/courses/study_guide.py`, `src/courses/card_grounding.py` | `tests/test_study_guide.py`, `tests/test_source_quality.py`, `tests/test_generation_contracts.py` |
| Import, compléments | `src/upload_service.py`, `src/course_documents.py` | `tests/test_upload_service.py`, `tests/test_course_documents.py` |
| Navigation, rendu | `app.py`, `src/learning_view.py`, `src/courses/card_presentation.py`, `static/learning_shell.js` | `tests/test_app_navigation.py`, `tests/test_card_presentation.py`, `tests/ui.cjs` |
| Programme, temps, progression | `static/study_plan.js`, `static/study_progress.js`, `static/revision.js` | `tests/ui.cjs` |
| Fournisseurs et budgets | `src/ai/client.py`, `src/ai/gemma.py`, `src/ai/gemini.py`, `src/ai/workload.py` | `tests/test_gemma_provider.py`, `tests/test_gemma_sdk.py`, `tests/test_quota_stop.py` |
| Stockage | `src/storage/repository.py`, `src/storage/course_repository.py` | `tests/test_storage_atomic.py`, `tests/test_course_repository.py` |

Test Python ciblé, depuis la racine (exemple) :

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p test_chat_api.py
```

Commandes de livraison et périmètres : `AGENTS.md`, `tests/README.md`, `tests/run.py`.
Pour une modification du générateur, respecter aussi le profil complet demandé par `tests/README.md`.
