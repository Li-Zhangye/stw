import os, sys, json, time, base64, http.server, urllib.parse, threading, socket, sqlite3, secrets

sys.path.insert(0, os.path.dirname(__file__))
from db import get_connection, close as db_close
from logger import add_log
def log(msg):
    t = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{t}] [守护进程] {msg}')
from utils import sanitize_html

DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
if not os.path.isdir(DATA_DIR):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        pass

CONFIG_PATH = os.path.join(DATA_DIR, 'config.json')
DAEMON_INFO_PATH = os.path.join(DATA_DIR, 'daemon.json')
PID_FILE = os.path.join(DATA_DIR, 'daemon.pid')

DAEMON_PORT = 0
_running = True
_start_time = time.time()

_NEW_SMS_EVENT = threading.Event()

MAX_SENDER_LEN = 100
MAX_CONTENT_LEN = 10000

def _load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def _save_config(cfg):
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except:
        pass

def _info_update_loop():
    while _running:
        time.sleep(10)
        _update_daemon_info()

def _escape_like(s):
    return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

def _validate_length(value, max_len, field_name):
    if not isinstance(value, str):
        return f'{field_name}格式错误'
    if len(value) > max_len:
        return f'{field_name}过长（最多{max_len}个字符）'
    return None

def _write_daemon_info():
    try:
        info = {
            'port': DAEMON_PORT,
            'pid': os.getpid(),
            'started_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'uptime': 0,
        }
        with open(DAEMON_INFO_PATH, 'w') as f:
            json.dump(info, f, indent=2, ensure_ascii=False)
        os.chmod(DAEMON_INFO_PATH, 0o644)
    except Exception as e:
        log(f'[守护进程] 写入信息文件失败: {e}')

def _update_daemon_info():
    try:
        if os.path.exists(DAEMON_INFO_PATH):
            with open(DAEMON_INFO_PATH, 'r') as f:
                info = json.load(f)
            info['uptime'] = int(time.time() - _start_time)
            info['port'] = DAEMON_PORT
            with open(DAEMON_INFO_PATH, 'w') as f:
                json.dump(info, f, indent=2, ensure_ascii=False)
    except:
        pass

def find_available_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

class DaemonHandler(http.server.BaseHTTPRequestHandler):
    server_tag = 'daemon'

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def _parse_body(self):
        content_type = self.headers.get('Content-Type', '')
        try:
            content_length = int(self.headers.get('Content-Length', 0))
        except (ValueError, TypeError):
            content_length = 0
        if content_length == 0:
            return {}
        content_length = min(content_length, 1 << 20)
        try:
            body = self.rfile.read(content_length)
        except Exception:
            return {}
        if 'application/json' in content_type:
            try:
                result = json.loads(body.decode('utf-8'))
                return result if isinstance(result, dict) else {}
            except:
                return {}
        try:
            text = body.decode('utf-8')
        except:
            return {}
        parsed = urllib.parse.parse_qs(text)
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)

    def _verify_token(self):
        auth = self.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return False
        token = auth[7:]
        cfg = _load_config()
        return token == cfg.get('daemon_token', '')

    def _handle(self):
        path = self.path.split('?')[0]
        query_params = {}
        if '?' in self.path:
            qs = urllib.parse.parse_qs(self.path.split('?')[1])
            query_params = {k: v[0] if len(v) == 1 else v for k, v in qs.items()}

        is_local = self.client_address[0] in ('127.0.0.1', '::1')

        if not is_local:
            if not self._verify_token():
                self._send_json({'success': False, 'message': 'unauthorized'}, 403)
                return
            is_local = True

        data = self._parse_body() if self.command == 'POST' else {}

        handlers = {
            ('GET', '/api/daemon/ping'): lambda: self._send_json({'ok': True}),
            ('GET', '/api/daemon/status'): self._handle_status,
            ('GET', '/api/daemon/sms/list'): lambda: self._handle_sms_list(data, query_params),
            ('POST', '/api/daemon/sms/list'): lambda: self._handle_sms_list(data, query_params),
            ('POST', '/api/daemon/sms/receive'): lambda: self._handle_sms_receive(data),
            ('POST', '/api/daemon/sms/batch-import'): lambda: self._handle_sms_batch_import(data),
            ('POST', '/api/daemon/sms/mark-read'): lambda: self._handle_sms_mark(data, 1),
            ('POST', '/api/daemon/sms/mark-unread'): lambda: self._handle_sms_mark(data, 0),
            ('POST', '/api/daemon/sms/delete'): lambda: self._handle_sms_delete(data),
            ('POST', '/api/daemon/sms/auto-cleanup'): lambda: self._handle_sms_auto_cleanup(data),
            ('GET', '/api/daemon/sms/export'): lambda: self._handle_sms_export(query_params),
            ('GET', '/api/daemon/sms/unread-count'): lambda: self._handle_sms_unread(query_params),
            ('POST', '/api/daemon/heartbeat'): lambda: self._handle_heartbeat(data),
            ('GET', '/api/daemon/device/status'): lambda: self._handle_device_status(query_params),
            ('POST', '/api/daemon/long-poll'): lambda: self._handle_long_poll(data),
        }

        handler = handlers.get((self.command, path))
        if handler:
            try:
                handler()
            except Exception as e:
                log(f'[守护进程错误] {self.command} {path}: {e}')
                self._send_json({'success': False, 'message': '内部错误'}, 500)
        else:
            self._send_json({'success': False, 'message': 'not found'}, 404)

    def _handle_status(self):
        db = get_connection()
        total_sms = db.execute('SELECT COUNT(*) as c FROM sms_messages').fetchone()['c']
        total_users = db.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
        unread = db.execute('SELECT COUNT(*) as c FROM sms_messages WHERE is_read = 0').fetchone()['c']
        self._send_json({
            'ok': True,
            'uptime': int(time.time() - _start_time),
            'total_sms': total_sms,
            'total_users': total_users,
            'unread_sms': unread,
        })

    def _handle_sms_list(self, data, query):
        user_id = data.get('userId', query.get('userId'))
        if not user_id:
            self._send_json({'success': False, 'message': '缺少用户ID'})
            return
        db = get_connection()
        user = db.execute('SELECT id FROM users WHERE id = ? AND is_active = 1', (user_id,)).fetchone()
        if not user:
            self._send_json({'success': False, 'message': '用户不存在'})
            return
        try:
            page = max(1, min(10000, int(query.get('page', 1))))
            limit = max(1, min(500, int(query.get('limit', 50))))
            since_id = int(query.get('since_id', 0))
        except ValueError:
            self._send_json({'success': False, 'message': '参数格式错误'})
            return
        search = query.get('search', '').strip()
        wait = query.get('wait') in ('1', 'true')
        offset = (page - 1) * limit
        if wait:
            _NEW_SMS_EVENT.clear()
        if search:
            like = f'%{_escape_like(search)}%'
            if since_id > 0:
                rows = db.execute(
                    'SELECT * FROM sms_messages WHERE user_id = ? AND id > ? AND (sender LIKE ? OR content LIKE ?) ORDER BY id DESC LIMIT ?',
                    (user_id, since_id, like, like, limit)
                ).fetchall()
            else:
                rows = db.execute(
                    'SELECT * FROM sms_messages WHERE user_id = ? AND (sender LIKE ? OR content LIKE ?) ORDER BY id DESC LIMIT ? OFFSET ?',
                    (user_id, like, like, limit, offset)
                ).fetchall()
        elif since_id > 0:
            rows = db.execute(
                'SELECT * FROM sms_messages WHERE user_id = ? AND id > ? ORDER BY id DESC LIMIT ?',
                (user_id, since_id, limit)
            ).fetchall()
            if wait and not rows:
                _NEW_SMS_EVENT.wait(timeout=25)
                _NEW_SMS_EVENT.clear()
                rows = db.execute(
                    'SELECT * FROM sms_messages WHERE user_id = ? AND id > ? ORDER BY id DESC LIMIT ?',
                    (user_id, since_id, limit)
                ).fetchall()
        else:
            rows = db.execute(
                'SELECT * FROM sms_messages WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?',
                (user_id, limit, offset)
            ).fetchall()
        total = db.execute(
            'SELECT COUNT(*) as c FROM sms_messages WHERE user_id = ?', (user_id,)
        ).fetchone()['c']
        unread = db.execute(
            'SELECT COUNT(*) as c FROM sms_messages WHERE user_id = ? AND is_read = 0', (user_id,)
        ).fetchone()['c']
        sms_data = []
        for r in rows:
            d = dict(r)
            d['sender'] = sanitize_html(d.get('sender', ''))
            d['content'] = sanitize_html(d.get('content', ''))
            sms_data.append(d)
        self._send_json({
            'success': True,
            'sms': sms_data,
            'total': total,
            'unread': unread,
            'page': page,
            'has_more': (offset + limit) < total
        })

    def _handle_sms_receive(self, data):
        user_id = data.get('userId')
        if not user_id:
            self._send_json({'success': False, 'message': '缺少用户ID'})
            return
        sender = data.get('sender', '')
        content = data.get('content', '')
        received_at = data.get('received_at', time.strftime('%Y-%m-%d %H:%M:%S'))
        ip = data.get('ip', '')
        if not sender or not content:
            self._send_json({'success': False, 'message': '缺少发件人或短信内容'})
            return
        err = _validate_length(sender, MAX_SENDER_LEN, '发件人') or _validate_length(content, MAX_CONTENT_LEN, '短信内容')
        if err:
            self._send_json({'success': False, 'message': err})
            return
        db = get_connection()
        user = db.execute('SELECT phone FROM users WHERE id = ? AND is_active = 1', (user_id,)).fetchone()
        if not user:
            self._send_json({'success': False, 'message': '用户不存在'})
            return
        db.execute(
            'INSERT INTO sms_messages (user_id, user_phone, sender, content, received_at) VALUES (?, ?, ?, ?, ?)',
            (user_id, user['phone'], sender, content, received_at)
        )
        db.execute(
            'UPDATE users SET last_active_at = datetime(\'now\',\'localtime\') WHERE id = ?',
            (user_id,)
        )
        db.commit()
        msg_id = db.execute('SELECT last_insert_rowid() as id').fetchone()['id']
        add_log('短信接收', user['phone'], f'来自{sender}: {content[:50]}', ip)
        log(f'[短信] 用户{user["phone"]} 收到来自{sender}的短信')
        _NEW_SMS_EVENT.set()
        self._send_json({'success': True, 'message': '已接收', 'id': msg_id})

    def _handle_sms_batch_import(self, data):
        user_id = data.get('userId')
        if not user_id:
            self._send_json({'success': False, 'message': '缺少用户ID'})
            return
        messages = data.get('messages', [])
        ip = data.get('ip', '')
        if not isinstance(messages, list) or not messages:
            self._send_json({'success': False, 'message': '短信列表格式错误'})
            return
        db = get_connection()
        user = db.execute('SELECT phone FROM users WHERE id = ? AND is_active = 1', (user_id,)).fetchone()
        if not user:
            self._send_json({'success': False, 'message': '用户不存在'})
            return
        imported = 0
        for msg in messages:
            sender = msg.get('sender', '')
            content = msg.get('content', '')
            received_at = msg.get('received_at', time.strftime('%Y-%m-%d %H:%M:%S'))
            if not sender or not content:
                continue
            existing = db.execute(
                'SELECT id FROM sms_messages WHERE user_id = ? AND sender = ? AND content = ? AND received_at = ?',
                (user_id, sender, content, received_at)
            ).fetchone()
            if existing:
                continue
            db.execute(
                'INSERT INTO sms_messages (user_id, user_phone, sender, content, received_at, is_read) VALUES (?, ?, ?, ?, ?, 1)',
                (user_id, user['phone'], sender, content, received_at)
            )
            imported += 1
        if imported > 0:
            db.commit()
            log(f'[短信] 用户{user["phone"]} 批量导入 {imported} 条历史短信')
            _NEW_SMS_EVENT.set()
        self._send_json({'success': True, 'imported': imported})

    def _handle_sms_mark(self, data, is_read):
        user_id = data.get('userId')
        ids = data.get('ids', [])
        if not user_id:
            self._send_json({'success': False, 'message': '缺少用户ID'})
            return
        if not isinstance(ids, list) or not ids:
            self._send_json({'success': False, 'message': '参数错误'})
            return
        ids = [int(i) for i in ids if str(i).isdigit()]
        if not ids:
            self._send_json({'success': False, 'message': '参数错误'})
            return
        db = get_connection()
        placeholders = ','.join('?' * len(ids))
        db.execute(
            f'UPDATE sms_messages SET is_read = ? WHERE user_id = ? AND id IN ({placeholders})',
            (is_read, user_id, *ids)
        )
        db.commit()
        self._send_json({'success': True, 'updated': len(ids)})

    def _handle_sms_delete(self, data):
        user_id = data.get('userId')
        ids = data.get('ids', [])
        if not user_id:
            self._send_json({'success': False, 'message': '缺少用户ID'})
            return
        if not isinstance(ids, list) or not ids:
            self._send_json({'success': False, 'message': '参数错误'})
            return
        ids = [int(i) for i in ids if str(i).isdigit()]
        if not ids:
            self._send_json({'success': False, 'message': '参数错误'})
            return
        db = get_connection()
        placeholders = ','.join('?' * len(ids))
        db.execute(
            f'DELETE FROM sms_messages WHERE user_id = ? AND id IN ({placeholders})',
            (user_id, *ids)
        )
        db.commit()
        self._send_json({'success': True, 'deleted': len(ids)})

    def _handle_sms_auto_cleanup(self, data):
        user_id = data.get('userId')
        if not user_id:
            self._send_json({'success': False, 'message': '缺少用户ID'})
            return
        db = get_connection()
        user = db.execute('SELECT id, phone, exported_at FROM users WHERE id = ? AND is_active = 1', (user_id,)).fetchone()
        if not user:
            self._send_json({'success': False, 'message': '用户不存在'})
            return
        count = db.execute('SELECT COUNT(*) as c FROM sms_messages WHERE user_id = ?', (user_id,)).fetchone()['c']
        if count == 0:
            self._send_json({'success': True, 'message': '没有需要清除的短信', 'deleted': 0})
            return
        has_exported = user['exported_at'] is not None
        if has_exported:
            db.execute('DELETE FROM sms_messages WHERE user_id = ?', (user_id,))
            db.commit()
            self._send_json({'success': True, 'message': f'已清除{count}条短信', 'deleted': count})
        else:
            self._send_json({'success': True, 'message': '您从未导出过短信，数据已保留但请注意隐私安全', 'deleted': 0, 'never_exported': True})

    def _handle_sms_export(self, query):
        user_id = query.get('userId')
        if not user_id:
            self._send_json({'success': False, 'message': '缺少用户ID'})
            return
        db = get_connection()
        user = db.execute('SELECT id, phone FROM users WHERE id = ? AND is_active = 1', (user_id,)).fetchone()
        if not user:
            self._send_json({'success': False, 'message': '用户不存在'})
            return
        rows = db.execute(
            'SELECT id, sender, content, received_at, created_at, is_read FROM sms_messages WHERE user_id = ? ORDER BY id ASC',
            (user['id'],)
        ).fetchall()
        export_data = {
            'export_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'phone': user['phone'],
            'total': len(rows),
            'messages': [dict(r) for r in rows]
        }
        db.execute('UPDATE users SET exported_at = datetime(\'now\',\'localtime\') WHERE id = ?', (user['id'],))
        db.commit()
        self._send_json({'success': True, 'data': export_data})

    def _handle_sms_unread(self, query):
        user_id = query.get('userId')
        if not user_id:
            self._send_json({'success': False, 'message': '缺少用户ID'})
            return
        db = get_connection()
        user = db.execute('SELECT id FROM users WHERE id = ? AND is_active = 1', (user_id,)).fetchone()
        if not user:
            self._send_json({'success': False, 'message': '用户不存在'})
            return
        count = db.execute(
            'SELECT COUNT(*) as c FROM sms_messages WHERE user_id = ? AND is_read = 0',
            (user_id,)
        ).fetchone()['c']
        self._send_json({'success': True, 'unread': count})

    def _handle_heartbeat(self, data):
        user_id = data.get('userId')
        if not user_id:
            self._send_json({'success': False, 'message': '缺少用户ID'})
            return
        db = get_connection()
        db.execute(
            'UPDATE users SET last_active_at = datetime(\'now\',\'localtime\') WHERE id = ?',
            (user_id,)
        )
        db.commit()
        self._send_json({'success': True, 'message': 'ok'})

    def _handle_device_status(self, query):
        user_id = query.get('userId')
        if not user_id:
            self._send_json({'success': False, 'message': '缺少用户ID'})
            return
        db = get_connection()
        row = db.execute(
            'SELECT last_active_at FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()
        if not row:
            self._send_json({'success': False, 'message': '用户不存在'})
            return
        last_active = row['last_active_at']
        online = False
        if last_active:
            try:
                active_ts = time.mktime(time.strptime(last_active, '%Y-%m-%d %H:%M:%S'))
                online = (time.time() - active_ts) < 60
            except:
                pass
        self._send_json({
            'success': True,
            'online': online,
            'last_active_at': last_active
        })

    def _handle_long_poll(self, data):
        user_id = data.get('userId')
        since_id = data.get('since_id', 0)
        timeout = min(int(data.get('timeout', 25)), 30)
        if not user_id:
            self._send_json({'success': False, 'message': '缺少用户ID'})
            return
        _NEW_SMS_EVENT.clear()
        _NEW_SMS_EVENT.wait(timeout=timeout)
        _NEW_SMS_EVENT.clear()
        db = get_connection()
        rows = db.execute(
            'SELECT * FROM sms_messages WHERE user_id = ? AND id > ? ORDER BY id DESC LIMIT 50',
            (user_id, since_id)
        ).fetchall()
        sms_data = []
        for r in rows:
            d = dict(r)
            d['sender'] = sanitize_html(d.get('sender', ''))
            d['content'] = sanitize_html(d.get('content', ''))
            sms_data.append(d)
        self._send_json({'success': True, 'sms': sms_data})


def run_daemon():
    global DAEMON_PORT, _running

    cfg = _load_config()
    if 'daemon_token' not in cfg:
        cfg['daemon_token'] = secrets.token_hex(32)
        _save_config(cfg)

    DAEMON_PORT = cfg.get('daemon_port', 0)
    if not DAEMON_PORT:
        DAEMON_PORT = find_available_port()
        cfg['daemon_port'] = DAEMON_PORT
        _save_config(cfg)

    try:
        server = http.server.ThreadingHTTPServer(('127.0.0.1', DAEMON_PORT), DaemonHandler)
    except OSError as e:
        log(f'[守护进程] 端口 {DAEMON_PORT} 绑定失败: {e}，尝试随机端口')
        DAEMON_PORT = find_available_port()
        cfg['daemon_port'] = DAEMON_PORT
        _save_config(cfg)
        try:
            server = http.server.ThreadingHTTPServer(('127.0.0.1', DAEMON_PORT), DaemonHandler)
        except OSError as e2:
            log(f'[守护进程] 端口绑定失败: {e2}')
            sys.exit(1)

    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

    _write_daemon_info()
    info_update_thread = threading.Thread(target=_info_update_loop, daemon=True)
    info_update_thread.start()

    log(f'[守护进程] 已启动 http://127.0.0.1:{DAEMON_PORT}')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log('\n[守护进程] 正在关闭...')
        server.shutdown()
        db_close()
        try:
            os.remove(PID_FILE)
        except:
            pass
        log('[守护进程] 已退出')
        sys.exit(0)


if __name__ == '__main__':
    run_daemon()
