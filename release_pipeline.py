#!/usr/bin/env python3
"""Start the benchmark for each dataset after its official release time."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import subprocess
import sys
from pathlib import Path

from kice_files import await_release
from subjects_catalog import ENGLISH_RELEASE, FOURTH_RELEASE, LABELS, RELEASE_ASSETS


ROOT = Path(__file__).resolve().parent
ENGLISH_MODELS = ('google/gemini-3.8-flash', 'qwen/qwen3.8-omni-flash',
                  'xiaomi/mimo-v2.6-flash', 'meta/muse-ember')
COMMON_MODELS = ('gpt-6.2-astra', 'gpt-6.2-sol', 'gpt-6.1-terra',
                 'claude-fable-5-2', 'claude-opus-5-5', 'claude-sonnet-5-5',
                 'google/gemini-4-hydrogen', 'google/gemma-4-31b-it')
EXTRA_MODELS = {
    'social': ('qwen/qwen3.8-flash',),
    'science': ('meta/muse-glimmer-30b',),
    'vocational': ('qwen/qwen3.8-flash',),
}


def prepare_dataset(dataset):
    label = LABELS[dataset]
    print(f'{label} · 공식 자료 준비 시작', flush=True)
    if dataset == 'english':
        prepare = ['prepare_english.py', '--year', '2027', '--download']
    else:
        prepare = ['prepare_fourth.py', '--subject', dataset]
    if subprocess.call([sys.executable, *prepare], cwd=ROOT):
        print(f'{label} · 자료 준비 실패', flush=True)
        return False
    return True


def evaluate_dataset(dataset):
    label = LABELS[dataset]
    if dataset == 'english':
        models, workers = ENGLISH_MODELS, 20
    else:
        models, workers = COMMON_MODELS + EXTRA_MODELS.get(RELEASE_ASSETS[dataset][0], ()), 8
    command = [sys.executable, 'benchmark.py', '--year', '2027', '--subject', dataset]
    for model in models:
        command.extend(('--model', model))
    for options in (['--workers', str(workers)], ['--workers', '2'],
                    ['--workers', '2', '--recover-effort', 'low']):
        if subprocess.call(command + options, cwd=ROOT) == 0:
            print(f'{label} · 공식 배점 채점 완료', flush=True)
            return True
    print(f'{label} · 체크포인트에 재시도가 필요한 문항이 있습니다.', flush=True)
    return False


def evaluate_fourth(datasets):
    with ThreadPoolExecutor(max_workers=3) as preparation, ThreadPoolExecutor(max_workers=3) as evaluation:
        remaining = list(datasets)
        scheduled = []
        for attempt in range(2):
            if not remaining:
                break
            if attempt:
                print(f'4교시 · 자료 준비 실패 {len(remaining)}과목 다시 확인', flush=True)
            pending = {preparation.submit(prepare_dataset, dataset): dataset for dataset in remaining}
            remaining = []
            for future in as_completed(pending):
                dataset = pending[future]
                if future.result():
                    scheduled.append(evaluation.submit(evaluate_dataset, dataset))
                else:
                    remaining.append(dataset)
        return sum(future.result() for future in as_completed(scheduled))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wave', choices=('english', 'fourth'))
    parser.add_argument('--subject', choices=RELEASE_ASSETS, action='append',
                        help='4교시에서 특정 선택과목만 재개')
    parser.add_argument('--wait-for-active-wave', action='store_true',
                        help='같은 공개 작업이 진행 중이면 끝난 뒤 재개')
    args = parser.parse_args()
    if args.subject and args.wave != 'fourth':
        parser.error('--subject는 4교시 재개에 사용하세요.')
    output = ROOT / 'output'
    output.mkdir(exist_ok=True)
    with (output / f'.release-{args.wave}.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if not args.wait_for_active_wave:
                raise SystemExit(f'{args.wave} 공개 작업이 이미 실행 중입니다.')
            print(f'{args.wave} · 진행 중인 공개 작업이 끝나면 재개합니다.', flush=True)
            fcntl.flock(lock, fcntl.LOCK_EX)
        if args.wave == 'english':
            await_release(ENGLISH_RELEASE, '2027학년도 영어', True)
            return int(not (prepare_dataset('english') and evaluate_dataset('english')))

        await_release(FOURTH_RELEASE, '2027학년도 한국사·탐구', True)
        subjects = ['history']
        for number in range(1, 10):
            subjects.extend(f'{group}-{number:02}' for group in ('social', 'science', 'vocational')
                            if f'{group}-{number:02}' in RELEASE_ASSETS)
        datasets = list(dict.fromkeys(args.subject or subjects))
        completed = evaluate_fourth(datasets)
        print(f'4교시 · {completed}/{len(datasets)}개 시험지 채점 완료', flush=True)
        return int(completed != len(datasets))


if __name__ == '__main__':
    raise SystemExit(main())
