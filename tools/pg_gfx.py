"""Flat motion-graphics helpers for "Selepas Pinggan Ditinggalkan" (clean card style on warm cream)."""
import math, functools
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1280, 720, 25
PG = "/home/user/esd/assets/pinggan/"
NOTO = "/usr/share/fonts/truetype/noto/"
F_SERIF_B = NOTO + "NotoSerif-Bold.ttf"
F_SERIF = NOTO + "NotoSerif-Regular.ttf"
F_SANS_B = NOTO + "NotoSans-Bold.ttf"
F_SANS = NOTO + "NotoSans-Regular.ttf"
F_SANS_SB = NOTO + "NotoSans-Bold.ttf"
F_HAND = "/usr/share/fonts/opentype/comic-neue/ComicNeue-Bold.otf"

CREAM = (248, 243, 234)
PAPER = (255, 253, 248)
INK = (48, 34, 30)
MUTED = (120, 104, 96)
LINE = (226, 216, 202)
GREEN = (74, 150, 96)
AMBER = (224, 150, 40)
RED = (200, 70, 60)
BLUE = (60, 118, 176)
COL = {"ju": (206, 120, 138), "amir": (34, 112, 120), "sara": (140, 98, 156), "lina": (112, 118, 60),
       "nar": (92, 72, 64)}


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def lerp(a, b, t): return a + (b - a) * t
def ease(t): t = clamp(t); return t * t * (3 - 2 * t)
def ease_out(t): t = clamp(t); return 1 - (1 - t) ** 3
def ease_io(t): t = clamp(t); return 4 * t ** 3 if t < .5 else 1 - (-2 * t + 2) ** 3 / 2
def back_out(t, s=1.6): t = clamp(t) - 1; return t * t * ((s + 1) * t + s) + 1
def seg(t, a, b): return clamp((t - a) / (b - a)) if b > a else float(t >= a)
def pop(t, t0, d=0.45): return 0.0 if t < t0 else back_out(seg(t, t0, t0 + d))
def fade(t, t0, d=0.4): return ease(seg(t, t0, t0 + d))


@functools.lru_cache(None)
def font(path, size): return ImageFont.truetype(path, size)


def tsize(text, fnt):
    b = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=fnt)
    return b[2] - b[0], b[3] - b[1], b


def wrap(text, fnt, maxw):
    out = []
    for para in text.split("\n"):
        words, line = para.split(" "), ""
        for w_ in words:
            cand = (line + " " + w_).strip()
            if tsize(cand, fnt)[0] <= maxw or not line: line = cand
            else: out.append(line); line = w_
        out.append(line)
    return out


# ---------------------------------------------------------------- compositing
def with_alpha(img, a):
    if a >= 0.999: return img
    info = dict(img.info); img = img.copy(); img.info.update(info); img.putalpha(img.getchannel("A").point(lambda v: int(v * clamp(a)))); return img


def place(fr, img, cx, cy, scale=1.0, alpha=1.0, rot=0.0, anchor=(0.5, 0.5)):
    if alpha <= 0.004 or scale <= 0.01: return
    if anchor == (0, 0) and img.info.get("pad"):
        cx -= img.info["pad"]; cy -= img.info["pad"]
    if abs(scale - 1) > 1e-3:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BICUBIC)
    if abs(rot) > 0.05: img = img.rotate(rot, Image.BICUBIC, expand=True)
    img = with_alpha(img, alpha)
    x, y = int(round(cx - anchor[0] * img.width)), int(round(cy - anchor[1] * img.height))
    l, t = max(0, x), max(0, y); r, b = min(fr.width, x + img.width), min(fr.height, y + img.height)
    if r > l and b > t: fr.alpha_composite(img.crop((l - x, t - y, r - x, b - y)), (l, t))


def shadow(img, off=(0, 6), blur=10, op=0.22):
    pad = blur * 2 + 8
    out = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (60, 40, 30, 0))
    sh.putalpha(img.getchannel("A").point(lambda v: int(v * op)))
    tmp = Image.new("RGBA", out.size, (0, 0, 0, 0)); tmp.paste(sh, (pad + off[0], pad + off[1]))
    out.alpha_composite(tmp.filter(ImageFilter.GaussianBlur(blur)))
    out.alpha_composite(img, (pad, pad))
    out.info["pad"] = pad
    return out


def rrect(w, h, fill=PAPER, r=18, outline=None, width=2):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=fill, outline=outline, width=width)
    return im


@functools.lru_cache(None)
def card(text, w, size=24, fg=INK, bg=PAPER, fnt=F_SANS_SB, pad=16, accent=None, h=None, align="left",
         sub=None, subsize=17, icon_name=None, strike=False):
    f = font(fnt, size); lines = wrap(text, f, w - 2 * pad - (8 if accent else 0) - (58 if icon_name else 0))
    lh = int(size * 1.32)
    sf = font(F_SANS, subsize); slines = wrap(sub, sf, w - 2 * pad - (58 if icon_name else 0)) if sub else []
    hh = h or (2 * pad + lh * len(lines) + (int(subsize * 1.35) * len(slines) + 4 if slines else 0))
    if icon_name: hh = max(hh, 2 * pad + 44)
    im = rrect(w, hh, bg, r=14)
    d = ImageDraw.Draw(im)
    x0 = pad + (8 if accent else 0)
    if accent: d.rounded_rectangle((0, 0, 8, hh - 1), 4, fill=accent); d.rectangle((4, 0, 8, hh - 1), fill=accent)
    if icon_name:
        ic = icon(icon_name, 44)
        im.alpha_composite(ic, (x0, (hh - 44) // 2)); x0 += 58
    y = (hh - (lh * len(lines) + (int(subsize * 1.35) * len(slines) + 4 if slines else 0))) // 2
    for ln in lines:
        tw = tsize(ln, f)[0]
        x = x0 if align == "left" else (w - tw) // 2
        d.text((x, y + (lh - size) // 2 - 2), ln, font=f, fill=fg)
        if strike:
            yy = y + lh // 2 + 1
            d.line((x - 4, yy, x + tw + 4, yy), fill=RED, width=4)
        y += lh
    if slines:
        y += 4
        for ln in slines:
            d.text((x0, y), ln, font=sf, fill=MUTED); y += int(subsize * 1.35)
    return shadow(im, blur=9, op=0.18)


@functools.lru_cache(None)
def chip(text, size=18, bg=(255, 255, 255), fg=INK, fnt=F_SANS_SB, padx=14, pady=7, dot=None):
    f = font(fnt, size); tw, th, b = tsize(text, f)
    w = tw + 2 * padx + (18 if dot else 0); h = size + 2 * pady + 4
    im = rrect(w, h, bg, r=h // 2)
    d = ImageDraw.Draw(im)
    x = padx
    if dot: d.ellipse((padx, h / 2 - 5, padx + 10, h / 2 + 5), fill=dot); x += 18
    d.text((x - b[0], (h - th) / 2 - b[1]), text, font=f, fill=fg)
    return im


# ---------------------------------------------------------------- icons (flat, drawn at 4x then reduced)
@functools.lru_cache(None)
def icon(name, s=64, color=None):
    S = s * 4; im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    c = color or INK; lw = max(4, S // 18)
    def P(*v): return [x * S for x in v]
    if name == "cart":
        d.line(P(.08, .2, .22, .2, .32, .66, .8, .66), fill=c, width=lw, joint="curve")
        d.polygon(P(.26, .3, .9, .3, .82, .56, .31, .56), fill=(236, 178, 70))
        for x in (.38, .74): d.ellipse(P(x - .07, .72, x + .07, .86), fill=c)
    elif name == "veg":
        d.ellipse(P(.12, .35, .55, .85), fill=(226, 110, 60)); d.ellipse(P(.4, .3, .88, .82), fill=(96, 164, 80))
        d.polygon(P(.3, .38, .22, .12, .42, .3), fill=(70, 140, 60))
    elif name == "pot":
        d.rounded_rectangle(P(.14, .36, .86, .84), S * .08, fill=(120, 130, 140))
        d.rectangle(P(.08, .32, .92, .42), fill=(90, 98, 108))
        d.rectangle(P(.02, .44, .14, .52), fill=(90, 98, 108)); d.rectangle(P(.86, .44, .98, .52), fill=(90, 98, 108))
        for x in (.35, .5, .65): d.arc(P(x - .05, .08, x + .05, .28), 90, 270, fill=(170, 170, 170), width=lw // 2)
    elif name in ("plate", "plate_s", "plate_l", "plate_left"):
        r = {"plate": .42, "plate_s": .3, "plate_l": .46, "plate_left": .42}[name]
        d.ellipse(P(.5 - r, .5 - r * .78, .5 + r, .5 + r * .78), fill=(250, 250, 250), outline=(200, 196, 190), width=lw // 2)
        d.ellipse(P(.5 - r * .7, .5 - r * .52, .5 + r * .7, .5 + r * .52), outline=(226, 222, 216), width=lw // 3)
        fr_ = {"plate": .45, "plate_s": .35, "plate_l": .62, "plate_left": .3}[name]
        d.ellipse(P(.5 - r * fr_, .5 - r * fr_ * .6, .5 + r * fr_ * .2, .5 + r * fr_ * .6), fill=(252, 248, 236))
        d.ellipse(P(.5, .5 - r * fr_ * .5, .5 + r * fr_ * .9, .5 + r * fr_ * .5), fill=(214, 128, 60))
        if name == "plate_left":
            d.ellipse(P(.54, .3, .66, .4), fill=(90, 150, 70))
    elif name == "taste":
        d.ellipse(P(.1, .1, .9, .9), fill=(250, 208, 90))
        d.ellipse(P(.3, .34, .38, .44), fill=c); d.ellipse(P(.62, .34, .7, .44), fill=c)
        d.arc(P(.28, .38, .72, .74), 20, 160, fill=c, width=lw)
    elif name == "coin":
        d.ellipse(P(.1, .1, .9, .9), fill=(232, 180, 60)); d.ellipse(P(.18, .18, .82, .82), outline=(200, 140, 30), width=lw // 2)
        f = font(F_SANS_B, int(S * .3)); tw, th, b = tsize("RM", f)
        d.text((S / 2 - tw / 2 - b[0], S / 2 - th / 2 - b[1]), "RM", font=f, fill=(120, 80, 10))
    elif name == "bin":
        d.polygon(P(.2, .3, .8, .3, .72, .92, .28, .92), fill=(110, 116, 122))
        d.rectangle(P(.14, .2, .86, .28), fill=(80, 86, 92)); d.rectangle(P(.4, .1, .6, .2), fill=(80, 86, 92))
        for x in (.38, .5, .62): d.line(P(x, .4, x, .82), fill=(170, 176, 182), width=lw // 2)
    elif name == "recycle":
        d.rounded_rectangle(P(.08, .08, .92, .92), S * .1, fill=BLUE)
        for k in range(3):
            a0 = k * 120 + 20
            d.arc(P(.24, .24, .76, .76), a0, a0 + 90, fill="white", width=lw)
            a = math.radians(a0 + 90); x, y = .5 + .26 * math.cos(a), .5 + .26 * math.sin(a)
            d.regular_polygon((x * S, y * S, S * .07), 3, rotation=-(a0 + 90) - 90, fill="white")
    elif name == "leafbin":
        d.rounded_rectangle(P(.08, .08, .92, .92), S * .1, fill=GREEN)
        d.ellipse(P(.3, .22, .7, .78), fill="white"); d.line(P(.5, .82, .5, .3), fill=GREEN, width=lw // 2)
    elif name == "trashbin":
        d.rounded_rectangle(P(.08, .08, .92, .92), S * .1, fill=(90, 96, 102))
        d.polygon(P(.3, .34, .7, .34, .66, .8, .34, .8), fill="white"); d.rectangle(P(.26, .24, .74, .3), fill="white")
    elif name == "box":
        d.polygon(P(.15, .3, .55, .18, .88, .3, .48, .42), fill=(244, 244, 240), outline=(190, 190, 186))
        d.polygon(P(.15, .3, .48, .42, .48, .9, .15, .76), fill=(232, 232, 226), outline=(190, 190, 186))
        d.polygon(P(.48, .42, .88, .3, .88, .76, .48, .9), fill=(250, 250, 246), outline=(190, 190, 186))
        d.ellipse(P(.58, .48, .76, .72), fill=GREEN)
    elif name == "scale":
        d.rounded_rectangle(P(.1, .5, .9, .9), S * .06, fill=(150, 156, 162))
        d.rectangle(P(.16, .38, .84, .48), fill=(190, 196, 202))
        d.rounded_rectangle(P(.36, .62, .64, .8), S * .03, fill=(40, 60, 50))
        f = font(F_SANS_B, int(S * .12)); d.text((.39 * S, .63 * S), "kg", font=f, fill=(120, 230, 150))
        d.polygon(P(.26, .38, .74, .38, .64, .16, .36, .16), fill=(120, 126, 132))
    elif name == "phone":
        d.rounded_rectangle(P(.25, .05, .75, .95), S * .08, fill=c)
        d.rounded_rectangle(P(.29, .12, .71, .86), S * .03, fill=(200, 230, 240))
    elif name == "note":
        d.rounded_rectangle(P(.18, .06, .86, .94), S * .05, fill=(255, 250, 230), outline=(200, 180, 140), width=lw // 2)
        for y in (.3, .45, .6, .75): d.line(P(.3, y, .76, y), fill=(160, 170, 200), width=lw // 3)
        for y in (.18, .38, .58, .78): d.ellipse(P(.12, y, .22, y + .06), fill=(120, 120, 120))
    elif name == "clip":
        d.rounded_rectangle(P(.16, .1, .84, .95), S * .05, fill=(190, 150, 100))
        d.rectangle(P(.24, .2, .76, .88), fill="white"); d.rounded_rectangle(P(.36, .04, .64, .16), S * .03, fill=(120, 124, 130))
        for y in (.36, .5, .64, .78): d.line(P(.32, y, .68, y), fill=(170, 170, 170), width=lw // 3)
    elif name == "people":
        for x, cc in ((.3, (206, 120, 138)), (.7, (34, 112, 120)), (.5, (140, 98, 156))):
            d.ellipse(P(x - .1, .18, x + .1, .38), fill=cc); d.pieslice(P(x - .18, .42, x + .18, .95), 180, 360, fill=cc)
    elif name == "clock":
        d.ellipse(P(.08, .08, .92, .92), fill="white", outline=c, width=lw)
        d.line(P(.5, .5, .5, .24), fill=c, width=lw); d.line(P(.5, .5, .7, .58), fill=c, width=lw)
    elif name == "check":
        d.ellipse(P(.05, .05, .95, .95), fill=GREEN); d.line(P(.27, .52, .44, .68, .74, .34), fill="white", width=lw * 2, joint="curve")
    elif name == "cross":
        d.ellipse(P(.05, .05, .95, .95), fill=RED)
        d.line(P(.32, .32, .68, .68), fill="white", width=lw * 2); d.line(P(.68, .32, .32, .68), fill="white", width=lw * 2)
    elif name == "question":
        d.ellipse(P(.05, .05, .95, .95), fill=AMBER)
        f = font(F_SANS_B, int(S * .62)); tw, th, b = tsize("?", f)
        d.text((S / 2 - tw / 2 - b[0], S / 2 - th / 2 - b[1]), "?", font=f, fill="white")
    elif name == "chart":
        d.rectangle(P(.1, .1, .9, .9), fill="white", outline=(200, 196, 190), width=lw // 3)
        for i, (hh, cc) in enumerate(((.5, BLUE), (.35, AMBER), (.6, GREEN))):
            d.rectangle(P(.2 + i * .22, .85 - hh, .34 + i * .22, .85), fill=cc)
    elif name == "folder":
        d.rounded_rectangle(P(.06, .2, .94, .88), S * .05, fill=(60, 64, 80))
        d.rectangle(P(.12, .26, .88, .82), fill="white")
        for y in (.38, .5, .62, .74): d.line(P(.2, y, .8, y), fill=(190, 190, 190), width=lw // 3)
    elif name == "bulb":
        d.ellipse(P(.22, .06, .78, .62), fill=(250, 208, 90)); d.rectangle(P(.38, .58, .62, .8), fill=(160, 160, 160))
    return im.resize((s, s), Image.LANCZOS)


# ---------------------------------------------------------------- photos
@functools.lru_cache(None)
def panel(k):
    """Storyboard panel k (1-12), upscaled with gentle sharpening."""
    im = Image.open(PG + "storyboard.webp").convert("RGB")
    rows = [(96, 412), (458, 740), (786, 1060), (1104, 1418)]
    cols = [[(5, 341), (349, 675), (683, 1019)]] * 2 + [[(5, 355), (363, 650), (657, 1019)], [(5, 349), (357, 647), (655, 1019)]]
    r, c = divmod(k - 1, 3)
    (y0, y1), (x0, x1) = rows[r], cols[r][c]
    p = im.crop((x0 + 2, y0 + 2, x1 - 2, y1 - 2))
    p = p.resize((p.width * 3, p.height * 3), Image.LANCZOS)
    return p.filter(ImageFilter.UnsharpMask(2.2, 70, 2))


@functools.lru_cache(None)
def face(name, s=96, ring=None):
    boxes = {"ju": (75, 85, 325, 335), "amir": (470, 78, 730, 338), "sara": (840, 95, 1080, 335),
             "lina": (1225, 85, 1475, 335)}
    im = Image.open(PG + "characters.webp").convert("RGB").crop(boxes[name]).resize((s * 2, s * 2), Image.LANCZOS)
    m = Image.new("L", im.size, 0); ImageDraw.Draw(m).ellipse((0, 0, s * 2 - 1, s * 2 - 1), fill=255)
    out = Image.new("RGBA", (s * 2 + 12, s * 2 + 12), (0, 0, 0, 0))
    ImageDraw.Draw(out).ellipse((0, 0, s * 2 + 11, s * 2 + 11), fill=ring or COL[name])
    rgba = im.convert("RGBA"); rgba.putalpha(m)
    out.alpha_composite(rgba, (6, 6))
    return out.resize((s + 6, s + 6), Image.LANCZOS)


def ken_burns(img, w, h, z, fx, fy):
    """Crop img to aspect w:h at zoom z (1 = fit), centred on (fx, fy) in 0..1, and resize to (w, h)."""
    iw, ih = img.size
    base = min(iw / w, ih / h)
    cw, ch = w * base / z, h * base / z
    cx = clamp(fx * iw, cw / 2, iw - cw / 2); cy = clamp(fy * ih, ch / 2, ih - ch / 2)
    return img.resize((w, h), Image.BICUBIC, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))


@functools.lru_cache(None)
def backdrop():
    rng = np.random.default_rng(3)
    n = rng.normal(0, 1, (H, W)).astype(np.float32)
    from scipy.ndimage import gaussian_filter
    n = gaussian_filter(n, 1.2) * 2.2
    yy, xx = np.mgrid[0:H, 0:W]
    vig = 1 - 0.07 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    arr = np.array(CREAM, np.float32)[None, None] * vig[..., None] + n[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
