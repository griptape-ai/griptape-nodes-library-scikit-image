// CompareImages: two images to wipe between, flip between, or see where they differ, before you run the node.
//
// Python compares the images at the node's preview size and sends a map of where they differ: 8-bit grayscale, white
// where they differ most, with no gain applied. This widget applies the node's gain to it, and gain is a synced
// parameter, so the differences brighten as the slider moves with no new comparison. The preview size changes what is
// compared, so Python compares again when it is released. The widget's own value is image_url, other_url, width and
// height (of the first image, which the second is stretched to), map_url, score and message.
//
// The view is only for looking: Wipe splits the two images at a line you drag, A and B show one of them, Difference
// draws the map as the node's output does, and Heat tints the first image red where the images differ.

const STYLE_ID = "compare-images-styles";
const DEFAULT_GAIN = 3;
const HEAT = [255, 60, 60];
const HEAT_ALPHA = 0.85;
const VIEWS = [
  ["wipe", "Wipe"],
  ["a", "A"],
  ["b", "B"],
  ["difference", "Difference"],
  ["heat", "Heat"],
];

function injectStyles() {
  let el = document.getElementById(STYLE_ID);
  if (!el) {
    el = document.createElement("style");
    el.id = STYLE_ID;
    document.head.appendChild(el);
  }
  el.textContent = `
    .cmp-wrap { display:flex; flex-direction:column; gap:6px; width:100%; height:100%; font-size:11px; color:var(--foreground); }
    .cmp-stage { position:relative; flex:1 1 0; min-height:180px; background:var(--muted); border-radius:6px; overflow:hidden; display:flex; align-items:center; justify-content:center; }
    .cmp-frame { position:relative; flex:none; touch-action:none; }
    .cmp-image, .cmp-canvas { position:absolute; inset:0; width:100%; height:100%; display:block; user-select:none; -webkit-user-drag:none; }
    .cmp-divider { position:absolute; top:0; bottom:0; width:0; border-left:2px solid #fff; box-shadow:0 0 0 1px rgba(0,0,0,0.5); pointer-events:none; }
    .cmp-handle { position:absolute; top:50%; width:22px; height:22px; margin:-11px 0 0 -11px; border-radius:50%; background:#fff; box-shadow:0 0 0 1px rgba(0,0,0,0.5); pointer-events:none; }
    .cmp-msg { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; padding:12px; text-align:center; color:var(--muted-foreground); }
    .cmp-bar { display:flex; align-items:center; gap:4px; }
    .cmp-summary { margin-left:auto; color:var(--muted-foreground); }
    .cmp-btn { border:none; border-radius:4px; background:var(--muted); color:var(--foreground); cursor:pointer; padding:3px 9px; height:24px; font-size:11px; font-family:inherit; }
    .cmp-btn:hover { background:var(--accent, rgba(122,157,184,0.2)); }
    .cmp-btn.active { background:rgba(122,157,184,0.25); box-shadow:inset 0 0 0 1px rgba(122,157,184,0.6); }
    .cmp-btn:disabled { opacity:0.4; cursor:default; }
  `;
}

function element(tag, className) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  return el;
}

export default function CompareImages(container, props) {
  if (container._cmpInst?.wrapper?.isConnected) {
    container._cmpInst.handleUpdate(props);
    return { cleanup: container._cmpInst.cleanup, update: container._cmpInst.handleUpdate };
  }

  injectStyles();

  let value = props.value || {};
  let view = "wipe";
  let wipe = 0.5; // where the divider is, from 0 at the left to 1 at the right
  let resizeWatcher = null;
  let mapUrl = ""; // the map that was decoded, and its gray values
  let map = null; // { width, height, gray: Uint8ClampedArray }
  let decoding = 0;

  const wrapper = element("div", "cmp-wrap nodrag nowheel");
  for (const type of ["pointerdown", "mousedown", "keydown", "wheel"]) {
    wrapper.addEventListener(type, (e) => e.stopPropagation());
  }

  const stage = element("div", "cmp-stage");
  const frame = element("div", "cmp-frame");
  const imageA = element("img", "cmp-image");
  const imageB = element("img", "cmp-image");
  for (const image of [imageA, imageB]) image.draggable = false;
  const canvas = element("canvas", "cmp-canvas");
  const divider = element("div", "cmp-divider");
  const handle = element("div", "cmp-handle");
  divider.appendChild(handle);
  frame.append(imageA, imageB, canvas, divider);
  const message = element("div", "cmp-msg");
  stage.append(frame, message);

  const bar = element("div", "cmp-bar");
  const buttons = new Map();
  for (const [name, label] of VIEWS) {
    const button = element("button", "cmp-btn");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", () => {
      view = name;
      draw();
    });
    buttons.set(name, button);
    bar.appendChild(button);
  }
  const summary = element("span", "cmp-summary");
  bar.appendChild(summary);

  wrapper.append(stage, bar);
  container.appendChild(wrapper);

  // ── the wipe line ────────────────────────────────────────────────────────

  function moveWipe(event) {
    const bounds = frame.getBoundingClientRect();
    if (!bounds.width) return;
    wipe = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
    drawWipe();
  }

  frame.addEventListener("pointerdown", (event) => {
    if (view !== "wipe") return;
    frame.setPointerCapture(event.pointerId);
    moveWipe(event);
  });
  frame.addEventListener("pointermove", (event) => {
    if (view === "wipe" && frame.hasPointerCapture(event.pointerId)) moveWipe(event);
  });

  function drawWipe() {
    const percent = wipe * 100;
    imageB.style.clipPath = view === "wipe" ? `inset(0 0 0 ${percent}%)` : "none";
    divider.style.left = `${percent}%`;
  }

  // ── the map of differences ───────────────────────────────────────────────

  function decodeMap(url) {
    if (url === mapUrl) return;
    mapUrl = url;
    map = null;
    const turn = ++decoding;
    if (!url) return;
    const picture = new Image();
    picture.onload = () => {
      if (turn !== decoding) return;
      const scratch = element("canvas");
      scratch.width = picture.naturalWidth;
      scratch.height = picture.naturalHeight;
      const context = scratch.getContext("2d");
      context.drawImage(picture, 0, 0);
      const rgba = context.getImageData(0, 0, scratch.width, scratch.height).data;
      const gray = new Uint8ClampedArray(scratch.width * scratch.height);
      for (let i = 0; i < gray.length; i++) gray[i] = rgba[i * 4];
      map = { width: scratch.width, height: scratch.height, gray };
      draw();
    };
    picture.src = url;
  }

  function drawMap() {
    if (!map || (view !== "difference" && view !== "heat")) return;
    const gain = Number(value.gain ?? DEFAULT_GAIN) || DEFAULT_GAIN;
    if (canvas.width !== map.width || canvas.height !== map.height) {
      canvas.width = map.width;
      canvas.height = map.height;
    }
    const context = canvas.getContext("2d");
    const picture = context.createImageData(map.width, map.height);
    const pixels = picture.data;
    const heat = view === "heat";
    for (let i = 0; i < map.gray.length; i++) {
      const level = Math.min(1, (map.gray[i] / 255) * gain);
      const o = i * 4;
      if (heat) {
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
  }

  // ── drawing ──────────────────────────────────────────────────────────────

  function size() {
    return [Number(value.width) || 0, Number(value.height) || 0];
  }

  function layout() {
    const [width, height] = size();
    if (width > 0 && height > 0) {
      const scale = Math.min((stage.clientWidth || 480) / width, (stage.clientHeight || 360) / height);
      frame.style.width = `${Math.round(width * scale)}px`;
      frame.style.height = `${Math.round(height * scale)}px`;
    }
    draw();
  }

  function setSource(image, url) {
    if (image.getAttribute("src") === url) return;
    if (url) image.setAttribute("src", url);
    else image.removeAttribute("src");
  }

  function draw() {
    const [width, height] = size();
    const urlA = typeof value.image_url === "string" ? value.image_url : "";
    const urlB = typeof value.other_url === "string" ? value.other_url : "";
    const hasA = !!urlA && width > 0 && height > 0;
    const hasBoth = hasA && !!urlB;
    const ready = hasBoth && !!map;
    decodeMap(typeof value.map_url === "string" ? value.map_url : "");

    // Only the first image is there until the second arrives. The comparison views need the second and the map.
    const shown = hasBoth ? view : "a";
    frame.style.display = hasA ? "block" : "none";
    message.style.display = hasA ? "none" : "flex";
    message.textContent = "Connect two images to compare them.";
    for (const [name, button] of buttons) {
      button.classList.toggle("active", name === shown);
      button.disabled = name !== "a" && !hasBoth;
    }
    setSource(imageA, urlA);
    setSource(imageB, hasBoth ? urlB : "");
    imageA.style.visibility = shown === "b" || shown === "difference" ? "hidden" : "visible";
    imageB.style.visibility = shown === "wipe" || shown === "b" ? "visible" : "hidden";
    divider.style.display = shown === "wipe" ? "block" : "none";
    canvas.style.display = ready && (shown === "difference" || shown === "heat") ? "block" : "none";
    drawWipe();
    drawMap();

    const score = Number(value.score);
    summary.textContent =
      hasBoth && Number.isFinite(score) && map
        ? `Similarity ${score.toFixed(3)} at ${Math.max(map.width, map.height)} px`
        : value.message || "";
  }

  function handleUpdate(newProps) {
    value = newProps.value || {};
    layout();
  }

  function cleanup() {
    decoding++;
    if (resizeWatcher) resizeWatcher.disconnect();
    resizeWatcher = null;
    wrapper.remove();
    delete container._cmpInst;
  }

  if (typeof ResizeObserver !== "undefined") {
    resizeWatcher = new ResizeObserver(() => layout());
    resizeWatcher.observe(stage);
  }
  layout();

  container._cmpInst = { handleUpdate, cleanup, wrapper };
  return { cleanup, update: handleUpdate };
}
