FROM python:3.12-slim
WORKDIR /app
COPY requirements-dashboard.txt .
RUN pip install --no-cache-dir -r requirements-dashboard.txt
COPY . .
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    CSAT_LEADERBOARD_FILE=/app/public-leaderboard.json
EXPOSE 80
CMD ["sh", "-c", "exec streamlit run dashboard.py --server.port \"${PORT:-80}\""]
