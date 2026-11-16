"""Nœuds du graphe LangGraph. Chaque nœud lit l'état, appelle des outils MCP et renvoie une mise à jour."""
from __future__ import annotations

import asyncio
import base64
import json
import re
from pathlib import Path

from langgraph.types import interrupt

from .. import llm, wording
from ..config import (CURRENT_YEAR, LLM_EXERCISES, LOW_ACCURACY, MIN_ANSWERS_PER_TERM, MIN_TERMS_FOR_PATTERN,
                      STRONG_ACCURACY, UPLOAD_DIR)
from ..i18n import pick, tr
from ..knowledge import CONTRAST, ERROR_TAXONOMY, LEVELS, SKILLS, find_forbidden_label
from ..records import audit
from . import contradictions, documents, planning, reasoning
from . import trends as trend_code
from .state import State, pct, skill_label, step
from .toolkit import Toolkit

from ..trends import TREND_PARAMS  # noqa: E402  (réexporté pour evals/run_evals.py)
SUMMARY_PROMPT = pick(
    "Tu rédiges pour la famille d'un élève de primaire un court message (120 mots max) en français très simple, "
    "chaleureux et concret : d'abord les réussites, puis ce qui est encore difficile (sans aucun diagnostic ni "
    "étiquette), puis ce que l'école fait et une idée simple pour aider à la maison. Ne compare pas l'enfant "
    'aux autres. JSON : {"text": ...}',
    "You write a short message (120 words max) for the family of a primary-school learner, in very simple, warm and "
    "concrete English: first the successes, then what is still difficult (without any diagnosis or label), then "
    "what the school is doing and one simple idea to help at home. Do not compare the child with others. Use the "
    'child\'s first name, never "he" or "she". JSON: {"text": ...}'
)
EXERCISE_PROMPT = pick(
    "Tu crées des exercices courts à choix multiples pour des élèves de primaire au Sénégal (contexte local, "
    "FCFA, prénoms sénégalais). Chaque mauvais choix correspond à un type d'erreur de la taxonomie. "
    'Réponds en JSON : {"exercises": [{"prompt", "answer", "choices", "error_map": {"choix_faux": "type"}, "hint"}]}',
    "You create short multiple-choice exercises in English for primary-school learners in Senegal (local context, "
    "CFA francs, Senegalese first names). Each wrong choice corresponds to an error type from the taxonomy. "
    'Answer in JSON: {"exercises": [{"prompt", "answer", "choices", "error_map": {"wrong_choice": "type"}, "hint"}]}'
)


class Nodes:
    def __init__(self, tk: Toolkit) -> None:
        self.tk = tk

    async def _call(self, state: State, tool: str, **args):
        return await self.tk.call(tool, state["thread_id"], state.get("learner_id"), **args)

    # -- Planification et collecte ------------------------------------------

    async def plan(self, state: State) -> dict:
        """Lit la situation de l'élève (ressource MCP), écrit un plan avec le modèle local, puis le vérifie."""
        status = llm.status()
        mode = "llm" if status["llm"] else "rules"
        base = {"mode": mode, "rounds": state.get("rounds", 0), "done_steps": []}
        if state["trigger"] == "document":
            return base | {"plan": {"steps": [], "focus": "tout"}} | step(
                tr("Planification"), tr("Un document est arrivé : le lire, vérifier sa cohérence avec la liste de "
                                        "classe, puis le faire confirmer par l'enseignant."))
        situation = json.loads(await self.tk.resource(f"xamkids://learners/{state['learner_id']}/situation"))
        plan, title, detail = await asyncio.to_thread(planning.make_plan, state, situation, mode == "llm")
        if f := state.get("followup"):
            detail = (tr("Vérification que je me suis programmée le {date} : {reason} ", date=f['created_at'][:10],
                         reason=f['reason']) + detail)
        missing = ", ".join(self.tk.unavailable)
        return base | {"plan": plan} | step(title, detail + (tr(" Serveurs indisponibles : {missing}.", missing=missing)
                                                             if missing else ""))

    async def analyze(self, state: State) -> dict:
        r = await self._call(state, "analyze_answers", learner_id=state["learner_id"], session_id=state.get("session_id"))
        dominant = ", ".join(f"{s}: {v['dominant_error']}" for s, v in r["by_skill"].items() if v["dominant_error"])
        return {"analysis": r, **step(tr("Analyse des réponses (analyze_answers)"),
                                      tr("{n} réponse(s) classée(s) ({scope}). Erreurs dominantes : {dominant}.",
                                         n=r['newly_classified'], scope=r['scope'], dominant=dominant or tr('aucune')))}

    async def retrieve(self, state: State) -> dict:
        tl = await self._call(state, "get_learner_timeline", learner_id=state["learner_id"])
        n = sum(s["n"] for t in tl["terms"] for s in t["skills"].values())
        detail = tr("{terms} trimestres, {n} réponses, {obs} observations, {findings} constats déjà enregistrés.",
                    terms=len(tl['terms']), n=n, obs=len(tl['observations']), findings=len(tl['findings']))
        if gap := await self._ask_for_missing_history(state, tl):
            detail += " " + gap
        return {"timeline": tl, **step(tr("Historique (get_learner_timeline)"), detail)}

    async def _ask_for_missing_history(self, state: State, tl: dict) -> str:
        """Sans historique des années passées, l'agent ne peut rien dire de durable : il identifie ce qui lui
        manque et le demande lui-même à l'enseignant (le livret scolaire), une seule fois."""
        past = [t for t in tl["terms"] if t["school_year"] < tl["current_year"]]
        if past or tl.get("report_card") or state["trigger"] == "guardian_summary":
            return ""
        name = tl["learner"]["first_name"]
        res = await self._call(state, "alert_teacher", learner_id=state["learner_id"], kind="question",
                               payload={"request": "livret"},
                               message=tr("Je n'ai aucun historique de {name} avant cette année : je ne peux donc rien "
                                          "dire de durable. Pouvez-vous m'envoyer une photo de son livret scolaire ?",
                                          name=name))
        return (tr("Information manquante : aucun historique avant cette année. ")
                + (tr("Livret scolaire demandé à l'enseignant.") if res.get("action") == "created"
                   else tr("Livret déjà demandé à l'enseignant, en attente.")))

    async def trends(self, state: State) -> dict:
        """Les tendances viennent du serveur MCP (compute_trends : mêmes chiffres pour tout client). L'agent les
        recalcule ensuite dans le bac à sable Run Python, avec le même code, pour les vérifier de façon
        indépendante : un écart est signalé et le calcul du serveur fait foi."""
        result = await self._call(state, "compute_trends", learner_id=state["learner_id"])
        where = tr("serveur MCP xamkids-profile")
        if not isinstance(result, dict) or "skills" not in result:  # serveur sans l'outil : calcul local
            result, where = trend_code.run_locally(state["timeline"], TREND_PARAMS), tr("repli local")
        check = tr("non vérifié (bac à sable indisponible)")
        if self.tk.has("run_python_code"):
            text = await self._call(state, "run_python_code", python_code=trend_code.build_code(state["timeline"], TREND_PARAMS))
            if m := re.search(r"<return_value>\s*(.*?)\s*</return_value>", text, re.S):
                sandbox = json.loads(m.group(1))
                same = all(sandbox["skills"].get(k, {}).get("consecutive_low_terms") == v["consecutive_low_terms"]
                           and sandbox["skills"].get(k, {}).get("pattern") == v["pattern"]
                           for k, v in result["skills"].items())
                check = tr("vérifié dans le bac à sable Run Python") if same else tr("ÉCART avec le bac à sable Run Python")
                if not same:
                    audit.log("agent", "run-python", "trend_mismatch", {"server": where}, "écart", "ok",
                              state["thread_id"], state["learner_id"])
        flagged = [tr("{skill} ({n} trim.)", skill=s, n=r['consecutive_low_terms'])
                   for s, r in result["skills"].items() if r["pattern"]]
        dips = [d["term"] for d in result["global_dips"]]
        return {"trends": result, **step(tr("Tendances calculées ({where}, {check})", where=where, check=check),
                                         tr("Tendances durables : {flagged}. Baisses généralisées : {dips}.",
                                            flagged=', '.join(flagged) or tr('aucune'),
                                            dips=', '.join(dips) or tr('aucune')))}

    # -- Croisement des observations écrites et des chiffres -----------------

    async def crosscheck(self, state: State) -> dict:
        """Le modèle relève les contradictions entre observations et chiffres ; le calcul les vérifie ; on demande."""
        title = tr("Croisement observations / chiffres")
        if state["mode"] != "llm":
            return step(title, tr("Sans modèle de langage, je ne sais pas lire les observations écrites : étape sautée."))
        found, rejected, n = await asyncio.to_thread(contradictions.find, state)
        asked = 0
        for c in found:
            res = await self._call(state, "alert_teacher", learner_id=state["learner_id"], kind="question",
                                   message=c["question"],
                                   payload={"observation_id": c["observation_id"], "skill": c["competence"],
                                            "term": c["term"], "accuracy": c["accuracy"], "type": c["type"]})
            asked += res.get("action") == "created"
        detail = tr("{n} observation(s) récente(s) relue(s) avec les chiffres de leur trimestre. ", n=n)
        detail += (tr("{found} contradiction(s) vérifiée(s) par le calcul, {asked} nouvelle(s) question(s) posée(s).",
                      found=len(found), asked=asked)
                   if found else tr("Aucune contradiction."))
        if rejected:
            detail += tr(" Propositions du modèle rejetées par le calcul : ") + "; ".join(rejected) + "."
        return step(title + tr(" (modèle local, vérifié par le calcul)"), detail)

    # -- Suivi : points forts et difficultés déjà enregistrées ----------------

    async def monitor(self, state: State) -> dict:
        notes = ([await self._record_strengths(state), await self._watch_attendance(state)]
                 + await self._follow_up_difficulties(state))
        return step(tr("Points forts et suivi"), "; ".join(n for n in notes if n) or tr("Rien de nouveau."))

    async def _record_strengths(self, state: State) -> str:
        tl, lid = state["timeline"], state["learner_id"]
        known = {f["skill"] for f in tl["findings"] if f["kind"] == "strength" and f["status"] == "active"}
        recorded = []
        for skill, r in state["trends"]["skills"].items():
            if r["consecutive_high_terms"] < 3 or skill in known:
                continue
            statement = reasoning.strength_statement(tl["learner"]["first_name"], skill, r)
            evidence = {"high_terms": r["high_terms"], "rate": r["mean_acc_high_terms"]}
            evidence["sentence"] = await self._sentence(state, "strength", skill, evidence, statement)
            res = await self._call(state, "update_profile", learner_id=lid, kind="strength", skill=skill,
                                   statement=statement, sources=[f"answer:{i}" for i in r["high_correct_ids"]],
                                   since=reasoning.since_term(r), evidence=evidence)
            if res.get("ok"):
                recorded.append((statement, res["finding_id"]))
        if not recorded:
            return ""
        await self._call(state, "alert_teacher", learner_id=lid, kind="strength", finding_id=recorded[0][1],
                         message=tr("Point(s) fort(s) durable(s) : ") + " ".join(s for s, _ in recorded))
        return tr("{n} point(s) fort(s) enregistré(s)", n=len(recorded))

    async def _watch_attendance(self, state: State) -> str:
        """Absences en hausse : un point « à surveiller », sourcé par les registres, jamais une difficulté."""
        a, lid = state["trends"].get("attendance") or {}, state["learner_id"]
        current = next((f for f in state["timeline"]["findings"]
                        if f["kind"] == "watch" and f["skill"] == "presence" and f["status"] == "active"), None)
        sources = [f"attendance:{i}" for i in a.get("attendance_ids", [])]
        if a.get("drop") and not current:
            statement = tr("Absences en hausse : {days} jours d'absence au {term} ({rate} de présence), contre {mean} "
                           "de présence en moyenne sur les trois trimestres précédents.", days=a['latest_absences'],
                           term=a['latest_term'], rate=pct(a['latest_rate']), mean=pct(a['previous_mean']))
            evidence = dict(a)
            evidence["sentence"] = await self._sentence(state, "watch", "presence", evidence, statement)
            res = await self._call(state, "update_profile", learner_id=lid, kind="watch", skill="presence",
                                   statement=statement, sources=sources, since=a["since_term"], evidence=evidence)
            if res.get("ok"):
                await self._call(state, "alert_teacher", learner_id=lid, kind="watch", finding_id=res["finding_id"],
                                 message=tr("À surveiller. {statement} Ce n'est pas une conclusion : à évoquer avec la "
                                            "famille si vous le jugez utile.", statement=statement))
                when = await self._schedule(state, res["finding_id"], after_sessions=3,
                                            reason=tr("Absences en hausse : vérifier si la présence revient à la normale."))
                return tr("absences en hausse : point à surveiller enregistré, vérification programmée {when}", when=when)
        if current and a.get("recovered"):
            await self._call(state, "update_profile", learner_id=lid, kind="watch", skill="presence", status="resolved",
                             statement=current["statement"] + tr(" — Présence revenue à {rate}.", rate=pct(a['latest_rate'])),
                             sources=sources)
            return tr("présence revenue à la normale")
        return ""

    async def _follow_up_difficulties(self, state: State) -> list[str]:
        tl, lid, trend = state["timeline"], state["learner_id"], state["trends"]["skills"]
        notes = []
        for f in tl["findings"]:
            if f["kind"] != "difficulty" or f["status"] != "active" or f["skill"] not in trend:
                continue
            r = trend[f["skill"]]
            recent = [x for x in r["series"] if x["n"] >= MIN_ANSWERS_PER_TERM][-2:]
            if len(recent) == 2 and not any(x["low"] for x in recent) and r["slope_last6"] > 0:
                ids = r["high_correct_ids"] or r["dominant_error_answer_ids"]
                res = await self._call(state, "update_profile", learner_id=lid, kind="difficulty", skill=f["skill"],
                                       status="resolved", sources=[f"answer:{i}" for i in ids],
                                       statement=f["statement"] + tr(" — Progrès nets sur les deux derniers trimestres."))
                if res.get("ok"):
                    await self._call(state, "alert_teacher", learner_id=lid, kind="persistent", finding_id=f["id"],
                                     message=tr("Bonne nouvelle : la difficulté en {skill} ne se retrouve plus sur les "
                                                "deux derniers trimestres.", skill=skill_label(f['skill'])))
                    notes.append(tr("difficulté en {skill} marquée comme résolue", skill=f['skill']))
            elif state["trigger"] == "term_review" and r["latest_low"]:
                await self._call(state, "alert_teacher", learner_id=lid, kind="persistent", finding_id=f["id"],
                                 message=tr("Difficulté toujours présente en {skill} ({n} trimestres consécutifs). "
                                            "{statement}", skill=skill_label(f['skill']), n=r['consecutive_low_terms'],
                                            statement=f['statement']))
                notes.append(tr("difficulté persistante signalée ({skill})", skill=f['skill']))
        return notes

    # -- Raisonnement et actions ---------------------------------------------

    async def reason(self, state: State) -> dict:
        decision, title, detail = await asyncio.to_thread(reasoning.decide, state, self.tk.catalog())
        return {"decision": decision, **step(title, detail)}

    async def propose(self, state: State) -> dict:
        d, lid = state["decision"], state["learner_id"]
        skill, etype = d["skill"], d["error_type"]
        prev = state.get("hypothesis") or {}
        switch = bool(d.get("switch"))
        hypothesis = d.get("hypothesis") if switch else (prev.get("text") or d.get("hypothesis"))
        explanation = d.get("explanation") if switch else (prev.get("explanation") or d.get("explanation") or "locale")
        tried = (prev.get("tried") or [prev["explanation"]] if prev.get("explanation") else [])
        tried = tried + [explanation] if explanation not in tried else tried
        same_skill = explanation in ("lecture", "rythme")  # contraste sur la même compétence (écouté / en prenant son temps)
        res, source = None, ""
        if state["mode"] == "llm" and LLM_EXERCISES and not same_skill:
            res, source = await self._model_exercises(state, skill, etype, hypothesis), tr("générés par le modèle local")
        if not res or not res.get("ok"):
            refused = bool(res)
            targets = await self._bank_picks(state, skill, etype)
            contrast_ids = (await self._same_skill_picks(state, skill, targets) if same_skill
                            else await self._contrast_picks(state, skill))
            role = {"lecture": "listened", "rythme": "slowed"}.get(explanation, f"contrast:{CONTRAST.get(skill, (skill,))[0]}")
            facts = wording.proposal_facts(state["timeline"]["learner"]["first_name"], skill, hypothesis,
                                           [(len(targets), "target")] + ([(len(contrast_ids), role)] if contrast_ids else []))
            teacher_text = await asyncio.to_thread(wording.proposal_sentences, facts, state["mode"] == "llm")
            res = await self._call(state, "propose_exercises", learner_id=lid, skill=skill, hypothesis=hypothesis,
                                   bank_exercise_ids=targets, contrast_exercise_ids=contrast_ids,
                                   contrast_mode={"lecture": "ecoute", "rythme": "temps"}.get(explanation, "voisine"),
                                   teacher_text={k: teacher_text[k] for k in ("noticed", "proposal", "source")})
            source = tr("choisis dans la banque") + (tr(" (exercices du modèle refusés par le serveur)") if refused else "")
        if not res.get("ok"):
            return {"outcome": tr("Échec de la proposition : {refused}", refused=res.get('refused')),
                    **step(tr("Exercices ciblés refusés"), res.get("refused", ""))}
        contrast = ("" if not res.get("contrast") else
                    tr(", dont {n} écoutés (texte lu à l'élève)", n=res['contrast']) if explanation == "lecture" else
                    tr(", dont {n} en prenant son temps", n=res['contrast']) if explanation == "rythme" else
                    tr(", dont {n} de contraste en {skill}", n=res['contrast'], skill=skill_label(CONTRAST[skill][0])))
        return {"hypothesis": {"skill": skill, "error_type": etype, "explanation": explanation, "text": hypothesis,
                               "base_text": prev.get("base_text") or prev.get("text") or hypothesis, "tried": tried,
                               "observations": d.get("observations") or prev.get("observations") or [],
                               "exercise_ids": res["exercise_ids"]},
                "rounds": state.get("rounds", 0) + 1,
                **step(tr("Changement de piste : nouveaux exercices ciblés (propose_exercises)") if switch
                       else tr("Exercices ciblés proposés (propose_exercises)"),
                       tr("{n} exercices {source}{contrast}, EN ATTENTE de validation. Hypothèse : {hypothesis}",
                          n=len(res['exercise_ids']), source=source, contrast=contrast, hypothesis=hypothesis))}

    async def _bank_picks(self, state: State, skill: str, etype: str) -> list[str]:
        """Exercices de la banque dont les mauvais choix visent l'erreur suspectée ; un nouveau tour en prend d'autres."""
        level = state["timeline"]["learner"]["level"]
        bank = json.loads(await self.tk.resource(f"xamkids://exercises/bank/{level}/{skill}"))
        fitting = [e["id"] for e in bank if etype in e["error_map"].values()]
        ordered = fitting + [e["id"] for e in bank if e["id"] not in fitting]
        start = 3 * state.get("rounds", 0) % max(1, len(ordered) - 2)
        return ordered[start:start + 3]

    async def _sentence(self, state: State, kind: str, skill: str, evidence: dict, statement: str = "",
                        status: str = "active") -> dict:
        """Phrase du constat pour l'enseignant : rédigée par le modèle local, vérifiée par le code (wording.py)."""
        return await asyncio.to_thread(wording.finding_sentence, state["timeline"]["learner"]["first_name"], kind,
                                       skill, evidence, statement, status, state["mode"] == "llm")

    async def _contrast_picks(self, state: State, skill: str) -> list[str]:
        """Deux exercices d'une compétence voisine (test par contraste), s'il en existe une pour cette compétence."""
        if skill not in CONTRAST:
            return []
        level = state["timeline"]["learner"]["level"]
        bank = json.loads(await self.tk.resource(f"xamkids://exercises/bank/{level}/{CONTRAST[skill][0]}"))
        start = 2 * state.get("rounds", 0) % max(1, len(bank) - 1)
        return [e["id"] for e in bank[start:start + 2]]

    async def _same_skill_picks(self, state: State, skill: str, targets: list[str]) -> list[str]:
        """Deux autres exercices de la même compétence (écoutés, ou faits en prenant son temps)."""
        level = state["timeline"]["learner"]["level"]
        bank = [e["id"] for e in json.loads(await self.tk.resource(f"xamkids://exercises/bank/{level}/{skill}"))
                if e["id"] not in targets]
        start = 2 * state.get("rounds", 0) % max(1, len(bank) - 1)
        return bank[start:start + 2]

    async def _model_exercises(self, state: State, skill: str, etype: str, hypothesis: str) -> dict | None:
        request = {"niveau": state["timeline"]["learner"]["level"], "competence": SKILLS[skill]["label"],
                   "hypothese_a_tester": hypothesis, "erreur_visee": etype, "nombre": 4, "taxonomie": ERROR_TAXONOMY}
        gen = await asyncio.to_thread(llm.chat_json, EXERCISE_PROMPT, json.dumps(request, ensure_ascii=False))
        if not gen or not gen.get("exercises"):
            return None
        return await self._call(state, "propose_exercises", learner_id=state["learner_id"], skill=skill,
                                hypothesis=hypothesis, exercises=gen["exercises"][:4],
                                contrast_exercise_ids=await self._contrast_picks(state, skill))

    async def wait_approval(self, state: State) -> dict:
        # Pause : l'exécution reprend quand l'enseignant valide ou refuse dans l'interface.
        answer = interrupt({"type": "approval", "exercise_ids": state["hypothesis"]["exercise_ids"],
                            "hypothesis": state["hypothesis"]["text"]})
        teacher, comment = answer.get("teacher"), answer.get("comment") or ""
        if not answer.get("approved"):
            return {"outcome": tr("Exercices refusés par {teacher} : {comment}. Hypothèse laissée ouverte, rien n'est "
                                  "enregistré.", teacher=teacher, comment=comment or tr('sans commentaire')),
                    **step(tr("Décision de l'enseignant : refus"), comment, teacher=teacher)}
        return step(tr("Décision de l'enseignant : exercices validés"), comment, teacher=teacher)

    async def wait_results(self, state: State) -> dict:
        # Pause : l'exécution reprend quand l'élève a fait les exercices ciblés.
        answer = interrupt({"type": "results", "exercise_ids": state["hypothesis"]["exercise_ids"]})
        return {"session_id": answer.get("session_id"), "trigger": "targeted_session",
                **step(tr("Exercices ciblés réalisés par l'élève"),
                       tr("Séance {session} : nouvelles informations, je refais mon plan.", session=answer.get('session_id')))}

    async def record(self, state: State) -> dict:
        d, h, lid = state["decision"], state["hypothesis"], state["learner_id"]
        ev = reasoning.evaluate_targeted(state)
        r = state["trends"]["skills"][h["skill"]]
        sources = ([f"exercise:{i}" for i in h["exercise_ids"]] + [f"answer:{i}" for i in ev["answer_ids"]] +
                   [f"answer:{i}" for i in r["dominant_error_answer_ids"][:10]] +
                   [f"observation:{i}" for i in (h.get("observations")
                                                  or reasoning.related_observations(state["timeline"], h["skill"]))])
        evidence = {"since": reasoning.since_term(r), "low_terms": r["low_terms"], "mean_acc_low_terms": r["mean_acc_low_terms"],
                    "class_acc": r["mean_class_acc_low_terms"], "dominant_error": h["error_type"],
                    "dominant_error_share": r["dominant_error_share"], "targeted": ev, "hypothesis": h["text"],
                    "explanation": h.get("explanation", "locale")}
        profile = dict(learner_id=lid, kind="difficulty", skill=h["skill"], sources=sources, evidence=evidence,
                       since=reasoning.since_term(r))

        if d["action"] == "rule_out":
            statement = tr("Hypothèse écartée : {hyp} Les exercices ciblés ont été réussis à {acc}.", hyp=h['text'],
                           acc=pct(ev['accuracy']))
            evidence["sentence"] = await self._sentence(state, "difficulty", h["skill"], evidence, statement, "ruled_out")
            res = await self._call(state, "update_profile", status="ruled_out", statement=statement, **profile)
            await self._call(state, "alert_teacher", learner_id=lid, kind="ruled_out", finding_id=res.get("finding_id"),
                             message=statement)
            return {"outcome": tr("Hypothèse écartée après les exercices ciblés."), "hypothesis": None,
                    **step(tr("Hypothèse écartée (update_profile, statut ruled_out)"), statement)}

        template = reasoning.finding_statement(state, h, ev)
        statement = d.get("statement") if d.get("source") == "modèle" and d.get("statement") else template
        evidence["sentence"] = await self._sentence(state, "difficulty", h["skill"], evidence, statement)
        res = await self._call(state, "update_profile", statement=statement, **profile)
        if not res.get("ok") and statement != template:  # formulation du modèle refusée : on reprend celle des règles
            statement = template
            res = await self._call(state, "update_profile", statement=statement, **profile)
        if not res.get("ok"):
            return {"outcome": tr("Constat refusé par le serveur : {refused}", refused=res.get('refused')),
                    **step(tr("Constat refusé"), res.get("refused", ""))}
        await self._call(state, "alert_teacher", learner_id=lid, kind="difficulty", finding_id=res["finding_id"],
                         message=tr("Difficulté durable confirmée. {statement} {n} sources citées dans le profil.",
                                    statement=statement, n=len(sources)))
        when = await self._schedule(state, res["finding_id"], after_sessions=4,
                                    reason=tr("Difficulté en {skill} : vérifier si elle persiste ou se résout.",
                                              skill=skill_label(h['skill'])))
        return {"outcome": tr("Difficulté enregistrée (constat n°{id}) et enseignant alerté. Prochaine vérification {when}.",
                              id=res['finding_id'], when=when), "hypothesis": None,
                **step(tr("Constat enregistré (update_profile), enseignant alerté (alert_teacher), vérification "
                          "programmée (schedule_followup)"),
                       tr("{statement} Je reviendrai vérifier {when}.", statement=statement, when=when),
                       sources=len(sources))}

    async def _schedule(self, state: State, finding_id: int, reason: str, after_sessions: int) -> str:
        """L'agent se programme lui-même une prochaine vérification (outil MCP schedule_followup)."""
        res = await self._call(state, "schedule_followup", learner_id=state["learner_id"], finding_id=finding_id,
                               reason=reason, after_sessions=after_sessions)
        return res.get("when", tr("plus tard")) if res.get("ok") else tr("(non programmée)")

    async def ask_teacher(self, state: State) -> dict:
        question = state["decision"].get("question") or state["decision"].get("rationale")
        await self._call(state, "alert_teacher", learner_id=state["learner_id"], kind="question", message=question,
                         payload={"hypothesis": state.get("hypothesis")})
        return {"outcome": tr("Question posée à l'enseignant."), **step(tr("Question à l'enseignant (alert_teacher)"), question)}

    async def summarize(self, state: State) -> dict:
        tl, trend = state["timeline"], state["trends"]["skills"]
        name = tl["learner"]["first_name"]
        # Seuls les constats validés par l'enseignant peuvent atteindre une famille.
        active = [f for f in tl["findings"] if f["status"] == "active" and f["validated_by"]]
        if not active:
            outcome = tr("Aucun constat validé par l'enseignant : rien à résumer pour la famille. "
                         "Validez d'abord les constats du profil.")
            return {"outcome": outcome, **step(tr("Résumé pour la famille non rédigé"), outcome)}
        strengths = [f for f in active if f["kind"] == "strength"]
        difficulties = [f for f in active if f["kind"] == "difficulty"]
        text = None
        if state["mode"] == "llm":
            facts = {"prenom": name, "points_forts": [f["statement"] for f in strengths],
                     "difficultes": [f["statement"] for f in difficulties]}
            text = ((await asyncio.to_thread(llm.chat_json, SUMMARY_PROMPT, json.dumps(facts, ensure_ascii=False))) or {}).get("text")
        if not text or find_forbidden_label(text):
            text = reasoning.guardian_summary_template(name, strengths, difficulties, trend)
        sources = [f"answer:{i}" for s in trend.values() for i in (s["high_correct_ids"] or s["dominant_error_answer_ids"])[:2]][:12]
        sources += [src for f in active for src in f["sources"][:4]]
        res = await self._call(state, "draft_guardian_summary", learner_id=state["learner_id"], text=text, sources=sources[:20])
        outcome = (tr("Résumé pour la famille rédigé, en attente de validation.") if res.get("ok")
                   else tr("Résumé refusé : {refused}", refused=res.get('refused')))
        return {"outcome": outcome, **step(tr("Résumé pour la famille (draft_guardian_summary)"),
                                           tr("Fondé sur {n} constat(s) validé(s) par l'enseignant. En attente de "
                                              "relecture et de validation.", n=len(active)))}

    # -- Documents -------------------------------------------------------------

    async def read_document(self, state: State) -> dict:
        doc = state["document"]
        if doc.get("kind") == "livret":
            return await self._read_livret(state, doc)
        rows, issues, how = await self._extract_rows(state, doc["filename"])
        roster = json.loads(await self.tk.resource(f"xamkids://classes/{doc['class_id']}/roster"))
        matched, mismatches = documents.match_roster(rows, roster)
        issues += mismatches
        payload = {"document_id": doc.get("document_id"), "filename": doc["filename"], "attendance": matched, "issues": issues}
        if issues:
            kind = "question"
            message = (tr("Document « {file} » : je préfère vous demander plutôt que deviner. ", file=doc['filename'])
                       + " ".join(issues)
                       + (tr(" {n} ligne(s) lue(s) sans problème, à confirmer.", n=len(matched)) if matched else ""))
        else:
            kind = "document"
            message = tr("Document « {file} » lu ({how}) : {n} lignes de présence. Merci de vérifier avant import.",
                         file=doc['filename'], how=how, n=len(matched))
        await self._call(state, "alert_teacher", kind=kind, class_id=doc["class_id"], message=message, payload=payload)
        return {"outcome": tr("Question posée à l'enseignant sur le document.") if issues
                else tr("Lecture soumise à l'enseignant."),
                **step(tr("Lecture du document ({how})", how=how or tr('échec')), message, rows=len(matched),
                       issues=len(issues))}

    async def _read_livret(self, state: State, doc: dict) -> dict:
        """Livret scolaire d'un élève qui arrive : notes et appréciations des années passées, à faire confirmer."""
        content, issues, how = await self._read_file(state, doc["filename"])
        livret: dict = {}
        if isinstance(content, str):
            livret, issues = documents.parse_livret_csv(content)
        elif isinstance(content, bytes):
            livret, issues = await asyncio.to_thread(documents.read_livret_scan, content)
        grades, appreciations, problems = documents.check_livret(livret, CURRENT_YEAR, LEVELS) if livret else ([], [], [])
        issues += problems
        kept = []
        for a in appreciations:  # une appréciation qui pose une étiquette n'entre pas dans le dossier
            if find_forbidden_label(a["text"]):  # le terme n'est pas recopié : le message serait lui-même refusé
                issues.append(tr("Appréciation {level} {year} T{term} non reprise : elle contient un terme diagnostique "
                                 "ou une étiquette, que XamKids n'enregistre jamais.", level=a['level'],
                                 year=a['school_year'], term=a['term']))
            else:
                kept.append(a)
        name = f"{livret.get('first_name', '')} {livret.get('last_name', '')}".strip() or tr("élève inconnu")
        learner_id, mismatch = None, []
        if livret:
            roster = json.loads(await self.tk.resource(f"xamkids://classes/{doc['class_id']}/roster"))
            learner_id, mismatch = documents.match_livret_learner(livret, roster)
            issues += mismatch
        new_learner = bool(livret) and learner_id is None and not mismatch
        payload = {"document_id": doc.get("document_id"), "filename": doc["filename"], "class_id": doc["class_id"],
                   "livret": {"name": name, "first_name": livret.get("first_name"), "last_name": livret.get("last_name"),
                              "matricule": livret.get("matricule") or None, "learner_id": learner_id,
                              "new_learner": bool(new_learner), "grades": grades, "appreciations": kept},
                   "issues": issues}
        years = sorted({g["school_year"] for g in grades})
        summary = (tr("{n} note(s) sur {years} année(s) ({first} → {last}) et {kept} appréciation(s)", n=len(grades),
                      years=len(years), first=years[0], last=years[-1], kept=len(kept))
                   if grades else tr("aucune note lisible"))
        who = (tr("élève de la classe") if learner_id else
               tr("nouvel élève : il sera inscrit dans la classe à la confirmation") if new_learner
               else tr("élève à identifier"))
        message = tr("Livret de {name} ({who}) lu ({how}) : {summary}. Le rang et les moyennes de classe ne sont jamais "
                     "repris.", name=name, who=who, how=how or tr('échec'), summary=summary)
        if issues:
            message += tr(" Je préfère vous demander plutôt que deviner : ") + " ".join(issues)
        await self._call(state, "alert_teacher", kind="question" if issues or not grades else "document",
                         class_id=doc["class_id"], learner_id=learner_id, message=message, payload=payload)
        outcome = (tr("Livret soumis à l'enseignant pour confirmation.") if grades and not issues
                   else tr("Question posée à l'enseignant sur le livret."))
        return {"outcome": outcome, **step(tr("Lecture du livret scolaire ({how})", how=how or tr('échec')), message,
                                           rows=len(grades), issues=len(issues))}

    async def _read_file(self, state: State, filename: str) -> tuple[str | bytes | None, list[str], str]:
        """Contenu d'un document téléversé, lu par le serveur Filesystem : texte (CSV) ou image."""
        path, ext = str(UPLOAD_DIR / filename), Path(filename).suffix.lower()
        if not self.tk.has("read_text_file"):
            return None, [tr("Le serveur Filesystem est indisponible : je ne peux pas lire le document.")], ""
        if ext in (".csv", ".txt"):
            return await self._call(state, "read_text_file", path=path), [], tr("CSV lu par le serveur Filesystem")
        if ext in (".png", ".jpg", ".jpeg"):
            blocks = await self._call(state, "read_media_file", path=path)
            data = next((b.get("base64") or b.get("data") for b in blocks
                         if isinstance(b, dict) and (b.get("base64") or b.get("data"))), None)
            if not data:
                return None, [tr("Impossible de lire l'image.")], ""
            return base64.b64decode(data), [], tr("photo lue par le serveur Filesystem et le modèle de vision")
        return None, [tr("Format non pris en charge : {ext}.", ext=ext)], ""

    async def _extract_rows(self, state: State, filename: str) -> tuple[list[dict], list[str], str]:
        content, issues, how = await self._read_file(state, filename)
        if isinstance(content, str):
            rows, issues = documents.parse_csv(content)
            return rows, issues, how
        if isinstance(content, bytes):
            rows, issues = await asyncio.to_thread(documents.read_scan, content)
            return rows, issues, how
        return [], issues, how

    async def finish(self, state: State) -> dict:
        outcome = state.get("outcome") or (state.get("decision") or {}).get("rationale") or tr("Terminé.")
        return {"outcome": outcome, **step(tr("Fin de l'exécution"), outcome)}
