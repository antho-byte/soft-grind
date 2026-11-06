"""Thumbnail (1280x720) and still (1920x1080) renderer: normal and cyberpunk style."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .brand import COLORS, FONT_DIR


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#"); return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _abril(px: int): return ImageFont.truetype(str(FONT_DIR / "AbrilFatface-Regular.ttf"), px)


def _inter(px: int, italic: bool = False):
    f = ImageFont.truetype(str(FONT_DIR / ("Inter-Italic.ttf" if italic else "Inter.ttf")), px)
    f.set_variation_by_axes([14, 500]); return f


def _orbitron(px: int):
    f = ImageFont.truetype(str(FONT_DIR / "Orbitron.ttf"), px)
    f.set_variation_by_axes([700]); return f


def cover_crop(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    img = img.convert("RGB"); w, h = size
    s = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * s) + 1, round(img.height * s) + 1), Image.LANCZOS)
    l, t = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((l, t, l + w, t + h))


def image_warnings(img: Image.Image) -> list[str]:
    out = []
    if img.width < 1920: out.append(f"Image is {img.width}px wide; the brand needs >= 1920px.")
    if abs(img.width / img.height - 16 / 9) > 0.02: out.append("Image is not 16:9; it will be centre-cropped.")
    return out


# ---------- logo ----------
def _bright_share(region: Image.Image) -> float:
    lum = np.asarray(region.convert("L"))
    return float((lum > 190).mean())


def draw_logo(img: Image.Image, mode: str = "auto") -> Image.Image:
    """'soft grind.' bottom-left, ~64px margin and ~60px tall at 1080p. Coral full stop, always."""
    sc = img.height / 1080
    font = _abril(round(72 * sc))
    word, dot = "soft grind", "."
    wb, db = font.getbbox(word), font.getbbox(dot)
    x0 = round(64 * sc)
    w = font.getlength(word) + font.getlength(dot)
    asc, desc = font.getmetrics()
    h = asc + desc
    y0 = img.height - round(64 * sc) - h
    region = img.crop((x0, y0, round(x0 + w), y0 + h))
    bright = _bright_share(region) > 0.35 if mode == "auto" else mode == "navy"
    col = _rgb(COLORS["night_indigo"] if bright else "#ffffff")
    d = ImageDraw.Draw(img)
    d.text((x0, y0), word, font=font, fill=col)
    d.text((x0 + font.getlength(word), y0), dot, font=font, fill=_rgb(COLORS["coral"]))
    return img


# ---------- headline ----------
def split_lines(quote: str) -> list[str]:
    words = quote.split()
    if len(words) <= 2: return [" ".join(words)]
    best, bw = None, 1e9
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if abs(len(a) - len(b)) < bw: bw, best = abs(len(a) - len(b)), [a, b]
    return best


def check_quote(q: str) -> list[str]:
    out = []
    if q != q.lower(): out.append("quote should be lowercase.")
    if not q.strip().endswith((".", "?")): out.append('quote should end with "." or "?".')
    if len(q.split()) > 3: out.append("more than 3 words; keep it short.")
    return out


@dataclass
class Layout:
    anchor: str = "top-center"  # top-left | top-center | top-right | center | bottom-right
    size: float = 1.5           # multiplier on base size (the house style: big)
    dx: int = 0                # fine offsets, px at 1080p scale
    dy: int = 0


def _text_box(lines, font, line_gap):
    ws = [font.getlength(l) for l in lines]
    asc, desc = font.getmetrics()
    lh = asc + desc + line_gap
    return max(ws), lh * len(lines) - line_gap, lh, ws


def _anchor_xy(anchor, W, H, bw, bh, margin):
    xs = {"left": margin, "center": (W - bw) / 2, "right": W - bw - margin}
    if anchor == "top-left": return xs["left"], H * 0.10
    if anchor == "top-center": return xs["center"], H * 0.10
    if anchor == "top-right": return xs["right"], H * 0.10
    if anchor == "center": return xs["center"], (H - bh) / 2
    return xs["right"], H * 0.62  # bottom-right


ANCHORS = ["top-left", "top-center", "top-right", "center", "bottom-right"]


def suggest_anchor(img: Image.Image, quote: str) -> str:
    """Pick the calmest area (lowest local detail + low brightness variance) for the headline."""
    small = cover_crop(img, (640, 360)).convert("L")
    arr = np.asarray(small, dtype=float)
    gy, gx = np.gradient(arr)
    detail = np.hypot(gx, gy)
    font = _abril(round(100 * 360 / 1080)); lines = split_lines(quote)
    bw, bh, _, _ = _text_box(lines, font, 4)
    best, score = "top-left", 1e9
    for a in ANCHORS:
        x, y = _anchor_xy(a, 640, 360, bw, bh, 40)
        reg = (slice(int(y), int(y + bh)), slice(int(x), int(x + bw)))
        s = detail[reg].mean() + 0.3 * arr[reg].std() + (0 if a == "top-left" else 1.0)  # slight default bias
        if s < score: best, score = a, s
    return best


def _shadowed(layer_size, draw_fn, sc):
    """Soft shadow per brand: 0 2px 0 rgba(10,12,50,.12), 0 6px 34px rgba(10,12,60,.38)."""
    W, H = layer_size
    out = Image.new("RGBA", layer_size, (0, 0, 0, 0))
    for (dy, blur, rgb, a) in ((2, 0, (10, 12, 50), .12), (6, 34, (10, 12, 60), .38)):
        m = Image.new("L", layer_size, 0)
        draw_fn(ImageDraw.Draw(m), 0, round(dy * sc), 255)
        if blur: m = m.filter(ImageFilter.GaussianBlur(blur * sc / 2))
        m = m.point(lambda v, a=a: int(v * a))
        out.alpha_composite(Image.merge("RGBA", (*[Image.new("L", layer_size, c) for c in rgb], m)))
    return out


# ---------- cyberpunk grade ----------
def cyber_grade(img: Image.Image) -> Image.Image:
    w, h = img.size
    base = img.convert("RGB")
    xs = np.linspace(0, 1, w)[None, :, None]; ys = np.linspace(0, 1, h)[:, None, None]
    t = np.clip((xs * .6 + ys * .4), 0, 1)
    cyan, mag = np.array([0, 220, 255]), np.array([255, 20, 160])
    grad = (cyan * (1 - t) + mag * t).astype(np.uint8)
    grad = np.broadcast_to(grad, (h, w, 3)).copy()
    tint = Image.fromarray(grad)
    out = ImageChops.soft_light(base, tint)
    out = Image.blend(base, out, 0.75)
    out = ImageChops.multiply(out, Image.new("RGB", out.size, (235, 225, 245)))
    scan = Image.new("L", out.size, 0); sd = ImageDraw.Draw(scan)
    for y in range(0, h, max(3, h // 180)): sd.line([(0, y), (w, y)], fill=22)
    return Image.composite(Image.new("RGB", out.size, (0, 0, 20)), out, scan)


def fit_font(lines: list[str], px: int, max_width: float):
    """Abril at `px`, or smaller if the widest line would be wider than `max_width`."""
    font = _abril(px)
    widest = max((font.getlength(l) for l in lines), default=0)
    if widest > max_width > 0:
        font = _abril(max(8, int(px * max_width / widest)))
    return font


# ---------- public renders ----------
def render_still(src: Image.Image, cyber: bool = False, size=(1920, 1080), logo_mode="auto", quote: str | None = None,
                 layout: Layout | None = None, tag: str = "CYBERPUNK SYNTHWAVE", subline: str = "") -> Image.Image:
    """The picture under the music. With a `quote` it is the thumbnail design in full HD (same layout), without it photo + logo."""
    if quote:
        return render_thumbnail(src, quote, layout, cyber, tag, subline, size=size, logo_mode=logo_mode)
    img = cover_crop(src, size)
    if cyber: img = cyber_grade(img)
    return draw_logo(img, logo_mode)


def render_thumbnail(src: Image.Image, quote: str, layout: Layout | None = None, cyber: bool = False,
                     tag: str = "CYBERPUNK SYNTHWAVE", subline: str = "", size=(1280, 720),
                     logo_mode="auto") -> Image.Image:
    layout = layout or Layout()
    W, H = size; sc = H / 1080
    img = cover_crop(src, size)
    if cyber: img = cyber_grade(img)
    img = img.convert("RGBA")

    lines = split_lines(quote.strip())
    gap = round(6 * sc)
    margin = 64 * sc
    font = fit_font(lines, round(150 * sc * layout.size), W - 2 * margin)      # shrinks only if the headline would run off the edge
    bw, bh, lh, ws = _text_box(lines, font, gap)
    x, y = _anchor_xy(layout.anchor, W, H, bw, bh, margin)
    x, y = x + layout.dx * sc, y + layout.dy * sc
    align_right = layout.anchor in ("top-right", "bottom-right")
    center = layout.anchor in ("top-center", "center")

    def line_x(i): return x + (bw - ws[i]) / 2 if center else (x + bw - ws[i] if align_right else x)

    def draw_text(d, ox, oy, fill):
        for i, l in enumerate(lines):
            d.text((line_x(i) + ox, y + i * lh + oy), l, font=font, fill=fill)

    if cyber:  # glitch: magenta (-x) / cyan (+x) offset behind headline
        off = max(3, round(6 * sc))
        for dx, rgb in ((-off, _rgb("#ff2d95")), (off, _rgb("#00e5ff"))):
            lay = Image.new("RGBA", size, (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
            draw_text(ld, dx, 0, rgb + (200,)); img.alpha_composite(lay)
        # yellow tag box above headline
        tf = _orbitron(round(34 * sc)); pad = round(14 * sc)
        tb = tf.getbbox(tag); tw, th = tb[2] - tb[0], tb[3] - tb[1]
        tx = x if not (center or align_right) else (x + (bw - tw - 2 * pad) / 2 if center else x + bw - tw - 2 * pad)
        ty = y - th - 2 * pad - round(18 * sc)
        d = ImageDraw.Draw(img)
        d.rectangle([tx, ty, tx + tw + 2 * pad, ty + th + 2 * pad], fill=_rgb(COLORS["cyber_yellow"]))
        d.text((tx + pad - tb[0], ty + pad - tb[1]), tag, font=tf, fill=_rgb("#0a0a14"))

    img.alpha_composite(_shadowed(size, draw_text, sc))
    d = ImageDraw.Draw(img); draw_text(d, 0, 0, (255, 255, 255, 255))

    if subline:
        sf = _inter(round(40 * sc), italic=True); sy = y + bh + round(16 * sc)
        sw = sf.getlength(subline)
        sx = x + (bw - sw) / 2 if center else (x + bw - sw if align_right else x)
        d.text((sx, sy), subline, font=sf, fill=(255, 255, 255, 235))

    return draw_logo(img.convert("RGB"), logo_mode)
