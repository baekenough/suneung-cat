"""Store scored exam runs and per-question evidence transactionally in SQLite."""
import json
import sqlite3
from contextlib import closing

SCHEMA = '''
CREATE TABLE IF NOT EXISTS runs (
    benchmark_key TEXT NOT NULL, model TEXT NOT NULL, year INTEGER NOT NULL, subject TEXT NOT NULL,
    questions_sha256 TEXT NOT NULL, answer_pdf_sha256 TEXT NOT NULL, reasoning_effort TEXT NOT NULL,
    score REAL, elapsed_seconds REAL, solved INTEGER NOT NULL, question_count INTEGER NOT NULL,
    metrics_json TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (benchmark_key, model)
);
CREATE TABLE IF NOT EXISTS responses (
    benchmark_key TEXT NOT NULL, model TEXT NOT NULL, question_id TEXT NOT NULL,
    expected INTEGER NOT NULL, prediction INTEGER, points INTEGER NOT NULL, correct INTEGER,
    request_json TEXT,
    PRIMARY KEY (benchmark_key, model, question_id),
    FOREIGN KEY (benchmark_key, model) REFERENCES runs (benchmark_key, model) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS runs_subject_year ON runs (subject, year, score);
'''


def save_results(path, subject, benchmark_key, summary):
    with closing(sqlite3.connect(path, timeout=15)) as db:
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('PRAGMA journal_mode = WAL')
        db.executescript(SCHEMA)
        with db:
            for model in summary['models']:
                metrics = {key: value for key, value in model.items() if key != 'items'}
                overall = model['overall']
                existing = db.execute('SELECT solved FROM runs WHERE benchmark_key=? AND model=?',
                                      (benchmark_key, model['model'])).fetchone()
                if existing and existing[0] > overall['solved']:
                    continue
                db.execute('''INSERT INTO runs (benchmark_key,model,year,subject,questions_sha256,answer_pdf_sha256,
                    reasoning_effort,score,elapsed_seconds,solved,question_count,metrics_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT (benchmark_key,model) DO UPDATE SET
                    score=excluded.score,elapsed_seconds=excluded.elapsed_seconds,solved=excluded.solved,
                    question_count=excluded.question_count,metrics_json=excluded.metrics_json,updated_at=CURRENT_TIMESTAMP''',
                    (benchmark_key, model['model'], summary['year'], subject, summary['question_sha256'],
                     summary['answer_pdf_sha256'], summary['settings']['reasoning_effort'], model['mean_score'],
                     model['elapsed_seconds'], overall['solved'], overall['questions'], json.dumps(metrics, ensure_ascii=False)))
                db.executemany('''INSERT INTO responses (benchmark_key,model,question_id,expected,prediction,points,correct,request_json)
                    VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (benchmark_key,model,question_id) DO UPDATE SET
                    expected=excluded.expected,prediction=excluded.prediction,points=excluded.points,
                    correct=excluded.correct,request_json=excluded.request_json''',
                    [(benchmark_key, model['model'], item['qid'], item['answer'], item['prediction'], item['points'],
                      item['correct'], json.dumps(item['request'], ensure_ascii=False) if item['request'] is not None else None)
                     for item in model['items']])
