# Historique des changements

## 2026-10-19 — Cadre commun pour les chapitres et les révisions

- Migration des discussions par chapitre et des sessions de révision vers le même
  menu et la même barre de discussion fixe que les fiches d'apprentissage.
- Aperçu, fiches, plan et PDF regroupés dans un panneau repliable du chapitre.
  Les raccourcis préparent la question sans lancer un appel IA automatiquement.
- Réglages et minuteur de session restylés ; actions d'explication placées près de
  la fiche. Le chat est masqué pendant la préparation et après la fin de session.
- Menu synchronisé avec le cours choisi. Démarrage désactivé tant que les fiches
  ne sont pas chargées ; réponses périmées ignorées lors d'un changement de cours.
- Réinitialisation du contexte de discussion en cas de changement de cours, même
  si deux cours partagent un identifiant de notion. Libellé Pause remis au début.
- Suppression du balisage des anciens menus et formulaires devenus redondants.

Vérifications : 118 tests Python et 6 tests JavaScript réussis ; un test de navigation
ajouté pour le cours demandé, le repli sur le premier cours et une bibliothèque vide.
Contrôles navigateur à 1280 × 900 et 390 × 844 : sélection du cours, fiche de session,
pause, accès aux actions, plein écran avec brouillon conservé, menu mobile, aperçu
et plan du chapitre. Aucun appel de génération IA réalisé pour ces contrôles.
Les sessions de contrôle ont été mises en pause puis quittées sans enregistrer de bilan.


## 2026-10-19 — Assistant permanent et espace de cours

- Barre de saisie fixe dans le parcours, les fiches, Mes documents et Ma progression.
  Son contexte indique le cours ou la notion active ; la discussion se déplie au-dessus.
- Formulaire commun plus compact, avec accents bleu-violet et rose, bouton d'envoi
  accessible et état d'attente distinct. Le plein écran reste disponible.
- Menu latéral repliable : retour aux cours, Apprendre, Mes documents, Ma progression.
  Sur petit écran, fermeture avec Échap et navigation clavier contenue dans le menu.
- Lecture sur une colonne, surfaces plus sobres et lumière statique discrète.
- Hauteur réservée sous le contenu pour garder les dernières actions accessibles.
  Choix question/réponse d'exercice conservé visible même avec la discussion repliée.

Vérifications : 117 tests Python et 6 tests JavaScript existants réussis ; syntaxe
JavaScript contrôlée. Vérifications dans le navigateur à 1280 × 900 et 390 × 844 :
formules, discussion enregistrée, accès au bas de la fiche, menu mobile, maintien du
brouillon entre les trois rubriques et au retour du plein écran. Compatibilité du
formulaire commun vérifiée dans une session de révision, mise en pause sans bilan.
Aucun appel de génération IA utilisé pour ces vérifications visuelles.

Le menu et la barre fixe concernent l'espace du cours et les fiches d'apprentissage.
Les écrans historiques de galerie, de chapitre et de session ne sont pas migrés
vers cette nouvelle disposition dans ce lot. Les brouillons ne sont pas persistés
entre deux chargements de page.

## 2026-10-19 — Navigation et confort du chat

- Regroupement du parcours d'un cours dans Apprendre, Mes documents et Ma progression.
- Catalogue des notions repliable, recherche par titre, chapitre, objectif et alias.
- Reprise de la dernière notion reconnue et accès direct à l'assistant depuis le cours.
- Chat agrandissable dans le parcours, les fiches, les chapitres et les révisions.
  Le même formulaire, le brouillon, les messages et l'exercice restent conservés.
- Début des nouvelles réponses rendu visible ; espace de lecture augmenté dans les fiches.
- Retrait du moteur de révision en doublon dans la galerie ; redirection vers la session commune.
- Dépôt rendu public sur demande ; données locales et secrets exclus du suivi Git.

Vérifications : 117 tests Python réussis, 6 tests JavaScript réussis. Contrôles dans
le navigateur de la navigation, de la recherche, des sources, de la progression,
de la reprise d'une discussion et de l'agrandissement avec retour au formulaire.
Affichage contrôlé à 390 et 1280 pixels. Un exemple déjà enregistré a servi à
vérifier les formules ; aucun nouveau benchmark de modèle n'est revendiqué.

La progression reste stockée dans le navigateur. Les réussites concernent des
exercices précis ; elles ne prouvent pas une maîtrise complète. Le mode express,
le guidage adaptatif et l'ajout de plusieurs documents à un cours restent prévus.
