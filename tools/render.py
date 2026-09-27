"""Render the ESD 'Bandar Kertas Lestari' animated video (16:9, 1280x720, 25 fps).

python3 render.py            -> build/esd_video.mp4 (+ .srt)
python3 render.py --still S T -> preview one frame of scene S at local time T
"""
import json, math, os, subprocess, sys, random
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
from scipy.io import wavfile
from scipy.signal import resample_poly
from lib import *
import world as Wd
from world import Cam, world_frame, seg_center, ytop, ybot

ROOT = "/home/user/esd"
BUILD = f"{ROOT}/build"
AUD = f"{BUILD}/audio"
META = json.load(open(f"{AUD}/meta.json"))
XF = 0.45  # cross-fade between scenes (s)

COMPS = ["SYSTEMS THINKING", "CRITICAL THINKING", "ANTICIPATORY", "NORMATIVE",
         "SELF-AWARENESS", "STRATEGIC", "COLLABORATION"]
FEET = 820  # world y where characters stand (foreground bank)


# ================================================================ assets
def _cut(name, off=(8, 10), blur=10):
    im = Image.open(f"{A}cutouts/{name}.png").convert("RGBA")
    s = shadowed(im, off=off, blur=blur, opacity=0.35)
    pad = (s.width - im.width) // 2
    s.anchor = (0.5, (pad + im.height) / s.height)
    return s


HAKIM = _cut("hakim_stand")
KNEEL = _cut("hakim_kneel")
HALL_H = _cut("hakim_hall")
LECT = _cut("lecturer")
IMG1 = Image.open(f"{A}scene15_storyboard.jpg").convert("RGB")
IMG2 = Image.open(f"{A}scene06_storyboard.jpg").convert("RGB")
IMG3 = Image.open(f"{A}scene08_collaboration.jpg").convert("RGB")

# hi-res plate of the Town Hall two-shot (storyboard panel 1, subtitle & label cropped out)
PX0, PY0, PK = 100, 8, 3
PLATE = np.asarray(IMG1.crop((PX0, PY0, 688, 339)).resize((588 * PK, 331 * PK), Image.LANCZOS)
                   .filter(ImageFilter.UnsharpMask(2, 60, 2)), np.float32)
def pp(x, y): return ((x - PX0) * PK, (y - PY0) * PK)   # storyboard px -> plate px
HAKIM_MOUTH, LECT_MOUTH = pp(213, 137.5), pp(507.5, 153)
LECT_HEAD, LECT_HAND = pp(507, 128), pp(362, 212)
NOTEBOOK = pp(252, 246)

# living-town panel (storyboard panel 4)
LIVING = IMG1.crop((700, 392, 1368, 690)).filter(ImageFilter.UnsharpMask(1.5, 50, 2))
LX0, LY0 = 700, 392


def living_view(x0, y0, w):
    """16:9 window of the living-town panel (storyboard coords)."""
    h = w * 9 / 16
    x0 = clamp(x0, LX0, LX0 + LIVING.width - w); y0 = clamp(y0, LY0, LY0 + LIVING.height - h)
    return LIVING.resize((W, H), Image.BICUBIC, box=(x0 - LX0, y0 - LY0, x0 - LX0 + w, y0 - LY0 + h)).convert("RGBA")


def panel2(r, c, inset=9):
    return IMG2.crop((c * 344 + inset, r * 256 + inset, (c + 1) * 344 - inset, (r + 1) * 256 - inset))


def photo(img, w, seed=0):
    """scrapbook photo: white torn border + shadow."""
    h = int(img.height * w / img.width)
    b = 14
    base = paper(w + 2 * b, h + 2 * b, (252, 251, 247), seed=seed, amp=2).convert("RGBA")
    base.putalpha(torn_mask(w + 2 * b, h + 2 * b, jag=6, seed=seed))
    base.paste(img.resize((w, h), Image.LANCZOS), (b, b))
    return shadowed(base, off=(6, 9), blur=9, opacity=0.35)


def frame_border():
    m = torn_mask(W - 24, H - 24, jag=9, seed=77, step=9)
    a = Image.new("L", (W, H), 255); a.paste(Image.eval(m, lambda v: 255 - v), (12, 12))
    a = a.filter(ImageFilter.GaussianBlur(0.7))
    im = paper(W, H, (250, 248, 242), seed=78, amp=2).convert("RGBA"); im.putalpha(a)
    return shadowed(im, off=(0, 2), blur=4, opacity=0.25).crop((0, 0, W, H)) if False else im
BORDER = frame_border()


# ================================================================ lip-sync envelopes
_ENV = {}
def envelope(key):
    if key not in _ENV:
        sr, x = wavfile.read(f"{AUD}/{key}_raw.wav")
        x = x.astype(np.float32); x /= np.abs(x).max() + 1e-9
        hop = sr // FPS
        rms = np.array([np.sqrt(np.mean(x[i:i + hop * 2] ** 2)) for i in range(0, len(x), hop)])
        rms /= np.percentile(rms, 95) + 1e-9
        o = np.clip((rms - 0.12) / 0.75, 0, 1) ** 0.8
        sm = np.zeros_like(o)
        for i in range(len(o)):
            prev = sm[i - 1] if i else 0
            sm[i] = prev + (o[i] - prev) * (0.75 if o[i] > prev else 0.45)
        _ENV[key] = sm
    return _ENV[key]


def mouth(key, t):
    e = envelope(key); i = int(t * FPS)
    return float(e[i]) if 0 <= i < len(e) else 0.0


# ================================================================ scene helpers
def progress(done, k=None, p=0.0):
    pr = [1.0 if i < done else 0.0 for i in range(8)]
    if k is not None: pr[k] = p
    return pr


def flag_pos(i): x = seg_center(i) + 330; return x, ytop(x) + 2


def draw_flags(fr, cam, earned, rising=None, t=0.0, t_rise=0.0):
    for i in range(7):
        if i < earned or i == rising:
            x, y = flag_pos(i)
            sx, sy = cam.s(x, y)
            if not (-200 < sx < W + 300): continue
            u = 1.0 if i != rising else ease_out(seg(t, t_rise, t_rise + 1.1))
            if u <= 0: continue
            place(fr, flag(COMPS[i]), sx, sy + (1 - u) * 150 * cam.z, scale=cam.z * 0.95, alpha=u,
                  rot=2.5 * math.sin(t * 2.2 + i))


def put_char(fr, img, cam, wx, wy=FEET, scale=0.95, flip=False, bob=0.0):
    sx, sy = cam.s(wx, wy)
    place(fr, img, sx, sy - bob, scale=scale * cam.z, flip=flip)


def walk_bob(t, moving): return abs(math.sin(t * 7.5)) * 7 if moving else 0.0


def zoom_frame(fr, z, fx=0.5, fy=0.5):
    if abs(z - 1) < 1e-3: return fr
    w, h = W / z, H / z
    x0, y0 = (W - w) * fx, (H - h) * fy
    return fr.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + w, y0 + h))


def sparkle(d, x, y, r, a=255):
    c = (255, 255, 255, a)
    d.polygon([(x, y - r), (x + r * .25, y - r * .25), (x + r, y), (x + r * .25, y + r * .25),
               (x, y + r), (x - r * .25, y + r * .25), (x - r, y), (x - r * .25, y - r * .25)], fill=c)


# ================================================================ scenes
def sc_title(t, d):
    fr = paper(W, H, CREAM, seed=3, amp=4).convert("RGBA")
    for i, (x, y, w, h, c) in enumerate(((60, 40, 360, 140, (250, 250, 247)), (900, 520, 330, 150, (205, 176, 136)),
                                          (820, 60, 300, 110, (190, 228, 236)))):
        s = paper(w, h, c, seed=i).convert("RGBA"); s.putalpha(torn_mask(w, h, 7, seed=i))
        place(fr, shadowed(s), x + w / 2, y + h / 2, rot=(-3, 2, 4)[i])
    u = back_out(seg(t, 0.2, 0.9))
    place(fr, card("BANDAR KERTAS LESTARI", 820, 120, bg=MUSTARD, size=76, seed=5), 640, 280, scale=u, rot=-1.5)
    place(fr, card("Education for Sustainable Development (ESD)", 700, 64, bg=(255, 255, 255), size=36, seed=6),
          640, 400, scale=back_out(seg(t, 0.8, 1.4)), rot=1)
    for k, n in enumerate(("leaf", "coin", "people")):
        place(fr, icon(n), 480 + k * 160, 540, scale=0.7 * pop(t, 1.3 + 0.3 * k))
    return fr


def sc01(t, d):
    """WHAT IS ESD? grey town, banner unfolds, leaf -> coin -> people."""
    c0 = seg_center(0) - 120
    z = lerp(1.0, 1.08, ease_in_out(t / d))
    cam = Cam(c0 + 40 * t / d, lerp(480, 470, t / d), z)
    fr = world_frame(cam, progress(0))
    u = ease_out(seg(t, 0.6, 1.7))
    place(fr, card("EDUCATION FOR SUSTAINABLE DEVELOPMENT", 840, 76, bg=(255, 255, 255), size=38, seed=9),
          640, 92, sx=max(0.02, u), alpha=clamp(u * 3))
    vo0, vd = 0.7, META["s01"]["dur"]
    for k, (n, tw) in enumerate((("leaf", .80), ("coin", .87), ("people", .95))):
        s = pop(t, 2.3 + 0.8 * k)
        tb = vo0 + vd * tw
        s *= 1 + 0.18 * math.exp(-((t - tb) / 0.18) ** 2)
        place(fr, icon(n), 470 + 170 * k, 205, scale=0.72 * s, rot=3 * math.sin(t + k))
    # Hakim walks in from the left, stops, then steps right
    enter = ease_out(seg(t, 0.0, 2.4)); leave = ease_in_out(seg(t, d - 1.6, d)) if t > d - 1.6 else 0
    wx = cam.box()[0] + lerp(-120, 330, enter) / z + 260 * leave
    put_char(fr, HAKIM, cam, wx, bob=walk_bob(t, t < 2.4 or t > d - 1.6))
    return fr


def sc02(t, d):
    """SYSTEMS THINKING: arrows link factory -> river -> fish -> market -> houses -> factory."""
    c = seg_center(0) + 150
    u = ease_in_out(seg(t, 0.2, 2.8))
    cam = Cam(lerp(c - 330, c, u), lerp(610, 470, u), lerp(1.45, 1.0, u))
    fr = world_frame(cam, progress(0, 0, ease_in_out(seg(t, 5.2, 7.2))))
    draw_flags(fr, cam, 0, rising=0, t=t, t_rise=5.3)
    put_char(fr, KNEEL, cam, c - 420, FEET - 10, scale=1.75)
    nodes = {"factory": (c - 230, 330), "river": (c + 20, 250), "fish": (c + 270, 320),
             "market": (c + 170, 450), "houses": (c - 110, 460)}
    for k, (n, (x, y)) in enumerate(nodes.items()):
        sx, sy = cam.s(x, y)
        place(fr, icon(n), sx, sy, scale=0.66 * cam.z * pop(t, 0.6 + 0.12 * k))
    d_ = ImageDraw.Draw(fr)
    order = ["factory", "river", "fish", "market", "houses", "factory"]
    nb = cam.s(c - 390, FEET - 190)
    marker_arrow(d_, curve(nb, cam.s(c - 280, 380), 0.2), seg(t, 1.3, 1.9), width=int(5 * cam.z) + 1)
    for k in range(5):
        a, b = nodes[order[k]], nodes[order[k + 1]]
        ang = math.atan2(b[1] - a[1], b[0] - a[0]); r = 62
        p0 = cam.s(a[0] + r * math.cos(ang), a[1] + r * math.sin(ang))
        p1 = cam.s(b[0] - r * math.cos(ang), b[1] - r * math.sin(ang))
        t0 = 2.0 + 0.62 * k
        if t >= t0: marker_arrow(d_, curve(p0, p1, -0.22), seg(t, t0, t0 + 0.55), width=int(5 * cam.z) + 1)
    x, y = nodes["fish"]
    if t > 6.3: marker_arrow(d_, curve(cam.s(x + 70, y), cam.s(x + 420, y - 20), 0.1), seg(t, 6.3, 7.2), width=6)
    return fr


def sc03(t, d):
    """CRITICAL THINKING: lift the '100% ECO-FRIENDLY' flap, reveal the hidden pipe."""
    c = seg_center(1)
    u = ease_in_out(t / d)
    cam = Cam(lerp(c - 60, c + 30, u), lerp(480, 500, u), lerp(1.0, 1.14, u))
    fr = world_frame(cam, progress(1, 1, ease_in_out(seg(t, 5.0, 7.2))))
    draw_flags(fr, cam, 1, rising=1, t=t, t_rise=4.9)
    fx, fy = c + 120, 400
    sx, sy = cam.s(fx, fy)
    place(fr, icon("factory", 260), sx, sy, scale=cam.z)
    # pipe + sludge
    d_ = ImageDraw.Draw(fr)
    p0, p1 = cam.s(fx - 40, fy + 90), cam.s(fx - 40, ytop(fx - 40) + 30)
    w = 26 * cam.z
    d_.rectangle((p0[0] - w / 2, p0[1], p0[0] + w / 2, p1[1]), fill=(95, 95, 100), outline=(255, 255, 255), width=3)
    for k in range(7):
        ph = (t * 0.45 + k / 7) % 1
        bx, by = p1[0] + ph * 160 * cam.z, p1[1] + 10 + 20 * math.sin(ph * 6 + k)
        r = (10 + 8 * ph) * cam.z
        d_.ellipse((bx - r, by - r * .6, bx + r, by + r * .6), fill=(90, 88, 82, 220))
    # billboard flap (hinged at the top)
    flap = ease_in_out(seg(t, 1.8, 2.7))
    bx, by = cam.s(fx - 40, fy + 70)
    place(fr, card("100% ECO-FRIENDLY", 300, 120, bg=(120, 196, 96), fg=(255, 255, 255), size=40, seed=12),
          bx, by, anchor=(0.5, 0.08), scale=cam.z, sy=max(0.06, 1 - 0.9 * flap), rot=-4 * flap)
    # evidence: red circle + question mark
    cx_, cy_ = p1[0], (p0[1] + p1[1]) / 2 + 20
    r = 95 * cam.z
    marker_circle(d_, (cx_ - r, cy_ - r * 1.1, cx_ + r, cy_ + r * 1.1), seg(t, 3.1, 3.9), width=7)
    place(fr, Image.new("RGBA", (1, 1)), 0, 0)
    q = pop(t, 4.1)
    if q > 0:
        qi = Image.new("RGBA", (120, 160), (0, 0, 0, 0))
        ImageDraw.Draw(qi).text((10, -10), "?", font=font(FONT_MARK, 150), fill=RED, stroke_width=4, stroke_fill=(255, 255, 255))
        place(fr, qi, cx_ + r + 40 * cam.z, cy_ - r * 0.6, scale=q * cam.z, rot=-8)
    put_char(fr, HAKIM, cam, c - 300)
    return fr


def sc04(t, d):
    """ANTICIPATORY: two 2035 futures rise from the notebook."""
    c = seg_center(2)
    cam = Cam(lerp(c - 140, c + 60, ease_in_out(t / d)), 470, 1.02)
    fr = world_frame(cam, progress(2, 2, ease_in_out(seg(t, 5.0, 7.2))))
    draw_flags(fr, cam, 2, rising=2, t=t, t_rise=4.7)
    hx = c - 60
    look_right = t > 3.3
    put_char(fr, HAKIM, cam, hx, flip=not look_right)
    nb = cam.s(hx + (-55 if look_right else 55), FEET - 290)
    for k, (clean, target) in enumerate(((False, (330, 210)), (True, (960, 210)))):
        u = ease_out(seg(t, 0.5 + 0.5 * k, 1.8 + 0.5 * k))
        if u <= 0: continue
        snap = Wd.crop_world((seg_center(5) - 520, 190, seg_center(5) + 520, 780), (380, 214), clean)
        ph = photo(snap, 380, seed=20 + k)
        focus = (k == 0 and 1.2 < t < 3.3) or (k == 1 and t >= 3.3)
        s = u * (1.06 if focus else 0.94)
        x, y = lerp(nb[0], target[0], u), lerp(nb[1], target[1], u)
        place(fr, ph, x, y, scale=s * cam.z, rot=(-3, 3)[k] * u, alpha=clamp(u * 2) * (1 if focus or t < 1.2 else 0.75))
        place(fr, card("2035", 110, 50, bg=(255, 236, 140), size=32, seed=31 + k), x - 150 * s, y - 115 * s,
              scale=s, rot=-6)
    return fr


def sc05(t, d):
    """NORMATIVE: balance the fish and the market stall."""
    c = seg_center(3)
    cam = Cam(c, 470, lerp(1.0, 1.07, ease_in_out(t / d)))
    fr = world_frame(cam, progress(3, 3, ease_in_out(seg(t, 5.0, 7.2))))
    draw_flags(fr, cam, 3, rising=3, t=t, t_rise=4.8)
    put_char(fr, HAKIM, cam, c - 380)
    bx, by = cam.s(c + 110, 640)
    z = cam.z
    settle = seg(t, 2.6, 4.6)
    ang = 13 * (1 - ease_out(settle)) * math.cos(settle * 7) if settle < 1 else 0.0
    if t < 2.6: ang = 13 + 1.2 * math.sin(t * 3)
    d_ = ImageDraw.Draw(fr)
    top = by - 300 * z
    d_.polygon([(bx - 80 * z, by), (bx + 80 * z, by), (bx + 20 * z, by - 30 * z), (bx - 20 * z, by - 30 * z)], fill=(160, 110, 70))
    d_.rectangle((bx - 9 * z, top, bx + 9 * z, by - 25 * z), fill=(185, 132, 84), outline=(255, 255, 255), width=2)
    a = math.radians(ang); L = 230 * z
    ends = [(bx - L * math.cos(a), top + L * math.sin(a)), (bx + L * math.cos(a), top - L * math.sin(a))]
    d_.line(ends, fill=(150, 104, 64), width=int(14 * z)); d_.line(ends, fill=(206, 156, 100), width=int(8 * z))
    d_.ellipse((bx - 16 * z, top - 16 * z, bx + 16 * z, top + 16 * z), fill=MUSTARD, outline=(255, 255, 255), width=3)
    for k, (ex, ey) in enumerate(ends):
        py = ey + 120 * z
        d_.line([(ex, ey), (ex - 70 * z, py)], fill=INK, width=3); d_.line([(ex, ey), (ex + 70 * z, py)], fill=INK, width=3)
        d_.chord((ex - 85 * z, py - 30 * z, ex + 85 * z, py + 30 * z), 0, 180, fill=(236, 206, 120), outline=(255, 255, 255), width=3)
        place(fr, icon(("fish", "market")[k]), ex, py - 35 * z, scale=0.6 * z)
    # Hakim adds a leaf (value) to the lighter side
    u = ease_in_out(seg(t, 1.6, 2.7))
    if 1.6 < t:
        hx, hy = cam.s(c - 320, FEET - 260)
        ex, ey = ends[1]
        lx, ly = (lerp(hx, ex + 40 * z, u), lerp(hy, ey + 60 * z, u) - 120 * z * math.sin(math.pi * u)) if t < 2.7 else (ex + 40 * z, ey + 60 * z)
        place(fr, icon("leaf"), lx, ly, scale=0.38 * z)
    return fr


P6 = [panel2(0, 1), panel2(0, 2), panel2(0, 3), panel2(1, 0), panel2(1, 1), panel2(1, 2), panel2(1, 3)]
P6_MAP = IMG2.crop((696, 520, 1366, 690))


def sc06(t, d):
    """SELF-AWARENESS: storyboard shots (bottle swap) as scrapbook photos."""
    c = seg_center(4)
    cam = Cam(c, 470, 1.04)
    fr = world_frame(cam, progress(4, 4, ease_in_out(seg(t, 6.0, 7.8))))
    draw_flags(fr, cam, 4, rising=4, t=t, t_rise=6.2)
    times = [0.0, 0.9, 1.8, 2.7, 3.6, 4.4, 5.1]
    shrink = ease_in_out(seg(t, 5.9, 6.7))
    for k, im in enumerate(P6):
        t0 = times[k]
        if t < t0: break
        u = ease_out(seg(t, t0, t0 + 0.35))
        ph = photo(im, 840, seed=40 + k)
        rot = (-2.5, 2, -1.5, 2.5, -2, 1.5, -1)[k]
        zoom = 1 + 0.05 * (t - t0)
        if k < 6 and t > times[k + 1] + 0.4: continue
        if k == 6 or t < times[min(k + 1, 6)] + 0.4:
            x = lerp(640 + (300 if k % 2 else -300), 640, u); y = 340
            s = zoom * lerp(1, 0.34, shrink)
            x, y = lerp(x, 1040, shrink), lerp(y, 150, shrink)
            place(fr, ph, x, y, scale=s, rot=rot * u, alpha=clamp(u * 2))
    if t > 6.3:
        u = ease_out(seg(t, 6.3, 7.1))
        place(fr, photo(P6_MAP, 520, seed=48), 330, 170, scale=0.8 * u, rot=-3, alpha=u)
    return fr


MAP = IMG2.crop((984, 520, 1240, 706)).filter(ImageFilter.UnsharpMask(2, 60, 2))


def sc07(t, d):
    """STRATEGIC: top-down town map, sticky notes 1-2-3, dotted route to the river."""
    fr = paper(W, H, (212, 186, 146), seed=51, amp=6).convert("RGBA")
    z = lerp(0.9, 1.0, ease_out(seg(t, 0, 1.2)))
    river = paper(160, H, (128, 126, 116), seed=52).convert("RGBA")
    riv_clean = paper(160, H, CYAN, seed=53).convert("RGBA")
    k = ease_in_out(seg(t, 6.0, 7.6))
    rv = Image.blend(river, riv_clean, k); rv.putalpha(torn_mask(160, H, 10, seed=54, edges="l"))
    paste(fr, rv, W - 170, 0)
    mp = photo(MAP, 860, seed=55)
    place(fr, mp, 560, 360, scale=z, rot=-2)
    pts = [(380, 480), (590, 270), (820, 470)]
    d_ = ImageDraw.Draw(fr)
    route = curve(pts[0], pts[1], 0.15) + curve(pts[1], pts[2], 0.15)[1:] + curve(pts[2], (1150, 420), -0.1)[1:]
    L1 = 0.62
    marker_arrow(d_, route, lerp(0, L1, seg(t, 3.2, 4.8)) + (1 - L1) * seg(t, 4.8, 5.8), dashed=True, width=7, head=18)
    for i, (x, y) in enumerate(pts):
        s = pop(t, 1.0 + 0.8 * i)
        place(fr, card(str(i + 1), 88, 84, bg=(255, 226, 90), size=56, fontpath=FONT_MARK, seed=60 + i, jag=2),
              x, y, scale=s, rot=(-6, 4, -3)[i])
    place(fr, flag(COMPS[5], size=24, pole=170), 90, 330, alpha=ease_out(seg(t, 5.0, 6.0)),
          sy=ease_out(seg(t, 5.0, 6.0)) + 0.01, rot=2 * math.sin(t * 2))
    tr = ease_in_out(seg(t, 3.2, 5.8))
    place(fr, KNEEL, 150 + 30 * tr, 760, scale=1.9)
    return fr


def _collab_mask():
    a = np.asarray(IMG3, np.float32) / 255
    mx, mn = a.max(2), a.min(2)
    sat = (mx - mn) / (mx + 1e-6)
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    grp = np.zeros(a.shape[:2], np.float32)
    g = Image.open(f"{A}cutouts/group.png"); gb = g.getbbox()
    # locate group cut-out: it came from crop box (390, 80) -> bbox shift
    ga = np.asarray(g.getchannel("A"), np.float32) / 255
    grp[80:80 + ga.shape[0], 390:390 + ga.shape[1]] = ga[:min(ga.shape[0], 768 - 80), :min(ga.shape[1], 1376 - 390)]
    river = (sat < 0.16) & (mx < 0.78) & (yy > 330 + 0.42 * xx * 0) & (yy > 420) & (xx < 900)
    m = gaussian_filter(river.astype(np.float32), 1.2) * (1 - np.clip(grp * 3, 0, 1))
    lum = a.mean(2)
    clean = np.clip(np.array(CYAN, np.float32)[None, None] / 255 * (0.55 + 0.75 * lum[..., None]), 0, 1)
    return m, clean * 255


from scipy.ndimage import gaussian_filter
_CM = {}


def sc08(t, d):
    """COLLABORATION: the four lower the filter net together; the grey water clears."""
    if not _CM: _CM["m"], _CM["c"] = _collab_mask()
    base = np.asarray(IMG3, np.float32)
    prog = ease_in_out(seg(t, 4.4, 7.4))
    if prog > 0:
        xx = np.arange(base.shape[1], dtype=np.float32)[None, :]
        front = lerp(900, -150, prog)
        w = np.clip((xx - front) / 120, 0, 1) * _CM["m"]
        base = base * (1 - w[..., None]) + _CM["c"] * w[..., None]
    lift = math.sin(seg(t, 0.8, 5.0) * math.pi * 2) * 7 * (1 if 0.8 < t < 5 else 0)
    base = warp_shift(base, 560, 470, 120, 0, -lift)
    im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")
    d_ = ImageDraw.Draw(im, "RGBA")
    for k in range(4):
        ph = ((t - 1.5) * 0.5 + k / 4) % 1
        if t < 1.5: break
        r = 20 + 110 * ph
        d_.ellipse((560 - r, 600 - r * .3, 560 + r, 600 + r * .3), outline=(255, 255, 255, int(200 * (1 - ph))), width=3)
    u = ease_in_out(t / d)
    z = lerp(1.0, 1.13, u)
    cw, ch = 1376 / z, 768 / z
    cx, cy = lerp(688, 640, u), lerp(384, 360, u)
    return im.resize((W, H), Image.BICUBIC, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))


def sc09(t, d):
    """INTEGRATED PROBLEM-SOLVING: seven flags travel downstream and merge."""
    u = ease_in_out(seg(t, 0.5, d))
    cam = Cam(lerp(8280, 8420, u), lerp(470, 420, u), lerp(1.0, 0.84, u))
    tm = 4.6
    fr = world_frame(cam, progress(7, 7, ease_out(seg(t, tm, tm + 1.4))))
    target = (560, 330)
    put_char(fr, HAKIM, cam, 8650, flip=True, scale=0.95)
    for i in range(7):
        t0 = 0.6 + 0.33 * i
        sx, sy = cam.s(*flag_pos(i))
        k = ease_in_out(seg(t, t0, t0 + 1.9))
        if t > tm: break
        x = lerp(max(sx, -200 - 40 * i), target[0] + (i - 3) * 14, k)
        y = lerp(sy, target[1] + 140, k) - 90 * math.sin(math.pi * k)
        place(fr, flag(COMPS[i]), x, y, scale=cam.z * lerp(0.95, 0.75, k), rot=5 * math.sin(t * 3 + i),
              alpha=1 - seg(t, tm - 0.25, tm))
    s = pop(t, tm, 0.6)
    if s > 0:
        place(fr, flag("INTEGRATED PROBLEM-SOLVING", size=36, pole=230, color=(255, 236, 120), big=True),
              target[0] - 40, target[1] + 190, scale=s, rot=2 * math.sin(t * 2))
        dd = ImageDraw.Draw(fr, "RGBA")
        b = seg(t, tm, tm + 1.2)
        for j in range(14):
            a = j / 14 * 2 * math.pi
            rr = 60 + 260 * ease_out(b)
            sparkle(dd, target[0] + 100 + rr * math.cos(a), target[1] + rr * 0.6 * math.sin(a), 14 * (1 - b), int(255 * (1 - b)))
    return fr


RIVER_PTS = [(935, 686), (955, 650), (985, 618), (1040, 600), (1110, 588), (1170, 568), (1215, 552)]


def sc10(t, d):
    """AHA: LIVING RIVER — crane over the restored town, then Hakim beside the river."""
    if t < 4.4:
        u = ease_in_out(seg(t, 0, 4.4))
        x0, y0, w = lerp(760, 790, u), lerp(530, 395, u), lerp(290, 505, u)
        fr = living_view(x0, y0, w)
        h = w * 9 / 16; k = W / w
        d_ = ImageDraw.Draw(fr, "RGBA")
        for i in range(18):
            p = RIVER_PTS[i % len(RIVER_PTS)]
            ph = (t * 0.8 + i * 0.37) % 1
            sx, sy = (p[0] + (i * 13) % 30 - 15 - x0) * k, (p[1] + (i * 7) % 16 - 8 - y0) * k
            sparkle(d_, sx, sy, 9 * math.sin(math.pi * ph), int(230 * math.sin(math.pi * ph)))
        return fr
    u = ease_in_out(seg(t, 4.4, d))
    x0, y0, w = lerp(905, 960, u), lerp(525, 470, u), lerp(300, 330, u)
    fr = living_view(x0, y0, w)
    place(fr, HAKIM, lerp(300, 170, u), 830, scale=1.15)
    return fr


def hall_bg():
    fr = Image.new("RGBA", (W, H))
    wall = np.linspace(0, 1, H)[:, None, None]
    arr = np.array((222, 204, 176), np.float32) * (1 - 0.12 * wall)
    arr = np.broadcast_to(arr, (H, W, 3)).copy()
    arr *= (1 + 0.03 * paper_noise(W, H, seed=90))[..., None]
    fr = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    d_ = ImageDraw.Draw(fr)
    for x in range(0, W, 160): d_.line([(x, 60), (x, 520)], fill=(205, 184, 152), width=3)
    d_.rectangle((0, 520, W, H), fill=(190, 150, 104)); d_.line([(0, 520), (W, 520)], fill=(240, 226, 200), width=10)
    for x in range(0, W, 200): d_.rectangle((x + 20, 560, x + 180, 700), outline=(170, 130, 88), width=4)
    # doorway
    d_.rectangle((1050, 140, 1250, 560), fill=(248, 240, 222)); d_.rectangle((1072, 162, 1228, 560), fill=(94, 66, 44))
    d_.rectangle((1072, 162, 1228, 560), outline=(120, 88, 60), width=4)
    # noticeboard
    cork = paper(700, 500, (196, 150, 98), seed=91, amp=10).convert("RGBA")
    cork.putalpha(torn_mask(700, 500, 4, seed=92))
    fr.alpha_composite(shadowed(cork, off=(6, 9), blur=8), (300 - 23, 110 - 23))
    fr.alpha_composite(card("TOWN HALL", 250, 64, bg=(250, 247, 238), size=44, seed=93), (505, 10))
    for x in (60, 1180):
        d_.polygon([(x - 40, 520), (x + 40, 520), (x + 30, 470), (x - 30, 470)], fill=(236, 236, 230))
        for k in range(6):
            a = -math.pi / 2 + (k - 2.5) * 0.4
            d_.ellipse((x + 70 * math.cos(a) - 18, 470 + 60 * math.sin(a) - 30, x + 70 * math.cos(a) + 18, 470 + 60 * math.sin(a) + 10), fill=(98, 150, 80))
    return fr
HALL = hall_bg()


def pin(d_, x, y):
    d_.ellipse((x - 9, y - 9, x + 9, y + 9), fill=RED, outline=(255, 255, 255), width=2)


def sc11(t, d):
    """MAPPING TO ASSESSMENT: MQF -> ESD -> assessment cards."""
    fr = HALL.copy()
    cards = [("MQF: COGNITIVE SKILLS", (236, 222, 190), 0.8), ("ESD: CRITICAL THINKING", (190, 228, 236), 2.2),
             ("CASE STUDY REPORT", (255, 226, 150), 3.8)]
    d_ = ImageDraw.Draw(fr)
    for i, (txt, bg, t0) in enumerate(cards):
        y = 190 + i * 150
        if i < 2:
            if t > t0 + 0.6: marker_arrow(d_, [(700, y + 45), (700, y + 105)], seg(t, t0 + 0.6, t0 + 1.1), width=6)
        if i == 2:
            u = ease_in_out(seg(t, t0, t0 + 0.9))
            if u <= 0: continue
            x, yy = lerp(330, 700, u), lerp(560, y, u) - 60 * math.sin(math.pi * u)
            place(fr, card(txt, 440, 84, bg=bg, size=38, seed=100 + i), x, yy, scale=lerp(0.4, 1, u), rot=lerp(12, -1, u))
            if u >= 1: pin(d_, 700, y - 30)
        else:
            s = pop(t, t0)
            place(fr, card(txt, 440, 84, bg=bg, size=38, seed=100 + i), 700, y, scale=s, rot=(-1.5, 1.2)[i])
            if s > 0.95: pin(d_, 700, y - 30)
    place(fr, HALL_H, 200, 790, scale=1.75)
    return zoom_frame(fr, lerp(1.0, 1.06, ease_in_out(t / d)), 0.55, 0.45)


BARS = [0.9, 0.75, 0.35, 0.2]


def rubric_img(k_lit, morph, t):
    w, h = 600, 360
    im = paper(w, h, (252, 250, 244), seed=110, amp=2).convert("RGBA")
    im.putalpha(torn_mask(w, h, 4, seed=111))
    d_ = ImageDraw.Draw(im)
    hd = 1 - morph
    if hd > 0:
        tb = font(FONT_LABEL, 44)
        d_.text((w / 2 - 70, 14), "RUBRIC", font=tb, fill=(34, 34, 38, int(255 * hd)))
    base_y, top_y = h - 50, 80
    for i in range(4):
        x0 = 40 + i * 135; x1 = x0 + 115
        lit = clamp(k_lit - i)
        col = tuple(int(lerp(g, cc, lit * (0.45 + 0.55 * i / 3))) for g, cc in zip((200, 200, 196), CYAN))
        full_top = top_y
        bar_top = base_y - BARS[i] * (base_y - top_y)
        yt = lerp(full_top, bar_top, ease_in_out(morph))
        xm = (x0 + x1) / 2; bw = lerp(115, 70, ease_in_out(morph))
        d_.rectangle((xm - bw / 2, yt, xm + bw / 2, base_y), fill=col, outline=(255, 255, 255), width=3)
        text_block(d_, (xm - 40, base_y + 6, xm + 40, base_y + 46), str(i + 1), font(FONT_MARK, 34), INK)
    if morph > 0:
        d_.line([(28, base_y), (w - 20, base_y)], fill=(34, 34, 38, int(255 * morph)), width=4)
        d_.line([(28, base_y), (28, 60)], fill=(34, 34, 38, int(255 * morph)), width=4)
    return shadowed(im, off=(5, 8), blur=7)


def sc12(t, d):
    """RUBRIC: notebook page grows into a 1-2-3-4 rubric, then into a bar chart."""
    fr = HALL.copy()
    u = ease_out(seg(t, 0.6, 1.7))
    lit = seg(t, 2.0, 4.8) * 4
    morph = ease_in_out(seg(t, 5.4, 6.6))
    x, y = lerp(330, 680, u), lerp(560, 360, u)
    if u > 0:
        s = lerp(0.12, 1, u) * lerp(1, 0.85, morph)
        place(fr, rubric_img(lit, morph, t), x + 60 * morph, y, scale=s, rot=lerp(10, 0, u))
    place(fr, HALL_H, 200, 790, scale=1.75)
    return fr


def sc13(t, d):
    """CQI: PLAN -> DO -> CHECK -> ACT; low results circled; lecturer steps out."""
    fr = HALL.copy()
    d_ = ImageDraw.Draw(fr)
    cx, cy, R = 560, 350, 160
    pos = {"PLAN": (cx, cy - R), "DO": (cx + R + 20, cy), "CHECK": (cx, cy + R), "ACT": (cx - R - 20, cy)}
    names = list(pos)
    for i in range(4):
        a, b = pos[names[i]], pos[names[(i + 1) % 4]]
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        p0 = (a[0] + 70 * math.cos(ang), a[1] + 50 * math.sin(ang))
        p1 = (b[0] - 70 * math.cos(ang), b[1] - 50 * math.sin(ang))
        marker_arrow(d_, curve(p0, p1, -0.25), seg(t, 0.3 + 0.2 * i, 0.8 + 0.2 * i), width=5)
    cols = {"PLAN": (255, 226, 90), "DO": (255, 180, 120), "CHECK": (150, 220, 236), "ACT": (170, 222, 140)}
    for i, n in enumerate(names):
        act = seg(t, 0.8 + 0.8 * i, 1.2 + 0.8 * i)
        hl = n == "ACT" and t > 4.3
        s = 1 + 0.12 * math.sin(math.pi * act) + (0.12 * ease_out(seg(t, 4.3, 4.8)) if hl else 0)
        bg = tuple(int(lerp(236, c, act)) for c in cols[n])
        if hl:
            g = Image.new("RGBA", (220, 150), (0, 0, 0, 0))
            ImageDraw.Draw(g).rounded_rectangle((0, 0, 219, 149), 30, fill=(255, 240, 120, 150))
            place(fr, g.filter(ImageFilter.GaussianBlur(10)), *pos[n], scale=s)
        place(fr, card(n, 150, 90, bg=bg, size=40, seed=120 + i, jag=2), *pos[n], scale=s, rot=(-2, 2, -1, 3)[i])
    place(fr, rubric_img(4, 1, t), 845, 520, scale=0.42)
    rd = ImageDraw.Draw(fr)
    marker_circle(rd, (752, 455, 870, 600), seg(t, 3.2, 3.9), width=6)
    s = pop(t, 4.8)
    if s > 0:
        cardim = Image.new("RGBA", (190, 120), (0, 0, 0, 0))
        place(cardim, icon("book", 110), 55, 60); place(cardim, icon("magnifier", 90), 140, 62)
        bgc = card(" ", 210, 140, bg=(255, 255, 255), seed=130)
        place(fr, bgc, 190, cy, scale=s, rot=-3)
        place(fr, cardim, 190, cy, scale=s, rot=-3)
    u = ease_out(seg(t, 5.8, 8.2))
    if u > 0:
        x = lerp(1160, 1080, u)
        place(fr, LECT, x, 800 - walk_bob(t, u < 1) * 0.6, scale=1.6, alpha=clamp(u * 2.5))
    return zoom_frame(fr, lerp(1.0, 0.98 + 0.0, 0), 0.5, 0.5)


def plate_frame(t, hakim_key=None, hk_t0=0.0, lect_key=None, lt_t0=0.0, nod=0.0, hand=0.0, z=1.0, fx=0.5, fy=0.5,
                overlay=None):
    arr = PLATE
    if hand: arr = warp_shift(arr, *LECT_HAND, 110, 0, -12 * hand)
    if nod: arr = warp_shift(arr, *LECT_HEAD, 95, 0, 7 * nod)
    if hakim_key: arr = warp_jaw(arr, *HAKIM_MOUTH, 16 * PK, mouth(hakim_key, t - hk_t0), maxd=0.45)
    if lect_key: arr = warp_jaw(arr, LECT_MOUTH[0], LECT_MOUTH[1] + nod * 5, 24 * PK, mouth(lect_key, t - lt_t0), maxd=0.3)
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    if overlay: overlay(im)
    pw, ph = im.size
    w, h = pw / z, ph / z
    x0, y0 = (pw - w) * fx, (ph - h) * fy
    return im.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + w, y0 + h))


def sc14(t, d):
    """CONCLUSION: Hakim speaks on screen (lip-sync), the lecturer nods."""
    nod = math.sin(math.pi * seg(t, d - 2.4, d - 1.4))
    return plate_frame(t, "s14", 0.8, nod=nod, z=lerp(1.1, 1.16, ease_in_out(t / d)), fx=0.45, fy=0.12)


CARDS15 = ["FACILITATOR", "REAL ISSUES", "ALIGNED\nASSESSMENT", "ROLE MODEL"]


def sc15(t, d):
    """THE LECTURER'S ROLE: question, four cards to the pillar, answer, pull back to the living town."""
    T_A, T_B = 0.6, 4.9
    def ov(im):
        pu = ease_out(seg(t, 1.9, 2.4))
        if pu > 0:
            pw, ph = 170, 440
            pil = paper(pw, ph, (238, 230, 214), seed=140, amp=6).convert("RGBA")
            pil.putalpha(Image.eval(torn_mask(pw, ph, 8, seed=141), lambda v: int(v * pu)))
            place(im, shadowed(pil, off=(4, 6), blur=6, opacity=0.25), 570, 392)
        for i, txt in enumerate(CARDS15):
            t0 = 2.3 + 0.55 * i
            u = ease_out(seg(t, t0, t0 + 0.6))
            if u <= 0: continue
            tx, ty = 570, 222 + i * 110
            x = lerp(NOTEBOOK[0], tx, u); y = lerp(NOTEBOOK[1], ty, u) - 140 * math.sin(math.pi * u)
            place(im, card(txt, 224, 92, bg=(236, 222, 190), size=32 if "\n" not in txt else 28, seed=150 + i),
                  x, y, scale=lerp(0.3, 1, u), rot=lerp(25, (-2, 2, -1, 1.5)[i], u))
    hand = ease_in_out(seg(t, 0.2, 0.9)) - ease_in_out(seg(t, 2.6, 3.4))
    z = lerp(1.1, 1.14, ease_in_out(seg(t, 0, 10)))
    main = plate_frame(t, "s15b", T_B, "s15a", T_A, hand=hand, z=z, fx=0.45, fy=0.12, overlay=ov)
    pb = ease_in_out(seg(t, 10.4, 12.8))
    if pb <= 0: return main
    bg = living_view(lerp(900, 780, pb), lerp(470, 398, pb), lerp(360, 515, pb))
    ph = photo(main.convert("RGB"), 1100, seed=160)
    gone = ease_in_out(seg(t, 12.4, 13.4))
    place(bg, ph, lerp(640, 330, pb) - 500 * gone, lerp(360, 250, pb) - 200 * gone, scale=lerp(1.12, 0.42, pb),
          rot=lerp(0, -4, pb), alpha=1 - gone)
    m = ease_out(seg(t, 13.2, 14.0))
    if m > 0:
        place(bg, card("ESD is not an extra topic;\nit changes how learning leads to responsible action.", 900, 128,
                       bg=(255, 255, 255), size=38, seed=170), 640, 610, scale=lerp(0.85, 1, m), alpha=m)
    fo = seg(t, d - 1.0, d)
    if fo > 0:
        bg = Image.blend(bg, Image.new("RGBA", (W, H), (250, 248, 242, 255)), fo)
    return bg


# ================================================================ timeline
def dur_for(key, start=0.8, tail=1.6, minimum=8.0): return max(minimum, start + META[key]["dur"] + tail)

SCENES = [
    # (fn, duration, [(vo_key, start)], [(sfx, t)], caption title)
    (sc_title, 3.6, [], [("pop", 0.25), ("pop", 0.85), ("pop", 1.3), ("pop", 1.6), ("pop", 1.9)]),
    (sc01, dur_for("s01", 0.7, 1.5), [("s01", 0.7)], [("paper", 0.6), ("pop", 2.3), ("pop", 3.1), ("pop", 3.9)]),
    (sc02, 8.0, [("s02", 0.8)], [("pop", 0.6), ("marker", 1.3), ("marker", 2.0), ("marker", 3.2), ("marker", 4.4), ("chime", 5.3)]),
    (sc03, 8.2, [("s03", 0.8)], [("paper", 1.8), ("marker", 3.1), ("pop", 4.1), ("chime", 5.0)]),
    (sc04, 8.0, [("s04", 0.8)], [("paper", 0.5), ("paper", 1.0), ("chime", 4.9)]),
    (sc05, 8.0, [("s05", 0.8)], [("paper", 1.6), ("pop", 2.7), ("chime", 5.0)]),
    (sc06, 8.4, [("s06", 0.8)], [("paper", 0.0), ("paper", 0.9), ("paper", 1.8), ("paper", 2.7), ("paper", 3.6), ("paper", 4.4), ("paper", 5.1), ("chime", 6.2)]),
    (sc07, 8.0, [("s07", 0.8)], [("pop", 1.0), ("pop", 1.8), ("pop", 2.6), ("marker", 3.2), ("chime", 5.0)]),
    (sc08, 8.0, [("s08", 0.8)], [("water", 0.0), ("chime", 4.6)]),
    (sc09, 8.4, [("s09", 0.8)], [("paper", 0.6), ("paper", 1.6), ("chime", 4.6), ("sparkle", 4.6)]),
    (sc10, 8.6, [("s10", 4.0)], [("water", 0.0), ("sparkle", 0.6)]),
    (sc11, dur_for("s11", 0.8, 1.4), [("s11", 0.8)], [("pop", 0.8), ("marker", 1.4), ("pop", 2.2), ("marker", 2.8), ("paper", 3.8), ("pop", 4.7)]),
    (sc12, dur_for("s12", 0.8, 1.6), [("s12", 0.8)], [("paper", 0.6), ("pop", 2.0), ("pop", 2.7), ("pop", 3.4), ("pop", 4.1), ("paper", 5.4)]),
    (sc13, dur_for("s13", 0.8, 1.8), [("s13", 0.8)], [("pop", 0.8), ("pop", 1.6), ("pop", 2.4), ("pop", 3.2), ("marker", 3.2), ("chime", 4.3), ("pop", 4.8)]),
    (sc14, dur_for("s14", 0.8, 1.8), [("s14", 0.8)], []),
    (sc15, 17.5, [("s15a", 0.6), ("s15b", 4.9)], [("paper", 2.3), ("pop", 2.9), ("pop", 3.45), ("pop", 4.0), ("pop", 4.55), ("paper", 10.4), ("water", 10.4), ("chime", 13.2)]),
]
STARTS = []
_t = 0.0
for s in SCENES:
    STARTS.append(_t); _t += s[1] - XF
TOTAL = STARTS[-1] + SCENES[-1][1]


def render_at(T):
    active = [(i, T - STARTS[i]) for i in range(len(SCENES)) if STARTS[i] <= T < STARTS[i] + SCENES[i][1]]
    if not active: active = [(len(SCENES) - 1, SCENES[-1][1] - 1e-3)]
    frames = []
    for i, lt in active[-2:]:
        frames.append((i, lt, SCENES[i][0](lt, SCENES[i][1])))
    if len(frames) == 1: out = frames[0][2]
    else:
        (i0, _, f0), (i1, lt1, f1) = frames
        out = Image.blend(f0.convert("RGBA"), f1.convert("RGBA"), ease(lt1 / XF))
    out = out.convert("RGBA"); out.alpha_composite(BORDER)
    return out.convert("RGB")


def _frame_bytes(f):
    return render_at(f / FPS).tobytes()


# ================================================================ audio
SR = 44100


def load_vo(key):
    sr, x = wavfile.read(f"{AUD}/{key}_raw.wav")
    x = x.astype(np.float32); x /= np.abs(x).max() + 1e-9
    x = resample_poly(x, SR, sr).astype(np.float32)
    # gentle room: short decaying noise convolution to soften the synthetic voice
    rng = np.random.default_rng(1)
    ir = rng.normal(0, 1, int(SR * 0.18)) * np.exp(-np.arange(int(SR * 0.18)) / (SR * 0.04))
    wet = np.convolve(x, ir)[:len(x)]; wet /= np.abs(wet).max() + 1e-9
    y = x * 0.9 + wet * 0.12
    return y / (np.abs(y).max() + 1e-9) * 0.92


def sfx(kind):
    rng = np.random.default_rng(abs(hash(kind)) % 999)
    t = lambda s: np.arange(int(SR * s)) / SR
    if kind == "pop":
        tt = t(0.12); f = 900 * np.exp(-tt * 25) + 300
        return 0.35 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 40)
    if kind == "paper":
        tt = t(0.4); n = rng.uniform(-1, 1, len(tt))
        n = np.convolve(n, np.ones(6) / 6, "same") - np.convolve(n, np.ones(40) / 40, "same")
        env = np.sin(np.pi * tt / 0.4) ** 2 * (0.6 + 0.4 * np.abs(np.sin(tt * 60)))
        return 0.45 * n * env
    if kind == "marker":
        tt = t(0.5); n = rng.uniform(-1, 1, len(tt))
        n = n - np.convolve(n, np.ones(3) / 3, "same")
        return 0.12 * n * (0.5 + 0.5 * np.sin(tt * 40) ** 2) * np.minimum(1, (0.5 - tt) * 10)
    if kind in ("chime", "sparkle"):
        out = np.zeros(int(SR * 1.8))
        notes = (72, 76, 79, 84) if kind == "chime" else (88, 91, 96, 100)
        for k, n in enumerate(notes):
            f = 440 * 2 ** ((n - 69) / 12); tt = t(1.8 - k * 0.08)
            s = np.sin(2 * np.pi * f * tt) * np.exp(-tt * 4) + 0.3 * np.sin(2 * np.pi * f * 2.76 * tt) * np.exp(-tt * 8)
            i = int(k * 0.08 * SR); out[i:i + len(s)] += s[:len(out) - i]
        return 0.16 * out
    if kind == "water":
        tt = t(8.0); n = rng.normal(0, 1, len(tt))
        lp = np.convolve(n, np.ones(30) / 30, "same")
        bub = np.zeros_like(tt)
        for _ in range(40):
            i = rng.integers(0, len(tt) - 3000); f = rng.uniform(500, 1400); b = t(0.05)
            bub[i:i + len(b)] += np.sin(2 * np.pi * f * (1 + 3 * b) * b) * np.exp(-b * 60)
        env = np.minimum(1, tt / 1.0) * np.minimum(1, (8 - tt) / 1.5)
        return (0.5 * lp + 0.05 * bub) * env * 0.5
    return np.zeros(10)


def build_audio(path):
    n = int(SR * TOTAL) + SR
    vo = np.zeros(n, np.float32); fx = np.zeros(n, np.float32)
    subs = []
    for i, (fn, d, vos, sfxs) in enumerate(SCENES):
        for key, st in vos:
            x = load_vo(key); a = int((STARTS[i] + st) * SR)
            vo[a:a + len(x)] += x[:n - a]
            subs.append((STARTS[i] + st, STARTS[i] + st + META[key]["dur"], META[key]["caption"]))
        for kind, st in sfxs:
            x = sfx(kind).astype(np.float32); a = int((STARTS[i] + st) * SR)
            fx[a:a + len(x)] += x[:n - a]
    mp = f"{BUILD}/music.wav"
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "music.py"), str(TOTAL), mp], check=True)
    sr, mus = wavfile.read(mp); mus = mus.astype(np.float32)
    mus = np.pad(mus, ((0, max(0, n - len(mus))), (0, 0)))[:n]
    act = np.abs(vo) > 0.02
    k = int(SR * 0.25)
    act = np.convolve(act.astype(np.float32), np.ones(k) / k, "same")
    duck = 1 - 0.62 * np.clip(act * 3, 0, 1)
    mix = mus * (0.55 * duck)[:, None] + (vo * 0.95)[:, None] + (fx * 0.8)[:, None]
    mix /= max(1.0, np.abs(mix).max() / 0.97)
    wavfile.write(path, SR, mix.astype(np.float32))
    return subs


def srt(subs, path):
    def ts(s):
        ms = int(round(s * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s_, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s_:02d},{ms:03d}"
    with open(path, "w") as f:
        for i, (a, b, txt) in enumerate(subs, 1):
            f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{txt}\n\n")


def main():
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    os.makedirs(BUILD, exist_ok=True)
    Wd.pano()
    wav = f"{BUILD}/mix.wav"
    subs = build_audio(wav)
    srt(subs, f"{BUILD}/esd_video.srt")
    nf = int(TOTAL * FPS)
    print(f"total {TOTAL:.1f}s, {nf} frames", flush=True)
    out = f"{BUILD}/esd_video.mp4"
    p = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out],
                         stdin=subprocess.PIPE)
    with Pool(4) as pool:
        for i, b in enumerate(pool.imap(_frame_bytes, range(nf), chunksize=4)):
            p.stdin.write(b)
            if i % 250 == 0: print(f"frame {i}/{nf}", flush=True)
    p.stdin.close(); p.wait()
    print("done", out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--still":
        s, lt = int(sys.argv[2]), float(sys.argv[3])
        T = STARTS[s] + lt
        render_at(T).save(sys.argv[4] if len(sys.argv) > 4 else f"{BUILD}/still.png")
    elif len(sys.argv) > 1 and sys.argv[1] == "--sheet":
        # contact sheet: several stills per scene
        Wd.pano()
        ims = []
        for s in range(len(SCENES)):
            d = SCENES[s][1]
            for lt in (0.35 * d, 0.7 * d, 0.95 * d):
                ims.append(render_at(STARTS[s] + lt).resize((320, 180)))
        cols = 6; rows = (len(ims) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 320, rows * 180), "white")
        for k, im in enumerate(ims): sheet.paste(im, ((k % cols) * 320, (k // cols) * 180))
        sheet.save(sys.argv[2])
    else:
        main()
