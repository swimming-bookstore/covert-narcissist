#!/usr/bin/env python3
"""Vertical English reels — one ~8s Q&A clip per covert-narcissist trait."""

import math
import os
import shutil
import subprocess
import tempfile

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo

W, H = 1080, 1920
FPS = 30
DUR = 8.0
OUTDIR = os.path.dirname(os.path.abspath(__file__))

BG = (0.97, 0.94, 0.90)
INK = (0.16, 0.11, 0.12)
ROSE = (0.78, 0.22, 0.30)
YELLOW = (0.96, 0.76, 0.12)

# num, slug, name, question, answer words (text, keyword), label
TRAITS = [
    (
        "01",
        "entitlement",
        "Entitlement",
        "What is entitlement?",
        [("They", False), ("think", True), ("they're", False), ("superior", True)],
    ),
    (
        "02",
        "withdraw",
        "Withdraw",
        "What is withdraw?",
        [("No show", True), ("or just", False), ("quiet", True)],
    ),
    (
        "03",
        "triangulation",
        "Triangulation",
        "What is triangulation?",
        [("They pull a", False), ("third", True), ("person in", False)],
        "TACTIC",
    ),
    (
        "04",
        "gaslighting",
        "Gaslighting",
        "What is gaslighting?",
        [("They make you", False), ("doubt", True), ("yourself", False)],
        "TACTIC",
    ),
]


def rgb(ctx, c, a=1.0):
    ctx.set_source_rgba(*c, a)


def round_rect(ctx, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()


def layout(ctx, text, size, weight="bold", width=None, align="left", font="Lato"):
    lay = PangoCairo.create_layout(ctx)
    fd = Pango.FontDescription()
    fd.set_family(font)
    fd.set_absolute_size(size * Pango.SCALE)
    fd.set_weight(Pango.Weight.BOLD if weight == "bold" else Pango.Weight.NORMAL)
    lay.set_font_description(fd)
    if width:
        lay.set_width(int(width * Pango.SCALE))
        lay.set_alignment(
            {"left": Pango.Alignment.LEFT, "center": Pango.Alignment.CENTER, "right": Pango.Alignment.RIGHT}[align]
        )
    lay.set_text(text, -1)
    return lay


def show(ctx, text, x, y, size, weight="bold", color=INK, width=None, align="left", font="Lato"):
    lay = layout(ctx, text, size, weight, width, align, font)
    rgb(ctx, color)
    ctx.move_to(x, y)
    PangoCairo.show_layout(ctx, lay)
    return lay.get_pixel_size()


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def pop(t):
    """Scale that overshoots, then settles. Karaoke pop."""
    t = max(0.0, min(1.0, t))
    c1 = 1.4
    c3 = c1 + 1
    return max(0.05, 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2)


def bg(ctx, t):
    rgb(ctx, BG)
    ctx.paint()
    for i, col, rad, a in (
        (0, (0.96, 0.78, 0.72), 640, 0.85),
        (1, (0.98, 0.88, 0.62), 520, 0.55),
        (2, (0.90, 0.72, 0.74), 420, 0.40),
    ):
        cx = 160 + i * 380 + math.sin(t * 0.55 + i) * 36
        cy = 280 + i * 620 + math.cos(t * 0.4 + i) * 28
        g = cairo.RadialGradient(cx, cy, 20, cx, cy, rad)
        g.add_color_stop_rgba(0, *col, a)
        g.add_color_stop_rgba(1, *col, 0)
        ctx.set_source(g)
        ctx.paint()


def draw(ctx, trait, t):
    _num, _slug, _title, question, words = trait[:5]
    label = trait[5] if len(trait) > 5 else "TRAIT"
    bg(ctx, t)

    k = ease(t / 0.25) if t < 0.25 else 1.0
    ctx.push_group()
    show(ctx, f"COVERT NARCISSIST {label}", 0, 150, 34, "bold", ROSE, width=W, align="center")

    # Question stays put. The answer pops in underneath, word by word.
    q_x, q_y, q_w, q_size = (W - 940) / 2, 430, 940, 84
    q_lay = layout(ctx, question, q_size, "bold", q_w, "center")

    # Yellow box behind the named word in the question (same idea as answer keywords).
    named = trait[1]
    if named and named in question.lower():
        start = question.lower().index(named)
        # index_to_pos is the real glyph box; prefix width is not, because of kerning.
        p0 = q_lay.index_to_pos(start)
        p1 = q_lay.index_to_pos(start + len(named))
        ux = q_x + min(p0.x, p1.x) / Pango.SCALE
        uy = q_y + p0.y / Pango.SCALE
        ww = abs(p1.x - p0.x) / Pango.SCALE
        wh = p0.height / Pango.SCALE
        pad_x, pad_y = 10, 4
        rgb(ctx, YELLOW, 0.72)
        round_rect(ctx, ux - pad_x, uy - pad_y, ww + pad_x * 2, wh + pad_y * 2, 16)
        ctx.fill()

    rgb(ctx, INK)
    ctx.move_to(q_x, q_y)
    PangoCairo.show_layout(ctx, q_lay)

    # One word per row, gaps big enough that a pop never hits the word above.
    n_words = len(words)
    starts = [2.6 + i * (3.0 / max(1, n_words - 1)) for i in range(n_words)]
    sized = []
    for text, key in words:
        size = 150 if key else 96
        label = text.upper() if key else text
        tw, th = layout(ctx, label, size, "bold").get_pixel_size()
        sized.append((label, key, size, tw, th))
    gap = 70
    total_h = sum(s[4] for s in sized) + gap * (len(sized) - 1)
    y = 720 + max(0, (900 - total_h) / 2)
    for (label, key, size, tw, th), start in zip(sized, starts):
        if t >= start:
            u = min(1.0, (t - start) / 0.42)
            sc = pop(u)
            ctx.save()
            ctx.translate(W / 2, y + th / 2)
            ctx.scale(sc, sc)
            ctx.translate(-tw / 2, -th / 2)
            if key:
                rgb(ctx, ROSE, 0.14)
                round_rect(ctx, -36, -16, tw + 72, th + 32, 28)
                ctx.fill()
            rgb(ctx, ROSE if key else INK)
            ctx.move_to(0, 0)
            PangoCairo.show_layout(ctx, layout(ctx, label, size, "bold"))
            ctx.restore()
        y += th + gap

    ctx.pop_group_to_source()
    ctx.paint_with_alpha(k)


def render(trait):
    num, slug = trait[0], trait[1]
    label = (trait[5] if len(trait) > 5 else "TRAIT").lower()
    tmp = tempfile.mkdtemp(prefix="reel_")
    try:
        n = int(round(DUR * FPS))
        for i in range(n):
            surface = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
            ctx = cairo.Context(surface)
            draw(ctx, trait, i / FPS)
            surface.write_to_png(os.path.join(tmp, f"f{i:04d}.png"))
        out = os.path.join(OUTDIR, f"reel_{num}_{label}_{slug}.mp4")
        subprocess.check_call(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-framerate", str(FPS),
                "-i", os.path.join(tmp, "f%04d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", "-crf", "20",
                "-preset", "veryfast",
                out,
            ]
        )
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    only = os.environ.get("ONLY")
    for trait in TRAITS:
        if only and trait[0] != only and trait[1] != only:
            continue
        print("wrote", render(trait), flush=True)


if __name__ == "__main__":
    main()
