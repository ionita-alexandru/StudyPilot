# Consignes de travail — StudyPilot

## Livraison et GitHub

L'utilisateur a demandé le 19 octobre 2026 de publier le projet sur son GitHub
et de mettre le dépôt à jour après chaque modification terminée.

- Dépôt : https://github.com/ionita-alexandru/StudyPilot (privé).
- Après un changement cohérent terminé : vérifier le diff, exécuter les contrôles
  utiles au changement, créer un commit descriptif puis pousser vers `origin`.
- Vérifier que le commit distant correspond au commit livré. Annoncer clairement
  tout échec de synchronisation ; un commit local seul n'est pas une publication.
- Cette autorisation vaut pour les prochaines modifications demandées. Elle
  n'autorise ni force-push, ni effacement d'historique, ni publication de secrets.
- Préserver les modifications de l'utilisateur. Ne pas inclure de changements
  étrangers à la livraison sans les comprendre.
- Ne jamais versionner les clés API, `.env`, données de `data/` (PDF, conversations,
  cours générés, caches, quotas), environnements virtuels ou journaux. Les fichiers
  `.gitkeep` peuvent être versionnés pour conserver les répertoires vides.
- Ne jamais mettre un jeton dans l'URL du remote, la documentation ou un script.

## Produit et validation

- Améliorer le parcours pour de nouveaux cours et plusieurs disciplines ; ne pas
  adapter les règles générales uniquement aux trois cours présents localement.
- Priorités et critères de réussite : `docs/PRIORITES.md`.
- Préférer les tests de comportements utiles. Aucun appel IA payant dans la suite
  courante ; réserver les évaluations réelles aux validations explicites et bornées.
- Commandes : `python -X utf8 tests/run.py` et `node --test tests/ui.cjs`.
  `--full` inclut les régressions historiques et intégrations aux PDF locaux.
- Sous Windows, utiliser le Python de `.venv` et conserver le mode UTF-8.
