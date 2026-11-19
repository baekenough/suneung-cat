#!/usr/bin/env python3
"""Use kordoc's question anchors to crop the supplied exam's two-column layout."""
import argparse
import hashlib
import json
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import fitz

from visual_materials import VISUALS, VISUALS_2027

ROOT = Path(__file__).resolve().parent
FORMS = ('홀수형', '짝수형')
SECTIONS = {'공통': (1, 12, range(1, 35)), '화법과 작문': (13, 16, range(35, 46)),
            '언어와 매체': (17, 20, range(35, 46))}
CHOICES = '①②③④⑤'
MARKER = re.compile(r'^(\[(\d+)[～~](\d+)\]|(\d{1,2})\.)')
EXAM_SHA256 = {
    2026: 'ddb1ede52e317cb67c94172b39aad24b0150bf888455be33f8e333010ce16a0a',
    2027: '6d9560b193a4e68d61a356215447f5268408793615ba013f777ac309ce109b84',
}
BRACKETS = {
    2026: {(5, 0): [('A', 433, 595)], (10, 0): [('A', 250, 629)]},
    2027: {(2, 0): [('A', 614, 884)], (8, 0): [('A', 695, 832)],
           (10, 0): [('A', 229, 331)], (14, 0): [('A', 838, 893), ('B', 931, 1007)],
           (14, 1): [('C', 715, 835)], (16, 0): [('A', 286, 370)]},
}
# Convert the PDF fonts' private-use glyphs to standard Unicode.
GLYPHS = str.maketrans({
    '\uf3b0': '코ᇰ', '\ue97d': 'ᄉᆞ', '\ued7c': 'ᅀᅴ', '\ued7f': 'ᅀᅵ', '\uf43d': 'ᄐᆞᆨ', '\u200b': '',
    '\U000f0854': '『', '\U000f0855': '』', '\U000f02b1': '1. ', '\U000f02b2': '2. ',
})


@dataclass(frozen=True)
class Line:
    x: float
    y: float
    text: str


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one_pdf(folder, year):
    files = [path for path in (ROOT / folder).glob(f'{year}_*.pdf')
             if '국어영역' in unicodedata.normalize('NFC', path.name)]
    if len(files) != 1:
        raise ValueError(f'{folder}에 {year}학년도 국어 PDF 한 부가 필요합니다.')
    return files[0]


def kordoc(path):
    result = subprocess.run(['node', str(ROOT / 'parse_pdf.mjs'), str(path)],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def ir_markers(blocks):
    for block in blocks:
        match = MARKER.match(block.get('text', ''))
        if match and 'bbox' in block:
            x = block['bbox']['x']
            if abs(x - 88) < 2 or abs(x - 437) < 2:
                yield match[1], block['bbox']
        yield from ir_markers(block.get('children', ()))
        for row in block.get('table', {}).get('cells', ()):
            for cell in row:
                if 'blocks' in cell:
                    yield from ir_markers(cell['blocks'])
                else:
                    match = MARKER.match(cell.get('text', ''))
                    if match:
                        yield match[1], None


def native_lines(page, left, right, top, bottom, with_underlines=False):
    bounds = fitz.Rect(left, top, right, bottom)
    lines = {}
    mode = 'rawdict' if with_underlines else 'dict'
    rules = [drawing['rect'] for drawing in page.get_drawings()
             if drawing['width'] and abs(drawing['width'] - 0.48) < 0.01
             and drawing['rect'].height < 0.01 and drawing['rect'].width > 2
             and left <= drawing['rect'].x0 < right and top <= drawing['rect'].y0 <= bottom
             ] if with_underlines else []
    for block in page.get_text(mode, clip=bounds, flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)['blocks']:
        for line in block.get('lines', ()):
            x, y, _, end = line['bbox']
            text = (styled_text(line, [rule for rule in rules if abs(rule.y0 - end) < 1.4])
                    if with_underlines else ''.join(span['text'] for span in line['spans'])).strip()
            if text:
                lines[round(x, 1), round(y, 1), text] = Line(x, y, text)
    return list(lines.values())


def styled_text(line, rules):
    parts = []
    underlined = False
    for span in line['spans']:
        for char in span['chars']:
            x0, _, x1, bottom = char['bbox']
            center = (x0 + x1) / 2
            highlight = any(rule.x0 <= center <= rule.x1 and abs(rule.y0 - bottom) < 1.1 for rule in rules)
            if highlight != underlined:
                parts.append('<u>' if highlight else '</u>')
                underlined = highlight
            parts.append(char['c'])
    if underlined:
        parts.append('</u>')
    return ''.join(parts)


def anchors_for_column(page, blocks, left, right, top, bottom):
    lines = native_lines(page, left, right, top, bottom)
    column_x = 87.9 if left < 400 else 436.6
    candidates = [(line, MARKER.match(line.text)) for line in lines
                  if abs(line.x - column_x) < 1.5]
    markers = {}
    for marker, bbox in ir_markers(blocks):
        if bbox is not None and not left <= bbox['x'] < right:
            continue
        y = page.rect.height - bbox['y'] - bbox['height'] if bbox else None
        for line, match in candidates:
            if match and match[1] == marker and (y is None or abs(y - line.y) <= 7):
                markers[marker] = (line, match)
    missing = {match[1] for _, match in candidates if match} - markers.keys()
    if missing:
        raise ValueError(f'kordoc 경계 누락, p.{page.number + 1}: {sorted(missing)}')
    return sorted(markers.values(), key=lambda item: item[0].y)


def read_region(page, year, local_page, left, right, top, bottom):
    if bottom <= top:
        return ''
    lines = native_lines(page, left, right, top, bottom, with_underlines=True)
    visuals = VISUALS if year == 2026 else VISUALS_2027
    for (x0, y0, x1, y1), text in visuals.get(local_page, ()):
        if left <= x0 < right and top <= y0 < bottom:
            lines = [line for line in lines if not (x0 - 4 <= line.x <= x1 and y0 - 1 <= line.y <= y1)]
            lines.append(Line(x0, y0, text))
    for label, begin, end in BRACKETS[year].get((local_page, int(left > 400)), ()):
        if top <= begin < bottom:
            lines = [line for line in lines if line.text != f'[{label}]']
            lines.extend((Line(left, begin, f'[{label} 시작]'), Line(left, end, f'[{label} 끝]')))
    if year == 2026 and local_page == 4 and left > 400 and top > 850:
        # The number is vertically centered between the two phrases it labels.
        lines = [Line(line.x, line.y - 9, line.text) if line.text in CHOICES else line for line in lines]
    lines.sort(key=lambda line: (round(line.y / 2), line.x, line.y))
    chunks = []
    for line in lines:
        text = line.text.translate(GLYPHS)
        if re.fullmatch(r'\*\s*확인 사항', text):
            break
        if year == 2026 and local_page == 17:
            archaic_ends = ('15세기 국어에서는 ‘', '형식과 내용의 결합은 변할 수 있다. ‘',
                            '’의 ‘', '외에 ‘ㆆ, ㅿ,')
            if text.endswith(archaic_ends):
                chunks.append(text + 'ㆁ')
                continue
            if chunks and chunks[-1].endswith('ㆁ') and text.startswith(('’', ',')):
                chunks[-1] += text
                continue
        chunks.append(text)
    return '\n'.join(chunks).strip()


def extract_questions(document, parsed, year):
    by_page = {page: [] for page in range(1, 41)}
    for block in parsed['blocks']:
        by_page[block['pageNumber']].append(block)
    questions = {}
    for form_i, form in enumerate(FORMS):
        for section, (first, last, expected) in SECTIONS.items():
            segments = []
            current = None
            for local_page in range(first, last + 1):
                page = document[form_i * 20 + local_page - 1]
                top = 215 if local_page in (1, 13, 17) else 145
                for left, right in ((85, 417), (428, 760)):
                    anchors = anchors_for_column(page, by_page[page.number + 1], left, right, top, 1065)
                    begin = top
                    for line, marker in [*anchors, (Line(0, 1065, ''), None)]:
                        end = line.y - 1
                        if current is not None:
                            text = read_region(page, year, local_page, left, right, begin, end)
                            if text:
                                current['parts'].append(text)
                                current['regions'].append({'page': page.number + 1,
                                                           'bbox': [left, round(begin, 1), right, round(end, 1)]})
                        if marker:
                            current = {'marker': marker, 'parts': [], 'regions': []}
                            segments.append(current)
                        begin = end
            shared = None
            actual = []
            for segment in segments:
                marker = segment['marker']
                source = {'text': '\n'.join(segment['parts']), 'regions': segment['regions']}
                if marker[2]:
                    shared = (range(int(marker[2]), int(marker[3]) + 1), source)
                    continue
                number = int(marker[4])
                actual.append(number)
                context = shared[1] if shared and number in shared[0] else None
                options = ''.join(ch for ch in source['text'] if ch in CHOICES)
                if not source['text'].startswith(f'{number}.') or options != CHOICES:
                    raise ValueError(f'{form} {section} {number}번의 번호 또는 선택지가 누락되었습니다.')
                qid = f'{form}/{section}/{number:02d}'
                questions[qid] = dict(form=form, section=section, number=number, passage=context, item=source)
            if actual != list(expected):
                raise ValueError(f'{form} {section}의 문항 순서 오류: {actual}')
    return questions


def extract_key(parsed):
    answer_key = {}
    for form_i, form in enumerate(FORMS, 1):
        blocks = [b for b in parsed['blocks'] if b['pageNumber'] == form_i]
        if not any(form[:2] in b.get('text', '') for b in blocks):
            raise ValueError(f'정답표에서 {form} 표기를 찾지 못했습니다.')
        table, = (block['table'] for block in blocks if block['type'] == 'table')
        for row in table['cells'][3:]:
            for index, section in enumerate(('공통', '공통', '화법과 작문', '언어와 매체')):
                number, choice, points = (cell['text'].strip() for cell in row[3 * index:3 * index + 3])
                if not number and not choice and not points:
                    continue
                number, points = int(number), int(points)
                qid = f'{form}/{section}/{number:02d}'
                if not choice or choice not in CHOICES or len(choice) != 1 or points not in (2, 3) or qid in answer_key:
                    raise ValueError(f'정답표 셀 형식 오류: {qid}')
                answer_key[qid] = {'answer': CHOICES.index(choice) + 1, 'points': points}
    return answer_key


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, choices=EXAM_SHA256, default=2027)
    parser.add_argument('--output', type=Path, default=ROOT / 'output')
    args = parser.parse_args()
    exam, key = one_pdf('subjects', args.year), one_pdf('answer_sheets', args.year)
    digest = sha256(exam)
    if digest != EXAM_SHA256[args.year]:
        raise ValueError('수동 전사 자료와 영역 배치가 등록된 국어 문제지와 다릅니다.')
    parsed_exam, parsed_key = kordoc(exam), kordoc(key)
    if (parsed_exam['pageCount'], parsed_key['pageCount']) != (40, 2):
        raise ValueError('문제지/정답표 페이지 수가 예상과 다릅니다.')
    with fitz.open(exam) as document:
        questions = extract_questions(document, parsed_exam, args.year)
    answers = extract_key(parsed_key)
    if questions.keys() != answers.keys():
        raise ValueError('문제지와 정답표의 문항 목록이 일치하지 않습니다.')
    for qid, question in questions.items():
        if ('[3점]' in question['item']['text']) != (answers[qid]['points'] == 3):
            raise ValueError(f'문제지와 정답표의 배점이 일치하지 않습니다: {qid}')
    for form in FORMS:
        for elective in ('화법과 작문', '언어와 매체'):
            total = sum(answers[qid]['points'] for qid, q in questions.items()
                        if q['form'] == form and q['section'] in ('공통', elective))
            if total != 100:
                raise ValueError(f'{form} {elective}의 만점이 {total}점입니다.')
    output = args.output / str(args.year)
    write_json(output / 'questions.json', {'year': args.year, 'kordoc_version': parsed_exam['version'],
                                               'source_sha256': digest, 'questions': questions})
    write_json(output / 'answer_key.json', {'source_sha256': sha256(key), 'answers': answers})
    print(f'kordoc {parsed_exam["version"]} · {len(questions)}개 문항 분리 및 정답표 대조 완료')


if __name__ == '__main__':
    main()
