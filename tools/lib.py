"""Shared drawing helpers for the paper-craft ESD animation."""
import math, random, functools
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops
from scipy.ndimage import gaussian_filter, map_coordinates

W, H, FPS = 1280, 720, 25
A = "/home/user/esd/assets/"
FONT_LABEL = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf"
FONT_MARK = "/usr/share/fonts/opentype/comic-neue/ComicNeue-Bold.otf"

CREAM = (246, 239, 224)
CYAN = (58, 196, 216)
MUSTARD = (226, 172, 52)
ORANGE = (238, 128, 56)
TEAL = (38, 160, 160)
GREEN = (98, 178, 88)
INK = (34, 34, 38)
RED = (214, 48, 44)


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def lerp(a, b, t): return a + (b - a) * t
def ease(t): t = clamp(t); return t * t * (3 - 2 * t)
def ease_out(t): t = clamp(t); return 1 - (1 - t) ** 3
def ease_in_out(t): t = clamp(t); return 4 * t ** 3 if t < .5 else 1 - (-2 * t + 2) ** 3 / 2
def back_out(t, s=1.7):
    t = clamp(t) - 1; return t * t * ((s + 1) * t + s) + 1
def seg(t, a, b): return clamp((t - a) / (b - a)) if b > a else float(t >= a)


@functools.lru_cache(None)
def font(path, size): return ImageFont.truetype(path, size)


# ---------------------------------------------------------------- textures
def paper_noise(w, h, seed=0, amp=1.0):
    r = np.random.default_rng(seed)
    n = gaussian_filter(r.normal(0, 1, (h, w)), 1.6) * 3.0
    f = gaussian_filter(r.normal(0, 1, (h, w)), (0.6, 4)) * 2.0
    return (n + f) * amp


def paper(w, h, color, seed=0, amp=5.0):
    n = paper_noise(w, h, seed)
    arr = np.clip(np.array(color, np.float32)[None, None, :] + amp * n[..., None], 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def torn_mask(w, h, jag=5, seed=0, step=7, edges="tblr"):
    r = random.Random(seed)
    j = lambda e: r.uniform(0, jag) if e in edges else 0
    pts = [(x, j("t")) for x in range(0, w, step)]
    pts += [(w - 1 - j("r"), y) for y in range(0, h, step)]
    pts += [(x, h - 1 - j("b")) for x in range(w - 1, 0, -step)]
    pts += [(j("l"), y) for y in range(h - 1, 0, -step)]
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


def shadowed(img, off=(5, 7), blur=7, opacity=0.35):
    pad = blur * 2 + max(abs(off[0]), abs(off[1]))
    w, h = img.size
    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    a = img.getchannel("A").point(lambda v: int(v * opacity))
    sh = Image.new("RGBA", img.size, (40, 30, 20, 0)); sh.putalpha(a)
    tmp = Image.new("RGBA", out.size, (0, 0, 0, 0))
    tmp.paste(sh, (pad + off[0], pad + off[1]))
    tmp = tmp.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(tmp)
    out.alpha_composite(img, (pad, pad))
    return out


def sticker(img, border=6, shadow=True):
    """White die-cut border + drop shadow, like the storyboard cut-outs."""
    b = border
    w, h = img.size
    big = Image.new("RGBA", (w + 2 * b, h + 2 * b), (0, 0, 0, 0))
    big.paste(img, (b, b))
    a = big.getchannel("A").point(lambda v: 255 if v > 60 else 0)
    a = a.filter(ImageFilter.MaxFilter(2 * b + 1)).filter(ImageFilter.GaussianBlur(0.8))
    white = Image.new("RGBA", big.size, (255, 255, 255, 0)); white.putalpha(a)
    white.alpha_composite(big)
    return shadowed(white) if shadow else white


def text_block(draw, box, text, fnt, fill, spacing=4):
    x0, y0, x1, y1 = box
    lines = text.split("\n")
    sizes = [draw.textbbox((0, 0), l, font=fnt) for l in lines]
    th = sum(s[3] - s[1] for s in sizes) + spacing * (len(lines) - 1)
    y = (y0 + y1 - th) / 2
    for l, s in zip(lines, sizes):
        tw = s[2] - s[0]
        draw.text(((x0 + x1 - tw) / 2 - s[0], y - s[1]), l, font=fnt, fill=fill)
        y += s[3] - s[1] + spacing


@functools.lru_cache(None)
def card(text, w, h, bg=(236, 222, 190), fg=INK, size=30, fontpath=FONT_LABEL, seed=1, jag=4,
         shadow=True, border=0):
    base = paper(w, h, bg, seed=seed, amp=4).convert("RGBA")
    base.putalpha(torn_mask(w, h, jag=jag, seed=seed))
    d = ImageDraw.Draw(base)
    if border:
        d.rectangle((6, 6, w - 7, h - 7), outline=(fg[0], fg[1], fg[2], 90), width=border)
    text_block(d, (8, 4, w - 8, h - 4), text, font(fontpath, size), fg)
    return shadowed(base, off=(3, 5), blur=5, opacity=0.35) if shadow else base


@functools.lru_cache(None)
def flag(text, size=22, pole=150, color=(255, 255, 255), fg=INK, big=False):
    fnt = font(FONT_MARK, size)
    tb = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=fnt)
    fw, fh = tb[2] - tb[0] + (40 if big else 26), tb[3] - tb[1] + (28 if big else 18)
    w, h = fw + 16, pole + 10
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 4, 9, h - 1), 3, fill=(150, 108, 70, 255))
    cloth = paper(fw, fh, color, seed=len(text), amp=3).convert("RGBA")
    m = torn_mask(fw, fh, jag=3, seed=len(text))
    # pennant notch on the right edge
    md = ImageDraw.Draw(m)
    md.polygon([(fw, 0), (fw - 14, fh / 2), (fw, fh)], fill=0)
    cloth.putalpha(m)
    cd = ImageDraw.Draw(cloth)
    cd.text(((fw - 14 - (tb[2] - tb[0])) / 2 - tb[0] + 4, (fh - (tb[3] - tb[1])) / 2 - tb[1]), text, font=fnt, fill=fg)
    img.alpha_composite(cloth, (9, 4))
    out = shadowed(img, off=(3, 4), blur=4, opacity=0.3)
    pad = (out.width - w) // 2
    out.anchor = ((pad + 5) / out.width, (pad + h) / out.height)   # foot of the pole
    return out


# ---------------------------------------------------------------- compositing
def transform(img, scale=1.0, rot=0.0, alpha=1.0, flip=False, sx=None, sy=None):
    if flip: img = img.transpose(Image.FLIP_LEFT_RIGHT)
    sx = scale if sx is None else sx * scale
    sy = scale if sy is None else sy * scale
    if abs(sx - 1) > 1e-3 or abs(sy - 1) > 1e-3:
        img = img.resize((max(1, int(img.width * abs(sx))), max(1, int(img.height * abs(sy)))), Image.BICUBIC)
    if abs(rot) > 0.05:
        img = img.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 0.999:
        a = img.getchannel("A").point(lambda v: int(v * clamp(alpha)))
        img = img.copy(); img.putalpha(a)
    return img


def paste(frame, img, x, y):
    """alpha_composite with clipping; (x, y) = top-left, may be negative."""
    x, y = int(round(x)), int(round(y))
    l, t = max(0, x), max(0, y)
    r, b = min(frame.width, x + img.width), min(frame.height, y + img.height)
    if r <= l or b <= t: return
    frame.alpha_composite(img.crop((l - x, t - y, r - x, b - y)), (l, t))


def place(frame, img, x, y, anchor=None, scale=1.0, rot=0.0, alpha=1.0, flip=False, sx=None, sy=None):
    if alpha <= 0.003 or scale <= 0.003: return
    anchor = anchor or getattr(img, "anchor", (0.5, 0.5))
    t = transform(img, scale, 0, alpha, flip, sx, sy)
    ax, ay = anchor[0] * t.width, anchor[1] * t.height
    if abs(rot) > 0.05:
        cx, cy = t.width / 2, t.height / 2
        r = t.rotate(rot, resample=Image.BICUBIC, expand=True)
        a = math.radians(rot)
        dx, dy = ax - cx, ay - cy
        rx, ry = dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)
        ax, ay = r.width / 2 + rx, r.height / 2 + ry
        t = r
    paste(frame, t, x - ax, y - ay)


def pop(t, t0, dur=0.45):
    """scale for a springy 'pop in' starting at t0."""
    return 0.0 if t < t0 else back_out(seg(t, t0, t0 + dur))


# ---------------------------------------------------------------- marker drawing
def polyline_partial(pts, frac):
    if frac <= 0: return []
    L = [0.0]
    for a, b in zip(pts, pts[1:]): L.append(L[-1] + math.dist(a, b))
    target = L[-1] * clamp(frac)
    out = [pts[0]]
    for i in range(1, len(pts)):
        if L[i] <= target: out.append(pts[i])
        else:
            u = (target - L[i - 1]) / (L[i] - L[i - 1] + 1e-9)
            out.append((lerp(pts[i - 1][0], pts[i][0], u), lerp(pts[i - 1][1], pts[i][1], u)))
            break
    return out


def curve(p0, p1, bend=0.25, n=24):
    (x0, y0), (x1, y1) = p0, p1
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    nx, ny = -(y1 - y0) * bend, (x1 - x0) * bend
    cx, cy = mx + nx, my + ny
    return [((1 - u) ** 2 * x0 + 2 * (1 - u) * u * cx + u * u * x1,
             (1 - u) ** 2 * y0 + 2 * (1 - u) * u * cy + u * u * y1) for u in np.linspace(0, 1, n)]


def marker_arrow(draw, pts, frac, color=INK, width=6, head=16, dashed=False):
    p = polyline_partial(pts, frac)
    if len(p) < 2: return
    if dashed:
        dist = 0.0
        for a, b in zip(p, p[1:]):
            seglen = math.dist(a, b); k = 0.0
            while k < seglen:
                on = (dist + k) % 26 < 14
                u0, u1 = k / seglen, min(seglen, k + 4) / seglen
                if on:
                    draw.line([(lerp(a[0], b[0], u0), lerp(a[1], b[1], u0)), (lerp(a[0], b[0], u1), lerp(a[1], b[1], u1))], fill=color, width=width)
                k += 4
            dist += seglen
    else:
        draw.line(p, fill=color, width=width, joint="curve")
        for q in (p[0], p[-1]):
            draw.ellipse((q[0] - width / 2, q[1] - width / 2, q[0] + width / 2, q[1] + width / 2), fill=color)
    if frac >= 0.999 or True:
        (xa, ya), (xb, yb) = p[-2], p[-1]
        ang = math.atan2(yb - ya, xb - xa)
        for s in (-1, 1):
            a = ang + math.pi + s * 0.5
            draw.line([(xb, yb), (xb + head * math.cos(a), yb + head * math.sin(a))], fill=color, width=width)


def marker_circle(draw, box, frac, color=RED, width=7, seed=3):
    x0, y0, x1, y1 = box
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    r = random.Random(seed)
    wob = [r.uniform(-0.05, 0.05) for _ in range(6)]
    n = int(80 * clamp(frac) * 1.12) + 1
    pts = []
    for i in range(n):
        a = -math.pi / 2 + 2 * math.pi * 1.12 * i / 80
        k = 1 + wob[i % 6] * math.sin(a * 2) + 0.06 * i / 80
        pts.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a)))
    if len(pts) > 1: draw.line(pts, fill=color, width=width, joint="curve")


# ---------------------------------------------------------------- paper icons
def _canvas(s): im = Image.new("RGBA", (s * 2, s * 2), (0, 0, 0, 0)); return im, ImageDraw.Draw(im)
def _done(im, s, border=6): return sticker(im.resize((s, s), Image.LANCZOS), border=border)


@functools.lru_cache(None)
def icon(name, s=150, grey=False):
    im, d = _canvas(s); S = 2 * s
    g = (lambda c: tuple(int(0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]) for _ in range(3))) if grey else (lambda c: c)
    if name == "leaf":
        d.ellipse((S*.18, S*.12, S*.82, S*.88), fill=g(GREEN))
        d.polygon([(S*.5, S*.05), (S*.62, S*.2), (S*.38, S*.2)], fill=g(GREEN))
        d.line([(S*.5, S*.95), (S*.5, S*.18)], fill=g((60, 120, 50)), width=int(S*.04))
        for k in range(3):
            y = S*(.35 + k*.15); d.line([(S*.5, y+S*.08), (S*.32, y)], fill=g((60, 120, 50)), width=int(S*.025))
            d.line([(S*.5, y+S*.08), (S*.68, y)], fill=g((60, 120, 50)), width=int(S*.025))
    elif name == "coin":
        d.ellipse((S*.1, S*.1, S*.9, S*.9), fill=g((230, 170, 40)))
        d.ellipse((S*.2, S*.2, S*.8, S*.8), fill=g((248, 200, 70)))
        text_block(d, (0, 0, S, S), "RM", font(FONT_LABEL, int(S*.28)), g((170, 110, 20)))
    elif name == "people":
        for cx, col, k in ((.3, ORANGE, .85), (.7, TEAL, .85), (.5, MUSTARD, 1.0)):
            r = S*.1*k
            d.ellipse((S*cx-r, S*(.32 if k == 1 else .38)-r, S*cx+r, S*(.32 if k == 1 else .38)+r), fill=g((236, 190, 150)))
            top = S*(.46 if k == 1 else .52)
            d.rounded_rectangle((S*cx-S*.14*k, top, S*cx+S*.14*k, S*.9), int(S*.08), fill=g(col))
    elif name == "factory":
        d.rectangle((S*.08, S*.5, S*.92, S*.9), fill=g((150, 150, 150)))
        d.polygon([(S*.08, S*.5), (S*.3, S*.35), (S*.3, S*.5), (S*.52, S*.35), (S*.52, S*.5)], fill=g((130, 130, 130)))
        d.rectangle((S*.62, S*.15, S*.74, S*.5), fill=g((120, 110, 110)))
        d.rectangle((S*.78, S*.25, S*.88, S*.5), fill=g((120, 110, 110)))
        for k in range(3):
            d.rectangle((S*(.15+k*.2), S*.62, S*(.25+k*.2), S*.74), fill=g((250, 220, 120)))
        d.ellipse((S*.58, S*.0, S*.8, S*.16), fill=(200, 200, 200))
    elif name == "fish":
        d.ellipse((S*.1, S*.3, S*.7, S*.7), fill=g(ORANGE))
        d.polygon([(S*.65, S*.5), (S*.92, S*.28), (S*.92, S*.72)], fill=g((220, 100, 40)))
        d.ellipse((S*.2, S*.42, S*.28, S*.5), fill=INK)
    elif name == "market":
        d.rectangle((S*.15, S*.45, S*.85, S*.9), fill=g((222, 196, 150)))
        for k in range(6):
            d.polygon([(S*(.08+k*.14), S*.28), (S*(.22+k*.14), S*.28), (S*(.22+k*.14), S*.45), (S*(.08+k*.14), S*.45)],
                      fill=g(RED if k % 2 else (250, 245, 235)))
        d.rectangle((S*.15, S*.58, S*.85, S*.66), fill=g((180, 130, 80)))
        for k in range(4): d.ellipse((S*(.2+k*.16), S*.5, S*(.3+k*.16), S*.58), fill=g((GREEN, ORANGE, MUSTARD, RED)[k]))
    elif name == "houses":
        for x0, col, h0 in ((.05, TEAL, .45), (.38, MUSTARD, .35), (.66, ORANGE, .5)):
            d.rectangle((S*x0, S*h0+S*.15, S*(x0+.28), S*.9), fill=g(col))
            d.polygon([(S*(x0-.03), S*h0+S*.16), (S*(x0+.14), S*h0), (S*(x0+.31), S*h0+S*.16)], fill=g((200, 80, 60)))
            d.rectangle((S*(x0+.1), S*.7, S*(x0+.18), S*.9), fill=g((120, 80, 50)))
    elif name == "river":
        d.rounded_rectangle((S*.06, S*.25, S*.94, S*.75), int(S*.2), fill=g(CYAN))
        for k in range(3):
            y = S*(.38 + k*.12)
            d.arc((S*.15, y-S*.06, S*.45, y+S*.06), 200, 340, fill=(230, 250, 255), width=int(S*.025))
            d.arc((S*.5, y-S*.06, S*.8, y+S*.06), 200, 340, fill=(230, 250, 255), width=int(S*.025))
    elif name == "book":
        d.polygon([(S*.08, S*.25), (S*.5, S*.32), (S*.5, S*.85), (S*.08, S*.78)], fill=(250, 245, 230))
        d.polygon([(S*.92, S*.25), (S*.5, S*.32), (S*.5, S*.85), (S*.92, S*.78)], fill=(240, 232, 214))
        d.line([(S*.08, S*.78), (S*.5, S*.85), (S*.92, S*.78)], fill=ORANGE, width=int(S*.05))
        for k in range(4):
            y = S*(.4+k*.09); d.line([(S*.15, y), (S*.43, y+S*.04)], fill=(150, 150, 150), width=4)
            d.line([(S*.57, y+S*.04), (S*.85, y)], fill=(150, 150, 150), width=4)
    elif name == "magnifier":
        d.line([(S*.58, S*.58), (S*.88, S*.88)], fill=(120, 80, 50), width=int(S*.1))
        d.ellipse((S*.1, S*.1, S*.66, S*.66), fill=(200, 240, 250), outline=(60, 60, 70), width=int(S*.06))
    elif name == "recycle":
        d.polygon([(S*.1, S*.35), (S*.9, S*.35), (S*.84, S*.92), (S*.16, S*.92)], fill=(196, 160, 110))
        d.polygon([(S*.1, S*.35), (S*.3, S*.18), (S*.7, S*.18), (S*.9, S*.35)], fill=(214, 182, 132))
        text_block(d, (0, S*.35, S, S*.92), "♻", font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", int(S*.35)), (40, 110, 60))
    elif name == "bottle":
        d.rounded_rectangle((S*.35, S*.25, S*.65, S*.92), int(S*.08), fill=(215, 225, 230))
        d.rectangle((S*.43, S*.1, S*.57, S*.25), fill=(90, 150, 210))
    elif name == "tbottle":
        d.rounded_rectangle((S*.33, S*.22, S*.67, S*.92), int(S*.12), fill=(70, 200, 190))
        d.rounded_rectangle((S*.4, S*.08, S*.6, S*.24), int(S*.04), fill=(40, 150, 140))
    return _done(im, s)


# ---------------------------------------------------------------- warping (lip-sync)
def warp_jaw(arr, cx, cy, mw, openness, maxd=0.3, interior=(70, 22, 26)):
    """Drop the lower lip/jaw of a face in an HxWx3 float array (in-place on a copy of the patch)."""
    if openness <= 0.02: return arr
    x0, x1 = int(cx - mw * 1.6), int(cx + mw * 1.6)
    y0, y1 = int(cy - mw * 0.2), int(cy + mw * 2.0)
    patch = arr[y0:y1, x0:x1]
    hh, ww = patch.shape[:2]
    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
    X, Y = xx + x0, yy + y0
    gx = np.exp(-((X - cx) / (mw * 0.5)) ** 2)
    line = cy - 0.16 * mw * ((X - cx) / (mw * 0.6)) ** 2          # smile-shaped lip line
    below = np.clip((Y - line) / (mw * 0.12), 0, 1)
    fall = np.clip(1 - (Y - (cy + mw * 0.9)) / (mw * 1.0), 0, 1)
    d = openness * maxd * mw * gx * below * fall
    srcy = Y - d
    out = np.empty_like(patch)
    for c in range(3):
        out[..., c] = map_coordinates(arr[..., c], [srcy, X], order=1, mode="nearest")
    # mouth cavity where the source would come from above the lip line
    gap = np.clip((line + 0.5 - srcy) / 1.5, 0, 1) * (Y > line)
    depth = np.clip((Y - line) / (d + 1e-3), 0, 1)
    cav = np.array(interior, np.float32)[None, None, :] * (0.6 + 0.6 * depth[..., None])
    tw = np.clip(1 - (Y - line) / (d * 0.3 + 1e-3), 0, 1) * np.clip((gx - 0.45) * 3, 0, 1) * 0.75
    cav = cav * (1 - tw[..., None]) + np.array((198, 186, 178), np.float32) * tw[..., None]
    g = gaussian_filter(gap, 0.9)[..., None]
    out = out * (1 - g) + cav * g
    arr = arr.copy()
    arr[y0:y1, x0:x1] = out
    return arr


def warp_shift(arr, cx, cy, r, dx, dy):
    """Smoothly displace a round region (e.g. a head nod)."""
    if abs(dx) < 0.05 and abs(dy) < 0.05: return arr
    x0, x1, y0, y1 = int(cx - r * 1.5), int(cx + r * 1.5), int(cy - r * 1.5), int(cy + r * 1.5)
    x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(arr.shape[1], x1), min(arr.shape[0], y1)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    g = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (r * r)))
    out = arr.copy()
    for c in range(3):
        out[y0:y1, x0:x1, c] = map_coordinates(arr[..., c], [yy - dy * g, xx - dx * g], order=1, mode="nearest")
    return out
