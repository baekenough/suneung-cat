from datetime import datetime, timedelta, timezone
from html import escape
import base64
import os
from urllib.error import URLError

import streamlit as st

from benchmark import format_duration
from leaderboard_data import hosted_leaderboard, local_leaderboard

TITLE = '2027학년도 수능 풀이 모델 리더보드'
SUBJECTS = {'korean': '국어', 'math': '수학'}
SHORT_COURSES = {'화법과 작문': '화작', '언어와 매체': '언매'}
PROVIDERS = {'all': '전체', 'openai': 'OpenAI', 'anthropic': 'Anthropic',
             'gemini': 'Gemini', 'openrouter': 'OpenRouter', 'upstage': 'Upstage'}
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title=TITLE, layout='wide')
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
.st-key-subject [role="radiogroup"] { gap: .45rem; }
.st-key-subject label { background: #fff; padding: .45rem .8rem; border: 1px solid #b6bec9;
                        border-radius: 8px; min-width: 76px; color: #161d26; }
.st-key-subject label:has(input:checked) { background: #eaf5ff; border-color: #0972d3; color: #033160; }
.st-key-subject label:has(input:checked) > div:first-child { background-color: #0972d3; border-color: #0972d3; }
.st-key-subject label:focus-within { outline: 2px solid #0972d3; outline-offset: 2px; }
.st-key-provider button { background: #fff; color: #20364d; border-color: #c4ccd7; font-size: .84rem; }
.st-key-provider button[aria-checked="true"], .st-key-provider button[aria-pressed="true"] {
    background: #eaf5ff; color: #064a88; border-color: #0972d3; }
.exam-board { border: 1px solid #d5dae1; background: #fff; overflow: hidden; }
.exam-board__header { padding: 16px 20px; display: flex; flex-wrap: wrap; gap: 8px 16px;
                      justify-content: space-between; align-items: baseline; }
.exam-board__header h2 { font-size: 1.125rem; margin: 0; padding: 0; color: #161d26; }
.exam-board__status { color: #46566b; font-size: .82rem; }
.exam-board__table { overflow-x: auto; }
.exam-board table { width: 100%; min-width: 760px; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.exam-board th, .exam-board td { padding: 12px 13px; border-block-start: 1px solid #e2e5eb; text-align: right; }
.exam-board th { background: #f3f5f7; color: #36465a; font-size: .76rem; white-space: nowrap; }
.exam-board td { color: #26384d; font-size: .88rem; }
.exam-board tbody tr:hover { background: #f2f8fd; }
.exam-board .name { text-align: left; font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
                   overflow-wrap: anywhere; font-weight: 650; color: #13253a; }
.exam-board .rank { text-align: center; width: 48px; }
.exam-board .rank strong { display: inline-block; min-width: 1.6rem; padding: .1rem .25rem;
                           border-radius: 4px; background: #edf1f6; color: #34475d; }
.exam-board .rank .first { color: #814800; background: #ffefd1; }
.exam-board .score { font-weight: 750; color: #07559e; white-space: nowrap; }
.exam-board .elapsed { white-space: nowrap; }
.exam-board .progress { min-width: 105px; text-align: left; white-space: nowrap; }
.exam-board progress { display: block; width: 100%; height: 5px; accent-color: #0972d3; margin-top: 6px; }
.exam-board .route { display: block; color: #536678; font: 400 .73rem system-ui, sans-serif; margin-top: 2px; }
.exam-note { color: #536678; font-size: .82rem; margin: .75rem 0 0; }
.exam-byline { color: #46566b;
               display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
               font-size: .84rem; gap: 8px 16px; }
.exam-byline p { margin: 0; }
.exam-byline nav { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; }
.exam-byline nav a { display: inline-flex; align-items: center; justify-content: center;
                     width: 42px; height: 42px; border: 1px solid #d5dae1; border-radius: 8px;
                     background: #fff; color: #182536; text-decoration: none; }
.exam-byline nav a:hover { background: #eaf5ff; border-color: #87b6e3; }
.exam-byline a:focus-visible { outline: 2px solid #0972d3; outline-offset: 2px; }
.exam-byline img { width: 20px; height: 20px; flex-shrink: 0; }
@media (max-width: 810px) {
    .stMainBlockContainer { padding: 1.25rem .85rem; }
    .exam-header { padding: 19px 18px; }
    .exam-board__header { padding: 13px 1px; }
    .exam-board { border: 0; background: transparent; }
    .exam-board__table { overflow: visible; }
    .exam-board table, .exam-board tbody { display: block; min-width: 0; }
    .exam-board thead { position: absolute; width: 1px; height: 1px; overflow: hidden;
                       clip-path: inset(50%); white-space: nowrap; }
    .exam-board tbody tr { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); column-gap: 10px;
                          background: #fff; border: 1px solid #d5dae1; border-radius: 10px;
                          padding: 10px 13px; margin-bottom: 9px; }
    .exam-board tbody tr:hover { background: #fff; }
    .exam-board td { text-align: left; padding: 7px 0; border: 0; grid-column: span 2; }
    .exam-board td::before { display: block; content: attr(data-label); color: #536678; font-size: .7rem;
                             white-space: nowrap; font-weight: 400; margin-bottom: 2px; }
    .exam-board .rank { width: auto; grid-column: 1; text-align: left; }
    .exam-board .name { grid-column: 2 / -1; }
    .exam-board .progress { min-width: 0; }
    .exam-board .case { border-block-start: 1px solid #e2e5eb; }
    .exam-board .rank::before, .exam-board .name::before { content: none; }
}
</style>
''')
# LinkedIn and GitHub marks follow Bootstrap Icons vector paths.
def brand_icon(svg):
    encoded = base64.b64encode(svg.encode()).decode()
    return f'<img alt="" src="data:image/svg+xml;base64,{encoded}">'

linkedin_icon = brand_icon('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="#0a66c2"><path d="M0 1.146C0 .513.526 0 1.175 0h13.65C15.474 0 16 .513 16 1.146v13.708c0 .633-.526 1.146-1.175 1.146H1.175C.526 16 0 15.487 0 14.854zm4.943 12.248V6.169H2.542v7.225zm-1.2-8.212c.837 0 1.358-.554 1.358-1.248-.015-.709-.52-1.248-1.342-1.248S2.4 3.226 2.4 3.934c0 .694.521 1.248 1.327 1.248zm4.908 8.212V9.359c0-.216.016-.432.08-.586.173-.431.568-.878 1.232-.878.869 0 1.216.662 1.216 1.634v3.865h2.401V9.25c0-2.22-1.184-3.252-2.764-3.252-1.274 0-1.845.7-2.165 1.193v.025h-.016l.016-.025V6.169h-2.4c.03.678 0 7.225 0 7.225z"/></svg>''')
gmail_icon = brand_icon('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 36">
<path fill="#4285f4" d="M3.273 36h7.636V17.455L0 9.273v23.454C0 34.538 1.467 36 3.273 36"/>
<path fill="#34a853" d="M37.091 36h7.636C46.538 36 48 34.538 48 32.727V9.273l-10.909 8.182"/>
<path fill="#fbbc04" d="M37.091 3.273v14.182L48 9.273V4.909c0-4.046-4.619-6.354-7.855-3.927"/>
<path fill="#ea4335" d="M10.909 17.455V3.273L24 13.091 37.091 3.273v14.182L24 27.273"/>
<path fill="#c5221f" d="M0 4.909v4.364l10.909 8.182V3.273L7.855.982C4.619-1.445 0 .863 0 4.909"/>
</svg>''')
github_icon = brand_icon('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="#182536"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8"/></svg>''')

st.html(f'''<aside class="exam-byline" aria-label="자료 출처 및 제작자">
<p><strong>baekenough</strong>가 <a href="https://cdn.kice.re.kr/27dae-suneung/index.html" target="_blank"
rel="noopener noreferrer">한국교육과정평가원 2027학년도 수능 자료</a>에서 받음</p>
<nav aria-label="제작자 연락처">
<a href="https://www.linkedin.com/in/%EC%83%81%EC%9D%B4-%EB%B0%B1-a8b028203/" target="_blank"
rel="noopener noreferrer" aria-label="LinkedIn">
{linkedin_icon}
</a>
<a href="mailto:baekenough@gmail.com" aria-label="Gmail" title="baekenough@gmail.com">
{gmail_icon}</a>
<a href="https://github.com/baekenough" target="_blank" rel="noopener noreferrer" aria-label="GitHub">
{github_icon}
</a></nav></aside>''')

st.html(f'''<header class="exam-header"><h1>{TITLE}</h1>
<p>선택과목별 원점수 평균으로 순위를 매깁니다. 동점이면 소요시간이 짧은 모델이 앞섭니다.</p></header>''')


def save_subject():
    st.query_params['subject'] = st.session_state.subject


if 'subject' not in st.session_state:
    requested_subject = st.query_params.get('subject', 'korean')
    st.session_state.subject = requested_subject if requested_subject in SUBJECTS else 'korean'
subject = st.radio('과목', list(SUBJECTS), key='subject', on_change=save_subject,
                   format_func=SUBJECTS.__getitem__, horizontal=True, label_visibility='collapsed')


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


@st.cache_data(ttl=2, show_spinner=False)
def cloud_scores():
    return hosted_leaderboard()


@st.fragment(run_every=2)
def leaderboard(subject_key, selected_provider):
    subject = SUBJECTS[subject_key]
    try:
        snapshot = cloud_scores() if os.environ.get('CSAT_LEADERBOARD_URL') else hosted_leaderboard()
    except (URLError, ValueError, KeyError, TimeoutError):
        st.warning('리더보드 데이터를 다시 불러오는 중입니다.')
        return
    data = snapshot.get(subject_key) if snapshot is not None else local_leaderboard(subject_key)
    if not data:
        st.info(f'{subject} 문항을 준비 중입니다.')
        return
    models = data['models']
    if not models:
        st.info(f'{subject} {data["questions"]}문항 준비 완료. 평가를 시작하면 진행률이 표시됩니다.')
        return
    if selected_provider != 'all':
        models = [model for model in models if provider_group(model) == selected_provider]
    if not models:
        st.info(f'{subject}의 {PROVIDERS[selected_provider]} 평가 결과를 준비 중입니다.')
        return

    cases = []
    for case in data['cases']:
        form, course = case.split(' ', 1)
        cases.append((case, f'{form[:2]} {SHORT_COURSES.get(course, course)}'))
    rows = []
    for model in models:
        submitted = model['solved']
        total = model['questions']
        mean = model['mean_score']
        scores = []
        for case, label in cases:
            points = model['scores'][case]
            value = points if points is not None else '–'
            scores.append(f'<td class="case" data-label="{escape(label)}">{value}</td>')
        average = f'{mean:.2f}' if mean is not None else '–'
        rank = model['rank'] or '–'
        badge = 'first' if rank == 1 else ''
        group = provider_group(model)
        route = PROVIDERS.get(group, '')
        if group in ('openai', 'anthropic') or (group == 'upstage' and not model['model'].startswith('upstage/')):
            route += ' API'
        rows.append(f'''<tr><td class="rank"><strong class="{badge}">{rank}</strong></td>
<td class="name">{escape(model['model'])}<small class="route">{route}</small></td>
<td class="score" data-label="평균">{average}</td>
<td class="progress" data-label="채점 완료">{submitted}/{total}<progress value="{submitted}" max="{total}" aria-label="채점 진행률"></progress></td>
<td class="elapsed" data-label="소요시간">{format_duration(model['elapsed_seconds'])}</td>{''.join(scores)}</tr>''')
    headings = ''.join(f'<th scope="col">{escape(label)}</th>' for _, label in cases)
    complete = sum(model['mean_score'] is not None for model in models)
    update = datetime.fromtimestamp(data['updated_at'], KST).strftime('%H:%M:%S')
    st.html(f'''<section class="exam-board" aria-label="{subject} 리더보드">
<header class="exam-board__header"><h2>{subject} 모델 순위</h2>
<span class="exam-board__status">{complete}/{len(models)}개 모델 완료 · {update} 갱신</span></header>
<div class="exam-board__table"><table aria-label="수능 {subject} 모델 순위">
<thead><tr><th class="rank" scope="col">순위</th><th class="name" scope="col">모델</th>
<th scope="col">평균</th><th class="progress" scope="col">채점 완료</th><th scope="col">소요시간</th>{headings}</tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>
<p class="exam-note">2초마다 갱신합니다. 소요시간은 첫 요청부터 마지막 채점 응답까지입니다.</p>''')


leaderboard(subject, provider)
