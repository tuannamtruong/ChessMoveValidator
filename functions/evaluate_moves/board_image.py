"""Dependency-free chess-board PNG renderer.

Renders an 8x8 board (as produced by the evaluator's engine) to PNG bytes using
only the standard library (``zlib`` + ``struct``). No Pillow, no Lambda layer.

The board is a list of 8 rows, index 0 = rank 1 (White's back rank) .. index 7 =
rank 8 (Black's back rank); each square is ``None`` or a ``(color, kind)`` tuple
with ``color in ('w', 'b')`` and ``kind in 'PNBRQK'``.
"""
import struct
import zlib

SQUARE = 64          # pixels per square
BORDER = 16          # margin around the board
BOARD_PX = SQUARE * 8
SIZE = BOARD_PX + 2 * BORDER

# Colors (R, G, B).
LIGHT_SQ = (238, 216, 184)
DARK_SQ = (171, 122, 84)
BG = (34, 34, 34)
WHITE_PIECE = (248, 248, 248)
BLACK_PIECE = (24, 24, 24)
OUTLINE = (24, 24, 24)

# 5x7 bitmap glyphs for the six piece letters. Each string row is 5 chars,
# '#' = filled. Scaled up and centered when drawn.
GLYPHS = {
    'K': ["#...#",
          "#.#.#",
          "##.##",
          ".#.#.",
          "##.##",
          "#.#.#",
          "#...#"],
    'Q': [".###.",
          "#...#",
          "#...#",
          "#.#.#",
          "#.#.#",
          "#.###",
          ".##.#"],
    'R': ["#.#.#",
          "#####",
          ".###.",
          ".###.",
          ".###.",
          ".###.",
          "#####"],
    'B': ["..#..",
          ".###.",
          "#####",
          "#####",
          ".###.",
          "..#..",
          ".###."],
    'N': ["..##.",
          ".####",
          "##.##",
          "..###",
          ".####",
          "#####",
          "#####"],
    'P': ["..#..",
          ".###.",
          ".###.",
          "..#..",
          ".###.",
          "#####",
          "#####"],
}

GLYPH_W = 5
GLYPH_H = 7
GLYPH_SCALE = 7      # 35x49 px piece, comfortably inside a 64px square


def _blank_canvas():
    """Return a fresh SIZE x SIZE RGB pixel buffer filled with the background."""
    return [[BG] * SIZE for _ in range(SIZE)]


def _fill_rect(px, x0, y0, x1, y1, color):
    for y in range(y0, y1):
        row = px[y]
        for x in range(x0, x1):
            row[x] = color


def _draw_glyph(px, cx, cy, kind, fill, outline):
    """Draw a piece glyph centered at (cx, cy)."""
    glyph = GLYPHS[kind]
    gw = GLYPH_W * GLYPH_SCALE
    gh = GLYPH_H * GLYPH_SCALE
    x0 = cx - gw // 2
    y0 = cy - gh // 2
    for gy, line in enumerate(glyph):
        for gx, ch in enumerate(line):
            if ch != '#':
                continue
            px0 = x0 + gx * GLYPH_SCALE
            py0 = y0 + gy * GLYPH_SCALE
            # Outline: draw a slightly larger block underneath for contrast.
            _fill_rect(px, px0 - 1, py0 - 1,
                       px0 + GLYPH_SCALE + 1, py0 + GLYPH_SCALE + 1, outline)
    for gy, line in enumerate(glyph):
        for gx, ch in enumerate(line):
            if ch != '#':
                continue
            px0 = x0 + gx * GLYPH_SCALE
            py0 = y0 + gy * GLYPH_SCALE
            _fill_rect(px, px0, py0, px0 + GLYPH_SCALE, py0 + GLYPH_SCALE, fill)


def _encode_png(px):
    """Encode an RGB pixel buffer (list of rows of (r,g,b)) to PNG bytes."""
    raw = bytearray()
    for row in px:
        raw.append(0)  # filter type 0 (None) for this scanline
        for (r, g, b) in row:
            raw.append(r)
            raw.append(g)
            raw.append(b)

    def chunk(tag, data):
        out = struct.pack('>I', len(data)) + tag + data
        crc = zlib.crc32(tag + data) & 0xffffffff
        return out + struct.pack('>I', crc)

    ihdr = struct.pack('>IIBBBBB', SIZE, SIZE, 8, 2, 0, 0, 0)  # 8-bit RGB
    idat = zlib.compress(bytes(raw), 9)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', idat)
            + chunk(b'IEND', b''))


def render_board_png(board):
    """Render ``board`` (engine format) to PNG bytes."""
    px = _blank_canvas()
    for r in range(8):
        # rank 8 (index 7) at the top of the image
        board_row = 7 - r
        for c in range(8):
            x0 = BORDER + c * SQUARE
            y0 = BORDER + r * SQUARE
            light = (board_row + c) % 2 == 1
            _fill_rect(px, x0, y0, x0 + SQUARE, y0 + SQUARE,
                       LIGHT_SQ if light else DARK_SQ)
            piece = board[board_row][c]
            if piece is None:
                continue
            color, kind = piece
            fill = WHITE_PIECE if color == 'w' else BLACK_PIECE
            _draw_glyph(px, x0 + SQUARE // 2, y0 + SQUARE // 2, kind, fill, OUTLINE)
    return _encode_png(px)
