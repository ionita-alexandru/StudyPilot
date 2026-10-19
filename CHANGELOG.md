# Historique des changements

## 2026-10-20 — Comparaison approfondie et repères conservés

- Campagne manuelle : trois questions plus exigeantes et le véritable générateur
  de fiches sur un mini-cours fictif, rapports locaux et budgets explicites.
- Contrat de rédaction clarifié ; l’unique correction reçoit le diagnostic et
  l’extrait de réponse rejeté même après un échec du schéma. Erreurs de couverture
  localisées à la source concernée ; contrôles de publication conservés.
- Prérequis exprimés par leurs clés convertis vers les titres des fiches du lot.
  Conditions et notations conservées dans les chapitres, les révisions et le chat.
- Avertissement visible dans la couverture pour les visuels à vérifier ; consignes
  du chat et de la relecture renforcées sur les affirmations non établies et les figures.
- Messages HTTP du transport commun attribués au bon fournisseur.

Gemini réussit le lot structuré initial ; Gemma est plus rapide sur les questions
de cette campagne, mais échoue sur le contrat puis la couverture. Sa correction
ciblée passe les contrôles automatiques tout en conservant une réserve de fond
relevée à la lecture humaine. Le moteur actif est conservé. La dernière consigne
de relecture des figures n’a pas été réévaluée par appel réel.

Détails et mesures : `docs/ESSAI_IA_APPROFONDI_2026-10-20.md`. 123 tests Python
et 8 tests JavaScript réussis, sans augmentation de leur nombre ni appel réel dans
la suite courante. Aucun document personnel envoyé pour cette campagne.

## 2026-10-20 — Compatibilité Gemini et essai limité des assistants

- Paramètre de réflexion LOW pour Gemini Flash : MINIMAL causait un rejet HTTP 400.
  Le réglage MINIMAL de Gemma est conservé et les deux réglages sont vérifiés dans
  les tests existants, sans ajouter de test redondant ni d’appel IA à la suite.
- Script d’évaluation manuelle bornée sur trois questions fictives par fournisseur,
  confirmation du forfait gratuit requise, rapports locaux exclus de Git.
- Six réponses relues : calcul, application Python et information absente d’une
  source réussis par les deux modèles. Sur cet essai uniquement, moyennes de
  3,67 s pour Gemma et 11,22 s pour Gemini ; aucune supériorité générale établie.
  Le moteur actif reste Gemma. Aucun changement de facturation.

Protocole, trois rejets de paramètre avant correction et limites des mesures :
`docs/ESSAI_IA_2026-10-20.md`. La génération réelle de fiches avec Gemini et
la qualité sur des documents complexes restent à évaluer.

Vérifications : 123 tests Python et 8 tests JavaScript réussis ; les 16 tests du
transport Google ont aussi été relancés après les assertions de compatibilité.

## 2026-10-19 — Guidage, Express et compléments PDF

- Programme guidé ou Express depuis le niveau déclaré, l’objectif, les prérequis
  identifiés, la progression et le temps disponible. Proposition avant démarrage,
  activités retenues et notions reportées explicites.
- Budget incluant pauses prévues et bilan ; distinction durée/heure limite,
  compteur fondé sur l’heure réelle, rappel actif, passage d’une notion,
  ajustement du temps et reprise d’une session conservée dans le navigateur.
- Ajout de compléments PDF au même cours : rôle, périmètre, file unique,
  lots contrôlés, checkpoints et reprise bornée. Les doublons sont refusés.
- Ressources et références document/page distinctes dans les fiches et le chat ;
  corrigés exclus du contexte ordinaire. Nouveaux noyaux obligatoires regroupés
  par document. Les compléments facultatifs ne gonflent pas le programme.
- Alignement de l’ordre des sessions sur le parcours, conservation de l’exercice
  après un ajout documentaire, et transmission des repères déclarés au tutorat.
- Adaptateur Gemini Flash préparé ; moteur actif conservé, sans bascule ni essai
  réel avant confirmation du forfait Google associé à la clé.

Vérifications : 123 tests Python, 8 tests JavaScript réussis ; parcours Express,
pause, rappel, reprise, ajustement et formulaire des documents contrôlés dans le
navigateur, dont un affichage à 390 × 844. Tests de compléments avec PDF synthétiques
et génération simulée. Aucun benchmark d’un nouveau modèle ni qualité de génération
sur complément réel revendiqué. Détails : `docs/GUIDAGE_ET_COMPLEMENTS.md`.


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
