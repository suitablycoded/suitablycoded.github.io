// 3D headers for the project pages. One scene per project, chosen by data-scene on the
// header: route-scheduler (vans drive routes to job pins), site-watch (a scan finds a change
// on a web page and sends an alert), contact-cleaner (messy rows pass through a cleaning gate
// and line up tidy, with a duplicate merging).
// Progressive: without WebGL or the module the header is plain. With "reduce motion" each
// scene shows its finished state as one still frame.
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.min.js";

const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const canvas = document.getElementById("hero-3d");
const hero = canvas && canvas.closest("[data-scene]");

const css = (n, f) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || f;
const ACCENT = css("--accent", "#5cc9b5");
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const ease = (x) => 1 - Math.pow(1 - clamp01(x), 3);
const span = (t, a, b) => clamp01((t - a) / (b - a));

function rr(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}

function canvasTex(w, h, draw) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return t;
}

// A dark rounded label, used for counters and alerts.
function label(text, { w = 560, h = 96, size = 40, scale = 3.2 } = {}) {
  // Widen the card to fit the text, so long labels are never cut off.
  const m = document.createElement("canvas").getContext("2d");
  m.font = `bold ${size}px system-ui, Segoe UI, sans-serif`;
  const need = Math.ceil(m.measureText(text).width) + 72;
  if (need > w) { scale *= need / w; w = need; }
  const tex = canvasTex(w, h, (g) => {
    g.fillStyle = "rgba(13,17,23,0.92)"; rr(g, 4, 4, w - 8, h - 8, 22); g.fill();
    g.strokeStyle = ACCENT; g.lineWidth = 4; g.stroke();
    g.fillStyle = "#e6edf3"; g.font = `bold ${size}px system-ui, Segoe UI, sans-serif`;
    g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(text, w / 2, h / 2 + 2);
  });
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, opacity: 0 }));
  s.scale.set(scale, scale * h / w, 1);
  return s;
}

// ------------------------------------------------------------------ route scheduler

function routeScene(root, data) {
  // A real street map of Harrogate (OpenStreetMap), with four vans driving routes that follow
  // real roads (planned once with OSRM and saved with the site).
  const CYCLE = 13;
  const BW = 8.0, BD = 6.0;                       // board size, 4:3 like the map image
  const board = new THREE.Group();
  board.rotation.x = 0.9;                         // tip the map towards the viewer
  board.position.y = -0.15;
  root.add(board);
  const mapTex = new THREE.TextureLoader().load(new URL("img/harrogate-map.jpg", import.meta.url).href);
  mapTex.colorSpace = THREE.SRGBColorSpace; mapTex.anisotropy = 8;
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(BW, BD),
    new THREE.MeshBasicMaterial({ map: mapTex, toneMapped: false }));
  ground.rotation.x = -Math.PI / 2;
  board.add(ground);
  const edge = new THREE.Mesh(new THREE.BoxGeometry(BW + 0.12, 0.12, BD + 0.12),
    new THREE.MeshStandardMaterial({ color: 0x1c2024 }));
  edge.position.y = -0.07;
  board.add(edge);

  const at = ([x, y], h = 0) => new THREE.Vector3((Math.min(1, Math.max(0, x)) - 0.5) * BW, h, (Math.min(1, Math.max(0, y)) - 0.5) * BD);

  const depot = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.26, 0.34),
    new THREE.MeshStandardMaterial({ color: 0x1b1e1d }));
  depot.position.copy(at(data.depot, 0.13));
  board.add(depot);

  const tints = [0x0a8f7a, 0x1d6fd6, 0xe07b00, 0x8a4fd6];
  const pinGeo = new THREE.ConeGeometry(0.12, 0.38, 16);
  pinGeo.rotateX(Math.PI); pinGeo.translate(0, 0.19, 0);
  const pins = [], routes = [];
  data.routes.forEach((r, i) => {
    const tint = tints[i % tints.length];
    const mat = new THREE.MeshStandardMaterial({ color: tint, emissive: tint, emissiveIntensity: 0.25 });
    r.pins.forEach((pt, k) => {
      const pin = new THREE.Mesh(pinGeo, mat);
      pin.position.copy(at(pt));
      pin.userData.delay = (i * 3 + k) * 0.12;
      pin.scale.setScalar(0.001);
      board.add(pin); pins.push(pin);
    });
    const pts = r.line.map((p) => at(p, 0.03));
    // cumulative length, so vans move at a steady speed
    const cum = [0];
    for (let k = 1; k < pts.length; k++) cum.push(cum[k - 1] + pts[k].distanceTo(pts[k - 1]));
    // A solid tube along the road (plain lines draw only 1px wide). Revealed segment by
    // segment as the van drives.
    const path = new THREE.CurvePath();
    for (let k = 1; k < pts.length; k++) path.add(new THREE.LineCurve3(pts[k - 1], pts[k]));
    const RAD = 6;
    const geo = new THREE.TubeGeometry(path, pts.length - 1, 0.035, RAD, false);
    geo.setDrawRange(0, 0);
    geo.userData.perSeg = RAD * 6;
    board.add(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: tint, emissive: tint, emissiveIntensity: 0.3 })));
    const van = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.16, 0.16),
      new THREE.MeshStandardMaterial({ color: tint, emissive: tint, emissiveIntensity: 0.4 }));
    van.visible = false;
    board.add(van);
    routes.push({ pts, cum, total: cum[cum.length - 1], geo, van, offset: i * 0.3 });
  });
  const pointAt = (r, p) => {
    const d = p * r.total;
    let k = r.cum.findIndex((c) => c >= d);
    if (k <= 0) return { pos: r.pts[0].clone(), idx: 1 };
    const f = (d - r.cum[k - 1]) / Math.max(1e-6, r.cum[k] - r.cum[k - 1]);
    return { pos: r.pts[k - 1].clone().lerp(r.pts[k], f), idx: k };
  };

  const jobs = data.routes.reduce((n, r) => n + r.pins.length, 0);
  const km = data.routes.reduce((n, r) => n + r.km, 0).toFixed(1);
  const counter = label(`${jobs} jobs · ${data.routes.length} vans · ${km} km`, { scale: 3.6 });
  counter.position.set(0, 2.7, 0.6);
  root.add(counter);

  return (t) => {
    const c = t % CYCLE;
    const out = 1 - span(c, CYCLE - 0.8, CYCLE);
    pins.forEach((p) => p.scale.setScalar(Math.max(0.001, ease(span(c, 0.3 + p.userData.delay, 0.8 + p.userData.delay)) * out)));
    routes.forEach((r) => {
      const p = span(c, 2.4 + r.offset, 9.0 + r.offset);    // steady drive, no easing
      const { pos, idx } = pointAt(r, p);
      r.geo.setDrawRange(0, out > 0 ? idx * r.geo.userData.perSeg : 0);
      r.van.visible = p > 0 && p < 1 && out > 0;
      if (r.van.visible) {
        r.van.position.copy(pos).setY(0.1);
        const ahead = pointAt(r, Math.min(1, p + 0.01)).pos.setY(0.1);
        if (ahead.distanceTo(r.van.position) > 1e-4) r.van.lookAt(ahead);
      }
    });
    counter.material.opacity = span(c, 10.4, 11.0) * out;
  };
}

// ------------------------------------------------------------------ site watch

function siteScene(root) {
  const CYCLE = 10;
  const PW = 5.6, PH = 3.5;
  const page = (g, w, h) => {
    g.fillStyle = "#ffffff"; g.fillRect(0, 0, w, h);
    g.fillStyle = "#e9ecef"; g.fillRect(0, 0, w, 52);
    ["#ff5f57", "#febc2e", "#28c840"].forEach((c, i) => { g.fillStyle = c; g.beginPath(); g.arc(26 + i * 22, 26, 7, 0, 7); g.fill(); });
    g.fillStyle = "#fff"; rr(g, 100, 12, 600, 28, 14); g.fill();
    g.fillStyle = "#6c757d"; g.font = "18px system-ui, sans-serif"; g.fillText("shop.example/plans", 118, 32);
    g.fillStyle = "#1b1e1d"; g.font = "bold 40px system-ui, sans-serif"; g.fillText("Plans and pricing", 48, 120);
    g.fillStyle = "#dee2e6";
    for (let i = 0; i < 4; i++) g.fillRect(48, 150 + i * 26, 520 - i * 70, 12);
    for (let i = 0; i < 3; i++) {
      const x = 48 + i * 330;
      g.strokeStyle = "#dee2e6"; g.lineWidth = 3; rr(g, x, 280, 300, 230, 14); g.stroke();
      g.fillStyle = "#1b1e1d"; g.font = "bold 28px system-ui, sans-serif"; g.fillText(["Basic", "Team", "Pro"][i], x + 24, 326);
      g.fillStyle = "#1b1e1d"; g.font = "bold 46px system-ui, sans-serif"; g.fillText(["£19", "£49", "£99"][i], x + 24, 392);
      g.fillStyle = "#dee2e6"; g.fillRect(x + 24, 420, 200, 10); g.fillRect(x + 24, 446, 160, 10); g.fillRect(x + 24, 472, 220, 10);
    }
  };
  const W = 1024, H = 640;
  const browser = new THREE.Mesh(new THREE.PlaneGeometry(PW, PH),
    new THREE.MeshBasicMaterial({ map: canvasTex(W, H, page), toneMapped: false }));
  const frame = new THREE.Mesh(new THREE.BoxGeometry(PW + 0.16, PH + 0.16, 0.12),
    new THREE.MeshStandardMaterial({ color: 0x1c2024, metalness: 0.5, roughness: 0.4 }));
  frame.position.z = -0.07;
  const win = new THREE.Group();
  win.add(frame, browser);
  win.position.x = -0.8;
  root.add(win);

  // the region of the page that changes: the Team price card
  const rx = 378 / W, ry = 280 / H, rw = 300 / W, rh = 230 / H;
  const cx = -PW / 2 + (rx + rw / 2) * PW, cy = PH / 2 - (ry + rh / 2) * PH;
  const diffTex = canvasTex(300, 230, (g) => {
    g.fillStyle = "#fff"; rr(g, 0, 0, 300, 230, 14); g.fill();
    g.strokeStyle = "#d63939"; g.lineWidth = 6; rr(g, 3, 3, 294, 224, 14); g.stroke();
    g.fillStyle = "#1b1e1d"; g.font = "bold 28px system-ui, sans-serif"; g.fillText("Team", 24, 46);
    g.fillStyle = "#d63939"; g.font = "bold 42px system-ui, sans-serif"; g.fillText("£49", 24, 108);
    g.fillRect(22, 92, 82, 5);
    g.fillStyle = "#1f8a4c"; g.font = "bold 54px system-ui, sans-serif"; g.fillText("£39", 130, 112);
    g.fillStyle = "#6c757d"; g.font = "20px system-ui, sans-serif"; g.fillText("Price changed", 24, 170);
    g.fillText("13 Nov, 09:14", 24, 200);
  });
  const diff = new THREE.Mesh(new THREE.PlaneGeometry(rw * PW, rh * PH),
    new THREE.MeshBasicMaterial({ map: diffTex, transparent: true, opacity: 0, toneMapped: false }));
  diff.position.set(cx, cy, 0.02);
  win.add(diff);

  const beam = new THREE.Mesh(new THREE.PlaneGeometry(PW + 0.4, 0.07),
    new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.9 }));
  const beamGlow = new THREE.Mesh(new THREE.PlaneGeometry(PW + 0.4, 0.5),
    new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.15 }));
  beam.add(beamGlow); beam.position.z = 0.05;
  win.add(beam);

  const alert = label("Change found: Team price", { scale: 3 });
  root.add(alert);
  alert.userData.base = alert.scale.clone();
  const mail = label("✉  Alert sent", { w: 360, h: 96, scale: 1.8 });
  mail.position.set(3.7, 2.1, 0.4);
  mail.userData.base = mail.scale.clone();
  root.add(mail);
  const start = new THREE.Vector3(), end = mail.position.clone();

  return (t) => {
    const c = t % CYCLE;
    const out = 1 - span(c, CYCLE - 0.6, CYCLE);
    const sweep = span(c, 0.4, 4.4);
    beam.position.y = PH / 2 - sweep * PH;
    beam.visible = sweep > 0 && sweep < 1;
    const hit = span(c, 0.4 + 4 * ((ry + rh / 2)), 0.4 + 4 * ((ry + rh / 2)) + 0.4);
    const lift = ease(span(c, 2.9, 4.0));
    diff.material.opacity = hit * out;
    diff.position.z = 0.02 + lift * 1.3;
    diff.scale.setScalar(1 + lift * 0.45);
    win.updateMatrixWorld();
    diff.getWorldPosition(start);
    const fly = ease(span(c, 4.6, 6.2));
    alert.position.copy(start).lerp(end, fly).add(new THREE.Vector3(0, 0.6 * (1 - fly), 0.3));
    alert.material.opacity = span(c, 4.3, 4.7) * (1 - span(fly, 0.7, 0.95)) * out;
    const k = 1 - fly * 0.6, base = alert.userData.base;
    alert.scale.set(base.x * k, base.y * k, 1);
    mail.material.opacity = span(c, 5.9, 6.3) * out;
    const pop = 1 + 0.2 * Math.sin(Math.PI * span(c, 6.0, 6.6));
    mail.scale.set(mail.userData.base.x * pop, mail.userData.base.y * pop, 1);
  };
}

// ------------------------------------------------------------------ contact cleaner

function cleanerScene(root) {
  const CYCLE = 11;
  const ROWS = [
    ["  mary SMITH ,07700900123 ", "Mary Smith · 07700 900123", 0],
    ["JOHN o'brien | +447700900456", "John O'Brien · 07700 900456", 1],
    ["anna kowalska;0161-496-0000", "Anna Kowalska · 0161 496 0000", 2],
    ["Mary Smith, 07700 900 123", "Mary Smith · 07700 900123", 0],   // duplicate of row 1
    ["sam lee  ,  (0113)4960001", "Sam Lee · 0113 496 0001", 3],
    ["PRIYA PATEL,7700900789", "Priya Patel · 07700 900789", 4],
    ["tom   o NEILL;;0207 9460002", "Tom O'Neill · 020 7946 0002", 5],
  ];
  const RW = 2.9, RH = 0.36;
  const tex = (text, messy) => canvasTex(640, 80, (g) => {
    g.fillStyle = messy ? "#2a1f1f" : "#ffffff"; rr(g, 2, 2, 636, 76, 12); g.fill();
    g.strokeStyle = messy ? "#d6393999" : ACCENT; g.lineWidth = 4; g.stroke();
    g.fillStyle = messy ? "#ffb4b4" : "#1b1e1d";
    g.font = `${messy ? "" : "bold "}30px ${messy ? "Consolas, monospace" : "system-ui, sans-serif"}`;
    g.textBaseline = "middle"; g.fillText(text, 22, 42);
    if (!messy) { g.fillStyle = "#1f8a4c"; g.font = "bold 32px system-ui"; g.fillText("✓", 594, 42); }
  });
  const geo = new THREE.PlaneGeometry(RW, RH);
  const GATE_X = 0;
  const rows = ROWS.map(([m, cl, slot], i) => {
    const mat = new THREE.MeshBasicMaterial({ map: tex(m, true), transparent: true, toneMapped: false });
    const mesh = new THREE.Mesh(geo, mat);
    root.add(mesh);
    const seed = Math.sin(i * 12.9898) * 43758.5453;
    const r = seed - Math.floor(seed);
    return {
      mesh, messy: mat.map, clean: tex(cl, false), slot, dup: i === 3,
      pile: new THREE.Vector3(-3.0 + r * 0.8, 1.9 - i * 0.62 + (r - 0.5) * 0.3, -0.4 + r * 0.6),
      spin: new THREE.Euler((r - 0.5) * 0.6, (r - 0.5) * 0.9, (r - 0.5) * 0.5),
      leave: 1.6 + i * 0.75,
    };
  });

  // the cleaning gate
  const gate = new THREE.Group();
  const gateMat = new THREE.MeshStandardMaterial({ color: new THREE.Color(ACCENT), emissive: new THREE.Color(ACCENT), emissiveIntensity: 0.6 });
  // A light curtain: a glowing bar top and bottom with a translucent sheet between them.
  const top = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.14, 1.1), gateMat); top.position.y = 2.0;
  const bot = top.clone(); bot.position.y = -2.0;
  const sheet = new THREE.Mesh(new THREE.PlaneGeometry(1.1, 4.0),
    new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.12, side: THREE.DoubleSide, depthWrite: false }));
  sheet.rotation.y = Math.PI / 2;
  const line = new THREE.Mesh(new THREE.PlaneGeometry(0.05, 4.0),
    new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.9 }));
  line.position.z = 0.56;
  gate.add(top, bot, sheet, line);
  gate.position.x = GATE_X;
  gate.rotation.y = 0.35;
  root.add(gate);

  const counter = label("600 rows in → 515 clean, 52 merged", { scale: 3.8 });
  counter.position.set(2.2, 2.55, 0.4);
  root.add(counter);

  const tmp = new THREE.Vector3();
  return (t) => {
    const c = t % CYCLE;
    const out = 1 - span(c, CYCLE - 0.6, CYCLE);
    sheet.material.opacity = 0.12;
    rows.forEach((r, i) => {
      const target = new THREE.Vector3(2.3, 1.7 - r.slot * 0.5, 0);
      const p = span(c, r.leave, r.leave + 1.5);
      const toGate = ease(span(p, 0, 0.5)), toSlot = ease(span(p, 0.5, 1));
      const gatePos = new THREE.Vector3(GATE_X, target.y, 0);
      if (p <= 0) {
        // messy pile, drifting
        tmp.copy(r.pile).add(new THREE.Vector3(0, Math.sin(t * 1.3 + i) * 0.05, 0));
        r.mesh.position.copy(tmp);
        r.mesh.rotation.set(r.spin.x + Math.sin(t + i) * 0.08, r.spin.y, r.spin.z + Math.sin(t * 0.7 + i) * 0.06);
      } else if (p < 0.5) {
        r.mesh.position.copy(r.pile).lerp(gatePos, toGate);
        r.mesh.rotation.set(r.spin.x * (1 - toGate), r.spin.y * (1 - toGate), r.spin.z * (1 - toGate));
      } else {
        r.mesh.position.copy(gatePos).lerp(target, toSlot);
        r.mesh.rotation.set(0, 0, 0);
      }
      const cleaned = p >= 0.5;
      r.mesh.material.map = cleaned ? r.clean : r.messy;
      if (Math.abs(p - 0.5) < 0.06) sheet.material.opacity = 0.45;   // flash as a row passes
      let a = 1;
      if (r.dup) a = 1 - span(p, 0.85, 1);                           // merges into its twin
      r.mesh.material.opacity = a * out;
    });
    counter.material.opacity = span(c, 7.4, 8.1) * out;
  };
}

// ------------------------------------------------------------------ shared stage

async function start() {
  if (!canvas || !hero) return;
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true }); }
  catch (err) { return; }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
  camera.position.set(0, 0, 11);
  scene.add(new THREE.AmbientLight(0xffffff, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 2);
  key.position.set(3, 6, 6);
  scene.add(key);

  const root = new THREE.Group();
  scene.add(root);
  const kind = hero.dataset.scene;
  const update = { "route-scheduler": routeScene, "site-watch": siteScene, "contact-cleaner": cleanerScene }[kind];
  if (!update) return;
  let data = null;
  if (kind === "route-scheduler") {
    try { data = await (await fetch(new URL("harrogate-routes.json", import.meta.url))).json(); }
    catch (err) { return; }
  }
  const tick = update(root, data);

  // Fit the scene (about 9.6 units wide) into the space right of the text, centred in its
  // own view so it never stretches on wide screens.
  const column = hero.querySelector(".wrap");
  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    let px = w / 2, s = 0.6;
    if (w > 900 && column) {
      const r = column.getBoundingClientRect(), cr = canvas.getBoundingClientRect();
      const unit = h / 6.94;
      const textRight = r.left - cr.left + 38 * 16 + 24;
      const space = w - textRight - 16;
      s = Math.max(0.4, Math.min(1, space / (9.8 * unit)));
      px = textRight + 4.9 * unit * s;
    }
    const fullW = 2 * Math.max(px, w - px);
    camera.aspect = fullW / h;
    camera.setViewOffset(fullW, h, fullW / 2 - px, 0, w, h);
    camera.updateProjectionMatrix();
    root.scale.setScalar(s);
    hero.style.setProperty("--orb-x", `${px}px`);
  }
  new ResizeObserver(resize).observe(canvas);
  resize();

  let mx = 0, my = 0;
  window.addEventListener("pointermove", (ev) => {
    mx = (ev.clientX / window.innerWidth - 0.5) * 2;
    my = (ev.clientY / window.innerHeight - 0.5) * 2;
  }, { passive: true });
  let visible = true;
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(canvas);

  const clock = new THREE.Clock();
  const frame = (t) => {
    root.rotation.y = -0.18 + Math.sin(t * 0.3) * 0.05 + mx * 0.12;
    root.rotation.x = Math.sin(t * 0.25) * 0.02 + my * 0.05;
    tick(t);
    renderer.render(scene, camera);
  };
  canvas.classList.add("ready");
  const FINAL = { "route-scheduler": 11.5, "site-watch": 6.8, "contact-cleaner": 9 }[kind];
  // Still mode draws once, then again when images (the map) finish loading.
  if (still) { THREE.DefaultLoadingManager.onLoad = () => frame(FINAL); frame(FINAL); return; }
  renderer.setAnimationLoop(() => { if (visible) frame(clock.getElapsedTime()); });
}

start();
