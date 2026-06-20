import sqlite3
import os
import threading

DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
DB_PATH = os.path.join(DATA_DIR, 'sms.db')

_connection = None
_db_lock = threading.Lock()

def get_connection():
    global _connection
    if _connection is None:
        with _db_lock:
            if _connection is None:
                os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
                _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
                _connection.row_factory = sqlite3.Row
                _connection.execute('PRAGMA journal_mode=WAL')
                _connection.execute('PRAGMA foreign_keys=ON')
                _init_tables()
    return _connection

def _init_tables():
    conn = get_connection()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            registered_at DATETIME DEFAULT (datetime('now','localtime')),
            last_login_at DATETIME,
            last_active_at DATETIME,
            login_fail_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS reg_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            unique_key TEXT UNIQUE NOT NULL,
            expires_at DATETIME NOT NULL,
            is_used INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS login_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at DATETIME NOT NULL,
            is_used INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS authorized_phones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_phone TEXT NOT NULL,
            authorized_phone TEXT NOT NULL,
            created_at DATETIME DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (owner_phone) REFERENCES users(phone)
        );

        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME NOT NULL,
            phone TEXT DEFAULT '',
            action TEXT NOT NULL,
            detail TEXT DEFAULT '',
            ip TEXT DEFAULT '',
            status TEXT DEFAULT 'success'
        );

        CREATE TABLE IF NOT EXISTS sms_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_phone TEXT NOT NULL,
            sender TEXT NOT NULL,
            content TEXT NOT NULL,
            received_at TEXT NOT NULL,
            created_at DATETIME DEFAULT (datetime('now','localtime')),
            is_read INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
        CREATE INDEX IF NOT EXISTS idx_reg_codes_key ON reg_codes(unique_key);
        CREATE INDEX IF NOT EXISTS idx_login_codes_phone ON login_codes(phone);
        CREATE INDEX IF NOT EXISTS idx_logs_created ON logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_logs_phone ON logs(phone);
        CREATE INDEX IF NOT EXISTS idx_sms_user ON sms_messages(user_id, id);
        CREATE INDEX IF NOT EXISTS idx_sms_unread ON sms_messages(user_id, is_read);

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            level TEXT DEFAULT 'info',
            related_id INTEGER DEFAULT 0,
            is_read INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(is_read);
        CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(type);
    ''')
    try:
        conn.execute('ALTER TABLE users ADD COLUMN last_active_at DATETIME')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute('ALTER TABLE users ADD COLUMN exported_at DATETIME')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute('ALTER TABLE users ADD COLUMN language TEXT DEFAULT \'zh\'')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.commit()
    print('[数据库] 初始化完成')

def close():
    global _connection
    if _connection:
        _connection.close()
        _connection = None

def add_notification(type_, title, message, level='info', related_id=0):
    conn = get_connection()
    conn.execute(
        'INSERT INTO notifications (type, title, message, level, related_id) VALUES (?, ?, ?, ?, ?)',
        (type_, title, message, level, related_id)
    )
    conn.commit()

def get_notifications(limit=50, offset=0, unread_only=False):
    conn = get_connection()
    if unread_only:
        rows = conn.execute(
            'SELECT * FROM notifications WHERE is_read = 0 ORDER BY id DESC LIMIT ? OFFSET ?',
            (limit, offset)
        ).fetchall()
        total = conn.execute(
            'SELECT COUNT(*) as c FROM notifications WHERE is_read = 0'
        ).fetchone()['c']
    else:
        rows = conn.execute(
            'SELECT * FROM notifications ORDER BY id DESC LIMIT ? OFFSET ?',
            (limit, offset)
        ).fetchall()
        total = conn.execute(
            'SELECT COUNT(*) as c FROM notifications'
        ).fetchone()['c']
    return [dict(r) for r in rows], total

def mark_notification_read(notif_id):
    conn = get_connection()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (notif_id,))
    conn.commit()

def mark_all_notifications_read():
    conn = get_connection()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE is_read = 0')
    conn.commit()

def get_unread_notification_count():
    conn = get_connection()
    return conn.execute('SELECT COUNT(*) as c FROM notifications WHERE is_read = 0').fetchone()['c']

def delete_old_notifications(days=30):
    conn = get_connection()
    conn.execute(
        "DELETE FROM notifications WHERE created_at < datetime('now', ? || ' days')",
        (str(-days),)
    )
    conn.commit()
