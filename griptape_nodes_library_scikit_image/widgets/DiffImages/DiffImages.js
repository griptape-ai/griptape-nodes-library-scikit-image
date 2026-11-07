// DiffImages: two images to wipe between, flip between, or see where they differ, before you run the node.
//
// Python compares the images at the node's preview size and sends a map of where they differ: 8-bit grayscale, white
// where they differ most, with no gain applied. The widget draws everything on one canvas. The view, the wipe position
// and the gain are parameters of the node, listed in synced_parameters, so the widget reads and writes them directly,
// and the node saves the view that is showing. The gain is applied here to the map, so the differences brighten as the
// slider moves with no new comparison. The preview size changes what is compared, so Python compares again when it is
// released. The widget's own value is image_url, other_url, width and height (of the first image, which the second is
// stretched to), map_url, score and message.
//
// The views are the same as tools.compare_view in Python: Wipe is the first image left of the divider and the second
// right of it, A and B are the images, Difference draws the map, and Heat tints the first image red where they differ.

const STYLE_ID = "diff-images-styles";
const DEFAULTS = { view: "Difference", wipe: 50, gain: 3 };
const VIEWS = ["Wipe", "A", "B", "Difference", "Heat"];
const HEAT = [255, 60, 60]; // as tools.HEAT_COLOUR and HEAT_ALPHA
const HEAT_ALPHA = 0.85;

function injectStyles() {
  let el = document.getElementById(STYLE_ID);
  if (!el) {
    el = document.createElement("style");
    el.id = STYLE_ID;
    document.head.appendChild(el);
  }
  el.textContent = `
    .diff-wrap { display:flex; flex-direction:column; gap:6px; width:100%; height:100%; font-size:11px; color:var(--foreground); }
    .diff-stage { position:relative; flex:1 1 0; min-height:180px; background:var(--muted); border-radius:6px; overflow:hidden; display:flex; align-items:center; justify-content:center; }
    .diff-canvas { flex:none; display:block; touch-action:none; }
    .diff-msg { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; padding:12px; text-align:center; color:var(--muted-foreground); pointer-events:none; }
    .diff-bar { display:flex; align-items:center; gap:4px; }
    .diff-summary { margin-left:auto; color:var(--muted-foreground); }
    .diff-btn { border:none; border-radius:4px; background:var(--muted); color:var(--foreground); cursor:pointer; padding:3px 9px; height:24px; font-size:11px; font-family:inherit; }
    .diff-btn:hover { background:var(--accent, rgba(122,157,184,0.2)); }
    .diff-btn.active { background:rgba(122,157,184,0.25); box-shadow:inset 0 0 0 1px rgba(122,157,184,0.6); }
    .diff-btn:disabled { opacity:0.4; cursor:default; }
  `;
}

function element(tag, className) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  return el;
}

export default function DiffImages(container, props) {
  if (container._diffInst?.wrapper?.isConnected) {
    container._diffInst.handleUpdate(props);
    return { cleanup: container._diffInst.cleanup, update: container._diffInst.handleUpdate };
  }

  injectStyles();

  let value = props.value || {};
  let onChange = props.onChange;
  let onLiveChange = props.onLiveChange;
  let locked = props.locked || [];
  let dragging = false;
  let liveWipe = null; // the wipe position while the divider is being dragged
  let resizeWatcher = null;
  const pictures = { a: null, b: null }; // loaded images, by url
  const urls = { a: "", b: "" };
  let map = null; // { url, width, height, gray } once the map is decoded
  let mapTurn = 0;
  let tint = null; // the map drawn with the gain, kept until the view, gain or map changes
  let tintKey = "";

  const wrapper = element("div", "diff-wrap nodrag nowheel");
  for (const type of ["pointerdown", "mousedown", "keydown", "wheel"]) {
    wrapper.addEventListener(type, (e) => e.stopPropagation());
  }
  const stage = element("div", "diff-stage");
  const canvas = element("canvas", "diff-canvas");
  const message = element("div", "diff-msg");
  message.textContent = "Connect two images to compare them.";
  stage.append(canvas, message);

  const bar = element("div", "diff-bar");
  const buttons = new Map();
  for (const name of VIEWS) {
    const button = element("button", "diff-btn");
    button.type = "button";
    button.textContent = name;
    button.addEventListener("click", () => {
      if (!locked.includes("view")) onChange?.({ ...value, view: name });
    });
    buttons.set(name, button);
    bar.appendChild(button);
  }
  const summary = element("span", "diff-summary");
  bar.appendChild(summary);
  wrapper.append(stage, bar);
  container.appendChild(wrapper);

  // ── the settings ─────────────────────────────────────────────────────────

  function setting(name) {
    const incoming = value[name];
    return incoming === undefined || incoming === null ? DEFAULTS[name] : incoming;
  }

  function currentView() {
    return VIEWS.includes(setting("view")) ? setting("view") : DEFAULTS.view;
  }

  function wipePosition() {
    const position = liveWipe ?? Number(setting("wipe"));
    return Math.min(1, Math.max(0, (Number.isFinite(position) ? position : DEFAULTS.wipe) / 100));
  }

  // ── the images and the map ───────────────────────────────────────────────

  function load(slot, url) {
    if (url === urls[slot]) return;
    urls[slot] = url;
    pictures[slot] = null;
    if (!url) return;
    const picture = new Image();
    picture.onload = () => {
      if (urls[slot] !== url) return;
      pictures[slot] = picture;
      draw();
    };
    picture.src = url;
  }

  function decodeMap(url) {
    if (url === (map?.url ?? "")) return;
    map = null;
    tint = null;
    const turn = ++mapTurn;
    if (!url) return;
    const picture = new Image();
    picture.onload = () => {
      if (turn !== mapTurn) return;
      const scratch = element("canvas");
      scratch.width = picture.naturalWidth;
      scratch.height = picture.naturalHeight;
      const context = scratch.getContext("2d");
      context.drawImage(picture, 0, 0);
      const rgba = context.getImageData(0, 0, scratch.width, scratch.height).data;
      const gray = new Uint8ClampedArray(scratch.width * scratch.height);
      for (let i = 0; i < gray.length; i++) gray[i] = rgba[i * 4];
      map = { url, width: scratch.width, height: scratch.height, gray };
      draw();
    };
    picture.src = url;
  }

  // The map with the gain applied, as a canvas the size of the map: gray for Difference, red with alpha for Heat.
  function tinted(view) {
    const gain = Number(setting("gain")) || DEFAULTS.gain;
    const key = `${view}|${gain}|${map.url}`;
    if (tint && key === tintKey) return tint;
    const layer = element("canvas");
    layer.width = map.width;
    layer.height = map.height;
    const context = layer.getContext("2d");
    const picture = context.createImageData(map.width, map.height);
    const pixels = picture.data;
    for (let i = 0; i < map.gray.length; i++) {
      const level = Math.min(1, (map.gray[i] / 255) * gain);
      const o = i * 4;
      if (view === "Heat") {
        pixels[o] = HEAT[0];
        pixels[o + 1] = HEAT[1];
        pixels[o + 2] = HEAT[2];
        pixels[o + 3] = level * HEAT_ALPHA * 255;
      } else {
        pixels[o] = pixels[o + 1] = pixels[o + 2] = level * 255;
        pixels[o + 3] = 255;
      }
    }
    context.putImageData(picture, 0, 0);
    tint = layer;
    tintKey = key;
    return layer;
  }

  // ── drawing ──────────────────────────────────────────────────────────────

  function size() {
    return [Number(value.width) || 0, Number(value.height) || 0];
  }

  function layout() {
    const [width, height] = size();
    if (width > 0 && height > 0) {
      const scale = Math.min((stage.clientWidth || 480) / width, (stage.clientHeight || 360) / height);
      const ratio = window.devicePixelRatio || 1;
      const shownWidth = Math.max(1, Math.round(width * scale));
      const shownHeight = Math.max(1, Math.round(height * scale));
      canvas.style.width = `${shownWidth}px`;
      canvas.style.height = `${shownHeight}px`;
      if (canvas.width !== Math.round(shownWidth * ratio) || canvas.height !== Math.round(shownHeight * ratio)) {
        canvas.width = Math.round(shownWidth * ratio);
        canvas.height = Math.round(shownHeight * ratio);
      }
    }
    draw();
  }

  function draw() {
    const [width, height] = size();
    const urlA = typeof value.image_url === "string" ? value.image_url : "";
    const urlB = typeof value.other_url === "string" ? value.other_url : "";
    load("a", urlA);
    load("b", urlB);
    decodeMap(typeof value.map_url === "string" ? value.map_url : "");

    const hasA = !!urlA && width > 0 && height > 0;
    const hasBoth = hasA && !!urlB;
    // Only the first image is there until the second arrives. The other views need the second and the map.
    const view = hasBoth ? currentView() : "A";
    canvas.style.display = hasA ? "block" : "none";
    message.style.display = hasA ? "none" : "flex";
    for (const [name, button] of buttons) {
      button.classList.toggle("active", name === view);
      button.disabled = (name !== "A" && !hasBoth) || locked.includes("view");
    }

    const context = canvas.getContext("2d");
    context.clearRect(0, 0, canvas.width, canvas.height);
    if (hasA) {
      const w = canvas.width;
      const h = canvas.height;
      const first = pictures.a;
      const second = pictures.b;
      const mapReady = map && hasBoth;
      if (view === "B" && second) {
        context.drawImage(second, 0, 0, w, h);
      } else if (view === "Difference" && mapReady) {
        context.imageSmoothingEnabled = true;
        context.drawImage(tinted("Difference"), 0, 0, w, h);
      } else if (view === "Wipe" && first && second) {
        const cut = Math.round(w * wipePosition());
        context.drawImage(first, 0, 0, w, h);
        context.save();
        context.beginPath();
        context.rect(cut, 0, w - cut, h);
        context.clip();
        context.drawImage(second, 0, 0, w, h);
        context.restore();
        drawDivider(context, cut, h);
      } else if (first) {
        context.drawImage(first, 0, 0, w, h);
        if (view === "Heat" && mapReady) context.drawImage(tinted("Heat"), 0, 0, w, h);
      }
    }

    const score = Number(value.score);
    summary.textContent =
      hasBoth && Number.isFinite(score) && map
        ? `Similarity ${score.toFixed(3)} at ${Math.max(map.width, map.height)} px`
        : value.message || "";
  }

  function drawDivider(context, x, h) {
    const ratio = window.devicePixelRatio || 1;
    context.fillStyle = "rgba(0,0,0,0.55)"; // a dark edge, so the line shows on white paper
    context.fillRect(x - 2 * ratio, 0, 4 * ratio, h);
    context.fillStyle = "#fff";
    context.fillRect(x - ratio, 0, 2 * ratio, h);
    context.beginPath();
    context.arc(x, h / 2, 11 * ratio, 0, Math.PI * 2);
    context.fill();
    context.lineWidth = ratio;
    context.strokeStyle = "rgba(0,0,0,0.5)";
    context.stroke();
  }

  // ── dragging the divider ─────────────────────────────────────────────────

  function wipeFrom(event) {
    const bounds = canvas.getBoundingClientRect();
    if (!bounds.width) return null;
    return Math.round(Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width)) * 1000) / 10;
  }

  canvas.addEventListener("pointerdown", (event) => {
    if (currentView() !== "Wipe" || locked.includes("wipe")) return;
    canvas.setPointerCapture(event.pointerId);
    dragging = true;
    liveWipe = wipeFrom(event);
    onLiveChange?.({ wipe: liveWipe });
    draw();
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    liveWipe = wipeFrom(event);
    onLiveChange?.({ wipe: liveWipe });
    draw();
  });
  const endDrag = () => {
    if (!dragging) return;
    dragging = false;
    const wipe = liveWipe;
    liveWipe = null;
    if (wipe !== null) onChange?.({ ...value, wipe });
  };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);

  // ── updates from the framework ───────────────────────────────────────────

  function handleUpdate(newProps) {
    onChange = newProps.onChange;
    onLiveChange = newProps.onLiveChange;
    locked = newProps.locked || [];
    // While the divider is being dragged, the incoming value is our own live value.
    if (!dragging) value = newProps.value || {};
    layout();
  }

  function cleanup() {
    mapTurn++;
    if (resizeWatcher) resizeWatcher.disconnect();
    resizeWatcher = null;
    wrapper.remove();
    delete container._diffInst;
  }

  if (typeof ResizeObserver !== "undefined") {
    resizeWatcher = new ResizeObserver(() => layout());
    resizeWatcher.observe(stage);
  }
  layout();

  container._diffInst = { handleUpdate, cleanup, wrapper };
  return { cleanup, update: handleUpdate };
}
