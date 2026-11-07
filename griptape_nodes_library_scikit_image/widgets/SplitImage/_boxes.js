// The geometry of Split Image's widget, with no DOM, so it can be tested on its own.
//
// A box is [left, top, right, bottom] in the image's pixels, with right and bottom not included. This is the form
// Python sends and receives. paddedBox, readingOrder and classify match splitting.py, so what is drawn is what is saved.

export function sameBox(first, second) {
  return first.length === 4 && second.length === 4 && first.every((n, i) => n === second[i]);
}

export function paddedBox(box, paddingPercent, width, height) {
  const padding = Math.round((paddingPercent / 100) * Math.max(width, height));
  return [
    Math.max(0, box[0] - padding),
    Math.max(0, box[1] - padding),
    Math.min(width, box[2] + padding),
    Math.min(height, box[3] + padding),
  ];
}

export function isExcluded(excluded, box) {
  return excluded.some((other) => sameBox(other, box));
}

export function toggleExcluded(excluded, box) {
  return isExcluded(excluded, box) ? excluded.filter((other) => !sameBox(other, box)) : [...excluded, box];
}

// Each piece with the number it is saved under, or null while it is left out. Numbers count the kept pieces only.
export function numbering(pieces, excluded) {
  let next = 1;
  return pieces.map((piece) => {
    const off = isExcluded(excluded, piece.box);
    return { ...piece, off, number: off ? null : next++ };
  });
}

// The piece under a point. Where boxes overlap, the smallest one wins, so a piece inside another can be picked.
export function pieceAt(pieces, x, y) {
  let best = null;
  let bestArea = Infinity;
  for (const piece of pieces) {
    const [left, top, right, bottom] = piece.box;
    if (x < left || x >= right || y < top || y >= bottom) continue;
    const area = (right - left) * (bottom - top);
    if (area < bestArea) {
      best = piece;
      bestArea = area;
    }
  }
  return best;
}

// The largest size with the image's shape that fits in the area.
export function fitSize(areaWidth, areaHeight, imageWidth, imageHeight) {
  if (!(imageWidth > 0 && imageHeight > 0 && areaWidth > 0 && areaHeight > 0)) return [0, 0];
  const scale = Math.min(areaWidth / imageWidth, areaHeight / imageHeight);
  return [Math.round(imageWidth * scale), Math.round(imageHeight * scale)];
}

// Left to right within a row, and rows from top to bottom. A piece joins the current row when its centre is within half
// the median piece height of the row's first piece. This is splitting.reading_order.
export function readingOrder(items) {
  if (!items.length) return [];
  const heights = items.map((item) => item.box[3] - item.box[1]).sort((a, b) => a - b);
  const rowHeight = heights[Math.floor(heights.length / 2)] / 2;
  const centre = (item) => (item.box[1] + item.box[3]) / 2;
  const rows = [];
  let rowStart = null;
  for (const item of [...items].sort((a, b) => centre(a) - centre(b))) {
    if (rowStart === null || centre(item) - rowStart > rowHeight) {
      rows.push([]);
      rowStart = centre(item);
    }
    rows[rows.length - 1].push(item);
  }
  return rows.flatMap((row) => [...row].sort((a, b) => a.box[0] - b.box[0]));
}

// The pieces to keep, in reading order, and the candidates dropped for the settings. This is splitting.classify. A
// candidate is { box, blob, tight, edges }: the sizes are percentages of the image's longer side, like minSize.
export function classify(candidates, minSize, ignoreCornerPieces) {
  const kept = [];
  const dropped = [];
  for (const candidate of candidates) {
    if (candidate.blob < minSize) continue;
    if (candidate.tight < minSize || (ignoreCornerPieces && candidate.edges >= 2)) dropped.push(candidate);
    else kept.push(candidate);
  }
  return { kept: readingOrder(kept), dropped };
}
