"""OpenAI image generation and structured Korean natural-language design edits.

No to_file import: uploads use standard file-like BytesIO objects, which work
with the OpenAI Python SDK's images.edit API.
"""
from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

from poster_engine import PALETTES, SIZES, default_spec, normalized_image

IMAGE_MODELS = {
    "최고 품질 · GPT Image 2.5 Sunburst": "gpt-image-2.5-sunburst",
    "빠른 생성 · GPT Image 2.5 Flare": "gpt-image-2.5-flare",
    "경제형 · GPT Image 2": "gpt-image-2",
    "이전 모델 · GPT Image 1.5": "gpt-image-1.5",
}

# Each output is intentionally a different art direction. Composition overlays
# are *not* generated inside the image model, to protect Korean readability.
ART_DIRECTIONS = [
    "Warm, sophisticated festival key visual. Rich painterly visual story with tactile gouache or cut-paper texture; immersive artistic environment, refined color harmony; harmonious oversized shapes, no goofy clipart. Main focal objects in the lower half, organic depth, fine details and beautifully integrated lighting.",
    "Premium vibrant art-fair identity. Confident bold geometric forms, handmade paper textures, asymmetric playful shapes, rich contrast, captivating contemporary cultural festival artwork, museum-quality art direction. Editorial sophistication instead of childish clipart.",
    "Elevated gallery editorial illustration with masterful negative space, layered spatial depth, delicate print textures, restrained luxurious color choices, detailed handcrafted motifs appropriate for an exhibition and cultural festival. Calm iconic composition.",
]


def from_sdk_client(key: str):
    # Lazy import so the local preview can be used even without openai installed.
    from openai import OpenAI
    return OpenAI(api_key=key, timeout=180.0, max_retries=1)


def image_size(size_name: str) -> str:
    w, h = SIZES.get(size_name, (1654,2339))
    if abs(w-h)/max(w,h)<.06:
        return "1024x1024"
    if w>h:
        return "1536x1024"
    return "1024x1536"


def build_art_prompt(
    meta: dict[str,str],
    mood: str,
    direction: int,
    palette: str,
    *,
    extra: str = "",
    edited: bool = False,
    reference_style: str = "",
) -> str:
    event=(meta.get("title") or "community art festival")[:140]
    subtitle=(meta.get("subtitle") or "")[:160]
    palette_desc={
        "autumn":"muted terracotta, burnt orange, marigold, warm cream, dark walnut",
        "pastel":"lavender, dusty pink, pale peach, elegant lilac, warm off-white",
        "ocean":"indigo, sea-glass teal, airy turquoise, cream, soft gold",
        "forest":"moss green, sage, rust, deep evergreen, ivory",
        "night":"deep midnight cobalt, moonlit gold, ink navy, vintage pearl",
        "sunshine":"saffron, marigold, poppy orange, pastel cream, sunny yellow",
        "mono":"neutral parchment, charcoal, warm grey, soft monochrome",
    }.get(palette,"harmonious premium editorial colors")
    concept=ART_DIRECTIONS[direction % 3]
    return f"""You are an award-winning art director making ONLY THE ILLUSTRATIVE ARTWORK LAYER for a Korean cultural event poster.
Event concept: {event}. Subtitle/context: {subtitle}.
Mood specified by client: {mood[:200]}. Preferred palette: {palette_desc}.
Distinct art direction: {concept}
The final poster will add accurate Korean typography, photographs, dates and venue later using code. Therefore:
- DO NOT put any text or letterforms whatsoever anywhere in the image: no Korean, English, numbers, logos, signage, posters, banner mockups, watermarks or placeholder glyphs.
- DO NOT make a poster mockup, dark caption/footer bar, fake information boxes, phone screen, or writing area with pseudo text.
- Produce beautiful sophisticated full-bleed pure artwork suitable for the centerpiece of an expertly designed print poster.
- High-end art direction, exquisite imagery, coherent lighting and depth, aesthetic restraint with rich tactile detail.
- Keep edges and upper part slightly quieter so designed overlay elements can have clear separation.
- All people and objects, if present, should look anatomically plausible and thoughtfully composed, not malformed or AI-collaged.
- Visual concepts should be appropriate for a school community and family audience; no identifiable real-life school branding.
{('Refine the previously generated artwork, preserve its strongest details and improve professional polish.' if edited else '')}
Style insights extracted from uploaded reference material (visual mood only): {reference_style[:1300]}
Additional specific user art direction: {extra[:600]}"""


def as_png_file(data: bytes, filename: str) -> io.BytesIO:
    file=io.BytesIO(normalized_image(data,max_edge=1700))
    file.name=filename
    file.seek(0)
    return file


def _read_result(result: Any) -> bytes:
    if not result.data:
        raise RuntimeError("이미지 생성 API가 결과 이미지를 반환하지 않았습니다.")
    value=getattr(result.data[0],"b64_json",None)
    if not value:
        raise RuntimeError("이미지 응답에 b64_json 데이터가 없습니다.")
    return base64.b64decode(value)


def generate_art(
    key: str,
    meta: dict[str,str],
    mood: str,
    direction: int,
    palette: str,
    size_name: str,
    model: str,
    quality: str,
    reference_images: list[bytes] | None = None,
    base_art: bytes | None = None,
    extra: str = "",
    reference_style: str = "",
) -> bytes:
    client=from_sdk_client(key)
    prompt=build_art_prompt(meta,mood,direction,palette,extra=extra,edited=bool(base_art),reference_style=reference_style)
    inputs=[]
    if base_art:
        inputs.append(as_png_file(base_art,"source_art.png"))
    for i, src in enumerate((reference_images or [])[:3]):
        inputs.append(as_png_file(src,f"reference_{i+1}.png"))
    options={"model":model,"prompt":prompt,"size":image_size(size_name),"quality":quality,"output_format":"png"}
    if inputs:
        # Style reference(s) are supplied to images.edit, without passing any
        # user's actual photographs destined for exact compositing.
        resp=client.images.edit(image=inputs,**options)
    else:
        resp=client.images.generate(**options)
    return _read_result(resp)


def analyze_reference_style(key: str, reference_images: list[bytes]) -> str:
    """Describe style only. Prevent copying letters from a user-supplied poster.

    This is preferable to feeding an entire reference poster straight into image
    edits, where AI can accidentally replicate pseudo-text and poor typography.
    """
    if not reference_images:
        return ""
    client = from_sdk_client(key)
    content = [{
        "type": "text",
        "text": (
            "You are a print design art director. Examine the supplied reference poster(s) "
            "and describe ONLY its visual style, materials, aesthetic qualities, season "
            "motifs, background illustration technique, color palette, composition rhythm "
            "and sophistication, in concise ENGLISH under 220 words. "
            "Do not quote any text, titles, date, venue, school names or branding in the image. "
            "Do not request any text or faux writing in a new artwork. "
            "Do not describe a copy of the original layout; abstract general style characteristics."
        ),
    }]
    for src in reference_images[:3]:
        data = normalized_image(src, max_edge=1100, jpeg=True)
        content.append({"type": "image_url", "image_url": {
            "url": "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii"),
            "detail": "low",
        }})
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role":"user", "content": content}],
        temperature=0.2,
        max_tokens=400,
    )
    brief = response.choices[0].message.content or ""
    return brief[:1300].strip()


def local_instruction(instruction: str, spec: dict[str,Any]) -> dict[str,Any]:
    """Always works offline. More subtle edits are supported with text model."""
    v=str(instruction).strip().lower()
    changes:dict[str,Any]={}
    if any(x in v for x in ("파랑","파란","푸른","청량","바다","blue")):
        changes["palette"]="ocean"
    elif any(x in v for x in ("보라","분홍","핑크","파스텔","purple","pink")):
        changes["palette"]="pastel"
    elif any(x in v for x in ("초록","녹색","숲","자연","green")):
        changes["palette"]="forest"
    elif any(x in v for x in ("검정","어두운","밤","고급스러운","navy")):
        changes["palette"]="night"
    elif any(x in v for x in ("가을","주황","낙엽","단풍","따뜻")):
        changes["palette"]="autumn"
    elif any(x in v for x in ("노랑","햇살","밝은","화사")):
        changes["palette"]="sunshine"
    elif any(x in v for x in ("흑백","모노톤","미니멀")):
        changes["palette"]="mono"
    clauses=[part.strip() for part in re.split(r"[,，;\n。.]",v) if part.strip()]
    for phrase in clauses:
        if any(word in phrase for word in ("제목","글씨","글자","타이틀")):
            factor=float(changes.get("title_scale",spec.get("title_scale",1)))
            if any(x in phrase for x in ("크게","키워","강조")):
                changes["title_scale"]=min(1.4, factor+0.17)
            elif any(x in phrase for x in ("작게","줄여","축소")):
                changes["title_scale"]=max(0.7, factor-0.15)
            if any(x in phrase for x in ("가운데","중앙","center")):
                changes["alignment"]="center"
            elif "왼쪽" in phrase:
                changes["alignment"]="left"
        if "사진" in phrase or "이미지" in phrase:
            scale=float(changes.get("photo_scale",spec.get("photo_scale",1)))
            if any(x in phrase for x in ("크게","확대","키워")):
                changes["photo_scale"]=min(1.28,scale+.12)
            elif any(x in phrase for x in ("작게","축소","줄여")):
                changes["photo_scale"]=max(.68,scale-.12)
    if any(x in v for x in ("미니멀","심플","전시","갤러리")):
        changes["layout"]="gallery"
    elif any(x in v for x in ("축제","경쾌","역동","발랄")):
        changes["layout"]="festival"
    elif any(x in v for x in ("잡지","정갈","편집","에디토리얼")):
        changes["layout"]="editorial"
    if any(x in v for x in ("배경","그림","일러스트","색감","하늘","분위기")):
        changes["background_note"]=instruction[:500]
    return {"spec": changes, "content_updates": {}, "repaint_background": bool(changes.get("background_note")),"summary":"로컬 규칙으로 디자인을 수정했습니다."}


def ai_instruction(key: str, instruction: str, spec: dict[str,Any], meta: dict[str,str]) -> dict[str,Any]:
    """Constrained JSON edit: never allow arbitrary code, positions, URLs or fonts."""
    client=from_sdk_client(key)
    system=f"""You are a Korean art director editing a layered poster. Return ONLY one JSON object, no markdown.
Available keys:
  spec: {{layout: one of [editorial,festival,gallery], palette: one of {list(PALETTES)}, title_scale: float between 0.7 and 1.4, photo_scale: float between 0.65 and 1.3, alignment: left or center, background_note: string of visual art direction}}
  content_updates: {{title, subtitle, when, where, details, organizer}} as strings. Only if explicitly requested to change FACTUAL WORDING. NEVER invent missing date/time/venue.
  repaint_background: boolean (true for requests modifying visual illustration/background itself; false for typography/layout/photo changes)
  summary: short Korean description of what changed.
The user provided current spec {json.dumps(spec,ensure_ascii=False)} and metadata {json.dumps(meta,ensure_ascii=False)}.
Interpret relative edits like 'make title bigger' by adding +0.15 to current title_scale. For anything not requested, omit that key."""
    rsp=client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role":"system","content":system},{"role":"user","content":instruction[:1200]}],
        response_format={"type":"json_object"},
        temperature=0.25,
    )
    content=rsp.choices[0].message.content or "{}"
    raw=json.loads(content)
    sanitized_spec:dict[str,Any]={}
    for key,value in dict(raw.get("spec") or {}).items():
        if key=="layout" and value in {"editorial","festival","gallery"}:
            sanitized_spec[key]=value
        elif key=="palette" and value in PALETTES:
            sanitized_spec[key]=value
        elif key in {"title_scale","photo_scale"}:
            try:
                num=float(value)
                sanitized_spec[key]=min(1.4 if key=="title_scale" else 1.3,max(.7 if key=="title_scale" else .65,num))
            except (TypeError, ValueError):
                pass
        elif key=="alignment" and value in {"left","center"}:
            sanitized_spec[key]=value
        elif key=="background_note" and isinstance(value,str):
            sanitized_spec[key]=value[:600]
    content_updates={k:v[:500] for k,v in dict(raw.get("content_updates") or {}).items() if k in {"title","subtitle","when","where","details","organizer"} and isinstance(v,str)}
    return {"spec":sanitized_spec,"content_updates":content_updates,"repaint_background":bool(raw.get("repaint_background",False)),"summary":str(raw.get("summary", "디자인을 수정했습니다."))[:200]}
