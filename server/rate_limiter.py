import time
import threading

_limits = {}
_lock = threading.Lock()

def check_rate_limit(key, max_attempts=5, window=60):
    with _lock:
        now = time.time()
        record = _limits.get(key)
        if not record or now - record['start'] > window:
            _limits[key] = {'count': 1, 'start': now}
            return True
        record['count'] += 1
        if record['count'] > max_attempts:
            return False
        return True

def _cleanup():
    while True:
        time.sleep(60)
        with _lock:
            now = time.time()
            expired = [k for k, v in _limits.items() if now - v['start'] > 120]
            for k in expired:
                del _limits[k]

_thread = threading.Thread(target=_cleanup, daemon=True)
_thread.start()
