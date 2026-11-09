"""AI 포스터 디자인 스튜디오 PRO v4.

핵심 변화
- API 키는 Streamlit Secrets에서 자동 로드
- AI 아트디렉터가 3개의 디자인 콘셉트를 먼저 기획
- 빠른 초안 / 전문가 모드 분리
- 생성된 시안에 대해 자동 품질 평가 및 추천안 제시
- 행사 정보/한글/실사용 사진은 코드 레이어로 정교하게 합성
"""
from __future__ import annotations

import copy
import io
import json
import os
import zipfile
from datetime import datetime

import streamlit as st

from poster_engine import (
    PALETTES,
    SIZES,
    STYLE_LABELS,
    default_spec,
    high_res_png,
    offline_background_bytes,
    render_poster,
)
from ai_services import (
    DESIGN_MODES,
    IMAGE_MODELS,
    QUALITY_PRESETS,
    ai_instruction,
    analyze_reference_style,
    evaluate_poster_quality,
    generate_art,
    generate_design_plans,
    local_instruction,
)

st.set_page_config(
    page_title="POSTER LAB PRO v4",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """<style>
      .block-container {padding-top: 1.8rem; max-width: 1520px;}
      h1 {font-size: 2.0rem !important; letter-spacing: -.04em;}
      h2,h3 {letter-spacing: -.03em;}
      [data-testid="stSidebar"] {background: #f7f4f1;}
      div.stButton > button[kind="primary"] {background:#bf5a35; border-color:#bf5a35;}
      .muted {color:#6b655e; font-size:.92rem; line-height:1.55;}
      .smallnote {color:#7a736c; font-size:.84rem;}
      .score-pill {display:inline-block;padding:.2rem .55rem;border-radius:999px;background:#f1ece7;color:#5b463c;font-size:.82rem;font-weight:600;margin-right:.3rem;}
      [data-testid="stImage"] img {border-radius: 4px; box-shadow: 0 10px 26px rgba(32,20,10,.12);}
      .plan-card {background:#fcfaf8;border:1px solid #efe5db;border-radius:14px;padding:.9rem 1rem;}
    </style>""",
    unsafe_allow_html=True,
)


def streamlit_key() -> str:
    try:
        secret = str(st.secrets.get("OPENAI_API_KEY", "") or "").strip()
    except Exception:
        secret = ""
    return secret or str(os.environ.get("OPENAI_API_KEY", "") or "").strip()


def bytes_of_files(uploaded, limit: int = 6) -> list[bytes]:
    if not uploaded:
        return []
    results = []
    for item in uploaded[:limit]:
        data = item.getvalue()
        if len(data) > 18 * 1024 * 1024:
            st.warning(f"{item.name}: 18MB가 넘는 이미지는 제외했습니다.")
        else:
            results.append(data)
    return results


def merged_meta(meta: dict[str, str], draft: dict) -> dict[str, str]:
    return {**meta, **draft.get("content_overrides", {})}


def output_png(draft: dict, meta: dict[str, str], photos: list[bytes], size_name: str) -> bytes:
    return render_poster(draft.get("art"), merged_meta(meta, draft), photos, draft["spec"], size_name)


def show_error(error: Exception) -> str:
    code = getattr(error, "status_code", None)
    message = str(error)
    if code == 401:
        return "API 키가 유효하지 않습니다. Streamlit Secrets의 OPENAI_API_KEY를 확인해 주세요."
    if code == 429:
        return "API 사용 한도 또는 결제 잔액 문제입니다. OpenAI Platform의 Billing과 Limits를 확인해 주세요."
    if code == 403:
        return "선택한 이미지 모델의 사용 권한이 없습니다. 계정 인증 또는 모델 접근 권한을 확인해 주세요."
    return (type(error).__name__ + ": " + message)[:380]


def plan_to_spec(plan: dict, fallback_palette: str, idx: int) -> dict:
    spec = default_spec(idx, plan.get("palette") or fallback_palette)
    spec.update({
        "layout": plan.get("layout", spec["layout"]),
        "palette": plan.get("palette", spec["palette"]),
        "title_scale": float(plan.get("title_scale", spec["title_scale"])),
        "photo_scale": float(plan.get("photo_scale", spec["photo_scale"])),
        "alignment": plan.get("alignment", spec["alignment"]),
        "photo_style": plan.get("photo_style", spec["photo_style"]),
        "background_note": plan.get("visual_prompt", ""),
    })
    return spec


def maybe_evaluate(api_key: str, use_ai: bool, mode_key: str, png: bytes, meta: dict, idx: int) -> dict:
    if not (use_ai and api_key and mode_key == "pro"):
        return {"score": 0, "summary": "자동 평가는 전문가 모드에서만 실행됩니다.", "strengths": [], "fixes": []}
    try:
        return evaluate_poster_quality(api_key, png, meta, idx + 1)
    except Exception as exc:
        return {"score": 0, "summary": "자동 평가를 완료하지 못했습니다: " + show_error(exc), "strengths": [], "fixes": []}


def generate_three(
    api_key: str,
    use_ai: bool,
    metadata: dict[str, str],
    mood: str,
    palette: str,
    size_name: str,
    model: str,
    quality: str,
    refs: list[bytes],
    ref_mode: str,
    mode_key: str,
    detail_focus: str,
    auto_evaluate: bool,
) -> tuple[list[dict], list[str], list[dict]]:
    drafts = []
    warnings = []
    style_brief = ""
    plans: list[dict] = []

    if use_ai and refs and ref_mode == "스타일만 분석 (추천)":
        try:
            with st.spinner("레퍼런스 포스터에서 스타일만 추출하고 있습니다."):
                style_brief = analyze_reference_style(api_key, refs)
        except Exception as exc:
            warnings.append("스타일 분석 실패. 참고 이미지를 직접 참고해 진행합니다: " + show_error(exc))

    if use_ai and api_key:
        try:
            with st.spinner("AI 아트디렉터가 3개의 디자인 콘셉트를 기획하고 있습니다."):
                plans = generate_design_plans(api_key, metadata, mood, palette, size_name, style_brief, detail_focus, len(refs))
        except Exception as exc:
            warnings.append("아트디렉터 계획 수립에 실패하여 기본 콘셉트로 진행합니다: " + show_error(exc))

    if not plans:
        plans = [
            {"name": "에디토리얼", "layout": "editorial", "palette": palette, "photo_style": "rounded", "alignment": "left", "title_scale": 1.0, "photo_scale": 1.0, "visual_prompt": "Refined editorial illustration with premium detail."},
            {"name": "페스티벌", "layout": "festival", "palette": palette, "photo_style": "polaroid", "alignment": "left", "title_scale": 1.02, "photo_scale": 1.0, "visual_prompt": "Vibrant artistic festival background with confident focal imagery."},
            {"name": "갤러리", "layout": "gallery", "palette": palette, "photo_style": "framed", "alignment": "center", "title_scale": 0.98, "photo_scale": 0.95, "visual_prompt": "Elegant gallery mood with quiet negative space and refined texture."},
        ]

    progress = st.progress(0, text="3개의 시안을 제작하고 있습니다.")
    for i in range(3):
        plan = plans[i] if i < len(plans) else plans[-1]
        spec = plan_to_spec(plan, palette, i)
        source = "AI 배경"
        if use_ai and api_key:
            try:
                send_refs = refs if (ref_mode != "스타일만 분석 (추천)" or (refs and not style_brief)) else []
                art = generate_art(
                    api_key,
                    metadata,
                    mood,
                    i,
                    spec.get("palette", palette),
                    size_name,
                    model,
                    quality,
                    send_refs,
                    extra=plan.get("visual_prompt", ""),
                    reference_style=style_brief,
                    pro_mode=(mode_key == "pro"),
                )
            except Exception as exc:
                art = offline_background_bytes(size_name, palette, i)
                source = "API 실패 · 로컬 대체"
                warnings.append(f"{i+1}안: {show_error(exc)}")
        else:
            art = offline_background_bytes(size_name, palette, i)
            source = "로컬 미리보기"

        draft = {
            "art": art,
            "spec": spec,
            "source": source,
            "history": [],
            "content_overrides": {},
            "edit_log": [],
            "plan": plan,
            "evaluation": {},
        }
        if auto_evaluate:
            png = output_png(draft, metadata, photos, size_name) if False else None
        drafts.append(draft)
        progress.progress((i + 1) / 3, text=f"{i+1}/3 시안을 준비했습니다.")
    progress.empty()
    return drafts, warnings, plans


def rank_and_evaluate(drafts: list[dict], api_key: str, use_ai: bool, mode_key: str, meta: dict, photos: list[bytes], size_name: str) -> list[dict]:
    for idx, draft in enumerate(drafts):
        try:
            png = output_png(draft, meta, photos, size_name)
        except Exception:
            draft["evaluation"] = {"score": 0, "summary": "평가용 이미지 렌더링에 실패했습니다.", "strengths": [], "fixes": []}
            continue
        draft["evaluation"] = maybe_evaluate(api_key, use_ai, mode_key, png, merged_meta(meta, draft), idx)
    drafts.sort(key=lambda d: d.get("evaluation", {}).get("score", 0), reverse=True)
    return drafts


if "drafts" not in st.session_state:
    st.session_state["drafts"] = []
if "selected" not in st.session_state:
    st.session_state["selected"] = 0
if "project_size" not in st.session_state:
    st.session_state["project_size"] = "A3 세로 · 297×420mm"
if "generation_notes" not in st.session_state:
    st.session_state["generation_notes"] = []

with st.sidebar:
    st.markdown("## 01 / 행사 정보")
    event_title = st.text_input("행사 제목 *", value="2026 꿈나눔예술제", max_chars=120)
    event_subtitle = st.text_input("부제 / 슬로건", value="우리의 상상이 예술이 되는 날", max_chars=150)
    event_when = st.text_area("날짜와 시간", value="", placeholder="예: 2026. 11. 10.(화) 14:00", height=78, max_chars=300)
    event_where = st.text_input("장소", value="한신초등학교", max_chars=180)
    event_details = st.text_area("추가 안내", value="작품 전시회 · 예술 발표회", height=84, max_chars=400)
    event_organizer = st.text_input("주최 / 주관 (상단 작은 글씨)", value="HANSIN SCHOOL ARTS FESTIVAL", max_chars=110)

    st.markdown("## 02 / 디자인 지시")
    mood = st.text_area(
        "원하는 분위기",
        value="따뜻한 가을 축제, 질감 있는 수채화와 고급스러운 편집 디자인, 생동감 있는 어린이 예술 활동",
        height=102,
    )
    detail_focus = st.selectbox("강조할 요소", ["행사 분위기", "일러스트 완성도", "사진 조화", "제목 가독성", "고급스러운 편집 디자인"], index=4)
    palette_labels = {
        "가을 · 테라코타": "autumn",
        "파스텔 · 라벤더": "pastel",
        "청량 · 블루": "ocean",
        "자연 · 포레스트": "forest",
        "밤 · 네이비": "night",
        "햇살 · 비비드": "sunshine",
        "미니멀 · 모노": "mono",
    }
    palette_label = st.selectbox("컬러 팔레트", list(palette_labels), index=0)
    palette = palette_labels[palette_label]
    size_name = st.selectbox("포스터 크기", list(SIZES), key="project_size")

    st.markdown("## 03 / 이미지 업로드")
    refs_upload = st.file_uploader("스타일 참고 이미지 (최대 3개)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key="style_refs", help="참고 포스터의 색감·질감·분위기 분석용입니다.")
    ref_mode = st.selectbox("레퍼런스 해석 방식", ["스타일만 분석 (추천)", "이미지 직접 참고"], help="스타일 분석은 가짜 글자가 생기는 문제를 줄입니다.")
    photos_upload = st.file_uploader("실제 사용할 사진 (최대 4개)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key="poster_photos", help="실제 사진은 AI 재생성이 아니라 코드 합성으로 처리합니다.")

    st.markdown("## 04 / 생성 모드")
    mode_label = st.selectbox("작업 모드", list(DESIGN_MODES), index=1)
    mode_key = DESIGN_MODES[mode_label]

    api_key = streamlit_key()
    if api_key:
        st.success("✅ 관리자 API 연결 완료 · 키 입력 없이 바로 사용할 수 있습니다.")
    else:
        st.warning("AI API가 아직 연결되지 않았습니다. 관리자만 한 번 설정하면 됩니다.")
        with st.expander("관리자: Streamlit Cloud에 API 키 등록 방법", expanded=True):
            st.markdown("1. Streamlit Cloud에서 앱 **Settings → Secrets**를 엽니다.\n2. 아래 예시의 값을 실제 OpenAI 키로 바꿔 붙여넣고 **Save**합니다.\n3. 앱을 새로고침하면 자동 연결됩니다.")
            st.code('OPENAI_API_KEY = "sk-여기에_발급받은_키"', language="toml")

    model_label = st.selectbox("이미지 모델", list(IMAGE_MODELS), index=0)
    selected_model = IMAGE_MODELS[model_label]
    quality_label = st.selectbox("품질 프로파일", list(QUALITY_PRESETS), index=1 if mode_key == "pro" else 0)
    selected_quality = QUALITY_PRESETS[quality_label]
    auto_evaluate = st.checkbox("생성 후 AI가 시안 품질 자동 평가", value=bool(api_key and mode_key == "pro"), disabled=not bool(api_key))
    st.caption("전문가 모드는 시안 생성 뒤 자동 평가까지 수행하므로 비용과 시간이 더 들 수 있습니다.")

meta = {
    "title": event_title.strip(),
    "subtitle": event_subtitle.strip(),
    "when": event_when.strip(),
    "where": event_where.strip(),
    "details": event_details.strip(),
    "organizer": event_organizer.strip(),
}
refs = bytes_of_files(refs_upload, limit=3)
photos = bytes_of_files(photos_upload, limit=4)

st.markdown("# POSTER LAB <span style='font-size:.48em;color:#bf5a35;font-weight:700'>PRO v4</span>", unsafe_allow_html=True)
st.markdown("**AI 아트디렉터가 콘셉트를 기획하고, 배경은 AI가 만들고, 한글·행사정보·실사용 사진은 별도 레이어로 정교하게 합성합니다.**")

left, right = st.columns([0.68, 0.32], gap="large")
with left:
    st.markdown("<div class='muted'>정보 입력 → 레퍼런스 분석 → 아트디렉터 콘셉트 3개 → 포스터 생성 → 자동 평가 → 자연어 수정</div>", unsafe_allow_html=True)
with right:
    st.caption("● " + ("AI 이미지 생성 준비됨" if api_key else "관리자 API 설정 필요 · 무료 미리보기는 이용 가능"))

btn1, btn2, _ = st.columns([1.2, 1, 2], gap="small")
with btn1:
    generate_clicked = st.button("✦ AI 포스터 3안 생성", type="primary", use_container_width=True, disabled=not bool(api_key))
with btn2:
    demo_clicked = st.button("무료 로컬 미리보기 3안", use_container_width=True)

if generate_clicked or demo_clicked:
    if not event_title.strip():
        st.error("행사 제목을 입력해 주세요.")
    else:
        with st.spinner("포스터 시안을 준비하고 있습니다."):
            new_drafts, notes, plans = generate_three(
                api_key,
                generate_clicked,
                meta,
                mood,
                palette,
                size_name,
                selected_model,
                selected_quality,
                refs,
                ref_mode,
                mode_key,
                detail_focus,
                auto_evaluate,
            )
            if auto_evaluate:
                new_drafts = rank_and_evaluate(new_drafts, api_key, generate_clicked, mode_key, meta, photos, size_name)
            st.session_state["drafts"] = new_drafts
            st.session_state["selected"] = 0
            st.session_state["generation_notes"] = notes
            st.session_state["design_plans"] = plans
        st.rerun()

notes = st.session_state.get("generation_notes") or []
if notes:
    with st.expander("생성 과정 메모 / 경고", expanded=False):
        for note in notes:
            st.write("- " + note)

plans = st.session_state.get("design_plans") or []
if plans:
    with st.expander("AI 아트디렉터가 만든 3가지 콘셉트 보기", expanded=False):
        cols = st.columns(3)
        for i, plan in enumerate(plans[:3]):
            with cols[i]:
                st.markdown("<div class='plan-card'>", unsafe_allow_html=True)
                st.markdown(f"**{i+1}. {plan.get('name','시안')}**")
                st.write(f"레이아웃: {STYLE_LABELS.get(plan.get('layout','editorial'), '에디토리얼')}")
                st.write(f"색상: {plan.get('palette', palette)}")
                st.caption(plan.get("summary", plan.get("visual_prompt", ""))[:220])
                st.markdown("</div>", unsafe_allow_html=True)

if not st.session_state["drafts"]:
    st.info("왼쪽 정보를 입력한 뒤 포스터 3안을 생성해 보세요. 전문가 모드는 완성도와 추천 기능이 더 좋지만 시간이 더 걸립니다.")
    st.stop()

st.divider()
st.subheader("02 · 시안 살펴보기")
thumb_cols = st.columns(3, gap="medium")
for idx, draft in enumerate(st.session_state["drafts"][:3]):
    with thumb_cols[idx]:
        png = output_png(draft, meta, photos, size_name)
        st.image(png, use_container_width=True)
        eval_info = draft.get("evaluation", {}) or {}
        score = int(eval_info.get("score", 0) or 0)
        if score:
            st.markdown(f"<span class='score-pill'>품질 점수 {score}</span>", unsafe_allow_html=True)
        if draft.get("source"):
            st.caption(draft.get("source"))
        if st.button(f"이 시안 선택", key=f"pick_{idx}", use_container_width=True):
            st.session_state["selected"] = idx
            st.rerun()
        if eval_info.get("summary"):
            st.caption(eval_info["summary"])

selected_idx = min(st.session_state.get("selected", 0), len(st.session_state["drafts"]) - 1)
draft = st.session_state["drafts"][selected_idx]

edit_col, detail_col = st.columns([0.40, 0.60], gap="large")
with edit_col:
    st.subheader(f"선택한 시안 · {selected_idx+1}안")
    eval_info = draft.get("evaluation", {}) or {}
    if eval_info.get("score"):
        st.success(f"AI 품질 점수: {int(eval_info['score'])}/100")
        strengths = eval_info.get("strengths") or []
        fixes = eval_info.get("fixes") or []
        if strengths:
            st.markdown("**좋은 점**")
            for s in strengths[:3]:
                st.write("- " + s)
        if fixes:
            st.markdown("**보완 제안**")
            for s in fixes[:3]:
                st.write("- " + s)

    st.markdown("**자연어 수정**")
    edit_instruction = st.text_area(
        "원하는 변경 내용을 자유롭게 적어주세요",
        value="",
        height=115,
        placeholder="예) 제목을 더 크게, 배경은 파스텔 핑크로, 사진을 조금 더 작게, 하단 정보는 더 또렷하게 만들어줘.",
        key="edit_instruction",
    )
    repaint = st.checkbox("AI 배경 그림도 새로 생성하기 (이미지 API 추가 비용 발생)", value=False)
    use_language_model = st.checkbox("AI가 자연어 지시를 분석하기 (소액의 텍스트 API 비용)", value=bool(api_key), disabled=not bool(api_key))
    fix_col, undo_col = st.columns([0.67, 0.33])
    with fix_col:
        apply_clicked = st.button("수정 적용", type="primary", use_container_width=True)
    with undo_col:
        undo_clicked = st.button("↶ 이전으로", use_container_width=True, disabled=not bool(draft.get("history")))

    if undo_clicked:
        st.session_state.pop("zip_result", None)
        st.session_state.pop("print_png", None)
        snapshot = draft["history"].pop()
        draft["spec"] = snapshot["spec"]
        draft["art"] = snapshot["art"]
        draft["content_overrides"] = snapshot["content_overrides"]
        draft["edit_log"].append("직전 수정 취소")
        st.rerun()

    if apply_clicked:
        if not edit_instruction.strip():
            st.warning("수정 명령을 먼저 입력해 주세요.")
        else:
            prior = {
                "spec": copy.deepcopy(draft["spec"]),
                "art": draft.get("art"),
                "content_overrides": copy.deepcopy(draft.get("content_overrides", {})),
            }
            try:
                if use_language_model and api_key:
                    try:
                        update = ai_instruction(api_key, edit_instruction, draft["spec"], merged_meta(meta, draft))
                    except Exception as exc:
                        st.warning("AI 명령 해석이 어려워 기본 규칙으로 적용했습니다: " + show_error(exc))
                        update = local_instruction(edit_instruction, draft["spec"])
                else:
                    update = local_instruction(edit_instruction, draft["spec"])

                next_spec = {**draft["spec"], **update.get("spec", {})}
                new_art = draft.get("art")
                if repaint:
                    if not api_key:
                        st.warning("API 키가 없어서 배경 재생성은 생략하고 레이아웃만 수정합니다.")
                    else:
                        try:
                            next_meta = {**merged_meta(meta, draft), **update.get("content_updates", {})}
                            with st.spinner("AI가 배경 아트워크를 다시 작업하고 있습니다."):
                                new_art = generate_art(
                                    api_key,
                                    next_meta,
                                    mood,
                                    selected_idx,
                                    next_spec.get("palette", palette),
                                    size_name,
                                    selected_model,
                                    selected_quality,
                                    refs,
                                    base_art=draft.get("art"),
                                    extra=next_spec.get("background_note") or edit_instruction,
                                    pro_mode=(mode_key == "pro"),
                                )
                        except Exception as exc:
                            st.warning("배경 재생성 실패 — 기존 배경을 유지합니다: " + show_error(exc))
                st.session_state.pop("zip_result", None)
                st.session_state.pop("print_png", None)
                draft["history"].append(prior)
                draft["history"] = draft["history"][-8:]
                draft["spec"] = next_spec
                draft["art"] = new_art
                draft["content_overrides"] = {**draft.get("content_overrides", {}), **update.get("content_updates", {})}
                draft["edit_log"].append(edit_instruction.strip()[:180])
                st.session_state["last_edit_summary"] = update.get("summary", "디자인을 수정했습니다.")
                if auto_evaluate:
                    png = output_png(draft, meta, photos, size_name)
                    draft["evaluation"] = maybe_evaluate(api_key, bool(api_key), mode_key, png, merged_meta(meta, draft), selected_idx)
                st.rerun()
            except Exception as exc:
                st.error("수정에 실패하여 이전 포스터를 유지합니다: " + show_error(exc))

    if st.session_state.get("last_edit_summary"):
        st.success(st.session_state["last_edit_summary"])

    with st.expander("선택 시안의 상세 디자인 설정"):
        option = draft["spec"]
        key_base = f"spec_{selected_idx}"
        new_palette = st.selectbox("색상", list(PALETTES), index=list(PALETTES).index(option.get("palette", "autumn")), key=f"{key_base}_palette")
        new_layout = st.selectbox("레이아웃", list(STYLE_LABELS), index=list(STYLE_LABELS).index(option.get("layout", "editorial")), format_func=lambda x: STYLE_LABELS[x], key=f"{key_base}_layout")
        new_ts = st.slider("제목 크기", 0.70, 1.4, float(option.get("title_scale", 1)), 0.05, key=f"{key_base}_ts")
        new_ps = st.slider("사진 크기", 0.65, 1.3, float(option.get("photo_scale", 1)), 0.05, key=f"{key_base}_ps")
        new_align = st.selectbox("제목 정렬", ["left", "center"], index=0 if option.get("alignment", "left") == "left" else 1, format_func=lambda v: "왼쪽" if v == "left" else "가운데", key=f"{key_base}_align")
        if st.button("세부 설정 적용", key=f"{key_base}_save"):
            st.session_state.pop("zip_result", None)
            st.session_state.pop("print_png", None)
            draft["history"].append({"spec": copy.deepcopy(option), "art": draft.get("art"), "content_overrides": copy.deepcopy(draft.get("content_overrides", {}))})
            option.update({"palette": new_palette, "layout": new_layout, "title_scale": new_ts, "photo_scale": new_ps, "alignment": new_align})
            st.rerun()

with detail_col:
    try:
        selected_png = output_png(draft, meta, photos, size_name)
        st.image(selected_png, use_container_width=True)
        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button("선택 시안 PNG", data=selected_png, file_name=f"poster_selected_{selected_idx+1}.png", mime="image/png", use_container_width=True)
        with col_b:
            if size_name.startswith("A3") or size_name.startswith("A4"):
                if st.button("300dpi 출력용 준비", use_container_width=True):
                    st.session_state["print_png"] = high_res_png(selected_png, size_name)
                if "print_png" in st.session_state:
                    st.download_button("출력용 PNG 저장", data=st.session_state["print_png"], file_name="poster_print_300dpi.png", mime="image/png", use_container_width=True)
        st.caption("출력용 PNG는 인쇄 크기로 리샘플링한 파일입니다. 원본 생성 이미지보다 새로운 화질 정보가 늘어나는 것은 아닙니다.")
    except Exception as exc:
        st.error("미리보기 오류: " + show_error(exc))

st.divider()
st.subheader("03 · 전체 결과 다운로드")
if st.button("3개 시안 ZIP 만들기", use_container_width=False):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for idx, item in enumerate(st.session_state["drafts"]):
            png = output_png(item, meta, photos, size_name)
            archive.writestr(f"poster_{idx+1}_{item['spec'].get('layout','design')}.png", png)
        record = {
            "event": meta,
            "size": size_name,
            "model": selected_model,
            "mode": mode_key,
            "quality": selected_quality,
            "designs": [
                {
                    "spec": d["spec"],
                    "source": d.get("source", ""),
                    "edits": d.get("edit_log", []),
                    "plan": d.get("plan", {}),
                    "evaluation": d.get("evaluation", {}),
                }
                for d in st.session_state["drafts"]
            ],
        }
        archive.writestr("project_info.json", json.dumps(record, ensure_ascii=False, indent=2))
    st.session_state["zip_result"] = output.getvalue()
if st.session_state.get("zip_result"):
    st.download_button("포스터 3안 ZIP 다운로드", st.session_state["zip_result"], file_name="poster_lab_pro_v4_designs.zip", mime="application/zip")

st.caption("POSTER LAB PRO v4 · 참고 이미지는 분위기 분석 또는 배경 생성에 활용될 수 있습니다. 실제 사용 사진은 코드 합성에만 사용합니다. 학교에서 사용할 때 학생 사진 및 초상권 동의를 확인하세요.")
