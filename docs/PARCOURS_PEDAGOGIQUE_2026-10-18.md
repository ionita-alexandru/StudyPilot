# Parcours pédagogique — 18 octobre 2026

Cette livraison applique les priorités de l’audit global aux mécanismes communs du projet. Elle ne repose pas sur des réponses préécrites pour les trois cours présents.

## Changements livrés

- **Correction après évaluation.** Un exercice possède un énoncé, un objectif, un corrigé et des critères conservés. Pour l’arithmétique, les produits matrice-vecteur, les valeurs propres associées à un vecteur donné et les petites fonctions arithmétiques Python, la référence est calculée localement depuis les données. L’énoncé numérique et sa solution sont construits depuis ces mêmes données. Un corrigé généré incohérent bloque la publication. Aucun code arbitraire n’est exécuté.
- **Tentative ou question.** Le sélecteur distingue répondre à l’exercice et demander une explication. Une réponse numérique non interprétable donne une demande de précision, pas un jugement négatif inventé. Les réponses rédigées sont évaluées par critères ; une erreur doit citer un passage exact de la tentative. Une justification absente est distinguée d’un résultat faux. Le jugement IA demeure identifié comme tel.
- **Exercice et conversation persistants.** Indice et solution sont enregistrés avec l’exercice, sans nouvel appel IA. L’exercice est séparé de l’historique récent et reste disponible après une relance ou un redémarrage. Les fichiers sont locaux, liés au cours et à la version du guide. Une nouvelle discussion est possible depuis chaque écran. Un changement explicite de notion change de discussion.
- **Un seul assistant et une seule progression.** Fiches, parties, découverte et révision utilisent StudyChat. L’ancien chat de révision, son rendu Markdown et ses styles devenus inutiles ont été retirés. Les anciennes progressions sont migrées sans effacer leurs sauvegardes. Lu, compris déclaré, réussi avec aide et réussi sans aide sont distincts. Une réussite concerne l’application demandée, pas la maîtrise entière du sujet.
- **Découvrir / Approfondir / Réviser.** La page du cours devient un vrai parcours, avec les notions ordonnées selon le document et une reprise de la dernière notion. Découvrir montre l’essentiel, les prérequis et des actions pour obtenir un exemple, une explication ou un exercice. Les prérequis correspondant sans ambiguïté à un titre ou alias sont liés ; les autres peuvent être expliqués à la demande.
- **Couverture inspectable.** Les passages, leurs destinations et les motifs de sélection sont visibles. La relecture des futures générations enregistre aussi les objectifs essentiels et leurs destinations, avec contrôle des références. Les anciens guides indiquent explicitement qu’ils ne disposent pas de ce contrôle détaillé. Les signalements sont conservés localement avec la fiche, sa version et ses sources ; ils sont visibles sur la fiche de découverte et ne sont pas présentés comme déjà corrigés.
- **Génération générale.** Le type Règle est accepté, notamment en grammaire. Prérequis, symboles et conditions sont structurés. La consigne exige la définition avant les conséquences et évite les formules décoratives. Les lots suivants reçoivent titres, objectifs et alias des notions précédentes au lieu de tous leurs corps. Les sources nouvellement extraites conservent les unités et coordonnées disponibles ; les éléments visuels à vérifier sont signalés.
- **Présentation.** Logo SVG commun, retour à l’accueil, navigation mobile, véritable entrée du cours et correction de la grille de révision sur petit écran. Les aperçus ne répètent plus un objectif qui était seulement le titre. La fiche de convergence normale a été complétée après lecture de sa page source ; les originaux restent conservés.

## Vérifications

- Suite complète : 436 tests, 435 réussis et un ignoré, exécutée en UTF-8 sous Windows. Le profil courant reste limité à 117 tests ; la suite historique est optionnelle. Six tests Python ciblés ont été ajoutés pour verdicts, cohérence des données, aide, persistance et traçabilité.
- Six tests JavaScript réussis, dont un test de migration commune des progressions. Syntaxe vérifiée pour tous les scripts locaux.
- Navigateur réel : parcours du cours → découverte → exercice → réponse correcte, reprise après rechargement, même conversation dans les fiches et la révision, retour à l’accueil. Contrôle à 390 px de largeur et correction du débordement du sélecteur ainsi que de la colonne fixe en révision.
- Modèle réel : exercice de valeur propre, réponse correcte évaluée localement ; exercice CSS, réponse inadéquate puis réponse correcte évaluées par critères. Les sorties et les énoncés ont été lus, pas seulement les statuts HTTP.
- Génération réelle sur un nouvel extrait synthétique de grammaire : défaut initial sur le type « rule », correction du contrat, puis deux fiches et une ressource d’exemples. Une reprise de génération a été nécessaire (quatre appels logiques dans cette exécution). Le contrôle des objectifs ajouté ensuite a été vérifié séparément en un appel. Détails dans `validation_generation_2026-10-18.json`. Ce test porte sur un extrait textuel, pas sur un nouvel import PDF complet.

## Limites encore réelles

- Le contrôle local couvre les opérations explicitement prises en charge. Il ne valide pas une démonstration générale, un programme arbitraire ni toute la pédagogie d’une réponse. L’évaluation des réponses rédigées reste probabiliste.
- Les exercices proposent actuellement un indice préparé ; adapter cet indice à un blocage particulier passe par une question à l’assistant. Il n’existe pas encore de progression automatique application → variante → transfert.
- L’ordre de découverte suit les parties du document. Ce n’est pas un graphe de prérequis exhaustif ni un diagnostic initial de niveau.
- La relecture des fiches utilise toujours le même modèle que leur rédaction. Les objectifs enregistrés rendent son contrôle inspectable, sans constituer une preuve d’exhaustivité indépendante.
- Les schémas complexes et tableaux ne sont pas tous interprétés visuellement. Les unités et zones sont conservées lorsqu’elles existent, et les pages concernées peuvent être vérifiées dans le PDF. L’analyse visuelle ciblée systématique et la correction experte avec régénération des seuls contenus dépendants restent à développer.
- Les cours existants n’ont pas tous été régénérés avec le nouveau contrat d’objectifs. Aucun gain universel de qualité ou de coût sur les cours longs n’est revendiqué.
- La progression reste propre au navigateur. Les discussions sont locales au projet et conservent huit messages récents, en plus de l’exercice actif. Une modification du guide invalide la discussion ; les anciennes autoévaluations ne constituent pas une validation de la nouvelle version.

## Conservation et coût

Sauvegarde avant intervention : `C:/StudyPilotProject/StudyPilot_Archives/refonte_pedagogique_20261018_125652/avant_refonte.zip`.

Pas de régénération massive des cours personnels. Un appel pour créer un exercice ; aucun appel pour un résultat numérique reconnu, un indice ou la solution conservée ; un appel pour une évaluation rédigée. La génération des fiches garde sa rédaction et sa relecture, avec au plus une correction du lot et les budgets existants. Les essais ont rencontré des erreurs HTTP 500 temporaires du fournisseur ; elles ne sont pas assimilées à des insuffisances du cours.
