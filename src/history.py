import sqlite3
import json
from datetime import datetime
import os
from src.config import BASE_DIR

# Store history.db alongside the project root, not relative to CWD
_DEFAULT_DB_PATH = os.path.join(BASE_DIR, "history.db")


class HistoryManager:
    def __init__(self, db_path=_DEFAULT_DB_PATH):
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
                    eval_method TEXT DEFAULT 'heuristic',
                    context TEXT
                )
            """)
            # Migration: add eval_method column to existing DBs
            try:
                cursor.execute("ALTER TABLE analysis_history ADD COLUMN eval_method TEXT DEFAULT 'heuristic'")
            except sqlite3.OperationalError:
                pass  # Column already exists
            conn.commit()

    def save_analysis(self, error_input, result, faithfulness, relevancy, context, eval_method="heuristic"):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO analysis_history
                (timestamp, error_input, analysis_result, faithfulness, relevancy, eval_method, context)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                error_input,
                result,
                faithfulness,
                relevancy,
                eval_method,
                json.dumps(context),
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
            cursor.execute("SELECT COUNT(*), AVG(faithfulness), AVG(relevancy) FROM analysis_history")
            count, avg_faith, avg_relevancy = cursor.fetchone()
            return {
                "total_analyses": count or 0,
                "avg_faithfulness": avg_faith or 0.0,
                "avg_relevancy": avg_relevancy or 0.0,
            }

    def get_patterns(self, min_occurrences: int = 2, limit: int = 10) -> list:
        """Returns recurring error patterns grouped by the first 80 chars of the input.

        A high occurrence count with a low avg_faithfulness signals that the KB
        lacks coverage for this error type — a direct action item for the team.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    substr(error_input, 1, 80) AS error_prefix,
                    COUNT(*)                   AS occurrences,
                    AVG(faithfulness)          AS avg_faithfulness,
                    AVG(relevancy)             AS avg_relevancy,
                    MAX(timestamp)             AS last_seen
                FROM analysis_history
                GROUP BY substr(error_input, 1, 80)
                HAVING occurrences >= ?
                ORDER BY occurrences DESC
                LIMIT ?
            """, (min_occurrences, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_weak_coverage_errors(self, faithfulness_threshold: float = 0.5, limit: int = 5) -> list:
        """Returns error types where the KB consistently provides poor context.

        These are errors the team should prioritise adding documentation for.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    substr(error_input, 1, 80) AS error_prefix,
                    COUNT(*)                   AS occurrences,
                    AVG(faithfulness)          AS avg_faithfulness
                FROM analysis_history
                GROUP BY substr(error_input, 1, 80)
                HAVING avg_faithfulness < ? AND occurrences >= 2
                ORDER BY avg_faithfulness ASC
                LIMIT ?
            """, (faithfulness_threshold, limit))
            return [dict(row) for row in cursor.fetchall()]
