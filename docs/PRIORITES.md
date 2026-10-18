# Organisation et priorités StudyPilot

Cadrage révisé le 19 octobre 2026. Ce document est une **proposition à valider**,
pas une annonce de fonctionnalités livrées. L’état précédent est décrit dans
`PARCOURS_PEDAGOGIQUE_2026-10-18.md`.

## Demandes confirmées et constats

L’utilisateur demande une organisation claire, moins de fonctions qui se recouvrent,
un chat plus lisible et pertinent, une IA sans paiement d’API, un guidage adapté,
un mode express, un menu moins intimidant, une interactivité utile et des compléments
de cours. Les commits doivent décrire uniquement les changements réellement faits.

Constats dans le code, sans nouveau test visuel à cette étape :

- `templates/course.html` propose Découvrir, Approfondir et Réviser, puis toutes les
  notions par partie. Approfondir ouvre la première partie du cours.
- `templates/presentation.html` propose aussi Mes fiches et Révision ; la navigation
  de `templates/learning_base.html` ajoute Mon parcours et Mes fiches.
- L’assistant est déjà commun (`static/study_chat.js`). Ses espaces d’affichage
  diffèrent : messages limités à `32vh` dans la fenêtre de fiche et à `30vh` dans
  Découvrir lorsqu’un exercice est présent. Ces règles réduisent la place de lecture.
- `static/revision.js` possède déjà durée personnalisée, minuteur, pauses et session.
  Un minuteur ne constitue toutefois pas un programme d’apprentissage adaptatif.
- `src/ai/client.py` centralise Gemma et Ollama. `src/ai/gemma.py` autorise actuellement
  deux variantes Gemma : passer à Gemini ou Groq exige une adaptation et des contrôles.
- Les sources sont actuellement liées au PDF principal du cours. Avec plusieurs
  documents, une référence doit identifier le document et sa page, pas seulement la page.

## Ordre de réalisation proposé

| Ordre | Travail | Résultat attendu |
| --- | --- | --- |
| 1 | Organisation et menu | Une navigation claire, accès progressif aux notions, mêmes fiches et progression partout. |
| 2 | Assistant : espace et réponses | Chat agrandissable, contexte visible, réponses directes et verdicts cohérents. |
| 3 | Choix du moteur IA | Comparaison mesurée de la qualité, de la vitesse et des limites selon le matériel réel. |
| 4 | Guidage commun | Prochaine activité adaptée au niveau, aux prérequis, aux objectifs et aux réponses. |
| 5 | Express | Programme compatible avec le temps disponible, priorités et limites visibles. |
| 6 | Documents complémentaires | Sources distinctes, enrichissement ciblé et adaptation du parcours. |
| 7 | Interactivité et finitions | Participer aide à apprendre ; la présentation et les retours motivent sans distraire. |

L’étude des moteurs peut avancer pendant le cadrage de l’interface. Le modèle de
données multi-document doit être prévu avant Express pour éviter de refaire le
planificateur. Les contrôles de sources, couverture et calcul restent nécessaires
à chaque étape. Les interactions utiles font partie du guidage dès sa construction.

## Organisation proposée, à confirmer

Accueil **Mes cours**. Dans chaque cours :

- **Apprendre** : reprendre, préparer une session ou explorer librement. Découvrir,
  réviser et approfondir sont des objectifs du même parcours. Express est une option
  de durée et de priorité, pas un quatrième espace indépendant.
- **Mes documents** : cours principal, compléments et sources.
- **Ma progression** : abordé, difficulté repérée, compris déclaré, exercice réussi.

Le catalogue des fiches reste disponible dans Apprendre : recherche, chapitres
repliables et liste complète à la demande. L’entrée montre la prochaine action et
un petit groupe de notions utiles. L’assistant commun reste accessible et agrandissable.
Préserver les anciennes destinations utiles et le cours sélectionné pendant la migration.

## Assistant

Prévoir un panneau large, une commande Agrandir et une vue mobile adaptée. Garder
l’énoncé accessible sans écraser la discussion. Vérifier formules longues, code,
clavier mobile, zoom et retour au cours sans perte de conversation ; éviter les
défilements imbriqués. Répondre d’abord à la question, puis proposer le détail utile.
Afficher notion et documents utilisés. Distinguer question, tentative et indice.
Le verdict vient après vérification ; une incertitude ne devient pas une erreur de l’élève.
Le contexte comprend les passages pertinents, l’exercice et les difficultés récentes,
sans renvoyer tout le PDF à chaque message. Un meilleur modèle ne remplace pas ces règles.

## IA sans paiement d’API : pistes à comparer

Sources officielles consultées le 19 octobre 2026 ; aucun essai comparatif réalisé ici.

| Piste | Intérêt à tester | Limite ou inconnue |
| --- | --- | --- |
| Ollama sur l’autre PC | Calcul local utilisable depuis ce PC | GPU, VRAM, RAM, système, réseau, qualité et latence inconnus. |
| Gemini Flash gratuit | Alternative hébergée au Gemma actuel | Éligibilité et quotas actifs du compte à vérifier ; adaptation nécessaire. |
| Groq gratuit | Autre candidat hébergé pour le chat | Limites par compte et modèle ; gain non mesuré dans StudyPilot. |

[Ollama permet une écoute réseau via OLLAMA_HOST](https://docs.ollama.com/faq).
Architecture envisagée : ce PC héberge StudyPilot et interroge l’autre PC sur un
réseau privé. Le serveur doit être allumé et joignable ; aucun port public n’est
nécessaire. Un modèle local évite la facturation par appel mais utilise ressources
et électricité. Un gros modèle n’est pas automatiquement meilleur ni assez rapide.

Google propose notamment Gemini 3.8 Flash dans son offre gratuite selon la
[page tarifaire consultée](https://ai.google.dev/gemini-api/docs/pricing).
Les [quotas actifs](https://ai.google.dev/gemini-api/docs/rate-limits) sont à vérifier
dans AI Studio. Groq publie également ses
[limites gratuites](https://console.groq.com/docs/rate-limits).
Ces offres ne garantissent pas une disponibilité illimitée. Aucun passage payant,
abonnement ni changement automatique de fournisseur n’est proposé sans accord.

Comparer sur les mêmes sources : explication française, calcul et correction,
code, texte argumentatif, extraction avec tableau ou formule, couverture et format.
Relever erreurs, temps d’attente, appels et quotas. Choisir après ces mesures et
connaissance du matériel, en conservant les vérifications locales indépendantes.

## Guidage commun et Express

Proposition : demander objectif, niveau déclaré, périmètre et temps disponible,
puis quelques questions diagnostiques facultatives. Un débutant peut commencer
sans test préalable ; les précisions libres restent facultatives.

Construire la session depuis les objectifs, prérequis et observations sur l’élève.
Distinguer essentiel du cours et important pour un examen documenté : ne pas inventer
une fréquence de sujet sans annales ou consigne. Alterner compréhension, rappel sans
regarder et application. Permettre de sauter, approfondir ou choisir une autre notion,
en expliquant l’impact sur le plan. Une réussite isolée ne vaut pas maîtrise entière.

Pour Express, distinguer durée de travail et heure butoir. Pause suspend la première,
pas la seconde. Diagnostic, pauses prévues et bilan entrent dans le budget annoncé.
L’IA aide à choisir les priorités ; le programme contrôle les durées et leur somme.
Les estimations sont révisées au rythme observé. Recalculer après un bilan court,
un changement de temps ou d’objectif, une difficulté persistante ou un complément,
pas à chaque clic. Réutiliser fiches, exercices et résultats déjà pertinents.
Afficher prévu, abordé, réussi et laissé de côté. Ne pas promettre « tout maîtriser
en trois heures » : proposer un objectif plus restreint si le cours est trop vaste.

## Compléments

Premier périmètre proposé : PDF. TD, annale, corrigé, dissertation ou article
indiquent le rôle du document, distinct de son format. Autres formats et URL
seront étudiés selon les besoins. Rattacher au cours ; proposer un rôle corrigible.

Chaque passage conserve document, version et page. Repérer nouvelles notions,
approfondissements, doublons et contradictions sans remplacer silencieusement
le cours principal. Un corrigé ne doit pas être révélé avant la tentative par défaut.
Proposer exigible, entraînement ou approfondissement : un article n’élargit pas
automatiquement le programme obligatoire. Montrer l’impact sur le temps et le
parcours ; proposer remplacer, reporter ou prolonger si nécessaire. Régénérer les
éléments concernés, conserver les réussites pertinentes et identifier celles à revalider.

## Interactivité utile

Réponse avant révélation, indices graduels, exemples à manipuler lorsqu’ils aident,
bilan concret et prochaine action simple. Minuteur et pauses discrets. Pas de
classement, notifications envahissantes ni récompense pour les clics dans cette
proposition. L’effet sur l’envie de réviser devra être vérifié en usage.

## Informations et décisions en attente

- Autre PC : GPU/VRAM, RAM, système et réseau entre les machines.
- Navigation Apprendre / Mes documents / Ma progression à confirmer ou modifier.
- Express : diagnostic facultatif, budget total, durée ou heure butoir, objectif réaliste.
- Compléments : PDF d’abord, rôle confirmé et ajout explicite au programme obligatoire.

## Livraison

Changements cohérents et limités, vérifications adaptées, commit descriptif et push
vérifié. Une proposition documentée reste une proposition. Ne pas inventer résultat
de benchmark ou de test, matériel, identité ou affiliation. Demander les informations
nécessaires lorsqu’elles manquent. Ce cadrage ne modifie pas encore l’application.
