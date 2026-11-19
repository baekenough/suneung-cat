from datetime import datetime
from html import escape

import streamlit as st

from benchmark import FORMS, ROOT, comparison_config, format_duration, read_json, run_directories, summarize

TITLE = '2027학년도 수능 풀이 모델 리더보드'
SUBJECTS = {'korean': '국어', 'math': '수학'}
KOREAN_CASES = [('홀수형 화법과 작문', '홀수 화작'), ('홀수형 언어와 매체', '홀수 언매'),
                ('짝수형 화법과 작문', '짝수 화작'), ('짝수형 언어와 매체', '짝수 언매')]

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
st.html(f'''<header class="exam-header"><h1>{TITLE}</h1>
<p>홀수형·짝수형의 선택과목별 100점 원점수 평균으로 비교합니다.</p></header>''')


def save_subject():
    st.query_params['subject'] = st.session_state.subject


if 'subject' not in st.session_state:
    requested_subject = st.query_params.get('subject', 'korean')
    st.session_state.subject = requested_subject if requested_subject in SUBJECTS else 'korean'
subject = st.radio('과목', list(SUBJECTS), key='subject', on_change=save_subject,
                   format_func=SUBJECTS.__getitem__, horizontal=True, label_visibility='collapsed')


def provider_label(endpoint):
    if not endpoint:
        return ''
    host = endpoint.split('/')[2] if '://' in endpoint else ''
    return {'api.openai.com': 'OpenAI API', 'api.anthropic.com': 'Anthropic API',
            'openrouter.ai': 'OpenRouter', 'api.upstage.ai': 'Upstage API'}.get(host, '')


@st.fragment(run_every=2)
def leaderboard(subject):
    output = ROOT / 'output' / ('2027' if subject == '국어' else '2027-math')
    dataset = output / 'questions.json'
    if not dataset.exists() or not (output / 'answer_key.json').exists():
        st.info(f'{subject} 문항을 준비 중입니다.')
        return
    data = read_json(dataset)
    key = read_json(output / 'answer_key.json')
    config = comparison_config(data, key, 'medium')
    directories = run_directories(output, config)
    models = summarize(directories, data, key['answers'], config)['models']
    if not models:
        st.info(f'{subject} {len(data["questions"])}문항 준비 완료. 평가를 시작하면 진행률이 표시됩니다.')
        return

    cases = KOREAN_CASES if subject == '국어' else [
        (f'{form} {course}', f'{form[:2]} {course}')
        for form in FORMS for course in data['electives']
    ]
    rows = []
    for model in models:
        submitted = model['overall']['solved']
        total = model['overall']['questions']
        mean = model['mean_score']
        scores = []
        for case, label in cases:
            result = model['scores'][case]
            value = result['points'] if result['solved'] == result['questions'] else '–'
            scores.append(f'<td class="case" data-label="{escape(label)}">{value}</td>')
        average = f'{mean:.2f}' if mean is not None else '–'
        rank = model['rank'] or '–'
        badge = 'first' if rank == 1 else ''
        route = provider_label(model['endpoint'])
        rows.append(f'''<tr><td class="rank"><strong class="{badge}">{rank}</strong></td>
<td class="name">{escape(model['model'])}<small class="route">{route}</small></td>
<td class="score" data-label="평균">{average}</td>
<td class="progress" data-label="채점 완료">{submitted}/{total}<progress value="{submitted}" max="{total}" aria-label="채점 진행률"></progress></td>
<td class="elapsed" data-label="소요시간">{format_duration(model['elapsed_seconds'])}</td>{''.join(scores)}</tr>''')
    headings = ''.join(f'<th scope="col">{escape(label)}</th>' for _, label in cases)
    latest = max((p.stat().st_mtime for d in directories for p in d.glob('*.json')), default=0)
    complete = sum(model['mean_score'] is not None for model in models)
    update = datetime.fromtimestamp(latest).strftime('%H:%M:%S')
    st.html(f'''<section class="exam-board" aria-label="{subject} 리더보드">
<header class="exam-board__header"><h2>{subject} 모델 순위</h2>
<span class="exam-board__status">{complete}/{len(models)}개 모델 완료 · {update} 갱신</span></header>
<div class="exam-board__table"><table aria-label="수능 {subject} 모델 순위">
<thead><tr><th class="rank" scope="col">순위</th><th class="name" scope="col">모델</th>
<th scope="col">평균</th><th class="progress" scope="col">채점 완료</th><th scope="col">소요시간</th>{headings}</tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>
<p class="exam-note">2초마다 갱신합니다. 소요시간은 첫 요청부터 마지막 채점 응답까지입니다.</p>''')


leaderboard(SUBJECTS[subject])
