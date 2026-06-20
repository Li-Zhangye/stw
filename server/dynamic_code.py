import time
import threading
from utils import generate_code

_codes = {}
_lock = threading.Lock()

def get_or_create_code(phone):
    with _lock:
        now = time.time()
        record = _codes.get(phone)
        if record and now - record['created_at'] < 60:
            return record['code']
        code = generate_code(6)
        _codes[phone] = {
            'code': code,
            'created_at': now
        }
        return code

def validate_code(phone, code):
    with _lock:
        record = _codes.get(phone)
        if not record:
            return False
        if record['code'] == code:
            del _codes[phone]
            return True
        return False

def cleanup_old():
    while True:
        time.sleep(60)
        with _lock:
            now = time.time()
            expired = [k for k, v in _codes.items() if now - v['created_at'] > 30]
            for k in expired:
                del _codes[k]

cleanup_thread = threading.Thread(target=cleanup_old, daemon=True)
cleanup_thread.start()
