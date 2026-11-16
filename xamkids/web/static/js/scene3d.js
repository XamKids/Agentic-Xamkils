// Scène 3D d'un exercice (Three.js). La scène arrive toute faite du serveur (xamkids/web/scene.py) :
// ce fichier ne fait que la dessiner. L'enfant tourne la scène en glissant, et touche un objet pour le mettre de côté.
// Rien n'indique la réponse : on voit la situation, l'enfant compte et réfléchit.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const PALETTE = { blue: "#2F80ED", green: "#0F7B4F", orange: "#E8694A", purple: "#7B5CD6", red: "#C0392B",
                  yellow: "#E8C14A", teal: "#0E9AA7" };
const COLORS = { mango: "#F2A516", doughnut: "#C98B4E", notebook: "#2F80ED", pen: "#7B5CD6", ruler: "#E8C14A",
                 bread: "#D9A55B", box: "#9AA5A0", cube: "#2F80ED" };
const mat = (color, rough = 0.55) => new THREE.MeshStandardMaterial({ color, roughness: rough });

function label(text, { size = 1.5, bg = "#FFFFFF", fg = "#16382A", border = "#16382A" } = {}) {
  const c = document.createElement("canvas");
  c.width = 256; c.height = 128;
  const g = c.getContext("2d");
  g.fillStyle = bg; g.strokeStyle = border; g.lineWidth = 8;
  g.beginPath(); g.roundRect(8, 8, 240, 112, 26); g.fill(); g.stroke();
  g.fillStyle = fg; g.font = "bold 64px Arial, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(text, 128, 68);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true }));
  s.scale.set(size, size / 2, 1);
  return s;
}

// ---- les objets ------------------------------------------------------------------------------
const BUILD = {
  mango() {
    const g = new THREE.Group();
    const body = new THREE.Mesh(new THREE.SphereGeometry(0.42, 24, 18), mat(COLORS.mango, 0.4));
    body.scale.set(1, 1.15, 0.9); body.position.y = 0.48;
    const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.16, 12, 8), mat("#2E9B4F"));
    leaf.scale.set(1.6, 0.35, 0.8); leaf.position.set(0.1, 1.02, 0); leaf.rotation.z = 0.5;
    g.add(body, leaf); return g;
  },
  doughnut() {
    const g = new THREE.Group();
    const base = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.17, 14, 28), mat(COLORS.doughnut, 0.7));
    const icing = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.15, 14, 28), mat("#E9759B", 0.35));
    icing.position.z = 0.04; icing.scale.set(1, 1, 0.8);
    g.add(base, icing); g.rotation.x = -Math.PI / 2.4; g.position.y = 0.2;
    const w = new THREE.Group(); w.add(g); return w;
  },
  notebook() {
    const g = new THREE.Group();
    const cover = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.1, 0.85), mat(COLORS.notebook, 0.5));
    const pages = new THREE.Mesh(new THREE.BoxGeometry(0.56, 0.07, 0.8), mat("#FFFFFF", 0.9));
    cover.position.y = 0.05; pages.position.set(0.02, 0.13, 0);
    g.add(cover, pages); g.scale.setScalar(1.5); return g;
  },
  pen() {
    const g = new THREE.Group();
    const body = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.95, 14), mat(COLORS.pen, 0.4));
    const tip = new THREE.Mesh(new THREE.ConeGeometry(0.07, 0.2, 14), mat("#22313A"));
    body.rotation.z = Math.PI / 2; tip.rotation.z = Math.PI / 2; tip.position.x = 0.57;
    g.add(body, tip); g.position.y = 0.08; g.rotation.y = 0.5;
    const w = new THREE.Group(); w.add(g); return w;
  },
  ruler() {
    const g = new THREE.Group();
    const bar = new THREE.Mesh(new THREE.BoxGeometry(1.05, 0.05, 0.2), mat(COLORS.ruler, 0.45));
    bar.position.y = 0.03; g.add(bar);
    for (let i = -4; i <= 4; i++) {
      const tick = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.06, i % 2 ? 0.06 : 0.1), mat("#22313A"));
      tick.position.set(i * 0.12, 0.06, 0.04); g.add(tick);
    }
    g.rotation.y = 0.35; return g;
  },
  bread() {
    const g = new THREE.Group();
    const loaf = new THREE.Mesh(new THREE.SphereGeometry(0.4, 22, 16), mat(COLORS.bread, 0.8));
    loaf.scale.set(1.45, 0.62, 0.7); loaf.position.y = 0.26;
    g.add(loaf);
    for (let i = -1; i <= 1; i++) {
      const cut = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.04, 0.3), mat("#B07A38"));
      cut.position.set(i * 0.26, 0.5, 0); cut.rotation.z = 0.35; g.add(cut);
    }
    return g;
  },
  marble(color) {
    const m = new THREE.Mesh(new THREE.SphereGeometry(0.3, 24, 18), mat(color, 0.15));
    m.position.y = 0.3; const g = new THREE.Group(); g.add(m); return g;
  },
  cube(color) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.5, 0.5), mat(color, 0.45));
    m.position.y = 0.25; const g = new THREE.Group(); g.add(m); return g;
  },
  rod(color) {
    const g = new THREE.Group();
    const m = new THREE.Mesh(new THREE.BoxGeometry(0.34, 2.4, 0.34), mat(color, 0.45));
    m.position.y = 1.2; g.add(m);
    for (let i = 1; i < 10; i++) {
      const line = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.015, 0.36), mat("#FFFFFF"));
      line.position.y = i * 0.24; g.add(line);
    }
    return g;
  },
  gift(color) {
    const g = new THREE.Group();
    const b = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.9, 1.2), mat(color, 0.5)); b.position.y = 0.45;
    const r1 = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.92, 1.22), mat("#FFE08A")); r1.position.y = 0.46;
    const r2 = new THREE.Mesh(new THREE.BoxGeometry(1.22, 0.92, 0.2), mat("#FFE08A")); r2.position.y = 0.46;
    g.add(b, r1, r2); return g;
  },
  banknote(color) {
    const g = new THREE.Group();
    const m = new THREE.Mesh(new THREE.BoxGeometry(1.9, 0.07, 1.0), mat("#BFE3C8", 0.7)); m.position.y = 0.04;
    const f = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.075, 0.6), mat(color, 0.6)); f.position.y = 0.045;
    g.add(m, f); return g;
  },
  thousand(color) {
    const g = new THREE.Group();
    const m = new THREE.Mesh(new THREE.BoxGeometry(2.4, 2.4, 2.4), mat(color, 0.45));
    m.position.y = 1.2; g.add(m);
    for (let i = 1; i < 10; i++) {
      const l = new THREE.Mesh(new THREE.BoxGeometry(2.42, 0.012, 2.42), mat("#FFFFFF")); l.position.y = i * 0.24; g.add(l);
    }
    return g;
  },
  flat(color) {
    const g = new THREE.Group();
    const m = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.18, 2.4), mat(color, 0.45));
    m.position.y = 0.09; g.add(m);
    for (let i = 1; i < 10; i++) {
      for (const [w, d, x, z] of [[2.4, 0.012, 0, -1.2 + i * 0.24], [0.012, 2.4, -1.2 + i * 0.24, 0]]) {
        const l = new THREE.Mesh(new THREE.BoxGeometry(w, 0.2, d), mat("#FFFFFF")); l.position.set(x, 0.09, z); g.add(l);
      }
    }
    return g;
  },
};

function make(kind, color) {
  const o = (BUILD[kind] || BUILD.cube)(color);
  o.userData.item = true;
  return o;
}

// ---- la scène conçue par l'agent : des groupes d'objets, de gauche à droite --------------------
const LAYOUT = {            // colonnes, pas, hauteur de l'étiquette
  rod: { cols: 9, step: 0.5, tagY: 3.1 }, flat: { cols: 9, step: 0.5, tagY: 2.2 }, thousand: { cols: 9, step: 0.5, tagY: 3.0 },
  cube: { cols: 3, step: 0.62, tagY: 1.6 }, marble: { cols: 4, step: 0.8, tagY: 1.6 }, banknote: { cols: 1, step: 1.2, tagY: 1.4 },
  gift: { cols: 2, step: 1.5, tagY: 1.9 },
};

function compose({ groups }) {
  const out = [];
  let x = 0;
  for (const g of groups) {
    const lay = LAYOUT[g.item] || { cols: 4, step: 1.15, tagY: 1.9 };
    const color = PALETTE[g.color] || PALETTE.blue;
    const tint = ["mango", "doughnut", "notebook", "pen", "ruler", "bread"].includes(g.item) ? COLORS[g.item] : color;
    const cols = Math.min(g.count, lay.cols);
    const items = Array.from({ length: g.count }, () => make(g.item, tint));
    items.forEach((o, i) => {
      if (g.item === "flat" || g.item === "thousand") o.position.set(x + i * lay.step, i * (g.item === "flat" ? 0.2 : 0.3), i * 0.15);
      else o.position.set(x + (i % cols) * lay.step, 0, Math.floor(i / cols) * lay.step);
    });
    out.push(...items);
    const width = Math.max(cols, 1) * lay.step;
    if (g.tag) {
      const t = label(g.tag, { size: 1.7 });
      t.position.set(x + width / 2 - lay.step / 2, lay.tagY, 0); t.userData.plain = true;
      out.push(t);
    }
    x += width + 1.6;
  }
  const shift = (x - 1.6) / 2;                      // la scène est centrée
  out.forEach((o) => { o.position.x -= shift; });
  return out;
}

// ---- le décor, la caméra et les touchers -----------------------------------------------------
export function mount(host, spec) {
  if (!spec || !Array.isArray(spec.groups)) return false;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  host.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
  scene.add(new THREE.HemisphereLight("#FFFFFF", "#D8CFB8", 1.1));
  const sun = new THREE.DirectionalLight("#FFFFFF", 1.7);
  sun.position.set(5, 9, 6); sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  Object.assign(sun.shadow.camera, { left: -10, right: 10, top: 10, bottom: -10 });
  scene.add(sun);
  const table = new THREE.Mesh(new THREE.CylinderGeometry(60, 60, 0.2, 64), mat("#F7F0E0", 0.95));
  table.position.y = -0.1; table.receiveShadow = true; scene.add(table);

  const objects = compose(spec);
  scene.updateMatrixWorld(true);
  const box = new THREE.Box3();
  objects.forEach((o, i) => {
    o.traverse((m) => { if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; } });
    o.userData.rest = o.position.y;
    o.userData.t0 = i * 0.045;
    scene.add(o);
    scene.updateMatrixWorld(true);
    if (!o.isSprite) box.expandByObject(o);
  });
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const span = Math.max(size.x, size.z * 1.9, size.y * 1.8, 5) * 0.88;
  camera.position.set(center.x, span * 0.6, center.z + span * 0.85);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(center.x, 0.5, center.z);
  Object.assign(controls, { enablePan: false, enableDamping: true, minDistance: span * 0.5, maxDistance: span * 1.6,
                            maxPolarAngle: Math.PI * 0.46 });

  const resize = () => {
    const w = host.clientWidth, h = host.clientHeight;
    renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(host);
  resize();

  // Toucher un objet le met de côté (il se soulève et devient transparent) ; un deuxième toucher le remet.
  const ray = new THREE.Raycaster(), pt = new THREE.Vector2();
  let down = null;
  renderer.domElement.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener("pointerup", (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 6) return;
    const r = renderer.domElement.getBoundingClientRect();
    pt.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(pt, camera);
    const hit = ray.intersectObjects(objects.filter((o) => !o.userData.plain), true)[0];
    if (!hit) return;
    let o = hit.object;
    while (o.parent && !o.userData.item) o = o.parent;
    o.userData.aside = !o.userData.aside;
  });

  const clock = new THREE.Clock();
  (function loop() {
    const t = clock.getElapsedTime();
    for (const o of objects) {
      const k = Math.min(Math.max((t - o.userData.t0) / 0.7, 0), 1);
      const drop = (1 - k) ** 2 * 5;                                   // arrive du haut
      const lift = o.userData.aside ? 1.4 : 0;
      o.userData.lift = (o.userData.lift ?? 0) + (lift - (o.userData.lift ?? 0)) * 0.18;
      o.position.y = o.userData.rest + drop + o.userData.lift;
      if (o.userData.item) {
        o.traverse((m) => { if (m.isMesh) { m.material.transparent = true; m.material.opacity = o.userData.aside ? 0.3 : 1; } });
      }
    }
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(loop);
  })();
  return true;
}

// L'agent conçoit la scène pendant que l'élève lit la question : on attend qu'elle soit prête, sans bloquer l'exercice.
async function load(host, tries = 0) {
  try {
    const r = await (await fetch(host.dataset.src, { cache: "no-store" })).json();
    if (!r.ready) { if (tries < 40) setTimeout(() => load(host, tries + 1), 1500); return; }
    if (!r.scene) return;
    host.hidden = false;
    if (host.nextElementSibling) host.nextElementSibling.hidden = false;
    if (!mount(host, r.scene)) host.hidden = true;
  } catch (err) {
    host.hidden = true;                // sans 3D possible, l'exercice reste complet
    console.warn("3D indisponible", err);
  }
}
for (const host of document.querySelectorAll("[data-src]")) load(host);
for (const host of document.querySelectorAll("[data-scene]")) {   // aperçu : scène donnée directement
  try { host.hidden = !mount(host, JSON.parse(host.dataset.scene)); } catch (err) { host.hidden = true; }
}
