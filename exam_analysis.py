"""Summarize scored papers without publishing answers or model responses."""
from collections import Counter
import statistics


def analyze(data, models):
    complete = [model for model in models if model['mean_score'] is not None]
    if not complete:
        return None
    scores = [model['mean_score'] for model in complete]
    fastest = min((model for model in complete if model['elapsed_seconds'] is not None),
                  key=lambda model: model['elapsed_seconds'], default=None)
    wrong = Counter(item['qid'] for model in complete for item in model['items']
                    if item['correct'] is False)
    hard_items = []
    for question_id, missed in sorted(wrong.items(), key=lambda item: (-item[1], item[0]))[:5]:
        question = data['questions'][question_id]
        hard_items.append({'form': question['form'], 'section': question['section'],
                           'number': question['number'], 'missed': missed})
    sections = []
    for section in data.get('sections', ()):
        scores_by_form = [record for model in complete for name, record in model['scores'].items()
                          if name.partition(' ')[2] == section]
        max_points = sum(record['max_points'] for record in scores_by_form)
        if max_points:
            sections.append({'name': section, 'percent': round(
                100 * sum(record['points'] for record in scores_by_form) / max_points, 2)})
    return {'completed': len(complete), 'registered': len(models), 'winner': complete[0]['model'],
            'top_score': max(scores), 'median_score': statistics.median(scores),
            'score_span': round(max(scores) - min(scores), 2),
            'fastest': {'model': fastest['model'], 'seconds': fastest['elapsed_seconds']} if fastest else None,
            'sections': sections, 'hard_items': hard_items}


def markdown(analysis):
    lines = [f'완료 모델 {analysis["completed"]}/{analysis["registered"]}개 · '
             f'1위 `{analysis["winner"]}` {analysis["top_score"]:.2f}점 · '
             f'중앙값 {analysis["median_score"]:.2f}점 · 최고–최저 {analysis["score_span"]:.2f}점']
    if fastest := analysis['fastest']:
        lines.append(f'최단 소요시간 `{fastest["model"]}` {fastest["seconds"]:.2f}초')
    if sections := analysis['sections']:
        lines.append('배점 기준 득점률 · ' + ' · '.join(f'{row["name"]} {row["percent"]:.2f}%' for row in sections))
    if items := analysis['hard_items']:
        lines.append('오답이 많은 문항 · ' + ' · '.join(
            f'{row["form"]} {row["section"]} {row["number"]}번 {row["missed"]}/{analysis["completed"]}개 모델'
            for row in items))
    return lines
