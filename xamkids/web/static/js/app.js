// XamKids Profile : voix, aides pendant les exercices, suivi des tâches de l'agent, graphiques.

// --- Textes affichés par ce script, dans la langue de la page -------------------------
const T = document.documentElement.lang === "en"
  ? { running: "In progress…", success: "% success", pct: "%" }
  : { running: "En cours…", success: " % de réussite", pct: " %" };

// --- Voix : les clips de la page sont joués l'un après l'autre -------------------------
let currentAudio = null;

function playSequence(urls) {
  if (!urls.length) return Promise.resolve();
  if (currentAudio) currentAudio.pause();
  const [first, ...rest] = urls;
  currentAudio = new Audio(first);
  currentAudio.onended = () => playSequence(rest);
  return currentAudio.play();
}

document.addEventListener("DOMContentLoaded", () => {
  const holder = document.querySelector("[data-voice]");
  if (holder) {
    const urls = JSON.parse(holder.dataset.voice || "[]").filter(Boolean);
    playSequence(urls).catch(() => {
      // Le navigateur bloque le son tant qu'on n'a pas cliqué : bouton pour l'activer.
      const unlock = document.querySelector(".voice-unlock");
      if (unlock) {
        unlock.style.display = "inline-flex";
        unlock.onclick = () => { unlock.style.display = "none"; playSequence(urls); };
      }
    });
  }

  // --- Aides pendant un exercice : écouter (signal observé par l'agent) et indice ------
  document.querySelectorAll("[data-listen]").forEach((btn) => btn.addEventListener("click", () => {
    document.querySelectorAll("input[name=read_aloud]").forEach((i) => (i.value = "1"));
    playSequence([btn.dataset.listen]);
  }));
  document.querySelectorAll("[data-hint]").forEach((btn) => btn.addEventListener("click", () => {
    document.querySelectorAll("input[name=hint]").forEach((i) => (i.value = "1"));
    document.querySelector(".hint")?.classList.add("show");
    if (btn.dataset.hint) playSequence([btn.dataset.hint]);
  }));

  // --- Exercice « en prenant son temps » : les réponses n'apparaissent qu'après quelques secondes ---
  document.querySelectorAll("[data-delay]").forEach((el) => setTimeout(() => {
    el.style.visibility = "visible";
    document.querySelector(".wait-msg")?.remove();
  }, el.dataset.delay * 1000));

  // --- Tâches de l'agent en arrière-plan : la page se recharge quand elles sont finies -
  const jobs = document.querySelector("#jobs[data-running='1']");
  if (jobs) {
    const poll = async () => {
      const res = await fetch(jobs.dataset.url);
      const list = await res.json();
      jobs.innerHTML = list.map((j) =>
        `<div class="card small"><b>${j.label}</b><br>${j.status === "running"
          ? `${T.running} ${j.total > 1 ? `${j.done}/${j.total}` : ""} ${j.message || ""}` : j.message}</div>`).join("");
      if (list.some((j) => j.status === "running")) setTimeout(poll, 2000);
      else setTimeout(() => location.reload(), 1200);
    };
    poll();
  }

  // --- Liens « ouvrir / fermer » : les liens restent en place, le contenu s'ouvre en dessous ------
  document.querySelectorAll(".toggles [data-open]").forEach((btn) => btn.addEventListener("click", () => {
    const panel = document.getElementById(btn.dataset.open);
    const opening = panel.hidden;
    btn.parentElement.querySelectorAll("[data-open]").forEach((b) => {
      b.classList.remove("on");
      const p = document.getElementById(b.dataset.open);
      if (p) p.hidden = true;
    });
    panel.hidden = !opening;
    btn.classList.toggle("on", opening);
    if (opening) panel.querySelector("input, textarea")?.focus();
  }));

  // --- Graphiques (Chart.js, servi localement) ----------------------------------------
  document.querySelectorAll("canvas[data-chart]").forEach((canvas) => {
    const cfg = JSON.parse(canvas.dataset.chart);
    if (canvas.dataset.mini) {
      // Petit graphique d'une seule compétence : pas de légende, axes discrets, survol pour lire les valeurs.
      // Seuls les morceaux qui baissent (rouge) ou montent (vert) nettement sont colorés ; le reste est gris.
      const RUN = { down: "#DC6B4A", up: "#16A34A" };
      cfg.datasets.forEach((ds) => {
        const seg = ds.segments || [];
        ds.segment = { borderColor: (c) => RUN[seg[c.p0DataIndex]], borderWidth: (c) => (seg[c.p0DataIndex] ? 2.2 : undefined) };
      });
      new Chart(canvas, {
        type: "line", data: cfg,
        options: {
          responsive: true, maintainAspectRatio: false, spanGaps: true, animation: false,
          scales: {
            x: { display: false },
            y: { min: 0, max: 100, display: false },
          },
          plugins: { legend: { display: false },
                     tooltip: { displayColors: false, callbacks: { label: (c) => c.parsed.y + T.success } } },
          elements: { line: { tension: 0.25, borderWidth: 1.5 }, point: { radius: 0, hoverRadius: 3 } },
        },
      });
      return;
    }
    new Chart(canvas, {
      type: "line",
      data: cfg,
      options: {
        responsive: true, maintainAspectRatio: false, spanGaps: true, animation: false,
        scales: { y: { min: 0, max: 100, ticks: { callback: (v) => v + T.pct } } },
        plugins: { legend: { position: "bottom" } },
        elements: { line: { tension: 0.3 }, point: { radius: 2 } },
      },
    });
  });
});
