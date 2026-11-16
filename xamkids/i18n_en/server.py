"""Traductions anglaises : serveur MCP (refus, notes, ressources), phrases pour l'enseignant (wording.py) et
dossiers de l'élève (records/decisions.py, sessions.py, db.py, audit.py)."""

EN = {
    # -- mcp_server.py ----------------------------------------------------------------------
    "Accès au dossier longitudinal des élèves. ": "Access to learners' longitudinal records. ",
    "Facultatif : identifiant de l'exécution de l'agent appelant, utilisé uniquement pour relier cet appel au "
    "journal d'audit.":
        "Optional: identifier of the calling agent's run, used only to link this call to the audit log.",
    "Élève {learner_id} inconnu.": "Unknown learner {learner_id}.",
    "Phrase pour l'enseignant refusée : terme diagnostique ou étiquette interdit (« {label} »).":
        "Sentence for the teacher refused: forbidden diagnostic term or label (\"{label}\").",
    "Compétence inconnue : {skill}.": "Unknown skill: {skill}.",
    "Hypothèse refusée : terme diagnostique ou étiquette interdit (« {label} »). Décrire l'erreur observable.":
        "Hypothesis refused: forbidden diagnostic term or label (\"{label}\"). Describe the observable error.",
    "Exercice de banque inconnu : {ex_id}.": "Unknown bank exercise: {ex_id}.",
    "Exercice incomplet, champs manquants : {missing}.": "Incomplete exercise, missing fields: {missing}.",
    "La bonne réponse doit figurer parmi au moins trois choix.":
        "The correct answer must be one of at least three choices.",
    "Exercice refusé : choix en double.": "Exercise refused: duplicate choices.",
    "Exercice refusé : chaque mauvais choix doit correspondre à un type d'erreur ({unmapped}).":
        "Exercise refused: each wrong choice must map to an error type ({unmapped}).",
    "Exercice refusé : l'énoncé parle de l'élève au lieu de s'adresser à lui.":
        "Exercise refused: the question talks about the learner instead of speaking to them.",
    "Types d'erreur hors taxonomie : {bad}.": "Error types not in the taxonomy: {bad}.",
    "Énoncé refusé (« {label} »).": "Question refused (\"{label}\").",
    "Contraste à l'écoute impossible en {skill} : il n'y a pas de texte à lire à l'élève.":
        "Listening contrast not possible for {skill}: there is no text to read to the learner.",
    "Exercice de contraste invalide : {ex_id} (il doit venir de la banque, d'une autre compétence).":
        "Invalid contrast exercise: {ex_id} (it must come from the bank, from another skill).",
    "Exercice de contraste invalide : {ex_id} (même compétence, différent des exercices cibles).":
        "Invalid contrast exercise: {ex_id} (same skill, different from the target exercises).",
    "Il faut 3 à 6 exercices ciblés dont au moins 2 cibles (reçu {targets} + {contrasts}).":
        "3 to 6 check exercises are needed, including at least 2 targets (received {targets} + {contrasts}).",
    "Exercices en attente : seul l'enseignant peut les valider depuis l'interface.":
        "Exercises pending: only the teacher can approve them, from the interface.",
    "Constat refusé : aucune source citée. Chaque constat doit citer les réponses, observations, exercices ciblés "
    "ou relevés de présence dont il provient.":
        "Finding refused: no source cited. Each finding must cite the answers, observations, check exercises or "
        "attendance records it comes from.",
    "Source mal formée : « {ref} » (attendu answer:ID, observation:ID, attendance:ID, report:ID ou exercise:ID).":
        "Malformed source: \"{ref}\" (expected answer:ID, observation:ID, attendance:ID, report:ID or exercise:ID).",
    "Source introuvable ou appartenant à un autre élève : {ref}.":
        "Source not found or belonging to another learner: {ref}.",
    "Constat refusé : un profil ne compare jamais l'élève à ses camarades (retirer la moyenne de classe).":
        "Finding refused: a profile never compares the learner with classmates (remove the class average).",
    "Constat refusé : terme diagnostique ou étiquette interdit (« {label} »). Décrire ce que l'élève réussit et "
    "ce qu'il ne réussit pas encore.":
        "Finding refused: forbidden diagnostic term or label (\"{label}\"). Describe what the learner can do and "
        "what the learner cannot do yet.",
    "Phrase pour l'enseignant refusée ({reason}) : envoyer la phrase fixe à la place.":
        "Sentence for the teacher refused ({reason}): send the fixed sentence instead.",
    "Difficulté non enregistrée : elle doit être confirmée par des exercices ciblés, validés par l'enseignant et "
    "réalisés par l'élève (citer exercise:ID).":
        "Difficulty not recorded: it must be confirmed by check exercises, approved by the teacher and completed "
        "by the learner (cite exercise:ID).",
    "Difficulté non enregistrée : citer aussi les réponses ou observations des trimestres concernés.":
        "Difficulty not recorded: also cite the answers or observations from the terms concerned.",
    "Classe {class_id} inconnue.": "Unknown class {class_id}.",
    "Indiquer l'élève (learner_id) ou la classe (class_id) concernée.":
        "Specify the learner (learner_id) or the class (class_id) concerned.",
    "Message refusé : terme diagnostique ou étiquette (« {label} »).":
        "Message refused: diagnostic term or label (\"{label}\").",
    "Motif refusé : terme diagnostique ou étiquette (« {label} »).":
        "Reason refused: diagnostic term or label (\"{label}\").",
    "après {n} séances ou au {year} T{term}": "after {n} sessions or at {year} T{term}",
    "Résumé refusé : terme diagnostique ou étiquette (« {label} »).":
        "Summary refused: diagnostic term or label (\"{label}\").",
    "séance {session_id}": "session {session_id}",
    "tout l'historique": "whole history",
    "Taxonomie des erreurs": "Error taxonomy",
    "Règles de l'agent": "Agent rules",
    "Banque d'exercices": "Exercise bank",
    "niveau ou compétence inconnu": "unknown level or skill",
    "Liste de classe": "Class list",
    "Situation d'un élève": "Learner situation",
    "élève inconnu": "unknown learner",

    # -- wording.py : raisons de refus d'une phrase -----------------------------------------
    "phrase vide": "empty sentence",
    "compétence absente ou mal écrite (« {must} » attendu)": "skill missing or misspelt (\"{must}\" expected)",
    "phrase trop longue": "sentence too long",
    "prénom absent": "first name missing",
    "étiquette interdite (« {label} »)": "forbidden label (\"{label}\")",
    "comparaison avec la classe": "comparison with the class",
    "s'adresse à l'élève au lieu de l'enseignant": "speaks to the learner instead of the teacher",
    "change le but (vérifier, pas entraîner)": "changes the purpose (check, not practise)",
    "chiffre absent des faits ({numbers})": "number not in the facts ({numbers})",
    "chiffre détourné de son sens (« {unit} »)": "number used with another meaning (\"{unit}\")",
    "modèle indisponible": "model unavailable",
    "la proposition doit commencer par « Je propose » ou « Pour vérifier »":
        "the proposal must start with \"I propose\" or \"To check\"",
    "la proposition doit dire qu'il s'agit de vérifier": "the proposal must say that the purpose is to check",

    # -- records : textes vus par l'élève ou l'enseignant ----------------------------------
    "Depuis le {level}": "Since {level}",
    "Depuis le début": "Since you started",
    "{since}, tu as fait {total} exercice{s}.": "{since}, you have done {total} exercise{s}.",
    " Ce trimestre, tu as trouvé {n} réponse{s} du premier coup !": " This term, you got {n} answer{s} right first time!",
    "Élève": "Learner",
    "ressenti : « {feeling} »": "feeling: \"{feeling}\"",
    "a préféré : ": "liked best: ",
    "Après la séance {n}, ": "After session {n}, ",
    "Centres d'intérêt déclarés par l'élève : {labels}.": "Interests chosen by the learner: {labels}.",
    "Lecture confirmée : {n} lignes importées.": "Reading confirmed: {n} rows imported.",
    "Livret scolaire ({level})": "Report card ({level})",
    "élève {learner_id}": "learner {learner_id}",
    "…[tronqué]": "…[truncated]",
}
