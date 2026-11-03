// BoilingLines: a live preview of the wobble that Boiling Lines will apply, with the settings to change it.
//
// The widget draws the image warped by the same noise the node uses (see _noise.js, which matches noise.py), so what
// you scrub through here is what the node saves. It never goes back to Python while you drag a slider.
//
// The value is a dict. Python sets image_url, width and height when an image is connected. frame_count, amplitude,
// wobble_size and seed are also parameters of the node: Python keeps them in step with this dict in both directions, so
// they can be set here, on the node, or by a connection. frame, view and fps are only for the preview.

import { makeLattice, warpPixels, noisePixels, visible } from "./_noise.js";

const STYLE_ID = "boil-styles";
const PREVIEW_MAX = 720; // longest side of the preview, in pixels
const ARROW_GRID = 28; // preview pixels between arrows in the noise view
const ARROW_REACH = ARROW_GRID * 1.4; // the longest an arrow is drawn, for the largest Amount
const LATTICE_CACHE = 120;

const DEFAULTS = {
  image_url: "",
  width: 0,
  height: 0,
  frame_count: 8,
  amplitude: 0.3,
  wobble_size: 2.0,
  seed: 1,
  frame: 1,
  view: "result",
  fps: 12,
};
const LIMITS = {
  frame_count: [2, 96],
  amplitude: [0.02, 5],
  wobble_size: [0.3, 20],
  seed: [0, 100000],
  fps: [1, 30],
};
const VIEWS = ["result", "noise", "original"];
const VIEW_LABELS = { result: "Result", noise: "Noise", original: "Original" };
const SETTING_KEYS = ["frame_count", "amplitude", "wobble_size", "seed", "frame", "view", "fps"];

function clamp(value, low, high) {
  return Math.min(Math.max(value, low), high);
}

function normalise(value) {
  const v = { ...DEFAULTS, ...((value && typeof value === "object") ? value : {}) };
  for (const [key, [low, high]] of Object.entries(LIMITS)) {
    const n = Number(v[key]);
    v[key] = clamp(Number.isFinite(n) ? n : DEFAULTS[key], low, high);
  }
  v.frame_count = Math.round(v.frame_count);
  v.seed = Math.round(v.seed);
  v.fps = Math.round(v.fps);
  v.frame = clamp(Math.round(Number(v.frame) || 1), 1, v.frame_count);
  if (!VIEWS.includes(v.view)) v.view = "result";
  v.image_url = typeof v.image_url === "string" ? v.image_url : "";
  v.width = Number(v.width) || 0;
  v.height = Number(v.height) || 0;
  return v;
}

function injectStyles() {
  let el = document.getElementById(STYLE_ID);
  if (!el) {
    el = document.createElement("style");
    el.id = STYLE_ID;
    document.head.appendChild(el);
  }
  el.textContent = `
    .boil-wrap { display:flex; flex-direction:column; gap:6px; width:100%; height:100%; font-size:11px; color:var(--foreground); }
    .boil-stage { position:relative; flex:1 1 0; min-height:180px; background:var(--muted); border-radius:6px; overflow:hidden; display:flex; align-items:center; justify-content:center; }
    .boil-canvas { display:block; flex:none; }
    .boil-msg { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; padding:12px; text-align:center; color:var(--muted-foreground); }
    .boil-row { display:flex; align-items:center; gap:6px; }
    .boil-heading { margin-top:4px; padding-top:4px; border-top:1px solid var(--border); font-weight:600; color:var(--muted-foreground); text-transform:uppercase; letter-spacing:0.04em; font-size:10px; }
    .boil-label { width:92px; flex-shrink:0; color:var(--muted-foreground); }
    .boil-range { flex:1; min-width:30px; accent-color:#7a9db8; cursor:pointer; }
    .boil-value { width:46px; flex-shrink:0; text-align:right; color:var(--foreground); }
    .boil-btn { border:none; border-radius:4px; background:var(--muted); color:var(--foreground); cursor:pointer; padding:3px 9px; height:24px; font-size:11px; font-family:inherit; flex-shrink:0; }
    .boil-btn:hover { background:var(--accent, rgba(122,157,184,0.2)); }
    .boil-btn.active { background:rgba(122,157,184,0.25); box-shadow:inset 0 0 0 1px rgba(122,157,184,0.6); }
    .boil-btn:disabled, .boil-range:disabled { opacity:0.4; cursor:default; }
    .boil-number { width:60px; background:var(--muted); color:var(--foreground); border:1px solid var(--border); border-radius:4px; padding:2px 4px; height:22px; font-size:11px; }
    .boil-views { display:flex; gap:4px; }
  `;
}

export default function BoilingLines(container, props) {
  if (container._boilInst?.wrapper?.isConnected) {
    container._boilInst.handleUpdate(props);
    return { cleanup: container._boilInst.cleanup, update: container._boilInst.handleUpdate };
  }

  injectStyles();

  let onChange = props.onChange;
  let disabled = !!props.disabled;
  let state = normalise(props.value);
  let emitSeq = 0;
  let interacting = false;

  // image and preview state
  let loadedUrl = "";
  let source = null; // ImageData of the preview-sized image
  let originalWidth = 0;
  let originalHeight = 0;
  let scale = 1;
  let resultData = null;
  let renderPending = false;
  const latticeCache = new Map();
  const arrows = [];
  let playTimer = null;
  let resizeWatcher = null;

  // ── DOM ──────────────────────────────────────────────────────────────────

  const wrapper = document.createElement("div");
  wrapper.className = "boil-wrap nodrag nowheel";
  for (const type of ["pointerdown", "mousedown", "keydown", "wheel"]) {
    wrapper.addEventListener(type, (e) => e.stopPropagation());
  }

  const stage = document.createElement("div");
  stage.className = "boil-stage";
  const canvas = document.createElement("canvas");
  canvas.className = "boil-canvas";
  canvas.width = 320;
  canvas.height = 180;
  const message = document.createElement("div");
  message.className = "boil-msg";
  stage.appendChild(canvas);
  stage.appendChild(message);
  wrapper.appendChild(stage);
  const ctx = canvas.getContext("2d");

  function row(labelText) {
    const el = document.createElement("div");
    el.className = "boil-row";
    if (labelText) {
      const label = document.createElement("span");
      label.className = "boil-label";
      label.textContent = labelText;
      el.appendChild(label);
    }
    wrapper.appendChild(el);
    return el;
  }

  function button(text, onClick) {
    const b = document.createElement("button");
    b.className = "boil-btn";
    b.textContent = text;
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }

  function heading(text) {
    const el = document.createElement("div");
    el.className = "boil-heading";
    el.textContent = text;
    wrapper.appendChild(el);
  }

  // Playback: how the preview is played. None of this changes the saved frames, except how many there are.
  heading("Playback");
  const transport = row("");
  const playButton = button("Play", () => (playTimer ? pause() : play()));
  const frameRange = document.createElement("input");
  frameRange.type = "range";
  frameRange.className = "boil-range";
  frameRange.step = "1";
  const frameLabel = document.createElement("span");
  frameLabel.className = "boil-value";
  frameLabel.style.width = "60px";
  transport.appendChild(playButton);
  transport.appendChild(frameRange);
  transport.appendChild(frameLabel);

  const viewRow = row("View");
  const viewBox = document.createElement("div");
  viewBox.className = "boil-views";
  const viewButtons = {};
  for (const view of VIEWS) {
    viewButtons[view] = button(VIEW_LABELS[view], () => {
      state.view = view;
      syncControls();
      scheduleRender();
      emit();
    });
    viewBox.appendChild(viewButtons[view]);
  }
  viewRow.appendChild(viewBox);

  const controls = {};
  function slider(key, labelText, step, format) {
    const el = row(labelText);
    const input = document.createElement("input");
    input.type = "range";
    input.className = "boil-range";
    input.min = String(LIMITS[key][0]);
    input.max = String(LIMITS[key][1]);
    input.step = String(step);
    const value = document.createElement("span");
    value.className = "boil-value";
    el.appendChild(input);
    el.appendChild(value);
    input.addEventListener("pointerdown", () => { interacting = true; });
    input.addEventListener("input", () => {
      state[key] = Number(input.value);
      state = normalise(state);
      syncControls();
      scheduleRender();
    });
    input.addEventListener("change", () => {
      interacting = false;
      emit();
    });
    controls[key] = { input, value, format };
  }
  slider("frame_count", "Frames", 1, (v) => String(v));
  slider("fps", "Preview speed", 1, (v) => `${v} fps`);

  // Wobble: what the noise does. These are also parameters of the node.
  heading("Wobble");
  slider("amplitude", "Amount", 0.01, (v) => `${v.toFixed(2)}%`);
  slider("wobble_size", "Wobble size", 0.05, (v) => `${v.toFixed(2)}%`);

  const seedRow = row("Seed");
  const seedInput = document.createElement("input");
  seedInput.type = "number";
  seedInput.className = "boil-number";
  seedInput.min = String(LIMITS.seed[0]);
  seedInput.max = String(LIMITS.seed[1]);
  seedInput.step = "1";
  const diceButton = button("Random", () => {
    state.seed = Math.floor(Math.random() * (LIMITS.seed[1] + 1));
    syncControls();
    scheduleRender();
    emit();
  });
  seedRow.appendChild(seedInput);
  seedRow.appendChild(diceButton);
  seedInput.addEventListener("change", () => {
    state.seed = Number(seedInput.value);
    state = normalise(state);
    syncControls();
    scheduleRender();
    emit();
  });

  container.appendChild(wrapper);

  // ── state ────────────────────────────────────────────────────────────────

  function emit() {
    if (disabled || typeof onChange !== "function") return;
    emitSeq += 1;
    onChange({ ...state, _seq: emitSeq });
  }

  function syncControls() {
    for (const [key, { input, value, format }] of Object.entries(controls)) {
      input.value = String(state[key]);
      value.textContent = format(state[key]);
    }
    frameRange.min = "1";
    frameRange.max = String(state.frame_count);
    frameRange.value = String(state.frame);
    frameLabel.textContent = `${state.frame} / ${state.frame_count}`;
    seedInput.value = String(state.seed);
    for (const view of VIEWS) viewButtons[view].classList.toggle("active", state.view === view);
    playButton.textContent = playTimer ? "Pause" : "Play";
    applyDisabled();
  }

  function applyDisabled() {
    const off = disabled;
    for (const { input } of Object.values(controls)) input.disabled = off;
    frameRange.disabled = false; // scrubbing only changes the preview
    seedInput.disabled = off;
    diceButton.disabled = off;
  }

  frameRange.addEventListener("pointerdown", () => { interacting = true; });
  frameRange.addEventListener("input", () => {
    state.frame = clamp(Number(frameRange.value), 1, state.frame_count);
    frameLabel.textContent = `${state.frame} / ${state.frame_count}`;
    scheduleRender();
  });
  frameRange.addEventListener("change", () => {
    interacting = false;
    emit();
  });

  // ── playback ─────────────────────────────────────────────────────────────

  function play() {
    if (playTimer) return;
    playTimer = setInterval(() => {
      state.frame = (state.frame % state.frame_count) + 1;
      frameRange.value = String(state.frame);
      frameLabel.textContent = `${state.frame} / ${state.frame_count}`;
      scheduleRender();
    }, 1000 / state.fps);
    syncControls();
  }

  function pause() {
    if (!playTimer) return;
    clearInterval(playTimer);
    playTimer = null;
    syncControls();
    emit();
  }

  // Changing the speed while playing restarts the timer at the new rate.
  controls.fps.input.addEventListener("change", () => {
    if (playTimer) {
      clearInterval(playTimer);
      playTimer = null;
      play();
    }
  });

  // ── layout ───────────────────────────────────────────────────────────────

  // Like the Crop Image widget: the widget fills the node, the stage takes the room the controls leave, and the image is
  // scaled to the largest size that fits in the stage. A bigger node gives a bigger preview, and a tall image can never
  // push the controls out of view. The canvas holds the preview pixels, and its size on the screen is set here.
  function fitCanvas() {
    if (!source) return;
    const areaWidth = stage.clientWidth || 300;
    const areaHeight = stage.clientHeight || 200;
    const fit = Math.min(areaWidth / source.width, areaHeight / source.height);
    canvas.style.width = `${Math.max(1, Math.floor(source.width * fit))}px`;
    canvas.style.height = `${Math.max(1, Math.floor(source.height * fit))}px`;
  }

  if (typeof ResizeObserver === "function") {
    resizeWatcher = new ResizeObserver(() => fitCanvas());
    resizeWatcher.observe(stage);
  }

  // ── image ────────────────────────────────────────────────────────────────

  function showMessage(text) {
    message.textContent = text;
    message.style.display = text ? "flex" : "none";
  }

  function loadImage(url) {
    loadedUrl = url;
    source = null;
    resultData = null;
    latticeCache.clear();
    if (!url) {
      showMessage("Connect an image to Image to preview the wobble.");
      return;
    }
    showMessage("Loading the image...");
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      if (url !== loadedUrl) return;
      originalWidth = img.naturalWidth || state.width;
      originalHeight = img.naturalHeight || state.height;
      scale = Math.min(1, PREVIEW_MAX / Math.max(originalWidth, originalHeight));
      const w = Math.max(1, Math.round(originalWidth * scale));
      const h = Math.max(1, Math.round(originalHeight * scale));
      canvas.width = w;
      canvas.height = h;
      scale = w / originalWidth;
      ctx.clearRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);
      try {
        source = ctx.getImageData(0, 0, w, h);
        resultData = ctx.createImageData(w, h);
        fitCanvas();
        showMessage("");
        scheduleRender();
      } catch (e) {
        source = null;
        showMessage("The browser would not let the widget read this image, so it cannot draw the preview.");
      }
    };
    img.onerror = () => {
      if (url !== loadedUrl) return;
      showMessage("Could not load the image.");
    };
    img.src = url;
  }

  // ── drawing ──────────────────────────────────────────────────────────────

  function scheduleRender() {
    if (renderPending) return;
    renderPending = true;
    const run = () => {
      renderPending = false;
      render();
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
    else setTimeout(run, 0);
  }

  function latticeFor(frame, size) {
    const key = `${originalWidth}x${originalHeight}|${size}|${frame}|${state.seed}`;
    let lattice = latticeCache.get(key);
    if (!lattice) {
      if (latticeCache.size >= LATTICE_CACHE) latticeCache.clear();
      lattice = makeLattice(originalWidth, originalHeight, size, frame, state.seed);
      latticeCache.set(key, lattice);
    }
    return lattice;
  }

  function render() {
    if (!source || !resultData) return;
    const longer = Math.max(originalWidth, originalHeight);
    const amplitude = (state.amplitude / 100) * longer;
    const size = Math.max(1, (state.wobble_size / 100) * longer);
    const w = source.width;
    const h = source.height;

    if (state.view === "original") {
      ctx.putImageData(source, 0, 0);
      return;
    }
    const lattice = latticeFor(state.frame - 1, size);
    if (state.view === "result") {
      warpPixels(source.data, w, h, lattice, amplitude, scale, resultData.data);
      ctx.putImageData(resultData, 0, 0);
      return;
    }
    const reference = (LIMITS.amplitude[1] / 100) * longer;
    noisePixels(source.data, w, h, lattice, amplitude, scale, resultData.data, arrows, ARROW_GRID, reference);
    ctx.putImageData(resultData, 0, 0);
    ctx.strokeStyle = "rgba(255,255,255,0.9)";
    ctx.lineWidth = 1;
    for (const [x, y, down, right] of arrows) {
      const push = Math.hypot(down, right);
      if (push <= 0) continue;
      // The arrow points where the image is pushed and its length grows with the push, so it grows with the Amount.
      const length = ARROW_REACH * visible(push, reference);
      const dx = (right / push) * length;
      const dy = (down / push) * length;
      const angle = Math.atan2(dy, dx);
      ctx.beginPath();
      ctx.moveTo(x - dx / 2, y - dy / 2);
      ctx.lineTo(x + dx / 2, y + dy / 2);
      ctx.lineTo(x + dx / 2 - 3 * Math.cos(angle - 0.5), y + dy / 2 - 3 * Math.sin(angle - 0.5));
      ctx.moveTo(x + dx / 2, y + dy / 2);
      ctx.lineTo(x + dx / 2 - 3 * Math.cos(angle + 0.5), y + dy / 2 - 3 * Math.sin(angle + 0.5));
      ctx.stroke();
    }
  }

  // ── updates from the framework ───────────────────────────────────────────

  function handleUpdate(newProps) {
    onChange = newProps.onChange;
    disabled = !!newProps.disabled;
    const incoming = normalise(newProps.value);
    const seq = Number(newProps.value && newProps.value._seq) || 0;
    const stale = seq > 0 && seq < emitSeq; // an echo of a snapshot older than what was last emitted

    state.width = incoming.width;
    state.height = incoming.height;
    if (incoming.image_url !== state.image_url) {
      state.image_url = incoming.image_url;
      loadImage(state.image_url);
    }
    if (!stale && !interacting) {
      for (const key of SETTING_KEYS) state[key] = incoming[key];
      state = normalise(state);
      syncControls();
      scheduleRender();
    } else {
      applyDisabled();
    }
  }

  function cleanup() {
    if (playTimer) clearInterval(playTimer);
    playTimer = null;
    if (resizeWatcher) resizeWatcher.disconnect();
    resizeWatcher = null;
    loadedUrl = "";
    source = null;
    wrapper.remove();
    delete container._boilInst;
  }

  syncControls();
  loadImage(state.image_url);

  container._boilInst = { handleUpdate, cleanup, wrapper };
  return { cleanup, update: handleUpdate };
}
