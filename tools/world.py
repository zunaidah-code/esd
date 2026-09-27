"""The long paper-craft river town. Two versions (polluted / restored) are blended per
column so each river section can turn from grey to clean cyan."""
import math, random, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from lib import *

PW, PH = 10000, 900
SEG0, SW = 700, 1100
BOUNDS = [0] + [SEG0 + i * SW for i in range(1, 8)] + [PW]
CACHE = "/home/user/esd/build/cache"


def seg_center(i): return (BOUNDS[i] + BOUNDS[i + 1]) / 2 if 0 < i < 7 else (SEG0 + SW / 2 if i == 0 else SEG0 + 7.5 * SW)


def ytop(x): return 585 + 18 * math.sin(x / 260) + 10 * math.sin(x / 97)
def ybot(x): return ytop(x) + 150 + 12 * math.sin(x / 180)


def _grey(c, k=0.25):
    l = 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
    return tuple(int(lerp(l, v, k) * 0.92) for v in c)


def build(clean):
    im = paper(PW, PH, CREAM, seed=11, amp=4).convert("RGBA")
    d = ImageDraw.Draw(im)
    col = (lambda c: c) if clean else _grey
    r = random.Random(5)
    # scraps of grid paper / kraft along the sky
    for x in range(0, PW, 900):
        w, h = r.randint(260, 420), r.randint(90, 150)
        sx, sy = x + r.randint(0, 400), r.randint(-40, 40)
        kind = r.random()
        base = (250, 250, 247) if kind < .5 else (205, 176, 136)
        s = paper(w, h, base, seed=x, amp=3).convert("RGBA")
        if kind < .5:
            sd = ImageDraw.Draw(s)
            for gx in range(0, w, 16): sd.line([(gx, 0), (gx, h)], fill=(190, 205, 225), width=1)
            for gy in range(0, h, 16): sd.line([(0, gy), (w, gy)], fill=(190, 205, 225), width=1)
        s.putalpha(torn_mask(w, h, jag=7, seed=x))
        im.alpha_composite(shadowed(s, off=(2, 3), blur=4, opacity=0.2), (sx, sy))
    # soft sky wash
    sky = Image.new("RGBA", (PW, 420), col((190, 228, 236)) + (0,))
    a = (110 * np.sin(np.linspace(0, np.pi, 420)))[:, None].repeat(PW, 1).astype(np.uint8)
    sky.putalpha(Image.fromarray(a)); im.alpha_composite(sky, (0, 120))
    # hills
    for layer, (base_y, amp, c) in enumerate(((420, 60, (160, 206, 128)), (470, 45, (118, 180, 98)))):
        pts = [(0, PH)]
        for x in range(0, PW + 40, 40):
            pts.append((x, base_y - amp * (0.5 + 0.5 * math.sin(x / (380 - layer * 90) + layer)) - 20 * math.sin(x / 150)))
        pts.append((PW, PH))
        d.polygon(pts, fill=col(c))
        d.line(pts[1:-1], fill=(255, 255, 255), width=3)
    # buildings + trees
    x = 20
    pal = [MUSTARD, ORANGE, TEAL, GREEN, (70, 190, 210), (250, 238, 214), (240, 160, 90)]
    while x < PW - 40:
        bw, bh = r.randint(70, 150), r.randint(90, 230)
        c = pal[r.randrange(len(pal))]
        bottom = int(ytop(x + bw / 2)) - 4
        if 9150 < x < 9700:  # leave room for the town hall
            x += bw; continue
        if r.random() < 0.25:  # tree
            tr = r.randint(30, 55)
            d.rectangle((x + tr - 5, bottom - 60, x + tr + 5, bottom), fill=col((130, 90, 60)))
            d.ellipse((x, bottom - 60 - 2 * tr, x + 2 * tr, bottom - 50), fill=col(GREEN if clean else (150, 140, 110)),
                      outline=(255, 255, 255), width=3)
            x += 2 * tr + 10; continue
        top = bottom - bh
        d.rectangle((x, top, x + bw, bottom), fill=col(c), outline=(255, 255, 255), width=3)
        if r.random() < 0.6:
            d.polygon([(x - 8, top + 2), (x + bw / 2, top - 38), (x + bw + 8, top + 2)], fill=col((206, 88, 64)),
                      outline=(255, 255, 255))
        for wy in range(top + 18, bottom - 30, 34):
            for wx in range(x + 14, x + bw - 24, 30):
                d.rectangle((wx, wy, wx + 14, wy + 18), fill=col((250, 244, 225)) if clean else (120, 120, 118))
        x += bw + r.randint(4, 30)
    # town hall at the far end
    hx, hb = 9420, int(ytop(9420)) - 4
    d.rectangle((hx - 190, hb - 170, hx + 190, hb), fill=col((246, 242, 232)), outline=(200, 190, 175), width=3)
    d.polygon([(hx - 210, hb - 170), (hx, hb - 260), (hx + 210, hb - 170)], fill=col((236, 230, 218)), outline=(200, 190, 175))
    for k in range(6):
        cx = hx - 150 + k * 60
        d.rectangle((cx - 10, hb - 160, cx + 10, hb - 8), fill=(255, 255, 255), outline=(210, 200, 185))
    d.rectangle((hx - 40, hb - 320, hx + 40, hb - 250), fill=col((246, 242, 232)), outline=(200, 190, 175), width=3)
    d.ellipse((hx - 22, hb - 305, hx + 22, hb - 261), fill=(255, 255, 255), outline=INK, width=3)
    lbl = card("TOWN HALL", 200, 44, bg=(250, 247, 238), size=30, seed=4)
    im.alpha_composite(lbl, (hx - lbl.width // 2, hb - 250))
    # river
    top = [(x, ytop(x)) for x in range(0, PW + 20, 20)]
    bot = [(x, ybot(x)) for x in range(PW, -20, -20)]
    d.polygon(top + bot, fill=CYAN if clean else (128, 126, 116))
    rr = random.Random(9)
    if clean:
        for _ in range(900):
            x = rr.uniform(0, PW); y = rr.uniform(ytop(x) + 18, ybot(x) - 14); w = rr.uniform(30, 80)
            d.arc((x, y - 8, x + w, y + 8), 200, 340, fill=(200, 243, 250), width=3)
    else:
        for _ in range(600):
            x = rr.uniform(0, PW); y = rr.uniform(ytop(x) + 14, ybot(x) - 10); w = rr.uniform(40, 120)
            d.ellipse((x, y - 6, x + w, y + 6), fill=(108, 106, 98))
        for _ in range(170):  # crumpled newspaper litter
            x = rr.uniform(0, PW); y = rr.uniform(ytop(x) + 25, ybot(x) - 25); s = rr.uniform(16, 34)
            pts = [(x + s * math.cos(a) * rr.uniform(.6, 1.1), y + s * .7 * math.sin(a) * rr.uniform(.6, 1.1))
                   for a in np.linspace(0, 2 * math.pi, 9)[:-1]]
            d.polygon(pts, fill=(212, 210, 200), outline=(150, 148, 140))
            d.line([pts[0], pts[4]], fill=(150, 148, 140), width=2)
    d.line(top, fill=(255, 255, 255), width=8)
    # foreground bank
    fg = [(x, ybot(x)) for x in range(0, PW + 20, 20)] + [(PW, PH), (0, PH)]
    d.polygon(fg, fill=(241, 232, 208) if clean else (222, 216, 202))
    d.line(fg[:-2], fill=(255, 255, 255), width=8)
    rr = random.Random(3)
    for _ in range(420):
        x = rr.uniform(0, PW); y = ybot(x) + rr.uniform(20, 160)
        c = (110, 180, 90) if clean else (170, 160, 130)
        for k in range(3):
            d.line([(x + k * 5, y), (x + k * 5 + rr.uniform(-6, 6), y - rr.uniform(10, 22))], fill=c, width=3)
    arr = np.asarray(im.convert("RGB"), np.float32)
    arr *= (1 + 0.035 * paper_noise(PW, PH, seed=21))[..., None] / 1.0
    return np.clip(arr, 0, 255).astype(np.uint8)


_P = {}
def pano():
    if not _P:
        os.makedirs(CACHE, exist_ok=True)
        for k, clean in (("grey", False), ("clean", True)):
            f = f"{CACHE}/pano_{k}.png"
            if not os.path.exists(f): Image.fromarray(build(clean)).save(f)
            _P[k] = Image.open(f).convert("RGB")
    return _P


def weights(xs, progress):
    """xs: pano x coords (array). progress: list of 8 values 0..1 -> blend weight per column."""
    w = np.zeros_like(xs, dtype=np.float32)
    for i, p in enumerate(progress):
        if p <= 0: continue
        a, b = BOUNDS[i], BOUNDS[i + 1]
        if p >= 1:
            w = np.maximum(w, ((xs >= a - 1) & (xs <= b + 1)).astype(np.float32)); continue
        front = a + p * (b - a + 260) - 130
        w = np.maximum(w, np.clip((front - xs) / 260 + 0.5, 0, 1) * ((xs >= a - 130) & (xs <= b + 130)))
    return np.clip(w, 0, 1)


class Cam:
    def __init__(self, cx, cy, z): self.cx, self.cy, self.z = cx, cy, z
    def box(self):
        hw, hh = W / (2 * self.z), H / (2 * self.z)
        self.cx = min(max(self.cx, hw), PW - hw); self.cy = min(max(self.cy, hh), PH - hh)
        return (self.cx - hw, self.cy - hh, self.cx + hw, self.cy + hh)
    def s(self, px, py): return ((px - self.cx) * self.z + W / 2, (py - self.cy) * self.z + H / 2)


def world_frame(cam, progress):
    P = pano()
    box = cam.box()
    g = P["grey"].resize((W, H), Image.BILINEAR, box=box)
    xs = np.linspace(box[0], box[2], W, dtype=np.float32)
    w = weights(xs, progress)
    if w.max() <= 0: return g.convert("RGBA")
    c = P["clean"].resize((W, H), Image.BILINEAR, box=box)
    if w.min() >= 1: return c.convert("RGBA")
    ga, ca = np.asarray(g, np.float32), np.asarray(c, np.float32)
    out = ga * (1 - w[None, :, None]) + ca * w[None, :, None]
    return Image.fromarray(out.astype(np.uint8)).convert("RGBA")


def crop_world(box, size, clean):
    """a still snippet of the world (used for the 2035 future cards)."""
    return pano()["clean" if clean else "grey"].resize(size, Image.BILINEAR, box=box)
