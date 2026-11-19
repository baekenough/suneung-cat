"""Fetch and validate official input files after their public release."""
from datetime import datetime
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory
import time
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile

import fitz


KICE_CDNS = ('https://cdn.kice.re.kr/27dae-suneung/', 'https://cdn2.kice.re.kr/27dae-suneung/')


def await_release(release, label, wait):
    remaining = (release - datetime.now(release.tzinfo)).total_seconds()
    if remaining <= 0:
        return
    message = f'평가원 {label} 공개 예정 {release:%Y-%m-%d %H:%M} KST'
    if not wait:
        raise SystemExit(message)
    print(f'{message} · 공개 시각까지 대기 중', flush=True)
    while remaining > 0:
        time.sleep(min(60, remaining))
        remaining = (release - datetime.now(release.tzinfo)).total_seconds()


def validate_file(path):
    if path.suffix == '.pdf':
        with fitz.open(path, filetype='pdf') as document:
            if not len(document):
                raise ValueError('빈 PDF')
    else:
        with ZipFile(path) as archive:
            if not archive.namelist() or archive.testzip():
                raise ValueError('빈 ZIP 또는 손상된 ZIP')


def fetch_asset(remote_name, destination):
    if destination.is_file():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.kice-', dir=destination.parent) as temporary:
        staged = Path(temporary) / destination.name
        for attempt in range(6):
            for base in KICE_CDNS:
                try:
                    with urlopen(base + remote_name, timeout=45) as response, staged.open('wb') as target:
                        copyfileobj(response, target)
                    validate_file(staged)
                except (URLError, TimeoutError, OSError, ValueError, RuntimeError, BadZipFile) as error:
                    last_error = error
                    continue
                try:
                    destination.hardlink_to(staged)
                except FileExistsError:
                    pass
                print(f'공식 자료 확인 · {destination.name}', flush=True)
                return destination
            if attempt < 5:
                time.sleep(10)
        raise RuntimeError(f'평가원 파일 {remote_name} 다운로드 실패') from last_error
