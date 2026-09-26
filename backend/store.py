import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS schemas (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    version INTEGER NOT NULL, status TEXT NOT NULL,
                    revision INTEGER NOT NULL, criteria TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(project_id, version)
                );
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    schema_id TEXT NOT NULL REFERENCES schemas(id), name TEXT NOT NULL,
                    sha256 TEXT NOT NULL, records TEXT NOT NULL, created_at TEXT NOT NULL
                );
            ''')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def schema(row):
        if row is None:
            return None
        result = dict(row)
        result['criteria'] = json.loads(result['criteria'])
        return result
