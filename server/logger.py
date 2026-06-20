import time
import threading
import re
from db import get_connection

_LOG_CLEAN_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_LOG_CRLF_RE = re.compile(r'[\r\n]+')

def _clean(val):
    if isinstance(val, str):
        val = _LOG_CLEAN_RE.sub('', val)
        val = _LOG_CRLF_RE.sub(' ', val)
        return val
    return val

_log_buffer = []
_buffer_lock = threading.Lock()
_flush_interval = 5

def add_log(action, phone, detail, ip='', status='success'):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    entry = (_clean(timestamp), _clean(phone), _clean(action), _clean(detail), _clean(ip), _clean(status))
    with _buffer_lock:
        _log_buffer.append(entry)

def _flush_logs():
    while True:
        time.sleep(_flush_interval)
        with _buffer_lock:
            if not _log_buffer:
                continue
            batch = _log_buffer[:]
            _log_buffer.clear()
        try:
            db = get_connection()
            db.executemany(
                'INSERT INTO logs (created_at, phone, action, detail, ip, status) VALUES (?, ?, ?, ?, ?, ?)',
                batch
            )
            db.commit()
        except Exception as e:
            print(f'[日志] 写入失败: {e}')

_flush_thread = threading.Thread(target=_flush_logs, daemon=True)
_flush_thread.start()

def init_logs_table():
    db = get_connection()
    db.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME NOT NULL,
            phone TEXT DEFAULT '',
            action TEXT NOT NULL,
            detail TEXT DEFAULT '',
            ip TEXT DEFAULT '',
            status TEXT DEFAULT 'success'
        )
    ''')
    db.execute('''
        CREATE INDEX IF NOT EXISTS idx_logs_created ON logs(created_at)
    ''')
    db.execute('''
        CREATE INDEX IF NOT EXISTS idx_logs_phone ON logs(phone)
    ''')
    db.commit()

def get_logs(limit=200, offset=0, action_filter=None, phone_filter=None):
    db = get_connection()
    where = []
    params = []
    if action_filter:
        where.append('action = ?')
        params.append(action_filter)
    if phone_filter:
        where.append('phone = ?')
        params.append(phone_filter)

    where_clause = ' AND '.join(where) if where else '1=1'
    rows = db.execute(
        f'SELECT * FROM logs WHERE {where_clause} ORDER BY id DESC LIMIT ? OFFSET ?',
        params + [limit, offset]
    ).fetchall()
    return [dict(r) for r in rows]

def get_log_stats():
    db = get_connection()
    total = db.execute('SELECT COUNT(*) as c FROM logs').fetchone()['c']
    today = db.execute(
        "SELECT COUNT(*) as c FROM logs WHERE created_at >= datetime('now', 'start of day')"
    ).fetchone()['c']
    actions = db.execute(
        'SELECT action, COUNT(*) as c FROM logs GROUP BY action ORDER BY c DESC'
    ).fetchall()
    return {
        'total': total,
        'today': today,
        'actions': [{'action': r['action'], 'count': r['c']} for r in actions]
    }
