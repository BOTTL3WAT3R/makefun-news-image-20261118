#!/usr/bin/env python3
"""The World in One Picture - Wednesday 18 November 2026.

Deterministic, standard-library-only poster generator for make.fun's
news-image-20261118 bounty. Draws a one-page news poster on a supersampled
canvas (own rasterizer: scanline polygons, circles, thick lines, gradients,
halftone textures, hand-drawn bitmap font) and writes it as a 1024x1024 PNG
to $MAKEFUN_OUTPUT_DIR/entry.png (default /output). No assets, no network,
no randomness, no clock: two runs produce byte-identical output.
"""

import math
import os
import struct
import zlib

SS = 2                      # supersampling factor
W = 1024                    # final width
H = 1024                    # final height


# --------------------------------------------------------------------------
# Canvas: RGB bytearray at SS resolution, primitives in final-image coords.
# --------------------------------------------------------------------------

class Canvas:
    def __init__(self, w, h, color):
        self.w = w * SS
        self.h = h * SS
        self.buf = bytearray(bytes(color) * (self.w * self.h))

    def _span(self, y, x0, x1, cb):
        """Fill SS pixel row y, columns [x0, x1), with color bytes cb."""
        if y < 0 or y >= self.h:
            return
        if x0 < 0:
            x0 = 0
        if x1 > self.w:
            x1 = self.w
        if x1 <= x0:
            return
        off = (y * self.w + x0) * 3
        n = x1 - x0
        self.buf[off:off + 3 * n] = cb * n

    def rect(self, x, y, w, h, color):
        cb = bytes(color)
        y0 = int(round(y * SS))
        y1 = int(round((y + h) * SS))
        x0 = int(round(x * SS))
        x1 = int(round((x + w) * SS))
        for yy in range(y0, y1):
            self._span(yy, x0, x1, cb)

    def circle(self, cx, cy, r, color):
        cb = bytes(color)
        cx2 = cx * SS
        cy2 = cy * SS
        r2 = r * SS
        ri = int(math.ceil(r2))
        ci = int(round(cy2))
        for dy in range(-ri, ri + 1):
            dx = math.isqrt(max(0, int(r2 * r2) - dy * dy))
            self._span(ci + dy, int(round(cx2)) - dx, int(round(cx2)) + dx, cb)

    def ellipse(self, cx, cy, rx, ry, color):
        cb = bytes(color)
        cy2 = cy * SS
        ry2 = ry * SS
        ri = int(math.ceil(ry2))
        ci = int(round(cy2))
        for dy in range(-ri, ri + 1):
            t = dy / ry2 if ry2 else 0.0
            dx = (rx * SS) * math.sqrt(max(0.0, 1.0 - t * t))
            self._span(ci + dy, int(round(cx * SS - dx)),
                       int(round(cx * SS + dx)), cb)

    def poly(self, pts, color):
        """Scanline polygon fill. pts: list of (x, y) in final coords."""
        cb = bytes(color)
        p = [(px * SS, py * SS) for (px, py) in pts]
        ys = [pt[1] for pt in p]
        y0 = max(0, int(math.floor(min(ys))))
        y1 = min(self.h - 1, int(math.ceil(max(ys))))
        n = len(p)
        for yy in range(y0, y1 + 1):
            yc = yy + 0.5
            xs = []
            for i in range(n):
                xa, ya = p[i]
                xb, yb = p[(i + 1) % n]
                if ya == yb:
                    continue
                if (yc >= ya and yc < yb) or (yc >= yb and yc < ya):
                    xs.append(xa + (yc - ya) * (xb - xa) / (yb - ya))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self._span(yy, int(round(xs[i])), int(round(xs[i + 1])), cb)

    def line(self, x0, y0, x1, y1, color, w):
        """Thick line: filled circles stamped along the segment."""
        dist = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(dist / max(0.4, w * 0.35)))
        for i in range(steps + 1):
            t = i / steps
            self.circle(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, w / 2.0, color)

    def path(self, pts, color, w):
        for i in range(len(pts) - 1):
            self.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
                      color, w)

    def curve(self, p0, p1, p2, color, w, steps=40):
        """Quadratic Bezier through sampled thick points."""
        prev = None
        for i in range(steps + 1):
            t = i / steps
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
            if prev is not None:
                self.line(prev[0], prev[1], x, y, color, w)
            prev = (x, y)

    def vgrad(self, x, y, w, h, c_top, c_bot):
        y0 = int(round(y * SS))
        y1 = int(round((y + h) * SS))
        x0 = int(round(x * SS))
        x1 = int(round((x + w) * SS))
        span = max(1, y1 - y0 - 1)
        for yy in range(y0, y1):
            t = (yy - y0) / span
            col = bytes(int(round(c_top[i] + (c_bot[i] - c_top[i]) * t))
                        for i in range(3))
            self._span(yy, x0, x1, col)

    def halftone(self, x, y, w, h, color, spacing, r0, r1, drift=0.0):
        """Dot grid; radius eases r0 -> r1 top to bottom."""
        rows = int(h / spacing)
        for j in range(rows + 1):
            cy = y + j * spacing
            t = j / max(1, rows)
            r = r0 + (r1 - r0) * t
            off = drift if (j % 2) else 0.0
            cols = int(w / spacing)
            for i in range(cols + 1):
                self.circle(x + i * spacing + off, cy, r, color)

    def frame(self, x, y, w, h, color, t):
        self.rect(x, y, w, t, color)
        self.rect(x, y + h - t, w, t, color)
        self.rect(x, y, t, h, color)
        self.rect(x + w - t, y, t, h, color)


# --------------------------------------------------------------------------
# Hand-drawn 5x7 bitmap font.
# --------------------------------------------------------------------------

FONT = {
    'A': (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    'B': ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    'C': (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    'D': ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    'E': ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    'F': ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    'G': (".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."),
    'H': ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    'I': ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    'J': ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    'K': ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    'L': ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    'M': ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    'N': ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    'O': (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    'P': ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    'Q': (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    'R': ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    'S': (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    'T': ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    'U': ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    'V': ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    'W': ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."),
    'X': ("#...#", ".#.#.", "..#..", "..#..", "..#..", ".#.#.", "#...#"),
    'Y': ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    'Z': ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    '0': (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    '1': ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", "#####"),
    '2': (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    '3': ("#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."),
    '4': ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    '5': ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    '6': (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    '7': ("#####", "....#", "...#.", "..#..", "..#..", "..#..", "..#.."),
    '8': (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    '9': (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
    ' ': (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    '-': (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    '.': (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    ',': (".....", ".....", ".....", ".....", ".##..", ".##..", ".#..."),
    ';': (".....", ".##..", ".##..", ".....", ".##..", ".##..", ".#..."),
    ':': (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    "'": (".##..", ".##..", ".#...", ".....", ".....", ".....", "....."),
    '+': (".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    '&': (".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"),
}


def text_width(s, scale, tracking=0.0):
    if not s:
        return 0.0
    return len(s) * (6.0 * scale + tracking) - tracking


def draw_text(cv, s, x, y, scale, color, tracking=0.0, bold=False):
    """Draw string s with top-left at (x, y). Returns the end x."""
    passes = [(0.0, 0.0)]
    if bold:
        passes.append((scale * 0.20, 0.0))
    for (ox, oy) in passes:
        cx = x + ox
        for ch in s:
            glyph = FONT.get(ch, FONT[' '])
            for row in range(7):
                line = glyph[row]
                for col in range(5):
                    if line[col] == '#':
                        cv.rect(cx + col * scale, y + oy + row * scale,
                                scale, scale, color)
            cx += 6.0 * scale + tracking
    return x + text_width(s, scale, tracking)


def draw_text_center(cv, s, cx, y, scale, color, tracking=0.0, bold=False):
    w = text_width(s, scale, tracking)
    return draw_text(cv, s, cx - w / 2.0, y, scale, color, tracking, bold)


def hash2(x, y):
    """Deterministic 2D integer hash -> [0, 1)."""
    n = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65536.0


# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------

NAVY = (15, 30, 60)
NAVY_DOT = (30, 52, 92)
GOLD = (233, 185, 79)
GOLD_DK = (198, 152, 52)
CREAM = (241, 235, 219)
PAPER = (253, 251, 245)
INK = (17, 32, 62)
SUBC = (74, 78, 90)
RED = (176, 32, 48)
WHITE = (250, 248, 240)
SHADOW = (203, 198, 184)


def star(cv, cx, cy, r, color, points=8, ratio=0.45, rot=-math.pi / 2):
    pts = []
    for i in range(points * 2):
        rr = r if i % 2 == 0 else r * ratio
        a = rot + i * math.pi / points
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    cv.poly(pts, color)


def burst(cv, cx, cy, r):
    star(cv, cx, cy, r, (214, 60, 40), points=8, ratio=0.42)
    star(cv, cx, cy, r * 0.72, (244, 130, 50), points=8, ratio=0.45)
    star(cv, cx, cy, r * 0.44, (255, 214, 90), points=8, ratio=0.5)
    cv.circle(cx, cy, r * 0.16, (255, 244, 200))


def jet(cv, cx, cy, s, color):
    """Little jet silhouette, nose pointing right, s = length scale."""
    pts = [(cx + 1.00 * s, cy), (cx + 0.55 * s, cy - 0.10 * s),
           (cx + 0.10 * s, cy - 0.12 * s), (cx - 0.18 * s, cy - 0.34 * s),
           (cx - 0.30 * s, cy - 0.36 * s), (cx - 0.26 * s, cy - 0.10 * s),
           (cx - 0.52 * s, cy - 0.10 * s), (cx - 0.62 * s, cy - 0.30 * s),
           (cx - 0.72 * s, cy - 0.30 * s), (cx - 0.66 * s, cy + 0.02 * s),
           (cx - 0.72 * s, cy + 0.16 * s), (cx - 0.30 * s, cy + 0.12 * s),
           (cx + 0.05 * s, cy + 0.30 * s), (cx + 0.28 * s, cy + 0.12 * s),
           (cx + 0.62 * s, cy + 0.08 * s)]
    cv.poly(pts, color)


# --------------------------------------------------------------------------
# Scene painters. Each fills the box (x, y, w, h).
# --------------------------------------------------------------------------

def scene_iran(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (28, 86, 112), (17, 56, 86))
    cv.halftone(x + 6, y + 8, w - 12, h - 16, (52, 116, 142), 15, 1.1, 1.1)
    sand = (219, 190, 132)
    sand_dk = (188, 156, 100)
    # north-west landmass (Kuwait / Saudi coast), bay bitten out of it
    cv.poly([(x, y), (x + 172, y), (x + 128, y + 15), (x + 106, y + 33),
             (x + 68, y + 58), (x + 30, y + 66), (x, y + 72)], sand)
    # city markers: Kuwait (NW) and Bahrain (mid-west coast)
    for (mx, my) in [(x + 148, y + 8), (x + 88, y + 42)]:
        cv.circle(mx, my, 3.4, (250, 248, 240))
        cv.circle(mx, my, 1.7, (176, 32, 48))
    # north-east landmass (Iran)
    cv.poly([(x + 318, y), (x + w, y), (x + w, y + 44), (x + 398, y + 34),
             (x + 356, y + 18)], sand)
    # southern shore strip
    cv.poly([(x, y + h), (x + 168, y + h), (x + 128, y + h - 18),
             (x + 44, y + h - 12), (x, y + h - 8)], sand)
    # Qeshm island
    cv.ellipse(x + 322, y + 41, 41, 10, sand_dk)
    cv.ellipse(x + 322, y + 39, 39, 9, sand)
    # missile arcs (dashed fire trails)
    for (p0, p1, p2) in [
            ((x + 386, y + 10), (x + 356, y - 8), (x + 324, y + 32)),
            ((x + 324, y + 34), (x + 210, y + 2), (x + 74, y + 50)),
            ((x + 300, y + 44), (x + 210, y + 66), (x + 96, y + h - 16))]:
        for i in range(13):
            t = i / 12.0
            bx = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
            by = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
            cv.circle(bx, by, 2.3, (255, 186, 100))
    # explosions: Qeshm site, Bahrain-side coast, southern shore
    burst(cv, x + 322, y + 36, 15)
    burst(cv, x + 70, y + 52, 11)
    burst(cv, x + 96, y + h - 16, 9)
    # jets with contrails
    cv.line(x + 128, y + 30, x + 176, y + 22, (226, 236, 240), 1.6)
    jet(cv, x + 196, y + 20, 30, (24, 30, 40))
    cv.line(x + 250, y + 66, x + 296, y + 60, (226, 236, 240), 1.6)
    jet(cv, x + 316, y + 58, 26, (24, 30, 40))


def scene_shenzhen(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (138, 184, 226), (250, 206, 150))
    cv.circle(x + 58, y + 16, 17, (255, 240, 198))
    cv.circle(x + 58, y + 16, 11, (255, 226, 150))
    # skyline silhouettes
    towers = [(0, 30, 22), (26, 40, 18), (48, 26, 24), (76, 44, 16),
              (96, 34, 20), (120, 48, 15), (140, 30, 22), (300, 36, 18),
              (322, 46, 16), (342, 28, 20), (366, 42, 17), (388, 32, 19),
              (410, 44, 16), (430, 30, 34)]
    sil = (92, 112, 142)
    for (tx, th, tw) in towers:
        cv.rect(x + tx, y + 62 - th, tw, th, sil)
        for wy in range(int(y + 62 - th) + 5, int(y + 58), 7):
            for wx in range(int(x + tx) + 4, int(x + tx + tw) - 3, 6):
                if hash2(wx, wy) > 0.45:
                    cv.rect(wx, wy, 2.2, 2.8, (255, 222, 130))
    # runway trapezoid
    cv.poly([(x, y + h), (x + w, y + h), (x + w - 58, y + 62),
             (x + 58, y + 62)], (48, 50, 56))
    for i in range(7):
        t = i / 6.0
        cxp = x + w / 2
        cyp = y + 68 + t * (h - 70)
        dw = 3 + t * 9
        cv.rect(cxp - dw / 2, cyp, dw, 2.6, (240, 240, 235))
    for i in range(5):
        t = i / 4.0
        cv.circle(x + 66 + t * 44, y + 66 + t * (h - 70), 1.6, (140, 230, 240))
        cv.circle(x + w - 66 - t * 44, y + 66 + t * (h - 70), 1.6,
                  (140, 230, 240))
    # the plane
    pc = (36, 50, 84)
    pc_dk = (26, 38, 66)
    cv.poly([(x + 196, y + 44), (x + 252, y + 20), (x + 268, y + 20),
             (x + 240, y + 46), (x + 268, y + 60), (x + 210, y + 52)],
            pc_dk)  # far wing
    cv.ellipse(x + 178, y + 46, 82, 13, pc)          # fuselage
    cv.poly([(x + 104, y + 40), (x + 88, y + 16), (x + 100, y + 15),
             (x + 122, y + 38)], pc_dk)               # tail fin
    cv.poly([(x + 100, y + 52), (x + 86, y + 62), (x + 118, y + 56)],
            pc_dk)                                   # tailplane
    cv.poly([(x + 168, y + 52), (x + 214, y + 74), (x + 232, y + 74),
             (x + 204, y + 50)], pc_dk)              # near wing
    cv.rect(x + 96, y + 43.5, 158, 2.6, (206, 44, 48))  # cheatline
    for i in range(12):
        cv.circle(x + 128 + i * 10, y + 40, 1.5, (205, 224, 242))
    # flags
    for (fx, cn) in [(x + 388, True), (x + 426, False)]:
        cv.rect(fx, y + 10, 2.4, 52, (70, 60, 48))
        if cn:
            cv.rect(fx + 2.4, y + 10, 31, 20, (206, 40, 44))
            cv.circle(fx + 8, y + 16, 2.6, (255, 214, 64))
            for (dx, dy) in [(15, 12.5), (17, 16), (17, 20), (15, 23.5)]:
                cv.circle(fx + dx, y + dy, 1.1, (255, 214, 64))
        else:
            cv.rect(fx + 2.4, y + 10, 33, 20, (244, 244, 244))
            for i in range(4):
                cv.rect(fx + 2.4, y + 10 + i * 5.4, 33, 2.7, (188, 44, 56))
            cv.rect(fx + 2.4, y + 10, 15, 10.5, (44, 56, 120))
            for r in range(3):
                for cidx in range(4):
                    cv.circle(fx + 5.4 + cidx * 3.6, y + 12.6 + r * 3.4, 0.8,
                              (255, 255, 255))


def scene_measles(cv, x, y, w, h):
    cv.rect(x, y, w, h, (248, 240, 232))
    cv.halftone(x + 4, y + 4, w - 8, h - 8, (242, 205, 198), 13, 1.0, 1.6)
    # stylised continental US
    us = [(4, 26), (26, 16), (58, 10), (104, 6), (150, 8), (186, 13),
          (198, 23), (210, 17), (224, 23), (238, 15), (249, 25), (243, 39),
          (233, 43), (237, 55), (227, 57), (231, 73), (221, 77), (213, 63),
          (195, 61), (175, 59), (147, 61), (119, 57), (97, 51), (89, 61),
          (74, 63), (60, 52), (41, 54), (24, 45), (10, 33)]
    pts = [(x + px * 1.02, y + 4 + py * 0.92) for (px, py) in us]
    cv.poly(pts, (233, 216, 182))
    cv.path(pts + [pts[0]], (168, 148, 118), 2.2)
    # virus particles
    def virus(cx, cy, r):
        for k in range(10):
            a = k * math.pi / 5 + cx
            cv.line(cx, cy, cx + (r + 5) * math.cos(a),
                    cy + (r + 5) * math.sin(a), (186, 60, 74), 2.2)
            cv.circle(cx + (r + 5) * math.cos(a), cy + (r + 5) * math.sin(a),
                      2.2, (186, 60, 74))
        cv.circle(cx, cy, r, (216, 92, 102))
        cv.circle(cx - r * 0.3, cy - r * 0.2, r * 0.30, (240, 168, 174))
        cv.circle(cx + r * 0.34, cy + r * 0.3, r * 0.22, (240, 168, 174))
        cv.circle(cx + r * 0.1, cy - r * 0.42, r * 0.16, (196, 70, 84))
    virus(x + 300, y + 28, 14)
    virus(x + 348, y + 62, 10.5)
    virus(x + 282, y + 68, 8)
    virus(x + 366, y + 20, 7.5)
    # cracked shield
    sh = [(x + 398, y + 14), (x + 442, y + 14), (x + 442, y + 42),
          (x + 420, y + 76), (x + 398, y + 42)]
    cv.poly(sh, (227, 231, 237))
    cv.path(sh + [sh[0]], (110, 116, 128), 3.2)
    cv.path([(x + 421, y + 18), (x + 414, y + 32), (x + 424, y + 44),
             (x + 415, y + 56), (x + 420, y + 70)], (70, 74, 84), 2.6)


def scene_nvidia(cv, x, y, w, h):
    cv.rect(x, y, w, h, (8, 24, 16))
    trace = (24, 110, 62)
    node = (46, 180, 100)
    runs = [
        [(6, 12), (70, 12), (70, 30)], [(6, 76), (52, 76), (52, 58)],
        [(120, 6), (120, 24), (150, 24)], [(30, 44), (30, 20), (58, 20)],
        [(250, 8), (250, 26), (282, 26)], [(452, 16), (404, 16), (404, 34)],
        [(458, 78), (420, 78)], [(268, 84), (268, 66), (296, 66)],
        [(180, 84), (180, 70)], [(86, 84), (86, 66), (110, 66)],
    ]
    for r in runs:
        cv.path([(x + px, y + py) for (px, py) in r], trace, 2.0)
        cv.circle(x + r[-1][0], y + r[-1][1], 2.6, node)
        cv.circle(x + r[0][0], y + r[0][1], 2.6, node)
    # the chip
    cx0, cy0 = x + 128, y + 14
    cv.rect(cx0, cy0, 96, 62, (22, 30, 26))
    cv.frame(cx0, cy0, 96, 62, (90, 200, 110), 2.4)
    cv.rect(cx0 + 20, cy0 + 13, 56, 36, (13, 20, 16))
    cv.frame(cx0 + 20, cy0 + 13, 56, 36, (60, 160, 84), 1.8)
    draw_text(cv, "AI", cx0 + 37, cy0 + 22, 2.6, (120, 235, 140), bold=True)
    pin = (176, 184, 178)
    for i in range(8):
        cv.rect(cx0 + 8 + i * 11, cy0 - 6, 6, 6, pin)
        cv.rect(cx0 + 8 + i * 11, cy0 + 62, 6, 6, pin)
    for i in range(5):
        cv.rect(cx0 - 6, cy0 + 8 + i * 11, 6, 6, pin)
        cv.rect(cx0 + 96, cy0 + 8 + i * 11, 6, 6, pin)
    # rising bars + arrow
    base = y + h - 8
    cv.line(x + 288, base, x + 456, base, (120, 130, 124), 2.0)
    greens = [(36, 140, 72), (44, 158, 80), (54, 178, 88), (70, 198, 98),
              (92, 222, 118)]
    for i, bh in enumerate([14, 24, 36, 50, 66]):
        cv.rect(x + 300 + i * 31, base - bh, 21, bh, greens[i])
    cv.path([(x + 292, base - 22), (x + 340, base - 34), (x + 384, base - 48),
             (x + 448, base - 76)], (130, 245, 150), 3.4)
    cv.poly([(x + 448, y + 6), (x + 438, y + 12), (x + 456, y + 16)],
            (130, 245, 150))


def scene_cop31(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (168, 212, 238), (233, 243, 245))
    # globe
    gx, gy, gr = x + 94, y + 46, 37
    cv.circle(gx, gy, gr, (70, 134, 204))
    cv.ellipse(gx - 12, gy - 12, 17, 10, (86, 170, 98))
    cv.ellipse(gx + 13, gy + 6, 13, 9, (86, 170, 98))
    cv.ellipse(gx - 4, gy + 20, 10, 6, (96, 178, 104))
    cv.ellipse(gx + 2, gy - 24, 15, 5, (240, 246, 248))
    # sun with rays
    sx, sy = x + 404, y + 20
    for k in range(8):
        a = k * math.pi / 4
        cv.line(sx + 17 * math.cos(a), sy + 17 * math.sin(a),
                sx + 23 * math.cos(a), sy + 23 * math.sin(a),
                (250, 170, 60), 2.6)
    cv.circle(sx, sy, 13, (255, 206, 66))
    # factory + smoke (behind table band)
    fac = (70, 77, 86)
    cv.rect(x + 330, y + 62, 124, h - 62, fac)
    cv.rect(x + 352, y + 32, 15, 34, (58, 64, 72))
    cv.rect(x + 392, y + 24, 15, 42, (58, 64, 72))
    for (ex, ey, er) in [(360, 24, 7), (364, 14, 9), (370, 5, 11),
                         (400, 16, 7), (405, 7, 9)]:
        cv.ellipse(x + ex, y + ey, er, er * 0.62, (198, 205, 212))
    # delegates at a long table
    cv.poly([(x + 148, y + h), (x + 330, y + h), (x + 322, y + h - 16),
             (x + 156, y + h - 16)], (52, 56, 64))
    skins = [(232, 190, 150), (198, 150, 105), (150, 105, 70),
             (240, 205, 170), (120, 82, 55)]
    for i, sk in enumerate(skins):
        hx = x + 178 + i * 30
        hy = y + h - 24
        cv.rect(hx - 7, hy + 4, 14, 9, (40, 44, 52))
        cv.circle(hx, hy, 6.4, sk)


def scene_cyclone(cv, x, y, w, h):
    cv.vgrad(x, y, w, h, (15, 56, 102), (25, 92, 138))
    # wave dashes
    for j, wy in enumerate([16, 33, 50, 67, 82]):
        for i in range(16):
            wx = x + 8 + i * 29 + (j % 2) * 13
            if wx < x + w - 16:
                cv.line(wx, y + wy, wx + 13, y + wy, (96, 156, 194), 1.8)
    # storm spiral: two interleaved arms
    cx, cy = x + 148, y + 45
    for arm, col, wd in [(0.0, (242, 247, 250), 7.0),
                         (math.pi, (198, 214, 226), 5.5)]:
        prev = None
        for i in range(90):
            t = i / 89.0
            ang = arm + t * 4.6 * math.pi
            rr = 5 + t * 44
            px = cx + rr * math.cos(ang)
            py = cy + rr * 0.72 * math.sin(ang)
            if prev is not None:
                cv.line(prev[0], prev[1], px, py, col, wd * (1 - t * 0.45))
            prev = (px, py)
    cv.circle(cx, cy, 8, (12, 42, 74))
    cv.circle(cx, cy, 10.5, (230, 240, 246))
    cv.circle(cx, cy, 8, (12, 42, 74))
    # coast landmass (right)
    cv.poly([(x + 348, y), (x + w, y), (x + w, y + h), (x + 386, y + h),
             (x + 356, y + 58), (x + 342, y + 26)], (214, 186, 128))
    cv.poly([(x + 348, y), (x + w, y), (x + w, y + 14), (x + 380, y + 12),
             (x + 356, y + 30), (x + 342, y + 26)], (96, 160, 90))
    # palms bending in the wind
    def palm(bx, by, s):
        top = (bx - 13 * s, by - 30 * s)
        cv.curve((bx, by), (bx - 2 * s, by - 18 * s), top, (122, 88, 54), 3.4)
        for da in (-0.9, -0.45, 0.0, 0.45, 0.9):
            ex = top[0] + 15 * s * math.sin(da + 2.6)
            ey = top[1] + 11 * s * math.cos(da + 2.6) + 4 * s
            cv.curve(top, (top[0] + (ex - top[0]) * 0.5,
                           top[1] - 6 * s), (ex, ey), (58, 138, 78), 2.4)
    palm(x + 404, y + 76, 1.0)
    palm(x + 438, y + 66, 0.8)
    palm(x + 378, y + 84, 0.7)
    # rain streaks
    for i in range(46):
        rx = x + 12 + hash2(i, 7) * (w - 30)
        ry = y + 6 + hash2(i, 13) * (h - 16)
        cv.line(rx, ry, rx - 3.5, ry + 9, (172, 206, 230), 1.5)


# --------------------------------------------------------------------------
# Page layout
# --------------------------------------------------------------------------

PANELS = [
    ("MIDDLE EAST", "IRAN STRIKES KUWAIT", "AND BAHRAIN",
     "REPLY TO US STRIKE ON", "QESHM ISLAND MISSILE SITE", scene_iran),
    ("ASIA-PACIFIC", "XI GREETS TRUMP", "IN SHENZHEN",
     "APEC OPENS; TRUMP-XI-PUTIN", "TALKS SET FOR THURSDAY", scene_shenzhen),
    ("HEALTH", "US LOSES MEASLES-FREE", "STATUS",
     "5,400+ CASES, 10 DEATHS;", "FIRST LOSS SINCE 2000", scene_measles),
    ("TECHNOLOGY", "NVIDIA EARNINGS", "BEAT FORECASTS",
     "Q3 REVENUE DOUBLES", "YEAR ON YEAR", scene_nvidia),
    ("CLIMATE", "COP31 DRAFT DEAL", "DIVIDES TALKS",
     "EU WANTS MAJOR CHANGES", "AS ANTALYA TALKS NEAR END", scene_cop31),
    ("WEATHER", "CYCLONE AKVAN", "STRENGTHENS",
     "INDIA LANDFALL FORECAST", "FRIDAY ON ANDHRA COAST", scene_cyclone),
]

TICKER_1 = ("ALSO: PELTOLA BEATS SULLIVAN IN ALASKA - "
            "DEMOCRATS PROJECTED 56-44 SENATE")
TICKER_2 = ("BOARD OF PEACE: ISRAEL & HAMAS FAILING GAZA TRUCE - "
            "VOYAGER 1 NOW ONE LIGHT-DAY FROM EARTH")


def draw_panel(cv, x, y, w, h, tag, head1, head2, sub1, sub2, scene):
    cv.rect(x + 4, y + 5, w, h, SHADOW)
    cv.rect(x, y, w, h, PAPER)
    cv.frame(x, y, w, h, NAVY, 3)
    # region tag
    draw_text(cv, tag, x + 16, y + 10, 1.5, RED, bold=True)
    tw = text_width(tag, 1.5)
    cv.rect(x + 20 + tw, y + 14, 26, 2.2, GOLD)
    # headlines
    draw_text(cv, head1, x + 16, y + 25, 3.55, INK, bold=True)
    draw_text(cv, head2, x + 16, y + 56, 3.55, INK, bold=True)
    # divider
    cv.rect(x + 16, y + 88, w - 32, 3, RED)
    # sub-caption
    draw_text(cv, sub1, x + 16, y + 97, 2.5, SUBC)
    draw_text(cv, sub2, x + 16, y + 118, 2.5, SUBC)
    # scene
    sx, sy, sw, sh = x + 12, y + 142, w - 24, h - 152
    scene(cv, sx, sy, sw, sh)
    cv.frame(sx, sy, sw, sh, (206, 200, 184), 1.6)


def draw_poster():
    cv = Canvas(W, H, CREAM)
    # ---- masthead ----
    cv.rect(0, 0, W, 176, NAVY)
    cv.halftone(6, 8, W - 12, 158, NAVY_DOT, 17, 1.4, 1.4, drift=8.0)
    draw_text_center(cv, "THE WORLD IN ONE PICTURE", W / 2, 16, 3.1, GOLD,
                     bold=True)
    cv.rect(120, 24, 120, 2.4, GOLD)
    cv.rect(W - 240, 24, 120, 2.4, GOLD)
    draw_text_center(cv, "18 NOVEMBER 2026", W / 2, 48, 9.6, WHITE, bold=True)
    cv.rect(232, 136, 150, 2.4, GOLD)
    cv.rect(W - 382, 136, 150, 2.4, GOLD)
    draw_text_center(cv, "WEDNESDAY", W / 2, 122, 4.4, GOLD, bold=True)
    cv.rect(0, 168, W, 4, GOLD)
    cv.rect(0, 174, W, 2, GOLD_DK)
    # ---- panels ----
    pw, ph = 488, 233
    for i, (tag, h1, h2, s1, s2, scene) in enumerate(PANELS):
        px = 18 + (i % 2) * (pw + 12)
        py = 192 + (i // 2) * (ph + 12)
        draw_panel(cv, px, py, pw, ph, tag, h1, h2, s1, s2, scene)
    # ---- ticker ----
    cv.rect(0, 924, W, 100, NAVY)
    cv.rect(0, 924, W, 4, GOLD)
    draw_text_center(cv, TICKER_1, W / 2, 944, 2.15, WHITE, tracking=-1.1,
                     bold=True)
    draw_text_center(cv, TICKER_2, W / 2, 976, 2.0, (238, 214, 150),
                     tracking=-1.3)
    return cv


# --------------------------------------------------------------------------
# Downscale, grain, PNG encode
# --------------------------------------------------------------------------

def downscale(cv):
    """Box-downscale the SS canvas to W x H, then add deterministic grain."""
    sw, sh = cv.w, cv.h
    src = cv.buf
    out = bytearray(W * H * 3)
    for yy in range(H):
        r0 = (yy * SS) * sw * 3
        r1 = ((yy * SS) + 1) * sw * 3
        orow = yy * W * 3
        for xx in range(W):
            i0 = r0 + xx * SS * 3
            i1 = r1 + xx * SS * 3
            o = orow + xx * 3
            g = int(hash2(xx, yy) * 3.0) - 1     # grain in [-1, +1]
            for c in range(3):
                v = (src[i0 + c] + src[i0 + 3 + c] + src[i1 + c]
                     + src[i1 + 3 + c]) // 4 + g
                out[o + c] = 0 if v < 0 else (255 if v > 255 else v)
    return out


def encode_png(pixels):
    raw = bytearray()
    stride = W * 3
    for yy in range(H):
        raw.append(0)
        raw += pixels[yy * stride:(yy + 1) * stride]

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        c += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return c

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def main():
    cv = draw_poster()
    data = encode_png(downscale(cv))
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "entry.png"), "wb") as f:
        f.write(data)


if __name__ == "__main__":
    main()
