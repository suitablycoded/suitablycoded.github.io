// 3D hero for the home page: a monitor where code scrolls up the screen, then the code
// "builds" into a finished app (a dashboard), holds, and starts again. Plus a gentle 3D
// tilt on the project cards.
// Progressive: if WebGL or the module fails to load, the page looks normal without it.
// Respects "reduce motion": the monitor shows the finished app as one still frame and the
// cards do not tilt.
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.min.js";

const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const canvas = document.getElementById("hero-3d");

function cssColour(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

// ------------------------------------------------------------------ screen content

const CODE = [
  ["k", "import "], ["t", "csv, datetime\n"],
  ["k", "from "], ["t", "pathlib "], ["k", "import "], ["t", "Path\n"],
  ["t", "\n"],
  ["k", "def "], ["f", "load_jobs"], ["t", "(path):\n"],
  ["t", "    rows = csv.DictReader(Path(path).open())\n"],
  ["t", "    "], ["k", "return "], ["t", "[clean(r) "], ["k", "for "], ["t", "r "], ["k", "in "], ["t", "rows]\n"],
  ["t", "\n"],
  ["k", "def "], ["f", "clean"], ["t", "(row):\n"],
  ["t", "    row["], ["s", "\"name\""], ["t", "] = row["], ["s", "\"name\""], ["t", "].strip().title()\n"],
  ["t", "    row["], ["s", "\"phone\""], ["t", "] = uk_phone(row["], ["s", "\"phone\""], ["t", "])\n"],
  ["t", "    "], ["k", "return "], ["t", "row\n"],
  ["t", "\n"],
  ["k", "def "], ["f", "schedule"], ["t", "(jobs, team):\n"],
  ["c", "    # urgent and tight windows first\n"],
  ["t", "    jobs.sort(key="], ["k", "lambda "], ["t", "j: (j.window, -j.priority))\n"],
  ["t", "    "], ["k", "for "], ["t", "job "], ["k", "in "], ["t", "jobs:\n"],
  ["t", "        tech = cheapest_fit(job, team)\n"],
  ["t", "        "], ["k", "if "], ["t", "tech: tech.route.insert(job)\n"],
  ["t", "    "], ["k", "return "], ["t", "team\n"],
  ["t", "\n"],
  ["k", "def "], ["f", "report"], ["t", "(team):\n"],
  ["t", "    total = "], ["f", "sum"], ["t", "(t.route.km "], ["k", "for "], ["t", "t "], ["k", "in "], ["t", "team)\n"],
  ["t", "    "], ["f", "print"], ["t", "("], ["s", "f\"Saved {saved:.0f} km today\""], ["t", ")\n"],
  ["t", "\n"],
  ["k", "if "], ["t", "__name__ == "], ["s", "\"__main__\""], ["t", ":\n"],
  ["t", "    team = schedule(load_jobs("], ["s", "\"jobs.csv\""], ["t", "), TEAM)\n"],
  ["t", "    report(team)\n"],
];

// Split the token list into lines of [kind, text] pieces.
const LINES = (() => {
  const out = [[]];
  for (const [kind, text] of CODE) {
    const parts = text.split("\n");
    parts.forEach((p, i) => {
      if (p) out[out.length - 1].push([kind, p]);
      if (i < parts.length - 1) out.push([]);
    });
  }
  return out;
})();

const W = 1024, H = 640;           // screen texture size (16:10)
const LINE_H = 30, PAD = 40;

function drawCode(ctx, scroll, typed, col) {
  ctx.fillStyle = "#0d1117";
  ctx.fillRect(0, 0, W, H);
  // editor chrome
  ctx.fillStyle = "#161b22";
  ctx.fillRect(0, 0, W, 34);
  ["#ff5f57", "#febc2e", "#28c840"].forEach((c, i) => {
    ctx.fillStyle = c; ctx.beginPath(); ctx.arc(22 + i * 22, 17, 6, 0, 7); ctx.fill();
  });
  ctx.fillStyle = "#8b949e"; ctx.font = "16px Consolas, ui-monospace, monospace";
  ctx.fillText("scheduler.py", 100, 23);

  const colours = { k: "#ff7b72", f: "#d2a8ff", s: "#a5d6ff", c: "#8b949e", t: "#e6edf3" };
  ctx.font = "20px Consolas, ui-monospace, monospace";
  ctx.save();
  ctx.beginPath(); ctx.rect(0, 34, W, H - 34); ctx.clip();
  let chars = 0;
  for (let i = 0; i < LINES.length; i++) {
    const y = 34 + PAD + i * LINE_H - scroll;
    if (y < 0 || y > H + LINE_H) { chars += LINES[i].reduce((n, p) => n + p[1].length, 0); continue; }
    ctx.fillStyle = "#484f58";
    ctx.fillText(String(i + 1).padStart(2, " "), 16, y);
    let x = 70;
    for (const [kind, text] of LINES[i]) {
      const show = Math.max(0, Math.min(text.length, typed - chars));
      chars += text.length;
      if (!show) continue;
      ctx.fillStyle = colours[kind];
      ctx.fillText(text.slice(0, show), x, y);
      x += ctx.measureText(text.slice(0, show)).width;
      if (show < text.length) { // caret at the typing point
        ctx.fillStyle = col; ctx.fillRect(x + 2, y - 18, 10, 22);
      }
    }
  }
  ctx.restore();
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

// The finished product: a small business dashboard. `grow` (0..1) animates it in.
function drawApp(ctx, grow, col) {
  const e = 1 - Math.pow(1 - Math.min(1, grow), 3);
  ctx.fillStyle = "#f6f7f9"; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, W, 64);
  ctx.fillStyle = "#e3e6ea"; ctx.fillRect(0, 64, W, 1);
  ctx.fillStyle = col; roundRect(ctx, 28, 18, 28, 28, 7); ctx.fill();
  ctx.fillStyle = "#1b1e1d"; ctx.font = "bold 24px system-ui, Segoe UI, sans-serif";
  ctx.fillText("Today's jobs", 70, 41);
  ctx.fillStyle = col; roundRect(ctx, W - 190, 16, 160, 34, 8); ctx.fill();
  ctx.fillStyle = "#fff"; ctx.font = "bold 16px system-ui, Segoe UI, sans-serif";
  ctx.fillText("Auto-schedule", W - 168, 39);

  // stat tiles
  const stats = [["Jobs booked", "38"], ["Travel saved", "131 km"], ["On time", "100%"]];
  stats.forEach(([label, value], i) => {
    const x = 28 + i * 330, y = 90 + (1 - e) * 30;
    ctx.globalAlpha = e;
    ctx.fillStyle = "#fff"; roundRect(ctx, x, y, 310, 110, 12); ctx.fill();
    ctx.strokeStyle = "#e3e6ea"; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = "#4d5452"; ctx.font = "18px system-ui, Segoe UI, sans-serif";
    ctx.fillText(label, x + 22, y + 38);
    ctx.fillStyle = "#1b1e1d"; ctx.font = "bold 40px system-ui, Segoe UI, sans-serif";
    ctx.fillText(value, x + 22, y + 86);
  });
  ctx.globalAlpha = 1;

  // bar chart
  ctx.fillStyle = "#fff"; roundRect(ctx, 28, 222, 600, 390, 12); ctx.fill();
  ctx.strokeStyle = "#e3e6ea"; ctx.stroke();
  ctx.fillStyle = "#1b1e1d"; ctx.font = "bold 20px system-ui, Segoe UI, sans-serif";
  ctx.fillText("Jobs per technician", 50, 258);
  const bars = [0.8, 0.62, 0.95, 0.7, 0.55, 0.88];
  bars.forEach((b, i) => {
    const h = 270 * b * e, x = 60 + i * 92;
    ctx.fillStyle = i === 2 ? col : col + "99";
    roundRect(ctx, x, 590 - h, 60, Math.max(h, 1), 6); ctx.fill();
  });

  // route list
  ctx.fillStyle = "#fff"; roundRect(ctx, 648, 222, 348, 390, 12); ctx.fill();
  ctx.strokeStyle = "#e3e6ea"; ctx.stroke();
  ctx.fillStyle = "#1b1e1d"; ctx.font = "bold 20px system-ui, Segoe UI, sans-serif";
  ctx.fillText("Routes", 670, 258);
  ["Asha  ·  6 jobs", "Ben  ·  7 jobs", "Carys  ·  5 jobs", "Dev  ·  6 jobs", "Ella  ·  7 jobs"].forEach((t, i) => {
    const y = 290 + i * 62;
    ctx.globalAlpha = Math.max(0, Math.min(1, e * 6 - i));
    ctx.fillStyle = "#f6f7f9"; roundRect(ctx, 668, y, 308, 48, 8); ctx.fill();
    ctx.fillStyle = col; ctx.beginPath(); ctx.arc(692, y + 24, 8, 0, 7); ctx.fill();
    ctx.fillStyle = "#1b1e1d"; ctx.font = "18px system-ui, Segoe UI, sans-serif";
    ctx.fillText(t, 712, y + 31);
    ctx.fillStyle = "#1f8a4c"; ctx.font = "bold 16px system-ui, Segoe UI, sans-serif";
    ctx.fillText("✓", 948, y + 31);
  });
  ctx.globalAlpha = 1;
}

// Timeline (seconds): type and scroll the code, build into the app, hold, loop.
const T_CODE = 9, T_BUILD = 1.6, T_HOLD = 4.5, CYCLE = T_CODE + T_BUILD + T_HOLD;
const TOTAL_CHARS = LINES.reduce((n, l) => n + l.reduce((m, p) => m + p[1].length, 0), 0);
const MAX_SCROLL = Math.max(0, LINES.length * LINE_H + PAD - (H - 34) + 40);

function paintScreen(ctx, t, col, scratch) {
  const c = t % CYCLE;
  if (c < T_CODE) {
    const p = c / T_CODE;
    const typed = Math.floor(TOTAL_CHARS * Math.min(1, p * 1.15));
    drawCode(ctx, MAX_SCROLL * Math.max(0, (p - 0.25) / 0.75), typed, col);
  } else if (c < T_CODE + T_BUILD) {
    // Build: the app sweeps up from the bottom over the code, with a glowing scan line.
    const p = (c - T_CODE) / T_BUILD;
    drawCode(ctx, MAX_SCROLL, TOTAL_CHARS, col);
    const sctx = scratch.getContext("2d");
    drawApp(sctx, p * 0.6, col);
    const edge = H * (1 - p);
    ctx.drawImage(scratch, 0, edge, W, H - edge, 0, edge, W, H - edge);
    const g = ctx.createLinearGradient(0, edge - 40, 0, edge + 6);
    g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(1, col);
    ctx.fillStyle = g; ctx.fillRect(0, edge - 40, W, 46);
  } else {
    drawApp(ctx, 0.6 + (c - T_CODE - T_BUILD) / 1.2, col);
  }
}

// ------------------------------------------------------------------ 3D scene

function startScene() {
  if (!canvas) return;
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  } catch (err) {
    return; // no WebGL: the hero keeps its plain background
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const col = cssColour("--accent", "#5cc9b5");
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
  camera.position.set(0, 0.35, 11);

  // Screen texture drawn with 2D canvas each frame.
  const screenCanvas = document.createElement("canvas");
  screenCanvas.width = W; screenCanvas.height = H;
  const sctx = screenCanvas.getContext("2d");
  const scratch = document.createElement("canvas");
  scratch.width = W; scratch.height = H;
  const tex = new THREE.CanvasTexture(screenCanvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = renderer.capabilities.getMaxAnisotropy();

  // Monitor: bezel, screen, neck and base.
  const monitor = new THREE.Group();
  scene.add(monitor);
  const sw = 5.2, sh = sw * (H / W);
  const frameMat = new THREE.MeshStandardMaterial({ color: 0x1c2024, metalness: 0.6, roughness: 0.35 });
  const bezel = new THREE.Mesh(new THREE.BoxGeometry(sw + 0.3, sh + 0.3, 0.22), frameMat);
  monitor.add(bezel);
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(sw, sh), new THREE.MeshBasicMaterial({ map: tex, toneMapped: false }));
  screen.position.z = 0.115;
  monitor.add(screen);
  const glowRim = new THREE.Mesh(new THREE.PlaneGeometry(sw + 0.9, sh + 0.9),
    new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.12 }));
  glowRim.position.z = -0.14;
  monitor.add(glowRim);
  const neck = new THREE.Mesh(new THREE.BoxGeometry(0.42, 1.2, 0.2), frameMat);
  neck.position.set(0, -sh / 2 - 0.6, -0.12);
  monitor.add(neck);
  const base = new THREE.Mesh(new THREE.CylinderGeometry(1.15, 1.25, 0.12, 48), frameMat);
  base.position.set(0, -sh / 2 - 1.2, 0);
  monitor.add(base);
  monitor.position.y = 0.55;

  // Connected services behind the monitor. Cables run out of the back of the monitor to each
  // one; they reach out as the finished app appears, then data pulses travel along them.
  const SERVICES = [
    ["CRM", "◎", [3.65, 3.03, -1.0]],
    ["Database", "▤", [6.09, 3.13, -1.3]],
    ["Email", "✉", [7.90, 1.63, -1.0]],
    ["Payments", "£", [8.01, -0.59, -1.3]],
    ["Maps", "⌖", [6.35, -2.23, -1.0]],
    ["Sheets", "▦", [3.91, -2.33, -1.3]],
  ];
  const links = new THREE.Group();
  scene.add(links);
  const port = new THREE.Vector3(0, 0.55, -0.3); // back of the monitor (world space, before sway)
  const pulseGeo = new THREE.SphereGeometry(0.07, 12, 12);
  const pulseMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
  const services = SERVICES.map(([label, icon, pos], i) => {
    // label card
    const c = document.createElement("canvas"); c.width = 320; c.height = 112;
    const g = c.getContext("2d");
    g.fillStyle = "rgba(13,17,23,0.92)"; roundRect(g, 4, 4, 312, 104, 22); g.fill();
    g.strokeStyle = col; g.lineWidth = 4; g.stroke();
    g.fillStyle = col; g.beginPath(); g.arc(58, 56, 32, 0, 7); g.fill();
    g.fillStyle = "#0d1117"; g.font = "bold 34px system-ui, Segoe UI, sans-serif"; g.textAlign = "center";
    g.fillText(icon, 58, 68);
    g.fillStyle = "#e6edf3"; g.font = "bold 36px system-ui, Segoe UI, sans-serif"; g.textAlign = "left";
    g.fillText(label, 106, 69);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
    const card = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, opacity: 0 }));
    card.scale.set(1.6, 0.56, 1);
    const home = new THREE.Vector3(...pos);
    card.position.copy(home);
    links.add(card);
    // cable: a curve bowing backwards out of the monitor
    const mid = port.clone().lerp(home, 0.5).add(new THREE.Vector3(0, 0, -1.2));
    const curve = new THREE.QuadraticBezierCurve3(port, mid, home);
    const pts = curve.getPoints(64);
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    geo.setDrawRange(0, 0);
    const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.8 }));
    links.add(line);
    const pulses = [0, 1].map(() => { const m = new THREE.Mesh(pulseGeo, pulseMat); m.visible = false; links.add(m); return m; });
    return { card, home, curve, geo, pulses, delay: i * 0.12, phase: i * 0.37 };
  });

  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const key = new THREE.DirectionalLight(0xffffff, 2.2);
  key.position.set(4, 5, 6);
  scene.add(key);
  const rim = new THREE.PointLight(new THREE.Color(col), 30, 20);
  rim.position.set(-4, 2, -3);
  scene.add(rim);

  // Draw the monitor at the centre of its own view, lined up with the text column on wide
  // screens, so it never stretches however wide the screen is.
  const column = canvas.parentElement.querySelector(".wrap");
  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    let px = w / 2, s = 0.8;
    if (w > 900 && column) {
      // Keep the monitor in the free space to the right of the headline (about 40rem wide).
      const r = column.getBoundingClientRect(), c = canvas.getBoundingClientRect();
      const textRight = r.left - c.left + 40 * 16 + 24;
      const space = w - textRight - 16;
      // Monitor plus the fan of services spans about -3 to +9 scene units from the monitor's
      // centre; one scene unit is h / 6.94 pixels at this camera distance.
      const unit = h / 6.94;
      s = Math.max(0.4, Math.min(1, space / (12.3 * unit)));
      px = textRight + 3.1 * unit * s;
    }
    canvas.parentElement.style.setProperty("--orb-x", `${px}px`);
    const fullW = 2 * Math.max(px, w - px);
    camera.aspect = fullW / h;
    camera.setViewOffset(fullW, h, fullW / 2 - px, 0, w, h);
    camera.updateProjectionMatrix();
    monitor.scale.setScalar(s);
    links.scale.setScalar(s);
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
  function frame(t) {
    paintScreen(sctx, t, col, scratch);
    tex.needsUpdate = true;
    monitor.rotation.y = -0.28 + Math.sin(t * 0.35) * 0.08 + mx * 0.18;
    monitor.rotation.x = -0.04 + Math.sin(t * 0.27) * 0.03 + my * 0.08;
    monitor.position.y = 0.55 + Math.sin(t * 0.6) * 0.06;
    // Connections follow the app: hidden while coding, reach out during the build, carry
    // data while the app is on screen, and pull back just before the loop restarts.
    const c = t % CYCLE;
    let reach;
    // Cables reach out one by one while the code is being written (10% to 85% of it), so
    // each service is connected by the time the app builds.
    if (c > CYCLE - 0.7) reach = (CYCLE - c) / 0.7;
    else reach = Math.max(0, Math.min(1, (c / T_CODE - 0.1) / 0.75));
    const building = c < T_CODE + T_BUILD;
    links.rotation.y = monitor.rotation.y * 0.5;
    services.forEach((s) => {
      const r = Math.max(0, Math.min(1, (reach - s.delay) / (1 - 0.6)));
      s.geo.setDrawRange(0, Math.floor(65 * r));
      s.card.material.opacity = Math.max(0, Math.min(1, r * 1.6 - 0.6));
      s.card.position.y = s.home.y + Math.sin(t * 0.8 + s.phase) * 0.08;
      const live = r >= 1;
      s.pulses.forEach((p, k) => {
        p.visible = live;
        if (!live) return;
        // While the code is written, data flows in from every service to the monitor;
        // once the app is live, one pulse goes out and one comes back.
        let u = (t * 0.45 + s.phase + k * 0.5) % 1;
        if (building || k === 1) u = 1 - u;
        p.position.copy(s.curve.getPoint(u));
      });
    });
    renderer.render(scene, camera);
  }
  canvas.classList.add("ready");
  if (still) { frame(T_CODE + T_BUILD + 2); return; } // finished app, no motion
  renderer.setAnimationLoop(() => { if (visible) frame(clock.getElapsedTime()); });
}

function tiltCards() {
  if (still || !window.matchMedia("(hover: hover)").matches) return;
  document.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("pointermove", (ev) => {
      const r = card.getBoundingClientRect();
      const x = (ev.clientX - r.left) / r.width - 0.5;
      const y = (ev.clientY - r.top) / r.height - 0.5;
      card.style.transform = `perspective(900px) rotateY(${x * 8}deg) rotateX(${-y * 8}deg) translateZ(0)`;
      card.style.setProperty("--gx", `${(x + 0.5) * 100}%`);
      card.style.setProperty("--gy", `${(y + 0.5) * 100}%`);
    });
    card.addEventListener("pointerleave", () => { card.style.transform = ""; });
  });
}

startScene();
tiltCards();
