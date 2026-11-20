import catalog from './catalog.js';

const REFRESH_MS = 10_000;
const pages = {overview: '종합', ...catalog.groups};
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
  const subject = Object.hasOwn(pages, params.get('subject')) ? params.get('subject') : 'overview';
  const choices = catalog.courses[subject] ?? {};
  const selectedCourse = Object.hasOwn(choices, params.get('course')) ? params.get('course') : Object.keys(choices)[0];
  const provider = Object.hasOwn(catalog.providers, params.get('provider')) ? params.get('provider') : 'all';
  return {subject, course: selectedCourse, provider, hideFrontier: params.get('hide_frontier') === '1'};
}

function selectionHref(subject, selectedCourse) {
  const params = new URLSearchParams();
  if (subject !== 'overview') params.set('subject', subject);
  if (selectedCourse) params.set('course', selectedCourse);
  if (state.provider !== 'all') params.set('provider', state.provider);
  if (state.hideFrontier) params.set('hide_frontier', '1');
  const query = params.toString();
  return query ? '/?' + query : '/';
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

const subjectButtons = buttons('.exam-subjects', pages, subject => {
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
  history.replaceState(null, '', selectionHref(state.subject, state.course));
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

function visibleModels(models) {
  return models.filter(model => (state.provider === 'all' || providerOf(model) === state.provider)
    && (!state.hideFrontier || !catalog.frontier.includes(model.model)));
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

function overviewLink(key, group, board, completed, compact) {
  const winner = completed[0];
  const title = catalog.labels[key];
  const href = selectionHref(group, key === group ? undefined : key);
  const count = winner ? completed.filter(model => model.rank === winner.rank).length : 0;
  const model = winner ? escape(winner.model) + (count > 1 ? ` 외 ${count - 1}개` : '') : '완료 결과 대기';
  const score = winner ? `<strong>${points(winner.mean_score)}</strong><small> / ${board.max_score}점</small>` : '–';
  const elapsed = winner && Number.isFinite(winner.elapsed_seconds) ? `<span>${points(winner.elapsed_seconds)}초</span>` : '';
  return `<a class="overview-course${compact ? ' overview-course--compact' : ''}" href="${escape(href)}">
    <span class="overview-course-title">${escape(title)}</span>
    <span class="overview-model">${model}</span>
    <span class="overview-score">${score}${elapsed}</span></a>`;
}

function overviewDashboard(boards) {
  const ranked = new Map();
  const appearances = new Map();
  const wins = new Map();
  let registered = 0;
  let completedCount = 0;
  let scoredCourses = 0;
  let updated = 0;

  for (const [key, board] of Object.entries(boards)) {
    const models = visibleModels(board.models);
    const completed = models.filter(model => model.rank != null);
    ranked.set(key, completed);
    registered += models.length;
    completedCount += completed.length;
    if (completed.length) scoredCourses++;
    updated = Math.max(updated, board.updated_at);
    for (const {model} of models) {
      if (!appearances.has(model)) appearances.set(model, 0);
    }
    for (const {model, rank} of completed) {
      appearances.set(model, appearances.get(model) + 1);
      if (rank === completed[0].rank) wins.set(model, (wins.get(model) ?? 0) + 1);
    }
  }

  const primary = Object.keys(catalog.groups).filter(key => !catalog.courses[key]);
  const highlights = [...wins].sort(([a, aWins], [b, bWins]) => bWins - aWins ||
      appearances.get(b) - appearances.get(a) || a.localeCompare(b)).slice(0, 5);
  const update = updated ? `<span class="exam-board__status">${clock.format(updated * 1000)} 갱신 · 10초마다 확인</span>` : '';
  const courses = (keys, group) => keys.map(key => overviewLink(
    key, group ?? key, boards[key], ranked.get(key) ?? [], Boolean(group))).join('');
  const filterNote = state.provider !== 'all' || state.hideFrontier
    ? '<span class="exam-board__status">선택한 필터 기준</span>' : '';
  const leaders = highlights.length ? `<section class="overview-section overview-wins" aria-labelledby="overview-wins">
    <div class="overview-heading"><h3 id="overview-wins">과목 1위 횟수</h3><span class="exam-board__status">1위 과목 / 채점한 과목</span></div>
    <ul>${highlights.map(([model, count]) => `<li><code>${escape(model)}</code>
      <meter min="0" max="${scoredCourses}" value="${count}" aria-label="${escape(model)} 1위 과목 수"></meter>
      <strong>${count} / ${appearances.get(model)}</strong></li>`).join('')}</ul></section>` : '';
  return `<section class="exam-overview" aria-labelledby="overview-title">
    <div class="overview-heading"><h2 id="overview-title">종합 대시보드</h2>${update}</div>
    <dl class="overview-metrics">
      <div><dt>공개 과목</dt><dd>${scoredCourses}<small> / ${catalog.datasets.length}과목</small></dd></div>
      <div><dt>평가 모델</dt><dd>${appearances.size}<small>개</small></dd></div>
      <div><dt>채점 완료</dt><dd>${completedCount}<small> / ${registered}건</small></dd></div>
    </dl>
    <section class="overview-section" aria-labelledby="overview-leaders">
      <div class="overview-heading"><h3 id="overview-leaders">과목별 1위</h3>${filterNote}</div>
      <div class="overview-primary">${courses(primary)}</div>
      <div class="overview-inquiry">${Object.entries(catalog.courses).map(([group, keys]) =>
        `<section class="overview-group"><h4>${escape(catalog.groups[group])}</h4>
          ${courses(Object.keys(keys), group)}</section>`).join('')}</div>
    </section>
    ${leaders}
  </section>`;
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
  if (key === 'overview') {
    const focused = content.contains(document.activeElement) ? document.activeElement.getAttribute('href') : null;
    content.innerHTML = overviewDashboard(board);
    if (focused) [...content.querySelectorAll('a')].find(link => link.getAttribute('href') === focused)?.focus({preventScroll: true});
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
  if (state.hideFrontier) models = visibleModels(models);
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
  const url = 'https://suneung-cat.vercel.app' + selectionHref(state.subject, state.course);
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
