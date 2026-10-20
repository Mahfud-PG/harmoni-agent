import sqlite3
import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sari_core.config_service import config

logger = logging.getLogger(__name__)

class DBManager:
    def __init__(self):
        self.db_path = config.DB_PATH
        self._init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, isolation_level=None) # autocommit
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for concurrency
        conn.execute('PRAGMA journal_mode=WAL;')
        # Foreign keys
        conn.execute('PRAGMA foreign_keys=ON;')
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Migration Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Check current version
            cursor.execute('SELECT MAX(version) as v FROM schema_version')
            row = cursor.fetchone()
            current_version = row['v'] if row and row['v'] is not None else 0
            
            self._apply_migrations(conn, current_version)

    def _apply_migrations(self, conn, current_version: int):
        cursor = conn.cursor()
        
        if current_version < 1:
            logger.info("Applying Migration v1: Core Schema")
            # Persons
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS persons (
                    person_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    profile_data TEXT 
                )
            ''')
            # Channels
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    person_id TEXT,
                    channel_type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(person_id) REFERENCES persons(person_id)
                )
            ''')
            # Events (Event Sourcing)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    person_id TEXT NOT NULL,
                    revision_number INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(person_id) REFERENCES persons(person_id),
                    UNIQUE(person_id, revision_number)
                )
            ''')
            # Snapshots
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    person_id TEXT NOT NULL,
                    last_revision_number INTEGER NOT NULL,
                    state_payload TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(person_id) REFERENCES persons(person_id),
                    UNIQUE(person_id, last_revision_number)
                )
            ''')
            # Provenance & Long Term Memories
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ltm_facts (
                    fact_id TEXT PRIMARY KEY,
                    person_id TEXT NOT NULL,
                    fact_text TEXT NOT NULL,
                    importance_score INTEGER DEFAULT 5,
                    confidence_score REAL DEFAULT 1.0,
                    source_channel TEXT,
                    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_verified_at TIMESTAMP,
                    status TEXT DEFAULT 'CAPTURED',
                    FOREIGN KEY(person_id) REFERENCES persons(person_id)
                )
            ''')
            
            cursor.execute('INSERT INTO schema_version (version) VALUES (1)')
            current_version = 1

        if current_version < 2:
            logger.info("Applying Migration v2: Conversation Sessions & Messages Schema")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    platform TEXT DEFAULT 'DESKTOP_UI',
                    created_at TEXT DEFAULT (datetime('now', 'localtime')),
                    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
                    is_active INTEGER DEFAULT 0
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS session_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    text TEXT NOT NULL,
                    timestamp TEXT DEFAULT (datetime('now', 'localtime')),
                    FOREIGN KEY(session_id) REFERENCES conversation_sessions(session_id) ON DELETE CASCADE
                )
            ''')
            cursor.execute('INSERT INTO schema_version (version) VALUES (2)')
            current_version = 2
            
        logger.info(f"Database initialized at version {current_version}")

db = DBManager()
