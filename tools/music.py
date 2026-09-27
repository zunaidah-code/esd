"""Procedurally composed, original cheerful background music (royalty-free: no samples,
every sound is synthesised here). Ukulele-style plucks, bass, glockenspiel melody,
shaker, soft kick and claps. Usage: music.py <seconds> <out.wav>"""
import sys, numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter

SR = 44100
BPM = 116
BEAT = 60.0 / BPM
rng = np.random.default_rng(7)

def midi(n): return 440.0 * 2 ** ((n - 69) / 12)

def pluck(freq, dur, bright=0.5):
    """Karplus-Strong plucked string (ukulele-like)."""
    n = int(SR * dur); p = max(2, int(SR / freq))
    buf = rng.uniform(-1, 1, p)
    buf = lfilter([bright, 1 - bright], [1], buf)
    out = np.empty(n); idx = 0
    for i in range(n):
        v = buf[idx]; nxt = buf[(idx + 1) % p]
        buf[idx] = 0.996 * 0.5 * (v + nxt)
        out[i] = v; idx = (idx + 1) % p
    return out

_pl_cache = {}
def pluck_c(note, dur):
    k = (note, round(dur, 2))
    if k not in _pl_cache: _pl_cache[k] = pluck(midi(note), dur)
    return _pl_cache[k]

def glock(freq, dur):
    t = np.arange(int(SR * dur)) / SR
    env = np.exp(-t * 5.0)
    return env * (np.sin(2*np.pi*freq*t) + 0.35*np.sin(2*np.pi*freq*2.76*t)*np.exp(-t*9)
                  + 0.15*np.sin(2*np.pi*freq*5.4*t)*np.exp(-t*14))

def bass(freq, dur):
    t = np.arange(int(SR * dur)) / SR
    env = np.minimum(1, t / 0.01) * np.exp(-t * 3.0)
    return env * (np.sin(2*np.pi*freq*t) + 0.25*np.sin(4*np.pi*freq*t))

def kick():
    t = np.arange(int(SR * 0.25)) / SR
    f = 50 + 90 * np.exp(-t * 35)
    return np.sin(2*np.pi*np.cumsum(f)/SR) * np.exp(-t * 14)

def hat(dur=0.05, hp=True):
    n = int(SR * dur); x = rng.uniform(-1, 1, n)
    x = x - lfilter([0.3], [1, -0.7], x)
    return x * np.exp(-np.arange(n) / SR * 70)

def clap():
    n = int(SR * 0.18); x = rng.uniform(-1, 1, n)
    x = lfilter([1, -1], [1, -0.4], x)
    t = np.arange(n) / SR
    env = np.exp(-t*25) + 0.6*np.exp(-np.maximum(0, t-0.012)*30)*(t > 0.012)
    return x * env * 0.5

def add(buf, x, t, g=1.0):
    i = int(t * SR)
    if i >= len(buf): return
    j = min(len(buf), i + len(x)); buf[i:j] += g * x[:j - i]

# C  G  Am  F  (I V vi IV) — bright and optimistic
CHORDS = [[60, 64, 67, 72], [59, 62, 67, 71], [57, 60, 64, 69], [57, 60, 65, 69]]
ROOTS = [36, 43, 45, 41]
# 2-bar melodic phrases per chord (beat offset, midi note, length in beats)
MEL_A = [[(0, 76, 1), (1, 79, 1), (2, 76, .5), (2.5, 74, .5), (3, 72, 1)],
         [(0, 74, 1.5), (1.5, 71, .5), (2, 74, 1), (3, 79, 1)],
         [(0, 76, 1), (1, 72, .5), (1.5, 76, .5), (2, 81, 1.5), (3.5, 79, .5)],
         [(0, 77, 1), (1, 76, 1), (2, 74, 1), (3, 72, 1)]]
MEL_B = [[(0, 72, .5), (.5, 74, .5), (1, 76, 1), (2, 79, 1), (3, 84, 1)],
         [(0, 83, 1), (1, 79, 1), (2, 74, 1), (3, 71, 1)],
         [(0, 72, 1), (1, 76, 1), (2, 81, .5), (2.5, 79, .5), (3, 76, 1)],
         [(0, 77, .5), (.5, 76, .5), (1, 74, 1), (2, 72, 2)]]
STRUM = [0, 1, 1.5, 2.5, 3, 3.5]  # island-style strum pattern within a bar

def render(total):
    n = int(SR * (total + 3)); L = np.zeros(n); R = np.zeros(n)
    bar = 4 * BEAT; nbars = int(total / bar) + 1
    for b in range(nbars):
        t0 = b * bar; ci = b % 4; section = (b // 8) % 2
        intro = b < 2; outro = t0 > total - 2 * bar
        # ukulele strums
        for k, off in enumerate(STRUM):
            down = off in (0, 1, 2.5, 3)
            notes = CHORDS[ci] if down else CHORDS[ci][::-1]
            for s, nn in enumerate(notes):
                x = pluck_c(nn, 0.9) * (0.55 if down else 0.38)
                add(L, x, t0 + off*BEAT + s*0.012, 0.16); add(R, x, t0 + off*BEAT + s*0.012, 0.13)
        if not intro:
            # bass
            for off, oct_ in ((0, 0), (1.5, 0), (2, 12), (3, 7)):
                x = bass(midi(ROOTS[ci] + oct_), BEAT*0.9)
                add(L, x, t0 + off*BEAT, 0.28); add(R, x, t0 + off*BEAT, 0.28)
            # drums
            for bt in (0, 2): add(L, kick(), t0 + bt*BEAT, 0.45); add(R, kick(), t0 + bt*BEAT, 0.45)
            for bt in (1, 3): add(L, clap(), t0 + bt*BEAT, 0.22); add(R, clap(), t0 + bt*BEAT, 0.26)
            for e in range(8):
                h = hat(); add(L, h, t0 + e*BEAT/2, 0.05 if e % 2 else 0.08); add(R, h, t0 + e*BEAT/2 + 0.004, 0.07)
        # glockenspiel melody (every other 8 bars gets variation B)
        if not intro and not outro:
            for off, nn, ln in (MEL_B if section else MEL_A)[ci]:
                x = glock(midi(nn), ln*BEAT + 0.6)
                add(L, x, t0 + off*BEAT, 0.09); add(R, x, t0 + off*BEAT + 0.01, 0.11)
    # final resolution chord
    end = total - 1.6
    for s, nn in enumerate([48, 60, 64, 67, 72, 76, 79, 84]):
        x = glock(midi(nn), 3.0) if nn > 70 else pluck_c(nn, 3.0)
        add(L, x, end + s*0.03, 0.12); add(R, x, end + s*0.03, 0.12)
    m = np.stack([L, R], 1)[:int(SR * total)]
    fade = np.ones(len(m)); fl = int(SR * 1.2); fade[-fl:] = np.linspace(1, 0, fl)
    m *= fade[:, None]
    m /= np.abs(m).max() + 1e-9
    return (m * 0.9).astype(np.float32)

if __name__ == "__main__":
    total = float(sys.argv[1]); out = sys.argv[2]
    wavfile.write(out, SR, render(total))
    print("music", total, "s ->", out)
