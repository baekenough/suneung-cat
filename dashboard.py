from datetime import datetime
from html import escape
import base64
import os
from pathlib import Path
from urllib.error import URLError

import streamlit as st

from exam_analysis import markdown as analysis_markdown
from leaderboard_data import BlobLeaderboard, REFRESH_SECONDS, local_leaderboard, packaged_leaderboard
from site_config import FRONTIER_MODELS, PROVIDER_HOSTS, PROVIDERS, SERVICE_NAME, SHORT_COURSES, TITLE
from subjects_catalog import COURSE_OPTIONS, ENGLISH_RELEASE, FOURTH_RELEASE, GROUPS, KST, LABELS

SITE_DIR = Path(__file__).resolve().parent / 'site'
CLOUD_LEADERBOARD_URL = os.environ.get('CSAT_LEADERBOARD_URL')
VIEW_REFRESH_SECONDS = 10 if CLOUD_LEADERBOARD_URL else REFRESH_SECONDS

st.set_page_config(page_title=f'{SERVICE_NAME} · {TITLE}', layout='wide')
st.html('<style>' + (SITE_DIR / 'leaderboard.css').read_text(encoding='utf-8') + '</style>')
# LinkedIn and GitHub marks follow Bootstrap Icons vector paths.
def icon_image(name):
    encoded = base64.b64encode((SITE_DIR / name).read_bytes()).decode()
    return f'<img alt="" src="data:image/svg+xml;base64,{encoded}">'

share_icon = icon_image('icons/share.svg')
linkedin_icon = icon_image('icons/linkedin.svg')
gmail_icon = icon_image('icons/gmail.svg')
github_icon = icon_image('icons/github.svg')

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
        if (current.get('hide_frontier') === '1') {
            url.searchParams.set('hide_frontier', '1');
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


def save_frontier_visibility():
    if st.session_state.hide_frontier:
        st.query_params['hide_frontier'] = '1'
    else:
        st.query_params.pop('hide_frontier', None)


if 'hide_frontier' not in st.session_state:
    st.session_state.hide_frontier = st.query_params.get('hide_frontier') == '1'
hide_frontier = st.checkbox('프론티어 모델 숨기기', key='hide_frontier', on_change=save_frontier_visibility,
                            help='숨기는 모델 · ' + ', '.join(sorted(FRONTIER_MODELS)))


def provider_group(model):
    if model['model'].startswith('google/gemini-'):
        return 'gemini'
    if model['model'].startswith('upstage/'):
        return 'upstage'
    endpoint = model['endpoint'] or ''
    host = endpoint.split('/')[2] if '://' in endpoint else ''
    return PROVIDER_HOSTS.get(host)


@st.cache_resource
def cloud_scores():
    return BlobLeaderboard(CLOUD_LEADERBOARD_URL, os.environ['BLOB_READ_WRITE_TOKEN'], VIEW_REFRESH_SECONDS)


def board_data(subject_key):
    try:
        snapshot = cloud_scores().read() if CLOUD_LEADERBOARD_URL else packaged_leaderboard()
    except (URLError, ValueError, KeyError, TimeoutError):
        return False
    return snapshot.get(subject_key) if snapshot is not None else local_leaderboard(subject_key)


def leaderboard(data, subject_key, selected_provider, hide_frontier):
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
    if hide_frontier:
        models = [model for model in models if model['model'] not in FRONTIER_MODELS]
        if not models:
            st.info('이 필터에서 표시할 모델이 없습니다. 프론티어 모델 숨기기를 해제하면 결과를 볼 수 있습니다.')
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
<p class="exam-note">{VIEW_REFRESH_SECONDS}초마다 갱신합니다. 소요시간은 첫 요청부터 마지막 채점 응답까지입니다.</p>''')
    includes_hidden_models = hide_frontier and any(row['model'] in FRONTIER_MODELS for row in data['models'])
    if not includes_hidden_models and (analysis := data.get('analysis')):
        with st.expander('채점 분석'):
            st.markdown('\n'.join(f'- {line}' for line in analysis_markdown(analysis)))


@st.fragment(run_every=VIEW_REFRESH_SECONDS)
def watch_board(subject_key, displayed_data):
    if board_data(subject_key) != displayed_data:
        st.rerun()


data = board_data(dataset)
leaderboard(data, dataset, provider, hide_frontier)
watch_board(dataset, data)
