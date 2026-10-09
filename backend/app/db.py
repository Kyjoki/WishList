import os
import sqlite3
from pathlib import Path


MIGRATION_DIR = Path(__file__).resolve().parent.parent / 'migrations'


def connect():
    path = Path(os.getenv('DATABASE_PATH', 'playwatch.db'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    return db


def migrate():
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)')
        for file in sorted(MIGRATION_DIR.glob('[0-9][0-9][0-9]_*.sql')):
            version = int(file.name.split('_', 1)[0])
            if not db.execute('SELECT 1 FROM schema_migrations WHERE version=?', (version,)).fetchone():
                db.executescript(file.read_text(encoding='utf-8'))
                db.execute('INSERT INTO schema_migrations(version) VALUES (?)', (version,))
