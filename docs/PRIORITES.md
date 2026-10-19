# Organisation et priorités StudyPilot

Cadrage révisé le 20 octobre 2026. La navigation a été **validée par l’utilisateur**,
avec un assistant central et une interface interactive et légère. Une première version du guidage, d’Express et des compléments PDF est maintenant disponible.
Le détail des fonctions livrées et de leurs limites figure dans `GUIDAGE_ET_COMPLEMENTS.md`.
L’état précédent est décrit dans
`PARCOURS_PEDAGOGIQUE_2026-10-18.md`.

## Demandes confirmées et constats

L’utilisateur demande une organisation claire, moins de fonctions qui se recouvrent,
un chat plus lisible et pertinent, une IA sans paiement d’API, un guidage adapté,
un mode express, un menu moins intimidant, une interactivité utile et des compléments
de cours. Les commits doivent décrire uniquement les changements réellement faits.

Constats avant le premier lot d'interface (conservés pour expliquer les priorités) :

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
| 1 | Organisation, menu et place du chatbot | Une navigation claire, un assistant central, accès progressif aux notions, mêmes fiches et progression partout. |
| 2 | Assistant : espace et réponses | Chat agrandissable, contexte visible, réponses directes et verdicts cohérents ; à traiter avec la refonte de navigation. |
| 3 | Choix du moteur IA | Comparaison mesurée de la qualité, de la vitesse et des limites selon le matériel réel. |
| 4 | Guidage commun | Prochaine activité adaptée au niveau, aux prérequis, aux objectifs et aux réponses. |
| 5 | Express | Programme compatible avec le temps disponible, priorités et limites visibles. |
| 6 | Documents complémentaires | Sources distinctes, enrichissement ciblé et adaptation du parcours. |
| 7 | Interactivité et finitions | Participer aide à apprendre ; la présentation et les retours motivent sans distraire. |

L’étude des moteurs peut avancer pendant le cadrage de l’interface. Le modèle de
données multi-document doit être prévu avant Express pour éviter de refaire le
planificateur. Les contrôles de sources, couverture et calcul restent nécessaires
à chaque étape. Les interactions utiles font partie du guidage dès sa construction.

## Organisation validée

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
L’utilisateur confirme cette structure à condition de ne pas négliger le chatbot,
l’interactivité et la légèreté de l’interface. Ces éléments appartiennent au premier
lot de conception, pas uniquement aux finitions. L’objectif est de donner envie de
revenir réviser grâce à des activités utiles et une progression compréhensible.

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

Sources officielles consultées les 19 et 20 octobre 2026. Un
[essai limité sur trois cas fictifs](ESSAI_IA_2026-10-20.md) a été réalisé après
déclaration du forfait gratuit par l’utilisateur ; aucune supériorité de Gemini
n’est démontrée. Gemma reste le moteur par défaut.
La [campagne approfondie](ESSAI_IA_APPROFONDI_2026-10-20.md) montre un résultat plus
favorable à Gemini pour le contrat de fiches sur un mini-cours, sans prouver une
supériorité générale ; Gemma a été plus rapide sur les questions de cette campagne.

| Piste | Intérêt à tester | Limite ou inconnue |
| --- | --- | --- |
| Ollama sur l’autre PC | Calcul local utilisable depuis ce PC, même sur un autre réseau | RTX 3060 Ti et 16 Go de RAM déclarés ; qualité et latence non mesurées. Adoption conditionnée à un gain réel. |
| Gemini Flash gratuit | Accès à la génération confirmé, adaptateur corrigé | Trois cas simples réussis, sans gain de qualité démontré ; quotas actifs à consulter dans AI Studio. |
| Groq gratuit | Autre candidat hébergé pour le chat | Limites par compte et modèle ; gain non mesuré dans StudyPilot. |

[Ollama permet une écoute réseau via OLLAMA_HOST](https://docs.ollama.com/faq).
Architecture envisagée : ce PC héberge StudyPilot et interroge l’autre PC sur un
réseau privé. Le serveur doit être allumé et joignable ; aucun port public n’est
nécessaire. Un modèle local évite la facturation par appel mais utilise ressources
et électricité. Un gros modèle n’est pas automatiquement meilleur ni assez rapide.

### Matériel communiqué et décision provisoire

Déclaration de l’utilisateur : Ryzen 5 3600 à 6 cœurs, 16 Go DDR4, RTX 3060 Ti,
SSD Samsung 870 EVO 500GB et Samsung MZVLB512HBJQ-000L7. Le système et l’espace
disponible ne sont pas connus ; aucune inspection de cette machine n’a été faite.
La [fiche NVIDIA](https://www.nvidia.com/en-us/geforce/graphics-cards/30-series/rtx-3060-3060ti/)
indique 8 Go de mémoire vidéo pour la RTX 3060 Ti. C’est une caractéristique du
modèle, pas une mesure effectuée sur le PC.

À titre d’ordre de grandeur, [Qwen3 8B Q4_K_M](https://ollama.com/library/qwen3:8b)
pèse 5,2 Go et [Qwen3 14B Q4_K_M](https://ollama.com/library/qwen3:14b) 9,3 Go.
Ce sont les tailles des modèles publiés, pas leur consommation totale :
[le contexte ajoute des besoins mémoire](https://docs.ollama.com/context-length).
Un modèle compact quantifié est donc une piste plausible pour ce GPU ; ces exemples
ne désignent ni le meilleur modèle actuel ni un modèle validé pour StudyPilot.
Un modèle qui dépasse la mémoire GPU peut nécessiter un partage avec le CPU/RAM,
avec un risque de ralentissement à mesurer. Les SSD ne remplacent pas la mémoire GPU.

L’utilisateur demande de pouvoir utiliser des réseaux différents et ne souhaite
cette méthode que si elle apporte une IA plus capable, sans paiement et avec peu
de restrictions. [Tailscale](https://tailscale.com/docs/how-to/quickstart) permet
de relier les machines dans un réseau privé ; son
[offre personnelle est gratuite](https://tailscale.com/pricing) pour l’usage
personnel non commercial prévu par cette offre. Les deux machines doivent rester
connectées et le serveur allumé. Une restriction d’accès à ces appareils sera
nécessaire, sans exposition publique de l’API Ollama.

Le local évite les quotas de requêtes d’un fournisseur pour un modèle exécuté sur
le PC ; il reste limité par mémoire, vitesse, contexte et disponibilité du PC.
Il ne donne pas accès gratuitement aux modèles propriétaires des API payantes.
**Décision provisoire : ne pas déployer le serveur distant comme moteur principal.**
Le gain de qualité demandé n’est pas démontré. Comparer d’abord les candidats
hébergés gratuits ; conserver le local comme essai conditionnel si un candidat
compatible peut améliorer les résultats. Ne pas demander d’achat matériel.

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

- Autre PC : système, mémoire GPU disponible et accès effectif restent inconnus.
  Ces détails ne sont nécessaires que si l’essai local conditionnel est retenu.
- Navigation Apprendre / Mes documents / Ma progression validée ; chatbot central,
  interactivité et présentation légère confirmés comme contraintes prioritaires.
- Express : diagnostic facultatif, budget total, durée ou heure butoir, objectif réaliste.
- Compléments : PDF d’abord, rôle confirmé et ajout explicite au programme obligatoire.

## Livraison

Premier lot réalisé le 19 octobre 2026 : navigation du cours Apprendre / Mes documents /
Ma progression, catalogue repliable avec recherche, reprise de la dernière notion,
assistant sur la page du cours et agrandissement du chat sur les écrans existants.
L'ancien moteur de révision de la galerie de fiches a été retiré ; son entrée ouvre
la session commune. Les anciennes URL et la consultation des sources restent disponibles.
Le dépôt GitHub est public à la demande de l'utilisateur. Voir `CHANGELOG.md` pour
les vérifications et les limites de ce lot. Le choix de moteur IA, le guidage
adaptatif, Express et les compléments multi-documents restent à réaliser.

Changements cohérents et limités, vérifications adaptées, commit descriptif et push
vérifié. Une proposition documentée reste une proposition. Ne pas inventer résultat
de benchmark ou de test, matériel, identité ou affiliation. Demander les informations
nécessaires lorsqu’elles manquent. Les propositions restantes ne décrivent pas des fonctions livrées.


Deuxième lot d'interface réalisé le 19 octobre 2026 : barre de discussion permanente
sur le parcours et les fiches, historique repliable, formulaire commun plus compact,
menu latéral sobre avec tiroir mobile et lecture centrale. Les références visuelles
fournies ont guidé l'espacement et les accents lumineux ; leurs images ne sont pas
intégrées au produit. Le moteur IA et les fonctions planifiées ne changent pas.


Troisième lot d'interface réalisé le 19 octobre 2026 : cadre commun étendu aux
chapitres et aux sessions de révision, avec chat fixe et menu lié au cours choisi.
Le contexte du chapitre reste consultable dans un panneau repliable. Ce lot ne
modifie pas la logique pédagogique du minuteur ni les critères de génération.


Quatrième lot réalisé le 19 octobre 2026 : programmes locaux guidés et Express,
niveau/objectif/temps, repères déclaratifs facultatifs, rappel actif, adaptation du
budget, reprise d’une session et compléments PDF avec sources distinctes. Le modèle
d’IA ne calcule pas les durées : le planificateur local les contrôle. L’adaptateur
Gemini est disponible en option ; un essai borné a confirmé l’accès après correction
du paramètre de réflexion, sans justifier de changement du moteur actif. Voir
`ESSAI_IA_2026-10-20.md` et `GUIDAGE_ET_COMPLEMENTS.md` pour les
contrôles effectués, les fonctions exactes et les limites qui restent à traiter.
