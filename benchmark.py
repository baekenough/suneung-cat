#!/usr/bin/env python3
"""Run one independent model request per exam question."""
import argparse
import base64
import concurrent.futures
from collections import Counter
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
import socket
import re
from http.client import HTTPException
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from native_models import ANTHROPIC, OPENAI, native_request, normalize_response
from result_store import save_results

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = 'solar-mini-4-5-preview'
UPSTAGE = 'https://api.upstage.ai/v1/chat/completions'
OPENROUTER = 'https://openrouter.ai/api/v1/chat/completions'
SYSTEM = ('당신은 수능 국어 시험에 응시합니다. 제공된 지문과 문제를 읽고 해당 문항 하나만 푸세요. '
          '자료는 원문의 글과 그림을 텍스트로 옮긴 것입니다. '
          '정답으로 고른 선택지의 번호 하나를 JSON의 answer 값(정수 1~5)으로 반환하세요.')
SCHEMA = {'type': 'json_schema', 'json_schema': {'name': 'exam_answer', 'strict': True, 'schema': {
    'type': 'object', 'properties': {'answer': {'type': 'integer', 'enum': [1, 2, 3, 4, 5]}},
    'required': ['answer'], 'additionalProperties': False}}}
FORMS = ('홀수형', '짝수형')
ELECTIVES = ('화법과 작문', '언어와 매체')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def config_value(*names):
    environment = {name.upper(): value for name, value in os.environ.items()}
    for name in names:
        if environment.get(name):
            return environment[name]
    values = {}
    env_file = ROOT / '.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            name, separator, value = line.strip().removeprefix('export ').partition('=')
            if separator and not name.startswith('#'):
                values[name.strip().upper()] = value.strip().strip('"\'')
    for name in names:
        if values.get(name):
            return values[name]
    return None


def model_endpoint(model):
    if '/' in model:
        return OPENROUTER
    if model.startswith('gpt-'):
        return OPENAI
    if model.startswith('claude-'):
        return ANTHROPIC
    return UPSTAGE


def api_key(endpoint):
    names = {OPENROUTER: ('OPENROUTER_API_KEY',), OPENAI: ('OPENAI_API_KEY',),
             ANTHROPIC: ('ANTHROPIC_API_KEY',), UPSTAGE: ('UPSTAGE_API_KEY', 'UPSTAGE_SOLAR_PRO4_PREVIEW')}[endpoint]
    key = config_value(*names)
    if not key:
        raise ValueError(f'환경 변수 또는 .env에서 {names[0]}를 찾지 못했습니다.')
    return key


def parse_choice(content, lower=1, upper=5):
    text = (content or '').strip()
    fence = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence[1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        single = re.fullmatch(r'(?:(?:정답|answer)\s*[:：]\s*)?([0-9]+|[①②③④⑤])\s*(?:번)?[.]?', text,
                              re.IGNORECASE)
        if not single:
            raise
        parsed = '①②③④⑤'.index(single[1]) + 1 if single[1] in '①②③④⑤' else int(single[1])
    if isinstance(parsed, list) and len(parsed) == 1:
        parsed = parsed[0]
    answer = parsed.get('answer') if isinstance(parsed, dict) else parsed
    if type(answer) is not int or not lower <= answer <= upper:
        raise ValueError(f'답안이 {lower}~{upper}의 정수가 아닙니다.')
    return answer


def make_messages(question, output=None):
    if 'image' in question:
        numeric = question['answer_type'] == 'integer'
        answer_label = '0~999 사이의 정수' if numeric else '선택지 번호 1~5 사이의 정수'
        message = f'이미지에 있는 수능 수학 문제 하나를 푸세요. 정답 {answer_label}를 JSON의 answer 값으로 반환하세요.'
        if question.get('subject') == '영어' or question['section'] in ('듣기', '읽기'):
            task = question.get('task_instruction', '')
            message = ('Solve the English CSAT question shown. Use the attached recording for listening questions. '
                       'For questions 16–17, answer only the numbered item shown. '
                       'Return the option number (integer 1–5) in the JSON answer field. ' + task)
        images = [*question.get('passage_images', ()), question['image']]
        content = [{'type': 'text', 'text': message}]
        for name in images:
            encoded = base64.b64encode((output / name).read_bytes()).decode('ascii')
            content.append({'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + encoded}})
        if name := question.get('audio'):
            encoded = base64.b64encode((output / name).read_bytes()).decode('ascii')
            content.append({'type': 'input_audio', 'input_audio': {'data': encoded, 'format': 'mp3'}})
        schema = SCHEMA if not numeric else {**SCHEMA, 'json_schema': {**SCHEMA['json_schema'],
            'schema': {**SCHEMA['json_schema']['schema'], 'properties': {'answer': {
                'type': 'integer', 'minimum': 0, 'maximum': 999}}}}}
        return [{'role': 'user', 'content': content}], schema, (0, 999) if numeric else (1, 5)
    item = question['item']['text']
    if question['passage']:
        item = '[공통 지문]\n' + question['passage']['text'] + '\n\n[문항]\n' + item
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': item}], SCHEMA, (1, 5)


def read_response(response, deadline):
    # Some gateways send whitespace while generating. A socket timeout alone can
    # leave a request open indefinitely as long as those bytes keep arriving.
    body = bytearray()
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError('API response deadline exceeded')
        chunk = response.read1(65536)
        if not chunk:
            return json.loads(body)
        body.extend(chunk)


def solve(key, model, settings, question, previous, recover_effort=None, output=None, workspace_id=None):
    endpoint = model_endpoint(model)
    native = endpoint in (OPENAI, ANTHROPIC)
    exhausted = previous.get('error') == '재시도 후에도 출력 토큰 한도 도달'
    recovery = (recover_effort if previous else None) or ('low' if exhausted else None)
    effort = recovery or settings['reasoning_effort']
    if native and effort == 'none':
        effort = 'low'
    cap = 8192 if recovery else settings['max_tokens']
    messages, schema, answer_range = make_messages(question, output)
    payload = {'model': model, 'temperature': settings['temperature'], 'max_tokens': cap,
               'response_format': schema, 'messages': messages}
    if endpoint != UPSTAGE:
        payload['reasoning'] = {'effort': effort, 'exclude': True}
    else:
        payload['reasoning_effort'] = effort
    if endpoint == OPENROUTER:
        payload['provider'] = {'require_parameters': True, 'sort': 'throughput'}
        if model.startswith('qwen/qwen3.') and 'finish_reason=stop' in previous.get('error', ''):
            payload['provider'].pop('sort')
            failed_providers = {attempt['provider'].casefold() for attempt in previous.get('attempts', ())
                                if attempt.get('provider')}
            if model == 'qwen/qwen3.5-27b':
                payload['provider']['order'] = ['deepinfra']
            elif failed_providers:
                payload['provider']['ignore'] = sorted(failed_providers)
    attempts = []
    for attempt in range(4):
        request = native_request(endpoint, key, payload, workspace_id) if native else Request(
            endpoint, json.dumps(payload, ensure_ascii=False).encode('utf-8'), headers={
            'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.monotonic()
        retry_after = 0
        usage = {}
        request_id = None
        finish = None
        provider = None
        content = None
        try:
            timeout = 60 if recovery else 210
            with urlopen(request, timeout=timeout) as response:
                data = read_response(response, started + timeout)
            if native:
                data = normalize_response(endpoint, data)
            request_id = data.get('id')
            provider = data.get('provider')
            usage = data.get('usage', {})
            choice = data['choices'][0]
            finish = choice['finish_reason']
            if finish == 'length':
                attempts.append({'error': '출력 토큰 한도 도달', 'finish_reason': finish,
                                 'max_tokens': payload['max_tokens'], 'request_id': request_id,
                                 'usage': usage, 'seconds': round(time.monotonic() - started, 3)})
                if recovery and not native and effort != 'none':
                    effort = 'none'
                    if endpoint == OPENROUTER:
                        payload['reasoning']['effort'] = effort
                    else:
                        payload['reasoning_effort'] = effort
                    payload['max_tokens'] = settings['max_tokens']
                    continue
                if payload['max_tokens'] >= 32768:
                    break
                payload['max_tokens'] *= 2
                continue
            if finish != 'stop':
                raise ValueError('응답 형식 오류')
            content = choice['message'].get('content')
            answer = parse_choice(content, *answer_range)
            latency = round(time.monotonic() - started, 3)
            return {'answer': answer, 'response_model': data.get('model'), 'request_id': request_id,
                    'started_at': started_at, 'latency_seconds': latency, 'max_tokens': payload['max_tokens'],
                    'effort': effort, 'provider': provider,
                    'attempts': attempts, 'usage': usage}
        except HTTPError as exc:
            message = f'HTTP {exc.code}'
            try:
                detail = json.load(exc).get('error', {}).get('message', '')
                message += ' ' + str(detail).replace(key, '[redacted]')[:240]
            except (ValueError, AttributeError):
                pass
            transient = exc.code in (408, 429, 500, 502, 503, 504, 529)
            try:
                retry_after = min(60, float(exc.headers.get('Retry-After', '0')))
            except ValueError:
                pass
        except (URLError, TimeoutError, socket.timeout, ConnectionError, HTTPException) as exc:
            message, transient = type(exc).__name__, True
            if recovery and not native and effort != 'none':
                effort = 'none'
                if endpoint == OPENROUTER:
                    payload['reasoning']['effort'] = effort
                else:
                    payload['reasoning_effort'] = effort
                payload['max_tokens'] = settings['max_tokens']
        except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
            message = f'응답 검증 실패 ({type(exc).__name__}, finish_reason={finish})'
            transient = attempt < 2 and finish == 'stop'
            if transient and provider and endpoint == OPENROUTER:
                route = payload['provider']
                route.setdefault('ignore', []).append(provider.casefold())
        attempts.append({'error': message, 'finish_reason': finish, 'request_id': request_id,
                         'usage': usage, 'provider': provider, 'content_chars': len(content) if isinstance(content, str) else None,
                         'seconds': round(time.monotonic() - started, 3)})
        if not transient or attempt == 3:
            return {'error': message, 'attempts': attempts}
        time.sleep(max(2 ** attempt, retry_after))
    return {'error': '재시도 후에도 출력 토큰 한도 도달', 'attempts': attempts}


def cohort_metrics(ids, records, key):
    solved = [qid for qid in ids if 'answer' in records.get(qid, {})]
    correct = [qid for qid in solved if records[qid]['answer'] == key[qid]['answer']]
    return {'questions': len(ids), 'solved': len(solved), 'correct': len(correct),
            'points': sum(key[qid]['points'] for qid in correct),
            'max_points': sum(key[qid]['points'] for qid in ids)}


def elapsed_seconds(run, solved):
    starts = []
    ends = []
    if run.get('started_at'):
        starts.append(datetime.fromisoformat(run['started_at']).timestamp())
    for response in solved:
        if response.get('started_at'):
            begin = datetime.fromisoformat(response['started_at']).timestamp()
            starts.append(begin)
            ends.append(begin + response['latency_seconds'])
    return round(max(ends) - min(starts), 3) if starts and ends else None


def format_duration(seconds):
    if seconds is None:
        return '–'
    minutes, millis = divmod(round(seconds * 1000), 60_000)
    hours, minutes = divmod(minutes, 60)
    return ((f'{hours}시간 ' if hours else '') + (f'{minutes}분 ' if minutes or hours else '')
            + f'{millis / 1000:.3f}초')


def ranking_key(model):
    score = model['mean_score']
    elapsed = model['elapsed_seconds']
    return (-score if score is not None else float('inf'),
            elapsed if elapsed is not None else float('inf'))


def summarize(directories, data, answers, config):
    questions = data['questions']
    electives = data.get('electives', ELECTIVES)
    results = []
    for path in sorted(path for directory in directories for path in directory.glob('*.json')):
        stored = read_json(path)
        records = stored['records']
        scopes = {}
        for form in FORMS:
            for section in ('공통', *electives, *data.get('sections', ())):
                ids = [qid for qid, q in questions.items() if q['form'] == form and (
                    (not electives and section == '공통') or q['section'] in ('공통', section))]
                scopes[f'{form} {section}'] = cohort_metrics(ids, records, answers)
        full = cohort_metrics(list(questions), records, answers)
        mean = (statistics.mean(scopes[f'{form} {elective}']['points']
                                for form in FORMS for elective in (electives or ('공통',)))
                if full['solved'] == full['questions'] else None)
        solved = [r for r in records.values() if 'answer' in r]
        responses = [dict(qid=qid, **answers[qid], prediction=records.get(qid, {}).get('answer'),
                          correct=records[qid]['answer'] == answers[qid]['answer']
                          if 'answer' in records.get(qid, {}) else None,
                          request=records.get(qid)) for qid in questions]
        results.append({'model': stored['model'], 'endpoint': stored.get('endpoint'),
                        'mean_score': mean, 'overall': full, 'scores': scopes,
                        'elapsed_seconds': elapsed_seconds(stored, solved),
                        'median_seconds': round(statistics.median(r['latency_seconds'] for r in solved), 3) if solved else None,
                        'recovered_questions': sum(bool(r.get('attempts')) for r in solved),
                        'backend_counts': dict(Counter(r['provider'] for r in solved if r.get('provider'))),
                        'effort_counts': dict(Counter(r.get('effort', config['settings']['reasoning_effort']) for r in solved)),
                        'raised_budget_questions': sum(r.get('max_tokens', config['settings']['max_tokens'])
                                                       > config['settings']['max_tokens'] for r in solved),
                        'usage': {field: sum(r['usage'].get(field, 0) for r in solved)
                                  for field in ('prompt_tokens', 'completion_tokens', 'total_tokens')},
                        'reasoning_tokens': sum(r['usage'].get('completion_tokens_details', {}).get('reasoning_tokens', 0)
                                                for r in solved), 'items': responses})
    results.sort(key=lambda r: (*ranking_key(r), r['model']))
    ranks = {}
    for r in results:
        r['rank'] = ranks.setdefault(ranking_key(r), len(ranks) + 1) if r['mean_score'] is not None else None
    summary = {'year': data['year'], 'question_sha256': config['questions_sha256'],
               'answer_pdf_sha256': config['answer_pdf_sha256'], 'settings': config['settings'], 'output_budget_on_length': [4096, 8192, 16384, 32768],
               'models': results}
    return summary


def report(output, directories, data, answers, config):
    summary = summarize(directories, data, answers, config)
    results = summary['models']
    subject = data.get('subject', '국어')
    save_results(output.parent / 'results.sqlite', subject, fingerprint(config), summary)
    write_json(output / 'results.json', summary)
    score_description = ('공식 배점으로 채점한 홀수형·짝수형 100점 원점수의 평균으로 순위를 매깁니다.'
                         if subject == '영어' else
                         '공식 배점으로 채점한 홀수형·짝수형 × 선택과목의 100점 원점수 평균으로 순위를 매깁니다. '
                         '공통 문항은 형별로 한 번씩 풀고 각 선택과목 점수에 공통으로 반영합니다.')
    lines = [f'# {data["year"]}학년도 수능 {subject} 모델 평가', '',
             f'각 요청에서 문항 하나를 풉니다. 기본 추론 설정 `{config["settings"]["reasoning_effort"]}`, '
             f'온도 지정을 지원하는 요청에서는 `{config["settings"]["temperature"]}`을 사용합니다. '
             + score_description + ' 동점에서는 소요시간이 짧은 모델을 앞에 둡니다.', '',
             '| 순위 | 모델 | 채점 완료 | 정답 | 원점수 평균 | 소요시간 |', '| --- | --- | ---: | ---: | ---: | ---: |']
    for r in results:
        full = r['overall']
        score = f'{r["mean_score"]:.2f}' if r['mean_score'] is not None else '미완료'
        lines.append(f'| {r["rank"] or "–"} | `{r["model"]}` | {full["solved"]}/{full["questions"]} | '
                     f'{full["correct"]} | {score} | {format_duration(r["elapsed_seconds"])} |')
    for r in results:
        lines.extend(['', f'## {r["model"]}', '', '| 시험지 | 원점수 | 정답 |', '| --- | ---: | ---: |'])
        for label, m in r['scores'].items():
            score = f'{m["points"]}/{m["max_points"]}' if m['solved'] == m['questions'] else '미완료'
            lines.append(f'| {label} | {score} | {m["correct"]}/{m["questions"]} |')
    markdown = output / 'leaderboard.md'
    temp = markdown.with_suffix('.md.tmp')
    temp.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    temp.replace(markdown)


def comparison_config(data, key_data, effort):
    config = {'questions_sha256': fingerprint(data['questions']), 'answer_pdf_sha256': key_data['source_sha256'],
              'settings': {'reasoning_effort': effort, 'temperature': 0, 'max_tokens': 4096},
              'system': SYSTEM, 'schema': SCHEMA}
    if 'subject' in data:
        config.update(subject=data['subject'], source_pdf_sha256=data['source_sha256'])
    if 'source_audio_sha256' in data:
        config['source_audio_sha256'] = data['source_audio_sha256']
    return config


def run_directories(output, config):
    runs = output / 'runs'
    return runs / fingerprint(config)[:16], runs / fingerprint({**config, 'endpoint': UPSTAGE})[:16]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subject', choices=['korean', 'math', 'english'], default='korean')
    parser.add_argument('--year', type=int, default=2027)
    parser.add_argument('--model', action='append', help='Upstage, OpenRouter, OpenAI 또는 Anthropic 모델 ID')
    parser.add_argument('--workers', type=int, default=8, choices=range(1, 33), metavar='1–32')
    parser.add_argument('--effort', default='medium', choices=['low', 'medium', 'high', 'xhigh', 'max'])
    parser.add_argument('--recover-effort', choices=['none', 'low', 'medium', 'high'],
                        help='이전에 실패한 문항을 재호출할 때 쓸 추론 설정')
    parser.add_argument('--output', type=Path, default=ROOT / 'output')
    args = parser.parse_args()
    output = args.output / (str(args.year) if args.subject == 'korean' else f'{args.year}-{args.subject}')
    data = read_json(output / 'questions.json')
    key_data = read_json(output / 'answer_key.json')
    questions, answers = data['questions'], key_data['answers']
    if questions.keys() != answers.keys() or data['year'] != args.year:
        raise ValueError('문제와 정답의 학년도 또는 문항이 일치하지 않습니다.')
    config = comparison_config(data, key_data, args.effort)
    directory, legacy = run_directories(output, config)
    directory.mkdir(parents=True, exist_ok=True)
    models = list(dict.fromkeys(args.model or [DEFAULT_MODEL]))
    if any(model_endpoint(model) == UPSTAGE for model in models) and args.subject != 'korean':
        raise SystemExit('수학·영어는 필요한 입력 형식을 지원하는 모델을 --model로 지정하세요.')
    if args.subject == 'english' and any(model_endpoint(model) != OPENROUTER for model in models):
        raise SystemExit('영어는 오디오와 이미지를 지원하는 OpenRouter 모델을 지정하세요.')
    workspace_id = config_value('ANTHROPIC_WORKSPACE_ID') if any(model_endpoint(m) == ANTHROPIC for m in models) else None
    states, paths, keys = {}, {}, {}
    failures = False
    with ExitStack() as locks:
        for model in models:
            name = fingerprint(model)[:16] + '.json'
            endpoint = model_endpoint(model)
            path = (legacy / name) if (legacy / name).exists() else (directory / name)
            lock_path = output / '.benchmark.lock' if path.parent == legacy else path.with_suffix('.lock')
            lock = locks.enter_context(lock_path.open('a'))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit(f'{model} 평가가 이미 실행 중입니다.')
            paths[model] = path
            keys[model] = api_key(endpoint)
            states[model] = read_json(path) if path.exists() else {'model': model, 'config': config, 'records': {},
                                              'started_at': datetime.now(timezone.utc).isoformat()}
            states[model]['endpoint'] = endpoint
            write_json(path, states[model])
        jobs = [(model, qid) for qid in questions for model in models
                if 'answer' not in states[model]['records'].get(qid, {})]
        counts = Counter(model for model, _ in jobs)
        print(f'동시 요청 최대 {args.workers}건', flush=True)
        for model in models:
            print(f'{model} · {counts[model]}문항 호출', flush=True)
        progress = Counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(solve, keys[model], model, config['settings'], questions[qid],
                                   states[model]['records'].get(qid, {}), args.recover_effort, output, workspace_id):
                       (model, qid) for model, qid in jobs}
            for future in concurrent.futures.as_completed(futures):
                model, qid = futures[future]
                state = states[model]
                previous = state['records'].get(qid, {})
                record = future.result()
                record['attempts'] = previous.get('attempts', []) + record['attempts']
                state['records'][qid] = record
                write_json(paths[model], state)
                if 'error' in record:
                    failures = True
                    print(f'{model} · {qid} · {record["error"]}', file=sys.stderr, flush=True)
                progress[model] += 1
                if progress[model] == counts[model] or progress[model] % 8 == 0:
                    print(f'{model} · {progress[model]}/{counts[model]} 처리', flush=True)
        with (output / '.report.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            report(output, (directory, legacy), data, answers, config)
    return int(failures)


if __name__ == '__main__':
    raise SystemExit(main())
