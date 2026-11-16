# Évaluation : que change le modèle local par rapport aux règles seules ?

Question posée : **les tâches de XamKids nécessitent-elles vraiment un agent, et un modèle de langage ?**
Cette évaluation mesure, sur la classe fictive, ce que le modèle local (Llama 3.1 8B, via Ollama) apporte,
ce qu'il n'apporte pas, et ce que la vérification par le code rattrape.

```
.venv/bin/python -m evals.run_evals --runs 3     # base jetable dans evals/.work, jamais les données de la plateforme
```

- Données : les 10 élèves fictifs de `xamkids/records/seed.py` (CI → CM2, cinq années d'historique).
- Réponses attendues : écrites à la main à partir des profils (`EXPECTED` dans `evals/run_evals.py`).
- 3 passages du modèle par élève (température 0,1 : les sorties varient d'un passage à l'autre).
- Résultats bruts : `evals/results.json`. Versions précédentes conservées pour comparaison.

## Deux décisions évaluées

1. **Choix de l'hypothèse** (la « piste ») : quelle difficulté durable tester, et quelle explication
   (`locale` : la compétence elle-même ; `lecture` : la lecture du texte ; `rythme` : des réponses trop rapides).
   Les règles utilisent tous les signaux chiffrés (gravité, effet de la lecture à voix haute, part de réponses
   en moins de 5 s). Le modèle reçoit les mêmes chiffres **et** les observations écrites des enseignants.
2. **Contradictions** entre une observation écrite et les chiffres du même trimestre (par exemple « Fatou a du
   mal en calcul » face à 100 % de réussite en calcul). Les règles ne lisent pas le texte : elles n'en trouvent
   aucune. Le modèle propose ; le code vérifie que l'observation parle bien de la compétence et que le chiffre la
   contredit vraiment ; l'agent pose alors une question à l'enseignant, sans rien conclure.

## Résultats (version finale du code, 3 passages)

| Élève | Piste attendue | Règles | Agent avec modèle (bonnes / passages) | Décisions du modèle rejetées | Contradictions attendues | Questions justes | Fausses questions | Propositions bloquées par le code |
|---|---|---|---|---|---|---|---|---|
| Awa | probleme_multi_etapes:locale | probleme_multi_etapes:locale ✅ | 3/3 | 3/3 | aucune | — | 0 | 23 |
| Moussa | decodage:locale *ou* probleme_multi_etapes:lecture | decodage:locale ✅ | 3/3 | 0/3 | aucune | — | 0 | 3 |
| Fatou | aucune | aucune ✅ | 3/3 | — | calcul | 3/3 | 0 | 3 |
| Ibrahima | aucune | aucune ✅ | 3/3 | — | aucune | — | 0 | 36 |
| Aminata | calcul:locale *ou* numeration:locale | numeration:locale ✅ | 3/3 | 0/3 | numeration | 2/3 | 0 | 3 |
| Cheikh | *:rythme | grammaire:rythme ✅ | **1/3** | 1/3 | aucune | — | 0 | 3 |
| Mariama | aucune | aucune ✅ | 3/3 | — | aucune | — | 0 | 5 |
| Ousmane | aucune (bruit) | probleme_simple:locale ❌ | 0/3 | 1/3 | aucune | — | 0 | 0 |
| Khady | aucune | aucune ✅ | 3/3 | — | aucune | — | 0 | 3 |
| Lamine | aucune | aucune ✅ | 3/3 | — | aucune | — | 0 | 0 |

« Décisions du modèle rejetées » : la décision du modèle a échoué à l'auto-vérification (action inconnue,
piste inexistante…) et l'agent a appliqué celle des règles. « — » : le modèle n'est pas appelé, car il n'y a
aucune piste à départager.

## Ce que nous en concluons

**1. Pour choisir l'hypothèse, le modèle n'apporte rien de mesurable, et il fait parfois moins bien.**
Les règles trouvent la bonne piste pour 9 élèves sur 10. Le modèle ne fait jamais mieux. Pour Cheikh, il choisit
2 fois sur 3 « problèmes à une étape, piste locale », alors que sa propre justification parle de réponses trop
rapides. Pour Awa, sa sortie est mal formée à chaque passage (« proposer_exercices »), et la vérification la
remplace par la décision des règles. Avec des signaux chiffrés, **le code suffit, et il est plus fiable**.

**2. Pour lire ce qu'écrivent les enseignants, le modèle est utile, mais seulement s'il est vérifié.**
- Avec vérification complète : 5 contradictions justes sur 6, **0 fausse question**.
- Sans le contrôle du sujet (version précédente, `results_v1_sans_controle_du_sujet.json`) : le modèle rattachait
  des phrases sans rapport à une compétence (« arrive souvent en retard » → calcul ; « hospitalisé » →
  numération). Résultat : les mêmes 5 questions justes, mais **16 fausses questions** sur 30 exécutions.
- Le modèle seul propose beaucoup de contradictions fausses : 79 propositions bloquées par le code en 30
  exécutions. Sans vérification, l'enseignante serait noyée de questions.

Le partage des rôles qui fonctionne : le **modèle** juge si une phrase est positive ou négative (« maîtrise bien
les grands nombres » contre « difficultés avec les grands nombres » : les mêmes mots-clés, des sens opposés) ;
le **code** vérifie que la phrase parle de la compétence et que le chiffre la contredit.

**3. Ce qui fait de XamKids un agent ne dépend pas du modèle.**
La boucle former une hypothèse → choisir le test par contraste → attendre la validation de l'enseignant → attendre
les réponses de l'élève (des jours plus tard) → replanifier → conclure ou demander, tourne entièrement en mode
règles (vérifié de bout en bout pour Cheikh : constat « réussit quand on l'invite à prendre son temps (2/2) mais
échoue en répondant vite (0/3) »). L'agentivité est dans cette boucle longue, avec ses pauses humaines, pas dans
le modèle de langage.

**4. Le bruit statistique est réel.** Ousmane est signalé (problèmes à une étape) par le hasard : 6 réponses
par trimestre, c'est peu. Ni les règles ni le modèle ne l'évitent. C'est le rôle des exercices ciblés : tester
avant de conclure, et écarter l'hypothèse si l'élève réussit.

## Coût mesuré (MacBook, Llama 3.1 8B local, sans GPU dédié)

- Choix de l'hypothèse par le modèle : 11 à 19 s par élève (0 s quand il n'y a rien à départager).
- Recherche de contradictions : 5 à 77 s par élève, selon le nombre d'observations récentes.
- Règles seules : moins d'une seconde. Aucun coût monétaire : tout tourne en local, rien ne quitte l'école.

## Limites de cette évaluation

- **Données fictives** : les réponses attendues ont été écrites par l'équipe qui a créé les données. Une vraie
  évaluation demande des dossiers réels anonymisés, annotés par des enseignants.
- **Petit échantillon** : 10 élèves, 3 passages, 2 contradictions placées volontairement.
- Le contrôle du sujet repose sur une **liste de mots-clés** (`SKILL_KEYWORDS`) : il manquera des contradictions
  formulées autrement (rappel plus faible, précision privilégiée).
- Un seul modèle testé (Llama 3.1 8B). Un modèle plus grand ferait peut-être mieux pour choisir l'hypothèse : à
  mesurer avec ce même script avant de le croire.
