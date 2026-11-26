"""Draws the v2 face's small images (gloves + icons) with the exact geometry of the Face Lab.

Run:  python deploy/esphome/v2/img/make_images.py   (needs Pillow)
Writes the PNGs next to this file. The firmware downloads them by URL at compile time, so a
changed image needs a NEW file name (ESPHome caches downloads by URL).

Every shape is drawn like the Face Lab canvas: a black copy grown by 3.5 px (the outline that
keeps a glove readable when it passes over an eye), then the colour on top, shape by shape in
draw order, so later fingers outline themselves over earlier ones.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

OUT = Path(__file__).resolve().parent
SS = 4                      # supersampling factor for smooth edges
AQUA = (94, 240, 226, 255)
BLACK = (0, 0, 0, 255)
PINK = (255, 121, 176, 255)
WHITE = (242, 255, 253, 255)
BLUE = (125, 185, 255, 255)
AMBER = (255, 198, 90, 255)
GREY = (184, 196, 194, 255)


def canvas(w, h):
    return Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))


def finish(img, name):
    w, h = img.size[0] // SS, img.size[1] // SS
    img.resize((w, h), Image.LANCZOS).save(OUT / name)


def pill_layer(w, h, r, col, grow):
    """One rounded rectangle (w×h, radius r) grown by `grow` px, centred in its own layer."""
    W, H = (w + 2 * grow + 4) * SS, (h + 2 * grow + 4) * SS
    lay = Image.new("RGBA", (int(W), int(H)), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    x0, y0 = (W - (w + 2 * grow) * SS) / 2, (H - (h + 2 * grow) * SS) / 2
    d.rounded_rectangle([x0, y0, x0 + (w + 2 * grow) * SS, y0 + (h + 2 * grow) * SS],
                        radius=(r + grow) * SS, fill=col)
    return lay


def stamp(img, layer, cx, cy, rot):
    """Rotate `layer` by rot degrees (clockwise, like canvas.rotate) and centre it on (cx, cy)."""
    if rot:
        layer = layer.rotate(-rot, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(layer, (int(cx * SS - layer.size[0] / 2), int(cy * SS - layer.size[1] / 2)))


def shape(img, s, ox, oy):
    """s = ('rr', x, y, w, h, r, rot) or ('c', x, y, r); drawn as outline then aqua fill."""
    if s[0] == "c":
        _, x, y, r = s
        w = h = 2 * r
        rr, rot = r, 0
    else:
        _, x, y, w, h, rr, rot = s
    for col, grow in ((BLACK, 3.5), (AQUA, 0)):
        stamp(img, pill_layer(w, h, min(rr, w / 2, h / 2), col, grow), ox + x, oy + y, rot)


def pill(x, y, w, h, rot=0):
    return ("rr", x, y, w, h, min(w, h) / 2, rot)


def glove(pose):
    """The Face Lab's `handShapes('gloves', pose)`, palm centre at (0, 0), fingers up."""
    S = []
    if pose == "scissors":                     # a V: index + middle up, the rest folded, thumb across
        for x in (4.5, 13.5):
            S.append(("c", x, -8, 5.5))
        S.append(pill(-13, -16, 9, 30, -12))
        S.append(pill(-2, -18, 9, 32, 10))
        S.append(("rr", 0, 8, 38, 32, 12, 0))
        S.append(pill(-6, 8, 22, 9))
        return S
    if pose in ("fist", "thumb", "point"):
        for x in ([-4.5, 4.5, 13.5] if pose == "point" else [-13.5, -4.5, 4.5, 13.5]):
            S.append(("c", x, -8, 5.5))
        if pose == "point":
            S.append(pill(-13.5, -20, 9, 32))
        if pose == "thumb":
            S.append(pill(-9, -18, 10, 28))
        S.append(("rr", 0, 8, 38, 32, 12, 0))
        if pose != "thumb":
            S.append(pill(-6, 8, 22, 9))
    else:
        for x, r in ((-13.5, -8), (-4.5, -3), (4.5, 3), (13.5, 8)):
            S.append(pill(x, -14, 9, 26, r))
        S.append(pill(-22, 6, 10, 24, -45))
        S.append(("rr", 0, 8, 36, 32, 12, 0))
    return S


def make_gloves():
    for pose in ("open", "fist", "thumb", "point", "scissors"):
        img = canvas(92, 92)
        for s in glove(pose):
            shape(img, s, 46, 46)
        small = img.resize((92, 92), Image.LANCZOS)
        small.save(OUT / f"glove_{pose}_r.png")
        ImageOps.mirror(small).save(OUT / f"glove_{pose}_l.png")


def bez(p0, p1, p2, p3, n=24):
    pts = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def quad(p0, p1, p2, n=16):
    pts = []
    for i in range(n + 1):
        t = i / n
        a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
        pts.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]))
    return pts


def poly(img, pts, col):
    ImageDraw.Draw(img).polygon([(x * SS, y * SS) for x, y in pts], fill=col)


def make_heart(size=40):
    img, cx, cy, k = canvas(size, size), size / 2, size / 2, size / 2 / 1.3
    pts = bez((cx, cy + k * .9), (cx - k * 1.3, cy + k * .05), (cx - k * .95, cy - k * 1.1), (cx, cy - k * .42))
    pts += bez((cx, cy - k * .42), (cx + k * .95, cy - k * 1.1), (cx + k * 1.3, cy + k * .05), (cx, cy + k * .9))
    poly(img, pts, PINK)
    finish(img, "heart.png")


def make_spark(size=26):
    img, c, s = canvas(size, size), size / 2, size / 2 - 2
    pts = quad((c, c - s), (c + s * .12, c - s * .12), (c + s, c)) + quad((c + s, c), (c + s * .12, c + s * .12), (c, c + s))
    pts += quad((c, c + s), (c - s * .12, c + s * .12), (c - s, c)) + quad((c - s, c), (c - s * .12, c - s * .12), (c, c - s))
    poly(img, pts, WHITE)
    finish(img, "spark.png")


def make_drop(size=24):
    img, cx, s = canvas(size, size), size / 2, 10.0
    cy = size / 2 - 1
    pts = bez((cx, cy - s), (cx + s * .2, cy - s * .5), (cx + s * .62, cy - s * .1), (cx + s * .62, cy + s * .28))
    pts += [(cx + s * .62 * math.cos(a), cy + s * .28 + s * .62 * math.sin(a)) for a in [i * math.pi / 20 for i in range(21)]]
    pts += bez((cx - s * .62, cy + s * .28), (cx - s * .62, cy - s * .1), (cx - s * .2, cy - s * .5), (cx, cy - s))
    poly(img, pts, BLUE)
    finish(img, "drop.png")


def make_bell(size=52, s=24):
    img, cx, cy = canvas(size, size), size / 2, size / 2 + 2
    pts = quad((cx - s * .78, cy + s * .42), (cx - s * .58, cy + s * .28), (cx - s * .56, cy - s * .12))
    pts += quad((cx - s * .56, cy - s * .12), (cx - s * .5, cy - s * .78), (cx, cy - s * .8))
    pts += quad((cx, cy - s * .8), (cx + s * .5, cy - s * .78), (cx + s * .56, cy - s * .12))
    pts += quad((cx + s * .56, cy - s * .12), (cx + s * .58, cy + s * .28), (cx + s * .78, cy + s * .42))
    poly(img, pts, AMBER)
    d = ImageDraw.Draw(img)
    r = s * .17
    d.ellipse([(cx - r) * SS, (cy + s * .58 - r) * SS, (cx + r) * SS, (cy + s * .58 + r) * SS], fill=AMBER)
    d.rounded_rectangle([(cx - s * .11) * SS, (cy - s * .98) * SS, (cx + s * .11) * SS, (cy - s * .78) * SS], radius=s * .06 * SS, fill=AMBER)
    finish(img, "bell.png")


def make_bulb(size=92):
    img, c = canvas(size, size), size / 2
    d = ImageDraw.Draw(img)
    cy = c - 4
    d.ellipse([(c - 14) * SS, (cy - 14) * SS, (c + 14) * SS, (cy + 14) * SS], fill=AMBER)
    d.rounded_rectangle([(c - 6) * SS, (cy + 16) * SS, (c + 6) * SS, (cy + 24) * SS], radius=2 * SS, fill=GREY)
    for dx, dy in ((-1, -1), (1, -1), (-1.3, .2), (1.3, .2)):
        d.line([((c + dx * 22) * SS, (cy + dy * 18) * SS), ((c + dx * 30) * SS, (cy + dy * 25) * SS)], fill=AMBER, width=3 * SS)
    finish(img, "bulb.png")


def make_spiral(size=78, R=30.0, w=9):
    img = canvas(size, size)
    d = ImageDraw.Draw(img)
    c = size / 2
    for i in range(3):
        r = R * (1 - i * .32)
        a0 = math.degrees(i * 2.1)
        a1 = math.degrees(i * 2.1 + 4.3)
        box = [(c - r) * SS, (c - r) * SS, (c + r) * SS, (c + r) * SS]
        d.arc(box, start=a0, end=a1, fill=AQUA, width=int(w * SS))
        for a in (a0, a1):   # round caps
            x, y = c + r * math.cos(math.radians(a)), c + r * math.sin(math.radians(a))
            d.ellipse([(x - w / 2) * SS, (y - w / 2) * SS, (x + w / 2) * SS, (y + w / 2) * SS], fill=AQUA)
    finish(img, "spiral.png")


def make_xeye(size=78, half=24, w=14):
    """Two crossed rounded bars: the "knocked out" eye of the Bang game."""
    img = canvas(size, size)
    c = size / 2
    for rot in (45, -45):
        shape_only = pill_layer(2 * half + w, w, w / 2, AQUA, 0)
        stamp(img, shape_only, c, c, rot)
    finish(img, "x_eye.png")


if __name__ == "__main__":
    make_xeye()
    make_gloves()
    make_heart()
    make_spark()
    make_drop()
    make_bell()
    make_bulb()
    make_spiral()
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))
