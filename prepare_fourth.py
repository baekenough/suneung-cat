#!/usr/bin/env python3
"""Prepare visual question crops and official answer keys for period 4."""
import argparse
import re
from pathlib import Path

import fitz

from kice_files import await_release, fetch_asset
from prepare_exam import CHOICES, FORMS, ROOT, kordoc, sha256, write_json
from prepare_math import render_crop
from subjects_catalog import FOURTH_RELEASE, LABELS, RELEASE_ASSETS, dataset_directory


MARKER = re.compile(r'^(?:(\d{1,2})\.(?!\d)|\[\s*(\d{1,2})\s*[~～∼]\s*(\d{1,2})\s*\])')
ANSWER = re.compile(r'(?<!\d)(\d{1,2})\s+([①②③④⑤])\s+([23])(?!\d)')
DOUBLE_FORMS = ('홀수형', '짝수형')
COMMON = '공통형'


def key_forms(key):
    ir = kordoc(key)
    forms = {}
    with fitz.open(key) as document:
        tables_by_page = {}
        for block in ir['blocks']:
            if block['type'] != 'table':
                continue
            page = block['pageNumber']
            rows = [' '.join(cell['text'].strip() for cell in row) for row in block['table']['cells']]
            values = tables_by_page.setdefault(page, [])
            values.extend((int(num), CHOICES.index(answer) + 1, int(points))
                          for row in rows for num, answer, points in ANSWER.findall(row))
        for page, triples in tables_by_page.items():
            if not triples:
                continue
            text = document[page - 1].get_text()
            markers = [form for form in FORMS if form[:2] in text]
            if len(markers) > 1:
                raise ValueError(f'{key.name} p.{page}에서 기형을 확정할 수 없습니다.')
            form = markers[0] if markers else COMMON
            values = {n: {'answer': a, 'points': p} for n, a, p in triples}
            if (form in forms or len(triples) != 20 or set(values) != set(range(1, 21))
                    or sum(v['points'] for v in values.values()) != 50):
                raise ValueError(f'{key.name} p.{page}의 문항 번호 또는 50점 배점이 일치하지 않습니다.')
            forms[form] = values
    if set(forms) == {COMMON}:
        return forms
    if set(forms) != set(DOUBLE_FORMS):
        raise ValueError(f'{key.name}에서 공통 또는 홀수·짝수형 정답표를 찾지 못했습니다.')
    return {form: forms[form] for form in FORMS}


def regions(page):
    dx, dy = page.rect.width / 842, page.rect.height / 1191
    columns = [[], []]
    bottoms = [1070 * dy, 1070 * dy]
    for block in page.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)['blocks']:
        for line in block.get('lines', ()):
            x, y, _, _ = line['bbox']
            if not 140 * dy < y < 1070 * dy:
                continue
            side = int(x > page.rect.width / 2)
            text = ''.join(span['text'] for span in line['spans']).strip()
            if y > 800 * dy and re.search(r'확인\s*사항', text):
                bottoms[side] = min(bottoms[side], y - 8 * dy)
            if abs(x - (436.6 if side else 87.9) * dx) > 3 * dx:
                continue
            if match := MARKER.match(text):
                number = int(match[1] or match[2])
                if 1 <= number <= 20:
                    columns[side].append((y, number, int(match[3]) if match[3] else 0))

    for side, anchors in enumerate(columns):
        ordered = sorted(set(anchors))
        left, right = ((82, 417), (430, 763))[side]
        for index, (y, number, last) in enumerate(ordered):
            bottom = ordered[index + 1][0] - 3 * dy if index + 1 < len(ordered) else bottoms[side]
            yield number, last, fitz.Rect(left * dx, y - 3 * dy, right * dx, bottom)


def prepare(dataset, paper, key, root, year=2027):
    output = root / dataset_directory(dataset, year)
    question_path, answer_path = output / 'questions.json', output / 'answer_key.json'
    source_hash, key_hash = sha256(paper), sha256(key)
    forms = key_forms(key)
    questions, answers = {}, {}
    order = []
    passage_images = {}
    subject = LABELS[dataset]
    with fitz.open(paper) as document:
        for page in document:
            for number, last, rect in regions(page):
                form_index = len(order) // 20
                if form_index >= len(forms) or number != len(order) % 20 + 1:
                    raise ValueError(f'{subject} p.{page.number + 1} 문항 순서 오류 · {number}번')
                form = tuple(forms)[form_index]
                if number == 1 and not last and form != COMMON:
                    header = page.get_text(clip=fitz.Rect(0, 0, page.rect.width, rect.y0))
                    other_form = next(other for other in FORMS if other != form)
                    if other_form[:2] in header:
                        raise ValueError(f'{subject} 문제지 기형 순서 오류 · {form}')
                name = f'questions/{form}/{"passage-" if last else ""}{number:02}.png'
                path = output / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if last:
                    if not number < last <= 20:
                        raise ValueError(f'{subject} 공통 지문 범위 오류 · {number}~{last}')
                    render_crop(page, rect, path, color=True)
                    for member in range(number, last + 1):
                        passage_images.setdefault((form, member), []).append(name)
                    continue

                official = forms[form][number]
                text = page.get_text(clip=rect)
                choices = set(text) & set(CHOICES)
                if choices and len(choices) != len(CHOICES):
                    raise ValueError(f'{subject} {form} {number}번 선택지 누락 · p.{page.number + 1}')
                is_three_points = bool(re.search(r'\[\s*3\s*점\s*\]', text))
                if is_three_points != (official['points'] == 3):
                    raise ValueError(f'{subject} {form} {number}번 배점 불일치 · p.{page.number + 1}')
                box = render_crop(page, rect, path, color=True)
                qid = f'{form}/{number:02}'
                answers[qid] = official
                questions[qid] = {'number': number, 'form': form, 'section': '공통', 'subject': subject,
                                  'answer_type': 'choice', 'image': name,
                                  'passage_images': passage_images.get((form, number), []),
                                  'item': {'regions': [{'page': page.number + 1, 'bbox': box}]}}
                order.append(qid)
    if len(order) != 20 * len(forms):
        raise ValueError(f'{subject} 20문항 × 시험지 {len(forms)}개와 분리 문항 수가 일치하지 않습니다.')
    write_json(answer_path, {'source_sha256': key_hash, 'answers': answers})
    write_json(question_path, {'year': year, 'subject': subject, 'forms': list(forms), 'electives': [],
                               'max_score': 50, 'source_sha256': source_hash, 'questions': questions})
    print(f'{subject} · {len(questions)}문항 준비 완료', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subject', choices=RELEASE_ASSETS, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'output')
    args = parser.parse_args()
    dataset = args.subject
    await_release(FOURTH_RELEASE, '한국사·탐구', False)
    _, suffix = RELEASE_ASSETS[dataset]
    prefix = f'27DaeSuneung_{suffix}'
    subject = LABELS[dataset]
    paper = fetch_asset(f'{prefix}.pdf', ROOT / 'subjects' / f'2027_{subject}_문제지.pdf')
    key = fetch_asset(f'{prefix}a.pdf', ROOT / 'answer_sheets' / f'2027_{subject}_정답표.pdf')
    prepare(dataset, paper, key, args.output)


if __name__ == '__main__':
    main()
