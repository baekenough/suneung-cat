#!/usr/bin/env python3
"""Prepare question images and grading keys for the supplied math exam."""
import argparse
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import fitz

from prepare_exam import CHOICES, FORMS, ROOT, kordoc, sha256, write_json

SECTIONS = {'공통': (1, 8, range(1, 23)), '확률과 통계': (9, 12, range(23, 31)),
            '미적분': (13, 16, range(23, 31)), '기하': (17, 20, range(23, 31))}
QUESTION = re.compile(r'(?:^|[\n\t])\s*([1-9]|[12][0-9]|30)\.')
POINTS = re.compile(r'\[\s*([234])\s*점\s*\]')


def math_pdf(folder, year):
    path, = (p for p in (ROOT / folder).glob(f'{year}_*.pdf')
             if '수학영역' in unicodedata.normalize('NFC', p.name))
    return path


def collect_numbers(block, page, numbers):
    page = block.get('bbox', {}).get('page', block.get('pageNumber', page))
    numbers[page].update(map(int, QUESTION.findall(block.get('text', ''))))
    for child in block.get('children', ()):
        collect_numbers(child, page, numbers)
    for row in block.get('table', {}).get('cells', ()):
        for cell in row:
            collect_numbers(cell, page, numbers)
            for child in cell.get('blocks', ()):
                collect_numbers(child, page, numbers)


def bounds_for_questions(page, allowed):
    columns = [[], []]
    footers = [1066, 1066]
    type_headings = [[], []]
    for block in page.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)['blocks']:
        for line in block.get('lines', ()):
            x, y, _, bottom = line['bbox']
            side = int(x > 421)
            if not 129 < y < 1066:
                continue
            text = ''.join(span['text'] for span in line['spans']).strip()
            if re.search(r'확인\s*사항', text) and y > 800:
                footers[side] = min(footers[side], y - 10)
            if re.search(r'(단답형|지선다형)', text) and len(text) < 10:
                type_headings[side].append(bottom + 7)
            match = QUESTION.match(text)
            if match and abs(x - (436.6 if side else 87.9)) < 2 and int(match[1]) in allowed:
                columns[side].append((y, int(match[1])))
    all_numbers = []
    for side, column in enumerate(columns):
        column = sorted(set(column))
        left, right = ((82, 416), (429, 762))[side]
        for index, (y, number) in enumerate(column):
            stop = column[index + 1][0] - 26 if index + 1 < len(column) else footers[side]
            all_numbers.append(number)
            header = 220 if (page.number % 20) in (0, 8, 12, 16) else 149
            top = max(y - 26, header, *(line for line in type_headings[side] if line < y))
            yield number, fitz.Rect(left, top, right, stop)
    if set(all_numbers) != allowed or len(all_numbers) != len(allowed):
        raise ValueError(f'PDF p.{page.number + 1}의 kordoc 문항과 인쇄 순서가 일치하지 않습니다.')


def render_crop(page, area, destination, color=False):
    from PIL import Image, ImageChops

    scale = 2.5
    colorspace = fitz.csRGB if color else fitz.csGRAY
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=area, colorspace=colorspace, alpha=False)
    image = Image.frombytes('RGB' if color else 'L', (pixmap.width, pixmap.height), pixmap.samples)
    ink = ImageChops.invert(image.convert('L') if color else image).point(lambda value: 255 if value > 34 else 0).getbbox()
    if ink is None:
        raise ValueError(f'PDF p.{page.number + 1}에 비어 있는 문항 영역이 있습니다.')
    x0, y0, x1, y1 = ink
    box = (max(x0 - 18, 0), max(y0 - 18, 0), min(x1 + 18, image.width), min(y1 + 18, image.height))
    image.crop(box).save(destination, optimize=True)
    return [round((origin + pixel) / scale, 2) for origin, pixel in zip((pixmap.x, pixmap.y) * 2, box)]


def spec_for(number):
    return 'integer' if number in range(16, 23) or number in (29, 30) else 'choice'


def answer_key(ir):
    results = {}
    for page, form in enumerate(FORMS, 1):
        blocks = [b for b in ir['blocks'] if b['pageNumber'] == page]
        if not any(form[:2] in b.get('text', '') for b in blocks):
            raise ValueError(f'정답표 {form} 표기 오류')
        table, = (b['table'] for b in blocks if b['type'] == 'table')
        for row in table['cells'][3:]:
            for index, section in enumerate(('공통', '공통', '확률과 통계', '미적분', '기하')):
                number, answer, points = (cell['text'].strip() for cell in row[index * 3:index * 3 + 3])
                if not number and not answer and not points:
                    continue
                n, points = int(number), int(points)
                if spec_for(n) == 'choice':
                    if len(answer) != 1 or answer not in CHOICES:
                        raise ValueError(f'{form} {section} {n} 객관식 정답 형식 오류')
                    value = CHOICES.index(answer) + 1
                else:
                    value = int(answer)
                    if not 0 <= value <= 999:
                        raise ValueError(f'{form} {section} {n} 단답형 정답 범위 오류')
                qid = f'{form}/{section}/{n:02}'
                if qid in results or points not in (2, 3, 4):
                    raise ValueError(f'{qid} 정답표 중복 또는 배점 오류')
                results[qid] = {'answer': value, 'points': points}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, choices=(2026, 2027), default=2027)
    parser.add_argument('--output', type=Path, default=ROOT / 'output')
    args = parser.parse_args()
    destination = args.output / f'{args.year}-math'
    crops = destination / 'questions'
    crops.mkdir(parents=True, exist_ok=True)
    exam, key = math_pdf('subjects', args.year), math_pdf('answer_sheets', args.year)
    exam_ir, key_ir = kordoc(exam), kordoc(key)
    if (exam_ir['pageCount'], key_ir['pageCount']) != (40, 2):
        raise ValueError('수학 문제지 또는 정답표의 페이지 수가 예상 범위와 다릅니다.')
    numbers = defaultdict(set)
    for block in exam_ir['blocks']:
        collect_numbers(block, None, numbers)
    answers = answer_key(key_ir)
    questions = {}
    with fitz.open(exam) as doc:
        for form_index, form in enumerate(FORMS):
            for section, (start, stop, expected) in SECTIONS.items():
                if sum(v['points'] for k, v in answers.items() if k.startswith(f'{form}/{section}/')) != (74 if section == '공통' else 26):
                    raise ValueError(f'{form} {section}의 공식 배점 합계 오류')
                actual = []
                for p in range(start, stop + 1):
                    page_number = p + 20 * form_index
                    page = doc[page_number - 1]
                    for number, area in bounds_for_questions(page, numbers[page_number]):
                        qid = f'{form}/{section}/{number:02}'
                        actual.append(number)
                        text = page.get_text('text', clip=area)
                        marks = POINTS.findall(text)
                        if len(marks) != 1 or int(marks[0]) != answers[qid]['points']:
                            raise ValueError(f'{qid} 문제 영역에서 공식 배점을 확인할 수 없습니다.')
                        labels = re.findall('[①②③④⑤]', text)
                        if sorted(labels) != (list(CHOICES) if spec_for(number) == 'choice' else []):
                            raise ValueError(f'{qid} 선택지 경계 검증 실패')
                        suffix = Path('questions') / form / section / f'{number:02}.png'
                        path = destination / suffix
                        path.parent.mkdir(parents=True, exist_ok=True)
                        bbox = render_crop(page, area, path)
                        questions[qid] = {'form': form, 'section': section, 'number': number,
                                          'answer_type': spec_for(number), 'image': str(suffix),
                                          'item': {'regions': [{'page': page_number, 'bbox': bbox}]}}
                if actual != list(expected):
                    raise ValueError(f'{form} {section} 문항 순서 오류: {actual}')
    if questions.keys() != answers.keys():
        raise ValueError('수학 문제지와 정답표의 문항 번호가 일치하지 않습니다.')
    write_json(destination / 'questions.json', {'year': args.year, 'subject': '수학', 'electives': list(SECTIONS)[1:],
               'kordoc_version': exam_ir['version'], 'source_sha256': sha256(exam), 'questions': questions})
    write_json(destination / 'answer_key.json', {'source_sha256': sha256(key), 'answers': answers})
    print(f'{args.year}학년도 수학 {len(questions)}문항 영역 이미지 및 정답표 준비 완료')


if __name__ == '__main__':
    main()
