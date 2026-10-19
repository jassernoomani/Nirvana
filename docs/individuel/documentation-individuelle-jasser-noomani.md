# Documentation individuelle : utilisation de l'IA générative

**Étudiant :** Jasser Noomani (compte Git `jassernoomani`)
**Projet :** Nirvana, application web de restaurant avec modules d'IA
**Période couverte :** 18 et 19 octobre 2026

Ce document répond au critère individuel de la grille : *« Documentation individuelle : prompts, interactions avec les LLM et justification des modèles choisis »*, ainsi qu'à *« Présentation et argumentation des choix (gain de productivité) »*. Il s'appuie sur des traces vérifiables :
- l'historique complet de la session avec l'assistant, d'où viennent les citations ;
- l'historique Git du dépôt ;
- les captures d'écran du dossier `Screenshots/`.

## 1. Outils utilisés et leur rôle

| Outil | Rôle dans le projet |
|---|---|
| **Claude Code** (Anthropic, application de bureau, modèle Claude Opus) | Mon seul assistant d'IA pour le développement. Il travaille directement dans le dépôt : il lit le code, exécute les commandes et les tests dans un terminal, et vérifie les pages dans un navigateur intégré. Je l'ai utilisé pour planifier, générer le code, faire la revue de sécurité et de bugs, écrire les tests et mener l'évaluation des modèles. |
| **Ollama** avec `qwen2.5:3b` (et, pour comparaison, `llama3.2:3b` et `qwen2.5:1.5b`) | **Partie du produit, pas un outil de développement.** C'est le modèle local appelé par l'application pour analyser les avis et reclasser les recommandations. |
| **scikit-learn** | Partie du produit : modèle de prévision de la demande (forêt aléatoire). |

Il faut distinguer deux usages de l'IA dans ce projet :
- **l'IA comme outil de génie logiciel** : Claude Code, qui m'a aidé à construire, tester et évaluer l'application ;
- **l'IA intégrée au produit** : Ollama et scikit-learn, qui fournissent les fonctionnalités intelligentes du restaurant.

Ce document porte surtout sur le premier usage, et justifie aussi les modèles choisis pour le second (section 5).

## 2. Ma façon de travailler avec l'assistant

Quatre règles, appliquées tout au long du projet :

1. **Le plan avant le code.** Ma première demande sur le sujet a été : *« Let's discuss the plan first before writing code. »* L'assistant a proposé un plan en phases : nettoyage, base de données et données de démonstration, fonctionnalités, modules d'IA, livrables. C'est moi qui ai choisi par quoi commencer.
2. **Vérifier l'existant avant de modifier.** *« lets pull the project first and test it locally before doing anything »* : le projet a d'abord été installé et testé tel quel (4 tests back-end, build front-end, pages vérifiées dans le navigateur).
3. **Avancer pas à pas, avec validation.** Pour la revue de code et l'évaluation, j'ai exigé : *« start with item two gradually while explaining what are you going to do while confirming each step with me »*. Chaque étape était annoncée, puis exécutée seulement après mon accord.
4. **Je garde la main sur Git.** *« I'll commit it myself from my account. Give me the commit message to use. »* L'assistant ne commit ni ne pousse jamais. Je relis l'état du dépôt, puis je fais le commit et le push moi-même.

## 3. Journal des interactions, par phase

Les heures sont celles de la session (UTC+1). Les prompts sont cités tels quels, en anglais, la langue dans laquelle je les ai écrits.

### 3.1 Démarrage et plan (18 octobre)

| Mon prompt | Ce que l'IA a produit | Ce que j'ai vérifié ou décidé |
|---|---|---|
| *« check HANDOFF.md and later i will tell you what project we are going to work on »* | Une lecture des supports du cours et des consignes du professeur | Le contexte est partagé avant tout travail |
| *« @…2sujet (2).docx this is the doc file that contains the ai models we are going to work on. how should i start »* puis *« Let's discuss the plan first before writing code. »* | Un plan en 5 phases. Constat clé : les trois modules d'IA ont besoin de données (clients, allergies, historique de commandes, avis) qui n'existaient pas encore. | J'ai validé l'ordre : base de données d'abord, puis les fonctionnalités, puis l'IA |
| *« lets pull the project first and test it locally before doing anything »* | Une installation complète, avec tests et build. Elle a fait apparaître les versions de Python et de Node qui diffèrent du README. | J'ai noté le risque pour le PC de démonstration |
| *« ok lest start with phase 0 and 1 »* | Le modèle de données (utilisateurs, allergies, ingrédients, recettes, stock, commandes, réservations, avis), un script de génération de 90 jours d'historique réaliste et des tests | Commit `Add data model, demo data seed and tests` |

### 3.2 Fonctionnalités de l'application (18 et 19 octobre)

Pour chaque fonctionnalité, j'ai rédigé une **spécification structurée**. Elle donne le contexte, les exigences, les contraintes de sécurité et les cas d'erreur. Extrait du prompt d'authentification :

> *« Implement a simple, functional authentication system with two roles: Customer […] Staff […]. Requirements: […] Customers must not be able to access staff-only operations by manipulating frontend routes or requests. […] Never allow public registration to assign the staff role to an ordinary user. Use secure password hashing […]. Do not hardcode production credentials or expose secrets in source code. »*

| Fonctionnalité | Spécification envoyée | Résultat (commit) |
|---|---|---|
| Authentification, 2 rôles | Rôles, protection côté serveur, hachage, comptes de test | `Add login and sign-up with customer and staff roles` |
| Panier et commande | Parcours client en étapes numérotées, recalcul des prix côté serveur | `Add checkout and order creation` |
| Réservations | Formulaire, créneaux, validation des dates | `Add table reservations` |
| Stock (personnel) | Quantités, seuils, alerte de stock bas | `Add staff inventory page` |
| Tableau de bord cuisine | Trois colonnes : nouvelles, en préparation, prêtes | `Add kitchen dashboard` |
| Avis clients | Note de 1 à 5, commentaire, lien avec la commande | `Add customer reviews` |
| Intégration des six | *« Reuse the existing layout […] Provide login, loading, empty, success, and error states. […] Do not leave nonfunctional buttons, placeholder pages, mock-only workflows »* | `Unify navigation and mobile layouts across the app` |

J'ai aussi demandé un **compte rendu de fin de tâche** dans un format imposé : *« When finished, provide: 1. A summary of the existing architecture discovered. 2. A list of implemented features. 3. The files created or modified. […] 7. Test results, including any failures. […] 9. Any known limitations or remaining work. »* La capture `Screenshots/Prompt to generate final deliverables.png` montre ce prompt.

Après chaque fonctionnalité, j'ai testé l'application dans le navigateur. Les captures d'écran du dossier `Screenshots/` montrent les résultats.

### 3.3 Intégration du travail de Manef (18 octobre)

Manef Akrimi a développé les trois modules d'IA : recommandations, prévision et analyse des avis. Mes prompts : *« ok so my friend did some changes and pushed in the main branch »*, puis *« i downloaded the model now what »*.

L'assistant a :
- mis à jour ma copie ;
- relancé les tests (56 réussis) ;
- testé les trois modules avec le vrai modèle local.

Ces essais ont révélé un **problème réel** : le premier appel au modèle échouait, car le chargement en mémoire dépassait le délai de 90 s. Le délai a été porté à 180 s dans `.env`, et une procédure de préchauffage a été prévue avant la démonstration.

### 3.4 Détection de bugs et de vulnérabilités assistée par l'IA (19 octobre)

Après l'intégration, j'ai mené une revue en cinq étapes, chacune lancée par un prompt explicite :
- *« start with step 1 »* : mesure de la couverture de tests ;
- *« Yes, start step 2: the AI security review. »* ;
- *« Go to step 3: the bug and refactoring review. Fixes come in step 4. »* ;
- *« Yes, start part 4b: fix the four bugs. »* ;
- *« Yes, start part 4c: the refactoring (R1 to R5 and the front-end README), and include the B5 message fix. »*

Le détail est dans `AI_TESTING_AND_REVIEW.md`. En résumé :
- **10 constats de sécurité confirmés par l'exécution**, par exemple aucune limite aux tentatives de connexion : 30 mauvais mots de passe en 1,3 s, puis le bon accepté. 7 sont corrigés et 3 sont acceptés et documentés.
- **5 bugs corrigés**, dont l'historique de commandes limité à 50 sans pagination. Chaque correction back-end suit la règle **« le test d'abord »** : le test reproduit le bug, échoue, puis passe après la correction.
- **5 refactorisations** de code dupliqué.
- **Résultat :** les tests passent de 69 à 77, la couverture de 92 % à 94 %, et `pip-audit` n'a plus de vulnérabilité connue.

**Mes décisions dans cette phase :**
- choisir quels constats corriger et lesquels accepter ;
- reporter une refactorisation (R6) : elle touchait quatre pages pour peu de gain visible, si près de l'échéance.

### 3.5 Évaluation et optimisation des modèles (19 octobre)

Prompts : *« start with model evaluation »*, puis une étape à la fois :
- *« Yes, start step 2: the evaluation script that measures the current model on this set. »*
- *« Yes, start step 3 with prompt tuning, the injection patterns and the break fix. Ask me before downloading a second model. »*

Le détail est dans `EVALUATION.md`.

**Une décision que j'ai prise moi-même.** L'assistant proposait de remplacer le prompt v4 par v5. J'ai demandé : *« isnt it better to adopt v5 but also keep v4 or document it ? »*, puis j'ai décidé : *« adopt v5 in the app, keep v3 and v4 as reference prompts for the evaluation, and document all of them. »* Ainsi, l'évaluation reste reproductible et l'historique de l'optimisation reste visible.

**Résultats que j'ai validés :**
- **Analyse des avis :** la justesse du sentiment passe de 60 % à 87 %, sur un jeu de 53 avis étiquetés. Plus aucune injection de prompt n'est suivie.
- **Comparaison de modèles :** j'ai autorisé le téléchargement de deux modèles de plus (*« Download both llama3.2:3b […] and qwen2.5:1.5b […] and compare all three. »*). `qwen2.5:3b` reste le meilleur choix.
- **Prévision :** une validation glissante sur 30 semaines et la comparaison de 30 configurations. J'ai décidé de **ne pas modifier l'application** (*« Don't change the app; just write section 3 »*), car le gain venait de données synthétiques qui avantagent ce modèle.
- **Recommandations :** 0 violation d'allergie sur 4 017 recommandations. L'audit des recettes a révélé un vrai risque : la sauce du calamar n'est pas détaillée.

## 4. Quand l'IA s'est trompée, et comment l'erreur a été détectée

L'assistant n'est pas fiable par défaut. Chaque affirmation importante a été **vérifiée par l'exécution** : un test, une requête ou une mesure. Erreurs relevées pendant le projet :

| Erreur de l'IA | Comment elle a été détectée | Correction |
|---|---|---|
| Elle a affirmé que la dépendance `httpx2` était une faute de frappe | En installant le projet : le paquet existe et s'installe | Correction annoncée explicitement par l'assistant, aucune modification faite |
| Deux bugs dans le code de données de démonstration qu'elle avait généré : un avis en double sur une commande, des avis datés dans le futur | Par les tests automatisés | Code corrigé, tests conservés |
| Conclusion trop optimiste sur la résistance aux injections de prompt (« les protections tiennent ») | L'évaluation sur 53 avis a montré qu'une injection reformulée était suivie par le modèle | Filtre élargi, et constat S7 réévalué de « faible » à « moyen » dans la documentation |
| Un script de modification a corrompu l'expression régulière anti-injection : `\b` transformé en caractère de retour arrière | En vérifiant le fichier après la modification | Bloc réécrit avec une méthode sûre |
| Première mesure « v4 sans exemples » invalide : le filtre ne retirait en réalité aucun exemple | En vérifiant les résultats de la mesure | Filtre corrigé, mesure refaite, et erreur documentée dans `EVALUATION.md` |
| `llama3.2:3b` répétait la même réponse jusqu'à 8 fois, ce qui faisait échouer les appels | Par le script d'évaluation (4 appels échoués) | Schéma de sortie limité à une seule réponse, imposé pendant la génération : 0 échec ensuite, et protection valable pour tous les modèles |

**Leçon retenue :** la valeur de l'assistant vient de sa vitesse **combinée** à une vérification systématique. Sans tests ni mesures, trois de ces erreurs seraient passées dans le rendu.

## 5. Justification des modèles choisis

### 5.1 Pour le développement : Claude Code

- **Il agit dans le dépôt réel.** Il exécute les tests, lance les serveurs et vérifie les pages dans un navigateur. Il peut donc **prouver** ce qu'il affirme, au lieu de proposer du code à copier sans l'avoir testé.
- **Il a une vue d'ensemble du code**, ce qui est indispensable pour une revue de sécurité ou une refactorisation qui touche des dizaines de fichiers (45 fichiers pour le commit de revue).
- **Je n'ai pas utilisé d'autre assistant :** un seul outil donne un historique cohérent et entièrement traçable.

### 5.2 Pour le produit : le modèle local `qwen2.5:3b`

Ce modèle était le choix initial de Manef. Mon évaluation l'a **confirmé par des mesures** (`EVALUATION.md`, section 2) :

| Modèle et prompt | Justesse du sentiment | F1 des sujets | Temps médian par avis | Injections suivies |
|---|---|---|---|---|
| **qwen2.5:3b, v5 (retenu)** | **87 %** | **0,91** | 1,01 s | **0 sur 2** |
| llama3.2:3b, v4 (son meilleur prompt) | 81 % | 0,87 | 1,72 s | 0 sur 2 |
| qwen2.5:1.5b, v5 | 57 % | 0,84 | 0,56 s | 0 sur 2 |
| qwen2.5:1.5b, v4 | 64 % | 0,77 | 0,57 s | **1 sur 2** |

**Pourquoi un modèle local plutôt qu'une API dans le cloud :**
- **Confidentialité :** les avis ne quittent jamais le PC du restaurant. Cela répond à la consigne du cours : « jamais de données personnelles brutes envoyées au LLM ».
- **Robustesse :** pas de clé, pas de quota, pas de coût par requête, et un fonctionnement hors ligne.
- **Taille :** 3B est la plus petite taille de qualité suffisante ; 1.5B est nettement moins bon.

### 5.3 Pour la prévision : la forêt aléatoire, gardée par une référence simple

La validation sur 30 semaines montre que la forêt aléatoire **n'est pas meilleure** que la simple moyenne des 3 semaines précédentes (erreur 1,046 contre 1,042). Elle est conservée parce que :
- l'application compare toujours les deux modèles et publie le meilleur, ce qui protège le résultat ;
- une meilleure option (la régression de Poisson, avec 12 % d'erreur en moins) n'a été mesurée que sur des données synthétiques construites exactement sous sa forme. Elle doit être confirmée sur des données réelles avant d'être adoptée.

## 6. Techniques de prompt engineering utilisées (lien avec le chapitre 2 du cours)

| Technique du cours | Où je l'ai appliquée |
|---|---|
| **Contexte, tâche, format, contraintes** | Mes spécifications de fonctionnalités : contexte de l'application, exigences numérotées, contraintes de sécurité (*« Never allow public registration to assign the staff role »*) et format du compte rendu imposé (*« When finished, provide: 1. … 9. »*) |
| **Clarté et spécificité** | Des critères vérifiables plutôt que vagues : *« Provide login, loading, empty, success, and error states »* |
| **Itération** | Le travail découpé en étapes validées une à une, et les prompts de l'application améliorés en 3 versions mesurées (v3 → v4 → v5) |
| **Exemples (few-shot)** | Exemples dans le prompt v4 de l'application. Leur effet a été mesuré : ils améliorent la précision (0,95 contre 0,86 sans exemples), pas le sentiment |
| **Décomposition** | Prompt v5 : le modèle extrait seulement des citations, et le code en déduit le sentiment. Justesse : 64 % → 87 % |
| **Sortie JSON contrôlée** | Schéma JSON imposé par Ollama pendant la génération, puis validation Pydantic avant l'affichage |
| **Température** | 0, pour des résultats reproductibles et mesurables |
| **Défense contre l'injection de prompt** | Filtre des formulations suspectes, consigne de traiter le texte comme des données, et obligation de citer le texte exact de l'avis. Testé avec de vraies attaques |

## 7. Gain de productivité

**Méthode.** Pour chaque tâche, je mesure la durée entre l'envoi de la spécification et le commit, d'après l'horodatage de la session et de Git. Cette durée inclut la génération par l'IA, ma relecture et les tests automatiques. Elle n'inclut pas la rédaction de la spécification elle-même. Ces durées sont **mesurées**. La colonne « sans IA » est mon **estimation** du temps nécessaire en écrivant le code à la main : un ordre de grandeur, pas une mesure.

| Tâche | Durée avec l'IA (mesurée) | Estimation sans IA |
|---|---|---|
| Modèle de données, script de données de démonstration, tests | 15 min | 1 jour |
| Authentification, 2 rôles | 10 min | 1 jour |
| Panier et commande | 7 min | 1 jour |
| Réservations | 6 min | 0,5 jour |
| Page de stock | 6 min | 0,5 jour |
| Tableau de bord cuisine | 7 min | 0,5 jour |
| Avis clients | 6 min | 0,5 jour |
| Intégration et adaptation mobile | 8 min | 0,5 jour |
| Revue de sécurité, de bugs et de refactorisation, avec corrections | 50 min | 2 jours |
| Évaluation des modèles (5 sections, 5 scripts, 2 téléchargements de modèles) | 1 h 25 | 3 à 4 jours |

**Analyse :**
- **Le gain est le plus grand sur le code de structure :** formulaires, API, pages d'administration.
- **Ce que le gain ne comprend pas :**
  - Le code généré a aussi introduit des erreurs. Deux bugs de données ont été trouvés plus tard par les tests, et cinq bugs par la revue (section 3.4).
  - Le temps économisé à l'écriture se reporte en partie sur la **vérification**, qui reste indispensable.
- **Le gain qualitatif compte autant que le temps :**
  - une couverture de tests de 94 % ;
  - une revue de sécurité systématique ;
  - une évaluation chiffrée des modèles.

  Sans assistant, ces trois activités sont souvent sacrifiées dans un projet d'une semaine.
- **Le facteur humain reste décisif :** l'ordre des tâches, le refus de modifier l'application sans preuve sur données réelles, la conservation des anciens prompts et le choix des constats à corriger sont des décisions que j'ai prises, pas l'IA.

## 8. Ce que je retiens

- **Un assistant de code est plus utile quand on lui donne une spécification précise et qu'on exige des preuves :** tests, mesures, captures.
- **Il faut le faire avancer par étapes validées :** c'est ce qui m'a permis de garder le contrôle sur un volume de code que je n'aurais pas pu écrire seul en deux jours.
- **Mesurer avant de changer :** plusieurs « améliorations » évidentes (forêt réglée, réordonnancement par le LLM) se sont révélées nulles ou négatives une fois mesurées.
