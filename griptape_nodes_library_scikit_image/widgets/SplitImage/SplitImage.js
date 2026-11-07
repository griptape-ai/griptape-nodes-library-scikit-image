// SplitImage: the image with the pieces Split Image found outlined on it.
//
// Python scans the image and sends the candidates: blobs of marks, each with a box, a colour, its sizes and how many
// image edges it touches. This widget works out which are pieces and which are dropped, so Minimum size and Ignore
// corner pieces change the picture while a slider moves. Sensitivity and Join distance change what the blobs are, so
// Python scans again when they are released. All five are parameters of the node, listed in the widget's
// synced_parameters, and the controls for them are on the node. The widget's own value is image_url, width and height,
// candidates, and excluded, the boxes the user switched off by clicking them. Boxes are [left, top, right, bottom] in
// the image's pixels, and sizes are percentages of the image's longer side.

import { classify, fitSize, numbering, paddedBox, pieceAt, toggleExcluded } from "./_boxes.js";

const STYLE_ID = "split-image-styles";
const SVG_NS = "http://www.w3.org/2000/svg";
let instances = 0; // each widget needs its own SVG ids, because a url(#id) finds the first element with that id on the page
const DROPPED_COLOUR = "#e62828";
const OFF_COLOUR = "#9aa0a6";

// The node's defaults, used until the widget has a value for a setting.
const DEFAULTS = { padding: 1.5, min_size: 3, ignore_corner_pieces: true };

function injectStyles() {
  let el = document.getElementById(STYLE_ID);
  if (!el) {
    el = document.createElement("style");
    el.id = STYLE_ID;
    document.head.appendChild(el);
  }
  el.textContent = `
    .split-wrap { display:flex; flex-direction:column; gap:6px; width:100%; height:100%; font-size:11px; color:var(--foreground); }
    .split-stage { position:relative; flex:1 1 0; min-height:180px; background:var(--muted); border-radius:6px; overflow:hidden; display:flex; align-items:center; justify-content:center; }
    .split-frame { position:relative; flex:none; }
    .split-image { position:absolute; inset:0; width:100%; height:100%; display:block; user-select:none; -webkit-user-drag:none; }
    .split-overlay { position:absolute; inset:0; width:100%; height:100%; }
    .split-piece { cursor:pointer; fill:transparent; }
    .split-piece:hover { fill:rgba(255,255,255,0.14); }
    .split-msg { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; padding:12px; text-align:center; color:var(--muted-foreground); }
    .split-summary { color:var(--muted-foreground); }
  `;
}

function svg(tag, attributes = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attributes)) el.setAttribute(key, String(value));
  return el;
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

export default function SplitImage(container, props) {
  if (container._splitInst?.wrapper?.isConnected) {
    container._splitInst.handleUpdate(props);
    return { cleanup: container._splitInst.cleanup, update: container._splitInst.handleUpdate };
  }

  injectStyles();
  const hatchId = `split-hatch-${++instances}`;
  const clearId = `split-clear-${instances}`;

  let value = props.value || {};
  let onChange = props.onChange;
    let disabled = !!props.disabled;
  let resizeWatcher = null;

  // ── DOM ──────────────────────────────────────────────────────────────────

  const wrapper = document.createElement("div");
  wrapper.className = "split-wrap nodrag nowheel";
  for (const type of ["pointerdown", "mousedown", "keydown", "wheel"]) {
    wrapper.addEventListener(type, (e) => e.stopPropagation());
  }

  const stage = document.createElement("div");
  stage.className = "split-stage";
  const frame = document.createElement("div");
  frame.className = "split-frame";
  const image = document.createElement("img");
  image.className = "split-image";
  image.draggable = false;
  const overlay = svg("svg", { class: "split-overlay", preserveAspectRatio: "none" });
  frame.append(image, overlay);
  const message = document.createElement("div");
  message.className = "split-msg";
  message.textContent = "Connect an image to see the pieces.";
  stage.append(frame, message);

  const summary = document.createElement("div");
  summary.className = "split-summary";

  wrapper.append(stage, summary);
  container.appendChild(wrapper);

  // ── drawing ──────────────────────────────────────────────────────────────

  function setting(name) {
    const incoming = value[name];
    return incoming === undefined || incoming === null ? DEFAULTS[name] : Number.isNaN(incoming) ? DEFAULTS[name] : incoming;
  }

  function candidates() {
    return Array.isArray(value.candidates) ? value.candidates : [];
  }

  function size() {
    return [Number(value.width) || 0, Number(value.height) || 0];
  }

  function layout() {
    const [width, height] = size();
    const [frameWidth, frameHeight] = fitSize(stage.clientWidth || 480, stage.clientHeight || 360, width, height);
    frame.style.width = `${frameWidth}px`;
    frame.style.height = `${frameHeight}px`;
    draw();
  }

  function draw() {
    const [width, height] = size();
    const url = typeof value.image_url === "string" ? value.image_url : "";
    const hasImage = !!url && width > 0 && height > 0;
    message.style.display = hasImage ? "none" : "flex";
    frame.style.display = hasImage ? "block" : "none";
    if (image.getAttribute("src") !== url) {
      if (url) image.setAttribute("src", url);
      else image.removeAttribute("src");
    }
    overlay.replaceChildren();
    if (!hasImage) {
      summary.textContent = "";
      return;
    }

    const frameWidth = frame.clientWidth || width;
    const perPixel = width / frameWidth; // image pixels in one screen pixel
    const { kept: keptCandidates, dropped: droppedCandidates } = classify(candidates(), setting("min_size"), !!setting("ignore_corner_pieces"));
    const pieces = numbering(keptCandidates, excludedBoxes());
    const dropped = droppedCandidates.map((candidate) => candidate.box);
    const padding = Number(setting("padding")) || 0;
    const crops = pieces.map((piece) => paddedBox(piece.box, padding, width, height));
    overlay.setAttribute("viewBox", `0 0 ${width} ${height}`);

    // Dropped boxes are hatched in red, except where a kept piece's crop sits over them.
    const defs = svg("defs");
    const hatch = svg("pattern", {
      id: hatchId,
      patternUnits: "userSpaceOnUse",
      width: 9 * perPixel,
      height: 9 * perPixel,
      patternTransform: "rotate(45)",
    });
    hatch.appendChild(svg("rect", { width: 9 * perPixel, height: 9 * perPixel, fill: "rgba(230,40,40,0.16)" }));
    hatch.appendChild(svg("line", { x1: 0, y1: 0, x2: 0, y2: 9 * perPixel, stroke: DROPPED_COLOUR, "stroke-width": 1.2 * perPixel }));
    const clear = svg("mask", { id: clearId, maskUnits: "userSpaceOnUse", x: 0, y: 0, width, height });
    clear.appendChild(svg("rect", { x: 0, y: 0, width, height, fill: "white" }));
    for (let i = 0; i < pieces.length; i++) {
      if (pieces[i].off) continue;
      const [left, top, right, bottom] = crops[i];
      clear.appendChild(svg("rect", { x: left, y: top, width: right - left, height: bottom - top, fill: "black" }));
    }
    defs.append(hatch, clear);
    overlay.appendChild(defs);

    const droppedLayer = svg("g", { mask: `url(#${clearId})`, "pointer-events": "none" });
    for (const [left, top, right, bottom] of dropped) {
      droppedLayer.appendChild(svg("rect", { x: left, y: top, width: right - left, height: bottom - top, fill: `url(#${hatchId})` }));
    }
    overlay.appendChild(droppedLayer);
    for (const [left, top, right, bottom] of dropped) {
      overlay.appendChild(svg("rect", {
        x: left, y: top, width: right - left, height: bottom - top,
        fill: "none", stroke: DROPPED_COLOUR, "stroke-width": 2, "vector-effect": "non-scaling-stroke", "pointer-events": "none",
      }));
    }

    const fontSize = 13 * perPixel;
    pieces.forEach((piece, index) => {
      const [left, top, right, bottom] = piece.box;
      const colour = piece.off ? OFF_COLOUR : piece.colour || "#7a9db8";
      const group = svg("g", { opacity: piece.off ? 0.55 : 1 });
      if (padding > 0 && !piece.off) {
        const [cropLeft, cropTop, cropRight, cropBottom] = crops[index];
        group.appendChild(svg("rect", {
          x: cropLeft, y: cropTop, width: cropRight - cropLeft, height: cropBottom - cropTop,
          fill: "none", stroke: colour, "stroke-width": 2, "stroke-dasharray": "6 5",
          "vector-effect": "non-scaling-stroke", "pointer-events": "none",
        }));
      }
      const box = svg("rect", {
        class: "split-piece", x: left, y: top, width: right - left, height: bottom - top,
        stroke: colour, "stroke-width": 2, "stroke-dasharray": piece.off ? "3 4" : "none", "vector-effect": "non-scaling-stroke",
      });
      const title = svg("title");
      title.textContent = piece.off
        ? "Left out. Click to bring it back."
        : `Piece ${piece.number}, ${right - left} by ${bottom - top} pixels. Click to leave it out.`;
      box.appendChild(title);
      group.appendChild(box);
      const text = piece.off ? "×" : String(piece.number);
      const labelWidth = (text.length * 0.62 + 0.7) * fontSize;
      group.appendChild(svg("rect", {
        x: left, y: top, width: labelWidth, height: fontSize * 1.3, fill: colour, "pointer-events": "none",
      }));
      const label = svg("text", {
        x: left + labelWidth / 2, y: top + fontSize * 1.02, "text-anchor": "middle",
        "font-size": fontSize, "font-weight": 700, fill: "#000", "pointer-events": "none",
      });
      label.textContent = text;
      group.appendChild(label);
      overlay.appendChild(group);
    });

    const kept = pieces.filter((piece) => !piece.off).length;
    const off = pieces.length - kept;
    const parts = [plural(kept, "piece")];
    if (off) parts.push(`${off} left out`);
    if (dropped.length) parts.push(`${dropped.length} dropped`);
    summary.textContent = `${parts.join(", ")}. Click a piece to leave it out.`;
  }

  function excludedBoxes() {
    return Array.isArray(value.excluded) ? value.excluded : [];
  }

  overlay.addEventListener("click", (event) => {
    if (disabled) return;
    const [width, height] = size();
    const bounds = overlay.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const x = ((event.clientX - bounds.left) / bounds.width) * width;
    const y = ((event.clientY - bounds.top) / bounds.height) * height;
    const piece = pieceAt(classify(candidates(), setting("min_size"), !!setting("ignore_corner_pieces")).kept, x, y);
    if (!piece) return;
    value = { ...value, excluded: toggleExcluded(excludedBoxes(), piece.box) };
    draw();
    onChange?.(value);
  });

  // ── updates from the framework ───────────────────────────────────────────

  function handleUpdate(newProps) {
    onChange = newProps.onChange;
    disabled = !!newProps.disabled;
    value = newProps.value || {};
    layout();
  }

  function cleanup() {
    if (resizeWatcher) resizeWatcher.disconnect();
    resizeWatcher = null;
    wrapper.remove();
    delete container._splitInst;
  }

  if (typeof ResizeObserver !== "undefined") {
    resizeWatcher = new ResizeObserver(() => layout());
    resizeWatcher.observe(stage);
  }
  layout();

  container._splitInst = { handleUpdate, cleanup, wrapper };
  return { cleanup, update: handleUpdate };
}
