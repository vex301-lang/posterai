import base64
import io
import os
import zipfile

import streamlit as st
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title='AI 포스터 디자인 스튜디오', page_icon='🎨', layout='wide')
st.title('🎨 AI 포스터 디자인 스튜디오')
st.caption('3가지 시안을 만들고, 마음에 드는 시안을 자연어로 수정하세요.')

with st.sidebar:
    st.header('1. 행사 정보')
    title = st.text_input('행사 제목 *', placeholder='2026 꿈나눔예술제')
    subtitle = st.text_input('부제 / 슬로건')
    date = st.text_input('날짜 및 시간')
    place = st.text_input('장소')
    details = st.text_area('추가 안내')
    mood = st.selectbox('분위기', ['밝고 경쾌한', '고급스럽고 세련된', '따뜻하고 감성적인', '미니멀한', '역동적이고 강렬한', '동화 같은', '직접 입력'])
    custom_mood = st.text_input('원하는 분위기') if mood == '직접 입력' else ''
    size = st.selectbox('포스터 크기', ['A3 세로 (297×420mm)', 'A4 세로 (210×297mm)', '정사각형 (1:1)', '가로형 (3:2)', '세로 SNS (4:5)', '스토리 (9:16)'])
    st.header('2. 사진 업로드')
    refs = st.file_uploader('레퍼런스 이미지', type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True)
    photos = st.file_uploader('포스터에 사용할 사진', type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True)
    st.header('3. API')
    try:
        default_key = st.secrets.get('OPENAI_API_KEY', '')
    except Exception:
        default_key = os.getenv('OPENAI_API_KEY', '')
    api_key = st.text_input('OpenAI API 키', value=default_key, type='password')
    model = st.selectbox('이미지 모델', ['gpt-image-1.5', 'gpt-image-1'], index=0)
    quality = st.selectbox('이미지 품질', ['medium', 'high', 'low'], index=0)
    st.caption('시안 생성과 자연어 수정은 각각 API 요금이 발생합니다.')


def output_size(value):
    if '정사각형' in value:
        return '1024x1024'
    if '가로형' in value:
        return '1536x1024'
    return '1024x1536'


def font_path():
    for path in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', '/usr/share/fonts/truetype/nanum/NanumGothic.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if os.path.exists(path):
            return path
    return None


def wrap_text(draw, text, font, max_width):
    lines = []
    for paragraph in text.splitlines():
        current = ''
        for ch in paragraph:
            if current and draw.textbbox((0, 0), current + ch, font=font)[2] > max_width:
                lines.append(current)
                current = ch
            else:
                current += ch
        if current:
            lines.append(current)
    return lines


def compose(background, meta):
    image = Image.open(io.BytesIO(background)).convert('RGBA')
    w, h = image.size
    overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, int(h * .65), w, h), fill=(7, 15, 30, 224))
    path = font_path()
    def font(size):
        return ImageFont.truetype(path, size) if path else ImageFont.load_default()
    fields = [('title', .68, .063, 2), ('subtitle', .79, .030, 1), ('date', .85, .028, 1), ('place', .90, .028, 1), ('details', .95, .021, 1)]
    for key, y, scale, limit in fields:
        value = meta.get(key, '').strip()
        if not value:
            continue
        f = font(max(16, int(w * scale)))
        for line in wrap_text(draw, value, f, int(w * .87))[:limit]:
            draw.text((int(w * .065), int(h * y)), line, font=f, fill='white')
            y += f.size * 1.12 / h if hasattr(f, 'size') else .02
    result = Image.alpha_composite(image, overlay).convert('RGB')
    buffer = io.BytesIO()
    result.save(buffer, format='PNG')
    return buffer.getvalue()


def image_file(data, name='poster.png'):
    file = io.BytesIO(data)
    file.name = name
    return file


def upload_files(files):
    result = []
    for index, file in enumerate(files[:10]):
        image = Image.open(io.BytesIO(file.getvalue())).convert('RGB')
        image.thumbnail((1800, 1800))
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        result.append(image_file(buf.getvalue(), f'input_{index}.png'))
    return result


def generated_bytes(response):
    return base64.b64decode(response.data[0].b64_json)


if 'designs' not in st.session_state:
    st.session_state.designs = []
if 'revision_log' not in st.session_state:
    st.session_state.revision_log = []

meta = dict(title=title, subtitle=subtitle, date=date, place=place, details=details)

if st.button('✨ 서로 다른 포스터 3개 생성', type='primary', use_container_width=True):
    if not title.strip():
        st.error('행사 제목을 입력하세요.')
    elif not api_key:
        st.error('API 키를 입력하세요.')
    else:
        client = OpenAI(api_key=api_key)
        styles = [
            'Minimal editorial design, sophisticated negative space and strong hierarchy.',
            'Bold colorful festival graphics, lively geometric shapes and dynamic energy.',
            'Warm artistic collage, tactile paper textures and expressive imagery.'
        ]
        new_designs = []
        for index, style in enumerate(styles):
            with st.spinner(f'{index + 1}/3 시안 생성 중...'):
                prompt = (f'Create a polished professional event poster BACKGROUND ARTWORK, with no text of any kind. '
                          f'Style: {style}. Mood: {custom_mood or mood}. Event theme: {title}. '
                          f'Use reference images for inspiration, and incorporate supplied event photos naturally when possible. '
                          f'Do not alter identities of people in photos. Reserve the bottom 35% as a calm, uncluttered area '
                          f'for a separate Korean text overlay. Aspect ratio: {size}. '
                          f'No words, letters, digits, logos, watermarks, signs or fake typography.')
                try:
                    images = upload_files(list(refs or []) + list(photos or []))
                    if images:
                        response = client.images.edit(model=model, image=images, prompt=prompt, size=output_size(size), quality=quality)
                    else:
                        response = client.images.generate(model=model, prompt=prompt, size=output_size(size), quality=quality)
                    background = generated_bytes(response)
                    new_designs.append({'background': background, 'history': [background]})
                except Exception as exc:
                    st.error(f'{index + 1}번 생성 실패: {exc}')
                    break
        if new_designs:
            st.session_state.designs = new_designs
            st.session_state.revision_log = []
            st.success(f'{len(new_designs)}개 시안을 생성했습니다.')

if st.session_state.designs:
    st.subheader('생성된 시안')
    columns = st.columns(len(st.session_state.designs))
    for index, design in enumerate(st.session_state.designs):
        with columns[index]:
            poster = compose(design['background'], meta)
            st.image(poster, caption=f'시안 {index + 1} · 수정 {len(design["history"]) - 1}회', use_container_width=True)
            st.download_button('PNG 저장', poster, file_name=f'poster_{index + 1}.png', mime='image/png', key=f'png_{index}')

    st.divider()
    st.subheader('💬 자연어로 포스터 수정')
    st.caption('예: 배경을 파스텔톤으로 바꿔줘 / 인물 사진을 더 크게 보여줘 / 왼쪽에 꽃 장식을 추가해줘')
    selection = st.selectbox('수정할 시안 선택', range(len(st.session_state.designs)), format_func=lambda i: f'시안 {i + 1}')
    instruction = st.text_area('수정 명령', placeholder='예: 전체 분위기를 더 따뜻하게 만들고 배경에 작은 별을 추가해줘.', height=110)
    st.info('행사 제목·시간·장소는 정확한 한글 표시를 위해 별도로 합성됩니다. 해당 문구는 왼쪽 행사 정보에서 수정하세요.')
    left, right = st.columns(2)
    with left:
        revise = st.button('🎨 선택한 시안 수정하기', type='primary', use_container_width=True)
    with right:
        undo = st.button('↩ 이전 디자인으로 되돌리기', use_container_width=True)

    if revise:
        if not instruction.strip():
            st.warning('수정할 내용을 입력하세요.')
        elif not api_key:
            st.error('API 키를 입력하세요.')
        else:
            with st.spinner('선택한 포스터를 수정하고 있습니다...'):
                try:
                    design = st.session_state.designs[selection]
                    prompt = (f'Edit the provided poster background artwork according to this Korean user instruction: '
                              f'{instruction.strip()}\n'
                              f'Keep the overall composition, subject identities and recognizable photographs unless the '
                              f'instruction explicitly requests a change. Preserve the bottom 35% as a visually quiet area '
                              f'for separately composited Korean event information. '
                              f'IMPORTANT: Do not add any text, letters, numbers, pseudo-text or watermarks. '
                              f'Output the revised poster background artwork only, maintaining the same aspect ratio.')
                    client = OpenAI(api_key=api_key)
                    response = client.images.edit(model=model, image=[image_file(design['background'])], prompt=prompt,
                                                  size=output_size(size), quality=quality)
                    updated = generated_bytes(response)
                    design['background'] = updated
                    design['history'].append(updated)
                    st.session_state.revision_log.append((selection + 1, instruction.strip()))
                    st.success('수정했습니다. 위 시안과 다운로드 파일에 반영되었습니다.')
                    st.rerun()
                except Exception as exc:
                    st.error(f'수정 실패: {exc}')
    if undo:
        design = st.session_state.designs[selection]
        if len(design['history']) <= 1:
            st.warning('되돌릴 이전 디자인이 없습니다.')
        else:
            design['history'].pop()
            design['background'] = design['history'][-1]
            st.rerun()

    if st.session_state.revision_log:
        with st.expander('수정 명령 기록'):
            for number, (design_number, command) in enumerate(st.session_state.revision_log, 1):
                st.write(f'{number}. 시안 {design_number}: {command}')

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for index, design in enumerate(st.session_state.designs):
            archive.writestr(f'poster_{index + 1}.png', compose(design['background'], meta))
    st.download_button('📦 모든 시안 ZIP 저장', buffer.getvalue(), file_name='poster_designs.zip', mime='application/zip')
    st.caption('AI 이미지 수정은 원본을 완벽하게 유지하지 않을 수 있습니다. 출력 전 인물, 텍스트, 해상도를 확인하세요.')
