# Fiches courtes, pertinence et assistant contextuel

Document de conception conservé comme historique de la décision. La mise en œuvre est décrite dans [le bilan de livraison](FICHES_COURTES_LIVRAISON.md). Les formulations « proposé » et « pas encore déplacé » ci-dessous décrivent l’état au moment de l’audit. L'audit porte sur les 116 fiches éditoriales actuellement proposées et sur le code de génération et de conversation. Il ne constitue pas une nouvelle vérification de chaque formule contre les 60 pages sources. Aucun appel au fournisseur IA n'a été effectué pour cette analyse.

## Diagnostic

La fidélité au cours et l'utilité d'une fiche sont deux critères différents. Une page bien retranscrite peut constituer une mauvaise fiche de révision. Le précédent travail a amélioré la fidélité et les conventions, mais a conservé trop de contenu immédiatement visible et trop de fiches d'exemples. Le badge « relue » ne garantit pas une bonne sélection pédagogique.

La fiche « Exercices du cours : valeurs propres et diagonalisation » mélange trois matrices et plusieurs énoncés, sans solution détaillée. Elle sert de réserve d'exercices, pas de réponse à une notion. La déplacer vers l'entraînement, avec un exercice à la fois, un lien vers la méthode, puis des indices et une correction à la demande. Les solutions produites doivent être identifiées comme générées, puisque le PDF ne les donne pas.

Les longueurs textuelles ne suffisent pas à mesurer le problème : 319 sections, 129 expressions mathématiques affichées séparément et 54 blocs de code sur les 116 fiches. Trois sections par fiche en médiane dans chacun des cours. Les matrices, les exemples de code complets et les rubriques répétées occupent beaucoup de hauteur. Ces nombres mesurent le contenu stocké, pas la hauteur réelle dans le navigateur.

### Décisions proposées après lecture de toutes les fiches

| Cours | Fiches actuelles | Fiches essentielles proposées | Autres contenus réorganisés |
| --- | ---: | ---: | ---: |
| Réduction des endomorphismes | 36 | 21 | 15 |
| CSS | 59 | 39 | 20 |
| Séries de Fourier | 21 | 14 | 7 |
| Total | 116 | 74 | 42 |

Ces nombres résultent de décisions individuelles ; ils ne sont pas des quotas à imposer à un futur cours. Une fusion peut encore être révisée si elle produit une fiche trop dense. Les 42 entrées réorganisées restent retrouvables comme variantes, exemples, explications, exercices ou références. Aucun contenu n'a encore été déplacé.

Le fichier `audit_pertinence_fiches.json` contient les 116 décisions, les raisons et les destinations proposées.

Exemples de décisions :

- Padding : réunir les quatre fiches de définition, côtés et raccourcis autour d'une seule notion, avec les variantes consultables. Ne pas recopier leurs quatre exemples complets.
- Classe et identifiant : remplacer les trois fiches répétitives par une comparaison concise ; garder la distinction sémantique.
- Calculer les valeurs propres et polynôme caractéristique : une même entrée principale ; détail des coefficients et calcul numérique à la demande.
- Espace propre et critère de diagonalisabilité : conserver deux objectifs distincts. La proximité dans le cours ne suffit pas à justifier leur fusion.
- Cayley-Hamilton et réduction des puissances : conserver le résultat et la méthode d'application comme deux entrées utiles, en retirant leurs développements numériques initiaux.
- Forme complexe de Fourier : garder le résultat ; proposer la dérivation par Euler dans l'approfondissement.
- Parseval : conserver la formule générale, proposer son cas réel avec sa condition, sans multiplier les entrées de même sujet.
- CSS : les propriétés aux effets différents restent identifiables et recherchables, même si des applications combinées sortent de la liste principale.

## Causes dans le code

1. `relevance.py` distingue principalement une notion développée d'une simple mention. Cela ne mesure pas son intérêt comme fiche autonome.
2. `learning_material.py` accepte comme développé un exemple expliqué ou un énoncé complet. `card_groups.py` peut ensuite lui attribuer une fiche autonome. L'ordre des racines dépend des racines précédentes, des pages puis des identifiants ; il ne choisit pas globalement les meilleurs objectifs pédagogiques.
3. `card_grounding.py` attend que tous les points requis soient couverts dans la fiche. Une fois des exemples et précisions incorporés à ces points, une rédaction vraiment courte risque d'être rejetée comme incomplète. Il faut modifier ce contrat, pas seulement ajouter « sois concis » au prompt.
4. `StudyCard.sections` permet un nombre libre de sections et jusqu'à 6 000 caractères par section. Il n'existe pas de représentation distincte du noyau à retenir et des ressources complémentaires.
5. Les fiches éditoriales sont chargées par un parcours distinct dans `reviewed.py`. Changer uniquement le générateur laisserait les 116 fiches visibles inchangées : une migration est nécessaire, sans en faire une exception permanente pour ces trois cours.
6. `/api/part-chat` reçoit cours, partie, question et huit messages d'historique, mais aucun identifiant de fiche ou de notion active. La recherche utilise la question courante, pas une référence explicite conservée entre les tours.
7. `part_study.py` relit le texte natif de toutes les pages du PDF à chaque recherche. Il ne réutilise ni les preuves validées ni l'extraction OCR préparée à l'import. Une demande comme « donne un exemple de celle-ci » ne désigne donc aucune notion pour le moteur de recherche. Le modèle voit l'historique, mais peut manquer du passage documentaire utile.
8. Le plan est rechargé à chaque requête, mais transmis au modèle seulement pour les questions reconnues comme globales. L'inventaire des notions et leurs relations ne sont pas transmis. L'accès aux données existe donc déjà partiellement, mais reste fragmenté.
9. `part_chat.js` ne rend que le gras et les retours à la ligne, alors que le prompt peut produire des titres Markdown et du code. Les pages renvoyées sont les passages consultés, pas des citations validées affirmation par affirmation.
10. L'import possède déjà un seul worker. Le coût vient surtout des étapes successives : sélection et contrôle des preuves, suffisance et éventuelle récupération, regroupement et contrôle de relation, rédaction et audit, reprises. Ajouter davantage de parallélisme ne résoudrait pas cette accumulation.

## Nouveau contrat de pertinence

Décider de l'organisation avant de rédiger les fiches, par groupe cohérent de notions d'une partie, puis vérifier les recouvrements entre parties à partir des identifiants et résumés.

Une entrée principale doit répondre à une question précise : « qu'est-ce que c'est ? », « quelle règle appliquer ? », « comment faire ? » ou « quelle distinction éviter de confondre ? ». Elle doit avoir un objectif propre, un contenu suffisamment soutenu par le cours, un titre couvrant exactement ce contenu et une utilité qui n'est pas déjà assurée ailleurs.

Chaque élément source reçoit une destination explicite : noyau de fiche, précision, exemple, exercice, référence, orientation ou mention sans enseignement. Les exemples et exercices ne deviennent pas automatiquement des fiches. Un contre-exemple peut rester essentiel s'il enseigne une distinction indispensable ; le classement ne repose donc pas uniquement sur le type déclaré.

La couverture signifie « chaque enseignement utile est accessible à une destination », pas « chaque phrase est visible dans une fiche ». Les hypothèses, domaines, exceptions déterminantes et conventions nécessaires restent dans le noyau. Les preuves longues et applications numériques peuvent être différées. Une information incertaine reste à examiner, elle n'est jamais classée inutile à cause d'une erreur technique.

Pour chaque regroupement, conserver objectifs, identifiants sources, raisons et destination. Le titre du groupe est choisi à partir du contenu retenu ; il n'est pas forcément le titre de la première notion rencontrée. Garder les variantes comme alias pour la recherche. Conserver les dépendances utiles sans construire un graphe encyclopédique.

## Construction et présentation d'une fiche

La fiche initiale contient :

- un titre explicite et un type discret ;
- l'idée essentielle en une ou deux phrases ;
- la formule ou la syntaxe minimale lorsqu'elle est nécessaire ;
- les conditions et la signification des symboles utiles ;
- éventuellement une confusion fréquente, si elle change vraiment l'usage ;
- les pages sources et trois actions : « Voir un exemple », « Approfondir », « M'entraîner ».

Cible éditoriale initiale : environ 40 à 90 mots de prose et un bloc central de formule ou code. Ce n'est pas une coupure automatique : un théorème garde ses hypothèses, une comparaison peut nécessiter plusieurs lignes et une méthode quelques étapes. Une formule ne doit pas être privée de ses conventions pour entrer dans une limite. Si une fusion dépasse ce cadre, revoir la fusion ou la disposition avant de raccourcir.

Exemple de noyau, « Valeur propre et vecteur propre » :

> Pour une matrice carrée A, un vecteur propre est un vecteur non nul que A transforme en un multiple de lui-même. Le facteur λ est sa valeur propre associée.
>
> Av = λv, avec v ≠ 0.
>
> v est un vecteur propre associé à λ. λ peut être nul, mais v ne peut pas l'être.

Le corps de travail reste indiqué par le cours et doit être explicité dans les fiches qui en dépendent. Cet exemple de conception n'est pas une fiche publiée.

Une fiche CSS n'a pas besoin d'une page HTML complète pour expliquer une propriété. Le code minimal montre la syntaxe pertinente ; le contexte HTML et le rendu apparaissent dans l'exemple. Les sections non nécessaires n'apparaissent pas. Les actions ouvrent le chat à côté de la fiche, avec son sujet déjà sélectionné.

## Assistant contextuel

### Contexte stable et actualisé

Conserver côté serveur un accès commun aux données validées : cours, version du PDF et du plan, parties, notions, noyaux de fiches, passages sources et ressources associées. Réutiliser les extractions natives/OCR existantes au lieu de retraiter le PDF à chaque question. Index lexical local au départ ; ajouter une recherche sémantique seulement si les essais montrent des échecs de rappel qu'elle résout.

Une requête issue d'une fiche transmet `course_id`, `part_id`, `card_id`, l'action demandée et l'identifiant de conversation. Le serveur vérifie les relations et charge le contenu canonique. Il conserve la notion active pour « pourquoi ? », « un autre exemple » ou « applique-la ». Un changement de cours ou de sujet met explicitement à jour ce contexte.

Ordre de recherche : fiche et passages liés, prérequis directs, partie, puis cours entier si nécessaire. L'élargissement se fait localement avant l'appel de réponse. Limiter le contexte aux éléments utiles et préserver les formules et phrases complètes. Sur un scan, utiliser l'OCR enregistré ou les zones visuelles prises en charge ; une absence de texte natif n'est pas une absence de cours.

« En temps réel » signifie ici lire la dernière version publiée du cours et invalider les caches concernés après une modification. Il n'est pas nécessaire de maintenir un agent actif ni d'analyser le cours en continu. Une requête utilise un instantané cohérent de cette version. Les fiches anciennes ne doivent pas être mélangées avec des références d'une nouvelle extraction.

### Réponses adaptées à l'action

| Action | Réponse attendue |
| --- | --- |
| Exemple | Situation minimale, application, résultat et une phrase qui relie le résultat à la notion. |
| Approfondir | Explication progressive de la difficulté demandée, sans recopier toute la fiche. |
| M'entraîner | Énoncé court au niveau du cours ; indices puis correction selon la demande. |
| Corriger ma réponse | Identifier le point correct ou l'erreur, expliquer et proposer la prochaine étape. |
| Question libre | Réponse directe, contexte élargi seulement si nécessaire. |

Le niveau de détail augmente à la demande. Un exemple source déjà disponible peut être affiché sans appel IA. Un exemple nouveau est indiqué comme créé par StudyPilot ; il ne devient pas artificiellement une citation du PDF. Les références utilisées renvoient à des passages identifiés. L'appartenance d'une référence au contexte peut être contrôlée automatiquement ; sa présence ne prouve pas à elle seule que toute la réponse est exacte.

Utiliser un rendu commun sûr pour paragraphes, vraies listes, titres, code et LaTeX. Ne pas transformer toutes les phrases en rubriques. Conserver une réponse en cours par conversation, empêcher les doubles envois et proposer une reprise explicite après erreur. Un affichage progressif pourra améliorer l'attente si le fournisseur le permet, mais ne réduira pas à lui seul les calculs.

### Exercices et vérification

Commencer par des exercices simples dont les données, la solution et la vérification sont maîtrisables. Une solution calculée doit indiquer ce qui a effectivement été vérifié. Exemples de contrôles : substitution dans une relation, produit matriciel, comparaison entre sortie attendue et sortie observée.

Ne pas promettre de traiter correctement tous les exercices, toutes les matières ou tout programme. Un premier périmètre raisonnable est : calculs simples via opérations contrôlées, code expliqué avec résultat attendu, puis exécution seulement dans un environnement isolé avec limites de temps et de ressources. Le processus Flask ne doit pas exécuter arbitrairement du code fourni par un cours ou par le chat. Une réponse simplement générée ne porte pas le statut « exécutée » ou « vérifiée ».

Le catalogue d'opérations vérifiables reste explicite. Les cas hors catalogue peuvent recevoir une aide raisonnée avec une indication précise des limites, ou une demande de clarification si l'énoncé manque. Il n'est pas utile de lancer automatiquement plusieurs modèles pour chaque réponse.

## Parcours de génération et budget

Parcours cible : extraction mise en cache → organisation pédagogique → rédaction des seuls noyaux → contrôle et publication. Exemples longs, approfondissements et entraînement restent disponibles depuis les sources ou sont produits à la demande.

Pour chaque lot borné par la taille du contexte : un appel d'organisation, un appel de rédaction, puis un contrôle sémantique ciblé ; les références, clés, destinations, cycles et délimiteurs sont vérifiés localement. Les formules transcrites, contradictions, preuves ambiguës ou omissions de conditions justifient des contrôles supplémentaires ciblés. Ne pas retirer ces garanties avant d'avoir comparé les résultats au parcours actuel.

La sélection, la suffisance et le regroupement doivent partager les mêmes unités documentaires et décisions persistées. L'objectif est de remplacer des relectures identiques, pas d'ajouter une nouvelle couche au moteur existant. Une reprise porte sur le lot ou l'élément défaillant. Un passage d'organisation entre parties peut rester nécessaire pour les notions répétées ; ce coût doit être comptabilisé.

Objectifs à mesurer, pas performances déjà obtenues : aucun appel pour réafficher une ressource enregistrée ; normalement un appel pour une réponse nouvelle disposant de son contexte ; appels supplémentaires uniquement pour un besoin identifié. Budgets globaux d'appels, de jetons et de reprises, qui incluent les tentatives réseau et les corrections de format. Arrêt explicite quand le budget est épuisé.

L'import reste séquentiel par étapes. Le chat doit pouvoir obtenir la priorité entre deux appels d'import, plutôt que subir toute la file. Pas d'analyse de toutes les notions après chaque message, pas de génération anticipée de tous les exercices. Les caches des réponses réutilisables incluent version du cours, notion, intention, niveau et données d'exercice ; les réponses dépendant de l'historique ne doivent pas être recyclées hors contexte.

## Ordre de réalisation

1. Définir le modèle commun noyau/ressources/destinations et les critères de pertinence. Produire un petit échantillon comparatif à partir de passages mathématiques, CSS et rédactionnels. Le noyau et les conditions doivent être compréhensibles avant de multiplier les migrations.
2. Adapter le générateur et son contrôle de couverture à ce contrat. Tester le parcours complet sur des supports nouveaux, en stockage isolé, avec budgets. Remplacer les anciennes étapes devenues équivalentes ; ne pas maintenir deux autorités de sélection.
3. Ajouter l'affichage court, les trois actions et le contexte explicite du chat. Réutiliser extraction, plan et notions par un service documentaire unique ; intégrer le rendu de code et de formules.
4. Ajouter les réponses par intention, puis le premier périmètre d'exercices vérifiables. Mesurer fidélité au contexte, longueur, exactitude des exemples et consommation réelle.
5. Migrer les collections existantes avec sauvegarde et liens de remplacement, puis retirer les branches obsolètes. La progression de plusieurs anciennes fiches fusionnées ne devient pas automatiquement « maîtrisée » : préserver le détail et redemander une révision du nouveau noyau si nécessaire.

Le prototype de présentation peut être réalisé dès l'étape 1 pour vérifier la lisibilité. La migration de tout le contenu arrive après validation du contrat commun, afin que les nouveaux imports et les cours existants aient le même comportement.

## Validation utile

Conserver quelques scénarios de bout en bout qui couvrent des risques différents :

- cours mathématique : hypothèses intactes, formule correcte, exemple rattaché et calcul simple vérifié ;
- cours de programmation : syntaxe minimale lisible, code complet à la demande, résultat distingué d'une exécution ;
- cours rédactionnel : sélection pertinente sans formule ni exemple ajouté artificiellement ;
- scan ou schéma : réutilisation de l'extraction, ambiguïtés visibles, aucune invention sur une zone illisible ;
- conversation : « cette formule », suivi, changement de notion et de cours, références dans la bonne version ;
- reprise : panne ou budget atteint, conservation des résultats valides, aucun doublon ni perte de progression.

Pour chaque scénario, évaluer séparément fidélité, pertinence des regroupements, lisibilité initiale, utilité de la réponse et coût. Inclure des vrais cours longs et variés avant de conclure à la généralisation. Les cinq petits documents synthétiques précédents ne suffisent pas.

Remplacer les tests d'anciennes étapes lorsque ces étapes disparaissent et conserver leurs garanties aux nouvelles frontières. Ne pas fixer un nombre arbitraire de tests, ni conserver plusieurs tests qui ne font que répéter la même assertion. Cette phase d'analyse n'a modifié aucun comportement et ne justifie pas une nouvelle exécution des suites applicatives.
