// The wobble behind Boiling Lines, in JavaScript.
//
// This must give the same numbers as griptape_nodes_library_scikit_image/noise.py, so the preview in the widget matches
// the frames the node saves. Both use the same 32-bit integer hash, the same lattice and the same smoothstep
// interpolation, and no random number generator. Change one and change the other. tests/test_boil_widget.py compares them.

const HASH_X = 374761393;
const HASH_Y = 668265263;
const HASH_KEY = 2246822519;
const HASH_SEED = 3266489917;
const HASH_MIX = 1274126177;

const mul = (a, b) => Math.imul(a, b) >>> 0;

// A value from -1 to 1 for one lattice point.
export function hashValue(x, y, key, seed) {
  let h = (mul(x, HASH_X) + mul(y, HASH_Y) + mul(key, HASH_KEY) + mul(seed, HASH_SEED)) >>> 0;
  h = mul((h ^ (h >>> 13)) >>> 0, HASH_MIX);
  h = (h ^ (h >>> 16)) >>> 0;
  return (h / 4294967295) * 2 - 1;
}

// The lattice for one frame: a grid of down and right pushes, one per `size` pixels, covering width x height.
export function makeLattice(width, height, size, frame, seed) {
  const step = Math.max(size, 1);
  const rows = Math.floor(height / step) + 3;
  const columns = Math.floor(width / step) + 3;
  const down = new Float64Array(rows * columns);
  const right = new Float64Array(rows * columns);
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < columns; x++) {
      down[y * columns + x] = hashValue(x, y, frame * 2, seed);
      right[y * columns + x] = hashValue(x, y, frame * 2 + 1, seed);
    }
  }
  return { rows, columns, step, down, right };
}

const smooth = (t) => t * t * (3 - 2 * t);

// The push at a point, in the pixels of the original image, written to out[0] (down) and out[1] (right).
export function pushAt(lattice, x, y, amplitude, out) {
  const u = x / lattice.step;
  const v = y / lattice.step;
  const column = Math.floor(u);
  const row = Math.floor(v);
  const sx = smooth(u - column);
  const sy = smooth(v - row);
  const at = row * lattice.columns + column;
  const next = at + lattice.columns;
  for (let k = 0; k < 2; k++) {
    const grid = k === 0 ? lattice.down : lattice.right;
    const top = grid[at] * (1 - sx) + grid[at + 1] * sx;
    const bottom = grid[next] * (1 - sx) + grid[next + 1] * sx;
    out[k] = (top * (1 - sy) + bottom * sy) * amplitude;
  }
}

// Warp RGBA pixels by the wobble. The pixels are a preview of an image `scale` times the size of the original, and
// the amplitude and the lattice are in original pixels. Each output pixel reads the source where the wobble points,
// with bilinear sampling and the edge pixels repeated, as the node does.
export function warpPixels(source, width, height, lattice, amplitude, scale, target) {
  const push = [0, 0];
  const maxX = width - 1;
  const maxY = height - 1;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      pushAt(lattice, x / scale, y / scale, amplitude, push);
      const sx = Math.min(Math.max(x + push[1] * scale, 0), maxX);
      const sy = Math.min(Math.max(y + push[0] * scale, 0), maxY);
      const x0 = Math.floor(sx);
      const y0 = Math.floor(sy);
      const x1 = Math.min(x0 + 1, maxX);
      const y1 = Math.min(y0 + 1, maxY);
      const fx = sx - x0;
      const fy = sy - y0;
      const i00 = (y0 * width + x0) * 4;
      const i10 = (y0 * width + x1) * 4;
      const i01 = (y1 * width + x0) * 4;
      const i11 = (y1 * width + x1) * 4;
      const out = (y * width + x) * 4;
      for (let c = 0; c < 4; c++) {
        const topRow = source[i00 + c] * (1 - fx) + source[i10 + c] * fx;
        const bottomRow = source[i01 + c] * (1 - fx) + source[i11 + c] * fx;
        target[out + c] = topRow * (1 - fy) + bottomRow * fy;
      }
    }
  }
}

// How strongly the noise view shows a push. Small pushes are boosted so they can be seen, and the curve still grows with
// the push all the way up to the reference, so changing the Amount visibly changes the picture.
export function visible(push, reference) {
  return reference > 0 ? Math.pow(Math.min(push / reference, 1), 0.6) : 0;
}

// Draw the wobble itself: hue is the direction each point is pushed and brightness is how far, judged against
// `reference`, the largest push the Amount slider allows, so it grows with the Amount. Draws over a dimmed copy of the
// image. Also fills `arrows` with [x, y, down, right] on a grid, in preview pixels for the position and original
// pixels for the push, for drawing as little arrows.
export function noisePixels(source, width, height, lattice, amplitude, scale, target, arrows, gridStep, reference) {
  const push = [0, 0];
  arrows.length = 0;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      pushAt(lattice, x / scale, y / scale, amplitude, push);
      const strength = visible(Math.hypot(push[0], push[1]), reference);
      const hue = ((Math.atan2(push[0], push[1]) / (2 * Math.PI)) + 1) % 1;
      const [r, g, b] = hsvToRgb(hue, 0.85, 0.2 + 0.8 * strength);
      const i = (y * width + x) * 4;
      const grey = (source[i] * 0.299 + source[i + 1] * 0.587 + source[i + 2] * 0.114) * 0.35;
      target[i] = grey * 0.45 + r * 0.55;
      target[i + 1] = grey * 0.45 + g * 0.55;
      target[i + 2] = grey * 0.45 + b * 0.55;
      target[i + 3] = 255;
      if (x % gridStep === Math.floor(gridStep / 2) && y % gridStep === Math.floor(gridStep / 2)) {
        arrows.push([x, y, push[0], push[1]]);
      }
    }
  }
}

export function hsvToRgb(h, s, v) {
  const i = Math.floor(h * 6);
  const f = h * 6 - i;
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const t = v * (1 - (1 - f) * s);
  const [r, g, b] = [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][i % 6];
  return [r * 255, g * 255, b * 255];
}
