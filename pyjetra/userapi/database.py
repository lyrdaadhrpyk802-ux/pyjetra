import sqlite3
import os
import json


class Database:
    """
    Local SQLite database for storing messages, dialogs, and groups.
    """
    
    def __init__(self, db_path="jetra_local.db"):
        self.db_path = db_path
        self.conn = None
        self._connect()
    
    def _connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
    
    def _create_tables(self):
        cursor = self.conn.cursor()
        
        # Messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER NOT NULL,
                peer_id INTEGER NOT NULL,
                peer_type TEXT NOT NULL,
                from_id INTEGER NOT NULL,
                date INTEGER NOT NULL,
                text TEXT,
                PRIMARY KEY (id, peer_id, peer_type)
            )
        ''')
        
        # Dialogs table (users and groups)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dialogs (
                peer_id INTEGER PRIMARY KEY,
                peer_type TEXT NOT NULL,
                title TEXT,
                access_hash INTEGER,
                updated_at INTEGER
            )
        ''')
        
        self.conn.commit()
    
    def save_message(self, message):
        """Save a message to the local database."""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO messages 
                (id, peer_id, peer_type, from_id, date, text)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                message.id,
                message.peer_id,
                message.peer_type,
                message.from_id,
                message.date,
                message.text,
            ))
            self.conn.commit()
        except Exception as e:
            print(f"Failed to save message: {e}")
    
    def get_messages(self, peer_id=None, limit=100):
        """Get messages from a specific peer or all peers."""
        cursor = self.conn.cursor()
        if peer_id is not None:
            cursor.execute('''
                SELECT * FROM messages 
                WHERE peer_id = ? 
                ORDER BY date DESC 
                LIMIT ?
            ''', (peer_id, limit))
        else:
            cursor.execute('''
                SELECT * FROM messages 
                ORDER BY date DESC 
                LIMIT ?
            ''', (limit,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def save_dialog(self, peer_id, peer_type, title, access_hash):
        """Save or update a dialog."""
        cursor = self.conn.cursor()
        import time
        cursor.execute('''
            INSERT OR REPLACE INTO dialogs 
            (peer_id, peer_type, title, access_hash, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (peer_id, peer_type, title, access_hash, int(time.time())))
        self.conn.commit()
    
    def get_dialogs(self, peer_type=None):
        """Get all dialogs, optionally filtered by type."""
        cursor = self.conn.cursor()
        if peer_type:
            cursor.execute('SELECT * FROM dialogs WHERE peer_type = ? ORDER BY title', (peer_type,))
        else:
            cursor.execute('SELECT * FROM dialogs ORDER BY title')
        return [dict(row) for row in cursor.fetchall()]
    
    def close(self):
        if self.conn:
            self.conn.close()
