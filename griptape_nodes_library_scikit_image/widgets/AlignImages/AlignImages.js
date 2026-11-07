// AlignImages: the aligned image against its reference, before you run the node.
//
// Python aligns reduced copies of the images and sends them inside the widget's value: the reference, the aligned image
// (both as JPEG data URLs), and a map of where the reference and the image differ before the alignment and after it
// (8-bit grayscale, white where they differ most, no gain applied). It also sends the shift, turn and scale it found.
// The widget draws everything on one canvas. The mode and the preview size change the alignment, so Python aligns again
// when they are released. The gain is a synced parameter and is applied here, so the differences brighten as it moves.
//
// The views are only for looking, so they are kept here and not saved: Wipe is the reference left of the divider and the
// aligned image right of it, Reference and Aligned are the pictures, and Before and After are the maps of differences,
// which show what the alignment fixed.

const STYLE_ID = "align-images-styles";
const DEFAULTS = { gain: 3 };
const VIEWS = ["Wipe", "Reference", "Aligned", "Before", "After"];

function injectStyles() {
  let el = document.getElementById(STYLE_ID);
  if (!el) {
    el = document.createElement("style");
    el.id = STYLE_ID;
    document.head.appendChild(el);
  }
  el.textContent = `
    .align-wrap { display:flex; flex-direction:column; gap:6px; width:100%; height:100%; font-size:11px; color:var(--foreground); }
    .align-stage { position:relative; flex:1 1 0; min-height:180px; background:var(--muted); border-radius:6px; overflow:hidden; display:flex; align-items:center; justify-content:center; }
    .align-canvas { flex:none; display:block; touch-action:none; }
    .align-msg { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; padding:12px; text-align:center; color:var(--muted-foreground); pointer-events:none; }
    .align-bar { display:flex; align-items:center; gap:4px; flex-wrap:wrap; }
    .align-btn { border:none; border-radius:4px; background:var(--muted); color:var(--foreground); cursor:pointer; padding:3px 9px; height:24px; font-size:11px; font-family:inherit; }
    .align-btn:hover { background:var(--accent, rgba(122,157,184,0.2)); }
    .align-btn.active { background:rgba(122,157,184,0.25); box-shadow:inset 0 0 0 1px rgba(122,157,184,0.6); }
    .align-btn:disabled { opacity:0.4; cursor:default; }
    .align-summary { color:var(--muted-foreground); line-height:1.4; }
  `;
}

function element(tag, className) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  return el;
}

function signed(number, digits) {
  const text = Math.abs(number).toFixed(digits);
  return `${number < 0 ? "−" : ""}${text}`;
}

export default function AlignImages(container, props) {
  if (container._alignInst?.wrapper?.isConnected) {
    container._alignInst.handleUpdate(props);
    return { cleanup: container._alignInst.cleanup, update: container._alignInst.handleUpdate };
  }

  injectStyles();

  let value = props.value || {};
  let view = "Wipe";
  let wipe = 0.5; // where the divider is, from 0 at the left to 1 at the right
  let dragging = false;
  let resizeWatcher = null;
  const pictures = { reference: null, aligned: null }; // loaded images
  const sources = { reference: "", aligned: "" };
  const maps = { before: null, after: null }; // { source, width, height, gray } once decoded
  const turns = { before: 0, after: 0 };
  const tints = new Map(); // a map drawn with the gain, by name, until the gain or the map changes

  const wrapper = element("div", "align-wrap nodrag nowheel");
  for (const type of ["pointerdown", "mousedown", "keydown", "wheel"]) {
    wrapper.addEventListener(type, (e) => e.stopPropagation());
  }
  const stage = element("div", "align-stage");
  const canvas = element("canvas", "align-canvas");
  const message = element("div", "align-msg");
  message.textContent = "Connect an image and a reference to see how they line up.";
  stage.append(canvas, message);

  const bar = element("div", "align-bar");
  const buttons = new Map();
  for (const name of VIEWS) {
    const button = element("button", "align-btn");
    button.type = "button";
    button.textContent = name;
    button.addEventListener("click", () => {
      view = name;
      draw();
    });
    buttons.set(name, button);
    bar.appendChild(button);
  }
  const summary = element("div", "align-summary");
  wrapper.append(stage, bar, summary);
  container.appendChild(wrapper);

  // ── the pictures and the maps ────────────────────────────────────────────

  function load(slot, source) {
    if (source === sources[slot]) return;
    sources[slot] = source;
    pictures[slot] = null;
    if (!source) return;
    const picture = new Image();
    picture.onload = () => {
      if (sources[slot] !== source) return;
      pictures[slot] = picture;
      draw();
    };
    picture.src = source;
  }

  function decodeMap(slot, source) {
    if (source === (maps[slot]?.source ?? "")) return;
    maps[slot] = null;
    tints.delete(slot);
    const turn = ++turns[slot];
    if (!source) return;
    const picture = new Image();
    picture.onload = () => {
      if (turn !== turns[slot]) return;
      const scratch = element("canvas");
      scratch.width = picture.naturalWidth;
      scratch.height = picture.naturalHeight;
      const context = scratch.getContext("2d");
      context.drawImage(picture, 0, 0);
      const rgba = context.getImageData(0, 0, scratch.width, scratch.height).data;
      const gray = new Uint8ClampedArray(scratch.width * scratch.height);
      for (let i = 0; i < gray.length; i++) gray[i] = rgba[i * 4];
      maps[slot] = { source, width: scratch.width, height: scratch.height, gray };
      draw();
    };
    picture.src = source;
  }

  // The map with the gain applied, as a gray canvas the size of the map.
  function tinted(slot) {
    const gain = Number(value.gain ?? DEFAULTS.gain) || DEFAULTS.gain;
    const kept = tints.get(slot);
    if (kept && kept.gain === gain) return kept.layer;
    const map = maps[slot];
    const layer = element("canvas");
    layer.width = map.width;
    layer.height = map.height;
    const context = layer.getContext("2d");
    const picture = context.createImageData(map.width, map.height);
    const pixels = picture.data;
    for (let i = 0; i < map.gray.length; i++) {
      const level = Math.min(1, (map.gray[i] / 255) * gain) * 255;
      const o = i * 4;
      pixels[o] = pixels[o + 1] = pixels[o + 2] = level;
      pixels[o + 3] = 255;
    }
    context.putImageData(picture, 0, 0);
    tints.set(slot, { gain, layer });
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
    const referenceData = typeof value.reference_data === "string" ? value.reference_data : "";
    const alignedData = typeof value.aligned_data === "string" ? value.aligned_data : "";
    load("reference", referenceData);
    load("aligned", alignedData);
    decodeMap("before", typeof value.before_map === "string" ? value.before_map : "");
    decodeMap("after", typeof value.after_map === "string" ? value.after_map : "");

    const ready = !!referenceData && !!alignedData && width > 0 && height > 0;
    canvas.style.display = ready ? "block" : "none";
    message.style.display = ready ? "none" : "flex";
    for (const [name, button] of buttons) {
      button.classList.toggle("active", name === view);
      button.disabled = !ready;
    }

    const context = canvas.getContext("2d");
    context.clearRect(0, 0, canvas.width, canvas.height);
    if (ready) {
      const w = canvas.width;
      const h = canvas.height;
      if (view === "Reference" && pictures.reference) {
        context.drawImage(pictures.reference, 0, 0, w, h);
      } else if (view === "Aligned" && pictures.aligned) {
        context.drawImage(pictures.aligned, 0, 0, w, h);
      } else if ((view === "Before" || view === "After") && maps[view.toLowerCase()]) {
        context.drawImage(tinted(view.toLowerCase()), 0, 0, w, h);
      } else if (view === "Wipe" && pictures.reference && pictures.aligned) {
        const cut = Math.round(w * wipe);
        context.drawImage(pictures.reference, 0, 0, w, h);
        context.save();
        context.beginPath();
        context.rect(cut, 0, w - cut, h);
        context.clip();
        context.drawImage(pictures.aligned, 0, 0, w, h);
        context.restore();
        drawDivider(context, cut, h);
      }
    }
    summary.textContent = ready ? describe() : "";
  }

  function describe() {
    const down = Number(value.shift_down) || 0;
    const right = Number(value.shift_right) || 0;
    const turn = Number(value.rotation) || 0;
    const factor = Number(value.scale) || 1;
    const parts = [`Moved ${signed(down, 1)} px down, ${signed(right, 1)} px right`];
    if (Math.abs(turn) > 0.005) parts.push(`turned ${signed(turn, 2)}°`);
    if (Math.abs(factor - 1) > 0.0005) parts.push(`scaled ${factor.toFixed(4)}`);
    const before = Number(value.before);
    const after = Number(value.after);
    const match = Number.isFinite(before) && Number.isFinite(after) ? `. Match ${before.toFixed(3)} → ${after.toFixed(3)}` : "";
    return parts.join(", ") + match;
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
    return bounds.width ? Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width)) : wipe;
  }

  canvas.addEventListener("pointerdown", (event) => {
    if (view !== "Wipe") return;
    canvas.setPointerCapture(event.pointerId);
    dragging = true;
    wipe = wipeFrom(event);
    draw();
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    wipe = wipeFrom(event);
    draw();
  });
  const endDrag = () => {
    dragging = false;
  };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);

  // ── updates from the framework ───────────────────────────────────────────

  function handleUpdate(newProps) {
    value = newProps.value || {};
    layout();
  }

  function cleanup() {
    turns.before++;
    turns.after++;
    if (resizeWatcher) resizeWatcher.disconnect();
    resizeWatcher = null;
    wrapper.remove();
    delete container._alignInst;
  }

  if (typeof ResizeObserver !== "undefined") {
    resizeWatcher = new ResizeObserver(() => layout());
    resizeWatcher.observe(stage);
  }
  layout();

  container._alignInst = { handleUpdate, cleanup, wrapper };
  return { cleanup, update: handleUpdate };
}
