#!/usr/bin/env python3
"""Render a vertical (9:16) GTA VI daily countdown reel as an MP4.

Usage:
    python3 make_reel.py                    # today's reel -> out/gta6-countdown-YYYY-MM-DD.mp4
    python3 make_reel.py --date 2026-11-01  # render for a specific day
    python3 make_reel.py --no-audio

Needs Pillow, numpy and ffmpeg on PATH.
"""
import argparse
import datetime as dt
import math
import os
import subprocess
import wave
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

RELEASE = dt.date(2026, 11, 19)
TZ = ZoneInfo("America/New_York")

W, H = 1080, 1920
FPS = 30
DURATION = 8.0
N_FRAMES = int(FPS * DURATION)
HORIZON = 1180

FONT_DIRS = ["/usr/share/fonts/opentype/inter", "/usr/share/fonts/truetype/dejavu"]


def font(name, size):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.truetype("DejaVuSans-Bold.ttf", size)


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out_cubic(t):
    return 1 - (1 - clamp(t)) ** 3


def ease_out_back(t, s=1.7):
    t = clamp(t) - 1
    return t * t * ((s + 1) * t + s) + 1


def phase(t, start, length):
    return clamp((t - start) / length)


# ---------------------------------------------------------------- background

def lerp_color(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def build_sky():
    stops = [(0.0, (12, 6, 34)), (0.35, (58, 14, 92)), (0.55, (176, 32, 120)),
             (0.68, (255, 94, 98)), (HORIZON / H, (255, 170, 80))]
    sky = np.zeros((H, W, 3), dtype=np.uint8)
    for y in range(HORIZON):
        f = y / H
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= f <= p1:
                sky[y, :] = lerp_color(c0, c1, (f - p0) / (p1 - p0))
                break
    sky[HORIZON:, :] = (14, 4, 30)
    img = Image.fromarray(sky)

    # stars in the upper sky
    rng = np.random.default_rng(6)
    d = ImageDraw.Draw(img)
    for _ in range(140):
        x, y = rng.integers(0, W), rng.integers(0, 620)
        r = rng.choice([1, 1, 1, 2])
        a = int(rng.integers(120, 255))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(a, a, a))
    return img


def draw_sun(img, t):
    cx, cy, r = W // 2, HORIZON - 150, 330
    sun = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sun)
    for y in range(cy - r, HORIZON):
        dy = y - cy
        if abs(dy) > r:
            continue
        half = int(math.sqrt(r * r - dy * dy))
        f = (y - (cy - r)) / (2 * r)
        col = lerp_color((255, 230, 90), (255, 40, 140), f)
        sd.line([(cx - half, y), (cx + half, y)], fill=col + (255,))
    # scrolling retro stripes cut into the lower half of the sun
    off = (t * 40) % 60
    for i in range(10):
        y0 = cy + 20 + i * 15 * (1 + i * 0.12) + off * (i + 1) / 20
        gap = 4 + i * 2.2
        sd.rectangle([cx - r, y0, cx + r, y0 + gap], fill=(0, 0, 0, 0))
    glow = sun.filter(ImageFilter.GaussianBlur(60))
    img.alpha_composite(glow)
    img.alpha_composite(sun)


def draw_grid(img, t):
    d = ImageDraw.Draw(img)
    floor_h = H - HORIZON
    col = (255, 60, 200, 255)
    # horizontal lines rushing toward the viewer
    speed = 0.9
    for i in range(18):
        z = ((i + (t * speed) % 1.0) / 18)
        y = HORIZON + floor_h * (z ** 2.4)
        w = max(1, int(1 + 4 * z))
        d.line([(0, y), (W, y)], fill=col, width=w)
    # vanishing lines
    vx = W // 2
    for k in range(-14, 15):
        x_bottom = vx + k * 170
        d.line([(vx + k * 8, HORIZON), (x_bottom, H)], fill=col, width=2)
    d.line([(0, HORIZON), (W, HORIZON)], fill=(255, 200, 120, 255), width=3)


def palm(d, base_x, base_y, height, flip=1):
    """Simple palm-tree silhouette."""
    col = (10, 2, 22, 255)
    pts = []
    for i in range(21):
        f = i / 20
        x = base_x + flip * (40 * math.sin(f * 1.6)) * f * 2.2
        y = base_y - height * f
        pts.append((x, y))
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        w = int(26 - 14 * (y0 - base_y) / -height)
        d.line([(x0, y0), (x1, y1)], fill=col, width=w)
    tx, ty = pts[-1]
    for ang in (-170, -140, -110, -70, -40, -10, 20, 200):
        a = math.radians(ang)
        frond = []
        for j in range(12):
            f = j / 11
            fx = tx + math.cos(a) * 230 * f
            fy = ty + math.sin(a) * 230 * f + 140 * f * f
            frond.append((fx, fy))
        for j, ((x0, y0), (x1, y1)) in enumerate(zip(frond, frond[1:])):
            d.line([(x0, y0), (x1, y1)], fill=col, width=max(4, 26 - j * 2))


# ---------------------------------------------------------------- text helpers

def text_layer(text, fnt, fill, glow_col=None, glow_r=18, tracking=0, stroke=0, stroke_fill=(30, 6, 50)):
    """Return an RGBA image of `text` with an optional neon glow."""
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    if tracking:
        widths = [tmp.textlength(ch, font=fnt) for ch in text]
        tw = int(sum(widths) + tracking * (len(text) - 1))
    else:
        tw = int(tmp.textlength(text, font=fnt))
    asc, desc = fnt.getmetrics()
    pad = (glow_r * 3 if glow_col else 4) + stroke
    layer = Image.new("RGBA", (tw + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if tracking:
        x = pad
        for ch, cw in zip(text, widths):
            d.text((x, pad), ch, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
            x += cw + tracking
    else:
        d.text((pad, pad), text, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    if glow_col:
        alpha = layer.split()[3]
        g = Image.new("RGBA", layer.size, glow_col + (0,))
        g.putalpha(alpha)
        g = g.filter(ImageFilter.GaussianBlur(glow_r))
        out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        out.alpha_composite(g)
        out.alpha_composite(g)
        out.alpha_composite(layer)
        layer = out
    return layer


def place(frame, layer, cx, cy, scale=1.0, alpha=1.0):
    if alpha <= 0 or scale <= 0:
        return
    if scale != 1.0:
        layer = layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))),
                             Image.LANCZOS)
    if alpha < 1.0:
        a = layer.split()[3].point(lambda v: int(v * alpha))
        layer = layer.copy()
        layer.putalpha(a)
    frame.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))


# ---------------------------------------------------------------- render

def render(days, today, out_path, audio=True):
    sky = build_sky().convert("RGBA")
    palms = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(palms)
    palm(pd, 90, HORIZON + 60, 620, flip=1)
    palm(pd, W - 70, HORIZON + 80, 520, flip=-1)

    f_kicker = font("Inter-ExtraBold.otf", 64)
    f_num = font("InterDisplay-Black.otf", 520) if os.path.exists(
        "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf") else font("Inter-Black.otf", 520)
    f_unit = font("Inter-ExtraBold.otf", 96)
    f_title = font("InterDisplay-Black.otf", 150) if os.path.exists(
        "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf") else font("Inter-Black.otf", 150)
    f_small = font("Inter-SemiBold.otf", 46)

    pink, cyan, white, gold = (255, 70, 190), (60, 230, 255), (255, 255, 255), (255, 210, 110)

    if days > 1:
        kicker, unit = "ONLY", "DAYS TO GO"
    elif days == 1:
        kicker, unit = "TOMORROW", "DAY TO GO"
    else:
        kicker, unit = "IT'S", "LAUNCH DAY"

    L_kicker = text_layer(kicker, f_kicker, white, pink, 14, tracking=18)
    L_unit = text_layer(unit, f_unit, white, pink, 16, tracking=10, stroke=4)
    L_title = text_layer("GTA VI", f_title, gold, pink, 22, tracking=8, stroke=7)
    L_date = text_layer(RELEASE.strftime("%b %d, %Y").upper(), f_small, cyan, cyan, 10, tracking=8, stroke=3)
    L_foot = text_layer("FOLLOW FOR THE DAILY COUNTDOWN", f_small, white, None, tracking=4)
    L_today = text_layer(today.strftime("%A · %b %d").upper(), f_small, (230, 200, 255), None, tracking=4)
    num_cache = {}

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    video_tmp = out_path + ".video.mp4"
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", video_tmp],
        stdin=subprocess.PIPE)

    for i in range(N_FRAMES):
        t = i / FPS
        frame = sky.copy()
        draw_sun(frame, t)
        draw_grid(frame, t)
        frame.alpha_composite(palms)

        # kicker
        p = ease_out_cubic(phase(t, 0.2, 0.5))
        place(frame, L_today, W / 2, 150, alpha=ease_out_cubic(phase(t, 0.0, 0.6)))
        place(frame, L_kicker, W / 2, 300 - 40 * (1 - p), alpha=p)

        # number: rolls up from 0, then punches in
        if days > 0:
            roll = ease_out_cubic(phase(t, 0.5, 1.6))
            n = int(round(days * roll))
            if n not in num_cache:
                num_cache[n] = text_layer(str(n), f_num, white, cyan, 30)
            punch = 1.0
            if t >= 2.1:
                punch = 1.0 + 0.12 * math.exp(-(t - 2.1) * 6) * math.cos((t - 2.1) * 18)
            breath = 1.0 + 0.015 * math.sin(t * 4) if t > 3 else 1.0
            place(frame, num_cache[n], W / 2, 640,
                  scale=(0.6 + 0.4 * ease_out_back(phase(t, 0.5, 0.6))) * punch * breath,
                  alpha=ease_out_cubic(phase(t, 0.5, 0.3)))

        # unit + title
        pu = ease_out_back(phase(t, 2.2, 0.5))
        place(frame, L_unit, W / 2, 960, scale=max(0.01, pu), alpha=clamp(pu))
        pt = ease_out_cubic(phase(t, 2.8, 0.6))
        place(frame, L_title, W / 2, 1110 + 60 * (1 - pt), alpha=pt)
        place(frame, L_date, W / 2, 1250, alpha=ease_out_cubic(phase(t, 3.3, 0.6)))

        # footer
        pf = ease_out_cubic(phase(t, 4.0, 0.6))
        place(frame, L_foot, W / 2, H - 170 + 30 * (1 - pf), alpha=pf)

        # flash on the punch + fade at the end
        flash = math.exp(-max(0.0, t - 2.1) * 10) if t >= 2.1 else 0
        fade = clamp((t - (DURATION - 0.5)) / 0.5)
        rgb = np.asarray(frame.convert("RGB"), dtype=np.float32)
        if flash > 0.01:
            rgb = rgb + (255 - rgb) * flash * 0.5
        if fade > 0:
            rgb = rgb * (1 - fade)
        proc.stdin.write(rgb.astype(np.uint8).tobytes())

    proc.stdin.close()
    proc.wait()

    if audio:
        wav = out_path + ".wav"
        make_audio(wav)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video_tmp, "-i", wav,
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out_path],
                       check=True)
        os.remove(wav)
        os.remove(video_tmp)
    else:
        os.replace(video_tmp, out_path)


# ---------------------------------------------------------------- audio

def make_audio(path, sr=44100):
    """Synthesize a short synthwave-ish beat: kick, bass, pad, riser and impact."""
    n = int(sr * DURATION)
    t = np.arange(n) / sr
    out = np.zeros(n)
    bpm = 112
    beat = 60 / bpm

    # pad chord (Am - F) with slow attack
    def chord(freqs, start, length, vol):
        s, e = int(start * sr), min(n, int((start + length) * sr))
        tt = t[s:e] - start
        env = np.minimum(1, tt / 0.6) * np.minimum(1, (length - tt) / 0.6)
        sig = sum(np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * f * 2.003 * tt) for f in freqs)
        out[s:e] += vol * env * sig / len(freqs)

    chord([220.0, 261.63, 329.63], 0.0, 4.3, 0.12)
    chord([174.61, 220.0, 261.63], 4.3, 3.7, 0.12)

    # riser before the punch
    s, e = int(0.4 * sr), int(2.1 * sr)
    tt = t[s:e] - 0.4
    noise = np.random.default_rng(1).standard_normal(e - s)
    out[s:e] += 0.08 * (tt / tt[-1]) ** 2 * noise

    # kicks + bass from the punch onward
    k = 2.1
    while k < DURATION - 0.3:
        s = int(k * sr)
        L = min(n - s, int(0.35 * sr))
        tt = np.arange(L) / sr
        freq = 50 + 110 * np.exp(-tt * 30)
        out[s:s + L] += 0.7 * np.sin(2 * np.pi * np.cumsum(freq) / sr) * np.exp(-tt * 9)
        bf = 55.0 if k < 4.3 else 43.65
        bl = min(n - s, int(beat * sr))
        bt = np.arange(bl) / sr
        out[s:s + bl] += 0.18 * np.sign(np.sin(2 * np.pi * bf * bt)) * np.exp(-bt * 4)
        k += beat

    # impact on the punch
    s = int(2.1 * sr)
    L = int(1.2 * sr)
    tt = np.arange(L) / sr
    out[s:s + L] += 0.35 * np.random.default_rng(2).standard_normal(L) * np.exp(-tt * 6)

    fade = np.clip((DURATION - t) / 0.6, 0, 1)
    out *= fade
    out /= max(1e-6, np.abs(out).max()) / 0.85
    data = (out * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="render as if today were YYYY-MM-DD (default: today, US Eastern)")
    ap.add_argument("--out", help="output path (default: out/gta6-countdown-<date>.mp4)")
    ap.add_argument("--no-audio", action="store_true")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(TZ).date()
    days = (RELEASE - today).days
    if days < 0:
        raise SystemExit("GTA VI is already out — go play it.")
    out = args.out or f"out/gta6-countdown-{today.isoformat()}.mp4"
    render(days, today, out, audio=not args.no_audio)
    print(f"{days} days to go -> {out}")


if __name__ == "__main__":
    main()
