"""Catalogue anglais de l'agent (xamkids/agent/*, live.py, records/seed.py). Clé = texte français exact."""

EN = {
    # -- contradictions.py ---------------------------------------------------------
    "Votre observation du {term} dit : « {quote} » Or, ce même trimestre, {name} réussit {acc} des exercices {of} "
    "({n} réponses). Les deux ne vont pas ensemble : je n'en tire aucune conclusion. Pouvez-vous me dire ce que vous "
    "observez ?":
        "Your observation from {term} says: \"{quote}\" Yet in that same term, {name} got {acc} of the exercises {of} "
        "right ({n} answers). The two do not match: I am not drawing any conclusion. Can you tell me what you see in "
        "class?",
    "observation {id} introuvable": "observation {id} not found",
    "type « {type} » inconnu": "unknown type \"{type}\"",
    "observation {id} : elle ne parle pas de « {skill} »": "observation {id}: it does not talk about \"{skill}\"",
    "pas de chiffres en « {skill} » au {term}": "no figures for \"{skill}\" in {term}",
    "observation {id} : {acc} en {skill}, ce n'est pas faible": "observation {id}: {acc} in {skill} is not low",
    "observation {id} : {acc} en {skill}, ce n'est pas nettement bon":
        "observation {id}: {acc} in {skill} is not clearly good",

    # -- documents.py --------------------------------------------------------------
    "L'image est trop floue pour être lue de façon fiable.": "The image is too blurry to be read reliably.",
    "Le modèle de vision ({model}) n'est pas installé : je ne peux pas lire l'image.":
        "The vision model ({model}) is not installed: I cannot read the image.",
    "Le modèle de vision n'a pas pu lire le tableau.": "The vision model could not read the table.",
    "Valeur illisible pour {first} {last}.": "Unreadable value for {first} {last}.",
    "« {name} » ne figure pas dans la classe : nouvel élève ou erreur de saisie ?":
        "\"{name}\" is not in the class: a new learner or a typing mistake?",
    "La photo du livret est trop floue pour être lue de façon fiable : merci d'en reprendre une.":
        "The photo of the report card is too blurry to be read reliably: please take another one.",
    "Le modèle de vision ({model}) n'est pas installé : je ne peux pas lire la photo. Vous pouvez recopier le livret "
    "en CSV ({columns}).":
        "The vision model ({model}) is not installed: I cannot read the photo. You can copy the report card into a CSV "
        "file ({columns}).",
    "Le modèle de vision n'a pas pu lire le livret.": "The vision model could not read the report card.",
    "Année scolaire illisible ou mal écrite ({where}).": "School year unreadable or badly written ({where}).",
    "Le livret contient l'année en cours ou une année future ({where}) : ligne écartée.":
        "The report card contains the current year or a future year ({where}): line set aside.",
    "Niveau inconnu « {level} » ({where}).": "Unknown level \"{level}\" ({where}).",
    "Trimestre illisible ({where}).": "Unreadable term ({where}).",
    "Matière illisible ({where}).": "Unreadable subject ({where}).",
    "Note illisible ou incohérente ({where} : {score} sur {max}).":
        "Unreadable or inconsistent mark ({where}: {score} out of {max}).",
    "Matière en double pour le même trimestre ({where}).": "Subject listed twice for the same term ({where}).",
    "Le matricule {mat} correspond à {first} {last}, mais le livret est au nom de {name} : lequel est le bon ?":
        "Student ID {mat} belongs to {first} {last}, but the report card is in the name of {name}: which one is right?",
    "{name} est dans la classe avec le matricule {known}, mais le livret indique {mat} : s'agit-il du même élève ?":
        "{name} is in the class with student ID {known}, but the report card says {mat}: is this the same learner?",
    "Le fichier ne suit pas le format attendu ({columns}) : {error}.":
        "The file does not follow the expected format ({columns}): {error}.",
    "Valeurs incohérentes pour {name} : {present} présents sur {total} jours.":
        "Inconsistent values for {name}: present {present} out of {total} days.",
    "Le livret ne suit pas le format attendu ({columns}) : {error}.":
        "The report card does not follow the expected format ({columns}): {error}.",
    "Barème contradictoire ({where} : {score} sur {max}).": "Contradictory marking scale ({where}: {score} out of {max}).",

    # -- nodes.py ------------------------------------------------------------------
    "Planification": "Planning",
    "Un document est arrivé : le lire, vérifier sa cohérence avec la liste de classe, puis le faire confirmer par "
    "l'enseignant.":
        "A document has arrived: read it, check it against the class list, then have the teacher confirm it.",
    "Vérification que je me suis programmée le {date} : {reason} ": "Check I scheduled for myself on {date}: {reason} ",
    " Serveurs indisponibles : {missing}.": " Unavailable servers: {missing}.",
    "Analyse des réponses (analyze_answers)": "Answer analysis (analyze_answers)",
    "{n} réponse(s) classée(s) ({scope}). Erreurs dominantes : {dominant}.":
        "{n} answer(s) classified ({scope}). Dominant errors: {dominant}.",
    "aucune": "none",
    "{terms} trimestres, {n} réponses, {obs} observations, {findings} constats déjà enregistrés.":
        "{terms} terms, {n} answers, {obs} observations, {findings} findings already recorded.",
    "Historique (get_learner_timeline)": "History (get_learner_timeline)",
    "Je n'ai aucun historique de {name} avant cette année : je ne peux donc rien dire de durable. Pouvez-vous "
    "m'envoyer une photo de son livret scolaire ?":
        "I have no history for {name} before this year, so I cannot say anything about lasting patterns. Could you "
        "send me a photo of {name}'s report card?",
    "Information manquante : aucun historique avant cette année. ": "Missing information: no history before this year. ",
    "Livret scolaire demandé à l'enseignant.": "Report card requested from the teacher.",
    "Livret déjà demandé à l'enseignant, en attente.": "Report card already requested from the teacher, waiting.",
    "serveur MCP xamkids-profile": "MCP server xamkids-profile",
    "repli local": "local fallback",
    "non vérifié (bac à sable indisponible)": "not checked (sandbox unavailable)",
    "vérifié dans le bac à sable Run Python": "checked in the Run Python sandbox",
    "ÉCART avec le bac à sable Run Python": "MISMATCH with the Run Python sandbox",
    "{skill} ({n} trim.)": "{skill} ({n} terms)",
    "Tendances calculées ({where}, {check})": "Trends computed ({where}, {check})",
    "Tendances durables : {flagged}. Baisses généralisées : {dips}.":
        "Lasting trends: {flagged}. General dips: {dips}.",
    "Croisement observations / chiffres": "Observations / figures cross-check",
    "Sans modèle de langage, je ne sais pas lire les observations écrites : étape sautée.":
        "Without a language model, I cannot read written observations: step skipped.",
    "{n} observation(s) récente(s) relue(s) avec les chiffres de leur trimestre. ":
        "{n} recent observation(s) reread against the figures for their term. ",
    "{found} contradiction(s) vérifiée(s) par le calcul, {asked} nouvelle(s) question(s) posée(s).":
        "{found} contradiction(s) confirmed by calculation, {asked} new question(s) asked.",
    "Aucune contradiction.": "No contradiction.",
    " Propositions du modèle rejetées par le calcul : ": " Model suggestions rejected by calculation: ",
    " (modèle local, vérifié par le calcul)": " (local model, checked by calculation)",
    "Points forts et suivi": "Strengths and follow-up",
    "Rien de nouveau.": "Nothing new.",
    "Point(s) fort(s) durable(s) : ": "Lasting strength(s): ",
    "{n} point(s) fort(s) enregistré(s)": "{n} strength(s) recorded",
    "Absences en hausse : {days} jours d'absence au {term} ({rate} de présence), contre {mean} de présence en "
    "moyenne sur les trois trimestres précédents.":
        "Rising absences: {days} days absent in {term} ({rate} attendance), compared with {mean} attendance on "
        "average over the previous three terms.",
    "À surveiller. {statement} Ce n'est pas une conclusion : à évoquer avec la famille si vous le jugez utile.":
        "To watch. {statement} This is not a conclusion: raise it with the family if you think it useful.",
    "Absences en hausse : vérifier si la présence revient à la normale.":
        "Rising absences: check whether attendance returns to normal.",
    "absences en hausse : point à surveiller enregistré, vérification programmée {when}":
        "rising absences: point to watch recorded, check scheduled {when}",
    " — Présence revenue à {rate}.": " — Attendance back to {rate}.",
    "présence revenue à la normale": "attendance back to normal",
    " — Progrès nets sur les deux derniers trimestres.": " — Clear progress over the last two terms.",
    "Bonne nouvelle : la difficulté en {skill} ne se retrouve plus sur les deux derniers trimestres.":
        "Good news: the difficulty in {skill} no longer shows over the last two terms.",
    "difficulté en {skill} marquée comme résolue": "difficulty in {skill} marked as resolved",
    "Difficulté toujours présente en {skill} ({n} trimestres consécutifs). {statement}":
        "Difficulty still present in {skill} ({n} consecutive terms). {statement}",
    "difficulté persistante signalée ({skill})": "persistent difficulty reported ({skill})",
    "générés par le modèle local": "generated by the local model",
    "choisis dans la banque": "chosen from the bank",
    " (exercices du modèle refusés par le serveur)": " (the model's exercises were refused by the server)",
    "Échec de la proposition : {refused}": "Proposal failed: {refused}",
    "Exercices ciblés refusés": "Check exercises refused",
    ", dont {n} écoutés (texte lu à l'élève)": ", including {n} listened to (text read to the learner)",
    ", dont {n} en prenant son temps": ", including {n} done while taking time",
    ", dont {n} de contraste en {skill}": ", including {n} contrast exercises in {skill}",
    "Changement de piste : nouveaux exercices ciblés (propose_exercises)":
        "Change of explanation: new check exercises (propose_exercises)",
    "Exercices ciblés proposés (propose_exercises)": "Check exercises proposed (propose_exercises)",
    "{n} exercices {source}{contrast}, EN ATTENTE de validation. Hypothèse : {hypothesis}":
        "{n} exercises {source}{contrast}, AWAITING approval. Hypothesis: {hypothesis}",
    "Exercices refusés par {teacher} : {comment}. Hypothèse laissée ouverte, rien n'est enregistré.":
        "Exercises declined by {teacher}: {comment}. Hypothesis left open, nothing recorded.",
    "sans commentaire": "no comment",
    "Décision de l'enseignant : refus": "Teacher's decision: declined",
    "Décision de l'enseignant : exercices validés": "Teacher's decision: exercises approved",
    "Exercices ciblés réalisés par l'élève": "Check exercises completed by the learner",
    "Séance {session} : nouvelles informations, je refais mon plan.":
        "Session {session}: new information, I am planning again.",
    "Hypothèse écartée : {hyp} Les exercices ciblés ont été réussis à {acc}.":
        "Hypothesis ruled out: {hyp} The check exercises were passed at {acc}.",
    "Hypothèse écartée après les exercices ciblés.": "Hypothesis ruled out after the check exercises.",
    "Hypothèse écartée (update_profile, statut ruled_out)": "Hypothesis ruled out (update_profile, status ruled_out)",
    "Constat refusé par le serveur : {refused}": "Finding refused by the server: {refused}",
    "Constat refusé": "Finding refused",
    "Difficulté durable confirmée. {statement} {n} sources citées dans le profil.":
        "Lasting difficulty confirmed. {statement} {n} sources cited in the profile.",
    "Difficulté en {skill} : vérifier si elle persiste ou se résout.":
        "Difficulty in {skill}: check whether it persists or resolves.",
    "Difficulté enregistrée (constat n°{id}) et enseignant alerté. Prochaine vérification {when}.":
        "Difficulty recorded (finding no. {id}) and teacher alerted. Next check {when}.",
    "Constat enregistré (update_profile), enseignant alerté (alert_teacher), vérification programmée "
    "(schedule_followup)":
        "Finding recorded (update_profile), teacher alerted (alert_teacher), check scheduled (schedule_followup)",
    "{statement} Je reviendrai vérifier {when}.": "{statement} I will check again {when}.",
    "plus tard": "later",
    "(non programmée)": "(not scheduled)",
    "Question posée à l'enseignant.": "Question asked to the teacher.",
    "Question à l'enseignant (alert_teacher)": "Question to the teacher (alert_teacher)",
    "Aucun constat validé par l'enseignant : rien à résumer pour la famille. Validez d'abord les constats du profil.":
        "No finding validated by the teacher: nothing to summarise for the family. Validate the profile's findings "
        "first.",
    "Résumé pour la famille non rédigé": "Family summary not written",
    "Résumé pour la famille rédigé, en attente de validation.": "Family summary written, awaiting approval.",
    "Résumé refusé : {refused}": "Summary refused: {refused}",
    "Résumé pour la famille (draft_guardian_summary)": "Family summary (draft_guardian_summary)",
    "Fondé sur {n} constat(s) validé(s) par l'enseignant. En attente de relecture et de validation.":
        "Based on {n} finding(s) validated by the teacher. Awaiting review and approval.",
    "Document « {file} » : je préfère vous demander plutôt que deviner. ":
        "Document \"{file}\": I would rather ask you than guess. ",
    " {n} ligne(s) lue(s) sans problème, à confirmer.": " {n} line(s) read without problems, to be confirmed.",
    "Document « {file} » lu ({how}) : {n} lignes de présence. Merci de vérifier avant import.":
        "Document \"{file}\" read ({how}): {n} attendance lines. Please check before importing.",
    "Question posée à l'enseignant sur le document.": "Question asked to the teacher about the document.",
    "Lecture soumise à l'enseignant.": "Reading submitted to the teacher.",
    "Lecture du document ({how})": "Document reading ({how})",
    "échec": "failed",
    "Appréciation {level} {year} T{term} non reprise : elle contient un terme diagnostique ou une étiquette, que "
    "XamKids n'enregistre jamais.":
        "Comment {level} {year} T{term} not kept: it contains a diagnostic term or a label, which XamKids never "
        "records.",
    "élève inconnu": "unknown learner",
    "{n} note(s) sur {years} année(s) ({first} → {last}) et {kept} appréciation(s)":
        "{n} mark(s) over {years} year(s) ({first} → {last}) and {kept} comment(s)",
    "aucune note lisible": "no readable mark",
    "élève de la classe": "learner in the class",
    "nouvel élève : il sera inscrit dans la classe à la confirmation":
        "new learner: will be enrolled in the class on confirmation",
    "élève à identifier": "learner to be identified",
    "Livret de {name} ({who}) lu ({how}) : {summary}. Le rang et les moyennes de classe ne sont jamais repris.":
        "Report card of {name} ({who}) read ({how}): {summary}. Class rank and class averages are never kept.",
    " Je préfère vous demander plutôt que deviner : ": " I would rather ask you than guess: ",
    "Livret soumis à l'enseignant pour confirmation.": "Report card submitted to the teacher for confirmation.",
    "Question posée à l'enseignant sur le livret.": "Question asked to the teacher about the report card.",
    "Lecture du livret scolaire ({how})": "Report card reading ({how})",
    "Le serveur Filesystem est indisponible : je ne peux pas lire le document.":
        "The Filesystem server is unavailable: I cannot read the document.",
    "CSV lu par le serveur Filesystem": "CSV read by the Filesystem server",
    "Impossible de lire l'image.": "Unable to read the image.",
    "photo lue par le serveur Filesystem et le modèle de vision": "photo read by the Filesystem server and the vision model",
    "Format non pris en charge : {ext}.": "Unsupported format: {ext}.",
    "Terminé.": "Done.",
    "Fin de l'exécution": "End of run",

    # -- planning.py ---------------------------------------------------------------
    "Faire le point complet de fin de trimestre.": "Carry out the full end-of-term review.",
    "Voir ce que la séance apporte au profil.": "See what the session adds to the profile.",
    "Évaluer l'hypothèse avec les réponses aux exercices ciblés.":
        "Evaluate the hypothesis with the answers to the check exercises.",
    "Préparer un résumé pour la famille à partir des constats validés.":
        "Prepare a family summary from the validated findings.",
    "Vérifier si le constat suivi persiste, se résout ou s'aggrave.":
        "Check whether the finding being followed persists, resolves or gets worse.",
    "Analyser la situation de l'élève.": "Analyse the learner's situation.",
    "Plan par défaut pour ce déclencheur.": "Default plan for this trigger.",
    "étape inconnue « {s} » retirée": "unknown step \"{s}\" removed",
    "« {s} » retiré : interdit pour ce déclencheur": "\"{s}\" removed: not allowed for this trigger",
    "« {s} » ajouté : obligatoire pour ce déclencheur": "\"{s}\" added: required for this trigger",
    "« {p} » ajouté : nécessaire avant « {s} »": "\"{p}\" added: needed before \"{s}\"",
    "ordre des étapes rétabli": "step order restored",
    "focus élargi à toutes les matières : une revue de trimestre examine tout":
        "focus widened to all subjects: a term review examines everything",
    "modèle local": "local model",
    "règles": "rules",
    " (sortie du modèle invalide)": " (invalid model output)",
    "Objectif : {objective} Plan : {labels}. Matière : {focus}. Pourquoi : {why} Vérification du plan : ":
        "Objective: {objective} Plan: {labels}. Subject: {focus}. Why: {why} Plan check: ",
    "conforme.": "compliant.",
    "Planification ({source})": "Planning ({source})",

    # -- runner.py / toolkit.py ----------------------------------------------------
    "En attente de la validation des exercices ciblés par l'enseignant.":
        "Waiting for the teacher to approve the check exercises.",
    "En attente des réponses de l'élève aux exercices ciblés.": "Waiting for the learner's answers to the check exercises.",
    "Serveur {server} indisponible : {error}": "Server {server} unavailable: {error}",

    # -- reasoning.py --------------------------------------------------------------
    "mêmes exercices, texte lu à l'élève": "same exercises, text read to the learner",
    "mêmes exercices, en invitant l'élève à prendre son temps": "same exercises, inviting the learner to take their time",
    "contraste en {skill}": "contrast in {skill}",
    "exercices ciblés seuls": "check exercises only",
    "{n} trimestres faibles consécutifs": "{n} consecutive weak terms",
    "{n} trimestres faibles sur les 6 derniers": "{n} weak terms out of the last 6",
    "{span} en {skill}, erreur dominante « {error} » ({share} des erreurs). Piste : {sens} (test : {test}). Une "
    "hypothèse, pas un constat : je la teste.":
        "{span} in {skill}, dominant error \"{error}\" ({share} of errors). Explanation: {sens} (test: {test}). A "
        "hypothesis, not a finding: I am testing it.",
    "Hypothèse déjà en cours de test ({skill}) : j'attends la validation de l'enseignant ou les réponses de l'élève.":
        "Hypothesis already being tested ({skill}): I am waiting for the teacher's approval or the learner's answers.",
    "Aucune difficulté durable non expliquée et non déjà suivie.":
        "No lasting difficulty that is unexplained and not already followed.",
    "Les exercices ciblés n'ont pas encore été réalisés.": "The check exercises have not been done yet.",
    "Exercices ciblés : {acc} de réussite, {same} erreur(s) du type attendu. L'hypothèse est confirmée.":
        "Check exercises: {acc} success, {same} error(s) of the expected type. The hypothesis is confirmed.",
    "{base} Nouvelle piste testée : {exp}.": "{base} New explanation tested: {exp}.",
    "Le contraste a échoué aussi ({c}/{n}) : la piste « {old} » ne suffit pas. Avant de vous solliciter, je teste une "
    "autre explication : {new}.":
        "The contrast failed too ({c}/{n}): the explanation \"{old}\" is not enough. Before asking you, I am testing "
        "another explanation: {new}.",
    "J'ai testé plusieurs explications ({tried}) : aucune ne localise la difficulté. ":
        "I tested several explanations ({tried}): none of them pins down the difficulty. ",
    ", puis ": ", then ",
    "{name} échoue aux exercices {of} lus seul ({correct}/{n}) et aussi quand le texte est lu à voix haute ({c}/{cn}) "
    ": la difficulté ne vient donc pas seulement de la lecture du texte. Je n'enregistre rien. Qu'observez-vous en "
    "classe ?":
        "{name} fails the exercises {of} when reading alone ({correct}/{n}) and also when the text is read aloud "
        "({c}/{cn}): so the difficulty does not come only from reading the text. I am not recording anything. What do "
        "you see in class?",
    "{name} échoue aux exercices {of} ({correct}/{n}) et aussi quand on l'invite à prendre son temps ({c}/{cn}) : la "
    "difficulté ne vient donc pas seulement du rythme. Je n'enregistre rien. Qu'observez-vous en classe ?":
        "{name} fails the exercises {of} ({correct}/{n}) and also when invited to take time ({c}/{cn}): so the "
        "difficulty does not come only from pace. I am not recording anything. What do you see in class?",
    "la difficulté semble plus large que prévu": "the difficulty seems broader than expected",
    "{name} échoue aux exercices ciblés ({correct}/{n}) mais aussi aux exercices de contraste en {skill} ({c}/{cn}) : "
    "{why}. Je n'enregistre rien. Qu'observez-vous en classe ?":
        "{name} fails the check exercises ({correct}/{n}) but also the contrast exercises in {skill} ({c}/{cn}): {why}. "
        "I am not recording anything. What do you see in class?",
    "Le test par contraste ne localise pas la difficulté et je n'ai plus d'autre piste à tester : je demande à "
    "l'enseignant au lieu de conclure.":
        "The contrast test does not pin down the difficulty and I have no other explanation left to test: I am asking "
        "the teacher instead of concluding.",
    "Exercices ciblés réussis à {acc} : l'hypothèse est écartée.":
        "Check exercises passed at {acc}: the hypothesis is ruled out.",
    "Résultat ambigu ({acc}) : nouveau tour d'exercices.": "Ambiguous result ({acc}): new round of exercises.",
    "Après {rounds} tours d'exercices ciblés, les résultats restent ambigus ({acc} de réussite). Qu'observez-vous en "
    "classe ?":
        "After {rounds} rounds of check exercises, the results remain ambiguous ({acc} success). What do you see in "
        "class?",
    "Résultats ambigus après le nombre maximal de tours : je rends la main à l'enseignant.":
        "Ambiguous results after the maximum number of rounds: I am handing over to the teacher.",
    "action inconnue « {action} »": "unknown action \"{action}\"",
    "terme interdit « {label} » dans {field}": "forbidden term \"{label}\" in {field}",
    "piste « {option} » inconnue : aucune tendance durable calculée ne la justifie":
        "unknown explanation \"{option}\": no computed lasting trend supports it",
    "observations citées introuvables : {ids}": "cited observations not found: {ids}",
    "le modèle s'écarte du choix des règles sans citer d'observation qui le justifie":
        "the model departs from the rules' choice without citing an observation to justify it",
    "les exercices ciblés sont nets ({acc} de réussite, {same} erreur(s) du type attendu) : la décision doit être "
    "« {expected} », pas « {action} »":
        "the check exercises are clear ({acc} success, {same} error(s) of the expected type): the decision must be "
        "\"{expected}\", not \"{action}\"",
    "constat sans confirmation par des exercices ciblés réalisés": "finding without confirmation by completed check exercises",
    "hypothèse écartée sans résultats ciblés suffisants": "hypothesis ruled out without enough check results",
    "une tendance durable a été calculée mais ignorée": "a lasting trend was computed but ignored",
    "le constat annonce {claimed} trimestres, les calculs en trouvent {real}":
        "the finding claims {claimed} terms, the calculations find {real}",
    " Problèmes : {problems}": " Problems: {problems}",
    " Vérification : cohérent avec les calculs.": " Check: consistent with the calculations.",
    "Raisonnement (règles) et auto-vérification": "Reasoning (rules) and self-check",
    "Raisonnement": "Reasoning",
    "Sortie du modèle invalide : décision par les règles. ": "Invalid model output: decision by the rules. ",
    "Auto-vérification : décision du modèle rejetée": "Self-check: model decision rejected",
    ". Décision retenue : {action} — {rationale}": ". Decision kept: {action} — {rationale}",
    # Repères lus par l'interface pour découper l'hypothèse (web/__init__.py).
    "Lecture du modèle :": "Model's reading:",
    "; erreur la plus fréquente :": "; most frequent error:",
    " (Les règles, qui ne lisent que les chiffres, auraient choisi la piste « {option} ».)":
        " (The rules, which only read the figures, would have chosen the explanation \"{option}\".)",
    "Raisonnement (modèle local) et auto-vérification réussie": "Reasoning (local model) and self-check passed",
    "sur {n} trimestres consécutifs ({first} → {last})": "over {n} consecutive terms ({first} → {last})",
    "sur {n} des 6 derniers trimestres": "in {n} of the last 6 terms",
    "{name} réussit {acc} des exercices {of} {span} ": "{name} gets {acc} of the exercises {of} right {span}",
    " Piste testée : {fast} des réponses sont données en moins de 5 secondes ; la difficulté viendrait d'un rythme "
    "trop rapide. On compare les mêmes exercices avec et sans invitation à prendre son temps.":
        " Explanation tested: {fast} of answers are given in under 5 seconds; the difficulty may come from working too "
        "fast. We compare the same exercises with and without an invitation to take time.",
    " Piste testée : la difficulté viendrait de la lecture du texte écrit":
        " Explanation tested: the difficulty may come from reading the written text",
    " (avec la lecture à voix haute, {pts:+d} points de réussite)": " (with read-aloud, {pts:+d} points of success)",
    " ; on compare les mêmes exercices lus seul et écoutés.":
        "; we compare the same exercises read alone and listened to.",
    "depuis {n} trimestres consécutifs": "for {n} consecutive terms",
    "{name} réussit les exercices {of} quand on l'invite à prendre son temps ({c}/{cn}) mais échoue en répondant vite "
    "({correct}/{n}) : la difficulté vient plutôt du rythme que de la compétence elle-même":
        "{name} passes the exercises {of} when invited to take time ({c}/{cn}) but fails when answering quickly "
        "({correct}/{n}): the difficulty comes from pace rather than from the skill itself",
    "{name} réussit les exercices {of} quand le texte lui est lu ({c}/{cn}) mais échoue quand il le lit seul "
    "({correct}/{n}) : la difficulté vient plutôt de la lecture du texte que de la compétence elle-même":
        "{name} passes the exercises {of} when the text is read aloud ({c}/{cn}) but fails when reading alone "
        "({correct}/{n}): the difficulty comes from reading the text rather than from the skill itself",
    "{name} réussit les exercices {contrast_of} ({c}/{cn}) mais échoue en {skill} ({correct}/{n} aux exercices ciblés)":
        "{name} passes the exercises {contrast_of} ({c}/{cn}) but fails in {skill} ({correct}/{n} on the check "
        "exercises)",
    "{name} échoue en {skill} ({correct}/{n} aux exercices ciblés)":
        "{name} fails in {skill} ({correct}/{n} on the check exercises)",
    "{lead}, une difficulté présente {span} ({acc} de réussite sur cette période). Erreur la plus fréquente : {error}.":
        "{lead}, a difficulty present {span} ({acc} success over this period). Most frequent error: {error}.",
    "{name} réussit {acc} des exercices {of} depuis {n} trimestres ({first} → {last}).":
        "{name} has got {acc} of the exercises {of} right for {n} terms ({first} → {last}).",
    "Bonjour, voici quelques nouvelles du travail de {name} ce trimestre.":
        "Hello, here is some news about {name}'s work this term.",
    "Ce qui marche bien : ": "What is going well: ",
    "Ce qui marche bien : {name} réussit bien en {skill}.": "What is going well: {name} does well in {skill}.",
    "Ce qui est encore difficile : {name} a besoin de plus d'entraînement en {skills}. En classe, nous lui proposons "
    "des exercices adaptés et nous suivons ses progrès.":
        "What is still difficult: {name} needs more practice in {skills}. In class, we offer {name} suitable "
        "exercises and follow the progress made.",
    "À la maison, vous pouvez demander à {name} de vous expliquer à voix haute comment résoudre un exercice : c'est "
    "un très bon entraînement.":
        "At home, you can ask {name} to explain out loud how to solve an exercise: it is very good practice.",
    "{name} progresse régulièrement. Continuez à l'encourager !": "{name} is making steady progress. Keep encouraging {name}!",
    "N'hésitez pas à venir en parler avec l'enseignant·e.": "Feel free to come and talk about it with the teacher.",

    # -- live.py -------------------------------------------------------------------
    "<{n} lignes de code>": "<{n} lines of code>",
    "<code Python>": "<Python code>",
    "l’agent réfléchit…": "the agent is thinking…",
    "élève {id}": "learner {id}",
    "classe": "class",
    "Suivre l'agent XamKids en direct.": "Follow the XamKids agent live.",
    "afficher les sorties de chaque outil": "show the output of each tool",
    "identifiant d'un élève à suivre seul": "id of a single learner to follow",
    "réafficher les N derniers appels avant de suivre": "show the last N calls again before following",
    "En attente d'activité. Ctrl+C pour quitter.": "Waiting for activity. Ctrl+C to quit.",
    "Fin du suivi.": "Stopped following.",

    # -- records/seed.py -----------------------------------------------------------
    "Mme Ndiaye (mère)": "Mrs Ndiaye (mother)",
    "M. Diallo (père)": "Mr Diallo (father)",
    "Mme Sow (mère)": "Mrs Sow (mother)",
    "M. Ba (oncle)": "Mr Ba (uncle)",
    "Mme Fall (grand-mère)": "Mrs Fall (grandmother)",
    "M. Mbaye (père)": "Mr Mbaye (father)",
    "Mme Gueye (mère)": "Mrs Gueye (mother)",
    "M. Diouf (père)": "Mr Diouf (father)",
    "Mme Thiam (mère)": "Mrs Thiam (mother)",
    "M. Sy (père)": "Mr Sy (father)",
    "Base créée : {learners} élèves, {n} réponses sur {years} années scolaires.":
        "Database created: {learners} learners, {n} answers over {years} school years.",
}
