// LinesToSvg: the traced shapes on your image, before you run the node.
//
// Python traces the image and sends the path, the same one the node saves into the SVG. This widget draws it with the
// node's fill colour, which is a synced parameter, so changing the colour needs no new trace. Sensitivity and Simplify
// decide the trace, so Python traces again when they are released. The widget's own value is image_url, width and
// height, path (the SVG path data), count (how many shapes) and message (why there is no path).
//
// The view is only for looking: Trace draws the shapes alone, Over image draws them partly see-through on the image,
// and Image is the image.

const STYLE_ID = "lines-to-svg-styles";
const SVG_NS = "http://www.w3.org/2000/svg";
const DEFAULT_FILL = "#000000";
const OVER_OPACITY = 0.55;
const VIEWS = [
  ["trace", "Trace"],
  ["over", "Over image"],
  ["image", "Image"],
];

function injectStyles() {
  let el = document.getElementById(STYLE_ID);
  if (!el) {
    el = document.createElement("style");
    el.id = STYLE_ID;
    document.head.appendChild(el);
  }
  el.textContent = `
    .trace-wrap { display:flex; flex-direction:column; gap:6px; width:100%; height:100%; font-size:11px; color:var(--foreground); }
    .trace-stage { position:relative; flex:1 1 0; min-height:180px; background:var(--muted); border-radius:6px; overflow:hidden; display:flex; align-items:center; justify-content:center; }
    .trace-frame { position:relative; flex:none; }
    .trace-image { position:absolute; inset:0; width:100%; height:100%; display:block; user-select:none; -webkit-user-drag:none; }
    .trace-overlay { position:absolute; inset:0; width:100%; height:100%; }
    .trace-msg { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; padding:12px; text-align:center; color:var(--muted-foreground); }
    .trace-bar { display:flex; align-items:center; gap:4px; }
    .trace-summary { margin-left:auto; color:var(--muted-foreground); }
    .trace-btn { border:none; border-radius:4px; background:var(--muted); color:var(--foreground); cursor:pointer; padding:3px 9px; height:24px; font-size:11px; font-family:inherit; }
    .trace-btn:hover { background:var(--accent, rgba(122,157,184,0.2)); }
    .trace-btn.active { background:rgba(122,157,184,0.25); box-shadow:inset 0 0 0 1px rgba(122,157,184,0.6); }
  `;
}

function luminance(hex) {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex || "");
  if (!match) return 0;
  const n = parseInt(match[1], 16);
  return 0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255);
}

export default function LinesToSvg(container, props) {
  if (container._traceInst?.wrapper?.isConnected) {
    container._traceInst.handleUpdate(props);
    return { cleanup: container._traceInst.cleanup, update: container._traceInst.handleUpdate };
  }

  injectStyles();

  let value = props.value || {};
  let view = "over";
  let resizeWatcher = null;

  const wrapper = document.createElement("div");
  wrapper.className = "trace-wrap nodrag nowheel";
  for (const type of ["pointerdown", "mousedown", "keydown", "wheel"]) {
    wrapper.addEventListener(type, (e) => e.stopPropagation());
  }

  const stage = document.createElement("div");
  stage.className = "trace-stage";
  const frame = document.createElement("div");
  frame.className = "trace-frame";
  const image = document.createElement("img");
  image.className = "trace-image";
  image.draggable = false;
  const overlay = document.createElementNS(SVG_NS, "svg");
  overlay.setAttribute("class", "trace-overlay");
  overlay.setAttribute("preserveAspectRatio", "none");
  const backdrop = document.createElementNS(SVG_NS, "rect");
  const shapes = document.createElementNS(SVG_NS, "path");
  shapes.setAttribute("fill-rule", "evenodd");
  overlay.append(backdrop, shapes);
  frame.append(image, overlay);
  const message = document.createElement("div");
  message.className = "trace-msg";
  stage.append(frame, message);

  const bar = document.createElement("div");
  bar.className = "trace-bar";
  const buttons = new Map();
  for (const [name, label] of VIEWS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "trace-btn";
    button.textContent = label;
    button.addEventListener("click", () => {
      view = name;
      draw();
    });
    buttons.set(name, button);
    bar.appendChild(button);
  }
  const summary = document.createElement("span");
  summary.className = "trace-summary";
  bar.appendChild(summary);

  wrapper.append(stage, bar);
  container.appendChild(wrapper);

  function size() {
    return [Number(value.width) || 0, Number(value.height) || 0];
  }

  function layout() {
    const [width, height] = size();
    const areaWidth = stage.clientWidth || 480;
    const areaHeight = stage.clientHeight || 360;
    if (width > 0 && height > 0) {
      const scale = Math.min(areaWidth / width, areaHeight / height);
      frame.style.width = `${Math.round(width * scale)}px`;
      frame.style.height = `${Math.round(height * scale)}px`;
    }
    draw();
  }

  function draw() {
    const [width, height] = size();
    const url = typeof value.image_url === "string" ? value.image_url : "";
    const hasImage = !!url && width > 0 && height > 0;
    const path = typeof value.path === "string" ? value.path : "";
    const fill = value.fill_colour || DEFAULT_FILL;

    frame.style.display = hasImage ? "block" : "none";
    message.style.display = hasImage && !(view !== "image" && value.message) ? "none" : "flex";
    message.textContent = hasImage ? value.message || "" : "Connect an image to see the trace.";
    for (const [name, button] of buttons) button.classList.toggle("active", name === view);
    if (image.getAttribute("src") !== url) {
      if (url) image.setAttribute("src", url);
      else image.removeAttribute("src");
    }
    if (!hasImage) {
      summary.textContent = "";
      return;
    }

    overlay.setAttribute("viewBox", `0 0 ${width} ${height}`);
    // The trace alone sits on a backdrop that contrasts with the fill, so a white fill is still visible.
    backdrop.setAttribute("x", 0);
    backdrop.setAttribute("y", 0);
    backdrop.setAttribute("width", width);
    backdrop.setAttribute("height", height);
    backdrop.setAttribute("fill", luminance(fill) > 150 ? "#282828" : "#ffffff");
    backdrop.style.display = view === "trace" ? "block" : "none";
    shapes.setAttribute("fill", fill);
    shapes.setAttribute("d", path);
    shapes.style.display = view === "image" ? "none" : "block";
    shapes.setAttribute("fill-opacity", view === "over" ? OVER_OPACITY : 1); // the drawing shows through
    image.style.opacity = view === "trace" ? "0" : "1";
    summary.textContent = value.count ? `${value.count} shape${value.count === 1 ? "" : "s"}` : "";
  }

  function handleUpdate(newProps) {
    value = newProps.value || {};
    layout();
  }

  function cleanup() {
    if (resizeWatcher) resizeWatcher.disconnect();
    resizeWatcher = null;
    wrapper.remove();
    delete container._traceInst;
  }

  if (typeof ResizeObserver !== "undefined") {
    resizeWatcher = new ResizeObserver(() => layout());
    resizeWatcher.observe(stage);
  }
  layout();

  container._traceInst = { handleUpdate, cleanup, wrapper };
  return { cleanup, update: handleUpdate };
}
