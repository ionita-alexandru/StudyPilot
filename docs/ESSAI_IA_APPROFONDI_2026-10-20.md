# Comparaison approfondie et corrections du parcours

Campagne du 20 octobre 2026, heure de Berlin. Elle complète l’[essai simple](ESSAI_IA_2026-10-20.md).
Les données sont entièrement fictives et les rapports restent dans `data/_ai/`,
exclus de Git. Aucune facturation ni configuration du moteur actif n’a été modifiée.

## Ce qui a réellement été comparé

Trois questions : une conclusion fausse sur la diagonalisabilité, une liste Python
partagée comme argument par défaut et un corpus dont les effectifs se contredisent.
Mêmes questions et consigne système, température 0, sortie limitée à 900 jetons,
réflexion MINIMAL pour Gemma et LOW pour Gemini. Les réponses ont été relues ; les
quelques mots recherchés automatiquement ne suffisent pas à établir leur justesse.
Ces questions évaluent les modèles directement, pas toute la récupération documentaire
et la gestion des exercices du chatbot en situation réelle.

Le lot de fiches utilise le véritable `generate_batch` : rédaction sous contrat
Pydantic, contrôles locaux, puis relecture dans un autre appel du même modèle.
Une seule correction est permise. La relecture est distincte de la rédaction,
mais n’est pas un contrôle par un modèle indépendant.

Le mini-cours comporte six passages : probabilité conditionnelle, indépendance et
incompatibilité, Bayes, exercice sans correction, rappel répété et mention d’une
figure non transcrite. Il représente un texte déjà extrait ; aucun import PDF,
OCR, découpage automatique ni compréhension réelle d’image n’a été mesuré ici.

## Résultats initiaux

| Cas | Gemma 4 26B A4B | Gemini 3.8 Flash | Relecture |
| --- | ---: | ---: | --- |
| Diagonalisabilité : hypothèse oubliée | 9,09 s | 35,23 s | Les deux distinguent le calcul juste de la conclusion fausse ; espace propre de dimension 1 correctement obtenu. |
| Python : argument mutable par défaut | 5,97 s | 44,42 s | Les deux prévoient `[1]`, puis `[1, 2]`, et proposent `None` sans prétendre exécuter le code. |
| Sources contradictoires | 7,33 s | 8,08 s | Les deux repèrent 40/400, l’absence de preuve causale et la représentativité non établie. Réserve : conclusions parfois trop catégoriques. |
| Rédaction et contrôle des fiches | Refus après deux rédactions, 75,14 s | Validé après rédaction et relecture, 126,86 s | Gemini produit trois noyaux et un exercice ; Gemma échoue sur des champs du contrat. |

Moyenne des trois questions : 7,46 s pour Gemma, 29,24 s pour Gemini. Ces valeurs
incluent comptage des jetons, réservation locale éventuelle et réseau. La rédaction
Gemini a rencontré un HTTP 503 puis une relance serveur ; son temps ne mesure donc
pas une vitesse normale garantie. Un seul exemplaire par cas, ordre fixe, aucun
intervalle de confiance ni test de saturation des quotas : pas de classement général.

Les fiches Gemini conservent les formules et leurs conditions, regroupent le rappel,
gardent l’exercice sans corrigé et signalent la figure non transcrite dans la couverture.
Cette figure reste inconnue, même si les autres passages sont correctement traités.
Les prérequis contiennent des clés techniques, peu adaptées à la navigation.

Le premier brouillon Gemma place un champ `coverage` dans une ressource ; le second
emploie `kind=exercise`, alors que `exercise` est un rôle. Les deux propositions
sont refusées. Des descriptions génériques de la figure apparaissent aussi sans
transcription suffisante : elles ne doivent pas être prises pour un contenu du cours.

## Corrections issues des constats

- Contrat expliqué plus précisément : distinction `role`/`kind`, emplacement de
  `coverage`, prérequis par titres et traitement d’une figure non transcrite.
- Après rejet du schéma, l’unique appel de correction reçoit aussi l’extrait rejeté
  et le diagnostic. Avant, la consigne de correction dépendait de l’existence d’un
  brouillon déjà validé par Pydantic. Les contraintes ne sont pas assouplies.
- Une couverture incohérente indique désormais la source, les destinations déclarées
  et celles des fiches, pour rendre la correction exploitable.
- Les clés de prérequis qui désignent une fiche du lot sont converties vers son
  titre, sans inventer de prérequis supplémentaire.
- Conditions et notations structurées conservées dans les fiches des chapitres,
  de révision et dans le contexte de discussion. Une condition déjà présente
  textuellement dans le noyau n’est pas ajoutée une seconde fois dans ces fiches.
  Les commandes mathématiques explicites des noms de symboles sont balisées pour
  le rendu, sans transformer les identifiants de code en formules.
- Consigne du chat renforcée : distinguer information absente, affirmation contredite
  et fait établi. Cela reste une consigne, pas une garantie de raisonnement juste.
- Les erreurs HTTP du transport partagé indiquent Gemini lorsque ce modèle est
  concerné ; elles étaient auparavant étiquetées Gemma.

Une nouvelle passe Gemma sur le seul lot, après clarification du contrat, ne comporte
plus d’erreur de schéma mais échoue encore sur la couverture : le rappel `p5-0` est
cité par une fiche et déclaré sans destination. Deux rédactions, 71,25 s, lot refusé.
Il ne s’agit donc pas d’une correction complète démontrée du générateur.

Une dernière correction ciblée réutilise ce brouillon, sans refaire les questions ni
modifier manuellement les fiches : diagnostic précis, rédaction puis relecture réelle.
Deux appels, 52,86 s. La couverture est corrigée et les contrôles automatiques passent,
avec trois noyaux et deux ressources. **La relecture humaine constate cependant que
la description générique de la figure a été conservée et acceptée par le contrôle IA.**
Ce résultat n’est donc pas considéré comme une réussite pédagogique complète.

La consigne de relecture exige désormais explicitement de refuser une description
plausible mais absente du passage ; cette dernière consigne n’a pas fait l’objet
d’un nouvel essai réel dans cette campagne. Dans l’interface, une source contenant
des visuels affiche « visuel à vérifier » même lorsqu’elle est rattachée à une fiche.
L’avertissement porte sur les éléments visuels, pas sur l’incomplétude de tout le texte.

Campagne entière, corrections ciblées comprises : 14 appels logiques, 29 requêtes
réseau dont 14 comptages de jetons et 15 tentatives de génération (une relance après
HTTP 503). Aucun appel supplémentaire lancé après ce plafond. Les résultats
automatiques et les réserves humaines sont volontairement distingués.

## Reproduire séparément des tests

Après confirmation du forfait gratuit, clé uniquement dans l’environnement :

```powershell
.\.venv\Scripts\python.exe -X utf8 evaluer_assistants.py --confirm-free-project --suite advanced --max-seconds 300
.\.venv\Scripts\python.exe -X utf8 evaluer_assistants.py --confirm-free-project --suite guide --providers gemma --max-seconds 180
```

`basic` reste le mode par défaut : trois questions, six appels logiques maximum.
`advanced` ajoute le lot : quatorze appels logiques maximum pour deux fournisseurs.
`guide` isole le lot : quatre appels maximum par fournisseur. Un appel logique peut
comporter comptage de jetons et relance serveur bornée. Les limites de temps sont
vérifiées avant les opérations ; une requête déjà partie n’est pas interrompue.
Les résultats intermédiaires et les brouillons refusés sont conservés localement.
Une campagne incomplète retourne un code de sortie non nul ; un résultat validé par
les contrôles automatiques exige toujours une relecture humaine.

La correction finale était une validation ciblée depuis le brouillon refusé conservé
dans le rapport local : `validate_draft` fournit le diagnostic, puis un budget de deux
appels exécute la correction sous `Draft` et `review_draft`. Elle ne prouve pas qu’un
nouvel import réussirait dès sa première passe et n’ajoute pas de troisième tentative
automatique au générateur courant.

Vérifications de régression : 123 tests Python et 8 tests JavaScript. Les tests
existants ont été renforcés pour la transmission des repères, les prérequis lisibles,
le retour d’un rejet de schéma dans la correction, les diagnostics de couverture et
la distinction texte/visuels. Aucun appel réel n’est ajouté à la suite courante.

## Décision et limites

Gemma reste actif. Gemini est une piste plus convaincante pour la génération structurée
sur ce lot, avec un coût de latence élevé ; les réponses du chat ne démontrent pas
de supériorité pédagogique nette. Un seul mini-cours ne justifie pas de changer
toutes les opérations du site ou de déployer l’autre PC. Les deux fournisseurs
restent explicitement sélectionnables, sans bascule cachée.

La campagne ne démontre ni couverture parfaite d’un cours, ni fiabilité sur tous les
domaines, ni disponibilité gratuite illimitée. Les contrôles de source, de format,
de calcul et les signalements restent nécessaires.

L’application locale a été redémarrée avec Gemma 26B. Accueil, parcours, chapitre
et préparation de révision répondent HTTP 200. Ce contrôle ne constitue pas une
nouvelle campagne visuelle sur ordinateur et mobile.
