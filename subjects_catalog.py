"""Identifiers, release times and leaderboard groupings for the 2027 exam."""
from datetime import datetime, timedelta, timezone


KST = timezone(timedelta(hours=9))
ENGLISH_RELEASE = datetime(2026, 11, 19, 17, 4, tzinfo=KST)
FOURTH_RELEASE = datetime(2026, 11, 19, 20, 15, tzinfo=KST)
GROUPS = {'korean': '국어', 'math': '수학', 'english': '영어', 'history': '한국사',
          'social': '사회탐구', 'science': '과학탐구', 'vocational': '직업탐구'}
COURSES = {
    'social': ('생활과 윤리', '윤리와 사상', '한국지리', '세계지리', '동아시아사', '세계사',
               '경제', '정치와 법', '사회·문화'),
    'science': ('물리학Ⅰ', '화학Ⅰ', '생명과학Ⅰ', '지구과학Ⅰ', '물리학Ⅱ', '화학Ⅱ', '생명과학Ⅱ', '지구과학Ⅱ'),
    'vocational': ('성공적인 직업생활', '농업 기초 기술', '공업 일반', '상업 경제', '수산·해운 산업 기초', '인간 발달'),
}
COURSE_OPTIONS = {group: {f'{group}-{number:02}': title for number, title in enumerate(titles, 1)}
                  for group, titles in COURSES.items()}
LABELS = {**GROUPS, **{key: title for options in COURSE_OPTIONS.values() for key, title in options.items()}}
RELEASE_ASSETS = {'history': ('history', '41')}
for group, prefix in (('social', '42'), ('science', '43'), ('vocational', '44')):
    RELEASE_ASSETS.update({key: (group, f'{prefix}_{number}')
                           for number, key in enumerate(COURSE_OPTIONS[group], 1)})
DATASETS = ('korean', 'math', 'english', *RELEASE_ASSETS)


def dataset_directory(dataset, year=2027):
    return str(year) if dataset == 'korean' else f'{year}-{dataset}'
