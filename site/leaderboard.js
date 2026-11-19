import catalog from './catalog.js';

const REFRESH_MS = 10_000;
const byId = id => document.getElementById(id);
const content = byId('exam-content');
const course = byId('exam-course');
const frontier = byId('hide-frontier');
const snapshots = new Map();
const pending = new Set();
const clock = new Intl.DateTimeFormat('ko-KR', {timeZone: 'Asia/Seoul', hourCycle: 'h23',
  hour: '2-digit', minute: '2-digit', second: '2-digit'});
const number = new Intl.NumberFormat('ko-KR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
let state = readLocation();
let courseGroup;
let shownDataset;

function readLocation() {
  const params = new URLSearchParams(location.search);
  const subject = Object.hasOwn(catalog.groups, params.get('subject')) ? params.get('subject') : 'korean';
  const choices = catalog.courses[subject] ?? {};
  const selectedCourse = Object.hasOwn(choices, params.get('course')) ? params.get('course') : Object.keys(choices)[0];
  const provider = Object.hasOwn(catalog.providers, params.get('provider')) ? params.get('provider') : 'all';
  return {subject, course: selectedCourse, provider, hideFrontier: params.get('hide_frontier') === '1'};
}

function selectionParams() {
  const params = new URLSearchParams({subject: state.subject});
  if (state.course) params.set('course', state.course);
  if (state.provider !== 'all') params.set('provider', state.provider);
  if (state.hideFrontier) params.set('hide_frontier', '1');
  return params;
}

function buttons(className, values, onPick) {
  const group = document.querySelector(className);
  return Object.entries(values).map(([key, title]) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.key = key;
    button.textContent = title;
    button.addEventListener('click', () => onPick(key));
    group.append(button);
    return button;
  });
}

const subjectButtons = buttons('.exam-subjects', catalog.groups, subject => {
  if (subject !== state.subject) update({subject, course: Object.keys(catalog.courses[subject] ?? {})[0]});
});
const providerButtons = buttons('.exam-providers', catalog.providers, provider => update({provider}));
course.addEventListener('change', () => update({course: course.value}));
frontier.title = '숨기는 모델 · ' + catalog.frontier.join(', ');
frontier.addEventListener('change', () => update({hideFrontier: frontier.checked}));
window.addEventListener('popstate', () => {
  state = readLocation();
  syncControls();
  render();
  refresh();
});

function syncControls() {
  for (const button of subjectButtons) button.setAttribute('aria-pressed', button.dataset.key === state.subject);
  for (const button of providerButtons) button.setAttribute('aria-pressed', button.dataset.key === state.provider);
  if (courseGroup !== state.subject) {
    const choices = Object.entries(catalog.courses[state.subject] ?? {});
    course.replaceChildren(...choices.map(([value, title]) => new Option(title, value)));
    course.parentElement.hidden = choices.length === 0;
    courseGroup = state.subject;
  }
  if (state.course) course.value = state.course;
  frontier.checked = state.hideFrontier;
}

function update(changes) {
  const previous = dataset();
  state = {...state, ...changes};
  history.replaceState(null, '', '?' + selectionParams());
  syncControls();
  render();
  if (previous !== dataset()) refresh();
}

function dataset() {
  return state.course || state.subject;
}

function escape(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

function providerOf({model, endpoint}) {
  if (model.startsWith('google/gemini-')) return 'gemini';
  if (model.startsWith('upstage/')) return 'upstage';
  try {
    return catalog.providerHosts[new URL(endpoint).hostname];
  } catch {
    return undefined;
  }
}

function caseLabel(label) {
  const index = label.indexOf(' ');
  const form = label.slice(0, index);
  const elective = label.slice(index + 1);
  return elective === '공통' ? form : form.slice(0, 2) + ' ' + (catalog.shortCourses[elective] ?? elective);
}

function message(text) {
  return `<p class="exam-message" role="status">${escape(text)}</p>`;
}

function points(value) {
  return Number.isFinite(value) ? number.format(value) : '–';
}

function tableRow(model, cases) {
  const group = providerOf(model);
  let route = catalog.providers[group] ?? '';
  if (group === 'openai' || group === 'anthropic' || (group === 'upstage' && !model.model.startsWith('upstage/'))) {
    route += ' API';
  }
  const casesHtml = cases.map(key =>
    `<td class="case" data-label="${escape(caseLabel(key))}">${escape(model.scores[key] ?? '–')}</td>`).join('');
  const duration = model.elapsed_seconds == null ? '–' : points(model.elapsed_seconds) + '초';
  return `<tr><td class="rank"><strong class="${model.rank === 1 ? 'first' : ''}">${model.rank ?? '–'}</strong></td>
    <td class="name">${escape(model.model)}<small class="route">${escape(route)}</small></td>
    <td class="score" data-label="평균">${points(model.mean_score)}</td>
    <td class="elapsed" data-label="소요시간">${duration}</td>${casesHtml}</tr>`;
}

function analysisDetails(analysis, expanded) {
  const lines = [`완료 모델 ${analysis.completed}/${analysis.registered}개 · 1위 <code>${escape(analysis.winner)}</code>
    ${points(analysis.top_score)}점 · 중앙값 ${points(analysis.median_score)}점 · 최고–최저 ${points(analysis.score_span)}점`];
  if (analysis.fastest) {
    lines.push(`최단 소요시간 <code>${escape(analysis.fastest.model)}</code> ${points(analysis.fastest.seconds)}초`);
  }
  if (analysis.sections.length) {
    lines.push('배점 기준 득점률 · ' + analysis.sections.map(row => `${escape(row.name)} ${points(row.percent)}%`).join(' · '));
  }
  if (analysis.hard_items.length) {
    lines.push('오답이 많은 문항 · ' + analysis.hard_items.map(row =>
      `${escape(row.form)} ${escape(row.section)} ${row.number}번 ${row.missed}/${analysis.completed}개 모델`).join(' · '));
  }
  return `<details class="exam-analysis"${expanded ? ' open' : ''}><summary>채점 분석</summary>
    <ul>${lines.map(line => `<li>${line}</li>`).join('')}</ul></details>`;
}

function render() {
  const key = dataset();
  const subject = catalog.labels[key];
  const entry = snapshots.get(key);
  const board = entry?.board;
  const expanded = shownDataset === key && content.querySelector('details')?.open;
  shownDataset = key;
  if (!entry || entry.error) {
    content.innerHTML = message(entry?.error ? '리더보드 데이터를 다시 불러오는 중입니다.' : '리더보드를 불러오는 중입니다.');
    return;
  }
  if (!board) {
    const release = new Date(catalog.release[key === 'english' ? 'english' : 'fourth']);
    content.innerHTML = message(!['korean', 'math'].includes(key) && Date.now() < release
      ? `${subject} 공식 자료 공개 예정 · ${clock.format(release).slice(0, 5)} KST`
      : `${subject} 문항을 준비 중입니다.`);
    return;
  }
  const description = key === 'english'
    ? '<p class="exam-note">영어는 공식 듣기 음원도 사용해, 문제 이미지와 오디오를 모두 지원하는 모델만 평가했습니다.</p>'
    : '';
  if (!board.models.length) {
    content.innerHTML = description + message(`${subject} ${board.questions}문항이 준비됐습니다. 모델 평가를 기다리고 있습니다.`);
    return;
  }
  let models = state.provider === 'all' ? board.models : board.models.filter(model => providerOf(model) === state.provider);
  if (!models.length) {
    const provider = catalog.providers[state.provider];
    content.innerHTML = description + message(key === 'english' ? `${provider}의 영어 평가 결과가 없습니다.`
      : `${subject}의 ${provider} 평가 결과를 준비 중입니다.`);
    return;
  }
  if (state.hideFrontier) models = models.filter(model => !catalog.frontier.includes(model.model));
  if (!models.length) {
    content.innerHTML = description + message('이 필터에서 표시할 모델이 없습니다. 프론티어 모델 숨기기를 해제하면 결과를 볼 수 있습니다.');
    return;
  }
  const headers = board.cases.map(key => `<th scope="col">${escape(caseLabel(key))}</th>`).join('');
  const html = `<section class="exam-board" aria-label="${escape(subject)} 리더보드" data-cases="${board.cases.length}">
    <header class="exam-board__header"><h2>${escape(subject)} 모델 순위</h2>
      <span class="exam-board__status">${models.length}개 모델 · ${clock.format(board.updated_at * 1000)} 갱신</span></header>
    <div class="exam-board__table"><table aria-label="수능 ${escape(subject)} 모델 순위">
      <colgroup><col class="rank"><col class="name"><col class="score"><col class="elapsed">${'<col>'.repeat(board.cases.length)}</colgroup>
      <thead><tr><th class="rank" scope="col">순위</th><th class="name" scope="col">모델</th>
        <th scope="col">평균 / ${board.max_score}</th><th class="elapsed" scope="col">소요시간</th>${headers}</tr></thead>
      <tbody>${models.map(model => tableRow(model, board.cases)).join('')}</tbody></table></div></section>
    <p class="exam-note">10초마다 갱신합니다. 소요시간은 첫 요청부터 마지막 채점 응답까지입니다.</p>`;
  const includesHiddenModels = state.hideFrontier && board.models.some(model => catalog.frontier.includes(model.model));
  content.innerHTML = description + html + (board.analysis && !includesHiddenModels ? analysisDetails(board.analysis, expanded) : '');
}

async function refresh() {
  const key = dataset();
  if (document.hidden || pending.has(key)) return;
  pending.add(key);
  try {
    const response = await fetch('/api/leaderboard?subject=' + encodeURIComponent(key), {credentials: 'omit'});
    if (response.status === 304) return;
    if (!response.ok) throw new Error('Leaderboard temporarily unavailable');
    const raw = await response.text();
    if (snapshots.get(key)?.raw !== raw) {
      snapshots.set(key, {raw, board: JSON.parse(raw)});
      if (key === dataset()) render();
    }
  } catch {
    if (!snapshots.has(key)) {
      snapshots.set(key, {error: true});
      if (key === dataset()) render();
    }
  } finally {
    pending.delete(key);
  }
}

let shareTimer;
byId('exam-share').onclick = async () => {
  const url = 'https://suneung-cat.vercel.app/?' + selectionParams();
  if (typeof navigator.share === 'function') {
    try {
      await navigator.share({title: document.title, url});
      return;
    } catch (error) {
      if (error.name === 'AbortError') return;
    }
  }
  try {
    await navigator.clipboard.writeText(url);
    const status = document.querySelector('.exam-share-status');
    status.textContent = '링크를 복사했습니다.';
    clearTimeout(shareTimer);
    shareTimer = setTimeout(() => { status.textContent = ''; }, 2500);
  } catch {
    window.prompt('공유할 URL을 복사하세요.', url);
  }
};

syncControls();
refresh();
setInterval(refresh, REFRESH_MS);
document.addEventListener('visibilitychange', refresh);
