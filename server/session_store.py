import time
import secrets
import threading

_sessions = {}
_lock = threading.Lock()
SESSION_TIMEOUT = 86400

def create_session(data):
    session_id = secrets.token_hex(32)
    with _lock:
        _sessions[session_id] = {
            'data': data,
            'created_at': time.time(),
            'accessed_at': time.time()
        }
    return session_id

def get_session(session_id):
    if not session_id:
        return None
    with _lock:
        session = _sessions.get(session_id)
        if not session:
            return None
        if time.time() - session['accessed_at'] > SESSION_TIMEOUT:
            del _sessions[session_id]
            return None
        expires = session['data'].get('expires')
        if expires and time.time() > expires:
            del _sessions[session_id]
            return None
        session['accessed_at'] = time.time()
        return session['data']

def update_session(session_id, data):
    if not session_id:
        return
    with _lock:
        if session_id in _sessions:
            _sessions[session_id]['data'] = data
            _sessions[session_id]['accessed_at'] = time.time()

def destroy_session(session_id):
    with _lock:
        _sessions.pop(session_id, None)

def cleanup_expired():
    with _lock:
        now = time.time()
        expired = [sid for sid, s in _sessions.items()
                   if now - s['accessed_at'] > SESSION_TIMEOUT
                   or (s['data'].get('expires') and now > s['data']['expires'])]
        for sid in expired:
            del _sessions[sid]

def iter_admin_sessions():
    with _lock:
        now = time.time()
        result = []
        for sid, s in list(_sessions.items()):
            data = s['data']
            if data.get('role') == 'admin':
                expires = data.get('expires') or s['accessed_at'] + SESSION_TIMEOUT
                if now < expires and now - s['accessed_at'] <= SESSION_TIMEOUT:
                    result.append(data)
        return result

def destroy_admin_sessions(username):
    with _lock:
        for sid in list(_sessions.keys()):
            data = _sessions[sid].get('data', {})
            if data.get('admin_username') == username:
                del _sessions[sid]

def destroy_user_sessions(user_id, except_session_id=None):
    with _lock:
        for sid in list(_sessions.keys()):
            data = _sessions[sid].get('data', {})
            if data.get('userId') == user_id and sid != except_session_id:
                del _sessions[sid]

def _cleanup_loop():
    while True:
        time.sleep(300)
        cleanup_expired()

_cleanup_thread = threading.Thread(target=_cleanup_loop, daemon=True)
_cleanup_thread.start()
