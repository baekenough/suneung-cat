from datetime import datetime
from html import escape
import base64
import os
from urllib.error import URLError

import streamlit as st

from exam_analysis import markdown as analysis_markdown
from leaderboard_data import BlobLeaderboard, REFRESH_SECONDS, local_leaderboard, packaged_leaderboard
from subjects_catalog import COURSE_OPTIONS, ENGLISH_RELEASE, FOURTH_RELEASE, GROUPS, KST, LABELS

SERVICE_NAME = '수능냥이'
TITLE = '2027학년도 수능 풀이 모델 리더보드'
SHORT_COURSES = {'화법과 작문': '화작', '언어와 매체': '언매'}
PROVIDERS = {'all': '전체', 'openai': 'OpenAI', 'anthropic': 'Anthropic',
             'gemini': 'Gemini', 'openrouter': 'OpenRouter', 'upstage': 'Upstage'}

st.set_page_config(page_title=f'{SERVICE_NAME} · {TITLE}', layout='wide')
st.html('''
<style>
.stApp { background: #f6f7f9; color: #161d26; }
[data-testid="stHeader"] { display: none; }
.stMainBlockContainer { max-width: 1360px; padding: 2.5rem 2rem 2rem; }
.exam-header, .exam-board { border-radius: 12px; }
.exam-header { padding: 30px 32px; background: #182536; color: #f8fafc; border-top: 4px solid #ff9900; }
.exam-header h1 { font-size: clamp(1.5rem, 3vw, 2.2rem); line-height: 1.3; letter-spacing: -0.035em;
                  color: #f8fafc; margin: 0; padding: 0; overflow-wrap: anywhere; }
.exam-header p { color: #d1d8e3; margin: .65rem 0 0; font-size: .94rem; }
.exam-header .exam-service-name { color: #ffbd61; margin: 0 0 .5rem; font-size: 1rem; font-weight: 750; }
.st-key-subject button { min-height: 40px; padding: .4rem .85rem; background: #fff; color: #263d56;
                         border: 1px solid #cdd9e7; border-radius: 8px; font-weight: 650; }
.st-key-subject button:hover { border-color: #82b4e1; background: #f2f8fe; }
.st-key-subject button[aria-checked="true"], .st-key-subject button[aria-pressed="true"] {
    background: #e3f1ff; border-color: #096ec5; color: #074a87; }
.st-key-subject button:focus-visible { outline: 2px solid #0972d3; outline-offset: 2px; }
.st-key-provider button { background: #fff; color: #20364d; border-color: #c4ccd7; font-size: .84rem; }
.st-key-provider button[aria-checked="true"], .st-key-provider button[aria-pressed="true"] {
    background: #eaf5ff; color: #064a88; border-color: #0972d3; }
.exam-board { width: 100%; border: 1px solid #d9e1eb; background: #fff; overflow: hidden;
              box-shadow: 0 5px 20px #172b4510; }
.exam-board__header { padding: 20px 23px; display: flex; flex-wrap: wrap; gap: 8px 16px;
                      justify-content: space-between; align-items: baseline; }
.exam-board__header h2 { font-size: 1.24rem; margin: 0; padding: 0; color: #162940; letter-spacing: -.025em; }
.exam-board__status { color: #52647a; font-size: .78rem; font-variant-numeric: tabular-nums; }
.exam-board__table { overflow-x: auto; }
.exam-board table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.exam-board th, .exam-board td { padding: 12px 15px; border-block-start: 1px solid #e9eef4; text-align: right; }
.exam-board th { background: #f0f4f9; color: #425773; font-size: .76rem;
                 word-break: keep-all; overflow-wrap: anywhere; }
.exam-board td { color: #26384d; font-size: .88rem; }
.exam-board tbody tr:nth-child(2n) { background: #fafcfe; }
.exam-board tbody tr:hover { background: #eef6ff; }
.exam-board .name { text-align: left; font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
                   overflow-wrap: anywhere; font-weight: 650; color: #13253a; }
.exam-board td.name { padding-inline-end: 12px; }
.exam-board[data-cases="6"] :is(th, td):not(.name) { padding-inline: 8px; }
.exam-board .rank { text-align: center; }
.exam-board .rank strong { display: inline-grid; place-items: center; min-width: 1.8rem; min-height: 1.8rem;
                           border-radius: 7px; background: #edf2f8; color: #364d67; }
.exam-board .rank .first { color: #814800; background: #ffefd1; }
.exam-board .score { font-size: 1.02rem; font-weight: 770; color: #07559e; white-space: nowrap; }
.exam-board :is(th, td).elapsed { color: #425773; text-align: left; white-space: nowrap; }
.exam-board .case { color: #52647a; }
.exam-board .route { display: table; color: #465c74; background: #eef3f8; border-radius: 5px;
                     font: 550 .68rem system-ui, sans-serif; padding: 2px 6px; margin-top: 4px; }
.exam-board .route:empty { display: none; }
.exam-note { color: #536678; font-size: .82rem; margin: .75rem 0 0; }
.exam-byline { color: #46566b;
               display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
               font-size: .84rem; gap: 8px 16px; }
.exam-byline p { margin: 0; }
.exam-byline nav { position: relative; display: flex; flex-wrap: wrap; align-items: center; gap: 7px; }
.exam-byline nav :is(a, button) { display: inline-flex; align-items: center; justify-content: center;
                                 width: 42px; height: 42px; border: 1px solid #d5dae1; border-radius: 8px;
                                 background: #fff; color: #182536; text-decoration: none; }
.exam-byline button { cursor: pointer; padding: 0; }
.exam-byline nav :is(a, button):hover { background: #eaf5ff; border-color: #87b6e3; }
.exam-byline :is(a, button):focus-visible { outline: 2px solid #0972d3; outline-offset: 2px; }
.exam-byline img { width: 20px; height: 20px; flex-shrink: 0; }
.exam-share-status { position: absolute; z-index: 1; inset-inline-end: 0; top: calc(100% + 5px);
                     white-space: nowrap; pointer-events: none; }
.exam-share-status:not(:empty) { padding: 4px 9px; border-radius: 5px; background: #182536; color: #fff; }
@media (min-width: 811px) {
    .exam-board { --model-width: clamp(194px, 25vw, 230px); }
    .exam-board table { table-layout: fixed; }
    .exam-board col.rank { width: 64px; }
    .exam-board col.name { width: var(--model-width); }
    .exam-board col.score { width: 96px; }
    .exam-board col.elapsed { width: 108px; }
    .exam-board[data-cases="0"] col.elapsed { width: auto; }
}
@media (max-width: 810px) {
    .stMainBlockContainer { padding: 1.25rem .85rem; }
    .exam-header { padding: 19px 18px; }
    .exam-board__header { padding: 13px 1px; }
    .exam-board { border: 0; background: transparent; box-shadow: none; }
    .exam-board__table { overflow: visible; }
    .exam-board table, .exam-board tbody { display: block; min-width: 0; }
    .exam-board colgroup { display: none; }
    .exam-board thead { position: absolute; width: 1px; height: 1px; overflow: hidden;
                       clip-path: inset(50%); white-space: nowrap; }
    .exam-board tbody tr { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); column-gap: 12px;
                          background: #fff; border: 1px solid #dce4ee; border-radius: 12px;
                          padding: 12px 14px; margin-bottom: 10px; }
    .exam-board tbody tr:nth-child(2n), .exam-board tbody tr:hover { background: #fff; }
    .exam-board td { text-align: left; padding: 7px 0; border: 0; grid-column: span 2; }
    .exam-board td::before { display: block; content: attr(data-label); color: #536678; font-size: .7rem;
                             white-space: nowrap; font-weight: 400; margin-bottom: 2px; }
    .exam-board .rank { grid-column: 1; text-align: left; }
    .exam-board .name { grid-column: 2 / -1; }
    .exam-board td.name { padding-inline-end: 0; }
    .exam-board[data-cases="6"] td:not(.name) { padding-inline: 0; }
    .exam-board :is(.score, .elapsed) { grid-column: span 3; }
    .exam-board .case { border-block-start: 1px solid #e9eef4; grid-column: span 3; }
    .exam-board[data-cases="6"] .case { grid-column: span 2; }
    .exam-board .rank::before, .exam-board .name::before { content: none; }
}
</style>
''')
# LinkedIn and GitHub marks follow Bootstrap Icons vector paths.
def icon_image(svg):
    encoded = base64.b64encode(svg.encode()).decode()
    return f'<img alt="" src="data:image/svg+xml;base64,{encoded}">'

share_icon = icon_image('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
fill="none" stroke="#182536" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
<path d="M8 7l4-4 4 4m-4-4v12m-5-5H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-2"/>
</svg>''')
linkedin_icon = icon_image('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="#0a66c2"><path d="M0 1.146C0 .513.526 0 1.175 0h13.65C15.474 0 16 .513 16 1.146v13.708c0 .633-.526 1.146-1.175 1.146H1.175C.526 16 0 15.487 0 14.854zm4.943 12.248V6.169H2.542v7.225zm-1.2-8.212c.837 0 1.358-.554 1.358-1.248-.015-.709-.52-1.248-1.342-1.248S2.4 3.226 2.4 3.934c0 .694.521 1.248 1.327 1.248zm4.908 8.212V9.359c0-.216.016-.432.08-.586.173-.431.568-.878 1.232-.878.869 0 1.216.662 1.216 1.634v3.865h2.401V9.25c0-2.22-1.184-3.252-2.764-3.252-1.274 0-1.845.7-2.165 1.193v.025h-.016l.016-.025V6.169h-2.4c.03.678 0 7.225 0 7.225z"/></svg>''')
gmail_icon = icon_image('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 36">
<path fill="#4285f4" d="M3.273 36h7.636V17.455L0 9.273v23.454C0 34.538 1.467 36 3.273 36"/>
<path fill="#34a853" d="M37.091 36h7.636C46.538 36 48 34.538 48 32.727V9.273l-10.909 8.182"/>
<path fill="#fbbc04" d="M37.091 3.273v14.182L48 9.273V4.909c0-4.046-4.619-6.354-7.855-3.927"/>
<path fill="#ea4335" d="M10.909 17.455V3.273L24 13.091 37.091 3.273v14.182L24 27.273"/>
<path fill="#c5221f" d="M0 4.909v4.364l10.909 8.182V3.273L7.855.982C4.619-1.445 0 .863 0 4.909"/>
</svg>''')
github_icon = icon_image('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="#182536"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8"/></svg>''')

st.html(f'''<aside class="exam-byline" aria-label="자료 출처 및 제작자">
<p><strong>baekenough</strong>가 <a href="https://cdn.kice.re.kr/27dae-suneung/index.html" target="_blank"
rel="noopener noreferrer">한국교육과정평가원 2027학년도 수능 자료</a>에서 받음</p>
<nav aria-label="제작자 연락처">
<button id="exam-share" type="button" aria-label="URL 공유하기" title="URL 공유하기"
data-subject="{' '.join(GROUPS)}" data-provider="{' '.join(PROVIDERS)}"
data-course="{' '.join(key for group in COURSE_OPTIONS.values() for key in group)}">{share_icon}</button>
<a href="https://www.linkedin.com/in/%EC%83%81%EC%9D%B4-%EB%B0%B1-a8b028203/" target="_blank"
rel="noopener noreferrer" aria-label="LinkedIn">
{linkedin_icon}
</a>
<a href="mailto:baekenough@gmail.com" aria-label="Gmail" title="baekenough@gmail.com">
{gmail_icon}</a>
<a href="https://github.com/baekenough" target="_blank" rel="noopener noreferrer" aria-label="GitHub">
{github_icon}
</a><span class="exam-share-status" role="status"></span></nav></aside>''' + '''
<script>
(() => {
    const button = document.getElementById('exam-share');
    const status = button.parentElement.querySelector('.exam-share-status');
    let statusTimer;
    button.onclick = async () => {
        const url = new URL('https://suneung-cat.vercel.app/');
        const current = new URLSearchParams(window.location.search);
        for (const key of ['subject', 'course', 'provider']) {
            const value = current.get(key);
            if (button.dataset[key].split(' ').includes(value)) {
                url.searchParams.set(key, value);
            }
        }
        if (typeof navigator.share === 'function') {
            try {
                await navigator.share({ title: document.title, url: url.href });
                return;
            } catch (error) {
                if (error.name === 'AbortError') return;
            }
        }
        try {
            await navigator.clipboard.writeText(url.href);
            status.textContent = '링크를 복사했습니다.';
            clearTimeout(statusTimer);
            statusTimer = setTimeout(() => { status.textContent = ''; }, 2500);
        } catch {
            window.prompt('공유할 URL을 복사하세요.', url.href);
        }
    };
})();
</script>
''', unsafe_allow_javascript=True)

st.html(f'''<header class="exam-header"><p class="exam-service-name">{SERVICE_NAME}</p><h1>{TITLE}</h1>
<p>선택과목별 원점수 평균으로 순위를 매깁니다. 동점이면 소요시간이 짧은 모델이 앞섭니다.</p></header>''')


def save_subject():
    st.query_params['subject'] = st.session_state.subject
    st.query_params.pop('course', None)


if 'subject' not in st.session_state:
    requested_subject = st.query_params.get('subject', 'korean')
    st.session_state.subject = requested_subject if requested_subject in GROUPS else 'korean'
subject = st.pills('과목', list(GROUPS), key='subject', on_change=save_subject, required=True,
                   format_func=GROUPS.__getitem__, label_visibility='collapsed')


def save_course(key):
    st.query_params['course'] = st.session_state[key]


dataset = subject
if subject in COURSE_OPTIONS:
    options = COURSE_OPTIONS[subject]
    course_key = f'course-{subject}'
    if course_key not in st.session_state:
        requested_course = st.query_params.get('course')
        st.session_state[course_key] = requested_course if requested_course in options else next(iter(options))
    dataset = st.selectbox('탐구 선택과목', list(options), key=course_key, format_func=options.__getitem__,
                           on_change=save_course, args=(course_key,))


def save_provider():
    st.query_params['provider'] = st.session_state.provider


if 'provider' not in st.session_state:
    requested_provider = st.query_params.get('provider', 'all')
    st.session_state.provider = requested_provider if requested_provider in PROVIDERS else 'all'
provider = st.pills('제공사', list(PROVIDERS), key='provider', on_change=save_provider, required=True,
                    format_func=PROVIDERS.__getitem__, label_visibility='collapsed')


def provider_group(model):
    if model['model'].startswith('google/gemini-'):
        return 'gemini'
    if model['model'].startswith('upstage/'):
        return 'upstage'
    endpoint = model['endpoint'] or ''
    host = endpoint.split('/')[2] if '://' in endpoint else ''
    return {'api.openai.com': 'openai', 'api.anthropic.com': 'anthropic',
            'openrouter.ai': 'openrouter', 'api.upstage.ai': 'upstage'}.get(host)


@st.cache_resource
def cloud_scores():
    return BlobLeaderboard(os.environ['CSAT_LEADERBOARD_URL'], os.environ['BLOB_READ_WRITE_TOKEN'])


def board_data(subject_key):
    try:
        snapshot = (cloud_scores().read() if os.environ.get('CSAT_LEADERBOARD_URL')
                    else packaged_leaderboard())
    except (URLError, ValueError, KeyError, TimeoutError):
        return False
    return snapshot.get(subject_key) if snapshot is not None else local_leaderboard(subject_key)


def leaderboard(data, subject_key, selected_provider):
    subject = LABELS[subject_key]
    if data is False:
        st.warning('리더보드 데이터를 다시 불러오는 중입니다.')
        return
    if not data:
        release = ENGLISH_RELEASE if subject_key == 'english' else FOURTH_RELEASE
        if subject_key not in ('korean', 'math') and datetime.now(KST) < release:
            st.info(f'{subject} 공식 자료 공개 예정 · {release:%H:%M} KST')
        else:
            st.info(f'{subject} 문항을 준비 중입니다.')
        return
    if subject_key == 'english':
        st.caption('영어는 공식 듣기 음원도 사용해, 문제 이미지와 오디오를 모두 지원하는 모델만 평가했습니다.')
    models = data['models']
    if not models:
        st.info(f'{subject} {data["questions"]}문항이 준비됐습니다. 모델 평가를 기다리고 있습니다.')
        return
    if selected_provider != 'all':
        models = [model for model in models if provider_group(model) == selected_provider]
    if not models:
        provider_name = PROVIDERS[selected_provider]
        st.info(f'{provider_name}의 영어 평가 결과가 없습니다.' if subject_key == 'english'
                else f'{subject}의 {provider_name} 평가 결과를 준비 중입니다.')
        return

    cases = []
    for case in data['cases']:
        form, course = case.split(' ', 1)
        label = form if course == '공통' else f'{form[:2]} {SHORT_COURSES.get(course, course)}'
        cases.append((case, label))
    rows = []
    for model in models:
        mean = model['mean_score']
        scores = []
        for case, label in cases:
            points = model['scores'][case]
            value = points if points is not None else '–'
            scores.append(f'<td class="case" data-label="{escape(label)}">{value}</td>')
        average = f'{mean:.2f}' if mean is not None else '–'
        rank = model['rank'] or '–'
        elapsed = model['elapsed_seconds']
        duration = f'{elapsed:,.2f}초' if elapsed is not None else '–'
        badge = 'first' if rank == 1 else ''
        group = provider_group(model)
        route = PROVIDERS.get(group, '')
        if group in ('openai', 'anthropic') or (group == 'upstage' and not model['model'].startswith('upstage/')):
            route += ' API'
        rows.append(f'''<tr><td class="rank"><strong class="{badge}">{rank}</strong></td>
<td class="name">{escape(model['model'])}<small class="route">{route}</small></td>
<td class="score" data-label="평균">{average}</td>
<td class="elapsed" data-label="소요시간">{duration}</td>{''.join(scores)}</tr>''')
    headings = ''.join(f'<th scope="col">{escape(label)}</th>' for _, label in cases)
    update = datetime.fromtimestamp(data['updated_at'], KST).strftime('%H:%M:%S')
    st.html(f'''<section class="exam-board" aria-label="{subject} 리더보드" data-cases="{len(cases)}">
<header class="exam-board__header"><h2>{subject} 모델 순위</h2>
<span class="exam-board__status">{len(models)}개 모델 · {update} 갱신</span></header>
<div class="exam-board__table"><table aria-label="수능 {subject} 모델 순위">
<colgroup><col class="rank"><col class="name"><col class="score"><col class="elapsed">{'<col>' * len(cases)}</colgroup>
<thead><tr><th class="rank" scope="col">순위</th><th class="name" scope="col">모델</th>
<th scope="col">평균 / {data.get('max_score', 100)}</th><th class="elapsed" scope="col">소요시간</th>{headings}</tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>
<p class="exam-note">2초마다 갱신합니다. 소요시간은 첫 요청부터 마지막 채점 응답까지입니다.</p>''')
    if analysis := data.get('analysis'):
        with st.expander('채점 분석'):
            st.markdown('\n'.join(f'- {line}' for line in analysis_markdown(analysis)))


@st.fragment(run_every=REFRESH_SECONDS)
def watch_board(subject_key, displayed_data):
    if board_data(subject_key) != displayed_data:
        st.rerun()


data = board_data(dataset)
leaderboard(data, dataset, provider)
watch_board(dataset, data)
