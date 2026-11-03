"""The widget previews the wobble in JavaScript, so it has to give the same numbers as the node's Python."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from griptape_nodes_library_scikit_image import noise

WIDGET = Path(__file__).parent.parent / "griptape_nodes_library_scikit_image" / "widgets" / "BoilingLines"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node.js is needed to run the widget's JavaScript."
)

SCRIPT = """
import { hashValue, makeLattice, pushAt } from "./_noise.js";
const { cases, points } = JSON.parse(process.argv[1]);
const result = { hashes: [], pushes: [] };
for (const [x, y, key, seed] of cases) result.hashes.push(hashValue(x, y, key, seed));
for (const [width, height, size, frame, seed, amplitude] of points.map((p) => p.setup)) {
  const lattice = makeLattice(width, height, size, frame, seed);
  const out = [0, 0];
  result.pushes.push(points.filter((p) => p.setup[0] === width && p.setup[3] === frame && p.setup[4] === seed)
    .flatMap((p) => { pushAt(lattice, p.x, p.y, amplitude, out); return [[out[0], out[1]]]; }));
}
console.log(JSON.stringify(result));
"""


def run_widget(cases, points):
    done = subprocess.run(
        ["node", "--input-type=module", "-e", SCRIPT, json.dumps({"cases": cases, "points": points})],
        cwd=WIDGET,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout)


def test_the_hash_matches_between_python_and_javascript():
    cases = [
        (x, y, key, seed)
        for x in (0, 1, 7, 300)
        for y in (0, 2, 55)
        for key in (0, 1, 9, 191)
        for seed in (0, 1, 12345)
    ]
    expected = [float(noise.lattice(y + 1, x + 1, key, seed)[y, x]) for x, y, key, seed in cases]
    got = run_widget(cases, [])["hashes"]
    assert np.allclose(got, expected, atol=1e-9)


@pytest.mark.parametrize(
    ("width", "height", "size", "frame", "seed", "amplitude"),
    [(400, 300, 40.0, 0, 1, 10.0), (387, 540, 10.8, 3, 42, 1.62), (1326, 1852, 37.04, 7, 99999, 5.56)],
)
def test_the_push_matches_between_python_and_javascript(width, height, size, frame, seed, amplitude):
    down, right = noise.displacement(height, width, frame, seed, amplitude, size)
    rng = np.random.default_rng(5)
    xs = rng.integers(0, width, 60)
    ys = rng.integers(0, height, 60)
    points = [
        {"x": int(x), "y": int(y), "setup": [width, height, size, frame, seed, amplitude]}
        for x, y in zip(xs, ys, strict=True)
    ]
    got = np.array(run_widget([], points)["pushes"][0])
    expected = np.stack([down[ys, xs], right[ys, xs]], axis=-1)
    assert np.allclose(got, expected, atol=1e-6)


HARNESS = """
const puts = [];
const context = {
  putImageData(data) { puts.push(Uint8ClampedArray.from(data.data)); }, drawImage() {}, clearRect() {},
  getImageData(x, y, w, h) { const d = new Uint8ClampedArray(w * h * 4); for (let i = 0; i < d.length; i++) d[i] = (i * 7) % 251; return { width: w, height: h, data: d }; },
  createImageData(w, h) { return { width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }; },
  beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, strokeStyle: "", lineWidth: 1,
};
function element(tag) {
  const listeners = {};
  return {
    tag, style: {}, children: [], className: "", textContent: "", value: "", listeners, isConnected: true,
    get clientWidth() { return this.className === "boil-stage" ? SIZES.width : undefined; },
    get clientHeight() { return this.className === "boil-stage" ? SIZES.height : undefined; },
    classList: { toggle() {}, add() {} },
    appendChild(child) { this.children.push(child); return child; },
    addEventListener(type, fn) { (listeners[type] ||= []).push(fn); },
    getContext() { return context; },
    remove() { this.isConnected = false; },
  };
}
const SIZES = JSON.parse(process.env.BOIL_SIZES || "{}");
globalThis.document = { createElement: element, getElementById: () => null, head: element("head") };
globalThis.Image = class { set src(v) { queueMicrotask(() => { this.naturalWidth = 387; this.naturalHeight = 540; this.onload(); }); } };
globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
const tick = () => new Promise((resolve) => setTimeout(resolve, 20));
const all = (node) => [node, ...node.children.flatMap(all)];
const fire = (node, type) => (node.listeners[type] || []).forEach((fn) => fn({ stopPropagation() {} }));

const { default: BoilingLines } = await import("./BoilingLines.js");
const emitted = [];
const container = element("div");
const handle = BoilingLines(container, {
  value: { image_url: "http://example/a.png", width: 387, height: 540, frame_count: 8, amplitude: 0.5, wobble_size: 2, seed: 1 },
  onChange: (v) => emitted.push(v),
  disabled: false,
});
await tick();
const log = { renders: puts.length, canvas: all(container).find((n) => n.tag === "canvas") && true };
const canvasNode = all(container).find((n) => n.tag === "canvas");
log.canvasSize = [canvasNode.style.width, canvasNode.style.height];

const nodes = all(container);
const ranges = nodes.filter((n) => n.tag === "input" && n.type === "range");
const amount = ranges.find((n) => n.step === "0.01");
const scrub = ranges.find((n) => n.max === "8" && n.step === "1");
const buttons = nodes.filter((n) => n.tag === "button");
const named = (text) => buttons.find((b) => b.textContent === text);

const resultFrame1 = puts[puts.length - 1];
scrub.value = "2"; fire(scrub, "input"); fire(scrub, "change"); await tick();
log.frameChangesTheResult = Buffer.compare(Buffer.from(resultFrame1), Buffer.from(puts[puts.length - 1])) !== 0;
amount.value = "2"; fire(amount, "input"); fire(amount, "change"); await tick();
log.emittedAmount = emitted[emitted.length - 1].amplitude;
log.emittedFrame = emitted[emitted.length - 1].frame;
named("Original").listeners.click[0](); await tick();
log.originalView = emitted[emitted.length - 1].view;
named("Noise").listeners.click[0](); await tick();
log.noiseView = emitted[emitted.length - 1].view;
named("Random").listeners.click[0](); await tick();
log.seedChanged = emitted[emitted.length - 1].seed !== 1;
named("Play").listeners.click[0](); await new Promise((resolve) => setTimeout(resolve, 200));
log.playing = named("Pause") !== undefined || buttons.some((b) => b.textContent === "Pause");
buttons.find((b) => b.textContent === "Pause").listeners.click[0]();
log.pausedEmitted = emitted.length;

// the framework echoing a new image and older settings back
handle.update({ value: { ...emitted[emitted.length - 1], image_url: "http://example/b.png" }, onChange: (v) => emitted.push(v), disabled: false });
await tick();
log.reloaded = true;
// calling the widget again on the same container updates in place
const again = BoilingLines(container, { value: emitted[emitted.length - 1], onChange: () => {}, disabled: false });
log.sameInstance = typeof again.update === "function" && container.children.length === 1;
handle.cleanup();
log.cleaned = container._boilInst === undefined;
console.log(JSON.stringify(log));
"""


def run_harness(tmp_path, sizes):
    script = tmp_path / "harness.mjs"
    script.write_text(HARNESS.replace('"./BoilingLines.js"', json.dumps((WIDGET / "BoilingLines.js").as_uri())))
    env = {**os.environ, "BOIL_SIZES": json.dumps(sizes)}
    return subprocess.run(["node", str(script)], capture_output=True, text=True, check=False, env=env)


@pytest.mark.parametrize(
    ("area_width", "area_height", "expected"),
    [
        (300, 400, ("286px", "400px")),  # a tall image in a narrow node is as tall as the stage allows
        (600, 300, ("215px", "300px")),  # a wide stage: the height is the limit, so the image never overflows
        (800, 1000, ("716px", "1000px")),  # a bigger node gives a bigger preview
        (200, 180, ("129px", "180px")),  # a small one gives a small preview
    ],
)
def test_the_preview_scales_with_the_stage_and_always_fits_in_it(tmp_path, area_width, area_height, expected):
    done = run_harness(tmp_path, {"width": area_width, "height": area_height})
    assert done.returncode == 0, done.stderr
    width, height = json.loads(done.stdout.strip().splitlines()[-1])["canvasSize"]
    assert (width, height) == expected
    assert int(width.removesuffix("px")) <= area_width
    assert int(height.removesuffix("px")) <= area_height


def test_the_widget_builds_renders_and_responds_in_a_fake_page(tmp_path):
    done = run_harness(tmp_path, {"width": 300, "height": 400})
    assert done.returncode == 0, done.stderr
    log = json.loads(done.stdout.strip().splitlines()[-1])
    assert log["renders"] >= 1
    assert log["frameChangesTheResult"]
    assert log["emittedAmount"] == 2
    assert log["emittedFrame"] == 2
    assert log["originalView"] == "original"
    assert log["noiseView"] == "noise"
    assert log["seedChanged"]
    assert log["playing"]
    assert log["sameInstance"]
    assert log["cleaned"]


WARP_SCRIPT = """
import { makeLattice, warpPixels } from "./_noise.js";
const { pixels, width, height, size, frame, seed, amplitude } = JSON.parse(process.argv[1]);
const lattice = makeLattice(width, height, size, frame, seed);
const target = new Float64Array(pixels.length);
warpPixels(Uint8ClampedArray.from(pixels), width, height, lattice, amplitude, 1, target);
console.log(JSON.stringify(Array.from(target, (v) => Math.round(v))));
"""


@pytest.mark.parametrize(
    ("frame", "seed", "amplitude_percent", "size_percent"), [(0, 1, 3.0, 12.0), (5, 77, 6.0, 20.0)]
)
def test_the_widget_warp_matches_the_frames_the_node_saves(frame, seed, amplitude_percent, size_percent):
    import PIL.Image

    from griptape_nodes_library_scikit_image import tools

    width, height = 96, 64
    rng = np.random.default_rng(2)
    rgb = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
    image = PIL.Image.fromarray(rgb)
    saved = np.asarray(tools.boiling_frames(image, frame + 1, amplitude_percent, size_percent, seed)[frame]).astype(int)

    rgba = np.concatenate([rgb, np.full((height, width, 1), 255, dtype=np.uint8)], axis=-1)
    longer = max(width, height)
    done = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            WARP_SCRIPT,
            json.dumps(
                {
                    "pixels": rgba.ravel().tolist(),
                    "width": width,
                    "height": height,
                    "size": size_percent / 100 * longer,
                    "frame": frame,
                    "seed": seed,
                    "amplitude": amplitude_percent / 100 * longer,
                }
            ),
        ],
        cwd=WIDGET,
        capture_output=True,
        text=True,
        check=True,
    )
    previewed = np.array(json.loads(done.stdout)).reshape(height, width, 4)[..., :3]
    assert np.abs(previewed - saved).max() <= 1
