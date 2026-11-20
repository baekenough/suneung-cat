"""Build the static public leaderboard using the local app's subject catalog."""

import json
from pathlib import Path
from shutil import copyfile, copytree

from site_config import FRONTIER_MODELS, PROVIDER_HOSTS, PROVIDERS, SHORT_COURSES
from subjects_catalog import COURSE_OPTIONS, DATASETS, ENGLISH_RELEASE, FOURTH_RELEASE, GROUPS, LABELS


ROOT = Path(__file__).resolve().parent
output = ROOT / 'web-dist'
copytree(ROOT / 'site', output, dirs_exist_ok=True)
image_directory = output / 'app/static'
image_directory.mkdir(parents=True, exist_ok=True)
copyfile(ROOT / 'static/suneung-cat-og.jpg', image_directory / 'suneung-cat-og.jpg')
catalog = {'groups': GROUPS, 'courses': COURSE_OPTIONS, 'labels': LABELS, 'datasets': DATASETS, 'providers': PROVIDERS,
           'providerHosts': PROVIDER_HOSTS, 'shortCourses': SHORT_COURSES, 'frontier': sorted(FRONTIER_MODELS),
           'release': {'english': ENGLISH_RELEASE.isoformat(), 'fourth': FOURTH_RELEASE.isoformat()}}
(output / 'catalog.js').write_text(f'export default {json.dumps(catalog, ensure_ascii=False)};\n', encoding='utf-8')
