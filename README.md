# 2027학년도 수능 풀이 모델 리더보드

수능 국어·수학 문제를 문항별로 나눠 모델 API에 병렬로 요청하고, 공식 정답표로 채점합니다. 2026학년도 자료는 문항 분리 검증에 사용합니다. Streamlit에서 과목별 순위, 채점 진행률, 소요시간을 2초마다 갱신합니다.

## 설치

Node.js 20 이상과 Python 3.10 이상이 필요합니다. 2026학년도 영어 듣기 자료를 준비하려면 FFmpeg도 설치합니다.

```bash
npm ci --omit=optional
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dashboard.txt
cp .env.example .env
```

평가할 API의 키를 `.env` 또는 환경 변수에 설정합니다. `gpt-` 모델은 `OPENAI_API_KEY`로 OpenAI Responses API를, `claude-` 모델은 `ANTHROPIC_API_KEY`로 Anthropic Messages API를 호출합니다. 워크스페이스 미지정 Anthropic 키는 `ANTHROPIC_WORKSPACE_ID`가 필요합니다. `회사/모델` 형식의 ID는 `OPENROUTER_API_KEY`를 쓰며, Upstage 직접 호출에는 `UPSTAGE_API_KEY`가 필요합니다.

## 데이터 준비

공식 홀수형·짝수형 통합 문제지는 `subjects/`, 정답표는 `answer_sheets/`에 둡니다. 파일 이름에는 `2027_` 또는 `2026_` 접두사와 `국어영역`, `수학영역`, `영어영역` 중 해당 과목명을 포함합니다. 국어 추출기는 원본 레이아웃과 시각 자료 전사를 검증하기 위해 등록된 파일의 SHA-256과 대조합니다.

```bash
.venv/bin/python prepare_exam.py --year 2027
.venv/bin/python prepare_math.py --year 2027
```

국어는 Kordoc의 블록에서 공통 지문과 문항 범위를 찾고, 국어 112문항의 텍스트와 시각 자료 전사를 구성합니다. 수학은 수식과 그래프가 보존되도록 92문항을 PDF에서 PNG로 잘라냅니다. 두 과목 모두 정답과 배점을 공식 정답표에서 추출합니다.

## 모델 평가 및 리더보드

```bash
.venv/bin/python benchmark.py --subject korean --year 2027 --workers 24 \
  --model gpt-6.2-astra --model gpt-6.2-sol --model gpt-6.1-terra \
  --model claude-fable-5-2 --model claude-opus-5-5 --model claude-sonnet-5-5

.venv/bin/python benchmark.py --subject math --year 2027 --workers 16 \
  --model google/gemini-4-neon --model google/gemini-4-hydrogen \
  --model google/gemini-4-carbon --model google/gemini-4-argon

.venv/bin/python -m streamlit run dashboard.py --server.address 127.0.0.1
```

두 평가 명령에서 `--subject korean`과 `--subject math`를 바꿔 다른 과목을 실행할 수 있습니다. 같은 명령으로 재실행하면 성공한 답안을 재사용합니다. `--recover-effort low`는 이전에 실패한 문항에 적용됩니다. 기본 추론 설정은 `medium`이며 온도 지정을 지원하는 호출에는 `0`을 설정합니다. 출력 한도에 도달하면 최대 32,768토큰까지 늘려 재시도합니다. 사용한 설정과 소요시간은 문항 응답에 기록합니다.

대시보드는 [국어](http://127.0.0.1:8501/?subject=korean)와 [수학](http://127.0.0.1:8501/?subject=math) 선택을 주소에 기록합니다. 홀수형·짝수형과 선택과목별 100점 원점수를 평균해 순위를 매깁니다. 동점이면 첫 요청부터 마지막 채점 응답까지의 소요시간이 짧은 모델을 앞에 둡니다. 결과는 문항별 체크포인트, `leaderboard.md`, `results.json`, SQLite의 `output/results.sqlite`에 기록합니다.

## 공개 리더보드

[Vercel 리더보드](https://suneung-cat.vercel.app)는 동일한 Streamlit 화면을 컨테이너로 실행합니다. 공개 화면에 필요한 점수, 순위, 진행률, 소요시간만 Vercel의 비공개 Blob에 저장합니다. 모델 API 키와 시험 원본, 정답표, 문항별 응답 및 SQLite는 평가 환경에 보관합니다.

Vercel 프로젝트에는 Blob의 `leaderboard.json` 주소를 `CSAT_LEADERBOARD_URL`로 설정합니다. 연결된 스토어의 `BLOB_READ_WRITE_TOKEN`을 `.env.local` 또는 환경 변수로 받은 뒤 평가하는 동안 다음 명령을 실행하면 집계가 바뀔 때마다 공개 리더보드에 반영됩니다.

```bash
.venv/bin/python leaderboard_data.py --publish --watch
```

## 2026학년도 영어 준비

`subjects/`에 영어 문제지 PDF와 공식 듣기 음원 ZIP을, `answer_sheets/`에 영어 정답표 PDF를 둡니다. `prepare_english.py`는 문항 90개와 듣기용 MP3 16개를 준비합니다. 16–17번은 공통 음원에 각 문항 이미지를 함께 보냅니다. 오디오와 이미지 입력을 확인한 OpenRouter 모델은 `google/gemini-3.8-flash`, `meta/muse-ember`, `qwen/qwen3.8-omni-flash`, `xiaomi/mimo-v2.6-flash`입니다. Streamlit 화면에는 국어와 수학을 표시합니다.

```bash
.venv/bin/python prepare_english.py --year 2026
```

[Kordoc](https://github.com/chrisryugj/kordoc) · [OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create) · [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create) · [OpenRouter 오디오 입력](https://openrouter.ai/docs/guides/overview/multimodal/audio)
