"""Build and load public scores without exam text or request records."""
import argparse
from functools import lru_cache
import json
import os
from pathlib import Path
from shutil import copyfile
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Lock
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import Request, urlopen

from benchmark import ELECTIVES, FORMS, ROOT, comparison_config, read_json, run_directories, summarize, write_json

DATASETS = {'korean': '2027', 'math': '2027-math'}
REFRESH_SECONDS = 2


def local_leaderboard(subject):
    output = ROOT / 'output' / DATASETS[subject]
    try:
        inputs = tuple((output / name).stat().st_mtime_ns for name in ('questions.json', 'answer_key.json'))
        runs = tuple(sorted((path, path.stat().st_mtime_ns) for path in (output / 'runs').glob('*/*.json')))
    except FileNotFoundError:
        return None
    return score_local_files(output, (inputs, runs))


@lru_cache(maxsize=4)
def score_local_files(output, version):
    data = read_json(output / 'questions.json')
    key = read_json(output / 'answer_key.json')
    config = comparison_config(data, key, 'medium')
    directories = run_directories(output, config)
    cases = [f'{form} {course}' for form in FORMS for course in data.get('electives', ELECTIVES)]
    models = []
    for result in summarize(directories, data, key['answers'], config)['models']:
        row = {field: result[field] for field in ('model', 'endpoint', 'rank', 'mean_score', 'elapsed_seconds')}
        row.update(solved=result['overall']['solved'], questions=result['overall']['questions'], scores={
            name: record['points'] if record['solved'] == record['questions'] else None
            for name, record in result['scores'].items() if name in cases})
        models.append(row)
    return {'questions': len(data['questions']), 'cases': cases, 'models': models,
            'updated_at': max((p.stat().st_mtime for d in directories for p in d.glob('*.json')), default=0)}


def packaged_leaderboard():
    path = os.environ.get('CSAT_LEADERBOARD_FILE')
    return read_json(Path(path)) if path and Path(path).is_file() else None


class BlobLeaderboard:
    """Share one revalidation across viewer sessions and keep the last good data."""

    def __init__(self, url, token):
        location = urlsplit(url)
        if location.scheme != 'https' or not (location.hostname or '').endswith('.private.blob.vercel-storage.com'):
            raise ValueError('CSAT_LEADERBOARD_URL은 Vercel 비공개 Blob HTTPS 주소여야 합니다.')
        query = dict(parse_qsl(location.query))
        query['cache'] = '0'
        self.url = location._replace(query=urlencode(query)).geturl()
        self.token = token
        self.lock = Lock()
        self.next_check = 0
        self.etag = None
        self.data = None

    def read(self):
        with self.lock:
            started = time.monotonic()
            if started < self.next_check:
                return self.data
            headers = {'Authorization': f'Bearer {self.token}'}
            if self.etag:
                headers['If-None-Match'] = self.etag
            try:
                with urlopen(Request(self.url, headers=headers), timeout=4) as response:
                    self.data = json.load(response)
                    self.etag = response.headers.get('ETag')
            except (URLError, ValueError, TimeoutError) as error:
                if isinstance(error, HTTPError):
                    error.close()
                if self.data is None:
                    raise
            # Share concurrent reads without skipping the next scheduled poll.
            self.next_check = started + REFRESH_SECONDS * 0.75
            return self.data


def publisher_environment():
    token = os.environ.get('BLOB_READ_WRITE_TOKEN')
    if not token:
        env_file = ROOT / '.env.local'
        if env_file.exists():
            for line in env_file.read_text(encoding='utf-8').splitlines():
                name, _, value = line.partition('=')
                if name == 'BLOB_READ_WRITE_TOKEN':
                    token = value.strip().strip('"\'')
                    break
    if not token:
        raise SystemExit('Vercel Blob 토큰을 환경 변수 또는 .env.local에 설정하세요.')
    env = {name: value for name, value in os.environ.items() if name not in ('VERCEL_OIDC_TOKEN', 'BLOB_STORE_ID')}
    return {**env, 'BLOB_READ_WRITE_TOKEN': token}


def publish_snapshot(path, env):
    with TemporaryDirectory(prefix='suneung-blob-') as directory:
        # The CLI otherwise loads the linked project's OIDC credentials as well.
        upload = Path(directory) / 'leaderboard.json'
        copyfile(path, upload)
        subprocess.run(['npx', '--yes', 'vercel', 'blob', 'put', str(upload), '--access', 'private',
                        '--force', '--no-multipart', '--cache-control-max-age', '0'],
                       cwd=directory, env=env, check=True, timeout=30)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'public-leaderboard.json')
    parser.add_argument('--publish', action='store_true', help='집계만 연결된 Vercel Blob에 업로드')
    parser.add_argument('--watch', action='store_true', help='2초마다 변경 사항을 확인')
    args = parser.parse_args()
    env = publisher_environment() if args.publish else None
    previous = None
    while True:
        snapshot = {subject: local_leaderboard(subject) for subject in DATASETS}
        if snapshot != previous:
            write_json(args.output, snapshot)
            try:
                if env is not None:
                    publish_snapshot(args.output, env)
                previous = snapshot
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                if not args.watch:
                    raise SystemExit('Vercel Blob 업로드 실패') from None
                print('Vercel Blob 업로드 재시도 중', file=sys.stderr, flush=True)
        if not args.watch:
            return
        time.sleep(REFRESH_SECONDS)


if __name__ == '__main__':
    main()
