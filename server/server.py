import os
import sys
import json
import time
import base64
import string
from io import BytesIO
import http.server
import urllib.request
import urllib.parse
import threading
import platform
import socket
import random
import ipaddress
import sqlite3
import hashlib
import hmac
import re
import ssl
import signal
import subprocess
import secrets
import mod_scanner

# i18n support — four independent languages: zh (简体), zh-tw (繁體), en (English)
_TRANSLATIONS = {
    'zh': {
        'lang_name': '简体中文',
        'server_running': '服务运行中',
        'server_stopped': '服务未运行',
        'login_success': '登录成功',
        'login_failed': '登录失败',
        'scan_complete': '安全扫描完成',
        'high_risk_found': '发现高风险问题',
        'no_issues': '未发现问题',
        'operation_success': '操作成功',
        'operation_failed': '操作失败',
        'unauthorized': '未授权',
        'not_found': '未找到',
        'rate_limited': '请求频率过高，请稍后再试',
        'mod_manifest_invalid': 'Mod 清单文件格式无效',
        'export_complete': '导出完成',
        'notification_scan_alert': '安全扫描告警',
        'notification_login_alert': '登录安全告警',
    },
    'zh-tw': {
        'lang_name': '繁體中文',
        'server_running': '服務運行中',
        'server_stopped': '服務未運行',
        'login_success': '登入成功',
        'login_failed': '登入失敗',
        'scan_complete': '安全掃描完成',
        'high_risk_found': '發現高風險問題',
        'no_issues': '未發現問題',
        'operation_success': '操作成功',
        'operation_failed': '操作失敗',
        'unauthorized': '未授權',
        'not_found': '未找到',
        'rate_limited': '請求頻率過高，請稍後再試',
        'mod_manifest_invalid': 'Mod 清單文件格式無效',
        'export_complete': '匯出完成',
        'notification_scan_alert': '安全掃描警告',
        'notification_login_alert': '登入安全警告',
    },
    'en': {
        'lang_name': 'English',
        'server_running': 'Server is running',
        'server_stopped': 'Server is stopped',
        'login_success': 'Login successful',
        'login_failed': 'Login failed',
        'scan_complete': 'Security scan complete',
        'high_risk_found': 'High risk issues found',
        'no_issues': 'No issues found',
        'operation_success': 'Operation successful',
        'operation_failed': 'Operation failed',
        'unauthorized': 'Unauthorized',
        'not_found': 'Not found',
        'rate_limited': 'Too many requests, please try again later',
        'mod_manifest_invalid': 'Invalid mod manifest format',
        'export_complete': 'Export complete',
        'notification_scan_alert': 'Security Scan Alert',
        'notification_login_alert': 'Login Security Alert',
    },
}

_CURRENT_LANG = 'zh'

def _t(key, lang=None):
    if lang is None:
        lang = _CURRENT_LANG
    if lang not in _TRANSLATIONS:
        lang = 'zh'
    return _TRANSLATIONS[lang].get(key, key)

def _lang_from_session(session):
    if session:
        return session.get('language', '') or session.get('lang', '') or _CURRENT_LANG
    return _CURRENT_LANG

def _load_config():
    config_path = os.path.join(DATA_DIR, 'config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _load_language():
    global _CURRENT_LANG
    cfg = _load_config()
    lang = cfg.get('language', 'zh')
    if lang in _TRANSLATIONS:
        _CURRENT_LANG = lang

COOKIE_SECURE = os.environ.get('COOKIE_SECURE', '') == '1'

_LOG_CLEAN_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_LOG_CRLF_RE = re.compile(r'[\r\n]+')
MAX_PHONE_LEN = 20
MAX_PASSWORD_LEN = 128
MAX_SENDER_LEN = 100
MAX_CONTENT_LEN = 10000
MAX_EMAIL_LEN = 200

def _validate_length(value, max_len, field_name):
    if not isinstance(value, str):
        return f'{field_name}格式错误'
    if len(value) > max_len:
        return f'{field_name}过长（最多{max_len}个字符）'
    return None

import check_env
from db import get_connection, close as db_close, add_notification, get_notifications, get_unread_notification_count, mark_notification_read, mark_all_notifications_read
import mail as mail_module
from mail import send_verification_code, send_login_code, save_config as save_mail_config
from utils import *
from session_store import *
from dynamic_code import get_or_create_code, validate_code as validate_dynamic
from logger import add_log, get_logs, get_log_stats
from admin_config import generate_admin, verify_admin
from rate_limiter import check_rate_limit

DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
if not os.path.isdir(DATA_DIR):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        pass

MANAGERS_PATH = os.path.join(DATA_DIR, 'managers.json')

_MANAGERS = []  # [{username, password, password_hash, level, created_at, created_by}]
_MANAGERS_LOCK = threading.Lock()
_NEW_SMS_EVENT = threading.Event()  # set when SMS arrives, cleared when poll consumes it

DAEMON_PORT = 0
SSL_ACTIVE = False
_daemon_proc = None
_daemon_online = False
_daemon_last_check = 0

def _check_password_strength(password):
    errors = []
    if len(password) < 8:
        errors.append('密码长度至少8位')
    if not re.search(r'[A-Z]', password):
        errors.append('必须包含大写字母')
    if not re.search(r'[a-z]', password):
        errors.append('必须包含小写字母')
    if not re.search(r'[0-9]', password):
        errors.append('必须包含数字')
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]', password):
        errors.append('必须包含特殊字符')
    return errors

def _load_managers(default_creds=None):
    global _MANAGERS
    with _MANAGERS_LOCK:
        if os.path.exists(MANAGERS_PATH):
            try:
                with open(MANAGERS_PATH, 'r') as f:
                    _MANAGERS = json.load(f)
            except (json.JSONDecodeError, OSError):
                _MANAGERS = []
        if not _MANAGERS and default_creds:
            _MANAGERS = [{
                'username': default_creds['username'],
                'password_hash': default_creds['password_hash'],
                'level': 3,
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'created_by': 'system'
            }]
            _save_managers()
            print(f'  [管理用户] 初始超级管理员账户已保存到 managers.json')

def _save_managers():
    with open(MANAGERS_PATH, 'w') as f:
        json.dump(_MANAGERS, f, ensure_ascii=False, indent=2)
    os.chmod(MANAGERS_PATH, 0o600)

def _verify_manager(username, password):
    with _MANAGERS_LOCK:
        for m in _MANAGERS:
            if m['username'] == username:
                stored = m['password_hash']
                if ':' in stored:
                    salt, pwd_hash = stored.split(':', 1)
                else:
                    salt = m['username']
                    pwd_hash = stored
                computed = hashlib.pbkdf2_hmac(
                    'sha256', password.encode('utf-8'),
                    salt.encode('utf-8'), 600000
                ).hex()
                if hmac.compare_digest(computed, pwd_hash):
                    return m['level']
                return None
    return None

def _add_manager(username, password, level, created_by='cli'):
    with _MANAGERS_LOCK:
        for m in _MANAGERS:
            if m['username'] == username:
                return False, '用户名已存在'
        if not (1 <= level <= 3):
            return False, '等级必须为1-3'
        if level == 3:
            count = sum(1 for m in _MANAGERS if m['level'] == 3)
            if count >= 3:
                return False, '超级管理员数量已达上限（最多3个）'
        errors = _check_password_strength(password)
        if errors:
            return False, '; '.join(errors)
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256', password.encode('utf-8'),
            salt.encode('utf-8'), 600000
        ).hex()
        stored = salt + ':' + pwd_hash
        _MANAGERS.append({
            'username': username,
            'password_hash': stored,
            'level': level,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'created_by': created_by
        })
        _save_managers()
    return True, f'管理用户 {username} 已添加（等级{level}）'

def _rm_manager(username):
    with _MANAGERS_LOCK:
        for i, m in enumerate(_MANAGERS):
            if m['username'] == username:
                _MANAGERS.pop(i)
                _save_managers()
                return True, f'管理用户 {username} 已删除'
    return False, f'用户 {username} 不存在'

def _list_managers():
    lines = []
    lines.append(f'{"用户名":<20} {"等级":<6} {"创建时间":<20}')
    lines.append('-' * 60)
    level_names = {1: '普通管理员', 2: '中级管理员', 3: '超级管理员'}
    for m in _MANAGERS:
        lname = level_names.get(m['level'], f'等级{m["level"]}')
        lines.append(f'{m["username"]:<20} {lname:<6} {m.get("created_at","-"):<20}')
    lines.append('-' * 60)
    lines.append(f'共 {len(_MANAGERS)} 个管理用户')
    return '\n'.join(lines)

def _cli_thread():
    while _running:
        try:
            cmd = sys.stdin.readline().strip()
            if not cmd:
                time.sleep(0.1)
                continue
            parts = cmd.split()
            if not parts:
                continue
            if parts[0] == 'add':
                if len(parts) < 4:
                    print('用法: add <用户名> <密码> <等级(1-3)>')
                    continue
                ok, msg = _add_manager(parts[1], parts[2], int(parts[3]), 'cli')
                print(f'  [管理用户] {msg}')
            elif parts[0] == 'rm':
                if len(parts) < 2:
                    print('用法: rm <用户名>')
                    continue
                ok, msg = _rm_manager(parts[1])
                print(f'  [管理用户] {msg}')
            elif parts[0] == 'list':
                print(_list_managers())
            else:
                print(f'未知命令: {parts[0]} 可用命令: add, rm, list')
        except Exception as e:
            print(f'  [CLI错误] {e}')

REPORTS_PATH = os.path.join(DATA_DIR, 'reports.json')

_REPORTS = []
_REPORT_ID = 0
_REPORTS_LOCK = threading.Lock()

def _load_reports():
    global _REPORTS, _REPORT_ID
    if os.path.exists(REPORTS_PATH):
        try:
            with open(REPORTS_PATH, 'r') as f:
                _REPORTS = json.load(f)
            if _REPORTS:
                _REPORT_ID = max(r['id'] for r in _REPORTS)
        except (json.JSONDecodeError, OSError):
            _REPORTS = []

def _save_reports():
    with open(REPORTS_PATH, 'w') as f:
        json.dump(_REPORTS, f, ensure_ascii=False, indent=2)
    os.chmod(REPORTS_PATH, 0o600)

def _require_level(admin, level):
    if not admin or admin.get('role') != 'admin':
        return False
    return admin.get('admin_level', 0) >= level

def _get_online_managers():
    online = []
    admin_sessions = iter_admin_sessions()
    session_usernames = set()
    for sess in admin_sessions:
        if sess.get('admin_username'):
            session_usernames.add(sess['admin_username'])
    for m in _MANAGERS:
        active = m['username'] in session_usernames
        level_names = {1: '普通管理员', 2: '中级管理员', 3: '超级管理员'}
        online.append({
            'username': m['username'],
            'level': m['level'],
            'levelName': level_names.get(m['level'], '未知'),
            'online': active,
            'created_at': m.get('created_at', '')
        })
    return online

PUBLIC_DIR = os.path.join(os.path.dirname(__file__), '..', 'public')
MOD_DIR = os.environ.get('MOD_DIR', os.path.join(os.getcwd(), 'mod'))
PRIORITIES_PATH = os.path.join(MOD_DIR, 'priorities.json')

RECOGNIZED_LANGUAGES = {
    '.js': 'JavaScript', '.py': 'Python', '.pyc': 'Python (字节码)',
    '.html': 'HTML', '.htm': 'HTML', '.css': 'CSS',
    '.c': 'C', '.cpp': 'C++', '.cc': 'C++', '.cxx': 'C++', '.h': 'C/C++ 头文件',
    '.java': 'Java', '.go': 'Go', '.rs': 'Rust', '.rb': 'Ruby',
    '.php': 'PHP', '.swift': 'Swift', '.kt': 'Kotlin', '.kts': 'Kotlin',
    '.ts': 'TypeScript', '.lua': 'Lua', '.pl': 'Perl', '.r': 'R',
    '.sh': 'Shell', '.bat': '批处理', '.ps1': 'PowerShell',
    '.sql': 'SQL', '.json': 'JSON', '.xml': 'XML', '.yaml': 'YAML', '.yml': 'YAML',
    '.vue': 'Vue', '.svelte': 'Svelte', '.dart': 'Dart',
}

def _escape_like(s):
    return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

def _daemon_url():
    return f'http://127.0.0.1:{DAEMON_PORT}'

def _daemon_request(method, path, data=None, query=None, timeout=10):
    if not DAEMON_PORT:
        return None
    url = f'{_daemon_url()}{path}'
    if query:
        url += '?' + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, method=method)
    if data is not None:
        body = json.dumps(data).encode('utf-8')
        req.data = body
        req.add_header('Content-Type', 'application/json')
    cfg = _load_config()
    token = cfg.get('daemon_token', '')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        log(f'[守护进程] 请求失败 {method} {path}: {e}')
        return None

_DAEMON_ROUTES = {
    '/api/sms/list', '/api/sms/receive', '/api/sms/batch-import',
    '/api/sms/mark-read', '/api/sms/mark-unread', '/api/sms/delete',
    '/api/sms/auto-cleanup', '/api/sms/export', '/api/sms/unread-count',
    '/api/heartbeat', '/api/device/status',
}

def _proxy_to_daemon(req, path, data, query=None):
    global _daemon_online
    if not DAEMON_PORT:
        req._send_json({'success': False, 'message': '系统未就绪', 'daemon_offline': True}, 503)
        return
    session = data.get('_session')
    if not session or 'userId' not in session:
        req._send_json({'success': False, 'message': '未登录'})
        return
    daemon_data = {
        'userId': session['userId'],
        'ip': data.get('_ip', ''),
    }
    if data:
        for k in ('sender', 'content', 'received_at', 'messages', 'ids',
                   'wait', 'since_id', 'page', 'limit', 'search'):
            if k in data:
                daemon_data[k] = data[k]

    is_long_poll = path == '/api/sms/list' and data.get('wait') == '1'
    timeout = 30 if is_long_poll else 10

    daemon_path = path.replace('/api/', '/api/daemon/', 1)
    result = _daemon_request('POST', daemon_path, daemon_data, query, timeout)
    if result is None:
        _daemon_online = False
        req._send_json({'success': False, 'message': '系统繁忙，请稍后再试', 'daemon_offline': True}, 503)
        return
    _daemon_online = True
    req._send_json(result)

def _start_daemon(exit_on_fail=False):
    global DAEMON_PORT, _daemon_proc, _daemon_online
    daemon_path = os.path.join(os.path.dirname(__file__), 'daemon.py')
    if not os.path.isfile(daemon_path):
        log(f'[守护进程] 未找到 {daemon_path}')
        if exit_on_fail:
            os._exit(1)
        return
    try:
        env = os.environ.copy()
        env['DATA_DIR'] = DATA_DIR
        daemon_log = os.path.join(DATA_DIR, 'daemon.log')
        with open(daemon_log, 'a') as dl:
            _daemon_proc = subprocess.Popen(
                [sys.executable, daemon_path],
                env=env,
                stdout=dl,
                stderr=dl,
            )
        time.sleep(1)
        cfg = _load_config()
        DAEMON_PORT = cfg.get('daemon_port', 0)
        if not DAEMON_PORT:
            log('[守护进程] 启动失败: 无法获取端口')
            if exit_on_fail:
                os._exit(1)
            return
        for i in range(10):
            result = _daemon_request('GET', '/api/daemon/ping')
            if result and result.get('ok'):
                _daemon_online = True
                log(f'[守护进程] 已就绪 (127.0.0.1:{DAEMON_PORT})')
                return
            time.sleep(0.5)
        log('[守护进程] 启动超时')
        _daemon_online = False
        if exit_on_fail:
            os._exit(1)
    except Exception as e:
        log(f'[守护进程] 启动失败: {e}')
        _daemon_online = False
        if exit_on_fail:
            os._exit(1)

def _stop_daemon():
    global _daemon_proc
    if _daemon_proc and _daemon_proc.poll() is None:
        try:
            _daemon_proc.terminate()
            _daemon_proc.wait(timeout=5)
            log('[守护进程] 已停止')
        except Exception:
            try:
                _daemon_proc.kill()
                log('[守护进程] 已强制停止')
            except Exception:
                pass
    _daemon_proc = None

def _daemon_health_loop():
    global _daemon_online, _daemon_last_check
    was_offline = False
    consecutive_failures = 0
    while _running:
        time.sleep(5)
        result = _daemon_request('GET', '/api/daemon/ping')
        _daemon_online = result is not None and result.get('ok')
        if not _daemon_online:
            consecutive_failures += 1
            if not was_offline:
                log('[守护进程] 连接丢失')
            was_offline = True
            if consecutive_failures >= 3:
                log('[守护进程] 连续3次无响应，尝试重启...')
                _stop_daemon()
                time.sleep(1)
                _start_daemon()
                consecutive_failures = 0
        else:
            consecutive_failures = 0
            if was_offline:
                log('[守护进程] 已恢复连接')
            was_offline = False
        _daemon_last_check = time.time()

def _detect_language(path):
    _, ext = os.path.splitext(path)
    return RECOGNIZED_LANGUAGES.get(ext.lower(), '未知')

def _load_mod_priorities():
    try:
        with open(PRIORITIES_PATH, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def _save_mod_priorities(priorities):
    try:
        with open(PRIORITIES_PATH, 'w') as f:
            json.dump(priorities, f, indent=2)
    except OSError:
        pass

def _set_mod_priority(mod_rel_path, source):
    priorities = _load_mod_priorities()
    priorities[mod_rel_path] = {'source': source, 'timestamp': time.time()}
    _save_mod_priorities(priorities)

def _get_mod_priority(mod_rel_path):
    priorities = _load_mod_priorities()
    return priorities.get(mod_rel_path, {}).get('source', '')

_MOD_MANIFESTS = {}

def _load_mod_manifests():
    global _MOD_MANIFESTS
    _MOD_MANIFESTS = {}
    manifest_path = os.path.join(MOD_DIR, 'manifest.json')
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, 'r') as f:
                data = json.load(f)
            if isinstance(data, dict):
                _MOD_MANIFESTS['_global'] = data
        except (json.JSONDecodeError, OSError):
            pass
    for root, _, files in os.walk(MOD_DIR):
        if 'manifest.json' in files and root != MOD_DIR:
            fp = os.path.join(root, 'manifest.json')
            rel = os.path.relpath(root, MOD_DIR)
            try:
                with open(fp, 'r') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    _MOD_MANIFESTS[rel] = data
            except (json.JSONDecodeError, OSError):
                pass
    if _MOD_MANIFESTS:
        for k, v in _MOD_MANIFESTS.items():
            name = v.get('name', k)
            ver = v.get('version', '?')
            author = v.get('author', '?')
            desc = v.get('description', '')
            print(f'  [Mod Manifest] {name} v{ver} by {author} — {desc}')

def _validate_manifest(manifest):
    errors = []
    if not isinstance(manifest, dict):
        return ['Manifest 必须是 JSON 对象']
    if 'name' not in manifest:
        errors.append('缺少必填字段: name')
    if not isinstance(manifest.get('name', ''), str) or len(manifest['name']) > 100:
        errors.append('name 必须是字符串且不超过100字符')
    if 'version' in manifest:
        v = manifest['version']
        if not isinstance(v, str) or not v:
            errors.append('version 不能为空')
    else:
        errors.append('缺少推荐字段: version')
    allowed_keys = {'name', 'version', 'author', 'description', 'license', 'dependencies', 'minimum_core_version', 'files', 'permissions', 'icon', 'homepage'}
    extra = set(manifest.keys()) - allowed_keys
    if extra:
        errors.append(f'未知字段: {", ".join(extra)}')
    if 'dependencies' in manifest:
        deps = manifest['dependencies']
        if not isinstance(deps, dict):
            errors.append('dependencies 必须是对象')
        else:
            for dep, ver in deps.items():
                if not isinstance(dep, str) or not isinstance(ver, str):
                    errors.append(f'依赖 {dep} 格式错误')
    if 'files' in manifest:
        if not isinstance(manifest['files'], list):
            errors.append('files 必须是数组')
    if 'permissions' in manifest:
        if not isinstance(manifest['permissions'], list):
            errors.append('permissions 必须是数组')
    return errors

def _is_valid_mod_file(path):
    return os.path.isfile(path) and os.access(path, os.R_OK)

def _resolve_static_path(path, mod_first=True):
    clean = path.split('?')[0]
    if clean == '/' or clean == '':
        clean = '/index.html'
    rel = clean.lstrip('/')
    if mod_first:
        mp = os.path.normpath(os.path.join(MOD_DIR, 'public', rel))
        if mp.startswith(os.path.normpath(os.path.join(MOD_DIR, 'public'))) and _is_valid_mod_file(mp):
            mod_rel = os.path.relpath(mp, MOD_DIR)
            prio = _get_mod_priority(mod_rel)
            if prio != 'builtin':
                return mp, True
    fp = os.path.normpath(os.path.join(PUBLIC_DIR, rel))
    if fp.startswith(os.path.normpath(PUBLIC_DIR)) and _is_valid_mod_file(fp):
        return fp, False
    if mod_first and not rel.startswith('..'):
        mp = os.path.normpath(os.path.join(MOD_DIR, 'public', rel))
        if mp.startswith(os.path.normpath(os.path.join(MOD_DIR, 'public'))) and _is_valid_mod_file(mp):
            mod_rel = os.path.relpath(mp, MOD_DIR)
            prio = _get_mod_priority(mod_rel)
            if prio != 'builtin':
                return mp, True
    return None, False

START_TIME = time.time()

_admin_creds = None
USER_PORT = 0
ADMIN_PORT = 0
USER_DOMAIN = ''
ADMIN_DOMAIN = ''
IP_WHITELIST = ''
REGISTRATION_ENABLED = True
DAILY_SMS_LIMIT = 0
_running = True

STATIC_EXTENSIONS = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json',
    # Images (90%+ formats)
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.jfif': 'image/jpeg',
    '.pjpeg': 'image/jpeg',
    '.pjp': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.avif': 'image/avif',
    '.bmp': 'image/bmp',
    '.dib': 'image/bmp',
    '.tif': 'image/tiff',
    '.tiff': 'image/tiff',
    '.ico': 'image/x-icon',
    '.cur': 'image/x-icon',
    '.svg': 'image/svg+xml',
    '.svgz': 'image/svg+xml',
    '.heic': 'image/heic',
    '.heif': 'image/heif',
    # Fonts (95%+ formats)
    '.ttf': 'font/ttf',
    '.otf': 'font/otf',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.eot': 'application/vnd.ms-fontobject',
    '.sfnt': 'font/sfnt',
}

def _clean_log(val):
    if isinstance(val, str):
        val = _LOG_CLEAN_RE.sub('', val)
        val = _LOG_CRLF_RE.sub(' ', val)
        return val
    return val

def log(msg):
    t = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{t}] {_clean_log(str(msg))}')

def find_available_port():
    start = random.randint(3000, 60000)
    for offset in range(10000):
        port = start + offset
        if port > 65535:
            port = 3000 + (port - 65536)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            result = s.connect_ex(('127.0.0.1', port))
            s.close()
            if result != 0:
                return port
        except Exception:
            continue
    return 3000

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
        s.close()
        if ip and ip != '127.0.0.1':
            return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return 'localhost'

def get_public_ip():
    for url in ['https://api.ipify.org', 'https://checkip.amazonaws.com', 'https://icanhazip.com']:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                ip = resp.read().decode().strip()
                if ip:
                    return ip
        except Exception:
            continue
    return None

def get_client_ip(request):
    addr = request.client_address[0]
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        try:
            ip = ipaddress.ip_address(addr)
            if ip.is_private:
                forwarded_ip = forwarded.split(',')[0].strip()
                ipaddress.ip_address(forwarded_ip)
                addr = forwarded_ip
        except ValueError:
            pass
    return addr

class BaseHandler(http.server.BaseHTTPRequestHandler):
    server_tag = 'user'

    def log_message(self, format, *args):
        t = time.strftime('%Y-%m-%d %H:%M:%S')
        ip = self.client_address[0]
        cmd = getattr(self, 'command', '?')
        path = getattr(self, 'path', '?')
        print(f'[{t}] [请求] {ip} - {cmd} {path} - {args[0] if args else "?"}')

    def _valid_origin(self):
        origin = self.headers.get('Origin', '')
        if not origin:
            return True
        host = self.headers.get('Host', '')
        if not host:
            return False
        from urllib.parse import urlparse
        try:
            o = urlparse(origin)
            netloc = o.netloc.split(':')[0]
            if netloc == host.split(':')[0]:
                return True
            if USER_DOMAIN and netloc == USER_DOMAIN:
                return True
            if ADMIN_DOMAIN and netloc == ADMIN_DOMAIN:
                return True
            return False
        except Exception:
            return False

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _send_cors_headers(self):
        origin = self.headers.get('Origin', '')
        if origin and self._valid_origin():
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Credentials', 'true')
        else:
            host = self.headers.get('Host', '')
            if USER_DOMAIN:
                self.send_header('Access-Control-Allow-Origin', f'https://{USER_DOMAIN}')
            elif ADMIN_DOMAIN:
                self.send_header('Access-Control-Allow-Origin', f'https://{ADMIN_DOMAIN}')
            else:
                self.send_header('Access-Control-Allow-Origin', host)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Requested-With')

    def _check_csrf(self):
        if not self._valid_origin():
            self._send_error(403, '请求来源不被允许')
            return False
        if self.headers.get('X-Requested-With', '') != 'XMLHttpRequest':
            self._send_error(403, '请求被拒绝')
            return False
        return True

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status, message):
        self._send_json({'success': False, 'message': message}, status)

    def _set_session_cookie(self, session_id):
        secure = '; Secure' if COOKIE_SECURE else ''
        self.send_header(
            'Set-Cookie',
            f'session_id={session_id}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400{secure}'
        )

    def _set_admin_cookie(self, session_id):
        secure = '; Secure' if COOKIE_SECURE else ''
        self.send_header(
            'Set-Cookie',
            f'admin_session={session_id}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400{secure}'
        )

    def _get_session_id(self):
        cookie = self.headers.get('Cookie', '')
        for part in cookie.split(';'):
            part = part.strip()
            if part.startswith('session_id='):
                return part[11:]
        return None

    def _get_admin_session_id(self):
        cookie = self.headers.get('Cookie', '')
        for part in cookie.split(';'):
            part = part.strip()
            if part.startswith('admin_session='):
                return part[14:]
        return None

    def _check_csrf(self):
        if self.headers.get('X-Requested-With', '') != 'XMLHttpRequest':
            self._send_error(403, '请求被拒绝')
            return False
        return True

    def _check_ip_whitelist(self):
        if not IP_WHITELIST:
            return True
        client_ip = self.client_address[0]
        allowed = [ip.strip() for ip in IP_WHITELIST.split(',') if ip.strip()]
        if client_ip in allowed:
            return True
        self._send_error(403, 'IP 不在白名单中')
        return False

    def _parse_body(self):
        content_type = self.headers.get('Content-Type', '')
        try:
            content_length = int(self.headers.get('Content-Length', 0))
        except (ValueError, TypeError):
            content_length = 0
        if content_length == 0:
            return {}
        content_length = min(content_length, 1 << 20)  # 1MB max
        try:
            body = self.rfile.read(content_length)
        except Exception:
            return {}
        if 'application/json' in content_type:
            try:
                result = json.loads(body.decode('utf-8'))
                return result if isinstance(result, dict) else {}
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                return {}
        try:
            text = body.decode('utf-8')
        except UnicodeDecodeError:
            return {}
        parsed = urllib.parse.parse_qs(text)
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

class UserHandler(BaseHandler):
    server_tag = 'user'

    def do_GET(self):
        if not self._check_ip_whitelist():
            return
        path = self.path.split('?')[0]
        if path.startswith('/api/'):
            self._handle_api('GET')
        else:
            self._serve_static()

    def do_POST(self):
        if not self._check_ip_whitelist():
            return
        self._handle_api('POST')

    def _serve_static(self):
        file_path, from_mod = _resolve_static_path(self.path)
        if not file_path:
            self._send_error(404, '文件不存在')
            return
        ext = os.path.splitext(file_path)[1].lower()
        content_type = STATIC_EXTENSIONS.get(ext, 'application/octet-stream')
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
            self.send_header('Cache-Control', 'no-cache, max-age=0')
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self._send_error(500, '读取文件失败')

    def _handle_api(self, method):
        path = self.path.split('?')[0]
        query_params = {}
        if '?' in self.path:
            query_params = urllib.parse.parse_qs(self.path.split('?')[1])
            query_params = {k: v[0] for k, v in query_params.items()}
        session_id = self._get_session_id()
        session = get_session(session_id)

        ip = get_client_ip(self)
        if not check_rate_limit(f'api:{ip}:{path}', 100, 60):
            self._send_json({'success': False, 'message': '请求频率过高，请稍后再试'})
            return
        
        if method == 'POST':
            if not self._check_csrf():
                return
            content_type = self.headers.get('Content-Type', '')
            if not content_type.startswith('application/json'):
                self._send_error(415, '只接受JSON请求')
                return

        if path == '/api/dynamic-code':
            if method == 'POST':
                body = self._parse_body()
                phone = body.get('phone', '')
            else:
                phone = query_params.get('phone', '')
            if not phone:
                self._send_json({'success': False, 'message': '缺少手机号'})
                return
            if not session or session.get('phone') != phone:
                self._send_json({'success': False, 'message': '未登录'})
                return
            if not check_rate_limit(f'dynamic_code:{phone}', 3, 30):
                self._send_json({'success': False, 'message': '操作过于频繁'})
                return
            code = get_or_create_code(phone)
            self._send_json({'success': True, 'code': code})
            log(f'[动态码] phone={phone} code=****{code[-2:]}')
            return

        if path in _DAEMON_ROUTES:
            if method == 'POST':
                body = self._parse_body()
            else:
                body = {}
            body['_session'] = session
            body['_session_id'] = session_id
            body['_ip'] = ip
            body['wait'] = query_params.get('wait', '')
            body['since_id'] = int(query_params.get('since_id', 0) or 0)
            body['page'] = int(query_params.get('page', 1) or 1)
            body['limit'] = int(query_params.get('limit', 50) or 50)
            body['search'] = query_params.get('search', '')
            _proxy_to_daemon(self, path, body, query_params)
            return

        if method == 'POST':
            data = self._parse_body()
        else:
            data = {}

        data['_session'] = session
        data['_session_id'] = session_id
        data['_ip'] = ip

        handler = USER_ROUTES.get((method, path))
        if handler:
            try:
                handler(self, data)
                log(f'[API] {method} {path} -> 200 (from {data.get("_ip","?")})')
            except Exception as e:
                log(f'[错误] {method} {path}: {e}')
                self._send_error(500, '服务器内部错误')
        else:
            self._send_error(404, '接口不存在')

    def _handle_sms_list(self, session, query):
        if not session or 'userId' not in session:
            self._send_json({'success': False, 'message': '未登录'})
            return
        db = get_connection()
        user = db.execute('SELECT id FROM users WHERE id = ? AND is_active = 1', (session['userId'],)).fetchone()
        if not user:
            self._send_json({'success': False, 'message': '用户已注销'})
            return
        user_id = user['id']
        try:
            page = max(1, min(10000, int(query.get('page', 1))))
            limit = max(1, min(500, int(query.get('limit', 50))))
            since_id = int(query.get('since_id', 0))
        except ValueError:
            self._send_json({'success': False, 'message': '参数格式错误'})
            return
        search = query.get('search', '').strip()
        wait = query.get('wait', '') == '1'
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

    def _handle_sms_export(self, session):
        if not session or 'userId' not in session:
            self._send_json({'success': False, 'message': '未登录'})
            return
        db = get_connection()
        user = db.execute('SELECT id, phone FROM users WHERE id = ? AND is_active = 1', (session['userId'],)).fetchone()
        if not user:
            self._send_json({'success': False, 'message': '用户已注销'})
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
        body = json.dumps(export_data, ensure_ascii=False, indent=2)
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Disposition', f'attachment; filename="sms_export_{user["phone"]}_{int(time.time())}.json"')
        self.send_header('Content-Length', str(len(body.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))

    def _handle_sms_unread(self, session):
        if not session or 'userId' not in session:
            self._send_json({'success': False, 'message': '未登录'})
            return
        db = get_connection()
        user = db.execute('SELECT id FROM users WHERE id = ? AND is_active = 1', (session['userId'],)).fetchone()
        if not user:
            self._send_json({'success': False, 'message': '用户已注销'})
            return
        count = db.execute(
            'SELECT COUNT(*) as c FROM sms_messages WHERE user_id = ? AND is_read = 0',
            (user['id'],)
        ).fetchone()['c']
        self._send_json({'success': True, 'unread': count})

    def _handle_sms_receive(self, data):
        session = data.get('_session')
        if not session or 'userId' not in session:
            self._send_json({'success': False, 'message': '未登录'})
            return
        sender = data.get('sender', '')
        content = data.get('content', '')
        received_at = time.strftime('%Y-%m-%d %H:%M:%S')
        if not sender or not content:
            self._send_json({'success': False, 'message': '缺少发件人或短信内容'})
            return
        err = _validate_length(sender, MAX_SENDER_LEN, '发件人') or _validate_length(content, MAX_CONTENT_LEN, '短信内容')
        if err:
            self._send_json({'success': False, 'message': err})
            return
        db = get_connection()
        user = db.execute('SELECT phone FROM users WHERE id = ? AND is_active = 1', (session['userId'],)).fetchone()
        if not user:
            self._send_json({'success': False, 'message': '用户不存在'})
            return
        if DAILY_SMS_LIMIT > 0:
            today = time.strftime('%Y-%m-%d')
            count = db.execute(
                'SELECT COUNT(*) as cnt FROM sms_messages WHERE user_id = ? AND received_at >= ?',
                (session['userId'], today)
            ).fetchone()['cnt']
            if count >= DAILY_SMS_LIMIT:
                self._send_json({'success': False, 'message': f'今日短信已达上限({DAILY_SMS_LIMIT}条)'})
                return
        db.execute(
            'INSERT INTO sms_messages (user_id, user_phone, sender, content, received_at) VALUES (?, ?, ?, ?, ?)',
            (session['userId'], user['phone'], sender, content, received_at)
        )
        db.execute(
            'UPDATE users SET last_active_at = datetime(\'now\',\'localtime\') WHERE id = ?',
            (session['userId'],)
        )
        db.commit()
        msg_id = db.execute('SELECT last_insert_rowid() as id').fetchone()['id']
        add_log('短信接收', user['phone'], f'来自{sender}: {content[:50]}', data.get('_ip', ''))
        log(f'[短信] 用户{user["phone"]} 收到来自{sender}的短信')
        _NEW_SMS_EVENT.set()
        self._send_json({'success': True, 'message': '已接收', 'id': msg_id})

    def _handle_sms_batch_import(self, data):
        session = data.get('_session')
        if not session or 'userId' not in session:
            self._send_json({'success': False, 'message': '未登录'})
            return
        messages = data.get('messages', [])
        if not isinstance(messages, list) or not messages:
            self._send_json({'success': False, 'message': '短信列表格式错误'})
            return
        db = get_connection()
        user = db.execute('SELECT phone FROM users WHERE id = ? AND is_active = 1', (session['userId'],)).fetchone()
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
                (session['userId'], sender, content, received_at)
            ).fetchone()
            if existing:
                continue
            db.execute(
                'INSERT INTO sms_messages (user_id, user_phone, sender, content, received_at, is_read) VALUES (?, ?, ?, ?, ?, 1)',
                (session['userId'], user['phone'], sender, content, received_at)
            )
            imported += 1
        if imported > 0:
            db.commit()
            log(f'[短信] 用户{user["phone"]} 批量导入 {imported} 条历史短信')
            _NEW_SMS_EVENT.set()
        self._send_json({'success': True, 'imported': imported})

    def _handle_sms_mark_read(self, data):
        session = data.get('_session')
        if not session or 'userId' not in session:
            self._send_json({'success': False, 'message': '未登录'})
            return
        db = get_connection()
        user = db.execute('SELECT id FROM users WHERE id = ? AND is_active = 1', (session['userId'],)).fetchone()
        if not user:
            self._send_json({'success': False, 'message': '用户已注销'})
            return
        ids = data.get('ids', [])
        if not isinstance(ids, list):
            self._send_json({'success': False, 'message': '无效的请求参数'})
            return
        if not ids:
            self._send_json({'success': False, 'message': '请选择要标记的短信'})
            return
        try:
            ids = [int(x) for x in ids]
        except (ValueError, TypeError):
            self._send_json({'success': False, 'message': '包含无效的ID'})
            return
        if len(ids) > 500:
            self._send_json({'success': False, 'message': '一次最多标记500条'})
            return
        placeholders = ','.join('?' for _ in ids)
        db.execute(
            f'UPDATE sms_messages SET is_read = 1 WHERE user_id = ? AND id IN ({placeholders})',
            [user['id']] + ids
        )
        db.commit()
        self._send_json({'success': True, 'message': f'已标记{len(ids)}条为已读'})

    def _handle_sms_mark_unread(self, data):
        session = data.get('_session')
        if not session or 'userId' not in session:
            self._send_json({'success': False, 'message': '未登录'})
            return
        db = get_connection()
        user = db.execute('SELECT id FROM users WHERE id = ? AND is_active = 1', (session['userId'],)).fetchone()
        if not user:
            self._send_json({'success': False, 'message': '用户已注销'})
            return
        ids = data.get('ids', [])
        if not isinstance(ids, list):
            self._send_json({'success': False, 'message': '无效的请求参数'})
            return
        if not ids:
            self._send_json({'success': False, 'message': '请选择要标记的短信'})
            return
        try:
            ids = [int(x) for x in ids]
        except (ValueError, TypeError):
            self._send_json({'success': False, 'message': '包含无效的ID'})
            return
        if len(ids) > 500:
            self._send_json({'success': False, 'message': '一次最多标记500条'})
            return
        placeholders = ','.join('?' for _ in ids)
        db.execute(
            f'UPDATE sms_messages SET is_read = 0 WHERE user_id = ? AND id IN ({placeholders})',
            [user['id']] + ids
        )
        db.commit()
        self._send_json({'success': True, 'message': f'已标记{len(ids)}条为未读'})

    def _handle_sms_delete(self, data):
        session = data.get('_session')
        if not session or 'userId' not in session:
            self._send_json({'success': False, 'message': '未登录'})
            return
        db = get_connection()
        user = db.execute('SELECT id FROM users WHERE id = ? AND is_active = 1', (session['userId'],)).fetchone()
        if not user:
            self._send_json({'success': False, 'message': '用户已注销'})
            return
        ids = data.get('ids', [])
        if not isinstance(ids, list):
            self._send_json({'success': False, 'message': '无效的请求参数'})
            return
        if not ids:
            self._send_json({'success': False, 'message': '请选择要删除的短信'})
            return
        try:
            ids = [int(x) for x in ids]
        except (ValueError, TypeError):
            self._send_json({'success': False, 'message': '包含无效的ID'})
            return
        if len(ids) > 500:
            self._send_json({'success': False, 'message': '一次最多删除500条'})
            return
        placeholders = ','.join('?' for _ in ids)
        db.execute(
            f'DELETE FROM sms_messages WHERE user_id = ? AND id IN ({placeholders})',
            [user['id']] + ids
        )
        db.commit()
        self._send_json({'success': True, 'message': f'已删除{len(ids)}条短信'})

class AdminHandler(BaseHandler):
    server_tag = 'admin'

    def do_GET(self):
        self._handle_admin_api()

    def do_POST(self):
        self._handle_admin_api()

    def _check_security_path(self, path):
        cfg = _load_config()
        sec = cfg.get('security_path', '')
        if not sec:
            return True, path
        if path.startswith(sec):
            inner = path[len(sec):]
            if not inner.startswith('/'):
                inner = '/' + inner
            return True, inner
        self._send_error(404, '安全入口已更新，请联系超级管理员获取新地址')
        return False, path

    def _handle_admin_api(self):
        raw_path = self.path.split('?')[0]
        ok, path = self._check_security_path(raw_path)
        if not ok:
            return
        if not self._check_ip_whitelist():
            return
        method = self.command
        if method == 'POST':
            if not self._check_csrf():
                return
            data = self._parse_body()
        else:
            data = {}
        admin_session_id = self._get_admin_session_id()
        admin_session = get_session(admin_session_id)
        data['_admin_session'] = admin_session
        data['_admin_session_id'] = admin_session_id
        ip = get_client_ip(self)
        data['_ip'] = ip
        if path.startswith('/api/admin/') and not check_rate_limit(f'admin:{ip}:{path}', 60, 60):
            self._send_json({'success': False, 'message': _t('rate_limited')})
            return

        if path.startswith('/api/admin/'):
            handler = ADMIN_ROUTES.get((method, path))
            if handler:
                try:
                    handler(self, data)
                    log(f'[管理API] {method} {path} -> 200 (from {data.get("_ip","?")})')
                except Exception as e:
                    log(f'[管理错误] {method} {path}: {e}')
                    self._send_error(500, '服务器内部错误')
            else:
                self._send_error(404, '接口不存在')
            return

        orig = self.path
        self.path = path
        self._serve_admin_static()
        self.path = orig
        return

    def _serve_admin_static(self):
        file_path, from_mod = _resolve_static_path(self.path)
        if not file_path:
            self._send_error(404, '文件不存在')
            return
        ext = os.path.splitext(file_path)[1].lower()
        content_type = STATIC_EXTENSIONS.get(ext, 'application/octet-stream')
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
            self.send_header('Cache-Control', 'no-cache, max-age=0')
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self._send_error(500, '读取文件失败')

USER_ROUTES = {}
ADMIN_ROUTES = {}

def api_route(method, path):
    def wrapper(func):
        USER_ROUTES[(method, path)] = func
        return func
    return wrapper

def admin_api_route(method, path):
    def wrapper(func):
        ADMIN_ROUTES[(method, path)] = func
        return func
    return wrapper

@api_route('GET', '/api/theme')
def handle_theme(req, data):
    cfg = _load_config()
    req._send_json({
        'success': True,
        'bg': cfg.get('theme_bg', ''),
        'font': cfg.get('theme_font', ''),
        'fontUrl': cfg.get('theme_font_url', ''),
        'color': cfg.get('theme_color', ''),
        'radius': cfg.get('theme_radius', ''),
        'shadow': cfg.get('theme_shadow', ''),
        'dark': cfg.get('theme_dark', ''),
        'fontSize': cfg.get('theme_font_size', ''),
        'gradient': cfg.get('theme_gradient', ''),
        'blur': cfg.get('theme_blur', ''),
        'animation': cfg.get('theme_animation', ''),
        'density': cfg.get('theme_density', ''),
        'preset': cfg.get('theme_preset', ''),
    })

@api_route('POST', '/api/sms/receive')
def handle_sms_receive_route(req, data):
    req._handle_sms_receive(data)

@api_route('POST', '/api/sms/batch-import')
def handle_sms_batch_import_route(req, data):
    req._handle_sms_batch_import(data)

@api_route('POST', '/api/sms/mark-read')
def handle_sms_mark_read_route(req, data):
    req._handle_sms_mark_read(data)

@api_route('POST', '/api/sms/mark-unread')
def handle_sms_mark_unread_route(req, data):
    req._handle_sms_mark_unread(data)

@api_route('POST', '/api/sms/delete')
def handle_sms_delete_route(req, data):
    req._handle_sms_delete(data)

@api_route('POST', '/api/sms/auto-cleanup')
def handle_sms_auto_cleanup(req, data):
    session = data.get('_session')
    if not session or 'userId' not in session:
        req._send_json({'success': False, 'message': '未登录'})
        return
    db = get_connection()
    user = db.execute('SELECT id, phone, exported_at FROM users WHERE id = ? AND is_active = 1', (session['userId'],)).fetchone()
    if not user:
        req._send_json({'success': False, 'message': '用户已注销'})
        return
    user_id = user['id']
    count = db.execute('SELECT COUNT(*) as c FROM sms_messages WHERE user_id = ?', (user_id,)).fetchone()['c']
    if count == 0:
        req._send_json({'success': True, 'message': '没有需要清除的短信', 'deleted': 0})
        return
    has_exported = user['exported_at'] is not None
    if has_exported:
        db.execute('DELETE FROM sms_messages WHERE user_id = ?', (user_id,))
        db.commit()
        add_log('短信自动清除', user['phone'], f'自动清除所有短信（共{count}条）', data.get('_ip', ''))
        req._send_json({'success': True, 'message': f'已清除{count}条短信', 'deleted': count})
    else:
        req._send_json({'success': True, 'message': '您从未导出过短信，数据已保留但请注意隐私安全', 'deleted': 0, 'never_exported': True})

@api_route('POST', '/api/heartbeat')
def handle_heartbeat(req, data):
    session = data.get('_session')
    if not session or 'userId' not in session:
        req._send_json({'success': False, 'message': '未登录'})
        return
    db = get_connection()
    db.execute(
        'UPDATE users SET last_active_at = datetime(\'now\',\'localtime\') WHERE id = ?',
        (session['userId'],)
    )
    db.commit()
    req._send_json({'success': True, 'message': 'ok'})

@api_route('GET', '/api/device/status')
def handle_device_status(req, data):
    session = data.get('_session')
    if not session or 'userId' not in session:
        req._send_json({'success': False, 'message': '未登录'})
        return
    db = get_connection()
    row = db.execute(
        'SELECT last_active_at FROM users WHERE id = ?',
        (session['userId'],)
    ).fetchone()
    if not row:
        req._send_json({'success': False, 'message': '用户不存在'})
        return
    last_active = row['last_active_at']
    online = False
    if last_active:
        try:
            active_ts = time.mktime(time.strptime(last_active, '%Y-%m-%d %H:%M:%S'))
            online = (time.time() - active_ts) < 60
        except Exception:
            pass
    req._send_json({
        'success': True,
        'online': online,
        'last_active_at': last_active
    })

@api_route('GET', '/api/panel/daemon-status')
def handle_panel_daemon_status(req, data):
    daemon_info = {}
    info_path = os.path.join(DATA_DIR, 'daemon.json')
    if os.path.exists(info_path):
        try:
            with open(info_path, 'r') as f:
                daemon_info = json.load(f)
        except Exception:
            pass
    req._send_json({
        'success': True,
        'daemon_online': _daemon_online,
        'daemon_port': DAEMON_PORT,
        'daemon_last_check': _daemon_last_check,
        'daemon_info': daemon_info,
    })

@api_route('POST', '/api/auth/register/send-code')
def handle_register_send_code(req, data):
    if not REGISTRATION_ENABLED:
        req._send_json({'success': False, 'message': '注册功能已关闭'})
        return
    phone = data.get('phone', '')
    email = data.get('email', '')
    ip = data.get('_ip', '')

    if not phone or not email:
        add_log('注册发码', phone, '手机号或邮箱为空', ip, 'fail')
        req._send_json({'success': False, 'message': '手机号和邮箱不能为空'})
        return
    err = _validate_length(phone, MAX_PHONE_LEN, '手机号') or _validate_length(email, MAX_EMAIL_LEN, '邮箱')
    if err:
        req._send_json({'success': False, 'message': err})
        return
    if not is_valid_phone(phone):
        add_log('注册发码', phone, '手机号格式不正确', ip, 'fail')
        req._send_json({'success': False, 'message': '手机号格式不正确'})
        return
    if not is_valid_email(email):
        add_log('注册发码', phone, '邮箱格式不正确', ip, 'fail')
        req._send_json({'success': False, 'message': '邮箱格式不正确'})
        return

    if not check_rate_limit(f'reg_send_code_short:{phone}', 1, 3):
        add_log('注册发码', phone, '发送频率过高', ip, 'fail')
        req._send_json({'success': False, 'message': '操作过于频繁，请3秒后再试'})
        return

    db = get_connection()
    existing = db.execute('SELECT id FROM users WHERE phone = ? AND is_active = 1', (phone,)).fetchone()
    if existing:
        add_log('注册发码', phone, '用户已存在，拒绝重复注册', ip, 'fail')
        req._send_json({'success': False, 'message': '该手机号已注册'})
        return

    code = generate_code(6)
    unique_key = generate_key()
    expires_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + 60))

    db.execute('DELETE FROM reg_codes WHERE expires_at < datetime(\'now\',\'localtime\')')
    db.execute('DELETE FROM reg_codes WHERE phone = ?', (phone,))
    db.execute('INSERT INTO reg_codes (phone, email, code, unique_key, expires_at) VALUES (?, ?, ?, ?, ?)',
               (phone, email, code, unique_key, expires_at))
    db.commit()

    lan_ip = get_lan_ip()
    public_ip = get_public_ip()
    proto = 'https' if SSL_ACTIVE else 'http'
    if USER_DOMAIN:
        verify_url = f'{proto}://{USER_DOMAIN}/verify.html?key={unique_key}'
    else:
        verify_url = f'{proto}://{lan_ip}:{USER_PORT}/verify.html?key={unique_key}'
        if public_ip:
            verify_url = f'{proto}://{public_ip}:{USER_PORT}/verify.html?key={unique_key}'
    add_log('注册发码', phone, f'验证链接: {verify_url}', ip)
    result = send_verification_code(email, code, verify_url)

    if result.get('success'):
        # 发送成功后锁定60秒防滥用（使用独立key，不与3秒防连点冲突）
        check_rate_limit(f'reg_send_code_long:{phone}', 1, 60)
        add_log('注册发码', phone, f'验证码已发送至 {email}', ip)
        req._send_json({'success': True, 'message': '验证码已发送', 'key': unique_key})
    else:
        # 发送失败不锁，允许立即重试（仅防连点）
        add_log('注册发码', phone, f'邮件发送失败: {result.get("error")}', ip, 'fail')
        req._send_json({'success': False, 'message': '发送失败，请检查SMTP配置后重试'})

@api_route('POST', '/api/auth/register/verify-code')
def handle_register_verify(req, data):
    key = data.get('key', '')
    phone = data.get('phone', '')
    code = data.get('code', '')
    ip = data.get('_ip', '')

    if not key or not phone or not code:
        add_log('注册验证', phone, '参数不完整', ip, 'fail')
        req._send_json({'success': False, 'message': '参数不完整'})
        return
    if not is_valid_phone(phone):
        add_log('注册验证', phone, '手机号格式不正确', ip, 'fail')
        req._send_json({'success': False, 'message': '手机号格式不正确'})
        return
    if not check_rate_limit(f'register_verify:{phone}', 5, 60):
        add_log('注册验证', phone, '验证频率过高', ip, 'fail')
        req._send_json({'success': False, 'message': '操作过于频繁，请稍后再试'})
        return

    db = get_connection()
    record = db.execute(
        'SELECT * FROM reg_codes WHERE unique_key = ? AND phone = ? AND is_used = 0',
        (key, phone)
    ).fetchone()

    if not record:
        add_log('注册验证', phone, '验证链接无效或已被使用', ip, 'fail')
        req._send_json({'success': False, 'message': '验证链接无效或已被使用'})
        return
    if record['expires_at'] < time.strftime('%Y-%m-%d %H:%M:%S'):
        add_log('注册验证', phone, '验证码已过期', ip, 'fail')
        req._send_json({'success': False, 'message': '验证码已过期，请重新注册'})
        return
    if record['code'] != code:
        add_log('注册验证', phone, '验证码输入错误', ip, 'fail')
        req._send_json({'success': False, 'message': '验证码错误'})
        return

    email = record['email']
    db.execute('UPDATE reg_codes SET is_used = 1 WHERE id = ?', (record['id'],))
    db.commit()
    temp_token = generate_key()
    create_session({'phone': phone, 'email': email, 'verified': True, 'expires': time.time() + 1800}, session_id=temp_token)

    add_log('注册验证', phone, '验证码验证通过', ip)
    req._send_json({'success': True, 'message': '验证码正确', 'tempToken': temp_token, 'phone': phone})

@api_route('POST', '/api/auth/register/set-password')
def handle_set_password(req, data):
    phone = data.get('phone', '')
    password = data.get('password', '')
    temp_token = data.get('tempToken', '')
    ip = data.get('_ip', '')

    if not phone or not password:
        add_log('注册设密', phone, '参数不完整', ip, 'fail')
        req._send_json({'success': False, 'message': '参数不完整'})
        return
    err = _validate_length(password, MAX_PASSWORD_LEN, '密码')
    if err:
        req._send_json({'success': False, 'message': err})
        return
    if not is_valid_phone(phone):
        add_log('注册设密', phone, '手机号格式不正确', ip, 'fail')
        req._send_json({'success': False, 'message': '手机号格式不正确'})
        return
    if not is_valid_password(password):
        add_log('注册设密', phone, '密码不符合规则', ip, 'fail')
        req._send_json({'success': False, 'message': get_password_error()})
        return
    if not temp_token:
        add_log('注册设密', phone, '缺少临时令牌', ip, 'fail')
        req._send_json({'success': False, 'message': '请先完成邮箱验证'})
        return

    verify_session = get_session(temp_token)
    if not verify_session:
        add_log('注册设密', phone, f'临时令牌无效（session不存在）', ip, 'fail')
        req._send_json({'success': False, 'message': '验证已过期，请重新注册'})
        return
    if verify_session.get('phone') != phone:
        add_log('注册设密', phone, f'临时令牌手机号不匹配', ip, 'fail')
        req._send_json({'success': False, 'message': '验证已过期，请重新注册'})
        return
    if not verify_session.get('verified'):
        add_log('注册设密', phone, '临时令牌未通过验证', ip, 'fail')
        req._send_json({'success': False, 'message': '验证已过期，请重新注册'})
        return

    db = get_connection()
    existing = db.execute('SELECT id FROM users WHERE phone = ? AND is_active = 1', (phone,)).fetchone()
    if existing:
        add_log('注册设密', phone, '用户已存在', ip, 'fail')
        req._send_json({'success': False, 'message': '该手机号已注册'})
        return

    email = verify_session.get('email', '') or ''
    password_hash = hash_password(password)

    try:
        db.execute('INSERT INTO users (phone, email, password_hash) VALUES (?, ?, ?)',
                   (phone, email, password_hash))
        db.commit()
    except sqlite3.IntegrityError:
        add_log('注册设密', phone, '用户已被并发注册', ip, 'fail')
        req._send_json({'success': False, 'message': '该手机号已注册'})
        return

    user = db.execute('SELECT id, phone FROM users WHERE phone = ?', (phone,)).fetchone()
    new_session = create_session({'userId': user['id'], 'phone': user['phone']})

    add_log('注册设密', phone, '账号注册成功（密码已加密存储）', ip)
    req.send_response(200)
    req._send_cors_headers()
    req.send_header('Content-Type', 'application/json; charset=utf-8')
    req._set_session_cookie(new_session)
    req.send_header('Cache-Control', 'no-store')
    req.end_headers()
    req.wfile.write(json.dumps({'success': True, 'message': '注册成功'}, ensure_ascii=False).encode('utf-8'))

@api_route('GET', '/api/mod/status')
def handle_mod_status(req, data):
    session = data.get('_session')
    admin = data.get('_admin_session')
    if not session and not admin:
        req._send_json({'success': True, 'enabled': True, 'mod_dir': MOD_DIR, 'file_count': 0, 'files': []})
        return
    files = []
    for root, _, names in os.walk(MOD_DIR):
        for f in names:
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, MOD_DIR)
            lang = _detect_language(f)
            files.append({'path': rel, 'language': lang, 'size': os.path.getsize(fp)})
    req._send_json({'success': True, 'enabled': True, 'mod_dir': MOD_DIR, 'file_count': len(files), 'files': files})

@api_route('POST', '/api/auth/login')
def handle_login(req, data):
    phone = data.get('phone', '')
    password = data.get('password', '')
    dynamic_code = data.get('dynamicCode', '')
    ip = data.get('_ip', '')

    if not check_rate_limit(f'login:{ip}', 10, 60):
        add_log('登录', phone, '登录频率过高', ip, 'fail')
        req._send_json({'success': False, 'message': '操作过于频繁，请稍后再试'})
        return
    err = _validate_length(phone, MAX_PHONE_LEN, '手机号') or _validate_length(password, MAX_PASSWORD_LEN, '密码')
    if err:
        req._send_json({'success': False, 'message': err})
        return
    if not phone or not password:
        add_log('登录', phone, '手机号或密码为空', ip, 'fail')
        req._send_json({'success': False, 'message': '手机号和密码不能为空'})
        return

    db = get_connection()
    user = db.execute('SELECT * FROM users WHERE phone = ? AND is_active = 1', (phone,)).fetchone()

    if not user:
        add_log('登录', phone, '查无此人', ip, 'fail')
        req._send_json({'success': False, 'message': '查无此人'})
        return

    fail_count = user['login_fail_count'] or 0
    if fail_count >= 10:
        last_login = user.get('last_login_at')
        if last_login:
            try:
                last_time = time.mktime(time.strptime(last_login, '%Y-%m-%d %H:%M:%S'))
                if time.time() - last_time > 1800:
                    db.execute('UPDATE users SET login_fail_count = 0 WHERE id = ?', (user['id'],))
                    db.commit()
                    fail_count = 0
            except Exception:
                pass
        if fail_count >= 10:
            add_log('登录', phone, '账号已被锁定（登录失败超过10次）', ip, 'fail')
            add_notification('login_alert', _t('notification_login_alert'),
                f'用户 {phone} 因登录失败超过10次已被锁定',
                'warning', user['id'])
            req._send_json({'success': False, 'message': '账号已被锁定，请30分钟后再试或通过邮箱验证码登录'})
            return

    password_correct = check_password(password, user['password_hash'])

    if password_correct and not dynamic_code:
        new_session = create_session({'userId': user['id'], 'phone': user['phone']})
        db.execute('UPDATE users SET last_login_at = datetime(\'now\',\'localtime\'), login_fail_count = 0 WHERE id = ?', (user['id'],))
        db.commit()
        add_log('登录', phone, '密码正确，登录成功', ip)
        req.send_response(200)
        req._send_cors_headers()
        req.send_header('Content-Type', 'application/json; charset=utf-8')
        req._set_session_cookie(new_session)
        req.send_header('Cache-Control', 'no-store')
        req.end_headers()
        req.wfile.write(json.dumps({'success': True, 'message': '登录成功'}, ensure_ascii=False).encode('utf-8'))
        return

    if not password_correct and not dynamic_code:
        new_fail = fail_count + 1
        db.execute('UPDATE users SET login_fail_count = ? WHERE id = ?', (new_fail, user['id'],))
        db.commit()
        add_log('登录', phone, f'密码错误（第{new_fail}次失败）', ip, 'fail')
        if new_fail >= 6:
            code = generate_code(6)
            expires_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + 120))
            db.execute("DELETE FROM login_codes WHERE phone = ?", (phone,))
            db.execute('INSERT INTO login_codes (phone, email, code, expires_at) VALUES (?, ?, ?, ?)',
                       (phone, user['email'], code, expires_at))
            db.commit()
            mail_ok = send_login_code(user['email'], code)
            if mail_ok and mail_ok.get('success'):
                req._send_json({'success': False, 'message': '密码错误次数过多，已向您的邮箱发送验证码', 'needEmailCode': True, 'showChangePwdTip': True})
            else:
                req._send_json({'success': False, 'message': '密码错误次数过多，但邮件发送失败，请稍后重试', 'needEmailCode': True, 'showChangePwdTip': True})
        elif new_fail >= 3:
            req._send_json({'success': False, 'message': '密码错误已达3次，请输入动态验证码', 'needDynamicCode': True, 'failCount': new_fail})
        else:
            req._send_json({'success': False, 'message': f'密码错误（第{new_fail}次）', 'failCount': new_fail})
        return

    if dynamic_code:
        is_valid = validate_dynamic(phone, dynamic_code)
        if not is_valid or not password_correct:
            new_fail = fail_count + 1
            db.execute('UPDATE users SET login_fail_count = ? WHERE id = ?', (new_fail, user['id'],))
            db.commit()
            add_log('登录', phone, '动态验证码或密码错误', ip, 'fail')
            if new_fail >= 6:
                code = generate_code(6)
                expires_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + 120))
                db.execute("DELETE FROM login_codes WHERE phone = ?", (phone,))
                db.execute('INSERT INTO login_codes (phone, email, code, expires_at) VALUES (?, ?, ?, ?)',
                           (phone, user['email'], code, expires_at))
                db.commit()
                mail_ok = send_login_code(user['email'], code)
                if mail_ok and mail_ok.get('success'):
                    req._send_json({'success': False, 'message': '验证失败次数过多，已向您的邮箱发送验证码', 'needEmailCode': True, 'showChangePwdTip': True})
                else:
                    req._send_json({'success': False, 'message': '验证失败次数过多，但邮件发送失败，请稍后重试', 'needEmailCode': True, 'showChangePwdTip': True})
            else:
                message = '动态验证码或密码错误'
                if not is_valid:
                    message = '动态验证码错误'
                else:
                    message = '密码错误'
                req._send_json({'success': False, 'message': message})
            return
        new_session = create_session({'userId': user['id'], 'phone': user['phone']})
        db.execute('UPDATE users SET last_login_at = datetime(\'now\',\'localtime\'), login_fail_count = 0 WHERE id = ?', (user['id'],))
        db.commit()
        add_log('登录', phone, '动态验证码+密码正确，登录成功', ip)
        req.send_response(200)
        req._send_cors_headers()
        req.send_header('Content-Type', 'application/json; charset=utf-8')
        req._set_session_cookie(new_session)
        req.send_header('Cache-Control', 'no-store')
        req.end_headers()
        req.wfile.write(json.dumps({'success': True, 'message': '登录成功'}, ensure_ascii=False).encode('utf-8'))
        return

    req._send_json({'success': False, 'message': '登录失败'})

@api_route('POST', '/api/auth/login/send-email-code')
def handle_send_email_code(req, data):
    phone = data.get('phone', '')
    ip = data.get('_ip', '')
    if not phone or not is_valid_phone(phone):
        add_log('发送邮箱验证码', phone, '手机号格式不正确', ip, 'fail')
        req._send_json({'success': False, 'message': '手机号格式不正确'})
        return

    if not check_rate_limit(f'email_code_short:{phone}', 1, 3):
        add_log('发送邮箱验证码', phone, '发送频率过高', ip, 'fail')
        req._send_json({'success': False, 'message': '操作过于频繁，请3秒后再试'})
        return

    db = get_connection()
    user = db.execute('SELECT * FROM users WHERE phone = ? AND is_active = 1', (phone,)).fetchone()
    if not user:
        add_log('发送邮箱验证码', phone, '手机号未注册', ip, 'fail')
        req._send_json({'success': True, 'message': '如果该手机号已注册，验证码已发送至绑定的邮箱'})
        return
    code = generate_code(6)
    expires_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + 60))
    db.execute("DELETE FROM login_codes WHERE expires_at < datetime('now','localtime')")
    db.execute('DELETE FROM login_codes WHERE phone = ?', (phone,))
    db.execute('INSERT INTO login_codes (phone, email, code, expires_at) VALUES (?, ?, ?, ?)',
               (phone, user['email'], code, expires_at))
    db.commit()
    result = send_login_code(user['email'], code)
    if result.get('success'):
        check_rate_limit(f'email_code_long:{phone}', 1, 60)
        add_log('发送邮箱验证码', phone, f'已发送至 {user["email"]}', ip)
        req._send_json({'success': True, 'message': '验证码已发送'})
    else:
        add_log('发送邮箱验证码', phone, f'发送失败: {result.get("error")}', ip, 'fail')
        req._send_json({'success': False, 'message': '发送失败，请检查SMTP配置后重试'})

@api_route('POST', '/api/auth/login/verify-email-code')
def handle_verify_email_code(req, data):
    phone = data.get('phone', '')
    email_code = data.get('emailCode', '')
    ip = data.get('_ip', '')
    if not phone or not email_code:
        add_log('验证邮箱码登录', phone, '参数不完整', ip, 'fail')
        req._send_json({'success': False, 'message': '参数不完整'})
        return
    if not check_rate_limit(f'verify_email_code:{phone}', 5, 60):
        add_log('验证邮箱码登录', phone, '验证频率过高', ip, 'fail')
        req._send_json({'success': False, 'message': '操作过于频繁，请稍后再试'})
        return
    db = get_connection()
    record = db.execute(
        'SELECT * FROM login_codes WHERE phone = ? AND code = ? AND is_used = 0',
        (phone, email_code)
    ).fetchone()
    if not record:
        add_log('验证邮箱码登录', phone, '验证码错误', ip, 'fail')
        req._send_json({'success': False, 'message': '验证码错误'})
        return
    if record['expires_at'] < time.strftime('%Y-%m-%d %H:%M:%S'):
        add_log('验证邮箱码登录', phone, '验证码已过期', ip, 'fail')
        req._send_json({'success': False, 'message': '验证码已过期'})
        return
    db.execute('UPDATE login_codes SET is_used = 1 WHERE id = ?', (record['id'],))
    db.commit()
    user = db.execute('SELECT * FROM users WHERE phone = ? AND is_active = 1', (phone,)).fetchone()
    if not user:
        req._send_json({'success': False, 'message': '用户不存在'})
        return
    new_session = create_session({'userId': user['id'], 'phone': user['phone']})
    db.execute('UPDATE users SET last_login_at = datetime(\'now\',\'localtime\'), login_fail_count = 0 WHERE id = ?', (user['id'],))
    db.commit()
    add_log('验证邮箱码登录', phone, '邮箱验证码正确，登录成功', ip)
    req.send_response(200)
    req._send_cors_headers()
    req.send_header('Content-Type', 'application/json; charset=utf-8')
    req._set_session_cookie(new_session)
    req.send_header('Cache-Control', 'no-store')
    req.end_headers()
    req.wfile.write(json.dumps({'success': True, 'message': '登录成功', 'showChangePwdTip': True}, ensure_ascii=False).encode('utf-8'))

@api_route('POST', '/api/auth/user/info')
def handle_user_info(req, data):
    session = data.get('_session')
    if not session or 'userId' not in session:
        req._send_json({'success': False, 'message': '未登录'})
        return
    db = get_connection()
    user = db.execute(
        'SELECT phone, email, registered_at, last_login_at, last_active_at FROM users WHERE id = ? AND is_active = 1',
        (session['userId'],)
    ).fetchone()
    if not user:
        req._send_json({'success': False, 'message': '用户不存在'})
        return
    online = False
    if user['last_active_at']:
        try:
            active_ts = time.mktime(time.strptime(user['last_active_at'], '%Y-%m-%d %H:%M:%S'))
            online = (time.time() - active_ts) < 60
        except Exception:
            pass
    req._send_json({
        'success': True,
        'data': {
            'phone': user['phone'],
            'email': user['email'],
            'registered_at': user['registered_at'],
            'last_login_at': user['last_login_at'] or '首次登录',
            'last_active_at': user['last_active_at'],
            'online': online
        }
    })

@api_route('POST', '/api/auth/change-password')
def handle_change_password(req, data):
    session = data.get('_session')
    ip = data.get('_ip', '')
    if not session or 'userId' not in session:
        req._send_json({'success': False, 'message': '未登录'})
        return
    current = data.get('currentPassword', '')
    new_pwd = data.get('newPassword', '')
    if not current or not new_pwd:
        req._send_json({'success': False, 'message': '参数不完整'})
        return
    err = _validate_length(current, MAX_PASSWORD_LEN, '当前密码') or _validate_length(new_pwd, MAX_PASSWORD_LEN, '新密码')
    if err:
        req._send_json({'success': False, 'message': err})
        return
    if not is_valid_password(new_pwd):
        req._send_json({'success': False, 'message': get_password_error()})
        return
    db = get_connection()
    user = db.execute('SELECT * FROM users WHERE id = ? AND is_active = 1', (session['userId'],)).fetchone()
    if not user:
        req._send_json({'success': False, 'message': '用户不存在'})
        return
    if not check_password(current, user['password_hash']):
        add_log('修改密码', user['phone'], '当前密码错误', ip, 'fail')
        req._send_json({'success': False, 'message': '当前密码错误'})
        return
    new_hash = hash_password(new_pwd)
    db.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, session['userId']))
    db.commit()
    destroy_user_sessions(session['userId'], except_session_id=data.get('_session_id'))
    add_log('修改密码', user['phone'], '密码修改成功', ip)
    req._send_json({'success': True, 'message': '密码修改成功'})

@api_route('POST', '/api/auth/change-password-by-email')
def handle_change_password_by_email(req, data):
    session = data.get('_session')
    ip = data.get('_ip', '')
    if not session or 'userId' not in session:
        req._send_json({'success': False, 'message': '未登录'})
        return
    db = get_connection()
    user = db.execute('SELECT * FROM users WHERE id = ? AND is_active = 1', (session['userId'],)).fetchone()
    if not user:
        req._send_json({'success': False, 'message': '用户不存在'})
        return
    email_code = data.get('emailCode', '')
    new_pwd = data.get('newPassword', '')
    if not email_code or not new_pwd:
        req._send_json({'success': False, 'message': '参数不完整'})
        return
    err = _validate_length(new_pwd, MAX_PASSWORD_LEN, '新密码')
    if err:
        req._send_json({'success': False, 'message': err})
        return
    if not is_valid_password(new_pwd):
        req._send_json({'success': False, 'message': get_password_error()})
        return
    record = db.execute(
        'SELECT * FROM login_codes WHERE phone = ? AND code = ? AND is_used = 0',
        (user['phone'], email_code)
    ).fetchone()
    if not record:
        add_log('修改密码（邮箱验证码）', user['phone'], '验证码错误', ip, 'fail')
        req._send_json({'success': False, 'message': '验证码错误'})
        return
    if record['expires_at'] < time.strftime('%Y-%m-%d %H:%M:%S'):
        add_log('修改密码（邮箱验证码）', user['phone'], '验证码已过期', ip, 'fail')
        req._send_json({'success': False, 'message': '验证码已过期'})
        return
    db.execute('UPDATE login_codes SET is_used = 1 WHERE id = ?', (record['id'],))
    new_hash = hash_password(new_pwd)
    db.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, session['userId']))
    db.commit()
    destroy_user_sessions(session['userId'], except_session_id=data.get('_session_id'))
    add_log('修改密码（邮箱验证码）', user['phone'], '通过邮箱验证码修改密码成功', ip)
    req._send_json({'success': True, 'message': '密码修改成功'})

@api_route('POST', '/api/auth/forgot-password/send-code')
def handle_forgot_send_code(req, data):
    phone = data.get('phone', '')
    ip = data.get('_ip', '')
    if not phone or not is_valid_phone(phone):
        req._send_json({'success': False, 'message': '手机号格式不正确'})
        return
    if not check_rate_limit(f'forgot_code_short:{phone}', 1, 3):
        req._send_json({'success': False, 'message': '操作过于频繁，请3秒后再试'})
        return
    db = get_connection()
    user = db.execute('SELECT * FROM users WHERE phone = ? AND is_active = 1', (phone,)).fetchone()
    if not user or not user['email']:
        add_log('忘记密码发码', phone, '用户无邮箱', ip, 'fail')
        req._send_json({'success': True, 'message': '如果该手机号已注册，验证码已发送至绑定的邮箱'})
        return
    code = generate_code(6)
    expires_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + 120))
    db.execute("DELETE FROM login_codes WHERE expires_at < datetime('now','localtime')")
    db.execute('DELETE FROM login_codes WHERE phone = ?', (phone,))
    db.execute('INSERT INTO login_codes (phone, email, code, expires_at) VALUES (?, ?, ?, ?)',
               (phone, user['email'], code, expires_at))
    db.commit()
    result = send_verification_code(user['email'], code, '')
    if result.get('success'):
        check_rate_limit(f'forgot_code_long:{phone}', 1, 60)
        add_log('忘记密码发码', phone, f'验证码已发送至 {user["email"]}', ip)
        req._send_json({'success': True, 'message': '验证码已发送'})
    else:
        add_log('忘记密码发码', phone, f'发送失败: {result.get("error")}', ip, 'fail')
        req._send_json({'success': False, 'message': '发送失败，请检查SMTP配置后重试'})

@api_route('POST', '/api/auth/forgot-password/reset')
def handle_forgot_reset(req, data):
    phone = data.get('phone', '')
    email_code = data.get('emailCode', '')
    new_pwd = data.get('newPassword', '')
    ip = data.get('_ip', '')
    if not phone or not email_code or not new_pwd:
        req._send_json({'success': False, 'message': '参数不完整'})
        return
    err = _validate_length(new_pwd, MAX_PASSWORD_LEN, '新密码')
    if err:
        req._send_json({'success': False, 'message': err})
        return
    if not is_valid_password(new_pwd):
        req._send_json({'success': False, 'message': get_password_error()})
        return
    if not check_rate_limit(f'forgot_reset:{phone}', 3, 60):
        req._send_json({'success': False, 'message': '操作过于频繁，请稍后再试'})
        return
    db = get_connection()
    record = db.execute(
        'SELECT * FROM login_codes WHERE phone = ? AND code = ? AND is_used = 0',
        (phone, email_code)
    ).fetchone()
    if not record:
        add_log('忘记密码重置', phone, '验证码错误', ip, 'fail')
        req._send_json({'success': False, 'message': '验证码错误'})
        return
    if record['expires_at'] < time.strftime('%Y-%m-%d %H:%M:%S'):
        add_log('忘记密码重置', phone, '验证码已过期', ip, 'fail')
        req._send_json({'success': False, 'message': '验证码已过期'})
        return
    user = db.execute('SELECT * FROM users WHERE phone = ? AND is_active = 1', (phone,)).fetchone()
    if not user:
        req._send_json({'success': False, 'message': '用户不存在'})
        return
    db.execute('UPDATE login_codes SET is_used = 1 WHERE id = ?', (record['id'],))
    new_hash = hash_password(new_pwd)
    db.execute('UPDATE users SET password_hash = ?, login_fail_count = 0 WHERE id = ?', (new_hash, user['id']))
    db.commit()
    destroy_user_sessions(user['id'])
    add_log('忘记密码重置', phone, '通过邮箱验证码重置密码成功', ip)
    req._send_json({'success': True, 'message': '密码重置成功，请重新登录'})

@api_route('POST', '/api/auth/logout')
def handle_logout(req, data):
    session_id = data.get('_session_id')
    phone = data.get('_session', {}).get('phone', '')
    if session_id:
        destroy_session(session_id)
    add_log('退出登录', phone, '用户退出登录', data.get('_ip', ''))
    req._send_json({'success': True, 'message': '已退出登录'})

@api_route('POST', '/api/auth/account/delete')
def handle_delete_account(req, data):
    session = data.get('_session')
    ip = data.get('_ip', '')
    if not session or 'userId' not in session:
        req._send_json({'success': False, 'message': '请先登录'})
        return
    password = data.get('password', '')
    if not password:
        req._send_json({'success': False, 'message': '需输入密码确认注销'})
        return
    db = get_connection()
    user = db.execute('SELECT * FROM users WHERE id = ? AND is_active = 1', (session['userId'],)).fetchone()
    if not user:
        req._send_json({'success': False, 'message': '用户不存在'})
        return
    if not check_password(password, user['password_hash']):
        add_log('注销账号', user['phone'], '密码错误，拒绝注销', ip, 'fail')
        req._send_json({'success': False, 'message': '密码错误'})
        return
    phone = user['phone']
    db.execute('UPDATE users SET is_active = 0 WHERE id = ?', (session['userId'],))
    db.execute('DELETE FROM authorized_phones WHERE owner_phone = ?', (phone,))
    db.commit()
    session_id = data.get('_session_id')
    if session_id:
        destroy_session(session_id)
    add_log('注销账号', phone, '账号已注销（软删除）', ip)
    req._send_json({'success': True, 'message': '账号已注销'})

@admin_api_route('POST', '/api/admin/login')
def handle_admin_login(req, data):
    username = data.get('username', '')
    password = data.get('password', '')
    ip = data.get('_ip', '')

    if not check_rate_limit(f'admin_login:{ip}', 5, 60):
        add_log('管理登录', '', '登录频率过高', ip, 'fail')
        req._send_json({'success': False, 'message': '操作过于频繁，请稍后再试'})
        return

    if not username or not password:
        add_log('管理登录', '', '用户名或密码为空', ip, 'fail')
        req._send_json({'success': False, 'message': '请输入用户名和密码'})
        return

    if verify_admin(username, password, _admin_creds):
        # 随机管理员（每次重启变化），默认等级3
        admin_session = create_session({'role': 'admin', 'admin_level': 3, 'admin_username': username, 'login_ip': ip})
        add_log('管理登录', '', f'管理员登录成功（随机账号）', ip)
        req.send_response(200)
        req._send_cors_headers()
        req.send_header('Content-Type', 'application/json; charset=utf-8')
        req._set_admin_cookie(admin_session)
        req.send_header('Cache-Control', 'no-store')
        req.end_headers()
        req.wfile.write(json.dumps({'success': True, 'message': '登录成功', 'level': 3}, ensure_ascii=False).encode('utf-8'))
    else:
        level = _verify_manager(username, password)
        if level is not None:
            admin_session = create_session({'role': 'admin', 'admin_level': level, 'admin_username': username, 'login_ip': ip})
            level_names = {1: '普通管理员', 2: '中级管理员', 3: '超级管理员'}
            lname = level_names.get(level, '未知')
            add_log('管理登录', '', f'管理用户登录成功（{lname}）', ip)
            req.send_response(200)
            req._send_cors_headers()
            req.send_header('Content-Type', 'application/json; charset=utf-8')
            req._set_admin_cookie(admin_session)
            req.send_header('Cache-Control', 'no-store')
            req.end_headers()
            req.wfile.write(json.dumps({'success': True, 'message': '登录成功', 'level': level}, ensure_ascii=False).encode('utf-8'))
        else:
            add_log('管理登录', '', '用户名或密码错误', ip, 'fail')
            req._send_json({'success': False, 'message': '用户名或密码错误'})

@api_route('GET', '/api/panel/status')
def handle_panel_status(req, data):
    uptime = int(time.time() - START_TIME)
    days, rem = divmod(uptime, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    uptime_str = f'{days}天{hours}时{mins}分{secs}秒' if days else f'{hours}时{mins}分{secs}秒' if hours else f'{mins}分{secs}秒'
    req._send_json({
        'success': True,
        'user_port': USER_PORT,
        'admin_port': ADMIN_PORT,
        'daemon_port': DAEMON_PORT,
        'daemon_online': _daemon_online,
        'uptime': uptime,
        'uptime_str': uptime_str,
        'started_at': int(START_TIME),
        'version': '1.0',
    })

@admin_api_route('POST', '/api/admin/check')
def handle_admin_check(req, data):
    admin = data.get('_admin_session')
    if admin and admin.get('role') == 'admin':
        level = admin.get('admin_level', 3)
        level_names = {1: '普通管理员', 2: '中级管理员', 3: '超级管理员'}
        req._send_json({'success': True, 'loggedIn': True, 'level': level, 'levelName': level_names.get(level, '未知'), 'username': admin.get('admin_username', '')})
    else:
        req._send_json({'success': True, 'loggedIn': False})

@admin_api_route('POST', '/api/admin/logout')
def handle_admin_logout(req, data):
    sid = data.get('_admin_session_id')
    if sid:
        destroy_session(sid)
    add_log('管理登出', '', '管理员退出登录', data.get('_ip', ''))
    req._send_json({'success': True, 'message': '已退出'})

@admin_api_route('POST', '/api/admin/logs')
def handle_admin_logs(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 1):
        req._send_json({'success': False, 'message': '未授权'})
        return
    try:
        limit = max(1, min(1000, int(data.get('limit', 200))))
        offset = max(0, int(data.get('offset', 0)))
    except ValueError:
        req._send_json({'success': False, 'message': '参数格式错误'})
        return
    action_filter = data.get('action', '') or None
    phone_filter = data.get('phone', '') or None
    logs = get_logs(limit=limit, offset=offset, action_filter=action_filter, phone_filter=phone_filter)
    req._send_json({'success': True, 'logs': logs})

@admin_api_route('GET', '/api/admin/logs')
def handle_admin_logs_get(req, data):
    handle_admin_logs(req, data)

@admin_api_route('POST', '/api/admin/users')
def handle_admin_users(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '未授权'})
        return
    db = get_connection()
    phone = data.get('phone', '').strip()
    email = data.get('email', '').strip()
    try:
        page = max(0, int(data.get('page', 0)))
        limit = max(1, min(200, int(data.get('limit', 50))))
    except (ValueError, TypeError):
        page = 0
        limit = 50
    offset = page * limit

    where = []
    params = []
    if phone:
        where.append('phone LIKE ?')
        params.append(f'%{_escape_like(phone)}%')
    if email:
        where.append('email LIKE ?')
        params.append(f'%{_escape_like(email)}%')
    where_clause = (' WHERE ' + ' AND '.join(where)) if where else ''

    total = db.execute(f'SELECT COUNT(*) as c FROM users{where_clause}', params).fetchone()['c']
    rows = db.execute(
        f'SELECT id, phone, email, registered_at, last_login_at, last_active_at, login_fail_count, is_active '
        f'FROM users{where_clause} ORDER BY id DESC LIMIT ? OFFSET ?',
        params + [limit, offset]
    ).fetchall()
    result = []
    for u in rows:
        user = dict(u)
        sms_count = db.execute(
            'SELECT COUNT(*) as c FROM sms_messages WHERE user_id = ?', (user['id'],)
        ).fetchone()['c']
        user['sms_count'] = sms_count
        result.append(user)
    req._send_json({'success': True, 'users': result, 'total': total, 'page': page, 'limit': limit})

@admin_api_route('POST', '/api/admin/user/detail')
def handle_admin_user_detail(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '未授权'})
        return
    try:
        user_id = int(data.get('user_id', 0))
    except (ValueError, TypeError):
        req._send_json({'success': False, 'message': '参数格式错误'})
        return
    if not user_id:
        req._send_json({'success': False, 'message': '缺少用户ID'})
        return
    db = get_connection()
    row = db.execute(
        'SELECT id, phone, email, registered_at, last_login_at, last_active_at, login_fail_count, is_active FROM users WHERE id = ?',
        (user_id,)
    ).fetchone()
    if not row:
        req._send_json({'success': False, 'message': '用户不存在'})
        return
    user = dict(row)
    user['sms_count'] = db.execute(
        'SELECT COUNT(*) as c FROM sms_messages WHERE user_id = ?', (user_id,)
    ).fetchone()['c']
    auth_phones = db.execute(
        'SELECT authorized_phone, created_at FROM authorized_phones WHERE owner_phone = ?',
        (user['phone'],)
    ).fetchall()
    user['authorized_phones'] = [dict(a) for a in auth_phones]
    req._send_json({'success': True, 'user': user})

@admin_api_route('POST', '/api/admin/user/toggle-active')
def handle_admin_user_toggle_active(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 3):
        req._send_json({'success': False, 'message': '权限不足（仅超级管理员可操作）'})
        return
    try:
        user_id = int(data.get('user_id', 0))
    except (ValueError, TypeError):
        req._send_json({'success': False, 'message': '参数格式错误'})
        return
    if not user_id:
        req._send_json({'success': False, 'message': '缺少用户ID'})
        return
    db = get_connection()
    row = db.execute('SELECT is_active, phone FROM users WHERE id = ?', (user_id,)).fetchone()
    if not row:
        req._send_json({'success': False, 'message': '用户不存在'})
        return
    new_status = 0 if row['is_active'] else 1
    db.execute('UPDATE users SET is_active = ? WHERE id = ?', (new_status, user_id))
    db.commit()
    action = '启用用户' if new_status else '禁用用户'
    add_log(action, row['phone'], f'管理员{action}: ID={user_id}', data.get('_ip', ''))
    req._send_json({'success': True, 'is_active': new_status, 'message': '用户状态已更新'})

@admin_api_route('POST', '/api/admin/user/delete')
def handle_admin_user_delete(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 3):
        req._send_json({'success': False, 'message': '权限不足（仅超级管理员可操作）'})
        return
    try:
        user_id = int(data.get('user_id', 0))
    except (ValueError, TypeError):
        req._send_json({'success': False, 'message': '参数格式错误'})
        return
    if not user_id:
        req._send_json({'success': False, 'message': '缺少用户ID'})
        return
    db = get_connection()
    row = db.execute('SELECT phone, email FROM users WHERE id = ?', (user_id,)).fetchone()
    if not row:
        req._send_json({'success': False, 'message': '用户不存在'})
        return
    phone = row['phone']
    email = row['email']
    db.execute('DELETE FROM sms_messages WHERE user_id = ?', (user_id,))
    db.execute('DELETE FROM authorized_phones WHERE owner_phone = ?', (phone,))
    db.execute('DELETE FROM reg_codes WHERE phone = ?', (phone,))
    db.execute('DELETE FROM login_codes WHERE phone = ?', (phone,))
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    # 清理日志中也抹掉手机号（隐私保护）
    db.execute('UPDATE logs SET phone = \'[已删除]\' WHERE phone = ?', (phone,))
    db.commit()
    add_log('删除用户', phone, f'管理员彻底删除用户: ID={user_id}, 手机={phone}, 邮箱={email}', data.get('_ip', ''))
    req._send_json({'success': True, 'message': f'用户 {phone} 已彻底删除'})

@admin_api_route('POST', '/api/admin/user/sms')
def handle_admin_user_sms(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '未授权'})
        return
    try:
        user_id = int(data.get('user_id', 0))
    except (ValueError, TypeError):
        req._send_json({'success': False, 'message': '参数格式错误'})
        return
    if not user_id:
        req._send_json({'success': False, 'message': '缺少用户ID'})
        return
    page = max(0, int(data.get('page', 0)))
    limit = max(1, min(500, int(data.get('limit', 50))))
    offset = page * limit
    search = data.get('search', '').strip()
    db = get_connection()
    if search:
        like = f'%{search}%'
        total = db.execute('SELECT COUNT(*) as c FROM sms_messages WHERE user_id = ? AND (sender LIKE ? OR content LIKE ?)', (user_id, like, like)).fetchone()['c']
        rows = db.execute(
            'SELECT id, sender, content, received_at, created_at, is_read FROM sms_messages WHERE user_id = ? AND (sender LIKE ? OR content LIKE ?) ORDER BY id DESC LIMIT ? OFFSET ?',
            (user_id, like, like, limit, offset)
        ).fetchall()
    else:
        total = db.execute('SELECT COUNT(*) as c FROM sms_messages WHERE user_id = ?', (user_id,)).fetchone()['c']
        rows = db.execute(
            'SELECT id, sender, content, received_at, created_at, is_read FROM sms_messages WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?',
            (user_id, limit, offset)
        ).fetchall()
    messages = [dict(r) for r in rows]
    req._send_json({'success': True, 'messages': messages, 'total': total, 'page': page, 'limit': limit})

@admin_api_route('POST', '/api/admin/stats')
def handle_admin_stats(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 1):
        req._send_json({'success': False, 'message': '未授权'})
        return
    db = get_connection()
    log_stats = get_log_stats()
    user_count = db.execute('SELECT COUNT(*) as c FROM users WHERE is_active = 1').fetchone()['c']
    total_users = db.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
    uptime_secs = int(time.time() - START_TIME)
    hours, remainder = divmod(uptime_secs, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f'{hours}小时{minutes}分{seconds}秒'
    req._send_json({
        'success': True,
        'stats': {
            'active_users': user_count,
            'total_users': total_users,
            'log_stats': log_stats,
            'uptime': uptime_str,
            'uptime_secs': uptime_secs,
            'server_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'python_version': platform.python_version(),
            'platform': platform.platform(),
            'user_port': USER_PORT,
            'admin_port': ADMIN_PORT,
            'user_domain': USER_DOMAIN,
            'admin_domain': ADMIN_DOMAIN,
            'mod_dir': MOD_DIR,
            'mod_files': len([1 for _,_,fs in os.walk(MOD_DIR) for _ in fs])
        }
    })

@admin_api_route('POST', '/api/admin/mod/reload')
def handle_admin_mod_reload(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '未授权'})
        return
    scanned = []
    for sub in ('public', 'server', 'plugins'):
        p = os.path.join(MOD_DIR, sub)
        if not os.path.isdir(p):
            try: os.makedirs(p, exist_ok=True)
            except Exception: pass
    for root, _, names in os.walk(MOD_DIR):
        for f in names:
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, MOD_DIR)
            lang = _detect_language(f)
            valid = _is_valid_mod_file(fp)
            scanned.append({'path': rel, 'language': lang, 'valid': valid})
    sys.path.insert(0, os.path.join(MOD_DIR, 'server'))
    req._send_json({'success': True, 'message': f'Mod 重载完成，发现 {len(scanned)} 个文件', 'files': scanned})

@admin_api_route('GET', '/api/admin/mod/priorities')
def handle_admin_mod_priorities_get(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '未授权'})
        return
    priorities = _load_mod_priorities()
    req._send_json({'success': True, 'priorities': priorities})

@admin_api_route('POST', '/api/admin/mod/priorities')
def handle_admin_mod_priorities_set(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '未授权'})
        return
    mod_path = data.get('path', '')
    source = data.get('source', '')
    if not mod_path or source not in ('mod', 'builtin', 'disabled'):
        req._send_json({'success': False, 'message': '参数错误: path + source(mod/builtin/disabled)'})
        return
    _set_mod_priority(mod_path, source)
    req._send_json({'success': True, 'message': f'{mod_path} → {source}'})

@admin_api_route('POST', '/api/admin/mod/priorities/clear')
def handle_admin_mod_priorities_clear(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '未授权'})
        return
    try:
        os.remove(PRIORITIES_PATH)
        req._send_json({'success': True, 'message': '优先级配置已清除'})
    except Exception:
        req._send_json({'success': False, 'message': '清除失败'})

@admin_api_route('POST', '/api/admin/mod/upload')
def handle_admin_mod_upload(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '未授权'})
        return
    filename = data.get('filename', '')
    subdir = data.get('subdir', 'public')
    file_content_b64 = data.get('content', '')
    if not filename or not file_content_b64:
        req._send_json({'success': False, 'message': '缺少参数: filename, content'})
        return
    if '/' in filename or '\\' in filename or '..' in filename:
        req._send_json({'success': False, 'message': '文件名不能包含路径分隔符'})
        return
    if subdir not in ('public', 'server', 'plugins'):
        req._send_json({'success': False, 'message': 'subdir 必须是 public/server/plugins'})
        return
    target_dir = os.path.join(MOD_DIR, subdir)
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, filename)
    try:
        raw = base64.b64decode(file_content_b64)
    except Exception:
        req._send_json({'success': False, 'message': 'Base64 解码失败'})
        return
    if len(raw) > 1 << 20:
        req._send_json({'success': False, 'message': '文件过大（最大 1MB）'})
        return
    file_bytes = raw
    try:
        with open(target_path, 'wb') as f:
            f.write(file_bytes)
    except Exception:
        req._send_json({'success': False, 'message': '文件写入失败'})
        return
    lang = _detect_language(filename)
    req._send_json({'success': True, 'message': f'上传成功: {subdir}/{filename} ({lang})'})

@admin_api_route('POST', '/api/admin/mod/delete')
def handle_admin_mod_delete(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '未授权'})
        return
    filepath = data.get('path', '')
    if not filepath:
        req._send_json({'success': False, 'message': '缺少 path'})
        return
    if '..' in filepath:
        req._send_json({'success': False, 'message': '非法路径'})
        return
    target = os.path.normpath(os.path.join(MOD_DIR, filepath))
    if not target.startswith(os.path.normpath(MOD_DIR)):
        req._send_json({'success': False, 'message': '路径越界'})
        return
    if not os.path.isfile(target):
        req._send_json({'success': False, 'message': '文件不存在'})
        return
    try:
        os.remove(target)
        req._send_json({'success': True, 'message': f'已删除: {filepath}'})
    except Exception:
        req._send_json({'success': False, 'message': '删除失败'})

@admin_api_route('POST', '/api/admin/mod/scan')
def handle_admin_mod_scan(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '未授权'})
        return
    try:
        results = mod_scanner.scan_directory(MOD_DIR, all_files=True)
        total_score = sum(r['summary']['score'] for r in results)
        total_high = sum(r['summary']['high'] for r in results)
        total_medium = sum(r['summary']['medium'] for r in results)
        total_low = sum(r['summary']['low'] for r in results)
        grade = mod_scanner.score_to_grade(total_score)
        data_list = []
        for r in results:
            data_list.append({
                'relpath': r.get('relpath', os.path.basename(r['file'])),
                'binary': r.get('binary', False),
                'total': r['summary']['total'],
                'high': r['summary']['high'],
                'medium': r['summary']['medium'],
                'low': r['summary']['low'],
                'score': r['summary']['score'],
                'highest': r['summary'].get('highest', 0),
                'issues': [(l or 0, w, d) for l, w, d in r['issues']],
            })
        if total_high > 0:
            add_notification('scan_alert', _t('notification_scan_alert'),
                f'扫描发现 {total_high} 个高风险, {total_medium} 个中风险问题 (评级: {grade})',
                'danger', 0)
        elif total_medium > 0:
            add_notification('scan_alert', _t('notification_scan_alert'),
                f'扫描发现 {total_medium} 个中风险问题 (评级: {grade})',
                'warning', 0)
        req._send_json({
            'success': True,
            'files_scanned': len(results),
            'total_score': total_score,
            'grade': grade,
            'summary': {'high': total_high, 'medium': total_medium, 'low': total_low},
            'files': data_list,
        })
    except Exception as e:
        log(f'[Mod扫描] 扫描失败: {e}')
        req._send_json({'success': False, 'message': '扫描失败，请检查文件路径'})

@admin_api_route('POST', '/api/admin/mod/scan-file')
def handle_admin_mod_scan_file(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '未授权'})
        return
    filepath = data.get('path', '')
    if not filepath:
        req._send_json({'success': False, 'message': '缺少 path'})
        return
    if '..' in filepath:
        req._send_json({'success': False, 'message': '非法路径'})
        return
    target = os.path.normpath(os.path.join(MOD_DIR, filepath))
    if not target.startswith(os.path.normpath(MOD_DIR)):
        req._send_json({'success': False, 'message': '路径越界'})
        return
    if not os.path.isfile(target):
        req._send_json({'success': False, 'message': '文件不存在'})
        return
    try:
        result = mod_scanner.scan_file(target)
        req._send_json({
            'success': True,
            'file': result.get('relpath', filepath),
            'binary': result.get('binary', False),
            'summary': result['summary'],
            'issues': [(l or 0, w, d) for l, w, d in result['issues']],
        })
    except Exception as e:
        log(f'[Mod扫描] 文件扫描失败: {e}')
        req._send_json({'success': False, 'message': '扫描文件失败'})

@admin_api_route('POST', '/api/admin/mail-config')
def handle_mail_config(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '未授权'})
        return

    if data.get('save'):
        host = data.get('host', '')
        port = data.get('port', 25)
        if not host or not isinstance(port, int) or port <= 0:
            req._send_json({'success': False, 'message': '请输入有效的SMTP服务器和端口'})
            return
        new_pass = data.get('pass', '')
        config_path = os.path.join(DATA_DIR, 'mail_config.json')
        if 'pass' not in data and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    existing = json.load(f)
                new_pass = existing.get('pass', '')
            except Exception:
                pass
        save_mail_config(
            host, port,
            data.get('user', ''),
            new_pass,
            data.get('from_addr', ''),
            data.get('from_name', ''),
            data.get('tls', False),
            data.get('verify_ssl', True)
        )
        add_log('邮件配置', '', f'SMTP配置已更新: {host}:{port}', data.get('_ip', ''))
        req._send_json({'success': True, 'message': '配置已保存'})
        return

    config_path = os.path.join(DATA_DIR, 'mail_config.json')
    cfg = {}
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            cfg = json.load(f)
    cfg.pop('pass', None)
    cfg['_current'] = {
        'host': mail_module.SMTP_HOST,
        'port': mail_module.SMTP_PORT,
        'user': mail_module.SMTP_USER,
        'pass': '',
        'from_addr': mail_module.FROM_ADDR,
        'from_name': mail_module.FROM_NAME,
        'tls': mail_module.SMTP_TLS,
        'verify_ssl': mail_module.SMTP_VERIFY_SSL
    }
    req._send_json({'success': True, 'config': cfg})

@admin_api_route('POST', '/api/admin/report/create')
def handle_admin_report_create(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '权限不足'})
        return
    target_user_id = data.get('target_user_id', 0)
    try:
        target_user_id = int(target_user_id)
    except (ValueError, TypeError):
        req._send_json({'success': False, 'message': '参数格式错误'})
        return
    reason = (data.get('reason', '') or '').strip()
    detail = (data.get('detail', '') or '').strip()
    if not target_user_id or not reason:
        req._send_json({'success': False, 'message': '请选择用户并填写原因'})
        return
    db = get_connection()
    target = db.execute('SELECT phone, email FROM users WHERE id = ?', (target_user_id,)).fetchone()
    if not target:
        req._send_json({'success': False, 'message': '目标用户不存在'})
        return
    with _REPORTS_LOCK:
        global _REPORT_ID
        _REPORT_ID += 1
        report = {
            'id': _REPORT_ID,
            'reporter': admin['admin_username'],
            'reporter_level': admin.get('admin_level', 2),
            'target_user_id': target_user_id,
            'target_phone': target['phone'],
            'target_email': target['email'] or '',
            'reason': reason,
            'detail': detail,
            'status': 'pending',
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'resolved_by': '',
            'resolved_at': '',
            'resolution': ''
        }
        _REPORTS.append(report)
        _save_reports()
    add_log('提交报告', '', f'管理员{admin["admin_username"]}提交删除报告: 用户{target["phone"]}, 原因:{reason}', data.get('_ip', ''))
    req._send_json({'success': True, 'message': '报告已提交，等待超级管理员审核', 'report_id': _REPORT_ID})

@admin_api_route('POST', '/api/admin/report/list')
def handle_admin_report_list(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': '权限不足'})
        return
    page = max(0, int(data.get('page', 0)))
    limit = max(1, min(100, int(data.get('limit', 20))))
    offset = page * limit
    status_filter = data.get('status', '') or None
    with _REPORTS_LOCK:
        filtered = _REPORTS
        if status_filter:
            filtered = [r for r in filtered if r['status'] == status_filter]
        if admin.get('admin_level', 0) < 3:
            filtered = [r for r in filtered if r['reporter'] == admin['admin_username']]
        total = len(filtered)
        page_data = filtered[offset:offset + limit]
    req._send_json({'success': True, 'reports': page_data, 'total': total, 'page': page, 'limit': limit})

@admin_api_route('POST', '/api/admin/report/resolve')
def handle_admin_report_resolve(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 3):
        req._send_json({'success': False, 'message': '权限不足（仅超级管理员可操作）'})
        return
    report_id = int(data.get('report_id', 0))
    resolution = (data.get('resolution', '') or '').strip()
    action = data.get('action', 'approve')
    if not report_id:
        req._send_json({'success': False, 'message': '缺少报告ID'})
        return
    with _REPORTS_LOCK:
        report = None
        for r in _REPORTS:
            if r['id'] == report_id:
                report = r
                break
        if not report:
            req._send_json({'success': False, 'message': '报告不存在'})
            return
        if report['status'] != 'pending':
            req._send_json({'success': False, 'message': '报告已经处理'})
            return
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        if action == 'approve':
            report['status'] = 'approved'
            report['resolution'] = resolution or '已批准删除'
        else:
            report['status'] = 'rejected'
            report['resolution'] = resolution or '已驳回'
        report['resolved_by'] = admin['admin_username']
        report['resolved_at'] = now
        _save_reports()
    add_log('处理报告', '', f'管理员{admin["admin_username"]} {report["status"]}报告 #{report_id}: {report["resolution"]}', data.get('_ip', ''))
    req._send_json({'success': True, 'message': f'报告 #{report_id} 已{("批准" if action=="approve" else "驳回")}'})

@admin_api_route('POST', '/api/admin/report/delete')
def handle_admin_report_delete(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 3):
        req._send_json({'success': False, 'message': '权限不足'})
        return
    report_id = int(data.get('report_id', 0))
    if not report_id:
        req._send_json({'success': False, 'message': '缺少报告ID'})
        return
    with _REPORTS_LOCK:
        global _REPORTS
        _REPORTS = [r for r in _REPORTS if r['id'] != report_id]
        _save_reports()
    req._send_json({'success': True, 'message': f'报告 #{report_id} 已删除'})

@admin_api_route('POST', '/api/admin/report/stats')
def handle_admin_report_stats(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 3):
        req._send_json({'success': False, 'message': '权限不足'})
        return
    with _REPORTS_LOCK:
        total = len(_REPORTS)
        pending = sum(1 for r in _REPORTS if r['status'] == 'pending')
        approved = sum(1 for r in _REPORTS if r['status'] == 'approved')
        rejected = sum(1 for r in _REPORTS if r['status'] == 'rejected')
    req._send_json({'success': True, 'stats': {'total': total, 'pending': pending, 'approved': approved, 'rejected': rejected}})

@admin_api_route('POST', '/api/admin/managers')
def handle_admin_managers(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 1):
        req._send_json({'success': False, 'message': '未授权'})
        return
    managers = _get_online_managers()
    req._send_json({'success': True, 'managers': managers})

@admin_api_route('POST', '/api/admin/manager/create')
def handle_admin_manager_create(req, data):
    admin = data.get('_admin_session')
    admin_level = admin.get('admin_level', 0) if admin else 0
    if admin_level < 2:
        req._send_json({'success': False, 'message': '权限不足，仅中级/超级管理员可创建管理账号'})
        return
    username = (data.get('username', '') or '').strip()
    password = data.get('password', '')
    level = int(data.get('level', 1))
    if not username or not password:
        req._send_json({'success': False, 'message': '请填写用户名和密码'})
        return
    if level < 1 or level > 3:
        req._send_json({'success': False, 'message': '等级必须为1-3'})
        return
    if admin_level < 3 and level >= admin_level:
        req._send_json({'success': False, 'message': f'您的等级（{admin_level}）不能创建等级≥{admin_level}的账号'})
        return
    ok, msg = _add_manager(username, password, level, admin['admin_username'])
    if ok:
        add_log('创建管理用户', '', f'管理员{admin["admin_username"]}创建了等级{level}的管理用户 {username}', data.get('_ip', ''))
    req._send_json({'success': ok, 'message': msg})

@admin_api_route('POST', '/api/admin/manager/delete')
def handle_admin_manager_delete(req, data):
    admin = data.get('_admin_session')
    admin_level = admin.get('admin_level', 0) if admin else 0
    if admin_level < 2:
        req._send_json({'success': False, 'message': '权限不足'})
        return
    username = (data.get('username', '') or '').strip()
    if not username:
        req._send_json({'success': False, 'message': '请填写要删除的用户名'})
        return
    target = None
    for m in _MANAGERS:
        if m['username'] == username:
            target = m
            break
    if not target:
        req._send_json({'success': False, 'message': f'用户 {username} 不存在'})
        return
    if admin_level < 3:
        if target['level'] >= admin_level:
            req._send_json({'success': False, 'message': '您的等级不能删除同级或更高级的管理员'})
            return
        if target.get('created_by', '') != admin['admin_username']:
            req._send_json({'success': False, 'message': '您只能删除自己创建的管理员'})
            return
    ok, msg = _rm_manager(username)
    if ok:
        add_log('删除管理用户', '', f'管理员{admin["admin_username"]}删除了管理用户 {username}', data.get('_ip', ''))
        destroy_admin_sessions(username)
    req._send_json({'success': ok, 'message': msg})

@admin_api_route('POST', '/api/admin/user/change-password')
def handle_admin_user_change_password(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 3):
        req._send_json({'success': False, 'message': '权限不足（仅超级管理员可更改用户密码）'})
        return
    user_id = int(data.get('user_id', 0))
    new_password = data.get('new_password', '')
    if not user_id or not new_password:
        req._send_json({'success': False, 'message': '请选择用户并填写新密码'})
        return
    if len(new_password) < 6:
        req._send_json({'success': False, 'message': '密码长度至少6位'})
        return
    from utils import hash_password, is_valid_password, get_password_error
    if not is_valid_password(new_password):
        req._send_json({'success': False, 'message': get_password_error()})
        return
    db = get_connection()
    user = db.execute('SELECT phone FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        req._send_json({'success': False, 'message': '用户不存在'})
        return
    new_hash = hash_password(new_password)
    db.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, user_id))
    db.commit()
    add_log('管理员改密', user['phone'], f'超级管理员 {admin["admin_username"]} 更改了用户密码', data.get('_ip', ''))
    req._send_json({'success': True, 'message': '密码已更新'})

@admin_api_route('POST', '/api/admin/user/update')
def handle_admin_user_update(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 3):
        req._send_json({'success': False, 'message': '权限不足（仅超级管理员可编辑用户）'})
        return
    user_id = int(data.get('user_id', 0))
    if not user_id:
        req._send_json({'success': False, 'message': '缺少用户ID'})
        return
    db = get_connection()
    user = db.execute('SELECT phone FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        req._send_json({'success': False, 'message': '用户不存在'})
        return
    new_email = (data.get('email', '') or '').strip()
    if new_email:
        db.execute('UPDATE users SET email = ? WHERE id = ?', (new_email, user_id))
    db.commit()
    add_log('编辑用户', user['phone'], f'超级管理员 {admin["admin_username"]} 编辑了用户信息', data.get('_ip', ''))
    req._send_json({'success': True, 'message': '用户信息已更新'})

@admin_api_route('GET', '/api/admin/notifications')
def handle_admin_notifications_get(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 1):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    try:
        limit = max(1, min(200, int(data.get('limit', 50))))
        offset = max(0, int(data.get('offset', 0)))
    except (ValueError, TypeError):
        limit, offset = 50, 0
    unread_only = data.get('unread_only', False) or data.get('unread', False)
    notifs, total = get_notifications(limit, offset, unread_only=bool(unread_only))
    unread = get_unread_notification_count()
    req._send_json({'success': True, 'notifications': notifs, 'total': total, 'unread': unread})

@admin_api_route('POST', '/api/admin/notifications')
def handle_admin_notifications_post(req, data):
    return handle_admin_notifications_get(req, data)

@admin_api_route('POST', '/api/admin/notifications/mark-read')
def handle_admin_notifications_mark_read(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 1):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    notif_id = data.get('id', 0)
    try:
        notif_id = int(notif_id)
    except (ValueError, TypeError):
        req._send_json({'success': False, 'message': '参数格式错误'})
        return
    if notif_id:
        mark_notification_read(notif_id)
        req._send_json({'success': True, 'message': _t('operation_success')})
    else:
        mark_all_notifications_read()
        req._send_json({'success': True, 'message': _t('operation_success')})

@admin_api_route('POST', '/api/admin/notifications/mark-all-read')
def handle_admin_notifications_mark_all_read(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 1):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    mark_all_notifications_read()
    req._send_json({'success': True, 'message': _t('operation_success')})

@admin_api_route('GET', '/api/admin/notifications/unread-count')
def handle_admin_notifications_unread_count(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 1):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    unread = get_unread_notification_count()
    req._send_json({'success': True, 'unread': unread})

@admin_api_route('GET', '/api/admin/mod/manifests')
def handle_admin_mod_manifests(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    manifests = []
    for rel_path, manifest in _MOD_MANIFESTS.items():
        entry = {'location': rel_path, 'manifest': manifest}
        if rel_path != '_global':
            entry['errors'] = _validate_manifest(manifest)
        manifests.append(entry)
    req._send_json({'success': True, 'manifests': manifests})

@admin_api_route('POST', '/api/admin/mod/manifests')
def handle_admin_mod_manifests_post(req, data):
    return handle_admin_mod_manifests(req, data)

@admin_api_route('POST', '/api/admin/mod/manifest/validate')
def handle_admin_mod_manifest_validate(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    manifest = data.get('manifest', {})
    errors = _validate_manifest(manifest)
    valid = len(errors) == 0
    req._send_json({'success': True, 'valid': valid, 'errors': errors})

@admin_api_route('GET', '/api/admin/export/sms-csv')
def handle_admin_export_sms_csv(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    try:
        limit = max(1, min(10000, int(data.get('limit', 5000))))
        offset = max(0, int(data.get('offset', 0)))
    except (ValueError, TypeError):
        limit, offset = 5000, 0
    user_id = data.get('user_id', 0)
    db = get_connection()
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', '用户ID', '用户手机', '发件人', '内容', '接收时间', '已读', '创建时间'])
    if user_id:
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            req._send_json({'success': False, 'message': '参数格式错误'})
            return
        rows = db.execute(
            'SELECT id, user_id, user_phone, sender, content, received_at, is_read, created_at FROM sms_messages WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?',
            (uid, limit, offset)
        ).fetchall()
    else:
        rows = db.execute(
            'SELECT id, user_id, user_phone, sender, content, received_at, is_read, created_at FROM sms_messages ORDER BY id DESC LIMIT ? OFFSET ?',
            (limit, offset)
        ).fetchall()
    for r in rows:
        writer.writerow([r['id'], r['user_id'], r['user_phone'], r['sender'], r['content'], r['received_at'], r['is_read'], r['created_at']])
    csv_data = output.getvalue()
    req.send_response(200)
    req._send_cors_headers()
    req.send_header('Content-Type', 'text/csv; charset=utf-8')
    req.send_header('Content-Disposition', f'attachment; filename="sms_export_{int(time.time())}.csv"')
    req.send_header('Content-Length', str(len(csv_data.encode('utf-8'))))
    req.send_header('X-Content-Type-Options', 'nosniff')
    req.end_headers()
    req.wfile.write(csv_data.encode('utf-8-sig'))

@admin_api_route('GET', '/api/admin/export/users-csv')
def handle_admin_export_users_csv(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    db = get_connection()
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', '手机号', '邮箱', '注册时间', '最后登录', '最后活跃', '登录失败', '活跃'])
    rows = db.execute(
        'SELECT id, phone, email, registered_at, last_login_at, last_active_at, login_fail_count, is_active FROM users ORDER BY id'
    ).fetchall()
    for r in rows:
        writer.writerow([r['id'], r['phone'], r['email'], r['registered_at'], r['last_login_at'] or '', r['last_active_at'] or '', r['login_fail_count'], '是' if r['is_active'] else '否'])
    csv_data = output.getvalue()
    req.send_response(200)
    req._send_cors_headers()
    req.send_header('Content-Type', 'text/csv; charset=utf-8')
    req.send_header('Content-Disposition', f'attachment; filename="users_export_{int(time.time())}.csv"')
    req.send_header('Content-Length', str(len(csv_data.encode('utf-8'))))
    req.send_header('X-Content-Type-Options', 'nosniff')
    req.end_headers()
    req.wfile.write(csv_data.encode('utf-8-sig'))

@admin_api_route('POST', '/api/admin/export/sms-json')
def handle_admin_export_sms_json(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    user_id = data.get('user_id', 0)
    try:
        limit = max(1, min(10000, int(data.get('limit', 5000))))
    except (ValueError, TypeError):
        limit = 5000
    db = get_connection()
    if user_id:
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            req._send_json({'success': False, 'message': '参数格式错误'})
            return
        rows = db.execute(
            'SELECT id, user_id, user_phone, sender, content, received_at, is_read, created_at FROM sms_messages WHERE user_id = ? ORDER BY id DESC LIMIT ?',
            (uid, limit)
        ).fetchall()
    else:
        rows = db.execute(
            'SELECT id, user_id, user_phone, sender, content, received_at, is_read, created_at FROM sms_messages ORDER BY id DESC LIMIT ?',
            (limit,)
        ).fetchall()
    export = {
        'export_time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(rows),
        'messages': [dict(r) for r in rows]
    }
    req._send_json({'success': True, 'export': export})

@admin_api_route('POST', '/api/admin/settings/language')
def handle_admin_settings_language(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    lang = data.get('language', 'zh')
    if lang not in _TRANSLATIONS:
        langs = ', '.join(_TRANSLATIONS.keys())
        msg = f'Unsupported language: {lang}, supported: {langs}'
        req._send_json({'success': False, 'message': msg})
        return
    session_id = data.get('_admin_session_id', '')
    if session_id:
        sess = get_session(session_id)
        if sess:
            sess['language'] = lang
            save_session(session_id, sess)
            # Also persist to config as server default
            config_path = os.path.join(DATA_DIR, 'config.json')
            try:
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        cfg = json.load(f)
                else:
                    cfg = {}
                cfg['language'] = lang
                with open(config_path, 'w') as f:
                    json.dump(cfg, f, indent=2)
            except Exception:
                pass
    admin_lang = _lang_from_session(admin)
    req._send_json({'success': True, 'message': _t('operation_success', admin_lang), 'language': lang, 'lang_name': _TRANSLATIONS[lang]['lang_name']})

@api_route('GET', '/api/languages')
def handle_languages(req, data):
    lang_list = []
    for code, t in _TRANSLATIONS.items():
        lang_list.append({'code': code, 'name': t.get('lang_name', code)})
    req._send_json({'success': True, 'languages': lang_list})

@admin_api_route('GET', '/api/admin/languages')
def handle_admin_languages(req, data):
    lang_list = []
    for code, t in _TRANSLATIONS.items():
        lang_list.append({'code': code, 'name': t.get('lang_name', code)})
    req._send_json({'success': True, 'languages': lang_list})

@admin_api_route('POST', '/api/admin/daemon/restart')
def handle_admin_daemon_restart(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    from threading import Thread
    Thread(target=lambda: (_stop_daemon(), time.sleep(1), _start_daemon()), daemon=True).start()
    req._send_json({'success': True, 'message': '守护进程正在重启...'})

# -- Icon Upload & Conversion --

SUPPORTED_IMAGE_FORMATS = {
    '.jpg': 'JPEG', '.jpeg': 'JPEG', '.jfif': 'JPEG', '.pjpeg': 'JPEG',
    '.png': 'PNG', '.gif': 'GIF', '.bmp': 'BMP', '.dib': 'BMP',
    '.tif': 'TIFF', '.tiff': 'TIFF', '.webp': 'WEBP',
    '.ico': 'ICO', '.svg': 'SVG',
}

SUPPORTED_FONT_FORMATS = {
    '.ttf': 'ttf', '.otf': 'otf', '.woff': 'woff', '.woff2': 'woff2', '.eot': 'eot',
}

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

@admin_api_route('POST', '/api/admin/upload-icon')
def handle_upload_icon(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    if not HAS_PIL:
        req._send_json({'success': False, 'message': '服务器缺少 Pillow 库，无法转换图片。请运行: pip install Pillow'})
        return
    image_b64 = data.get('image', '')
    fmt = data.get('format', '').lower().strip('.')
    if not image_b64:
        req._send_json({'success': False, 'message': '请提供图片数据 (base64)'})
        return
    ext = '.' + fmt if fmt else '.png'
    try:
        raw = base64.b64decode(image_b64)
        img = Image.open(BytesIO(raw))
        img.verify()
        img = Image.open(BytesIO(raw))
        if img.mode not in ('RGB', 'RGBA'):
            if img.mode == 'P':
                img = img.convert('RGBA' if 'transparency' in img.info else 'RGB')
            else:
                img = img.convert('RGBA')
        # Generate icons
        sizes = {
            'favicon.ico': (32, 32),
            'icon.png': (192, 192),
            'icon-512.png': (512, 512),
        }
        public_dir = PUBLIC_DIR
        for name, (w, h) in sizes.items():
            out = img.copy()
            out.thumbnail((w, h), Image.LANCZOS)
            if out.mode == 'RGBA' and name.endswith('.ico'):
                bg = Image.new('RGB', out.size, (255, 255, 255))
                bg.paste(out, mask=out.split()[3])
                out = bg
            if name.endswith('.ico'):
                out.save(os.path.join(public_dir, name), format='ICO', sizes=[(w, h)])
            else:
                out.save(os.path.join(public_dir, name), format='PNG')
        # Regenerate Android drawables
        _regenerate_android_icons(img)
        req._send_json({'success': True, 'message': '图标已更新 (favicon.ico / icon.png / icon-512.png / Android drawables)'})
    except Exception as e:
        req._send_json({'success': False, 'message': f'图片处理失败: {e}'})

def _regenerate_android_icons(img):
    android_dirs = {
        'drawable-nodpi': (256, 256, 'ic_project.png'),
        'drawable': (48, 48, 'ic_project_small.png'),
    }
    mobile_base = os.path.join(os.path.dirname(__file__), '..', 'mobile', 'SmsToWeb', 'app', 'src', 'main', 'res')
    for d, (w, h, fname) in android_dirs.items():
        target_dir = os.path.join(mobile_base, d)
        if not os.path.isdir(target_dir):
            continue
        out = img.copy()
        out.thumbnail((w, h), Image.LANCZOS)
        if out.mode != 'RGBA':
            out = out.convert('RGBA')
        out.save(os.path.join(target_dir, fname), format='PNG')

@admin_api_route('POST', '/api/admin/upload-font')
def handle_upload_font(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    font_b64 = data.get('font', '')
    ext = data.get('format', '').lower().strip('.')
    if not font_b64 or not ext:
        req._send_json({'success': False, 'message': '请提供字体数据 (base64) 和格式'})
        return
    if '.' + ext not in SUPPORTED_FONT_FORMATS:
        req._send_json({'success': False, 'message': f'不支持的字体格式: {ext}。支持: {", ".join(SUPPORTED_FONT_FORMATS.keys())}'})
        return
    try:
        raw = base64.b64decode(font_b64)
        fonts_dir = os.path.join(PUBLIC_DIR, 'fonts')
        os.makedirs(fonts_dir, exist_ok=True)
        fname = f'custom_font.{ext}'
        fpath = os.path.join(fonts_dir, fname)
        with open(fpath, 'wb') as f:
            f.write(raw)
        # Update config to use this font via @font-face
        cfg = _load_config()
        if ext in ('ttf', 'otf', 'woff', 'woff2'):
            cfg['theme_font'] = f'"Custom Font", -apple-system, sans-serif'
            cfg['theme_font_url'] = f'/fonts/{fname}'
        else:
            cfg['theme_font'] = f'-apple-system, sans-serif'
        config_path = os.path.join(DATA_DIR, 'config.json')
        with open(config_path, 'w') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        req._send_json({'success': True, 'message': f'字体已上传: /fonts/{fname}'})
    except Exception as e:
        req._send_json({'success': False, 'message': f'字体上传失败: {e}'})

@admin_api_route('POST', '/api/admin/manage/clean-panel-cache')
def handle_manage_clean_panel_cache(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    try:
        logs = 0; pycs = 0; sessions = 0
        for f in [f'{DATA_DIR}/../server.log', f'{DATA_DIR}/../daemon.log']:
            if os.path.isfile(f):
                open(f, 'w').close()
                logs += 1
        for root, dirs, files in os.walk(os.path.dirname(DATA_DIR)):
            for f in files:
                if f.endswith('.pyc'):
                    os.remove(os.path.join(root, f)); pycs += 1
            for d in dirs:
                if d == '__pycache__':
                    import shutil; shutil.rmtree(os.path.join(root, d), ignore_errors=True); pycs += 1
        for f in os.listdir(DATA_DIR):
            if f.startswith('session_'):
                os.remove(os.path.join(DATA_DIR, f)); sessions += 1
        req._send_json({'success': True, 'message': f'面板缓存已清理 (日志:{logs} pyc:{pycs} 会话:{sessions})'})
    except Exception as e:
        req._send_json({'success': False, 'message': f'清理失败: {e}'})

@admin_api_route('POST', '/api/admin/manage/clean-system-cache')
def handle_manage_clean_system_cache(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    try:
        results = []
        for pkg, cmd in [('apt-get', 'apt-get clean'), ('dnf', 'dnf clean all'), ('yum', 'yum clean all'), ('pacman', 'pacman -Scc --noconfirm')]:
            if subprocess.run(['which', pkg], capture_output=True).returncode == 0:
                r = subprocess.run(cmd.split(), capture_output=True, timeout=30)
                results.append(f'{pkg}:{"OK" if r.returncode==0 else "FAIL"}')
        if subprocess.run(['which', 'journalctl'], capture_output=True).returncode == 0:
            subprocess.run(['journalctl', '--vacuum-size=100M'], capture_output=True, timeout=30)
            results.append('journal:OK')
        req._send_json({'success': True, 'message': '系统缓存已清理: ' + ', '.join(results)})
    except Exception as e:
        req._send_json({'success': False, 'message': f'清理失败: {e}'})

@admin_api_route('POST', '/api/admin/manage/config')
def handle_manage_config(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    config_path = os.path.join(DATA_DIR, 'config.json')
    action = data.get('action', 'get')
    if action == 'get':
        cfg = _load_config()
        req._send_json({'success': True, 'config': cfg})
    elif action == 'set':
        key = data.get('key', '')
        val = data.get('value', '')
        if not key:
            req._send_json({'success': False, 'message': 'key required'})
            return
        try:
            cfg = _load_config()
            cfg[key] = val
            with open(config_path, 'w') as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            req._send_json({'success': True, 'message': f'{key} 已设置'})
        except Exception as e:
            req._send_json({'success': False, 'message': f'写入失败: {e}'})
    else:
        req._send_json({'success': False, 'message': f'Unknown action: {action}'})

@admin_api_route('POST', '/api/admin/manage/backup')
def handle_manage_backup(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 2):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    try:
        import shutil
        bak_dir = os.path.join(os.path.dirname(DATA_DIR), 'backup')
        os.makedirs(bak_dir, exist_ok=True)
        fname = f'sms2web-backup-{time.strftime("%Y%m%d_%H%M%S")}.tar.gz'
        fpath = os.path.join(bak_dir, fname)
        base = os.path.dirname(DATA_DIR)
        archive = shutil.make_archive(fpath.replace('.tar.gz', ''), 'gztar', base, ['data', 'mod'])
        if archive:
            req._send_json({'success': True, 'file': fname, 'size': os.path.getsize(archive)})
        else:
            req._send_json({'success': False, 'message': '备份创建失败'})
    except Exception as e:
        req._send_json({'success': False, 'message': f'备份失败: {e}'})

@admin_api_route('POST', '/api/admin/manage/backups')
def handle_manage_backups(req, data):
    admin = data.get('_admin_session')
    if not _require_level(admin, 1):
        req._send_json({'success': False, 'message': _t('unauthorized')})
        return
    bak_dir = os.path.join(os.path.dirname(DATA_DIR), 'backup')
    files = []
    if os.path.isdir(bak_dir):
        for f in sorted(os.listdir(bak_dir), reverse=True):
            if f.endswith('.tar.gz'):
                fpath = os.path.join(bak_dir, f)
                files.append({'name': f, 'size': os.path.getsize(fpath), 'mtime': os.path.getmtime(fpath)})
    req._send_json({'success': True, 'files': files})

# -- SSL --
SSL_DIR = os.path.join(DATA_DIR, 'ssl')

def _ensure_ssl_dir():
    os.makedirs(SSL_DIR, exist_ok=True)

def _cert_is_valid(cert_path, key_path):
    """验证证书和密钥文件是否有效"""
    if not os.path.isfile(cert_path) or not os.path.isfile(key_path):
        return False
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert_path, key_path)
        return True
    except Exception:
        return False

def _gen_self_signed_cert():
    _ensure_ssl_dir()
    cert = os.path.join(SSL_DIR, 'server.crt')
    key = os.path.join(SSL_DIR, 'server.key')
    if _cert_is_valid(cert, key):
        log(f'[SSL] 使用现有证书: {cert}')
        return cert, key
    try:
        import subprocess
        subprocess.run([
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
            '-keyout', key, '-out', cert, '-days', '3650',
            '-nodes', '-subj', '/CN=SMS2Web/O=SMS2Web/C=CN'
        ], check=True, capture_output=True)
        log(f'[SSL] 自签名证书已生成: {cert}')
        return cert, key
    except Exception as e:
        log(f'[SSL] 生成证书失败: {e}')
        return None, None

def _get_ssl_context():
    cfg = _load_config()
    if not cfg.get('ssl_enabled', False):
        return None
    cert = cfg.get('ssl_cert', '')
    key = cfg.get('ssl_key', '')
    if not cert or not key:
        cert, key = _gen_self_signed_cert()
        if cert:
            cfg['ssl_cert'] = os.path.relpath(cert, DATA_DIR)
            cfg['ssl_key'] = os.path.relpath(key, DATA_DIR)
            try:
                with open(os.path.join(DATA_DIR, 'config.json'), 'w') as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
    if not cert or not os.path.isfile(cert):
        log('[SSL] 证书文件缺失，回退到 HTTP')
        return None
    if not key or not os.path.isfile(key):
        log('[SSL] 密钥文件缺失，回退到 HTTP')
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ctx.load_cert_chain(cert, key)
    except Exception as e:
        log(f'[SSL] 证书加载失败 ({e})，尝试重新生成...')
        cert, key = _gen_self_signed_cert()
        if not cert:
            log('[SSL] 证书生成失败，回退到 HTTP')
            return None
        ctx.load_cert_chain(cert, key)
        cfg['ssl_cert'] = os.path.relpath(cert, DATA_DIR)
        cfg['ssl_key'] = os.path.relpath(key, DATA_DIR)
        try:
            with open(os.path.join(DATA_DIR, 'config.json'), 'w') as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    log('[SSL] HTTPS 已启用')
    return ctx

def _wrap_ssl(server, ctx):
    if ctx:
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    return server

def _rotate_security_path():
    cfg_path = os.path.join(DATA_DIR, 'config.json')
    try:
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                cfg = json.load(f)
        else:
            cfg = {}
        new_path = '/' + ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))
        cfg['security_path'] = new_path
        with open(cfg_path, 'w') as f:
            json.dump(cfg, f, indent=2)
        proto = 'https' if SSL_ACTIVE else 'http'
        lan_ip = get_lan_ip()
        public_ip = get_public_ip()
        log(f'[安全] 安全入口已轮换: {new_path}')
        log(f'[安全] 管理后台:')
        log(f'[安全]   内网: {proto}://{lan_ip}:{ADMIN_PORT}{new_path}/console.html')
        if public_ip:
            log(f'[安全]   公网: {proto}://{public_ip}:{ADMIN_PORT}{new_path}/console.html')
        log('[安全] 旧入口已失效')
    except Exception as e:
        log(f'[安全] 安全入口轮换失败: {e}')

def _security_path_rotator():
    while True:
        time.sleep(86400)
        _rotate_security_path()

def run_server():
    global USER_PORT, ADMIN_PORT, _admin_creds

    # tracer.start_trace()

    print('[检测] 正在执行环境与安全检测...')
    env_ok, sec_issues = check_env.run_all_checks()
    if not env_ok:
        print('\n[错误] 环境检测未通过，请修复后重试')
        sys.exit(1)
    if sec_issues > 0:
        print(f'\n[警告] 发现 {sec_issues} 个安全问题，建议修复后继续')
    print('[检测] 通过，启动服务器...\n')

    _load_language()

    for sub in ('public', 'server', 'plugins'):
        p = os.path.join(MOD_DIR, sub)
        if not os.path.isdir(p):
            try:
                os.makedirs(p, exist_ok=True)
            except Exception:
                pass
    _load_mod_manifests()
    _mod_files = []
    for root, _, files in os.walk(MOD_DIR):
        for f in files:
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, MOD_DIR)
            lang = _detect_language(f)
            _mod_files.append({'path': rel, 'language': lang, 'size': os.path.getsize(fp), 'mtime': os.path.getmtime(fp)})
    if _mod_files:
        print(f'  [Mod] 检测到 {len(_mod_files)} 个 mod 文件')
        for mf in _mod_files:
            print(f'    {mf["path"]} ({mf["language"]})')
        priorities = _load_mod_priorities()
        for mf in _mod_files:
            if mf['path'].startswith('public/'):
                builtin_path = os.path.join(PUBLIC_DIR, mf['path'][7:])
                if os.path.isfile(builtin_path):
                    rel_path = mf['path']
                    if rel_path not in priorities:
                        log(f'[冲突] {rel_path} 与内置文件冲突')
                        log(f'  默认使用 mod 版本（内置版本被覆盖）')
                        try:
                            prio = input(f'  [?] 使用哪个? (mod/builtin) [mod]: ').strip().lower()
                        except (EOFError, OSError):
                            prio = 'mod'
                        if prio in ('builtin', 'b', 'built-in'):
                            _set_mod_priority(rel_path, 'builtin')
                            log(f'[优先] {rel_path} → 使用内置版本')
                        else:
                            _set_mod_priority(rel_path, 'mod')
                            log(f'[优先] {rel_path} → 使用 mod 版本')
        seen = {}
        for mf in _mod_files:
            if mf['path'].startswith('public/'):
                base = mf['path'][7:]
                if base in seen:
                    log(f'[冲突] 多个 mod 文件提供相同的路径: {mf["path"]} 和 {seen[base]}')
                    if mf['path'] not in priorities:
                        try:
                            chosen = input(f'  [?] 使用哪个? ({mf["path"]} / {seen[base]}) [{os.path.basename(seen[base])}]: ').strip()
                        except (EOFError, OSError):
                            chosen = ''
                        if chosen == mf['path']:
                            _set_mod_priority(mf['path'], 'mod')
                            _set_mod_priority(seen[base], 'disabled')
                            log(f'[优先] {mf["path"]} 启用, {seen[base]} 禁用')
                        elif chosen:
                            _set_mod_priority(seen[base], 'mod')
                            _set_mod_priority(mf['path'], 'disabled')
                            log(f'[优先] {seen[base]} 启用, {mf["path"]} 禁用')
                seen[base] = mf['path']
    sys.path.insert(0, os.path.join(MOD_DIR, 'server'))

    def _parse_env_port(key):
        try:
            return int(os.environ.get(key, 0))
        except (ValueError, TypeError):
            return 0

    USER_PORT = _parse_env_port('FORCE_USER_PORT') or find_available_port()
    ADMIN_PORT = _parse_env_port('FORCE_ADMIN_PORT') or find_available_port()
    while ADMIN_PORT == USER_PORT:
        ADMIN_PORT = find_available_port()

    global USER_DOMAIN, ADMIN_DOMAIN, IP_WHITELIST, REGISTRATION_ENABLED, DAILY_SMS_LIMIT
    cfg = _load_config()
    USER_DOMAIN = cfg.get('user_domain', '') or ''
    ADMIN_DOMAIN = cfg.get('admin_domain', '') or ''
    IP_WHITELIST = cfg.get('ip_whitelist', '') or ''
    REGISTRATION_ENABLED = cfg.get('registration_enabled', True)
    DAILY_SMS_LIMIT = int(cfg.get('daily_sms_limit', 0))

    lan_ip = get_lan_ip()
    public_ip = get_public_ip()
    _admin_creds = generate_admin(ADMIN_PORT, lan_ip, public_ip)
    _load_managers(default_creds=_admin_creds)
    _load_reports()

    def _cleanup(signum, frame):
        log(f'[信号] 收到信号 {signum}，正在清理...')
        _stop_daemon()
        sys.exit(0)
    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    print('[守护进程] 正在启动短信处理引擎...')
    _start_daemon(exit_on_fail=True)
    health_thread = threading.Thread(target=_daemon_health_loop, daemon=True)
    health_thread.start()

    cfg = _load_config()
    if cfg.get('security_path'):
        log(f'[安全] 安全入口已启用: {cfg["security_path"]}')
        log('[安全] 每 24 小时自动轮换')
        rotator = threading.Thread(target=_security_path_rotator, daemon=True)
        rotator.start()

    try:
        ctx = _get_ssl_context()
        SSL_ACTIVE = ctx is not None
        user_server = _wrap_ssl(http.server.ThreadingHTTPServer(('0.0.0.0', USER_PORT), UserHandler), ctx)
        admin_server = _wrap_ssl(http.server.HTTPServer(('0.0.0.0', ADMIN_PORT), AdminHandler), ctx)
    except OSError as e:
        log(f'[错误] 端口绑定失败: {e}')
        sys.exit(1)

    user_thread = threading.Thread(target=user_server.serve_forever, daemon=True)
    admin_thread = threading.Thread(target=admin_server.serve_forever, daemon=True)

    log('=' * 45)
    log('  短 信 转 网 页  —  系 统 已 启 动')
    log('=' * 45)
    log(f'  【内网IP】{lan_ip}')
    if public_ip:
        log(f'  【公网IP】{public_ip}')
    if USER_DOMAIN:
        log(f'  【用户域名】{USER_DOMAIN}')
    if ADMIN_DOMAIN:
        log(f'  【管理域名】{ADMIN_DOMAIN}')
    proto = 'https' if ctx else 'http'
    log(f'  【用户端】端口: {USER_PORT}')
    log(f'    内网首页:  {proto}://{lan_ip}:{USER_PORT}')
    log(f'    内网登录:  {proto}://{lan_ip}:{USER_PORT}/login.html')
    log(f'    内网注册:  {proto}://{lan_ip}:{USER_PORT}/register.html')
    if USER_DOMAIN:
        log(f'    用户域名:  {proto}://{USER_DOMAIN}')
    if public_ip:
        log(f'    公网首页:  {proto}://{public_ip}:{USER_PORT}')
        log(f'    公网登录:  {proto}://{public_ip}:{USER_PORT}/login.html')
        log(f'    公网注册:  {proto}://{public_ip}:{USER_PORT}/register.html')
    log(f'  【管理台】端口: {ADMIN_PORT}')
    log(f'    内网管理:  {proto}://{lan_ip}:{ADMIN_PORT}/console.html')
    if ADMIN_DOMAIN:
        log(f'    管理域名:  {proto}://{ADMIN_DOMAIN}')
    if public_ip:
        log(f'    公网管理:  {proto}://{public_ip}:{ADMIN_PORT}/console.html')
    pwd = _admin_creds['password']
    masked = pwd[:2] + '*' * (len(pwd) - 4) + pwd[-2:]
    log(f'    用户名:    {_admin_creds["username"]}')
    log(f'    密  码:    {masked}')
    log(f'    凭证文件:  data/admin_credentials.txt（含完整密码）')
    log('-' * 45)

    user_thread.start()
    admin_thread.start()
    if sys.stdin.isatty():
        cli_thread = threading.Thread(target=_cli_thread, daemon=True)
        cli_thread.start()
    daemon_port = ''
    try:
        djson = os.path.join(DATA_DIR, 'daemon.json')
        if os.path.exists(djson):
            with open(djson) as f:
                dd = json.load(f)
            daemon_port = str(dd.get('port', ''))
    except Exception:
        pass
    server_info = {
        'user_port': USER_PORT, 'admin_port': ADMIN_PORT,
        'daemon_port': daemon_port,
        'lan_ip': lan_ip, 'public_ip': public_ip or '',
        'user_domain': USER_DOMAIN or '',
        'admin_domain': ADMIN_DOMAIN or '',
        'protocol': proto,
        'username': _admin_creds['username'],
        'ssl_enabled': ctx is not None,
        'started_at': int(time.time()),
        'status': 'running'
    }
    try:
        with open(os.path.join(DATA_DIR, 'server_info.json'), 'w') as f:
            json.dump(server_info, f, indent=2)
        os.chmod(os.path.join(DATA_DIR, 'server_info.json'), 0o600)
    except Exception:
        pass
    daemon_status = '在线' if _daemon_online else '离线'
    log(f'[就绪] 面板+守护进程({daemon_status}) 已启动，等待请求...')

    try:
        while _running:
            time.sleep(1)
    except KeyboardInterrupt:
        log('\n[关闭] 正在关闭服务器...')
        _stop_daemon()
        user_server.shutdown()
        admin_server.shutdown()
        db_close()
        log('[关闭] 已安全退出')
        sys.exit(0)

if __name__ == '__main__':
    run_server()
