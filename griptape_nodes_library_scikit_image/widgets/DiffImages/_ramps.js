// The colour of a palette at a level from 0 to 1, as tools.heat_colours does in Python. A palette is a list of
// [position, [r, g, b]] stops from 0 to 1. A level between two stops is mixed between their colours, and a level outside
// them takes the colour of the nearest stop.

export function rampColour(stops, level) {
  if (!stops.length) return [255, 60, 60];
  if (level <= stops[0][0]) return stops[0][1];
  for (let i = 1; i < stops.length; i++) {
    const [after, colourAfter] = stops[i];
    if (level <= after) {
      const [before, colourBefore] = stops[i - 1];
      const mix = after > before ? (level - before) / (after - before) : 1;
      return colourBefore.map((channel, c) => channel + (colourAfter[c] - channel) * mix);
    }
  }
  return stops[stops.length - 1][1];
}

// 256 colours across the ramp, so a picture can be coloured with one lookup per pixel.
export function rampLookup(stops, size = 1024) {
  const table = new Uint8ClampedArray(size * 3);
  for (let i = 0; i < size; i++) {
    const colour = rampColour(stops, i / (size - 1));
    table.set(colour, i * 3);
  }
  return table;
}
