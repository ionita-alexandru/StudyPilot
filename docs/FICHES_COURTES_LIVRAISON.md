# Fiches courtes et assistant contextuel — 17 octobre 2026

La nouvelle version est disponible localement. Le détail des décisions reste dans `audit_pertinence_fiches.json` et leur migration dans `migration_fiches_courtes.json`.

## Ce qui change

| Cours | Avant | Fiches essentielles | Prose moyenne par fiche |
|---|---:|---:|---:|
| Réduction des endomorphismes | 36 | 21 | 43 mots |
| CSS | 59 | 39 | 38 mots |
| Séries de Fourier | 21 | 14 | 51 mots |
| Total | 116 | 74 | — |

Les mesures excluent les formules et blocs de code. Les 74 noyaux comportent au maximum 70 mots de prose. Les exemples, preuves, variantes et exercices sont accessibles dans les ressources ; les 116 contenus originaux sont conservés. Les 42 entrées sorties de la liste principale n'ont pas été supprimées du cours. La fiche d'exercices signalée devient ainsi une ressource d'entraînement.

Chaque fiche présente l'essentiel et trois actions : exemple, approfondissement, entraînement. Elles ouvrent le chat sur la bonne notion. Un exemple déjà enregistré s'affiche sans appel IA. Les questions suivantes gardent le sujet et les derniers échanges. Une nouvelle notion explicitement nommée peut changer le contexte ; un simple « pourquoi ? » conserve la notion active. Le logo StudyPilot revient à l'accueil.

Le chat rend les titres, listes, formules et blocs de code avec le même moteur sûr que les fiches. Il distingue ressource enregistrée et réponse générée. Les exercices demandés ne donnent pas directement la solution ; les boutons indice et solution apparaissent ensuite. Les pages indiquées sont les passages consultés, et non une certification de toutes les affirmations.

## Parcours commun aux nouveaux PDF

Le plan et les aperçus restent communs à tous les cours. Le générateur de fiches travaille ensuite par lots de sources :

1. Extraire et conserver le texte/OCR avec les pages physiques.
2. Choisir les objectifs distincts, rédiger leurs noyaux courts et classer les autres contenus comme ressources.
3. Contrôler références, destinations, longueur et délimiteurs localement.
4. Faire relire séparément fidélité, conditions indispensables, couverture et redondance.
5. Autoriser une correction ciblée en transmettant la proposition précédente et ses défauts. Enregistrer les lots validés et signaler ceux restant à reprendre.

Il n'existe aucun quota de fiches ni règle spécifique aux trois cours personnels dans ce générateur. Leur réorganisation éditoriale est une migration initiale séparée, conservée dans les archives.

Un lot valide demande normalement deux appels de génération : rédaction et contrôle. Une correction ajoute au plus deux appels ; les relances réseau du fournisseur sont comptées séparément. Par lancement : plafond de 48 appels logiques, 20 minutes vérifiées avant les appels, et budget conservateur de requêtes/jetons. Un appel déjà en cours peut dépasser l'échéance jusqu'à son délai réseau. Les valeurs de jetons réservés ne constituent pas une facture ni une mesure exacte des jetons produits.

Les lots validés sont réutilisés sans appel IA ; leur cache dépend des sources, du plan, du modèle et de la version des consignes. Dans le serveur, un seul appel IA s'exécute à la fois. Les questions interactives passent avant les prochains lots d'import ; elles n'interrompent pas un appel déjà commencé. L'extraction et la recherche sont locales. Le chat consulte la fiche active, le plan courant, les sources pertinentes et huit messages récents, avec au plus sept passages et 10 500 caractères de sources.

Pour les anciens cours, les contenus relus sont complétés par l'extraction du PDF original, mise en cache. Une modification du guide ou du plan invalide le contexte d'une conversation. Le chat n'envoie pas tout le PDF à chaque question.

## Vérifications et limites

- Profil courant : 111 tests Python réussis ; 5 tests JavaScript réussis.
- Suite complète : 429 réussis, un ignoré (430 exécutés). Après les derniers ajustements de correction et de réponse, les 111 tests du profil courant ont été relancés avec succès.
- Trois anciens tests d'orchestration et leur fonction devenue inutilisée ont été retirés. Les tests historiques des commandes encore disponibles restent dans le profil complet ; ils ne sont pas lancés quotidiennement.
- La migration préserve les JSON originaux, contrôlés par comparaison avec la sauvegarde. Les identifiants des nouveaux noyaux diffèrent des anciennes fiches : les anciennes données de progression ne sont pas supprimées, mais ne sont pas automatiquement transférées aux fiches fusionnées.
- Des essais réels sur cinq petits PDF synthétiques couvrent mathématiques, programmation, texte, schéma et scan. Les résultats et reprises sont consignés dans `evaluation_fiches_courtes.json`. Les cinq cas ont fini par produire des fiches publiables : deux pour le schéma, une pour les mathématiques, deux pour la programmation, deux pour le texte et une pour le scan. Le cas rédactionnel a nécessité une correction de redondance ; plusieurs tentatives ont subi des erreurs HTTP 500 du fournisseur. Ce n'est donc pas un succès en une seule tentative pour chaque document. Ces supports d'une page ne démontrent pas une fiabilité universelle sur des cours longs.

Le contrôle local des réponses peut vérifier une expression arithmétique, un produit matrice-vecteur de petite taille ou une fonction Python arithmétique à un paramètre. Il n'exécute pas de programme arbitraire. Il contrôle uniquement les données fournies dans le bloc de calcul, pas toute l'explication ni une démonstration. Le modèle doit fournir ce bloc : toutes les réponses ne disposent donc pas d'un contrôle automatique.

Les erreurs du fournisseur et les passages insuffisants restent visibles. Un lot qui échoue à la relecture n'est pas publié comme fiable. Les formules complexes restent sensibles à la qualité d'extraction ; une relecture IA n'est pas une preuve mathématique.

## Vérification dans le navigateur

Le parcours fiche → exemple enregistré → question de suivi a été vérifié avec les valeurs propres. Le chat a repris la matrice de l'exemple et le vecteur sans changement de sujet. Un second calcul explicite a produit le résultat `(3, 3)` et le statut « Calcul contrôlé » après vérification locale. Le parcours exercice sans solution puis demande de correction a également été parcouru ; le dernier contrôle numérique porte sur le produit explicite ci-dessus.

Le défilement du chat reste désormais dans sa colonne. La fiche et son titre restent visibles pendant la lecture d'une réponse. Un aperçu est enregistré dans `fiches_courtes_apercu.png`. La navigation du logo vers l'accueil a été vérifiée.

## Récupération et fichiers utiles

Sauvegarde complète avant refonte : `C:/StudyPilotProject/StudyPilot_Archives/fiches_courtes_20261016`. Elle conserve le code précédent, les données originales, la migration et les journaux de vérification. Aucune clé API n'a été enregistrée dans les fichiers du projet.

Le parcours actif se trouve dans `src/courses/guide_generation.py`, `src/courses/study_guide.py`, `src/tutor.py` et `src/study_checks.py`. Les interfaces fiche et partie partagent `static/study_chat.js`.
