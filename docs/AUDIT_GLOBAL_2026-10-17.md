# Audit de StudyPilot — commencé le 17, finalisé le 18 octobre 2026

## Portée et conclusion

Audit fondé sur les deux captures de l'utilisateur, une inspection de l'accueil et de l'espace de cours dans le navigateur, la lecture des parcours de génération/chat/révision et un échantillon de fiches en algèbre, CSS et Fourier. Les trois profils ci-dessous sont une analyse de parcours, pas des entretiens avec de vrais utilisateurs. Aucun nouveau PDF ni appel IA n'a été nécessaire. Le produit n'a pas été modifié pendant cet audit.

StudyPilot offre désormais une base utile pour retrouver et réviser un cours déjà abordé : fiches courtes, formules rendues, ressources à la demande, PDF accessible et génération reprenable. Son utilité pour apprendre un cours entièrement nouveau reste moins établie. Sa principale faiblesse est l'écart entre une présentation convaincante et une validation pédagogique encore partielle.

Les 74 fiches et les tests techniques ne constituent pas une mesure de compréhension, d'exhaustivité ou de justesse de chaque réponse. La précédente refonte a amélioré plusieurs parcours sans encore les unifier tous.

## 1. La contradiction signalée

Pour les données visibles, A = ((4, 2), (1, 3)) et v = (2, 1), le produit est Av = (10, 5) = 5v. Ce calcul a été reproduit avec le vérificateur local. Si la réponse de l'élève était λ = 5 pour ce vecteur, elle était correcte. Le message original de l'élève n'apparaît pas dans les captures : on ne peut pas juger une éventuelle autre étape non visible. En revanche, l'assistant annonce une erreur sans l'identifier, puis valide le résultat ; son retour est donc incohérent et inutilisable pour comprendre ce qui serait à corriger.

Faiblesse établie dans le code : `tutor.answer` reçoit une réponse libre puis appelle `verify_response`. Ce dernier contrôle uniquement un éventuel bloc technique de calcul. Il ne compare pas systématiquement la réponse de l'élève à une solution de référence et ne vérifie pas la cohérence entre introduction et conclusion. Une phrase contradictoire sans bloc de calcul traverse ce contrôle sans modification. Même un calcul local correct ne suffit pas à valider le verdict pédagogique. Cela explique pourquoi cette contradiction peut être affichée, sans permettre d'établir précisément pourquoi le modèle l'a produite dans cet échange.

À construire : un exercice identifié et conservé (énoncé, données, question exacte, méthode de validation), puis une évaluation structurée : correct, partiellement correct, incorrect, ou impossible à conclure. Le message doit être rédigé à partir de cette évaluation, avec un seul verdict. Toute erreur annoncée doit pointer l'étape fautive. Un résultat juste avec un raisonnement insuffisant doit être reconnu comme tel, sans être appelé « faux ».

Pour les opérations prises en charge, effectuer le contrôle avant d'afficher le verdict et confronter les données à celles de l'exercice, pas seulement au bloc proposé par le modèle. Pour les autres exercices, conserver explicitement la limite du contrôle. Une seconde relecture IA peut être réservée aux désaccords et cas ambigus ; elle ne doit pas devenir un appel supplémentaire obligatoire pour chaque message.

## 2. Trois regards sur l'application

| Profil | Ce qui l'aide actuellement | Ce qui le freine | Parcours cible |
|---|---|---|---|
| Élève ayant les bases | Retrouver une règle, revoir une formule, ouvrir un exemple et poser une question ciblée. | Peu de diagnostic des lacunes ; entraînements peu structurés ; progression déclarative ; continuité fragile entre écrans. | Choisir une notion, tenter un exercice, recevoir un retour précis, travailler son erreur puis réussir une variante. |
| Professeur ou expert | Consulter rapidement une synthèse et revenir au PDF. | Provenance trop large ; hypothèses difficiles à inspecter globalement ; peu d'outils pour signaler/corriger une fiche ; aucune preuve de couverture complète. | Examiner objectifs, hypothèses et sources exactes ; comparer au support ; corriger une unité avec un historique de version. |
| Débutant n'ayant pas lu le cours | Aperçus courts, objectifs de partie et liste de prérequis existants. | Doit savoir quoi demander ; vocabulaire déjà spécialisé ; prérequis non reliés aux fiches ; pas de chemin guidé ni contrôle des connaissances intermédiaires. | Comprendre le but, vérifier les bases nécessaires, découvrir une idée, voir un exemple, essayer, puis avancer vers la notion suivante. |

Pour un débutant, « tout ce qu'il faut savoir » doit être défini par le périmètre du document et ses objectifs. Un chapitre peut supposer des connaissances absentes du PDF. StudyPilot doit les signaler et proposer des compléments identifiés comme tels, sans prétendre qu'ils viennent du cours.

## 3. Fiches : constats et nouvelle règle de qualité

Les fiches courtes sont une amélioration pour la consultation. Le nombre de fiches ne doit toutefois pas devenir un objectif de minimisation. Deux notions proches peuvent exiger des unités distinctes ; une liste de variantes peut rester un complément.

Exemples relevés :

- « Valeurs propres, vecteurs propres et spectre » donne la relation Av = λv et précise v ≠ 0. C'est utile pour réviser. Un débutant doit encore comprendre matrice, vecteur, multiplication et corps de travail.
- « Convergence normale » commence par des conditions de sommabilité et une borne sur u_n, sans définir d'abord la notion ni u_n. Une formulation courte peut donc rester difficile à comprendre.
- Les fiches CSS montrent des syntaxes pertinentes ; un aperçu du résultat visuel serait souvent plus instructif qu'une explication supplémentaire en prose.

Contrat proposé : titre précis, idée centrale, règle/formule/code si utile, définition des symboles et conditions indispensables. La longueur est un garde-fou, pas une raison d'enlever une hypothèse. Si cela devient trop dense, séparer les objectifs et garder les liens entre eux.

Trois profondeurs issues d'une même unité canonique :

1. **Essentiel** : mémoriser et retrouver rapidement.
2. **Comprendre** : explication progressive, prérequis accessibles et exemple minimal.
3. **Aller plus loin** : justification, preuve, limites, contre-exemple ou application plus complexe selon la matière.

Ces profondeurs ne doivent pas créer trois collections indépendantes et contradictoires. Les contenus stables sont enregistrés ; la personnalisation supplémentaire se fait à la demande.

## 4. Compréhension du document et génération

Le parcours actuel utilise du texte natif/OCR découpé en passages, une rédaction par lots, des contrôles locaux et une relecture avec le même modèle. Les références et décisions de couverture sont utiles. Elles attestent qu'un passage a une destination, pas que chaque enseignement qu'il contient a été correctement conservé.

La relecture utilise un appel distinct, mais pas un évaluateur indépendant du modèle auteur. Les deux appels peuvent partager les mêmes erreurs. Le générateur actuel exploite surtout la transcription textuelle : lire les mots d'un schéma n'établit pas le sens de ses flèches, sa géométrie ou ses relations. La simplification des sources en texte perd une partie de la structure disponible à l'extraction.

Améliorations :

- Conserver les unités documentaires : titre, paragraphe, définition, théorème, preuve, exemple, tableau, schéma, exercice et corrigé.
- Associer chaque unité à sa page et, quand disponible, à sa zone exacte. Préserver l'ordre des colonnes, les tableaux et les blocs de code.
- Repérer les symboles douteux, formules tronquées et régions visuelles insuffisamment interprétées. Déclencher une analyse visuelle seulement sur les zones qui le nécessitent.
- Construire une carte légère des objectifs et prérequis avant ou pendant la rédaction ; réconcilier les objectifs entre lots pour éviter répétitions et trous.
- Donner à chaque objectif une destination : fiche, étape guidée, ressource utile ou élément explicitement non traité avec raison. Un exemple contenant une idée nouvelle ne doit pas disparaître sous prétexte qu'il est un exemple.
- Montrer les passages restant à vérifier au lieu d'afficher une complétude globale trompeuse. Ne pas inventer un pourcentage de fiabilité.

Conserver les bons choix actuels : un import à la fois, cache de sources, lots reprenables, correction bornée, ressources réutilisées et priorité aux questions interactives. Pour les longs cours, transmettre une synthèse structurée des notions pertinentes plutôt que le corps de toutes les fiches déjà produites. Mesurer séparément extraction, génération, contrôle, reprises et temps d'attente.

## 5. Assistant, révision et progression

Constats vérifiés :

- Le chat des fiches/parties conserve huit messages récents et une notion active ; les sessions sont en mémoire et expirent après inactivité. Ce n'est pas un suivi pédagogique durable.
- La recherche des passages et le changement automatique de notion reposent surtout sur les mots des titres, alias et questions. Synonymes, comparaison de notions et références à un ancien exercice restent des cas fragiles.
- `revision.js` appelle encore l'ancien chemin de `/api/part-chat`, avec le titre inséré dans la question mais sans `card_id`, `conversation_id` ni demande contextuelle. Il ne bénéficie donc pas automatiquement de tout le parcours `tutor` et de ses contrôles.
- Les deux interfaces de révision utilisent des stockages différents : `studypilot-main-v155` et `studypilot.revision.progress.v1`. Un bouton « maîtrisée » reste une autoévaluation, pas une preuve de réussite.

Priorités : unifier l'assistant, le rendu et les états de progression ; conserver séparément l'exercice actif et la notion active ; gérer plusieurs notions dans une comparaison ; permettre de reprendre une discussion ; distinguer lu, compris déclaré, réussi avec aide et réussi sans aide.

Les exercices doivent progresser : application directe, variante, puis transfert. Un indice répond au blocage précis. La correction respecte ce que l'élève a déjà réussi et termine sur la prochaine action utile, sans compliments automatiques. Les exemples générés restent distingués des exemples du document.

L'extension des vérificateurs doit suivre les usages : équivalences simples et conventions en mathématiques, rendu isolé HTML/CSS, petits cas de test pour le code, critères sourcés pour des réponses rédigées. Il n'est pas pertinent de promettre un exécuteur universel de tous les exercices.

## 6. Navigation, apparence et logo

Le thème sombre et la séparation fiche/approfondissement donnent une base cohérente. La hiérarchie fonctionnelle reste dispersée entre accueil, partie, vue des fiches et deux révisions.

Observations dans le navigateur et le code :

- L'accueil propose « Expliquer le cours » et « Comprendre le cours », deux intentions peu différenciées.
- À la largeur étroite observée sur l'accueil, le logo et la navigation latérale disparaissent. Le CSS masque effectivement la barre latérale sous 650 px sans afficher d'équivalent dans cet écran.
- L'espace de partie réserve une large colonne centrale au chat initialement presque vide, alors que le contenu du cours est serré dans la colonne droite.
- « Retour au cours » mène à une route qui redirige vers la première partie : ce n'est pas une véritable vue générale du cours.
- Les aperçus possèdent déjà une liste de prérequis, mais ces noms ne conduisent pas à un diagnostic ou une explication dédiée.

Proposition : une entrée de cours avec trois intentions distinctes — **Découvrir**, **Approfondir**, **Réviser** — et un bouton **Reprendre**. Dans Découvrir, le contenu occupe l'espace principal ; l'assistant accompagne la lecture. Sur petit écran, afficher un panneau à la fois et une navigation compacte toujours accessible.

Uniformiser typographie, espacements, boutons et états. Renforcer la lisibilité des textes secondaires, les labels, les focus clavier et les zones tactiles ; vérifier les contrastes mesurés avant de déclarer une conformité d'accessibilité. Adapter les longues expressions à la largeur sans couper leurs conditions ni réduire tout le texte.

Le logo actuel « SP » est lisible mais générique et varie selon les écrans. Direction proposée, à prototyper : un signe simple évoquant une trajectoire d'apprentissage ou un repère de navigation, associé au nom StudyPilot. Le dessiner en SVG, cohérent en version complète et icône, lisible à 16–24 px et en monochrome. Éviter l'accumulation livre + avion + cerveau. Sa cohérence et sa présence dans la navigation comptent davantage qu'un effet décoratif supplémentaire.

## 7. Feuille de route priorisée et critères de réussite

| Ordre | Chantier | Résultat observable attendu |
|---|---|---|
| P0–1 | Verdict pédagogique fiable | Une réponse correcte n'est jamais annoncée fausse dans les cas de référence ; toute erreur déclarée est localisée ; verdict et conclusion concordent. |
| P0–2 | Exercice actif structuré | Une relance, un indice ou une correction conserve les mêmes données et la même question, même après plusieurs échanges. |
| P0–3 | Unification des chats et révisions | La même notion conserve contexte, rendu et progression quel que soit l'écran d'entrée. |
| P0–4 | Couverture et provenance inspectables | Chaque objectif essentiel d'un corpus relu possède une destination ; les passages incertains sont visibles et ouvrables précisément. |
| P1–1 | Parcours Découvrir | Un nouveau lecteur sait par quoi commencer et peut comprendre un prérequis inconnu sans quitter son parcours. |
| P1–2 | Fiches à profondeur progressive | Le noyau reste bref tout en conservant sens, symboles et conditions ; approfondir ne répète pas simplement la fiche. |
| P1–3 | Lecture documentaire structurée | Colonnes, tableaux, figures, conventions et code sont préservés sur un corpus hétérogène ; les ambiguïtés déclenchent un contrôle ciblé. |
| P1–4 | Entraînement et suivi utiles | Les erreurs récurrentes orientent l'exercice suivant ; lecture et réussite autonome sont distinguées. |
| P1–5 | Navigation et petit écran | Accueil, cours, fiches et reprise restent accessibles ; le contenu principal est lisible sans naviguer entre plusieurs défilements concurrents. |
| P2–1 | Outils de relecture expert | Signaler puis corriger une affirmation ou une source sans refaire tout le cours ; conserver la version et invalider seulement les dérivés concernés. |
| P2–2 | Identité visuelle | Logo, composants et vocabulaire cohérents dans tous les écrans. |
| P2–3 | Extensions ciblées | Ajouter les formats de documents et les capacités de calcul/code selon les besoins constatés, après stabilisation du PDF. |

## 8. Vérifier les améliorations sans multiplier les tests inutiles

Garder une petite suite de scénarios pédagogiques qui changent réellement le verdict : réponse correcte, incorrecte, partielle, résultat équivalent, exercice ambigu, changement de notion, reprise et demande d'indice sans divulgation de la solution. Réutiliser chaque scénario dans les différents points d'entrée, plutôt que dupliquer des dizaines d'assertions internes.

Pour la généralisation, employer quelques documents nouveaux mais représentatifs, dont au moins un long, un scanné, un avec figures/tableaux et un non mathématique. Définir avant génération les objectifs essentiels et difficultés attendues avec une relecture humaine. Mesurer omissions, affirmations non soutenues, doublons, contradictions de verdict et coût des reprises. Compter les fiches ou les tests réussis ne remplace pas ces mesures.

Enfin, faire parcourir de vraies tâches aux trois profils : trouver une notion et réussir une variante pour l'élève, vérifier une affirmation pour l'expert, apprendre une première notion et identifier la suivante pour le débutant. Observer les blocages sans expliquer à leur place où cliquer.

## Repères de code

- `src/tutor.py:86` : recherche et notion active ; `:152` : réponse et historique.
- `src/study_checks.py:95` : contrôle des blocs numériques, pas du verdict complet.
- `src/courses/study_guide.py:25` : unité publiée sans graphe de prérequis ; `:152` : projection textuelle des sources.
- `src/courses/guide_generation.py:64` : relecture ; `:197` : corps des noyaux précédents transmis aux lots suivants.
- `static/revision.js:1251` et `app.py:193` : coexistence de deux chemins de chat.
- `static/presentation.js:1` et `static/revision.js:1438` : progressions distinctes.
- `static/workspace.css:2621` : navigation d'accueil masquée sur petit écran.
- `app.py:60` : entrée de cours redirigée vers la première partie.

Cet audit recommande d'abord de rendre les verdicts, les états d'apprentissage et la couverture cohérents, puis de développer le parcours débutant et la présentation. Le logo accompagne cette amélioration ; il ne résout pas les défauts pédagogiques.
