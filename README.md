# AI 포스터 디자인 스튜디오 PRO v4

이번 버전은 포스터 전체를 AI에게 통째로 그리게 하지 않고,

1. **AI 아트디렉터가 콘셉트 3개를 먼저 기획**하고  
2. **이미지 모델은 배경/무드/일러스트만 생성**한 뒤  
3. **한글 제목·일시·장소·행사 정보는 코드로 정교하게 합성**하고  
4. **실제 사용할 사진은 원본을 유지한 채 직접 배치**하며  
5. **전문가 모드에서는 완성된 시안을 다시 AI가 자동 평가**하도록 설계했습니다.

## 주요 기능

- API 키 자동 로드 (Streamlit Secrets)
- 빠른 초안 / 전문가 모드
- 레퍼런스 포스터 스타일 분석
- 3개 시안 자동 생성
- 자연어 명령 수정
- 생성 결과 자동 품질 평가
- 선택 시안 PNG 다운로드
- 3개 시안 ZIP 다운로드
- A3/A4 300dpi 출력용 PNG 준비

## 파일 구성

- `app.py` : Streamlit 앱 메인
- `ai_services.py` : 이미지 생성 / 아트디렉터 / 품질평가 API 연동
- `poster_engine.py` : 포스터 레이아웃 렌더링 엔진
- `requirements.txt` : Python 의존성
- `packages.txt` : 시스템 폰트 패키지
- `.streamlit/secrets.toml.example` : API 키 예시

## Streamlit Secrets 설정

Streamlit Cloud → 앱 Settings → Secrets 에 아래를 입력합니다.

```toml
OPENAI_API_KEY = "sk-여기에_발급받은_키"
```

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 참고

- 전문가 모드는 시안 생성 후 자동 평가까지 포함되므로 API 호출 수가 더 많습니다.
- 실제 학생 사진은 AI 배경 생성용으로 다시 그리지 않고, 앱 내부에서 그대로 합성합니다.
- 실제 배포 환경에서 이미지 생성 모델 이름이나 파라미터는 계정 권한에 따라 조정이 필요할 수 있습니다.
