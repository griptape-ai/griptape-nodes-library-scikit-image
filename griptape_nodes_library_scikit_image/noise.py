"""The wobble behind Boiling Lines: smooth value noise from an integer hash.

The Boiling Lines widget draws the same wobble in the browser, so this has to give the same numbers as
widgets/BoilingLines/_noise.js. Both use the same 32-bit integer hash, the same lattice and the same smoothstep
interpolation, and no random number generator. Change one and change the other, and keep tests/test_boil_widget.py passing.
"""

from __future__ import annotations

from typing import Any

HASH_X = 374761393
HASH_Y = 668265263
HASH_KEY = 2246822519
HASH_SEED = 3266489917
HASH_MIX = 1274126177
MASK = 0xFFFFFFFF


def lattice(rows: int, columns: int, key: int, seed: int) -> Any:
    """A grid of values from -1 to 1, one per lattice point, fixed by the key and the seed."""
    import numpy as np

    y, x = np.mgrid[0:rows, 0:columns].astype(np.uint64)
    mask = np.uint64(MASK)
    h = (x * np.uint64(HASH_X) + y * np.uint64(HASH_Y) + np.uint64(key * HASH_KEY) + np.uint64(seed * HASH_SEED)) & mask
    h = ((h ^ (h >> np.uint64(13))) * np.uint64(HASH_MIX)) & mask
    h = h ^ (h >> np.uint64(16))
    return h.astype(np.float64) / MASK * 2 - 1


def displacement(height: int, width: int, frame: int, seed: int, amplitude: float, size: float) -> tuple[Any, Any]:
    """How far each pixel of a frame is pushed, down and right, in pixels.

    The noise has one value per `size` pixels, blended smoothly between them, and reaches at most `amplitude`. Each frame
    and each direction has its own noise.
    """
    import numpy as np

    size = max(size, 1.0)
    rows, columns = int(height / size) + 3, int(width / size) + 3
    v = np.arange(height, dtype=np.float64) / size
    u = np.arange(width, dtype=np.float64) / size
    row0, column0 = np.floor(v).astype(int), np.floor(u).astype(int)
    fy = v - row0
    fx = u - column0
    sy = (fy * fy * (3 - 2 * fy))[:, None]
    sx = (fx * fx * (3 - 2 * fx))[None, :]
    pushes = []
    for channel in range(2):
        grid = lattice(rows, columns, frame * 2 + channel, seed)
        top = grid[np.ix_(row0, column0)] * (1 - sx) + grid[np.ix_(row0, column0 + 1)] * sx
        bottom = grid[np.ix_(row0 + 1, column0)] * (1 - sx) + grid[np.ix_(row0 + 1, column0 + 1)] * sx
        pushes.append((top * (1 - sy) + bottom * sy) * amplitude)
    return pushes[0], pushes[1]
