"""Render the animated video "Selepas Pinggan Ditinggalkan" (16:9, 1280x720, 25 fps).

Visuals: the 12 approved storyboard panels (slow Ken Burns moves inside a photo frame) + animated
flat infographics per scene, character face badges from the character sheet, burned-in captions.
Audio: offline TTS lines (pinggan_voices.py), original synthesised cheerful music (music.py,
royalty-free), synthesised cafeteria ambience and UI sound effects.

    python3 pinggan_voices.py
    python3 pinggan.py                      # build/pg/pinggan.mp4 + .srt
    python3 pinggan.py --still <scene> <t>  # one frame
    python3 pinggan.py --sheet out.png      # contact sheet
"""
import json, math, os, subprocess, sys
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw
from scipy.io import wavfile
from scipy.signal import resample_poly, lfilter
from pg_gfx import *

BUILD = "/home/user/esd/build/pg"
AUD = BUILD + "/audio"
SR = 44100
META = json.load(open(AUD + "/meta.json"))
XF = 0.5          # crossfade between scenes (s)

# photo frame & right-hand panel
PX, PY, PW, PH = 48, 100, 628, 528
RX, RW = 712, 520
RC = RX + RW // 2

COMPS = [("Pemikiran Sistem", "Systems Thinking"), ("Kompetensi Antisipasi", "Anticipatory"),
         ("Kompetensi Normatif", "Normative"), ("Kompetensi Kolaborasi", "Collaboration"),
         ("Pemikiran Kritis", "Critical Thinking"), ("Kesedaran Kendiri", "Self-awareness"),
         ("Kompetensi Strategik", "Strategic"), ("Penyelesaian Masalah Bersepadu", "Integrated Problem-solving")]
SHORT = ["Sistem", "Antisipasi", "Normatif", "Kolaborasi", "Kritis", "Kendiri", "Strategik", "Bersepadu"]


# ================================================================ drawing helpers
def photo(fr, k, z, fx, fy, alpha=1.0, box=(PX, PY, PW, PH), k2=None, mix=0.0):
    x, y, w, h = box
    im = ken_burns(panel(k), w, h, z, fx, fy)
    if k2 and mix > 0: im = Image.blend(im, ken_burns(panel(k2), w, h, z, fx, fy), clamp(mix))
    b = 8
    f = Image.new("RGBA", (w + 2 * b, h + 2 * b), (255, 255, 255, 255))
    f.paste(im, (b, b))
    place(fr, shadow(f, blur=12, op=0.25), x + w / 2, y + h / 2 + 4, alpha=alpha)


def kb(t, d, a, b):
    """interpolate Ken-Burns tuples (z, fx, fy) across the scene."""
    u = ease_io(t / d)
    return tuple(lerp(p, q, u) for p, q in zip(a, b))


def kb_path(t, keys):
    """keys: [(time, (z, fx, fy)), ...] eased piecewise."""
    if t <= keys[0][0]: return keys[0][1]
    for (t0, a), (t1, b) in zip(keys, keys[1:]):
        if t <= t1:
            u = ease_io(seg(t, t0, t1)); return tuple(lerp(p, q, u) for p, q in zip(a, b))
    return keys[-1][1]


def header(fr, num, title, comp, t):
    d = ImageDraw.Draw(fr)
    a = fade(t, 0.1, 0.5)
    if a <= 0: return
    ov = Image.new("RGBA", (W, 96), (0, 0, 0, 0)); o = ImageDraw.Draw(ov)
    o.ellipse((PX, 26, PX + 48, 74), fill=INK)
    f = font(F_SANS_B, 22); tw, th, bb = tsize(num, f)
    o.text((PX + 24 - tw / 2 - bb[0], 50 - th / 2 - bb[1]), num, font=f, fill=CREAM)
    o.text((PX + 62, 28), title, font=font(F_SERIF_B, 32), fill=INK)
    # competency tracker (8 dots)
    x0 = W - 48 - 8 * 34
    for i in range(8):
        cx, cy = x0 + i * 34 + 14, 50
        if comp is not None and i < comp:
            o.ellipse((cx - 13, cy - 13, cx + 13, cy + 13), fill=GREEN)
        elif comp is not None and i == comp:
            r = 13 + 2.5 * (0.5 + 0.5 * math.sin(t * 4))
            o.ellipse((cx - r, cy - r, cx + r, cy + r), fill=AMBER)
        else:
            o.ellipse((cx - 12, cy - 12, cx + 12, cy + 12), outline=LINE, width=3, fill=PAPER)
        f2 = font(F_SANS_B, 14); s = str(i + 1); tw, th, bb = tsize(s, f2)
        col = "white" if comp is not None and i <= comp else MUTED
        o.text((cx - tw / 2 - bb[0], cy - th / 2 - bb[1]), s, font=f2, fill=col)
    f3 = font(F_SANS, 13); s = "8 kompetensi ESD"; tw = tsize(s, f3)[0]
    o.text((W - 48 - tw, 70), s, font=f3, fill=MUTED)
    place(fr, ov, W / 2, 48, alpha=a)


def comp_badge(fr, comp, t, t0=0.3):
    """competency label chip under the header, top-left of the right panel."""
    if comp is None: return
    ms, en = COMPS[comp]
    s = pop(t, t0, 0.5)
    txt = f"{comp + 1}  {ms}  ·  {en}"
    im = chip(txt, size=17 if tsize(txt, font(F_SANS_B, 17))[0] < RW - 40 else 14, bg=AMBER, fg="white", fnt=F_SANS_B, padx=16, pady=8)
    place(fr, im, RX, PY + 2, scale=s, anchor=(0, 0))


def line_on(L, k, t, lead=0.1): return L[k][0] - lead <= t


def sticky(fr, img, x, y, t, t0, anchor=(0.5, 0.5), out=None, dy=18):
    """pop/slide an element in at t0 (and fade it out from `out`)."""
    if t < t0: return
    u = ease_out(seg(t, t0, t0 + 0.5))
    a = u if out is None else u * (1 - fade(t, out, 0.4))
    place(fr, img, x, y + (1 - u) * dy, alpha=a, anchor=anchor)


def hand_text(fr, text, x, y, t, t0, dur, size=30, color=(40, 50, 110), maxw=440):
    """handwriting reveal (left-to-right wipe line by line)."""
    if t < t0: return
    f = font(F_HAND, size); lines = wrap(text, f, maxw); lh = int(size * 1.35)
    total = sum(tsize(l, f)[0] for l in lines) + 1
    shown = total * ease(seg(t, t0, t0 + dur))
    for i, l in enumerate(lines):
        lw = tsize(l, f)[0]
        if shown <= 0: break
        im = Image.new("RGBA", (lw + 10, lh + 6), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((2, 0), l, font=f, fill=color)
        cut = int(min(lw + 10, shown + 2))
        im = im.crop((0, 0, cut, lh + 6))
        fr.alpha_composite(im, (int(x), int(y + i * lh)))
        shown -= lw


def arrow(d, p0, p1, frac, color=INK, width=4, head=12):
    if frac <= 0: return
    x = lerp(p0[0], p1[0], frac); y = lerp(p0[1], p1[1], frac)
    d.line((p0, (x, y)), fill=color, width=width)
    a = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    for s in (-1, 1):
        b = a + math.pi + s * 0.5
        d.line(((x, y), (x + head * math.cos(b), y + head * math.sin(b))), fill=color, width=width)


def stamp(fr, text, x, y, t, t0, color=GREEN, size=22, rot=-6):
    if t < t0: return
    im = chip(text, size=size, bg=(255, 255, 255), fg=color, fnt=F_SANS_B, padx=18, pady=10)
    o = Image.new("RGBA", (im.width + 8, im.height + 8), (0, 0, 0, 0))
    o.alpha_composite(im, (4, 4))
    ImageDraw.Draw(o).rounded_rectangle((2, 2, o.width - 3, o.height - 3), o.height // 2, outline=color, width=4)
    u = seg(t, t0, t0 + 0.35)
    place(fr, o, x, y, scale=lerp(1.6, 1.0, ease_out(u)), alpha=ease(u * 2), rot=rot)


def speaker_card(fr, who, text, x, y, t, t0, w=RW, out=None, size=22):
    img = card(text, w, size=size, accent=COL[who])
    sticky(fr, img, x, y, t, t0, anchor=(0, 0), out=out)
    if t >= t0:
        a = ease(seg(t, t0, t0 + 0.4)) * (1 - (fade(t, out, 0.4) if out else 0))
        place(fr, face(who, 44), x + w - 20, y + 6, alpha=a)


# ================================================================ scenes
def sc_title(fr, t, d, L):
    u = ease_out(seg(t, 0.2, 1.4))
    place(fr, icon("plate_left", 180), W / 2, 200, scale=pop(t, 0.2, 0.6))
    f = font(F_SERIF_B, 64); s = "Selepas Pinggan Ditinggalkan"; tw = tsize(s, f)[0]
    ov = Image.new("RGBA", (tw + 40, 110), (0, 0, 0, 0)); o = ImageDraw.Draw(ov)
    o.text((20, 10), s, font=f, fill=INK)
    place(fr, ov, W / 2, 350 + (1 - u) * 30, alpha=u)
    d_ = ImageDraw.Draw(fr)
    wline = 520 * ease(seg(t, 1.0, 2.0))
    d_.line((W / 2 - wline / 2, 412, W / 2 + wline / 2, 412), fill=(214, 160, 150), width=5)
    sub = chip("Kisah lapan kompetensi ESD di kafeteria kampus", size=22, bg=CREAM, fg=MUTED, fnt=F_SANS)
    place(fr, sub, W / 2, 450, alpha=fade(t, 1.6, 0.6))
    for i, (n, nm) in enumerate((("ju", "Ju"), ("amir", "Amir"), ("sara", "Sara"), ("lina", "Kak Lina"))):
        x = W / 2 + (i - 1.5) * 170
        s = pop(t, 2.4 + i * 0.25, 0.5)
        place(fr, shadow(face(n, 96), blur=8, op=0.2), x, 560, scale=s)
        place(fr, chip(nm, size=18, bg=COL[n], fg="white", fnt=F_SANS_B), x, 638, scale=s)


def sc01(fr, t, d, L):
    z = kb_path(t, [(0, (1.15, .45, .35)), (8, (1.05, .5, .45)), (12, (1.05, .5, .45)), (d, (1.75, .6, .8))])
    photo(fr, 1, *z)
    header(fr, "01", "Selepas acara", None, t)
    # opening: the event photo on Amir's phone, then lowered to reveal the plate
    if t < 6.5:
        u = ease_io(seg(t, 4.2, 6.2))
        ph = Image.new("RGBA", (340, 620), (0, 0, 0, 0)); p = ImageDraw.Draw(ph)
        p.rounded_rectangle((0, 0, 339, 619), 44, fill=(28, 28, 32))
        scr = Image.new("RGB", (308, 560), (130, 196, 230)); s = ImageDraw.Draw(scr)
        for yy in range(560): s.line((0, yy, 308, yy), fill=(int(lerp(120, 250, yy / 560)), int(lerp(190, 230, yy / 560)), int(lerp(236, 200, yy / 560))))
        s.rectangle((0, 330, 308, 560), fill=(214, 176, 128))
        s.rectangle((24, 90, 284, 170), fill=(34, 112, 120))
        f = font(F_SANS_B, 26)
        for j, ln in enumerate(("PROGRAM", "KAMPUS LESTARI")):
            tw = tsize(ln, f)[0]; s.text((154 - tw / 2, 98 + j * 34), ln, font=f, fill="white")
        for k in range(9):
            x = 16 + k * 34; s.polygon(((x, 40), (x + 30, 40), (x + 15, 70)), fill=[(226, 110, 60), (250, 208, 90), (96, 164, 80)][k % 3])
        rng = np.random.default_rng(4)
        for k in range(60):
            x, y = rng.uniform(0, 308), rng.uniform(0, 320)
            s.rectangle((x, y, x + 6, y + 10), fill=tuple(int(c) for c in rng.choice([[226, 110, 60], [250, 208, 90], [206, 120, 138], [60, 118, 176]])))
        for k in range(7):
            x = 20 + k * 42; cc = [COL["amir"], COL["ju"], COL["sara"], COL["lina"], BLUE, COL["amir"], COL["sara"]][k]
            s.ellipse((x, 300, x + 34, 334), fill=(196, 150, 120)); s.pieslice((x - 12, 336, x + 46, 440), 180, 360, fill=cc)
        s.rectangle((0, 420, 308, 560), fill=(160, 120, 84))
        for k in range(4): s.ellipse((20 + k * 72, 440, 80 + k * 72, 480), fill="white")
        f2 = font(F_SANS, 15); s.text((16, 520), "Suka 128 · Program meriah!", font=f2, fill="white")
        ph.paste(scr, (16, 30)); p.rounded_rectangle((130, 12, 210, 20), 4, fill=(60, 60, 66))
        place(fr, shadow(ph, blur=16, op=0.3), W / 2, 380 + u * 520 + (1 - ease_out(seg(t, 0, .6))) * 40, alpha=1 - u * 0.3,
              rot=u * 8)
    # right side: leftovers noticed
    sticky(fr, card("Program tadi meriah…", RW, size=26, accent=COL["amir"], sub="…tetapi pinggan yang ditinggalkan masih berisi."), RX, PY + 10, t, 7.0)
    for i in range(6):
        x = RX + 44 + (i % 3) * 170 + 30; y = PY + 210 + (i // 3) * 120
        place(fr, shadow(icon("plate_left", 110), blur=6, op=0.18), x, y, scale=pop(t, 10.5 + i * 0.45))
    sticky(fr, chip("Makanan yang tidak habis", size=20, bg=RED, fg="white", fnt=F_SANS_B), RC, PY + 470, t, 14.0)


def sc02(fr, t, d, L):
    photo(fr, 2, *kb_path(t, [(0, (1.5, .3, .6)), (6, (1.1, .4, .5)), (13, (1.3, .75, .35)), (d, (1.05, .5, .5))]))
    header(fr, "02", "Jawapan segera", None, t)
    t1 = L["s02a"][0]; t2 = L["s02b"][0]
    speaker_card(fr, "amir", "Cadangan: tambah tong kitar semula", RX, PY + 10, t, t1)
    for i, n in enumerate(("leafbin", "recycle", "trashbin")):
        place(fr, shadow(icon(n, 96), blur=6, op=0.2), RX + 110 + i * 150, PY + 160, scale=pop(t, t1 + 0.6 + i * 0.3))
    speaker_card(fr, "ju", "Kalau makanan masih dibuang… masalah selesai?", RX, PY + 250, t, t2)
    if t >= t2 + 2.5:
        place(fr, shadow(icon("plate_left", 120), blur=6, op=0.2), RX + 110, PY + 420, scale=pop(t, t2 + 2.5))
        d_ = ImageDraw.Draw(fr); u = ease(seg(t, t2 + 3.0, t2 + 4.0))
        if u > 0: d_.arc((RX + 35, PY + 350, RX + 185, PY + 490), -90, -90 + 360 * u, fill=RED, width=6)
        sticky(fr, card("Makanan masih dibuang — punca belum difahami", 300, size=19), RX + 210, PY + 380, t, t2 + 3.4, anchor=(0, 0))
    sticky(fr, chip("Sara membuka buku nota…", size=17, bg=PAPER, fg=COL["sara"], fnt=F_SANS_B, dot=COL["sara"]), RX + RW, PY + 500, t, d - 5.5, anchor=(1, 0.5))


MAP = [("Pembelian", "cart"), ("Penyediaan", "pot"), ("Saiz hidangan", "plate"), ("Citarasa", "taste"),
       ("Kos", "coin"), ("Sisa / tong", "bin")]


def system_map(fr, t, t_in, t_move, t_arrows, x0=RX, y0=PY + 70, cw=280, gap=78, bracket=None, alpha=1.0):
    """vertical chain of picture cards. The bin card starts on top and is moved to the end at t_move."""
    order_start = [5, 0, 1, 2, 3, 4]
    um = ease_io(seg(t, t_move, t_move + 1.6))
    pos = {}
    for slot, idx in enumerate(order_start):
        final = idx
        y = lerp(y0 + slot * gap, y0 + final * gap, um)
        x = x0 + (math.sin(um * math.pi) * 150 if idx == 5 else 0)
        pos[idx] = (x, y)
    d_ = ImageDraw.Draw(fr)
    for i in range(5):
        fa = seg(t, t_arrows + i * 0.35, t_arrows + i * 0.35 + 0.4)
        if fa > 0:
            xa = x0 + cw / 2
            arrow(d_, (xa, y0 + i * gap + 58), (xa, y0 + (i + 1) * gap - 2), fa, color=(150, 120, 100), width=4, head=10)
    for idx in [0, 1, 2, 3, 4, 5]:
        name, ic = MAP[idx]
        im = card(name, cw, size=22, icon_name=ic, h=60, accent=(RED if idx == 5 else (214, 160, 150)))
        x, y = pos[idx]
        s = pop(t, t_in + order_start.index(idx) * 0.3)
        place(fr, im, x + cw / 2, y + 30, scale=s, alpha=alpha)
    if bracket is not None and t >= bracket:
        u = ease(seg(t, bracket, bracket + 0.6))
        bx = x0 + cw + 28
        d_.line((bx, y0 + 4, bx + 14, y0 + 4, bx + 14, y0 + lerp(4, 4 * gap + 56, u), bx, y0 + lerp(4, 4 * gap + 56, u)), fill=GREEN, width=4)
        lab = card("Punca di hulu", 170, size=18, sub="beli · masak · hidang · pilih · kos", subsize=13)
        place(fr, lab, bx + 2, y0 + 2 * gap + 30, alpha=u, anchor=(0, 0.5))
        lab2 = card("Kesan di hilir", 170, size=18)
        place(fr, lab2, bx + 2, y0 + 5 * gap + 30, alpha=u, anchor=(0, 0.5))


def sc03(fr, t, d, L):
    photo(fr, 3, *kb_path(t, [(0, (1.0, .5, .5)), (8, (1.6, .72, .82)), (13, (1.6, .72, .82)), (d, (1.15, .45, .45))]))
    header(fr, "03", "Hubung kait", 0, t)
    comp_badge(fr, 0, t)
    system_map(fr, t, 2.2, 8.5, 10.6, bracket=12.8)
    if 8.2 <= t <= 11.5:
        a = fade(t, 8.2, .3) * (1 - fade(t, 11.0, .4))
        place(fr, chip("Sara alih kad tong ke hujung", size=16, bg=COL["sara"], fg="white", fnt=F_SANS_B), RX + 350, PY + 300, alpha=a)


def scenario(fr, x, y, w, h, t, t0, key, title, sub):
    if t < t0: return
    u = ease_out(seg(t, t0, t0 + 0.6))
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); o = ImageDraw.Draw(im)
    o.rounded_rectangle((0, 0, w - 1, h - 1), 22, fill=(250, 246, 255))
    for k in range(0, 2 * (w + h), 22):  # dashed border = imagined scenario
        pass
    o.rounded_rectangle((3, 3, w - 4, h - 4), 20, outline=(170, 150, 200), width=3)
    tag = chip("Senario bayangan", size=15, bg=(170, 150, 200), fg="white", fnt=F_SANS_B)
    im.alpha_composite(tag, ((w - tag.width) // 2, 16))
    f = font(F_SANS_B, 23)
    for j, ln in enumerate(wrap(title, f, w - 40)):
        tw = tsize(ln, f)[0]; o.text(((w - tw) / 2, 62 + j * 30), ln, font=f, fill=INK)
    # counter
    o.rounded_rectangle((20, 250, w - 20, 268), 6, fill=(186, 192, 198))
    o.rectangle((30, 268, w - 30, 300), fill=(210, 214, 218))
    if key == "A":
        for i in range(3): im.alpha_composite(icon("plate_l", 88), (24 + i * 104, 168))
        im.alpha_composite(icon("bin", 70), (w // 2 - 35, 320))
        for i in range(2): im.alpha_composite(icon("plate_left", 58), (40 if i == 0 else w - 100, 334))
    elif key == "B":
        for i in range(3): im.alpha_composite(icon("plate_s", 88), (24 + i * 104, 168))
        im.alpha_composite(icon("people", 90), (w // 2 - 45, 318))
    else:
        for i, n in enumerate(("plate_s", "plate", "plate_l")): im.alpha_composite(icon(n, 88), (24 + i * 104, 168))
        for i, s_ in enumerate(("Kecil", "Sederhana", "Besar")):
            c = chip(s_, size=13, bg=(255, 255, 255), fg=INK, fnt=F_SANS_B, padx=8, pady=4)
            im.alpha_composite(c, (68 + i * 104 - c.width // 2, 140))
        im.alpha_composite(icon("clip", 80), (w // 2 - 90, 320)); im.alpha_composite(icon("question", 64), (w // 2 + 20, 328))
    fs = font(F_SANS, 18)
    for j, ln in enumerate(wrap(sub, fs, w - 40)):
        tw = tsize(ln, fs)[0]; o.text(((w - tw) / 2, h - 70 + j * 24), ln, font=fs, fill=MUTED)
    place(fr, shadow(im, blur=12, op=0.2), x + w / 2, y + h / 2 + (1 - u) * 30, alpha=u)


def sc04(fr, t, d, L):
    photo(fr, 3, *kb(t, d, (1.05, .5, .5), (1.2, .6, .45)))
    header(fr, "04", "Bayangkan kesan", 1, t)
    comp_badge(fr, 1, t)
    back = d - 4.5
    a = 1 - fade(t, back, 0.8)
    if a > 0.01:
        ov = Image.new("RGBA", (W, H - 92), CREAM + (255,))
        place(fr, ov, 0, 92, alpha=a * fade(t, 1.6, 0.5), anchor=(0.001, 0))  # cover
        if t < back + 0.8:
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            scenario(layer, 48, 130, 380, 470, t, 2.2, "A", "Amalan hidangan semasa diteruskan", "Sisa mungkin berterusan.")
            scenario(layer, 450, 130, 380, 470, t, 5.0, "B", "Semua hidangan dikecilkan", "Ada pelajar mungkin tidak puas hati atau masih lapar.")
            scenario(layer, 852, 130, 380, 470, t, 8.0, "C", "Pelajar memilih saiz sesuai", "Kesannya belum pasti — perlu dipantau.")
            place(fr, layer, W / 2, H / 2, alpha=a)
    if t >= back:
        for i, (k, s_) in enumerate((("A", "Amalan semasa"), ("B", "Semua dikecilkan"), ("C", "Pilih saiz + pantau"))):
            sticky(fr, card(f"{k}: {s_}", RW, size=22, icon_name="question", h=70), RX, PY + 70 + i * 96, t, back + 0.6 + i * 0.3, anchor=(0, 0))
        sticky(fr, chip("Kumpulan menimbang pilihan", size=17, bg=INK, fg="white", fnt=F_SANS_B), RC, PY + 400, t, back + 1.6)


def balance(fr, cx, cy, tilt, a=1.0):
    im = Image.new("RGBA", (460, 230), (0, 0, 0, 0)); o = ImageDraw.Draw(im)
    o.polygon(((230, 90), (200, 210), (260, 210)), fill=(150, 120, 100))
    ang = math.radians(tilt); dx, dy = 170 * math.cos(ang), 170 * math.sin(ang)
    o.line((230 - dx, 90 - dy, 230 + dx, 90 + dy), fill=(120, 96, 80), width=8)
    for sgn, n, lab in ((-1, "plate_s", "Saiz kecil"), (1, "plate_l", "Saiz besar")):
        x, y = 230 + sgn * dx, 90 + sgn * dy
        o.line((x, y, x, y + 30), fill=(120, 96, 80), width=3)
        im.alpha_composite(icon(n, 84), (int(x - 42), int(y + 12)))
        c = chip(lab, size=15, bg=PAPER, fg=INK, fnt=F_SANS_B); im.alpha_composite(c, (int(x - c.width / 2), int(y + 96)))
    place(fr, im, cx, cy, alpha=a)


def sc05(fr, t, d, L):
    photo(fr, 5, *kb_path(t, [(0, (1.0, .5, .5)), (6, (1.3, .75, .5)), (12, (1.5, .65, .8)), (d, (1.1, .5, .5))]))
    header(fr, "05", "Keperluan berbeza", 2, t)
    comp_badge(fr, 2, t)
    ta, tb, tc = L["s05a"][0], L["s05b"][0], L["s05c"][0]
    ph2 = tc + L["s05c"][1] - L["s05c"][0] + 1.6
    out = ph2
    speaker_card(fr, "sara", "Semua hidangan dikecilkan?", RX, PY + 60, t, ta, out=out)
    if tb - 0.2 <= t < out + 0.4:
        tilt = 12 * math.sin(clamp((t - tb) / 1.8) * math.pi * 2.5) * math.exp(-clamp(t - tb) * 0.8)
        balance(fr, RC, PY + 250, tilt, a=fade(t, tb - 0.2, .4) * (1 - fade(t, out, .4)))
    speaker_card(fr, "lina", "Ada pelajar yang perlukan lebih: beri pilihan", RX, PY + 380, t, tb + 1.5, out=out, size=20)
    speaker_card(fr, "amir", "Harga jelas dan berpatutan", RX, PY + 460, t, tc, out=out, size=20)
    if t >= out:
        board = card("Kriteria keputusan", RW, size=26, fnt=F_SERIF_B, h=64, align="center")
        sticky(fr, board, RX, PY + 80, t, out + 0.4, anchor=(0, 0))
        for i, (ms, en, c) in enumerate((("Keadilan", "fairness", COL["sara"]), ("Mampu milik", "affordability", COL["amir"]),
                                         ("Pilihan", "choice", COL["lina"]))):
            sticky(fr, card(ms, RW - 60, size=26, accent=c, sub=en, h=86), RX + 30, PY + 170 + i * 110, t, out + 1.0 + i * 0.7, anchor=(0, 0))


def sc06(fr, t, d, L):
    photo(fr, 6, *kb_path(t, [(0, (1.05, .5, .5)), (5, (1.4, .72, .45)), (12, (1.4, .72, .45)), (d, (1.1, .55, .7))]))
    header(fr, "06", "Dengar dahulu", 3, t)
    comp_badge(fr, 3, t)
    tb_end = L["s06b"][1]
    old = card("Cadangan asal", RW, size=22, accent=(170, 160, 150),
               sub="• 5 saiz hidangan  • kupon tempahan awal  • borang pilih lauk", subsize=18, strike=t >= tb_end + 0.2)
    a_old = 1 - 0.45 * fade(t, tb_end + 0.2, .4)
    sticky(fr, with_alpha(old, a_old), RX, PY + 60, t, 1.2, anchor=(0, 0))
    place(fr, face("lina", 64), RX + RW - 50, PY + 250, scale=pop(t, L["s06b"][0]))
    if t >= L["s06b"][0]:
        sticky(fr, card("Waktu rehat singkat: mesti mudah & cepat", RW - 90, size=20, accent=COL["lina"]), RX, PY + 222, t, L["s06b"][0] + 0.3, anchor=(0, 0))
    stamp(fr, "Terlalu rumit", RX + RW - 110, PY + 90, t, tb_end + 0.3, color=RED)
    if t >= tb_end + 1.2:
        new = card("Cadangan disemak", RW, size=24, accent=GREEN, sub="3 pilihan jelas: Kecil · Sederhana · Besar", subsize=19)
        sticky(fr, new, RX, PY + 330, t, tb_end + 1.2, anchor=(0, 0))
        for i, n in enumerate(("plate_s", "plate", "plate_l")):
            place(fr, icon(n, 80), RX + 120 + i * 140, PY + 480, scale=pop(t, tb_end + 1.8 + i * 0.25))
        sticky(fr, chip("Perubahan hasil input Kak Lina", size=16, bg=COL["lina"], fg="white", fnt=F_SANS_B), RC, PY + 545, t, tb_end + 2.8)


def sc07(fr, t, d, L):
    photo(fr, 7, *kb_path(t, [(0, (1.5, .2, .5)), (6, (1.5, .2, .5)), (10, (1.3, .75, .45)), (16, (1.1, .5, .5)), (d, (1.6, .25, .8))]))
    header(fr, "07", "Semak bukti", 4, t)
    comp_badge(fr, 4, t)
    ta, tb = L["s07a"][0], L["s07b"][0]
    place(fr, shadow(icon("box", 120), blur=8, op=0.2), RX + 70, PY + 125, scale=pop(t, ta))
    sticky(fr, card("Dakwaan: “lebih mesra alam”", RW - 150, size=21, accent=COL["amir"]), RX + 140, PY + 95, t, ta + 0.3, anchor=(0, 0))
    ev = [("Apa buktinya?", tb), ("Adakah ia mengurangkan makanan yang tidak habis?", L["s07c"][0])]
    for i, (q, t0) in enumerate(ev):
        sticky(fr, card(q, RW, size=20, icon_name="question", accent=COL["sara"]), RX, PY + 200 + i * 92, t, t0, anchor=(0, 0))
    t3 = L["s07c"][1] + 0.6
    sticky(fr, card("Belum ada bukti bukan bermakna salah", RW, size=20, accent=AMBER, sub="Semak dahulu sebelum membuat kesimpulan."), RX, PY + 390, t, t3, anchor=(0, 0))
    if t >= t3 + 2.5:
        sticky(fr, chip("Fokus semula: makanan yang tidak habis", size=17, bg=INK, fg="white", fnt=F_SANS_B), RX + 10, PY + 515, t, t3 + 2.5, anchor=(0, 0.5))
        place(fr, icon("plate_left", 64), RX + RW - 40, PY + 515, scale=pop(t, t3 + 3.0))


def sc08(fr, t, d, L):
    photo(fr, 8, *kb_path(t, [(0, (1.05, .5, .45)), (4, (1.8, .62, .8)), (9, (1.8, .62, .8)), (d, (1.7, .32, .78))]))
    header(fr, "08", "Peranan diri", 5, t)
    comp_badge(fr, 5, t)
    nb = Image.new("RGBA", (RW, 440), (0, 0, 0, 0)); o = ImageDraw.Draw(nb)
    o.rounded_rectangle((0, 0, RW - 1, 439), 14, fill=(255, 252, 238))
    for y in range(80, 430, 42): o.line((30, y, RW - 20, y), fill=(200, 212, 232), width=2)
    o.line((70, 0, 70, 439), fill=(236, 170, 170), width=2)
    for y in range(30, 430, 60): o.ellipse((16, y, 32, y + 16), fill=(220, 214, 200))
    sticky(fr, shadow(nb, blur=10, op=0.2), RX, PY + 70, t, 1.0, anchor=(0, 0))
    y0 = PY + 70 + 22
    hand_text(fr, "Refleksi", RX + 110, y0, t, 1.8, 0.8, size=34, color=(160, 60, 60))
    ta = L["s08a"][0]
    hand_text(fr, "Aku pun selalu ambil lebih daripada yang aku makan.", RX + 110, y0 + 70, t, ta, L["s08a"][1] - ta, size=28, maxw=RW - 150)
    hand_text(fr, "Esok: ambil secukupnya dulu. Tambah jika perlu.", RX + 110, y0 + 70 + 42 * 3, t, L["s08a"][1] + 1.2, 3.0, size=28, maxw=RW - 150,
              color=(30, 110, 90))


def sc09(fr, t, d, L):
    photo(fr, 9, *kb_path(t, [(0, (1.0, .5, .5)), (8, (1.5, .72, .6)), (16, (1.6, .2, .5)), (24, (1.3, .8, .75)), (d, (1.0, .5, .5))]))
    header(fr, "09", "Uji cadangan", 6, t)
    comp_badge(fr, 6, t)
    tab = Image.new("RGBA", (RW, 262), (0, 0, 0, 0)); o = ImageDraw.Draw(tab)
    o.rounded_rectangle((0, 0, RW - 1, 261), 14, fill=PAPER)
    o.rounded_rectangle((0, 0, RW - 1, 44), 14, fill=INK); o.rectangle((0, 30, RW - 1, 44), fill=INK)
    fb, fr_ = font(F_SANS_B, 17), font(F_SANS, 16)
    cols = (16, 136, 380)
    for x, h_ in zip(cols, ("Siapa", "Tugas", "Bila")): o.text((x, 11), h_, font=fb, fill="white")
    rows = [("Kak Lina", "Uji susunan 3 saiz", "Waktu makan", "lina"), ("Sara", "Kumpul maklum balas", "Selepas makan", "sara"),
            ("Amir", "Timbang sisa (stesen berasingan)", "Setiap hari rintis", "amir"), ("Ju", "Bimbing & semak kemajuan", "Mingguan", "ju")]
    for i, (a, b, c, who) in enumerate(rows):
        y = 56 + i * 50
        o.line((10, y - 6, RW - 10, y - 6), fill=LINE, width=1)
        o.text((cols[0], y + 6), a, font=fb, fill=COL[who])
        for j, ln in enumerate(wrap(b, fr_, 230)): o.text((cols[1], y + (6 if len(wrap(b, fr_, 230)) == 1 else -3) + j * 20), ln, font=fr_, fill=INK)
        o.text((cols[2], y + 6), c, font=fr_, fill=MUTED)
    # reveal rows progressively
    vis = int(56 + 50 * 4 * ease(seg(t, 3.5, 9.0)))
    tab2 = tab.crop((0, 0, RW, max(46, min(262, vis))))
    sticky(fr, shadow(tab2, blur=9, op=0.18), RX, PY + 50, t, 2.5, anchor=(0, 0))
    chips = [("Data asas dahulu (baseline)", BLUE), ("Kriteria kejayaan dipersetujui", GREEN), ("Sumber: penimbang, label, borang", AMBER)]
    x = RX; y = PY + 350
    for i, (s_, c) in enumerate(chips):
        im = chip(s_, size=15, bg=c, fg="white", fnt=F_SANS_B)
        if x + im.width > RX + RW: x = RX; y += 44
        sticky(fr, im, x, y, t, 10.5 + i * 0.6, anchor=(0, 0)); x += im.width + 10
    sticky(fr, card("Stesen timbang sisa", RW, size=20, icon_name="scale", sub="Diletakkan berasingan daripada kaunter makanan.", subsize=16), RX, PY + 440, t, 14.5, anchor=(0, 0))
    if t >= 20:
        blink = 0.5 + 0.5 * math.sin(t * 5)
        im = chip("  Rintis sedang berjalan · pemerhatian direkod", size=16, bg=(40, 40, 44), fg="white", fnt=F_SANS_B, dot=(230, int(60 + 120 * blink), 60))
        sticky(fr, im, RC, PY + 555, t, 20)


def sc10(fr, t, d, L):
    photo(fr, 10, *kb_path(t, [(0, (1.0, .5, .5)), (8, (1.5, .3, .75)), (16, (1.4, .72, .45)), (d, (1.05, .5, .5))]))
    header(fr, "10", "Nilai dan ubah", 7, t)
    comp_badge(fr, 7, t)
    ta, tb = L["s10a"][0], L["s10b"][0]
    ph2 = L["s10b"][1] + 4.0
    out = ph2
    items = [("Sisa makanan", "scale"), ("Kos", "coin"), ("Maklum balas", "people"), ("Beban kerja", "clock")]
    for i, (s_, ic) in enumerate(items):
        x = RX + (i % 2) * (RW // 2 + 5); y = PY + 60 + (i // 2) * 86
        sticky(fr, card(s_, RW // 2 - 5, size=19, icon_name=ic, h=72), x, y, t, ta + 0.3 + i * 0.5, anchor=(0, 0), out=out)
    sticky(fr, chip("Dibaca bersama — bukan berasingan", size=16, bg=INK, fg="white", fnt=F_SANS_B), RC, PY + 250, t, ta + 2.8, out=out)
    if tb - 0.2 <= t < out + 0.4:
        a = fade(t, tb - 0.2, .4) * (1 - fade(t, out, .4))
        old = card("Label:  S  /  M  /  L", 250, size=22, icon_name="question", h=74)
        place(fr, with_alpha(old, a), RX + 10, PY + 290, anchor=(0, 0))
        place(fr, face("lina", 44), RX + 250, PY + 296, alpha=a)
        if t >= tb + 2.4:
            d_ = ImageDraw.Draw(fr); arrow(d_, (RX + 272, PY + 330), (RX + 312, PY + 330), seg(t, tb + 2.4, tb + 2.8), color=GREEN)
            new = card("Kecil · Sederhana · Besar", 200, size=18, sub="+ gambar saiz", subsize=15)
            sticky(fr, with_alpha(new, a), RX + 318, PY + 290, t, tb + 2.8, anchor=(0, 0))
        for i, n in enumerate(("plate_s", "plate", "plate_l")):
            place(fr, icon(n, 70), RX + 330 + i * 70, PY + 430, scale=pop(t, tb + 3.2 + i * 0.2), alpha=a)
    if t >= out:
        # integration: earlier competencies feed one decision
        cx, cy = RC, PY + 300
        d_ = ImageDraw.Draw(fr)
        for i in range(7):
            ang = -math.pi / 2 + (i - 3) * 0.42 + (math.pi if i > 99 else 0)
            ang = math.radians(-180 + i * 30)
            x, y = cx + 210 * math.cos(ang), cy + 0 + 190 * math.sin(ang) * 0.9 + 60
            u = seg(t, out + 0.4 + i * 0.25, out + 0.9 + i * 0.25)
            if u > 0:
                arrow(d_, (x, y), (lerp(x, cx, 0.62), lerp(y, cy + 60, 0.62)), ease(seg(t, out + 2.4, out + 3.2)), color=(200, 180, 160), width=3, head=9)
                place(fr, chip(f"{i + 1} {SHORT[i]}", size=15, bg=GREEN, fg="white", fnt=F_SANS_B), x, y, scale=back_out(u))
        s = pop(t, out + 3.0, 0.6)
        disc = Image.new("RGBA", (190, 190), (0, 0, 0, 0)); o = ImageDraw.Draw(disc)
        o.ellipse((0, 0, 189, 189), fill=AMBER)
        f = font(F_SANS_B, 20)
        for j, ln in enumerate(("Keputusan", "bersepadu")):
            tw = tsize(ln, f)[0]; o.text((95 - tw / 2, 70 + j * 26), ln, font=f, fill="white")
        place(fr, shadow(disc, blur=8, op=0.2), cx, cy + 60, scale=s)
        stamp(fr, "Percubaan disemak semula", RC, PY + 510, t, out + 5.0, color=GREEN, size=20)


def sc11(fr, t, d, L):
    photo(fr, 11, *kb_path(t, [(0, (1.0, .5, .5)), (8, (1.6, .52, .8)), (16, (1.3, .65, .5)), (d, (1.05, .5, .5))]))
    header(fr, "11", "Bukti pembelajaran", None, t)
    tc = L["s11c"][0] - 1.2
    out = tc
    sticky(fr, chip("Portfolio pembelajaran", size=17, bg=INK, fg="white", fnt=F_SANS_B), RX, PY + 2, t, 0.4, anchor=(0, 0), out=out)
    items = ["Peta sistem", "Perbandingan pilihan", "Maklum balas pihak berkepentingan", "Rekod rintis", "Refleksi kendiri"]
    for i, s_ in enumerate(items):
        y = PY + 60 + i * 50
        sticky(fr, card(s_, 330, size=17, h=42, pad=12), RX, y, t, 1.0 + i * 0.5, anchor=(0, 0), out=out)
        place(fr, icon("check", 30), RX + 330, y + 26, scale=pop(t, 2.2 + i * 0.6) * (1 - fade(t, out, .4)))
    t_fb = L["s11b"][1] + 0.3
    sticky(fr, card("“Pilihan C paling baik.”", RW - 30, size=19, accent=RED, sub="Maklum balas: Apa buktinya? Siapa terkesan?", subsize=16),
           RX + 30, PY + 318, t, max(6.0, t_fb - 5.5), anchor=(0, 0), out=out)
    sticky(fr, card("Disemak: C diuji kerana memberi pilihan, boleh dilaksana di kaunter dan boleh dipantau.", RW - 30, size=17, accent=GREEN),
           RX + 30, PY + 420, t, max(9.0, t_fb - 2.0), anchor=(0, 0), out=out)
    if t >= out:
        sticky(fr, chip("Untuk pensyarah", size=17, bg=COL["ju"], fg="white", fnt=F_SANS_B), RX, PY + 2, t, out + 0.3, anchor=(0, 0))
        cx, cy, r = RC, PY + 235, 150
        nodes = ["Pentaksiran", "Kenal pasti jurang", "Tambah baik pengajaran", "Semak keberkesanan"]
        d_ = ImageDraw.Draw(fr)
        u = ease(seg(t, out + 0.6, out + 2.6))
        if u > 0:
            d_.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * u, fill=(214, 190, 170), width=6)
        hi = int(((t - out - 3) / 1.6)) % 4 if t > out + 3 else -1
        for i, s_ in enumerate(nodes):
            ang = math.radians(-90 + i * 90)
            x, y = cx + r * math.cos(ang), cy + r * math.sin(ang)
            c = card(s_, 170, size=16, align="center", bg=(AMBER if i == hi else PAPER), fg=("white" if i == hi else INK), pad=10)
            place(fr, c, x, y, scale=pop(t, out + 0.8 + i * 0.5))
        place(fr, chip("CQI", size=22, bg=INK, fg="white", fnt=F_SANS_B), cx, cy, scale=pop(t, out + 2.8))
        sticky(fr, card("Semakan projek pelajar berbeza daripada CQI kursus / program", RW, size=17, accent=COL["ju"],
                        sub="Satu penyerahan semula tidak melengkapkan kitaran CQI.", subsize=15), RX, PY + 430, t, out + 4.5, anchor=(0, 0))
    if t > d - 2.2:
        place(fr, shadow(icon("folder", 110), blur=8, op=0.2), PX + PW - 70, PY + PH - 70, scale=pop(t, d - 2.2))


def sc12(fr, t, d, L):
    mix = ease(seg(t, 0.4, 2.6))
    photo(fr, 1 if mix < 1 else 12, *kb_path(t, [(0, (1.05, .5, .5)), (8, (1.3, .45, .6)), (d, (1.0, .5, .5))]), k2=12, mix=mix)
    if t < 3.2:
        place(fr, chip("Seperti babak 1 …", size=16, bg=INK, fg="white", fnt=F_SANS_B), PX + 20, PY + 24, anchor=(0, 0), alpha=1 - fade(t, 2.6, .5))
    header(fr, "12", "Makan tengah hari berikutnya", None, t)
    ta = L["s12a"][0]
    speaker_card(fr, "amir", "“Sedikit dahulu. Kalau perlu, saya tambah.”", RX, PY + 30, t, ta, size=21)
    sticky(fr, chip("Sara merekod pemerhatian", size=16, bg=COL["sara"], fg="white", fnt=F_SANS_B, dot=(255, 255, 255)), RX, PY + 150, t, ta + 3.0, anchor=(0, 0))
    sticky(fr, chip("Ju memerhati", size=16, bg=COL["ju"], fg="white", fnt=F_SANS_B, dot=(255, 255, 255)), RX + 270, PY + 150, t, ta + 3.6, anchor=(0, 0))
    tb = L["s12b"][0]
    steps = [("Fahami hubungan", "cart"), ("Pertimbang kesan", "question"), ("Bertindak bersama", "people"), ("Semak & tambah baik", "chart")]
    for i, (s_, ic) in enumerate(steps):
        t0 = tb + [0.3, 2.6, 5.0, L["s12c"][0] - tb][i]
        sticky(fr, card(s_, RW, size=21, icon_name=ic, h=66), RX, PY + 215 + i * 80, t, t0, anchor=(0, 0))


def sc_question(fr, t, d, L):
    place(fr, icon("plate", 120), W / 2, 170, scale=pop(t, 0.2))
    f = font(F_SERIF_B, 46); lines = ["Di kampus anda, apakah satu masalah", "yang boleh disiasat dan", "ditambah baik bersama?"]
    for i, ln in enumerate(lines):
        u = ease_out(seg(t, 0.6 + i * 0.5, 1.4 + i * 0.5))
        tw = tsize(ln, f)[0]
        im = Image.new("RGBA", (tw + 20, 70), (0, 0, 0, 0)); ImageDraw.Draw(im).text((10, 0), ln, font=f, fill=INK)
        place(fr, im, W / 2, 300 + i * 70 + (1 - u) * 20, alpha=u)
    sticky(fr, chip("Bincangkan bersama kumpulan anda", size=20, bg=COL["amir"], fg="white", fnt=F_SANS_B), W / 2, 560, t, 5.0)


def sc_credits(fr, t, d, L):
    f = font(F_SERIF_B, 40); s = "Selepas Pinggan Ditinggalkan"; tw = tsize(s, f)[0]
    im = Image.new("RGBA", (tw + 20, 60), (0, 0, 0, 0)); ImageDraw.Draw(im).text((10, 0), s, font=f, fill=INK)
    place(fr, im, W / 2, 200, alpha=fade(t, 0.2))
    rows = ["Video pendidikan ESD untuk pelajar pengajian tinggi Malaysia",
            "Visual: papan cerita & helaian watak yang diluluskan · Animasi grafik: dijana dengan kod",
            "Suara: TTS luar talian (espeak-ng + MBROLA)",
            "Muzik & kesan bunyi: gubahan asal, disintesis — bebas hak cipta",
            "Contoh dalam video adalah ilustrasi; tiada statistik atau pemetaan rasmi dicipta."]
    for i, r_ in enumerate(rows):
        c = chip(r_, size=18 if i else 20, bg=CREAM, fg=INK if i == 0 else MUTED, fnt=F_SANS_B if i == 0 else F_SANS)
        place(fr, c, W / 2, 290 + i * 48, alpha=fade(t, 0.6 + i * 0.3))
    for i, n in enumerate(("ju", "amir", "sara", "lina")):
        place(fr, face(n, 64), W / 2 + (i - 1.5) * 90, 580, scale=pop(t, 1.8 + i * 0.2))


# ================================================================ timeline
def S(fn, lines, minimum, tail=2.0, amb=1.0, sub=True):
    """lines: [(key, start or None, gap)] -> absolute local starts; duration = max(minimum, last end + tail)."""
    L, cur = {}, 0.0
    for key, st, gap in lines:
        s = st if st is not None else cur + gap
        L[key] = (s, s + META[key]["dur"]); cur = L[key][1]
    return dict(fn=fn, L=L, d=max(minimum, cur + tail), amb=amb, sub=sub)


SCENES = [
    S(sc_title, [("t00", 1.2, 0)], 7.0, amb=0.0, sub=False),
    S(sc01, [("s01a", 7.0, 0)], 20.0),
    S(sc02, [("s02a", 2.2, 0), ("s02b", None, 1.4)], 25.0),
    S(sc03, [("s03n", 0.6, 0), ("s03a", 14.2, 0), ("s03b", None, 0.7)], 30.0),
    S(sc04, [("s04n", 0.6, 0), ("s04a", 2.8, 0), ("s04b", 5.4, 0), ("s04c", 9.2, 0)], 25.0, amb=0.25),
    S(sc05, [("s05n", 0.6, 0), ("s05a", 3.0, 0), ("s05b", None, 1.4), ("s05c", None, 1.4)], 30.0),
    S(sc06, [("s06n", 0.6, 0), ("s06a", 3.0, 0), ("s06b", None, 1.3)], 25.0),
    S(sc07, [("s07n", 0.6, 0), ("s07a", 3.0, 0), ("s07b", None, 1.2), ("s07c", None, 0.4)], 25.0),
    S(sc08, [("s08n", 0.6, 0), ("s08a", 5.5, 0)], 20.0, amb=0.6),
    S(sc09, [("s09n", 0.6, 0), ("s09a", 3.0, 0), ("s09b", None, 0.6)], 35.0),
    S(sc10, [("s10n", 0.6, 0), ("s10a", 3.4, 0), ("s10b", None, 2.0)], 35.0),
    S(sc11, [("s11a", 2.0, 0), ("s11b", None, 0.5), ("s11c", 21.0, 0), ("s11d", None, 0.3)], 35.0, amb=0.3),
    S(sc12, [("s12a", 3.0, 0), ("s12b", None, 2.0), ("s12c", None, 0.8)], 25.0, tail=2.5),
    S(sc_question, [("s12q", 0.8, 0)], 10.0, amb=0.0, sub=False),
    S(sc_credits, [], 7.0, amb=0.0),
]
STARTS = [0.0]
for sc in SCENES[:-1]: STARTS.append(STARTS[-1] + sc["d"])
TOTAL = STARTS[-1] + SCENES[-1]["d"]


# ================================================================ captions
_ENV = {}
def envelope(key):
    if key not in _ENV:
        sr, x = wavfile.read(f"{AUD}/{key}_raw.wav"); x = x.astype(np.float32); x /= np.abs(x).max() + 1e-9
        hop = sr // FPS
        e = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x), hop)])
        _ENV[key] = np.clip(e / (np.percentile(e, 95) + 1e-9), 0, 1)
    return _ENV[key]


def subtitles(fr, sc, t):
    if not sc["sub"]: return
    for key, (a, b) in sc["L"].items():
        if a - 0.15 <= t <= b + 0.5:
            m = META[key]; spk = m["speaker"]
            al = fade(t, a - 0.15, 0.25) * (1 - fade(t, b + 0.25, 0.25))
            f = font(F_SANS_B, 25); fn = font(F_SANS_B, 18)
            text = m["caption"]; lines = wrap(text, f, 1000)
            bw, bh = 1184, 20 + 34 * len(lines)
            bar = rrect(bw, bh, (34, 28, 26, 215), r=16); o = ImageDraw.Draw(bar)
            x0 = 24
            if spk != "nar": x0 = 96
            bar2 = Image.new("RGBA", (bw, bh + 24), (0, 0, 0, 0)); bar2.alpha_composite(bar, (0, 24))
            o = ImageDraw.Draw(bar2)
            o.rounded_rectangle((x0 - 10, 8, x0 + tsize(m["name"].upper() if spk != "nar" else "NARATOR", fn)[0] + 12, 34), 10,
                                fill=COL[spk])
            o.text((x0, 9), m["name"].upper() if spk != "nar" else "NARATOR", font=fn, fill="white")
            for i, ln in enumerate(lines):
                o.text((x0, 38 + i * 34), ln, font=f, fill=(255, 250, 240))
            place(fr, bar2, W / 2, H - 14, alpha=al, anchor=(0.5, 1))
            if spk != "nar":
                e = envelope(key); i = int((t - a) * FPS)
                v = float(e[i]) if 0 <= i < len(e) else 0.0
                place(fr, face(spk, 64), 48 + 12 + 34, H - 14 - (bh + 24) + 34 + 2 - v * 4, alpha=al, scale=1 + 0.04 * v)


def render_at(T):
    i = max(k for k in range(len(SCENES)) if STARTS[k] <= T + 1e-9)
    t = T - STARTS[i]
    fr = draw_scene(i, t)
    if i > 0 and t < XF:
        prev = draw_scene(i - 1, SCENES[i - 1]["d"] - 0.001)
        fr = Image.blend(prev, fr, ease(t / XF))
    if T > TOTAL - 1.0:
        fr = Image.blend(fr, Image.new("RGBA", (W, H), (0, 0, 0, 255)), ease((T - (TOTAL - 1.0)) / 1.0))
    return fr.convert("RGB")


def draw_scene(i, t):
    sc = SCENES[i]; fr = backdrop().copy()
    sc["fn"](fr, t, sc["d"], sc["L"])
    subtitles(fr, sc, t)
    return fr


def _frame_bytes(f): return render_at(f / FPS).tobytes()


# ================================================================ audio
def load_vo(key):
    sr, x = wavfile.read(f"{AUD}/{key}_raw.wav"); x = x.astype(np.float32); x /= np.abs(x).max() + 1e-9
    x = resample_poly(x, SR, sr).astype(np.float32)
    rng = np.random.default_rng(1)
    ir = rng.normal(0, 1, int(SR * 0.16)) * np.exp(-np.arange(int(SR * 0.16)) / (SR * 0.035))
    wet = np.convolve(x, ir)[:len(x)]; wet /= np.abs(wet).max() + 1e-9
    y = x * 0.9 + wet * 0.1
    g = 0.7 if key == "s08a" else 0.92
    return y / (np.abs(y).max() + 1e-9) * g


def ambience(n):
    """cafeteria: murmur (band-limited noise with slow syllabic modulation) + random cutlery clinks."""
    rng = np.random.default_rng(11)
    x = rng.normal(0, 1, n).astype(np.float32)
    x = lfilter([0.02], [1, -0.98], x); x = x - lfilter([0.05], [1, -0.95], x)
    mod = np.zeros(n, np.float32)
    for k in range(6):
        f = rng.uniform(2.5, 5.5); ph = rng.uniform(0, 6.28)
        mod += 0.5 + 0.5 * np.sin(2 * np.pi * f * np.arange(n) / SR + ph)
    x = x * (mod / 6); x /= np.abs(x).max() + 1e-9
    y = x * 0.35
    t = np.arange(int(SR * 0.25)) / SR
    for _ in range(int(n / SR * 0.9)):
        i = rng.integers(0, n - len(t)); f = rng.uniform(2200, 4200)
        c = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.51 * t)) * np.exp(-t * rng.uniform(25, 45))
        y[i:i + len(t)] += c * rng.uniform(0.04, 0.12)
    return y


def build_audio(path):
    n = int(SR * TOTAL) + SR
    vo = np.zeros(n, np.float32); amb_env = np.zeros(n, np.float32)
    subs = []
    for i, sc in enumerate(SCENES):
        a0, a1 = int(STARTS[i] * SR), int((STARTS[i] + sc["d"]) * SR)
        amb_env[a0:a1] = sc["amb"]
        for key, (s, e) in sc["L"].items():
            x = load_vo(key); a = int((STARTS[i] + s) * SR)
            vo[a:a + len(x)] += x[:n - a]
            if sc["sub"] or key == "s12q": subs.append((STARTS[i] + s, STARTS[i] + e, META[key]["caption"]))
    k = int(SR * 1.0); amb_env = np.convolve(amb_env, np.ones(k) / k, "same")
    amb = ambience(n) * amb_env
    mp = f"{BUILD}/music.wav"
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "music.py"), str(TOTAL), mp], check=True)
    sr, mus = wavfile.read(mp); mus = mus.astype(np.float32)
    mus = np.pad(mus, ((0, max(0, n - len(mus))), (0, 0)))[:n]
    act = (np.abs(vo) > 0.02).astype(np.float32)
    k = int(SR * 0.3); act = np.convolve(act, np.ones(k) / k, "same")
    duck = 1 - 0.7 * np.clip(act * 3, 0, 1)
    mix = mus * (0.42 * duck)[:, None] + (vo * 0.95)[:, None] + (amb * 0.22)[:, None]
    mix /= max(1.0, np.abs(mix).max() / 0.97)
    wavfile.write(path, SR, mix.astype(np.float32))
    return sorted(subs)


def srt(subs, path):
    def ts(s):
        ms = int(round(s * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s_, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s_:02d},{ms:03d}"
    with open(path, "w") as f:
        for i, (a, b, txt) in enumerate(subs, 1): f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{txt}\n\n")


def main():
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    wav = f"{BUILD}/mix.wav"
    subs = build_audio(wav); srt(subs, f"{BUILD}/pinggan.srt")
    nf = int(TOTAL * FPS)
    print(f"total {TOTAL:.1f}s, {nf} frames", flush=True)
    out = f"{BUILD}/pinggan.mp4"
    p = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out],
                         stdin=subprocess.PIPE)
    with Pool(4) as pool:
        for i, b in enumerate(pool.imap(_frame_bytes, range(nf), chunksize=8)):
            p.stdin.write(b)
            if i % 500 == 0: print(f"frame {i}/{nf}", flush=True)
    p.stdin.close(); p.wait()
    print("done", out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--still":
        s, lt = int(sys.argv[2]), float(sys.argv[3])
        render_at(STARTS[s] + lt).save(sys.argv[4] if len(sys.argv) > 4 else f"{BUILD}/still.png")
    elif len(sys.argv) > 1 and sys.argv[1] == "--sheet":
        ims = []
        fr_ = [float(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else (0.3, 0.6, 0.95)
        for s in range(len(SCENES)):
            for u in fr_: ims.append(render_at(STARTS[s] + u * SCENES[s]["d"]).resize((426, 240)))
        cols = len(fr_) * 2; rows = (len(ims) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 426, rows * 240), "white")
        for k, im in enumerate(ims): sheet.paste(im, ((k % cols) * 426, (k // cols) * 240))
        sheet.save(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "--times":
        for i, sc in enumerate(SCENES): print(i, sc["fn"].__name__, round(STARTS[i], 1), round(sc["d"], 1))
        print("TOTAL", round(TOTAL, 1))
    else:
        main()
