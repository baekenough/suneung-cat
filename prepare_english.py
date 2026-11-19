#!/usr/bin/env python3
"""Prepare English CSAT images, official audio tracks and scoring keys."""
import argparse
import re
import unicodedata
from pathlib import Path
from subprocess import run
from zipfile import ZipFile

import fitz

from prepare_exam import CHOICES, FORMS, ROOT, kordoc, sha256, write_json
from prepare_math import render_crop
from kice_files import await_release, fetch_asset
from subjects_catalog import ENGLISH_RELEASE

MARK = re.compile(r'^(\d{1,2})\.(?:\s|$)|^\[(\d{1,2})[~～](\d{1,2})\]')
PASSAGES = {41: [41, 42], 43: [43, 44, 45]}
GROUP_PROMPTS = {
    31: 'Choose the best option to fill in the blank.',
    36: 'Choose the correct order of the paragraphs following the given paragraph.',
    38: 'Choose where the given sentence best fits in the passage.',
}
KICE_ENGLISH = (
    ('27DaeSuneung_3.pdf', 'subjects', '_문제지', 'pdf'),
    ('27DaeSuneung_3a.pdf', 'answer_sheets', '_정답표', 'pdf'),
    ('27DaeSuneung_3.zip', 'subjects', '듣기평가음원', 'zip'),
    ('27DaeSuneung_31.pdf', 'subjects', '듣기평가대본', 'pdf'),
)


def source(folder, year, phrase, suffix):
    candidates = [p for p in (ROOT / folder).glob(f'{year}_*.{suffix}')
                  if '영어영역' + phrase in unicodedata.normalize('NFC', p.name)]
    if not candidates:
        raise FileNotFoundError(f'{year} {folder} 영어영역{phrase}.{suffix} 파일이 필요합니다.')
    if len(candidates) > 1:
        raise ValueError(f'{year} {folder} 영어영역{phrase}.{suffix} 파일을 하나씩 준비하세요.')
    return candidates[0]


def download_2027(wait):
    await_release(ENGLISH_RELEASE, '2027학년도 영어', wait)
    for remote_name, folder, phrase, suffix in KICE_ENGLISH:
        try:
            source(folder, 2027, phrase, suffix)
            continue
        except FileNotFoundError:
            pass
        fetch_asset(remote_name, ROOT / folder / f'2027_영어영역{phrase}.{suffix}')


def audio_files(archive, output):
    folder = output / 'audio'
    folder.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as z:
        members = {}
        for entry in z.infolist():
            match = re.match(r'^\s*(\d{1,2})(?=$|[_ .\-(번~～])', Path(entry.filename).stem)
            if match and entry.filename.lower().endswith('.mp3') and int(match[1]) in range(1, 18):
                number = int(match[1])
                if number in members:
                    raise ValueError(f'영어 음원 트랙 중복: {number}')
                members[number] = entry
        if sorted(members) not in (list(range(1, 17)), list(range(1, 18))):
            raise ValueError('영어 공식 음원에 01~16번 트랙이 필요합니다.')
        for number, entry in members.items():
            dest = folder / f'{number:02}.mp3'
            run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', 'pipe:0', '-map', '0:a:0',
                 '-ac', '1', '-ar', '24000', '-codec:a', 'libmp3lame', '-b:a', '48k', str(dest)],
                input=z.read(entry), check=True)
    return {n: f'audio/{n if n in members else 16:02}.mp3' for n in range(1, 18)}


def english_key(pdf):
    ir = kordoc(pdf)
    answers = {}
    for page, form in enumerate(FORMS, 1):
        table, = (b['table'] for b in ir['blocks'] if b['type'] == 'table' and b['pageNumber'] == page)
        for row in table['cells'][1:]:
            for col in range(0, len(row), 3):
                n, choice, points = (c['text'].strip() for c in row[col:col + 3])
                if not n:
                    continue
                if len(choice) != 1 or choice not in CHOICES or points not in ('2', '3'):
                    raise ValueError(f'{form} 영어 {n}번 정답표를 확인하세요.')
                answers[f'{form}/{int(n):02}'] = {'answer': CHOICES.index(choice) + 1, 'points': int(points)}
        if sum(v['points'] for k, v in answers.items() if k.startswith(form)) != 100:
            raise ValueError(f'{form} 영어 배점 합이 100점이 아닙니다.')
    return answers


def page_areas(page):
    columns = [[], []]
    ends = [1070.0, 1070.0]
    for block in page.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)['blocks']:
        for line in block.get('lines', ()):
            x, y, _, _ = line['bbox']
            side = int(x > 421)
            if not 150 <= y <= 1069:
                continue
            value = ''.join(s['text'] for s in line['spans']).strip()
            if re.search(r'확인\s*사항', value) and y > 900:
                ends[side] = min(ends[side], y - 9)
            m = MARK.match(value)
            if m and abs(x - (436.6 if side else 87.9)) < 2:
                columns[side].append((y, int(m[1] or m[2]), m[1] is None))
    for side, column in enumerate(columns):
        column = sorted(set(column))
        left, right = ((84, 414), (433, 761))[side]
        if page.number % 8 == 7 and side == 1:
            yield 43, True, fitz.Rect(left, 151, right, column[0][0] - 3)
        for i, (y, n, group) in enumerate(column):
            end = column[i + 1][0] - 3 if i + 1 < len(column) else ends[side]
            yield n, group, fitz.Rect(left, y - 3, right, end)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, default=2026)
    parser.add_argument('--output', type=Path, default=ROOT / 'output')
    parser.add_argument('--download', action='store_true', help='2027학년도 영어 자료를 평가원에서 받기')
    parser.add_argument('--wait-for-release', action='store_true', help='공식 공개 시각까지 대기 후 진행')
    args = parser.parse_args()
    year = args.year
    if args.wait_for_release and not args.download:
        parser.error('--wait-for-release는 --download와 함께 사용하세요.')
    if args.download:
        if year != 2027:
            parser.error('--download는 2027학년도 영어를 지원합니다.')
        download_2027(args.wait_for_release)
    output = args.output / f'{year}-english'
    paper = source('subjects', year, '_문제지', 'pdf')
    key_file = source('answer_sheets', year, '_정답표', 'pdf')
    audio_zip = source('subjects', year, '듣기평가음원', 'zip')
    audio = audio_files(audio_zip, output)
    answers = english_key(key_file)
    questions = {}
    with fitz.open(paper) as doc:
        if len(doc) != 16:
            raise ValueError('영어 홀수·짝수형 통합 PDF 16페이지가 필요합니다.')
        for index, form in enumerate(FORMS):
            passages = {}
            found = []
            for page in list(doc)[index * 8:index * 8 + 8]:
                for number, group, rect in page_areas(page):
                    if group and number not in PASSAGES:
                        continue
                    images = passages.setdefault(number, []) if group else []
                    suffix = f'questions/{form}/{"passage" if group else "question"}-{number:02}-{len(images)}.png'
                    path = output / suffix
                    path.parent.mkdir(parents=True, exist_ok=True)
                    box = render_crop(page, rect, path)
                    if group:
                        images.append(suffix)
                        continue
                    sheet_id = f'{form}/{number:02}'
                    if sheet_id not in answers or number in found:
                        raise ValueError(f'{sheet_id} 문제지 문항을 확인하세요.')
                    source_text = page.get_text('text', clip=rect)
                    if (number != 4 and any(choice not in source_text for choice in CHOICES)) or (('[3점]' in source_text) != (answers[sheet_id]['points'] == 3)):
                        raise ValueError(f'{sheet_id} 선택지 또는 배점 누락')
                    found.append(number)
                    question = {'form': form, 'section': '듣기' if number <= 17 else '읽기', 'number': number,
                                'answer_type': 'choice', 'image': suffix,
                                'item': {'regions': [{'page': page.number + 1, 'bbox': box}]}}
                    if number in audio:
                        question['audio'] = audio[number]
                    for start, members in PASSAGES.items():
                        if number in members:
                            question['passage_images'] = passages[start].copy()
                    for start, end in ((31, 34), (36, 37), (38, 39)):
                        if start <= number <= end:
                            question['task_instruction'] = GROUP_PROMPTS[start]
                    questions[sheet_id] = question
            if found != list(range(1, 46)) or {k: len(v) for k, v in passages.items()} != {41: 1, 43: 2}:
                raise ValueError(f'{form} 영어 문항 또는 공통 지문 구간 누락')
    if questions.keys() != answers.keys():
        raise ValueError('영어 문제지와 정답표의 문항 번호가 일치하지 않습니다.')
    write_json(output / 'answer_key.json', {'source_sha256': sha256(key_file), 'answers': answers})
    write_json(output / 'questions.json', {'year': year, 'subject': '영어', 'electives': [], 'sections': ['듣기', '읽기'],
               'source_sha256': sha256(paper), 'source_audio_sha256': sha256(audio_zip), 'questions': questions})
    print(f'{year}학년도 영어 {len(questions)}문항과 공식 듣기 {len(set(audio.values()))}개 트랙 준비 완료')


if __name__ == '__main__':
    main()
