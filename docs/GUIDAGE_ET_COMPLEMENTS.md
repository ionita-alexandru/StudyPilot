# Révisions guidées, Express et compléments PDF

Première version du 19 octobre 2026. Les trois parcours utilisent la même session,
les mêmes fiches, la même progression et le même assistant.

## Préparer sa révision

Depuis Apprendre, choisir Préparer ma révision ou J’ai peu de temps · Express.
Choisir le cours, le périmètre, le niveau déclaré, l’objectif et le temps disponible.
Les trois repères facultatifs sont des autoévaluations, pas un diagnostic validé.
Les notes libres sont transmises à l’assistant lorsqu’une notion est sélectionnée.

Guidé suit les bases dans l’ordre du cours et revient sur les difficultés déclarées.
Express privilégie les difficultés, les prérequis identifiés et les notions non
encore abordées ; un débutant conserve l’ordre des bases. Libre propose les fiches
dans leur ordre, sans ce classement. Les prérequis ne sont reliés que lorsqu’un nom
correspond sans ambiguïté à une notion publiée. L’absence de lien ne prouve pas
qu’il n’existe aucun prérequis.

Le programme est calculé localement, sans appel IA, depuis les métadonnées du
cours et les observations du navigateur. Il affiche les activités retenues,
les durées estimées et les notions reportées. Ce classement n’est pas une preuve
que certaines notions tombent plus souvent à un examen. Les temps ne sont pas
encore calibrés par une étude d’usage ; le niveau et l’objectif modulent l’estimation.

Le budget comprend activités, pauses prévues et deux minutes de bilan pour une
session d’au moins dix minutes. Une pause manuelle suspend une durée, mais une
heure limite continue de courir. Le compteur utilise l’heure réelle ; les longues
périodes en arrière-plan sont prises en compte. Il ne prouve pas un travail effectif.

Pendant la session : rappel sans regarder, fiche, exemple ou exercice dans le chat,
autoévaluation, possibilité de passer une notion et d’ajuster le temps restant.
Une difficulté peut provoquer un second passage, au maximum deux tentatives de
lecture par notion, et le report d’une activité tardive si nécessaire.
L’autoévaluation n’est jamais présentée comme une réussite d’exercice.

Une session en cours est conservée dans le navigateur et reprend en pause. Une
heure limite garde son échéance. Après une évolution des documents, la reprise
recalcule les activités depuis les données actualisées ; les observations restent
conservées. Les documents ajoutés pendant une session peuvent aussi être intégrés
avec Ajuster le temps restant. Une même sauvegarde active est conservée par navigateur.

## Ajouter un document

Dans Mes documents, ajouter un PDF en précisant son rôle et son périmètre :

- TD, annale, corrigé, article ou complément de cours ;
- À apprendre : nouvelles notions ajoutées au catalogue et au programme ;
- Entraînement ou approfondissement : ressources consultables et contexte du chat,
  sans élargissement automatique des notions obligatoires.

Un même PDF ne peut pas être rattaché deux fois au cours, y compris le PDF principal.
La préparation réutilise la file d’import à un seul travailleur. Elle extrait le
texte/OCR une fois, rédige les lots, les fait relire et conserve les lots validés.
Une passe est plafonnée à huit appels de contrat IA ; les budgets réseau et de
jetons existants restent appliqués. Un document long peut nécessiter Reprendre.
Changer son rôle impose une nouvelle préparation ; changer son périmètre seul
ne régénère pas le contenu. Les nouvelles notions portent des identifiants stables.

Les contenus portent le document et la page physique. Le chat sélectionne au plus
sept passages et 10 500 caractères, dont au plus deux passages complémentaires.
Les corrigés sont exclus de la récupération ordinaire et des exemples automatiques ;
ils sont accessibles sur demande de correction ou après ouverture explicite du document.
Les désaccords entre documents doivent être signalés par l’assistant, pas résolus
silencieusement. Cette consigne ne constitue pas un détecteur exhaustif de contradictions.

Les nouveaux noyaux sont regroupés à part dans le catalogue, sous le titre du
complément. Leur rattachement technique à une partie permet le tutorat existant ;
il ne prétend pas établir une nouvelle structure pédagogique parfaite.

## Moteur IA

Gemma reste le moteur actif de cette installation. Un adaptateur Gemini Flash utilise
le transport Google commun et une liste explicite de modèle autorisé.
Il ne bascule pas automatiquement de fournisseur et n’active pas la facturation.
Google publie une offre gratuite pour [Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/pricing),
avec des limites propres au projet. Après déclaration du forfait gratuit par
l’utilisateur, un [essai sur trois cas fictifs](ESSAI_IA_2026-10-20.md) a réussi avec
chaque moteur. Le paramètre de réflexion de Gemini a été corrigé. Aucun gain de
qualité n’est démontré sur cet échantillon ; le moteur actif est conservé. La
génération réelle de compléments avec Gemini reste à évaluer.
La [campagne approfondie](ESSAI_IA_APPROFONDI_2026-10-20.md) valide ensuite la
rédaction/relecture Gemini d’un mini-cours fictif déjà extrait. Elle relève des
échecs de contrat et une validation trop permissive d’une description de figure
avec Gemma. Cela ne valide pas l’import complet d’un PDF ni tous les domaines.

Les conditions et notations d’une fiche sont aussi conservées dans les chapitres,
la révision et le contexte du chat. Les clés de prérequis reconnues dans un lot sont
converties vers les titres. Une source avec visuels reste signalée « visuel à vérifier »
dans la couverture, même si son texte a une destination.

Configuration une fois ces points vérifiés : `STUDYPILOT_AI_PROVIDER=gemini`,
`STUDYPILOT_MODEL=gemini-3.8-flash`, clé dans `GEMINI_API_KEY`, puis redémarrage.
Aucune clé ne doit être écrite dans les sources, les captures ou Git.
L’essai du second PC reste conditionné à un gain réel ; aucune installation réseau
ni hypothèse sur son système n’est faite ici.

## Vérifications et limites

123 tests Python et 8 tests JavaScript réussis. Tests utiles ajoutés : budgets et
prérequis, échéance pendant une pause, longues périodes en arrière-plan, documents
dupliqués, reprise sans régénérer un lot, périmètre obligatoire/facultatif, références
au bon PDF, exclusion des corrigés, conservation de l’exercice après ajout d’un document,
et sélection explicite de Gemini avec rejet d’un modèle non autorisé.

Contrôles navigateur : programme Express débutant de 30 minutes, début par les bases,
lancement, pause, rappel, reprise après rechargement, passage à 20 minutes, et formulaire
de complément sur petit écran. La séparation des sources et les routes des PDF sont
vérifiées avec des documents synthétiques et une génération simulée dans les tests.
La qualité de génération d’un complément réel n’a pas été évaluée dans ces contrôles.
L’essai limité des modèles, réalisé ensuite, est décrit séparément ci-dessus.

Le guidage reste fondé sur des règles locales et les métadonnées publiées. Un document
peut contenir une figure ou une formule insuffisamment transcrite ; consulter l’original
reste nécessaire. Les contrôles actuels ne prouvent ni compréhension parfaite du PDF,
ni couverture exhaustive, ni maîtrise globale du cours par l’élève.
