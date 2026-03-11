import sqlite3
import json
from datetime import datetime
import os

class HistoryManager:
    def __init__(self, db_path="history.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analysis_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    error_input TEXT,
                    analysis_result TEXT,
                    faithfulness REAL,
                    relevancy REAL,
                    context_precision REAL DEFAULT 0.0,
                    context_recall REAL DEFAULT 0.0,
                    context TEXT
                )
            """)
            # Migrate: add new columns if table already exists without them
            try:
                cursor.execute("ALTER TABLE analysis_history ADD COLUMN context_precision REAL DEFAULT 0.0")
            except sqlite3.OperationalError:
                pass  # column already exists
            try:
                cursor.execute("ALTER TABLE analysis_history ADD COLUMN context_recall REAL DEFAULT 0.0")
            except sqlite3.OperationalError:
                pass  # column already exists
            conn.commit()

    def save_analysis(self, error_input, result, faithfulness, relevancy, context,
                      context_precision=0.0, context_recall=0.0):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO analysis_history
                (timestamp, error_input, analysis_result, faithfulness, relevancy,
                 context_precision, context_recall, context)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                error_input,
                result,
                faithfulness,
                relevancy,
                context_precision,
                context_recall,
                json.dumps(context)
            ))
            conn.commit()

    def get_history(self, limit=50):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM analysis_history ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*), AVG(faithfulness), AVG(relevancy),
                       AVG(context_precision), AVG(context_recall)
                FROM analysis_history
            """)
            count, avg_faith, avg_relevancy, avg_ctx_prec, avg_ctx_recall = cursor.fetchone()
            return {
                "total_analyses": count or 0,
                "avg_faithfulness": avg_faith or 0.0,
                "avg_relevancy": avg_relevancy or 0.0,
                "avg_context_precision": avg_ctx_prec or 0.0,
                "avg_context_recall": avg_ctx_recall or 0.0,
            }
