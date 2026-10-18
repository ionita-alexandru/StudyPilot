# Génération commune et tests — 16 octobre 2026

> Bilan historique de la première refonte. Le parcours actif et les résultats actualisés sont décrits dans [Fiches courtes et chat](FICHES_COURTES_LIVRAISON.md).

## Changements appliqués

La vue d'ensemble possède maintenant un contrat commun à toutes les matières : résumé de 55 mots maximum sans équation, capacités à acquérir, notions, prérequis et utilité éventuelle. Les réponses non conformes sont renvoyées au modèle une fois, avec un diagnostic précis ; elles ne sont plus tronquées au milieu d'une formule ou d'une explication. Les aperçus ont une version de contenu : un ancien `draft` ne suffit plus à éviter la mise à niveau.

Les 16 aperçus des trois cours existants ont été régénérés automatiquement par ce mécanisme. Dans l'interface, les objectifs sont distincts du résumé ; les prérequis et l'utilité sont dépliables. Les notations des listes utilisent le même rendu HTML échappé et MathJax que les fiches. La commande `manage.py refresh-overviews --course ...` permet de mettre à niveau un cours sans reconstruire ses fiches.

Plusieurs défauts du parcours commun ont été corrigés à partir de nouveaux documents :

- Le détecteur de notations ne découpe plus les mots accentués en pseudo-symboles. « Géométrique » créait notamment de fausses obligations de notation et pouvait faire rejeter une preuve correcte.
- Le plan et les aperçus passent par le même parseur JSON que les fiches. Le LaTeX mal échappé est protégé ; les clés JSON répétées sont rejetées, pour éviter que la dernière liste de notions écrase silencieusement les précédentes.
- Les lignes pédagogiques commençant par « Exemple » ou « Résultat » sont conservées dans les preuves. Le signal utilisé pour rechercher les frontières des parties reste séparé, afin que cette correction ne dégrade pas le découpage des cours existants.
- Une fin de ligne physique coupant manifestement une phrase peut être complétée par copie de sa continuation immédiate. La sélection initiale est conservée dans la trace. Une nouvelle rubrique, du code ou une borne invalide ne sont pas absorbés ; une sélection encore ambiguë doit être reprise et l'audit de portée reste nécessaire.
- Un exemple mathématique introduit par « Exemple : » n'est plus assimilé à une déclaration de code. L'absence d'extrait de programmation n'interdit plus de restituer les formules du cours en LaTeX.
- Les consignes de génération demandent des sections adaptées à la notion et évitent les formules décoratives dans les documents rédactionnels.

Les fichiers `reviewed_cards.json` et `reviewed_coverage.json` n'ont pas été modifiés pendant cette intervention. Les inventaires, fiches automatiques et préparations pédagogiques des trois cours personnels ont également été préservés. Seuls leurs plans ont reçu les nouveaux aperçus ; les plans de travail correspondant au même PDF et aux mêmes parties ont été synchronisés. Des sauvegardes précèdent ces mises à niveau.

## Imports reprenables

Les états d'import sont désormais enregistrés atomiquement dans `data/imports/`. Au redémarrage, un traitement auparavant actif est signalé comme interrompu. Le bouton « Reprendre l'analyse » remet le même import dans la file et réutilise le PDF ainsi que les checkpoints du parcours commun.

La page de suivi retrouve l'import après rechargement, distingue les étapes de plan, de notions et de fiches, et permet de consulter un résultat partiel sans le présenter comme terminé. Le parcours depuis l'accueil utilise cette même page. Une reprise simultanée ou un chemin PDF hors du dossier autorisé sont refusés.

La vue des fiches garde aussi visibles les cours dont aucune fiche n'a encore été publiée, indique la préparation incomplète et désactive une révision vide. L'étiquette de matière déduite du nom « CSS ou mathématiques » a été supprimée : les nouveaux documents ne reçoivent plus une discipline inventée.

## Tests recentrés

Huit méthodes redondantes ou sans contrôle utile ont été retirées ou regroupées. Les variantes de rendu mathématique et les garanties de non-adoption d'un plan restent vérifiées dans leurs familles respectives. Sept anciens fichiers portent des noms descriptifs plutôt que des numéros de version. Le [manifeste](reorganisation_tests.json) justifie les changements.

La commande courante sélectionne les contrats et risques communs ; la suite complète ajoute les régressions spécialisées et les PDF locaux. Les nouveaux tests protègent les bugs effectivement rencontrés, la conservation des données lors d'une mise à niveau et la reprise d'un import. La suite JavaScript vérifie également le suivi après rechargement et l'ouverture du cours seulement après un état terminé.

Les nombres de tests ne constituent pas un score de qualité. Le total complet peut augmenter lorsqu'un nouveau bug justifie un contrôle ; la réduction recherchée porte sur les doublons et les vérifications inutiles, pas sur la disparition de risques distincts. Voir le [guide d'exécution](../tests/README.md).

## Évaluation réelle

`evaluer_import.py` utilise le fournisseur réellement configuré, le service d'import commun et un stockage isolé via `STUDYPILOT_DATA_DIR`. Il refuse de travailler dans les données personnelles par défaut. Il ne charge aucune fiche éditoriale et ne simule aucune réponse du modèle. Les budgets d'appels et de durée sont explicites ; la durée est contrôlée avant chaque appel, sans interrompre brutalement un appel réseau déjà lancé. Les reprises réutilisent le même PDF validé.

Le corpus est composé de cinq documents synthétiques d'une page : classement/indexation, fonctions Python, suite géométrique, cycle de traitement illustré, observation/mesure sous forme de scan. Les sujets attendus sont déclarés dans `tests/fixtures/generalisation.json`, sans réponse de fiche préécrite. Ces petits supports servent à révéler des défauts ; ils ne remplacent pas une campagne sur de vrais cours longs, des tableaux complexes ou des scans dégradés.

Les résultats détaillés, réponses du seul corpus synthétique et journaux sont conservés hors du projet dans `C:\StudyPilotProject\StudyPilot_Archives\automatisation_20261016`. Les appels logiques comptés dans les rapports peuvent inclure des relances de format ; les tentatives réseau supplémentaires du transport sont distinctes et visibles dans les journaux. Les arrêts volontaires de budget sont séparés des refus du fournisseur dans les rapports récents.

Un état technique `ready` ne prouve pas à lui seul la bonne granularité, la pertinence du titre ou la qualité pédagogique. Les fiches produites doivent aussi être confrontées au support. Les erreurs serveur HTTP 500 rencontrées sont des interruptions fournisseur, pas des preuves que le document serait insuffisant.

## Résultat observé et limites restantes

| Support nouveau | État du stockage en fin de campagne | Lecture du contenu |
| --- | --- | --- |
| Mathématique | Complet, 1 fiche | Formules, domaine des indices et exemple présents ; rendu vérifié dans l'application. |
| Scan propre | Complet, 2 fiches | Observation et mesure distinguées, exemples et unité conservés. |
| Illustré | Complet, 1 fiche | Cycle et validation expliqués, schéma source disponible ; titre trop étroit. |
| Programmation | 3 fiches précédemment validées conservées | Code fidèle ; répétitions importantes entre Fonction et Paramètre. Consignes recentrées, mais la nouvelle rédaction n'a pas pu être validée à cause d'un HTTP 500 persistant. |
| Rédactionnel | Partiel, 0 fiche publiée, 3 brouillons conservés | Sélections de phrases tronquées détectées ; correctif de continuation appliqué, dernière lecture interrompue par HTTP 500. |

Ces résultats ont nécessité plusieurs reprises : ils ne correspondent pas à cinq réussites au premier import. L'état « complet » ne vaut pas validation pédagogique globale. Le [relevé détaillé](evaluation_generation.json) indique l'état actuel et celui de la dernière tentative séparément.

La génération reste trop coûteuse en appels pour de petits supports et sa granularité demeure inégale. Les prochains défauts à traiter sont la sélection de racines dont le titre correspond au contenu regroupé, les citations couvrant plusieurs notions qui entraînent des répétitions, et la réduction des contrôles redondants du moteur. Les consignes de rédaction et d'audit ont été recentrées ; leur efficacité sur les répétitions doit encore être confirmée par une génération réelle achevée. Aucun résultat parfait sur « n'importe quel cours » n'est revendiqué.

Vérifications finales : **217 tests courants réussis**, suite complète **423 réussis et 1 ignoré**, **5 tests JavaScript réussis**. Les tests sont sans appel IA réel ; la campagne ci-dessus utilise réellement l'API et reste distincte. Les 16 aperçus des cours personnels respectent le contrat de contenu et les 116 fiches éditoriales restent accessibles. La vérification des empreintes confirme que seuls les plans personnels ont changé pendant la mise à niveau des aperçus.

Captures : [aperçu régénéré automatiquement](vue_ensemble_automatique.png), [fiche mathématique réellement générée](fiche_generee_automatiquement.png).
