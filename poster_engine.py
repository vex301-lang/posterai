"""Poster Studio Pro: deterministic high-quality Korean poster composition.

AI creates *artwork only*. Text and supplied photographs are layered locally to
preserve spelling, readability, and fidelity. No font binaries are distributed.
"""
from __future__ import annotations

import io
import math
import os
import random
import textwrap
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

# Rendering canvases favor poster-like ratios and remain comfortably viewable.
SIZES: dict[str, tuple[int, int]] = {
    "A3 세로 · 297×420mm": (1654, 2339),
    "A4 세로 · 210×297mm": (1654, 2339),
    "SNS 세로 · 4:5": (1600, 2000),
    "정사각형 · 1:1": (1800, 1800),
    "스토리 · 9:16": (1440, 2560),
    "가로형 · 3:2": (2048, 1365),
}

PALETTES: dict[str, dict[str, str]] = {
    "autumn": {"paper": "#FFF7E8", "ink": "#402B23", "accent": "#D96237", "accent2": "#E9B75E", "soft": "#F7D8B1", "deep": "#7B4537"},
    "pastel": {"paper": "#FCF7FA", "ink": "#393852", "accent": "#BA77C7", "accent2": "#F0B9C9", "soft": "#E7DCF6", "deep": "#645489"},
    "ocean": {"paper": "#F0F8FA", "ink": "#15374B", "accent": "#007DA4", "accent2": "#E0B86F", "soft": "#CBEAEF", "deep": "#103B60"},
    "forest": {"paper": "#F6F7EB", "ink": "#253C2E", "accent": "#4A765A", "accent2": "#E2A65E", "soft": "#E4ECD9", "deep": "#294E43"},
    "night": {"paper": "#F8F3EA", "ink": "#141B35", "accent": "#283B76", "accent2": "#E5AF63", "soft": "#D8DBF1", "deep": "#202342"},
    "sunshine": {"paper": "#FFFBEA", "ink": "#3C342C", "accent": "#EC793E", "accent2": "#F7CA52", "soft": "#FFE8AE", "deep": "#A64D38"},
    "mono": {"paper": "#F8F7F5", "ink": "#1F2226", "accent": "#323C4E", "accent2": "#A8A9B0", "soft": "#E4E4E7", "deep": "#10131A"},
}

STYLE_LABELS = {"editorial": "01 · 에디토리얼", "festival": "02 · 페스티벌", "gallery": "03 · 갤러리"}


def default_spec(index: int, palette: str = "autumn") -> dict[str, Any]:
    return {
        "layout": ("editorial", "festival", "gallery")[index % 3],
        "palette": palette if palette in PALETTES else "autumn",
        "title_scale": 1.0,
        "photo_scale": 1.0,
        "alignment": "left",
        "photo_style": ("rounded", "polaroid", "framed")[index % 3],
        "background_strength": 0.83,
        "background_note": "",
    }


def rgb(color: str) -> tuple[int, int, int]:
    color = color.removeprefix("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    return (*rgb(color), alpha)


def color_blend(a: str, b: str, fraction: float) -> tuple[int, int, int]:
    ar, ag, ab = rgb(a)
    br, bg, bb = rgb(b)
    return tuple(int(round(x * (1 - fraction) + y * fraction)) for x, y in zip((ar, ag, ab), (br, bg, bb)))


@lru_cache(maxsize=12)
def resolve_font(weight: str = "regular") -> str:
    """Find Korean fonts on Linux. Streamlit packages.txt installs fonts-nanum."""
    candidates = {
        "bold": [
            "/usr/share/fonts/truetype/nanum/NanumSquareEB.ttf",
            "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
        ],
        "regular": [
            "/usr/share/fonts/truetype/nanum/NanumSquareR.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
        ],
    }
    paths = candidates.get(weight, candidates["regular"]) + candidates["regular"] + candidates["bold"]
    for path in paths:
        if Path(path).is_file():
            return path
    search_roots = ["/usr/local/share/fonts", "/usr/share/fonts", str(Path.home() / ".fonts")]
    for root in search_roots:
        base = Path(root)
        if not base.exists():
            continue
        for pattern in ("**/NanumGothic*Bold.ttf" if weight == "bold" else "**/NanumGothic.ttf", "**/NotoSansCJK*.ttc", "**/Nanum*.ttf"):
            match = next(base.glob(pattern), None)
            if match:
                return str(match)
    raise RuntimeError("한글 폰트를 찾을 수 없습니다. packages.txt에 fonts-nanum을 추가하고 앱을 재시작하세요.")


@lru_cache(maxsize=128)
def font_px(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(resolve_font(weight), max(13, int(size)))


def text_len(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> float:
    return draw.textlength(text, font=font)


def wrap_lines(draw: ImageDraw.ImageDraw, raw: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int = 4) -> list[str]:
    result: list[str] = []
    for paragraph in str(raw or "").split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        current = ""
        for chunk in paragraph.split(" "):
            proposed = chunk if not current else current + " " + chunk
            if text_len(draw, proposed, font) <= max_width:
                current = proposed
                continue
            if current:
                result.append(current)
            current = ""
            for ch in chunk:
                if text_len(draw, current + ch, font) > max_width and current:
                    result.append(current)
                    current = ch
                else:
                    current += ch
        if current:
            result.append(current)
    if len(result) > max_lines:
        result = result[:max_lines]
        last = result[-1]
        while last and text_len(draw, last + "…", font) > max_width:
            last = last[:-1]
        result[-1] = last + "…"
    return result


def text_block(
    canvas: Image.Image,
    text: str,
    box: tuple[int, int, int, int],
    size: int,
    fill: str | tuple,
    *,
    weight: str = "regular",
    align: str = "left",
    max_lines: int = 4,
    line_height: float = 1.20,
    min_size: int | None = None,
    stroke_width: int = 0,
    stroke_fill: str | None = None,
) -> int:
    if not text or not str(text).strip():
        return box[1]
    d = ImageDraw.Draw(canvas)
    x1, y1, x2, y2 = box
    availw, availh = max(2, x2 - x1), max(2, y2 - y1)
    current_size = int(size)
    low = min_size or max(17, int(size * 0.52))
    while True:
        f = font_px(current_size, weight)
        lines = wrap_lines(d, str(text), f, availw, max_lines)
        line_px = int(current_size * line_height)
        if (len(lines) * line_px <= availh and max((text_len(d, ln, f) for ln in lines), default=0) <= availw) or current_size <= low:
            break
        current_size -= max(1, int(current_size * 0.045))
    y = y1
    for line in lines:
        length = text_len(d, line, f)
        xx = x1 + (availw - length) / 2 if align == "center" else x2 - length if align == "right" else x1
        # pillow anchors place the top glyph consistently (no mysterious baseline offset)
        d.text((round(xx), y), line, font=f, fill=fill, anchor="lt", stroke_width=stroke_width, stroke_fill=stroke_fill)
        y += int(current_size * line_height)
    return y


def image_from_bytes(data: bytes, max_edge: int = 5000) -> Image.Image:
    # PIL.load() ensures the compressed upload is decoded before file closure.
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im)
        im.load()
        im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        return im.convert("RGB").copy()


def normalized_image(data: bytes, max_edge: int = 1800, jpeg: bool = False) -> bytes:
    im = image_from_bytes(data, max_edge)
    out = io.BytesIO()
    if jpeg:
        im.save(out, format="JPEG", quality=92, optimize=True)
    else:
        im.save(out, format="PNG", optimize=True)
    return out.getvalue()


def crop_cover(im: Image.Image, size: tuple[int, int], center: tuple[float, float] = (0.5, 0.5)) -> Image.Image:
    if size[0] < 1 or size[1] < 1:
        raise ValueError("Invalid crop size")
    return ImageOps.fit(im.convert("RGB"), size, method=Image.Resampling.LANCZOS, centering=center)


def rounded_photo(canvas: Image.Image, image: Image.Image, rect: tuple[int, int, int, int], radius: int, border: int = 0, border_color: str = "#FFFFFF", shadow: int = 18) -> None:
    x1, y1, x2, y2 = (int(v) for v in rect)
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return
    if shadow:
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle((x1 - 3, y1 + 6, x2 + 3, y2 + 12), radius=radius, fill=(18, 24, 27, 100))
        canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(shadow)))
    if border:
        ImageDraw.Draw(canvas).rounded_rectangle((x1 - border, y1 - border, x2 + border, y2 + border), radius=radius + border, fill=border_color)
    photo = crop_cover(image, (w, h))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    canvas.paste(photo.convert("RGBA"), (x1, y1), mask)


def tilted_photo(canvas: Image.Image, im: Image.Image, box: tuple[int, int, int, int], angle: float, paper: str, shadow: bool = True) -> None:
    x1, y1, x2, y2 = (int(n) for n in box)
    w, h = x2 - x1, y2 - y1
    frame = Image.new("RGBA", (w, h), rgba(paper))
    inner = max(9, int(w * 0.042))
    pic_h = h - inner * 3
    pic = crop_cover(im, (w - 2 * inner, pic_h))
    frame.paste(pic, (inner, inner))
    rotated = frame.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    px = x1 - (rotated.width - w) // 2
    py = y1 - (rotated.height - h) // 2
    if shadow:
        alpha = rotated.getchannel("A").filter(ImageFilter.GaussianBlur(22))
        sh = Image.new("RGBA", rotated.size, (15, 13, 11, 0))
        sh.putalpha(alpha.point(lambda a: int(a * 0.34)))
        canvas.alpha_composite(sh, (px + 7, py + 16))
    canvas.alpha_composite(rotated, (px, py))


def round_rect(canvas: Image.Image, xy: tuple[int, int, int, int], radius: int, fill: str | tuple, outline: str | None = None, width: int = 1) -> None:
    ImageDraw.Draw(canvas).rounded_rectangle(tuple(map(int, xy)), radius=max(0, int(radius)), fill=fill, outline=outline, width=width)


def line(canvas: Image.Image, xy: tuple[int, int, int, int], fill: str | tuple, width: int) -> None:
    ImageDraw.Draw(canvas).line(xy, fill=fill, width=max(1, width))


def circle(canvas: Image.Image, center: tuple[int, int], radius: int, color: str, alpha: int = 255) -> None:
    x, y = center
    ImageDraw.Draw(canvas).ellipse((x - radius, y - radius, x + radius, y + radius), fill=rgba(color, alpha))


def blend_bg_art(
    canvas: Image.Image,
    artwork: Image.Image | None,
    bounds: tuple[int, int, int, int],
    palette: dict[str, str],
    alpha: float = 1.0,
) -> None:
    x1, y1, x2, y2 = (int(t) for t in bounds)
    if artwork is None:
        return
    tile = crop_cover(artwork, (x2 - x1, y2 - y1)).convert("RGBA")
    if alpha < 1:
        tile.putalpha(int(255 * alpha))
    canvas.alpha_composite(tile, (x1, y1))


def fallback_artwork(size: tuple[int, int], palette_name: str = "autumn", seed: int = 0, variant: int = 0) -> Image.Image:
    """Local test/preview fallback, clearly not presented as AI output."""
    w, h = size
    colors = PALETTES.get(palette_name, PALETTES["autumn"])
    rnd = random.Random(98762 + seed + 31 * variant)
    bg = Image.new("RGB", size, rgb(colors["soft"]))
    d = ImageDraw.Draw(bg, "RGBA")
    for y in range(h):
        p = y / max(1, h - 1)
        c = color_blend(colors["paper"], colors["soft"], min(1, p * 0.80))
        d.line((0, y, w, y), fill=(*c, 255))
    # Construct an editorial abstract artwork with deliberate organic shapes.
    minside = min(w, h)
    for i in range(7):
        cx = int(w * rnd.uniform(-0.1, 1.1))
        cy = int(h * rnd.uniform(0.18, 1.0))
        rw = int(minside * rnd.uniform(0.12, 0.48))
        rh = int(minside * rnd.uniform(0.10, 0.33))
        col = [colors["accent"], colors["accent2"], colors["deep"], colors["soft"]][i % 4]
        d.ellipse((cx - rw, cy - rh, cx + rw, cy + rh), fill=rgba(col, rnd.randint(70, 135)))
    # Leaves and little stars / dots, aesthetically restricted to lower & side zones
    for i in range(16):
        xx = int(w * rnd.choice([rnd.uniform(-.04, .17), rnd.uniform(.80, 1.04)]))
        yy = int(h * rnd.uniform(.27, .96))
        r = int(minside * rnd.uniform(.015, .048))
        col = colors["accent"] if i % 3 == 0 else colors["deep"]
        d.ellipse((xx-r, yy-r//2, xx+r, yy+r//2), fill=rgba(col, rnd.randint(70, 180)))
    return bg


def make_layer(size: tuple[int, int], color: str | tuple = (0, 0, 0, 0)) -> Image.Image:
    return Image.new("RGBA", size, color)


def draw_kicker(canvas: Image.Image, label: str, pos: tuple[int, int], color: str, ratio: float, tracking: int = 0) -> None:
    d = ImageDraw.Draw(canvas)
    fs = int(24 * ratio)
    d.text(pos, label, font=font_px(fs, "bold"), fill=color, anchor="lt")


def decorative_stars(canvas: Image.Image, seed: int, region: tuple[int, int, int, int], accent: str, quantity: int = 12) -> None:
    d = ImageDraw.Draw(canvas, "RGBA")
    rnd = random.Random(seed)
    x1, y1, x2, y2 = region
    for i in range(quantity):
        x = rnd.randint(x1, x2)
        y = rnd.randint(y1, y2)
        rr = rnd.randint(max(2, (x2-x1)//230), max(4, (x2-x1)//65))
        if i % 3:
            d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=rgba(accent, 130))
        else:
            d.line((x-rr*2,y,x+rr*2,y), fill=rgba(accent,170), width=max(2,rr//4))
            d.line((x,y-rr*2,x,y+rr*2), fill=rgba(accent,170), width=max(2,rr//4))


def _photo_set(photos: Iterable[bytes], limit: int = 4) -> list[Image.Image]:
    out = []
    for b in list(photos)[:limit]:
        try:
            out.append(image_from_bytes(b, 2300))
        except Exception:
            pass
    return out


def layout_editorial(canvas: Image.Image, artwork: Image.Image | None, meta: dict[str, str], photos: list[Image.Image], spec: dict[str, Any], p: dict[str, str]) -> None:
    w, h = canvas.size
    u = w / 1200
    d = ImageDraw.Draw(canvas, "RGBA")
    # Generous, restrained cream-colored information header.
    panel_end = int(h * (.350 if h > w else .44))
    canvas.paste(rgba(p["paper"]), (0, 0, w, h))
    art_start = panel_end
    art_end = int(h * (.835 if h > w else .82))
    blend_bg_art(canvas, artwork, (0, art_start, w, art_end), p, .98)
    d = ImageDraw.Draw(canvas, "RGBA")
    d.rectangle((0, 0, w, panel_end), fill=rgba(p["paper"]))
    d.rectangle((0, art_end, w, h), fill=rgba(p["paper"]))
    left = int(w * .080)
    right = int(w * .920)
    kicker_y = int(h * (.060 if h > w else .078))
    draw_kicker(canvas, (meta.get("organizer") or "POSTER DESIGN STUDIO").upper()[:52], (left, kicker_y), p["accent"], u)
    line(canvas, (left, int(h*.10), right, int(h*.10)), p["accent"], max(2, int(2*u)))
    title_y = int(h * (.12 if h > w else .14))
    title_bottom = int(h * (.255 if h > w else .335))
    title_font = int(93 * u * float(spec.get("title_scale",1)))
    text_block(canvas, meta.get("title") or "행사 제목을 입력하세요", (left,title_y,right,title_bottom), title_font, p["ink"],weight="bold",max_lines=3, line_height=1.15, align=spec.get("alignment","left"), min_size=int(53*u))
    text_block(canvas, meta.get("subtitle", ""), (left, int(h*.275 if h>w else h*.34), right, panel_end-int(h*.022)), int(33*u), p["deep"], weight="regular", max_lines=2)
    # Colored accent patch near header-art boundary
    d = ImageDraw.Draw(canvas,"RGBA")
    d.rectangle((left, panel_end- int(7*u), int(w*.27), panel_end + int(7*u)), fill=rgba(p["accent"]))
    # Photo tiles with natural faces, no AI alteration
    if photos:
        scale=float(spec.get("photo_scale",1))
        photo_y = int(art_start + (art_end-art_start) * .17)
        if len(photos) == 1:
            cw=int(w*.52*scale); ch=int((art_end-art_start)*.65*scale)
            x=int(w*.39); y=min(photo_y,art_end-ch-int(15*u))
            rounded_photo(canvas,photos[0],(x,y,x+cw,y+ch),int(22*u),int(8*u),"#FFFFFF",int(21*u))
        else:
            item_w=int(w*(.35 if len(photos)==2 else .29)*scale)
            item_h=int((art_end-art_start)*.55*scale)
            count=min(len(photos),3)
            gap=int(w*.026)
            total=item_w*count+gap*(count-1)
            x0=max(int(w*.05), (w-total)//2)
            for i in range(count):
                xx=x0+(item_w+gap)*i
                yy=photo_y+int((i%2)*u*24)
                rounded_photo(canvas,photos[i],(xx,yy,xx+item_w,yy+item_h),int(18*u),int(7*u),"#FFFFFF",int(16*u))
    else:
        # small floating editorial captions instead of images, keep art visible
        decorated = make_layer(canvas.size)
        deco = ImageDraw.Draw(decorated,"RGBA")
        deco.rounded_rectangle((int(w*.07),int(art_end-h*.115),int(w*.31),int(art_end-h*.078)), radius=int(14*u),fill=(255,250,241,224))
        canvas.alpha_composite(decorated)
        text_block(canvas, "ART · CULTURE · COMMUNITY", (int(w*.087),int(art_end-h*.110),int(w*.30),int(art_end-h*.08)),int(18*u),p["ink"], weight="bold",max_lines=1)
    footer_y = art_end + int(h * .027)
    text_block(canvas, meta.get("when", ""), (left,footer_y,right,footer_y+int(h*.048)),int(38*u),p["ink"],weight="bold",max_lines=2)
    text_block(canvas, meta.get("where", ""), (left,footer_y+int(h*.052),right,footer_y+int(h*.094)),int(31*u),p["deep"],max_lines=2)
    if meta.get("details", ""):
        text_block(canvas,meta["details"],(left,footer_y+int(h*.098),right,h-int(h*.014)),int(22*u),p["deep"],max_lines=3)
    d=ImageDraw.Draw(canvas)
    d.line((int(w*.74),int(h*.944),right,int(h*.944)), fill=p["accent"],width=max(2,int(2*u)))


def layout_festival(canvas: Image.Image, artwork: Image.Image | None, meta: dict[str,str], photos: list[Image.Image], spec: dict[str,Any], p: dict[str,str]) -> None:
    w,h=canvas.size
    u=w/1200
    d=ImageDraw.Draw(canvas,"RGBA")
    canvas.paste(rgba(p["paper"]),(0,0,w,h))
    # Wide colorful block with floating circular accent and graphic border.
    headline_bottom=int(h*(.285 if h>w else .35))
    art_bottom=int(h*(.800 if h>w else .79))
    blend_bg_art(canvas,artwork,(0,headline_bottom,w,art_bottom),p,1)
    d=ImageDraw.Draw(canvas,"RGBA")
    d.rectangle((0,0,w,headline_bottom),fill=rgba(p["accent"]))
    d.rectangle((0,art_bottom,w,h),fill=rgba(p["paper"]))
    circle(canvas,(int(w*.86),int(h*.08)),int(w*.19),p["accent2"],145)
    decorative_stars(canvas,6,(int(w*.74),int(h*.04),w-int(w*.02),headline_bottom-int(h*.045)),p["paper"],11)
    left=int(w*.075); right=int(w*.93)
    draw_kicker(canvas, "A CELEBRATION OF IMAGINATION",(left,int(h*.045)),p["paper"],u)
    fs=int(104*u*float(spec.get("title_scale",1)))
    text_block(canvas,meta.get("title") or "우리들의 예술 축제",(left,int(h*.105),right,headline_bottom-int(h*.035)),fs,p["paper"],weight="bold",min_size=int(55*u),max_lines=3,line_height=1.16,align=spec.get("alignment","left"))
    if meta.get("subtitle"):
        round_rect(canvas,(left,headline_bottom-int(h*.020),int(w*.88),headline_bottom+int(h*.029)),int(22*u),p["accent2"])
        text_block(canvas,meta["subtitle"],(left+int(15*u),headline_bottom-int(h*.008),int(w*.85),headline_bottom+int(h*.023)),int(23*u),p["ink"],max_lines=1,weight="bold")
    if photos:
        scale=float(spec.get("photo_scale",1))
        if len(photos)>=2:
            count=min(3,len(photos))
            ph=int((art_bottom-headline_bottom)*.54*scale); pw=int(w*.29*scale)
            start=(w-(pw*count+int(w*.03)*(count-1)))//2
            for idx in range(count):
                x=start+idx*(pw+int(w*.03)); y=int(headline_bottom+(art_bottom-headline_bottom)*.23)+(idx%2)*int(25*u)
                tilted_photo(canvas,photos[idx],(x,y,x+pw,y+ph),[-5,4,-3][idx],p["paper"])
        else:
            ph=int((art_bottom-headline_bottom)*.64*scale); pw=int(w*.62*scale)
            x=int(w*.19); y=int(headline_bottom+(art_bottom-headline_bottom)*.15)
            tilted_photo(canvas,photos[0],(x,y,x+pw,y+ph),-4,p["paper"])
    else:
        decorative_stars(canvas,12,(int(w*.06),headline_bottom+int(h*.16),int(w*.92),art_bottom-int(h*.07)),p["accent2"],16)
    footer_top=art_bottom+int(h*.020)
    round_rect(canvas,(left,footer_top,right,footer_top+int(h*.070)),int(21*u),p["accent"])
    text_block(canvas,meta.get("when",""),(left+int(25*u),footer_top+int(h*.010),right-int(20*u),footer_top+int(h*.060)),int(41*u),p["paper"],weight="bold",max_lines=2)
    text_block(canvas,meta.get("where",""),(left,footer_top+int(h*.078),right,footer_top+int(h*.124)),int(32*u),p["ink"],weight="bold",max_lines=2)
    text_block(canvas,meta.get("details", ""),(left,footer_top+int(h*.128),right,h-int(h*.016)),int(22*u),p["deep"],max_lines=3)


def layout_gallery(canvas: Image.Image, artwork: Image.Image | None, meta: dict[str,str], photos: list[Image.Image], spec: dict[str,Any], p: dict[str,str]) -> None:
    w,h=canvas.size
    u=w/1200
    canvas.paste(rgba(p["paper"]),(0,0,w,h))
    d=ImageDraw.Draw(canvas,"RGBA")
    left=int(w*.076); right=int(w*.92)
    # Striking framed hero art above crisp type block, like a gallery exhibition.
    hero_top=int(h*.08)
    hero_bottom=int(h*(.570 if h>w else .490))
    draw_kicker(canvas,"EXHIBITION / FESTIVAL / CULTURE",(left,int(h*.035)),p["accent"],u)
    line(canvas,(left,int(h*.064),right,int(h*.064)),p["ink"],max(2,int(2*u)))
    blend_bg_art(canvas,artwork,(left,hero_top,right,hero_bottom),p,1)
    d=ImageDraw.Draw(canvas,"RGBA")
    d.rectangle((left,hero_top,right,hero_bottom),outline=rgba(p["deep"],125),width=max(2,int(4*u)))
    if photos:
        scale=float(spec.get("photo_scale",1))
        count=min(2,len(photos))
        if count==1:
            x=int(w*.49); y=int(h*.19); ww=int(w*.34*scale); hh=int((hero_bottom-hero_top)*.68*scale)
            rounded_photo(canvas,photos[0],(x,y,x+ww,y+hh),int(16*u),int(11*u),p["paper"],int(25*u))
        else:
            ww=int(w*.31*scale); hh=int((hero_bottom-hero_top)*.58*scale)
            for i in range(2):
                x=int(w*(.15 if i==0 else .54)); y=int(h*(.24 if i==0 else .19))
                rounded_photo(canvas,photos[i],(x,y,x+ww,y+hh),int(16*u),int(10*u),p["paper"],int(25*u))
    bottom_start=hero_bottom+int(h*.022)
    # editorial rule + constrained title block ensures all information remains readable
    line(canvas,(left,bottom_start,right,bottom_start),p["accent"],max(3,int(5*u)))
    ty=bottom_start+int(h*.020)
    max_title_height=int(h*.145 if h>w else h*.17)
    title_scale=float(spec.get("title_scale",1))
    text_block(canvas,meta.get("title") or "행사 제목",(left,ty,right,ty+max_title_height),int(92*u*title_scale),p["ink"],weight="bold",min_size=int(48*u),max_lines=3,align=spec.get("alignment","left"))
    meta_y=ty+max_title_height+int(h*.017)
    if meta.get("subtitle"):
        text_block(canvas,meta["subtitle"],(left,meta_y,right,meta_y+int(h*.045)),int(31*u),p["accent"],weight="bold",max_lines=2)
        meta_y+=int(h*.045)
    if meta.get("when"):
        text_block(canvas,meta["when"],(left,meta_y,right,meta_y+int(h*.050)),int(35*u),p["ink"],weight="bold",max_lines=2)
        meta_y+=int(h*.049)
    if meta.get("where"):
        text_block(canvas,meta["where"],(left,meta_y,right,meta_y+int(h*.048)),int(31*u),p["deep"],max_lines=2)
        meta_y+=int(h*.046)
    if meta.get("details"):
        text_block(canvas,meta["details"],(left,meta_y,right,h-int(h*.020)),int(23*u),p["deep"],max_lines=3)


def render_poster(art_bytes: bytes | None, meta: dict[str, str], photo_bytes: list[bytes], spec: dict[str, Any], size_name: str) -> bytes:
    w,h=SIZES.get(size_name,SIZES["A3 세로 · 297×420mm"])
    canvas=Image.new("RGBA",(w,h),"white")
    palette=PALETTES.get(str(spec.get("palette","autumn")),PALETTES["autumn"])
    art=image_from_bytes(art_bytes, 3500) if art_bytes else None
    photos=_photo_set(photo_bytes)
    layout=spec.get("layout","editorial")
    if layout=="festival":
        layout_festival(canvas,art,meta,photos,spec,palette)
    elif layout=="gallery":
        layout_gallery(canvas,art,meta,photos,spec,palette)
    else:
        layout_editorial(canvas,art,meta,photos,spec,palette)
    # Add subtle print border outside main composition to signal a finished poster.
    edge=ImageDraw.Draw(canvas)
    edge.rectangle((0,0,w-1,h-1), outline=rgba(palette["ink"],28),width=max(1,int(w/600)))
    output=io.BytesIO()
    canvas.convert("RGB").save(output,format="PNG",optimize=True,dpi=(200,200))
    return output.getvalue()


def offline_background_bytes(size_name: str, palette: str, variant: int = 0) -> bytes:
    w,h=SIZES.get(size_name,SIZES["A3 세로 · 297×420mm"])
    im=fallback_artwork((max(800,int(w*.65)),max(900,int(h*.65))),palette,variant=variant)
    out=io.BytesIO()
    im.save(out,format="PNG")
    return out.getvalue()


def high_res_png(png_bytes: bytes, size_name: str, dpi: int = 300) -> bytes:
    """Resample to print dimensions (NOT additional generative detail)."""
    dims_mm={"A3 세로 · 297×420mm":(297,420),"A4 세로 · 210×297mm":(210,297)}
    if size_name not in dims_mm:
        return png_bytes
    width_mm,height_mm=dims_mm[size_name]
    target=(round(width_mm / 25.4 * dpi),round(height_mm / 25.4 * dpi))
    with Image.open(io.BytesIO(png_bytes)) as src:
        img=src.resize(target,Image.Resampling.LANCZOS)
        out=io.BytesIO()
        img.save(out,format="PNG",dpi=(dpi,dpi),optimize=True)
        return out.getvalue()
