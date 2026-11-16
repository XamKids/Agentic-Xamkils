"""Connaissances pédagogiques partagées : taxonomie des erreurs, banque d'exercices, règles de l'agent.

Ces contenus sont exposés à l'agent comme ressources MCP (lecture seule) par le serveur xamkids-profile.
Français par défaut ; anglais si XAMKIDS_LANG=en (voir i18n.py). Les clés (compétences, types d'erreur,
pistes, identifiants d'exercices) ne changent jamais : seules les valeurs lisibles sont traduites.
"""
from __future__ import annotations

import random
import re

from .i18n import LANG, pick

LEVELS = ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]  # cycle élémentaire sénégalais

SKILLS = pick({
    "calcul": {"subject": "maths", "label": "Calcul (opérations posées et mentales)"},
    "numeration": {"subject": "maths", "label": "Numération (valeur des chiffres)"},
    "probleme_simple": {"subject": "maths", "label": "Problèmes à une étape"},
    "probleme_multi_etapes": {"subject": "maths", "label": "Problèmes à plusieurs étapes"},
    "decodage": {"subject": "francais", "label": "Lecture de mots (décodage)"},
    "comprehension": {"subject": "francais", "label": "Compréhension de texte"},
    "grammaire": {"subject": "francais", "label": "Orthographe grammaticale"},
}, {
    "calcul": {"subject": "maths", "label": "Arithmetic (written and mental calculation)"},
    "numeration": {"subject": "maths", "label": "Place value (value of digits)"},
    "probleme_simple": {"subject": "maths", "label": "One-step word problems"},
    "probleme_multi_etapes": {"subject": "maths", "label": "Multi-step word problems"},
    "decodage": {"subject": "francais", "label": "Word reading (decoding)"},
    "comprehension": {"subject": "francais", "label": "Reading comprehension"},
    "grammaire": {"subject": "francais", "label": "Grammar (agreement and homophones)"},
})

# Domaines suivis hors exercices (constats « à surveiller » uniquement).
OTHER_DOMAINS = {"presence": {"subject": "vie_scolaire", "label": pick("Présence en classe", "Class attendance")}}


# Noms courts affichés dans l'interface (les textes de l'agent gardent le nom complet).
SHORT_LABEL = pick({
    "calcul": "Calcul", "numeration": "Numération", "probleme_simple": "Problèmes simples",
    "probleme_multi_etapes": "Problèmes à étapes", "decodage": "Lecture", "comprehension": "Compréhension de texte",
    "grammaire": "Orthographe", "presence": "Présence",
}, {
    "calcul": "Arithmetic", "numeration": "Place value", "probleme_simple": "One-step problems",
    "probleme_multi_etapes": "Multi-step problems", "decodage": "Reading", "comprehension": "Reading comprehension",
    "grammaire": "Grammar", "presence": "Attendance",
})


def short_label(key: str) -> str:
    return SHORT_LABEL.get(key) or domain_label(key)


def domain_label(key: str) -> str:
    return (SKILLS.get(key) or OTHER_DOMAINS.get(key) or {"label": key})["label"]


# Test par contraste : pour une compétence en difficulté, une compétence voisine qui isole la cause.
# Si l'élève réussit le contraste et échoue à la cible, la difficulté est bien localisée ;
# s'il échoue aux deux, elle est peut-être ailleurs (explication donnée à l'enseignant).
CONTRAST = pick({
    "probleme_multi_etapes": ("probleme_simple", "les problèmes courts sont aussi échoués : la difficulté vient peut-être "
                              "de la lecture des énoncés plutôt que de l'enchaînement des étapes"),
    "probleme_simple": ("calcul", "les calculs seuls sont aussi échoués : la difficulté vient peut-être du calcul "
                        "plutôt que de la compréhension du problème"),
    "calcul": ("numeration", "la valeur des chiffres est aussi mal maîtrisée : la difficulté vient peut-être de la "
               "numération plutôt que des opérations"),
    "numeration": ("calcul", "les calculs sont aussi échoués : la difficulté semble plus large que la valeur des chiffres"),
    "comprehension": ("decodage", "la lecture de mots isolés est aussi difficile : la compréhension dépend peut-être "
                      "d'abord du décodage"),
    "grammaire": ("decodage", "la lecture de mots isolés est aussi difficile : l'orthographe dépend peut-être "
                  "d'abord du décodage"),
}, {
    "probleme_multi_etapes": ("probleme_simple", "short problems are also failed: the difficulty may come from "
                              "reading the problem rather than from chaining the steps"),
    "probleme_simple": ("calcul", "calculations on their own are also failed: the difficulty may come from calculation "
                        "rather than from understanding the problem"),
    "calcul": ("numeration", "place value is also shaky: the difficulty may come from place value "
               "rather than from the operations"),
    "numeration": ("calcul", "calculations are also failed: the difficulty seems broader than place value"),
    "comprehension": ("decodage", "reading single words is also difficult: comprehension may depend "
                      "on decoding first"),
    "grammaire": ("decodage", "reading single words is also difficult: spelling may depend "
                  "on decoding first"),
})

# Pistes d'explication qu'un agent peut envisager pour une difficulté durable (catalogue fermé).
# Chaque piste dit quel test la départage :
# - « locale » : la difficulté est dans la compétence elle-même ; contraste = compétence voisine (CONTRAST) ;
# - « lecture » : la difficulté vient de la lecture du texte écrit ; contraste = mêmes exercices, mais le texte
#   est lu à l'élève (exercices « écoutés »). Réussir à l'écoute et échouer seul localise la difficulté dans la lecture ;
# - « rythme » : l'élève répond trop vite pour avoir lu ; contraste = mêmes exercices, mais l'élève est invité à
#   relire et les réponses n'apparaissent qu'après quelques secondes. Envisagée seulement si les réponses trop
#   rapides sont fréquentes (calculé).
EXPLANATIONS = pick({
    "locale": "la difficulté porte sur la compétence elle-même",
    "lecture": "la difficulté vient de la lecture du texte écrit, pas de la compétence elle-même",
    "rythme": "l'élève répond trop vite, avant d'avoir lu ou réfléchi, pas un manque dans la compétence",
}, {
    "locale": "the difficulty lies in the skill itself",
    "lecture": "the difficulty comes from reading the written text, not from the skill itself",
    "rythme": "the pupil answers too quickly, before reading or thinking, not a gap in the skill",
})
LISTENABLE = {"comprehension", "probleme_simple", "probleme_multi_etapes"}  # textes qu'on peut lire à l'élève


def explanations_for(skill: str, fast_rate: float = 0.0, fast_threshold: float = 1.0) -> list[str]:
    return (["locale"] + (["lecture"] if skill in LISTENABLE else [])
            + (["rythme"] if fast_rate >= fast_threshold else []))


ERROR_TAXONOMY = pick({
    "fait_numerique": "Résultat d'opération faux (table, fait numérique non maîtrisé)",
    "retenue": "Oubli ou mauvaise gestion de la retenue",
    "valeur_position": "Confusion sur la valeur d'un chiffre selon sa position (unités, dizaines, centaines…)",
    "choix_operation": "Mauvaise opération choisie pour résoudre le problème",
    "etape_incomplete": "S'arrête après une étape intermédiaire d'un problème à plusieurs étapes",
    "inversion_lettres": "Inversion de lettres visuellement proches (b/d, p/q, on/no)",
    "confusion_sons": "Confusion de sons proches (f/v, ch/j, t/d, s/z)",
    "comprehension_litterale": "Information écrite explicitement dans le texte non retrouvée",
    "inference": "Information à déduire du texte non comprise",
    "accord": "Accord sujet-verbe ou nom-adjectif non respecté",
    "homophone": "Confusion d'homophones (a/à, et/est, son/sont…)",
    "reponse_impulsive": "Réponse fausse donnée très vite (moins de 4 s), sans lecture complète",
    "sans_reponse": "Question laissée sans réponse",
    "non_classee": "Erreur que la taxonomie ne permet pas de classer",
}, {
    "fait_numerique": "Wrong calculation result (times tables or number facts not mastered)",
    "retenue": "Forgotten or mishandled carrying",
    "valeur_position": "Confusion about a digit's value depending on its place (ones, tens, hundreds…)",
    "choix_operation": "Wrong operation chosen to solve the problem",
    "etape_incomplete": "Stops after an intermediate step of a multi-step problem",
    "inversion_lettres": "Reversal of visually similar letters or letter order (b/d, p/q, on/no)",
    "confusion_sons": "Confusion of similar sounds (f/v, t/d, s/z, ch/j)",
    "comprehension_litterale": "Information written explicitly in the text not found",
    "inference": "Information that must be inferred from the text not understood",
    "accord": "Subject–verb or number agreement not respected",
    "homophone": "Homophone confusion (there/their/they're, its/it's, to/too/two…)",
    "reponse_impulsive": "Wrong answer given very quickly (under 4 s), without reading it all",
    "sans_reponse": "Question left unanswered",
    "non_classee": "Error the taxonomy cannot classify",
})

# Règles non négociables, rappelées à l'agent et appliquées par le serveur MCP.
AGENT_RULES = pick("""\
1. Tu décris des difficultés observables d'apprentissage, jamais un trouble : aucun diagnostic
   (dyslexie, dyscalculie, TDAH, troubles de l'attention, autisme, dyspraxie, retard…) et aucune étiquette sur l'enfant.
2. Chaque constat enregistré dans le profil cite ses sources : identifiants des réponses, observations,
   exercices ciblés ou relevés de présence dont il provient. Sans source, pas de constat.
3. Une seule séance ne suffit jamais. Une difficulté n'est retenue que si elle dure dans le temps
   (au moins deux trimestres) et qu'elle est confirmée par des exercices ciblés validés par l'enseignant.
4. Un trimestre marqué par de fortes absences s'interprète avec prudence : une mauvaise période n'est pas une tendance.
5. Si un document est illisible ou si des données se contredisent, tu poses la question à l'enseignant au lieu de deviner.
6. Tu ne contactes jamais une famille. Les résumés pour les familles restent en attente jusqu'à validation par l'enseignant.
7. Les exercices ciblés que tu proposes restent en attente : seul un enseignant peut les rendre visibles aux élèves.
""", """\
1. You describe observable learning difficulties, never a disorder: no diagnosis
   (dyslexia, dyscalculia, ADHD, attention disorders, autism, dyspraxia, developmental delay…) and no label on the child.
2. Every finding recorded in the profile cites its sources: the ids of the answers, observations,
   targeted exercises or attendance records it comes from. No source, no finding.
3. A single session is never enough. A difficulty is only retained if it lasts over time
   (at least two terms) and is confirmed by targeted exercises approved by the teacher.
4. A term marked by many absences must be interpreted with caution: a bad period is not a trend.
5. If a document is unreadable or if data contradict each other, you ask the teacher instead of guessing.
6. You never contact a family. Summaries for families stay pending until the teacher approves them.
7. The targeted exercises you propose stay pending: only a teacher can make them visible to pupils.
""")

# Étiquettes interdites, en français et en anglais quelle que soit la langue de la plateforme.
# « trouble » n'est pas refusé dans les tournures anglaises courantes (« has trouble with/reading… »),
# qui décrivent une difficulté et non un diagnostic.
FORBIDDEN_LABELS = re.compile(
    r"dyslex|dyscalcul|dysorthograph|dyspraxi|dysphas|tdah|adhd|hyperacti|"
    r"trouble(?!s?\s+(?:with|in|at|to|for|on|when|reading|writing|spelling|counting|doing|getting|understanding|"
    r"focusing|remembering|following|finding|keeping|staying|making|solving|working)\b)|"
    r"autis|tsa\b|d[ée]ficit|retard mental|handicap|diagnosti|paresseu|lent d'esprit|attardé|attarde|bête|"
    r"dysgraph|(?-i:\bADD\b)|(?-i:\bASD\b)|disorder|disabilit|diagnos(?:is|es|ed|e)\b|retarded|"
    r"slow learner|slow[- ]witted|\blaz(?:y|iness)\b|stupid|\bdumb\b|on the spectrum|neurodiver",
    re.IGNORECASE,
)


def find_forbidden_label(text: str) -> str | None:
    m = FORBIDDEN_LABELS.search(text or "")
    return m.group(0) if m else None


HINTS = pick({
    "calcul": "Pose l'opération en colonnes et commence par les unités.",
    "numeration": "Écris le nombre dans un tableau : centaines, dizaines, unités.",
    "probleme_simple": "Que cherche-t-on ? Est-ce que la quantité augmente ou diminue ?",
    "probleme_multi_etapes": "Découpe le problème : que dois-tu calculer d'abord ? Et ensuite ?",
    "decodage": "Lis chaque son du mot lentement, lettre par lettre.",
    "comprehension": "Relis la phrase du texte qui parle de la question.",
    "grammaire": "Qui fait l'action ? Est-ce un seul ou plusieurs ?",
}, {
    "calcul": "Write the sum in columns and start with the ones.",
    "numeration": "Write the number in a table: hundreds, tens, ones.",
    "probleme_simple": "What are we looking for? Does the amount go up or down?",
    "probleme_multi_etapes": "Break the problem into steps: what must you work out first? And then?",
    "decodage": "Say each sound of the word slowly, letter by letter.",
    "comprehension": "Read again the sentence in the text that talks about the question.",
    "grammaire": "Who is doing the action? Is it one person or thing, or more than one?",
})

# ---------------------------------------------------------------------------
# Banque d'exercices (générée de façon déterministe)
# ---------------------------------------------------------------------------
# La version anglaise suit exactement la même suite de tirages aléatoires que la version française (mêmes
# listes de même longueur, même nombre de choix par exercice) : identifiants, niveaux, nombres et réponses
# des exercices de maths sont identiques dans les deux langues.

_NAMES = ["Awa", "Modou", "Khady", "Ousmane", "Ndèye", "Lamine", "Mariama", "Pape", "Coumba", "Babacar"]
_ITEMS = pick([("cahiers", 250), ("stylos", 150), ("mangues", 100), ("pains", 175), ("beignets", 50), ("règles", 200)],
              [("notebooks", 250), ("pens", 150), ("mangoes", 100), ("loaves of bread", 175), ("doughnuts", 50),
               ("rulers", 200)])
_SINGULAR_EN = {"notebooks": "notebook", "pens": "pen", "mangoes": "mango", "loaves of bread": "loaf of bread",
                "doughnuts": "doughnut", "rulers": "ruler"}
_LEVEL_SCALE = {"CI": 1, "CP": 1, "CE1": 1, "CE2": 2, "CM1": 4, "CM2": 8}
_EARLY = ("CI", "CP")  # petites classes : petits nombres, histoires du quotidien, pas de prix

_WORDS = [  # (mot, indice de sens) : l'élève doit reconnaître l'orthographe sans voir le mot écrit
    ("bol", "On y verse le lait du petit-déjeuner."), ("dame", "Une femme adulte."),
    ("banane", "Un fruit jaune et allongé."), ("bateau", "Il flotte sur la mer."),
    ("poule", "Elle pond des œufs."), ("pomme", "Un fruit rond, rouge ou vert."),
    ("dent", "On la brosse matin et soir."), ("robe", "Un vêtement pour les filles et les femmes."),
    ("doigt", "Nous en avons cinq à chaque main."), ("pied", "On met la chaussure dessus."),
    ("cadeau", "On l'offre pour un anniversaire."), ("bidon", "On y met de l'eau ou de l'huile."),
    ("dindon", "Un gros oiseau de la ferme."), ("boubou", "Un grand vêtement traditionnel."),
    ("tapis", "On le pose par terre pour s'asseoir."), ("bonbon", "Une petite friandise sucrée."),
    ("pédale", "On appuie dessus pour avancer à vélo."), ("pantalon", "On l'enfile sur les jambes."),
    ("biberon", "Le bébé boit son lait avec."), ("bougie", "On l'allume quand il n'y a plus de courant."),
]
_SWAPS_VISUAL = {"b": "d", "d": "b", "p": "q", "q": "p"}
_SWAPS_SOUND = [("f", "v"), ("v", "f"), ("ch", "j"), ("j", "ch"), ("t", "d"), ("s", "z"), ("z", "s")]

# Anglais : orthographes fautives écrites une à une (les permutations automatiques donnent en anglais des formes
# peu plausibles). Même nombre de choix que le mot français de même rang : 2 inversions (b/d, p/q ou ordre des
# lettres), plus une confusion de sons (f/v, t/d, s/z) aux rangs 3, 6, 8, 14 et 17.
_WORDS_EN = [  # (mot, indice de sens, {orthographe fautive: type d'erreur})
    ("bird", "It has feathers and it can fly.", {"dird": "inversion_lettres", "birb": "inversion_lettres"}),
    ("bread", "The baker makes it every morning.", {"dreab": "inversion_lettres", "breab": "inversion_lettres"}),
    ("baby", "A very young child.", {"daby": "inversion_lettres", "bady": "inversion_lettres"}),
    ("table", "We put our plates on it to eat.",
     {"tadle": "inversion_lettres", "talbe": "inversion_lettres", "dable": "confusion_sons"}),
    ("queen", "The wife of a king.", {"pueen": "inversion_lettres", "qeuen": "inversion_lettres"}),
    ("drum", "A musical instrument you hit with your hands.", {"brum": "inversion_lettres", "durm": "inversion_lettres"}),
    ("dress", "A piece of clothing for girls and women.",
     {"bress": "inversion_lettres", "derss": "inversion_lettres", "drezz": "confusion_sons"}),
    ("bed", "You sleep in it at night.", {"deb": "inversion_lettres", "beb": "inversion_lettres"}),
    ("bus", "Many people ride in it to go to town.",
     {"dus": "inversion_lettres", "bsu": "inversion_lettres", "buz": "confusion_sons"}),
    ("board", "The teacher writes on it with chalk.", {"doard": "inversion_lettres", "boarb": "inversion_lettres"}),
    ("bowl", "You eat your rice from it.", {"dowl": "inversion_lettres", "bwol": "inversion_lettres"}),
    ("ball", "Children kick it in the schoolyard.", {"dall": "inversion_lettres", "blal": "inversion_lettres"}),
    ("drop", "A tiny bit of water.", {"brop": "inversion_lettres", "droq": "inversion_lettres"}),
    ("pupil", "A child who goes to school.", {"qupil": "inversion_lettres", "puqil": "inversion_lettres"}),
    ("bottle", "You fill it with water.",
     {"dottle": "inversion_lettres", "botlte": "inversion_lettres", "boddle": "confusion_sons"}),
    ("bench", "You sit on it in the yard.", {"dench": "inversion_lettres", "bnech": "inversion_lettres"}),
    ("paddle", "You push the water with it to move a pirogue.",
     {"qaddle": "inversion_lettres", "pabble": "inversion_lettres"}),
    ("basket", "You carry fruit in it on your head.",
     {"dasket": "inversion_lettres", "bakset": "inversion_lettres", "bazket": "confusion_sons"}),
    ("bucket", "You carry water from the well in it.", {"ducket": "inversion_lettres", "bukcet": "inversion_lettres"}),
    ("bridge", "You walk over it to cross the river.", {"dridge": "inversion_lettres", "bribge": "inversion_lettres"}),
]

_TEXTS = pick([
    ("Le marché de Tilène",
     "Samedi matin, Fatou accompagne sa grand-mère au marché de Tilène. Elles achètent des oignons, "
     "du poisson et trois mangues. Il fait très chaud, alors la grand-mère achète aussi un bissap bien frais. "
     "Sur le chemin du retour, Fatou porte le panier, car sa grand-mère a mal au dos.",
     [("Combien de mangues achètent-elles ?", "trois", ["deux", "cinq", "aucune"], "comprehension_litterale"),
      ("Pourquoi Fatou porte-t-elle le panier ?", "Pour aider sa grand-mère qui a mal au dos",
       ["Parce qu'il est léger", "Parce qu'elle veut manger les mangues", "Parce qu'il fait chaud"], "inference")]),
    ("La pirogue de Mamadou",
     "Mamadou est pêcheur à Kayar. Chaque nuit, il part en mer avec ses deux frères dans une grande pirogue bleue. "
     "Ce matin, le ciel est gris et le vent souffle fort. Mamadou regarde la mer longtemps, puis il range ses filets.",
     [("De quelle couleur est la pirogue ?", "bleue", ["rouge", "verte", "jaune"], "comprehension_litterale"),
      ("Pourquoi Mamadou range-t-il ses filets ?", "Parce qu'il ne partira pas en mer à cause du mauvais temps",
       ["Parce qu'il a déjà beaucoup de poissons", "Parce que ses frères sont malades", "Parce que la pirogue est cassée"],
       "inference")]),
    ("Le baobab de l'école",
     "Dans la cour de notre école, il y a un vieux baobab. À la récréation, les élèves s'assoient à son ombre. "
     "Le maître dit qu'il a plus de deux cents ans. Un jour, une branche est tombée pendant l'orage, "
     "mais personne n'était dans la cour.",
     [("Où les élèves s'assoient-ils à la récréation ?", "À l'ombre du baobab",
       ["Dans la classe", "Devant le portail", "Sous le préau"], "comprehension_litterale"),
      ("Pourquoi personne n'a été blessé par la branche ?", "Parce que les élèves n'étaient pas dans la cour pendant l'orage",
       ["Parce que la branche était petite", "Parce que le maître l'a attrapée", "Parce que le baobab est vieux"],
       "inference")]),
    ("La lettre d'Ibou",
     "Ibou vit à Ziguinchor. Il écrit une lettre à son cousin Alioune qui habite à Saint-Louis. "
     "Il lui raconte qu'il a gagné le concours de lecture de son école. Il termine sa lettre par : "
     "« Viens vite pendant les vacances, j'ai plein de livres à te prêter ! »",
     [("Où habite Alioune ?", "À Saint-Louis", ["À Ziguinchor", "À Dakar", "À Thiès"], "comprehension_litterale"),
      ("Qu'est-ce qu'Ibou aime sûrement ?", "La lecture", ["Le football", "La pêche", "La cuisine"], "inference")]),
    ("La saison des pluies",
     "En juillet, les premières pluies arrivent dans le village de Khady. Son père prépare le champ avec la houe. "
     "Khady l'aide à semer le mil. Quelques semaines plus tard, de petites pousses vertes sortent de la terre.",
     [("Que sèment Khady et son père ?", "Du mil", ["Du riz", "Des arachides", "Du maïs"], "comprehension_litterale"),
      ("Pourquoi le père attend-il juillet pour préparer le champ ?", "Parce que c'est le début des pluies",
       ["Parce que c'est les vacances", "Parce que Khady est libre", "Parce que la houe est neuve"], "inference")]),
    ("Le match du quartier",
     "Dimanche, l'équipe de la Médina joue contre celle de Grand-Yoff. À la mi-temps, la Médina perd deux buts à zéro. "
     "À la fin du match, les joueurs de la Médina dansent et chantent sur le terrain.",
     [("Quelles équipes jouent dimanche ?", "La Médina et Grand-Yoff",
       ["La Médina et Pikine", "Grand-Yoff et Rufisque", "Pikine et Rufisque"], "comprehension_litterale"),
      ("Que s'est-il sûrement passé en deuxième mi-temps ?", "La Médina a marqué plusieurs buts et a gagné",
       ["Grand-Yoff a marqué encore", "Le match a été arrêté", "Il a plu très fort"], "inference")]),
], [
    ("Tilène Market",
     "On Saturday morning, Fatou goes to Tilène market with her grandmother. They buy onions, "
     "fish and three mangoes. It is very hot, so her grandmother also buys a cold glass of bissap. "
     "On the way home, Fatou carries the basket, because her grandmother has a sore back.",
     [("How many mangoes do they buy?", "three", ["two", "five", "none"], "comprehension_litterale"),
      ("Why does Fatou carry the basket?", "To help her grandmother, who has a sore back",
       ["Because it is light", "Because she wants to eat the mangoes", "Because it is hot"], "inference")]),
    ("Mamadou's Pirogue",
     "Mamadou is a fisherman in Kayar. Every night, he goes out to sea with his two brothers in a big blue pirogue. "
     "This morning, the sky is grey and the wind is blowing hard. Mamadou looks at the sea for a long time, "
     "then he puts away his nets.",
     [("What colour is the pirogue?", "blue", ["red", "green", "yellow"], "comprehension_litterale"),
      ("Why does Mamadou put away his nets?", "Because he will not go to sea in such bad weather",
       ["Because he already has a lot of fish", "Because his brothers are ill", "Because the pirogue is broken"],
       "inference")]),
    ("The School Baobab",
     "In our schoolyard, there is an old baobab tree. At break time, the pupils sit in its shade. "
     "The teacher says it is more than two hundred years old. One day, a branch fell during a storm, "
     "but nobody was in the yard.",
     [("Where do the pupils sit at break time?", "In the shade of the baobab",
       ["In the classroom", "By the school gate", "Under the shelter"], "comprehension_litterale"),
      ("Why was nobody hurt by the branch?", "Because the pupils were not in the yard during the storm",
       ["Because the branch was small", "Because the teacher caught it", "Because the baobab is old"],
       "inference")]),
    ("Ibou's Letter",
     "Ibou lives in Ziguinchor. He writes a letter to his cousin Alioune, who lives in Saint-Louis. "
     "He tells him that he won the reading contest at his school. He ends his letter with: "
     "\u201cCome quickly in the holidays, I have lots of books to lend you!\u201d",
     [("Where does Alioune live?", "In Saint-Louis", ["In Ziguinchor", "In Dakar", "In Thiès"], "comprehension_litterale"),
      ("What does Ibou probably like?", "Reading", ["Football", "Fishing", "Cooking"], "inference")]),
    ("The Rainy Season",
     "In July, the first rains reach Khady's village. Her father prepares the field with a hoe. "
     "Khady helps him sow the millet. A few weeks later, little green shoots come out of the ground.",
     [("What do Khady and her father sow?", "Millet", ["Rice", "Groundnuts", "Maize"], "comprehension_litterale"),
      ("Why does her father wait until July to prepare the field?", "Because it is the start of the rains",
       ["Because it is the holidays", "Because Khady is free", "Because the hoe is new"], "inference")]),
    ("The Neighbourhood Match",
     "On Sunday, the Médina team plays against the Grand-Yoff team. At half-time, Médina is losing two goals to nil. "
     "At the end of the match, the Médina players dance and sing on the pitch.",
     [("Which teams play on Sunday?", "Médina and Grand-Yoff",
       ["Médina and Pikine", "Grand-Yoff and Rufisque", "Pikine and Rufisque"], "comprehension_litterale"),
      ("What most likely happened in the second half?", "Médina scored several goals and won",
       ["Grand-Yoff scored again", "The match was stopped", "It rained very hard"], "inference")]),
])

_GRAMMAR = pick([
    ("Les enfants ___ à l'école.", "vont", {"va": "accord", "von": "homophone"}),
    ("Mes sœurs ___ contentes.", "sont", {"est": "accord", "son": "homophone"}),
    ("Il ___ un vélo rouge.", "a", {"à": "homophone", "ont": "accord"}),
    ("Nous ___ du thé.", "buvons", {"boit": "accord", "buvont": "homophone"}),
    ("Awa ___ Modou jouent ensemble.", "et", {"est": "homophone", "sont": "accord"}),
    ("Les mangues sont ___.", "mûres", {"mûr": "accord", "mur": "homophone"}),
    ("Tu ___ ton cahier.", "ranges", {"range": "accord", "rangé": "homophone"}),
    ("Elles ___ chanté.", "ont", {"a": "accord", "on": "homophone"}),
], [
    ("The children ___ in the yard.", "were", {"was": "accord", "where": "homophone"}),
    ("The mangoes ___ ripe.", "are", {"is": "accord", "our": "homophone"}),
    ("Modou ___ the answer.", "knows", {"know": "accord", "nose": "homophone"}),
    ("We ___ rice and fish at lunch.", "ate", {"eats": "accord", "eight": "homophone"}),
    ("Look at the girls: ___ dancing!", "they're", {"their": "homophone", "she's": "accord"}),
    ("The cat licks ___ paw.", "its", {"it's": "homophone", "their": "accord"}),
    ("I have ___ pens.", "two", {"too": "homophone", "a": "accord"}),
    ("Khady ___ the school bell.", "hears", {"hear": "accord", "here's": "homophone"}),
])


# Énoncés des exercices, dans la langue de la plateforme (« she » : l'élève du problème est une fille).
def _pron_fr(she: bool, cap: bool = False) -> str:
    return ("Elle" if she else "Il") if cap else ("elle" if she else "il")


_PROMPTS = pick({
    "calc": lambda a, b: f"Calcule : {a} + {b} = ?",
    "places": [("dizaines", -2), ("centaines", -3)],
    "num": lambda n, place: f"Dans le nombre {n}, quel est le chiffre des {place} ?",
    "ps_early": lambda name, she, a, b: (
        f"{name} a {a} mangues. Sa maman lui en donne {b}. Combien de mangues a-t-{_pron_fr(she)} ?"),
    "pm_early": lambda name, she, a, b, c: (
        f"{name} a {a} billes. {_pron_fr(she, True)} en gagne {b}, puis en perd {c}. "
        f"Combien de billes a-t-{_pron_fr(she)} maintenant ?"),
    "ps": lambda name, she, q, item, price: (
        f"{name} achète {q} {item} à {price} F l'un. Combien paie-t-{_pron_fr(she)} ?"),
    "pm": lambda name, she, q, item, price, q2, item2, price2, paid: (
        f"{name} achète {q} {item} à {price} F l'un et {q2} {item2 if q2 > 1 else item2[:-1]} à {price2} F l'un. "
        f"{_pron_fr(she, True)} paie avec {paid} F. Combien lui rend-on ?"),
    "dec": lambda clue: f"{clue} Appuie sur 🔊 pour écouter le mot, puis choisis comment il s'écrit.",
    "gram": lambda sent: f"Complète : {sent}",
}, {
    "calc": lambda a, b: f"Work it out: {a} + {b} = ?",
    "places": [("tens", -2), ("hundreds", -3)],
    "num": lambda n, place: f"In the number {n}, which digit is in the {place} place?",
    "ps_early": lambda name, she, a, b: (
        f"{name} has {a} mangoes. {'Her' if she else 'His'} mum gives {'her' if she else 'him'} {b} more. "
        f"How many mangoes does {'she' if she else 'he'} have now?"),
    "pm_early": lambda name, she, a, b, c: (
        f"{name} has {a} marbles. {'She' if she else 'He'} wins {b} more, then loses {c}. "
        f"How many marbles does {'she' if she else 'he'} have now?"),
    "ps": lambda name, she, q, item, price: (
        f"{name} buys {q} {item} at {price} F each. How much does {'she' if she else 'he'} pay?"),
    "pm": lambda name, she, q, item, price, q2, item2, price2, paid: (
        f"{name} buys {q} {item} at {price} F each and {q2} {item2 if q2 > 1 else _SINGULAR_EN[item2]} "
        f"at {price2} F each. {'She' if she else 'He'} pays with {paid} F. "
        f"How much change does {'she' if she else 'he'} get?"),
    "dec": lambda clue: f"{clue} Press 🔊 to hear the word, then choose how it is spelled.",
    "gram": lambda sent: f"Fill in the blank: {sent}",
})


def _mcq(rng: random.Random, answer: str, error_map: dict[str, str]) -> list[str]:
    choices = [answer] + [c for c in error_map if c != answer]
    rng.shuffle(choices)
    return choices


def _ex(ex_id, skill, level, prompt, answer, error_map, rng, extra=None):
    d = {
        "id": ex_id, "subject": SKILLS[skill]["subject"], "skill": skill, "level": level,
        "prompt": prompt, "answer": str(answer),
        "error_map": {str(k): v for k, v in error_map.items() if str(k) != str(answer)},
        "hint": HINTS[skill],
    }
    d["choices"] = _mcq(rng, d["answer"], d["error_map"])
    if extra:
        d.update(extra)
    return d


def _maths_exercises(rng: random.Random, level: str, s: int, i: int, name: str, she: bool) -> list[dict]:
    """Calcul, numération et problèmes, adaptés au niveau."""
    out = []
    # Calcul : addition avec retenue (les unités dépassent toujours 10)
    ua = rng.randint(5, 9)
    ub = rng.randint(10 - ua, 9)
    if level == "CI":
        a, b = ua, ub
    elif level == "CP":
        a, b = rng.randint(1, 3) * 10 + ua, ub
    else:
        a, b = rng.randint(1, 5 * s) * 10 + ua, rng.randint(1, 4 * s) * 10 + ub
    right = a + b
    out.append(_ex(f"{level}-calc-{i}", "calcul", level, _PROMPTS["calc"](a, b), right,
                   {right - 10: "retenue", right + rng.choice([1, 2]): "fait_numerique", abs(a - b): "choix_operation"}, rng))
    # Numération : chiffre des dizaines ou des centaines (chiffres tous différents)
    digits = rng.sample("123456789", 2 if level in _EARLY else 3 if s < 4 else 4)
    n = int("".join(digits))
    places = _PROMPTS["places"]
    place, idx = places[0] if len(digits) == 2 else rng.choice(places)
    right = digits[idx]
    out.append(_ex(f"{level}-num-{i}", "numeration", level, _PROMPTS["num"](n, place), right,
                   {digits[-1]: "valeur_position", str(n)[:idx + len(digits) + 1]: "valeur_position", str(n): "valeur_position",
                    digits[0] if digits[0] != right else digits[1]: "valeur_position"}, rng))
    if level in _EARLY:
        # Problèmes du quotidien avec de petites quantités
        a, b, c = rng.randint(3, 9), rng.randint(2, 6), rng.randint(1, 3)
        out.append(_ex(f"{level}-ps-{i}", "probleme_simple", level, _PROMPTS["ps_early"](name, she, a, b),
                       a + b, {abs(a - b): "choix_operation", a + b + 1: "fait_numerique", b: "comprehension_litterale"}, rng))
        out.append(_ex(f"{level}-pm-{i}", "probleme_multi_etapes", level, _PROMPTS["pm_early"](name, she, a, b, c),
                       a + b - c, {a + b: "etape_incomplete", a - c: "etape_incomplete", a + b + c: "choix_operation",
                                   a + b - c + 1: "fait_numerique"}, rng))
        return out
    # Problème à une étape
    item, price = rng.choice(_ITEMS)
    q = rng.randint(2, 3 + s)
    right = q * price
    out.append(_ex(f"{level}-ps-{i}", "probleme_simple", level, _PROMPTS["ps"](name, she, q, item, price),
                   right, {q + price: "choix_operation", right + price: "fait_numerique", price: "comprehension_litterale"}, rng))
    # Problème à plusieurs étapes
    item2, price2 = rng.choice([x for x in _ITEMS if x[0] != item])
    q2 = rng.randint(1, 2)
    total = q * price + q2 * price2
    paid = (total // 1000 + 1) * 1000
    out.append(_ex(f"{level}-pm-{i}", "probleme_multi_etapes", level,
                   _PROMPTS["pm"](name, she, q, item, price, q2, item2, price2, paid),
                   paid - total, {total: "etape_incomplete", paid - q * price: "etape_incomplete",
                                  paid + total: "choix_operation", paid - total + 100: "fait_numerique"}, rng))
    return out


def _decoding_item(k: int) -> tuple[str, str, dict[str, str]]:
    """Mot à reconnaître, indice de sens et orthographes fautives (avec leur type d'erreur)."""
    if LANG == "en":
        word, clue, err = _WORDS_EN[k]
        return word, clue, dict(err)
    word, clue = _WORDS[k]
    err = {"".join(_SWAPS_VISUAL.get(c, c) for c in word): "inversion_lettres",
           word[0] + word[2] + word[1] + word[3:]: "inversion_lettres"}
    for x, y in _SWAPS_SOUND:
        if x in word:
            err[word.replace(x, y, 1)] = "confusion_sons"
            break
    return word, clue, err


def build_exercise_bank(per_skill: int = 10) -> list[dict]:
    rng = random.Random(2026)
    bank: list[dict] = []
    for level in LEVELS:
        s = _LEVEL_SCALE[level]
        for i in range(per_skill):
            name = rng.choice(_NAMES)
            she = name in ("Awa", "Khady", "Ndèye", "Mariama", "Coumba")
            bank += _maths_exercises(rng, level, s, i, name, she)
            # Décodage
            word, clue, err = _decoding_item((i + LEVELS.index(level) * 5) % len(_WORDS))
            bank.append(_ex(f"{level}-dec-{i}", "decodage", level, _PROMPTS["dec"](clue), word, err, rng,
                            {"read_aloud_text": word}))
            # Compréhension
            title, text, qs = _TEXTS[(i + LEVELS.index(level)) % len(_TEXTS)]
            question, ans, wrongs, etype = qs[i % 2]
            bank.append(_ex(f"{level}-comp-{i}", "comprehension", level,
                            f"**{title}**\n\n{text}\n\n{question}", ans, {w: etype for w in wrongs}, rng,
                            {"read_aloud_text": f"{text} {question}"}))
            # Grammaire
            sent, ans, errs = _GRAMMAR[(i + LEVELS.index(level)) % len(_GRAMMAR)]
            bank.append(_ex(f"{level}-gram-{i}", "grammaire", level, _PROMPTS["gram"](sent), ans, errs, rng))
    return bank


EXERCISE_BANK = build_exercise_bank()


def bank_by_id() -> dict[str, dict]:
    return {e["id"]: e for e in EXERCISE_BANK}


# Pistes pédagogiques affichées à l'enseignant sous un constat de difficulté : des gestes de classe, jamais un
# diagnostic. Une piste par type d'erreur dominant.
CLASSROOM_TIPS = pick({
    "fait_numerique": "Revoir les tables par petites séries, quelques minutes chaque jour, à l'oral.",
    "retenue": "Faire poser l'opération en écrivant la retenue en couleur au-dessus de la colonne suivante.",
    "valeur_position": "Manipuler un tableau unités / dizaines / centaines avec du matériel (bâtonnets, jetons).",
    "choix_operation": "Faire dire avec ses mots ce que demande le problème avant de choisir l'opération.",
    "etape_incomplete": "Faire relire la question finale avant de calculer, et numéroter les étapes du problème.",
    "inversion_lettres": "Travailler les lettres proches (b/d, p/q) en les traçant et en les disant à voix haute.",
    "confusion_sons": "Faire répéter et comparer les sons proches (f/v, ch/j) à l'oral avant de les écrire.",
    "comprehension_litterale": "Faire souligner dans le texte la phrase qui contient la réponse.",
    "inference": "Poser des questions « pourquoi ? » à l'oral sur de courts textes, en cherchant les indices ensemble.",
    "accord": "Faire relier par une flèche le sujet et le verbe avant d'écrire la terminaison.",
    "homophone": "Proposer l'astuce de remplacement (a → avait, et → et puis) au moment de la relecture.",
    "reponse_impulsive": "Inviter l'élève à relire la question et à attendre quelques secondes avant de répondre.",
}, {
    "fait_numerique": "Review times tables in small sets, out loud, for a few minutes every day.",
    "retenue": "Have the pupil write the sum in columns, with the carried digit in colour above the next column.",
    "valeur_position": "Use a ones / tens / hundreds table with real objects (sticks, counters).",
    "choix_operation": "Ask the pupil to say in their own words what the problem asks before choosing the operation.",
    "etape_incomplete": "Have the pupil reread the final question before calculating, and number the steps of the problem.",
    "inversion_lettres": "Practise similar letters (b/d, p/q) by tracing them and saying them out loud.",
    "confusion_sons": "Have the pupil repeat and compare similar sounds (f/v, s/z) out loud before writing them.",
    "comprehension_litterale": "Ask the pupil to underline the sentence in the text that contains the answer.",
    "inference": "Ask \u201cwhy?\u201d questions out loud about short texts, looking for clues together.",
    "accord": "Have the pupil draw an arrow from the subject to the verb before writing the ending.",
    "homophone": "Teach the substitution trick when rereading (it's → it is, they're → they are).",
    "reponse_impulsive": "Invite the pupil to reread the question and wait a few seconds before answering.",
})

# Formulation courte de chaque type d'erreur, pour la vue d'ensemble de la classe.
ERROR_SHORT = pick({
    "fait_numerique": "se trompe dans les tables",
    "retenue": "oublie la retenue",
    "valeur_position": "confond unités, dizaines et centaines",
    "choix_operation": "choisit la mauvaise opération",
    "etape_incomplete": "s'arrête à la première étape",
    "inversion_lettres": "inverse b/d, p/q",
    "confusion_sons": "confond f/v, ch/j",
    "comprehension_litterale": "ne retrouve pas l'info dans le texte",
    "inference": "a du mal à déduire",
    "accord": "oublie les accords",
    "homophone": "confond a/à, et/est",
    "reponse_impulsive": "répond trop vite",
}, {
    "fait_numerique": "gets times tables wrong",
    "retenue": "forgets to carry",
    "valeur_position": "mixes up ones, tens and hundreds",
    "choix_operation": "picks the wrong operation",
    "etape_incomplete": "stops after the first step",
    "inversion_lettres": "mixes up b/d, p/q",
    "confusion_sons": "mixes up f/v, s/z",
    "comprehension_litterale": "can't find the information in the text",
    "inference": "struggles to infer",
    "accord": "forgets agreement",
    "homophone": "mixes up there/their, its/it's",
    "reponse_impulsive": "answers too quickly",
})
