# POSTER LAB PRO · AI 포스터 디자인 스튜디오 (Streamlit)

**한글과 사진을 AI에게 통째로 그리게 하지 않고, 고급 아트워크 위에 개별 레이어로 정확하게 합성하는 포스터 제작기**입니다.

## 주요 기능

- 행사 제목, 슬로건, 날짜/시간, 장소, 주최, 안내문 입력
- A3/A4/SNS/스토리/정사각/가로형 비율 선택
- 참고 포스터 3장까지 AI 스타일 참고: **기본은 이미지 비전 분석 → 스타일 문장 추출 → 새 아트 생성** (글자 복제 위험 감소). 선택 시 이미지 직접 참고도 가능
- 실제 사진 4장까지 로컬 합성 (이미지 생성 API에 사진을 전달하지 않음)
- 서로 다른 3가지 디자인: 에디토리얼 / 페스티벌 / 갤러리
- 한국어 자연어 수정 (레이아웃·컬러·제목 크기·사진 크기·문구 수정)
- 필요할 때만 AI 배경 재생성 (추가 API 비용)
- 편집 이전으로 되돌리기, 3안 PNG/ZIP 저장, A3/A4 300dpi 표기 출력 크기 리샘플링
- API 없이 디자인 구조를 확인하는 무료 로컬 미리보기

## Streamlit Community Cloud 배포

1. ZIP을 압축 해제합니다. `app.py`, `poster_engine.py`, `ai_services.py`, `requirements.txt`, `packages.txt`, `.streamlit/config.toml` 등을 **GitHub 저장소의 최상위 폴더**에 올립니다.
2. 기존 `posterai` 저장소라면 파일들을 교체/추가합니다. **`app.py`만 바꾸면 다른 모듈을 못 찾아 오류가 납니다.**
3. [Streamlit Cloud](https://share.streamlit.io/)에서 저장소의 `app.py`를 배포합니다.
4. 앱의 **Settings → Secrets** 에 다음 TOML을 입력하고 저장합니다.

   ```toml
   OPENAI_API_KEY = "sk-본인_키"
   ```

5. `AI 포스터 3안 생성`을 누릅니다. API 키가 없는 경우 `무료 로컬 미리보기 3안`이 작동합니다.
6. `.streamlit/secrets.toml.example`은 **예시일 뿐이며 실제 비밀번호를 절대 GitHub에 올리지 마세요.**

### GitHub 업로드 시 주의

ZIP 파일 자체를 GitHub에 올리는 것이 아닙니다. ZIP을 풀어 내부 파일들을 저장소 루트에 올려야 합니다. `.streamlit/config.toml` 폴더도 함께 업로드하세요. `packages.txt`는 Linux 배포 환경에 무료 한국어 폰트 `fonts-nanum`을 설치합니다.

## 로컬 실행

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Linux에 나눔 글꼴이 없다면 `sudo apt-get install fonts-nanum` 명령으로 설치합니다.
Windows/macOS는 `poster_engine.py`의 `resolve_font()` 함수에 로컬 한글 글꼴 경로를 추가해야 할 수 있습니다.

## 모델 선택 및 API 비용

| 모델 | 추천 용도 |
| --- | --- |
| `gpt-image-2.5-sunburst` | 전문 시안/참고 이미지 반영과 정교한 수정 |
| `gpt-image-2.5-flare` | 속도와 품질의 균형 |
| `gpt-image-2` | 경제형, 최대 high 품질 |
| `gpt-image-1.5` | 이전 모델과 호환을 위한 선택지 |

- OpenAI **이미지 API 3회**가 시안 3개 생성에 사용됩니다. 스타일 참고 모드가 「스타일만 분석」이고 참고 이미지가 있을 때는 **gpt-4.1-mini 분석 1회**가 먼저 발생합니다. 선택한 모델·출력 해상도·품질과 입력 참고 이미지 개수에 따라 실제 요금이 달라집니다.
- `자연어 AI 분석`을 켜면 `gpt-4.1-mini` 호출이 추가되고, `AI 배경 그림도 새로 생성하기`를 선택하면 이미지 API 호출이 추가됩니다.
- `gpt-image-1`은 2026-10-23 종료된 모델이므로 목록에서 제거했습니다.
- OpenAI 계정에 따라 이미지 기능 사용 전에 **Organization Verification**이 필요할 수 있습니다.

## 결과물 품질에 대해

이 앱은 타이포그래피를 **정확한 한글 레이어**로 구성하고, 스타일 배경은 AI가 생성하므로 어색한 한글/글리프 문제를 줄입니다. 다만 완전한 디자이너 수준을 자동 보장하는 것은 아니며, API가 반환하는 이미지 자체가 부자연스러우면 수정이 필요합니다.

**A3/A4 출력용 300dpi PNG**는 출력 픽셀 수에 맞춰 *리샘플링*한 결과물이며 AI 원본의 실제 해상도에 존재하지 않던 디테일을 복원해 주지 않습니다. 전문 인쇄는 별도 고해상도 작업을 권합니다.

## 개인정보 안내

- `스타일 참고 이미지`는 스타일 분석 또는 스타일 참고를 위해 선택한 AI 서비스에 전송됩니다. 기본 「스타일만 분석」은 참고 포스터의 분위기만 분석해 신규 생성에 활용합니다.
- `실제로 사용할 사진`은 PIL로만 합성하여 **OpenAI 이미지 API에 전송하지 않습니다**.
- 자연어 분석을 사용할 경우 행사 제목 등 텍스트 메타데이터는 텍스트 AI API에 전송됩니다.
- 실제 학교 행사에서는 학생/교직원 사진을 사용하는 데 필요한 동의와 내부 규정을 확인하세요.

## 문제 해결

- `ImportError: cannot import name 'to_file'`: 이번 버전은 `to_file`을 전혀 사용하지 않습니다. 이전 `app.py`가 배포된 것인지 확인하세요.
- `ModuleNotFoundError: poster_engine / ai_services`: 새 ZIP의 파일을 모두 저장소 루트에 업로드했는지 확인하세요.
- 한글이 네모로 보임: `packages.txt`에서 `fonts-nanum` 설치가 되었는지 배포 로그를 확인하세요.
- `401 Unauthorized`: `OPENAI_API_KEY` 값과 비밀키를 확인하세요.
- `429 quota`: API 결제 잔액, rate limit, organization tier를 확인하세요.
- 모델 권한 오류: OpenAI API에서 이미지 모델 사용 권한과 조직 인증을 확인하세요.

## 파일 구성

```text
app.py                   # Streamlit UI / 이미지 생성 / 자연어 수정 / 다운로드
poster_engine.py         # 한글 글꼴·레이아웃·사진·레이어 합성
ai_services.py           # OpenAI 이미지/텍스트 API 어댑터
requirements.txt         # Python 의존성
packages.txt             # Linux 한글 폰트 설치
.streamlit/config.toml   # UI 테마 및 업로드 설정
.streamlit/secrets.toml.example  # API Secrets 예시 (진짜 키 아님)
.gitignore               # 비밀키 커밋 방지
README.md                # 이 문서
```

## 참고 문서

- [OpenAI Image Generation](https://developers.openai.com/api/docs/guides/image-generation)
- [OpenAI Image Edits API](https://developers.openai.com/api/reference/python/resources/images/methods/edit)
- [Streamlit Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
