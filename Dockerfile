FROM python:3.12-slim
WORKDIR /app
COPY requirements-dashboard.txt .
RUN pip install --no-cache-dir -r requirements-dashboard.txt
RUN python - <<'PY'
from hashlib import sha256
import re
from pathlib import Path

import streamlit

# The deployed theme uses system fonts. Remove Streamlit's default startup font.
index = Path(streamlit.__file__).parent / 'static' / 'index.html'
html = index.read_text(encoding='utf-8')
source_sans_preload = r'<link\s+rel="preload"\s+href="\./static/media/SourceSansVF-Upright\.[^"]+\.woff2"[^>]*>'
html = re.sub(source_sans_preload, '', html)
for href in re.findall(r'href="(\./static/css/index\.[^"]+\.css)"', html):
    stylesheet = index.parent / href
    css = re.sub(r'@font-face\{font-family:Source Sans;[^}]*\}', '', stylesheet.read_text(encoding='utf-8'))
    digest = sha256(css.encode()).hexdigest()[:12]
    optimized = stylesheet.with_name(f'index.{digest}.css')
    optimized.write_text(css, encoding='utf-8')
    html = html.replace(href, f'./static/css/{optimized.name}')
index.write_text(html, encoding='utf-8')
PY
COPY . .
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    CSAT_LEADERBOARD_FILE=/app/public-leaderboard.json
EXPOSE 80
CMD ["sh", "-c", "exec streamlit run dashboard.py --server.port \"${PORT:-80}\" --theme.font 'system-ui, sans-serif'"]
