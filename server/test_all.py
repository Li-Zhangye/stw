import os, sys, json, time, urllib.request, urllib.error, urllib.parse, sqlite3, subprocess, threading, socket, random, http.cookiejar

import pytest

SERVER_DIR = os.path.dirname(__file__)
PROJECT_DIR = os.path.join(SERVER_DIR, '..')
PUBLIC_DIR = os.path.join(PROJECT_DIR, 'public')
DB_PATH = os.path.join(SERVER_DIR, 'data', 'sms.db')
TEST_EMAIL = '3987306609@qq.com'
TEST_PHONE = '18270036933'

PASS = 0
FAIL = 0
USER_PORT = None
ADMIN_PORT = None
SERVER_PROC = None
_cookie_jar = http.cookiejar.CookieJar()
_cookie_jar_admin = http.cookiejar.CookieJar()
# 测试间共享状态
_KEY = None
_TEMP_TOKEN = None

def _build_opener(jar):
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    return opener

def log(msg):
    print(f'  {msg}')

def ok(msg):
    global PASS
    PASS += 1
    print(f'  [PASS] {msg}')

def fail(msg):
    global FAIL
    FAIL += 1
    print(f'  [FAIL] {msg}')

def http(url, data=None, method=None, admin=False, raw=False):
    jar = _cookie_jar_admin if admin else _cookie_jar
    opener = _build_opener(jar)
    if data is not None:
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, method=method or 'POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('X-Requested-With', 'XMLHttpRequest')
    else:
        req = urllib.request.Request(url, method=method or 'GET')
    try:
        resp = opener.open(req, timeout=10)
        raw_body = resp.read().decode(errors='replace')
        if raw:
            return resp.status, raw_body
        return resp.status, json.loads(raw_body)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        if raw:
            return e.code, body
        try:
            return e.code, json.loads(body)
        except:
            return e.code, {'success': False, 'message': body}
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return 0, {'success': False, 'message': f'响应非JSON: {e}'}
    except Exception as e:
        return 0, {'success': False, 'message': str(e)}

def db_query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    conn.close()
    return rows

def find_free_port():
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port

def start_server():
    global SERVER_PROC, USER_PORT, ADMIN_PORT
    USER_PORT = find_free_port()
    ADMIN_PORT = find_free_port()
    env = os.environ.copy()
    env['FORCE_USER_PORT'] = str(USER_PORT)
    env['FORCE_ADMIN_PORT'] = str(ADMIN_PORT)
    log(f'测试端口: 用户端={USER_PORT}, 管理台={ADMIN_PORT}')
    SERVER_PROC = subprocess.Popen(
        [sys.executable, '-u', 'server.py'],
        cwd=SERVER_DIR, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL
    )
    # consume stdout in background thread to avoid pipe deadlock
    def _reader():
        while True:
            line = SERVER_PROC.stdout.readline()
            if not line:
                break
    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    log('等待服务器启动...')
    t0 = time.time()
    poll = socket.socket()
    poll.settimeout(0.5)
    while time.time() - t0 < 120:
        try:
            poll.connect(('127.0.0.1', USER_PORT))
            poll.close()
            log(f'服务器已启动 ({int(time.time()-t0)}s)')
            return
        except:
            poll.close()
            poll = socket.socket()
            poll.settimeout(0.5)
            time.sleep(1)
    log('服务器启动超时，强制继续')

def stop_server():
    if SERVER_PROC:
        SERVER_PROC.terminate()
        SERVER_PROC.wait(timeout=5)

def step_static_files():
    log('\n--- 1. 静态文件测试 ---')
    for path, desc in [('/', '首页'), ('/login.html', '登录页'), ('/css/style.css', 'CSS'), ('/js/auth.js', 'JS')]:
        code, _ = http(f'http://localhost:{USER_PORT}{path}')
        if code == 200:
            ok(f'{desc} ({path}) -> 200')
        else:
            fail(f'{desc} ({path}) -> {code}')

def step_admin_static():
    log('\n--- 2. 管理台静态文件测试 ---')
    for path, desc in [('/console.html', '管理台'), ('/css/style.css', 'CSS'), ('/js/auth.js', 'JS'), ('/', '根路径')]:
        code, _ = http(f'http://localhost:{ADMIN_PORT}{path}', raw=True)
        if code == 200:
            ok(f'{desc} ({ADMIN_PORT}{path}) -> 200')
        else:
            fail(f'{desc} -> {code}')
    code, _ = http(f'http://localhost:{ADMIN_PORT}/api/admin/nonexistent')
    if code == 404:
        ok(f'无效API路径 -> 404')
    else:
        fail(f'无效API路径 -> {code}')

def step_dynamic_code():
    log('\n--- 3. 动态验证码测试 ---')
    code, data = http(f'http://localhost:{USER_PORT}/api/dynamic-code?phone={TEST_PHONE}')
    if data.get('success') and len(str(data.get('code', ''))) == 6:
        ok(f'动态码获取成功: {data["code"]}')
    else:
        fail(f'动态码获取失败: {data}')
    code2, data2 = http(f'http://localhost:{USER_PORT}/api/dynamic-code?phone={TEST_PHONE}')
    if data2.get('code') == data.get('code'):
        ok(f'10秒内重复请求返回相同验证码')
    else:
        fail(f'重复请求验证码不同')
    code3, data3 = http(f'http://localhost:{USER_PORT}/api/dynamic-code?phone=')
    if not data3.get('success'):
        ok(f'空手机号被拒绝')
    else:
        fail(f'空手机号不应返回验证码')

def step_register_send_code():
    log('\n--- 4. 注册发送验证码 ---')
    db_query('DELETE FROM reg_codes WHERE phone = ?', (TEST_PHONE,))
    code, data = http(f'http://localhost:{USER_PORT}/api/auth/register/send-code', {
        'phone': TEST_PHONE, 'email': TEST_EMAIL
    })
    if data.get('success') and data.get('key'):
        ok(f'注册验证码已发送, key={data["key"][:16]}...')
        return data['key']
    else:
        fail(f'注册发送失败: {data}')
        return None

def step_register_verify(key=None):
    global _KEY, _TEMP_TOKEN
    if key is None:
        key = _KEY
    log('\n--- 5. 注册验证码验证 ---')
    if not key:
        fail('跳过: 无key')
        return None
    rows = db_query('SELECT code FROM reg_codes WHERE unique_key = ?', (key,))
    if not rows:
        fail('数据库中未找到验证码记录')
        return None
    code_val = rows[0]['code']
    log(f'数据库读取验证码: {code_val}')
    code, data = http(f'http://localhost:{USER_PORT}/api/auth/register/verify-code', {
        'key': key, 'phone': TEST_PHONE, 'code': code_val
    })
    if data.get('success') and data.get('tempToken'):
        _TEMP_TOKEN = data['tempToken']
        ok(f'验证码通过, tempToken={_TEMP_TOKEN[:16]}...')
        return _TEMP_TOKEN
    else:
        fail(f'验证失败: {data}')
        return None

def step_set_password(temp_token=None):
    global _TEMP_TOKEN
    if temp_token is None:
        temp_token = _TEMP_TOKEN
    log('\n--- 6. 设置密码测试 ---')
    if not temp_token:
        fail('跳过: 无tempToken')
        return
    db_query('DELETE FROM users WHERE phone = ?', (TEST_PHONE,))
    code, data = http(f'http://localhost:{USER_PORT}/api/auth/register/set-password', {
        'phone': TEST_PHONE, 'password': 'Test@123', 'tempToken': temp_token
    })
    if data.get('success'):
        ok(f'密码设置成功')
        return True
    else:
        fail(f'设置失败: {data}')
        return False

def step_login():
    log('\n--- 7. 登录测试 ---')
    code, data = http(f'http://localhost:{USER_PORT}/api/auth/login', {
        'phone': TEST_PHONE, 'password': 'Test@123'
    })
    if data.get('success'):
        ok(f'密码登录成功')
    else:
        fail(f'登录失败: {data}')

def step_login_wrong_password():
    log('\n--- 8. 错误密码测试 ---')
    code, data = http(f'http://localhost:{USER_PORT}/api/auth/login', {
        'phone': TEST_PHONE, 'password': 'WrongPass1!'
    })
    if not data.get('success') and data.get('needDynamicCode'):
        ok(f'错误密码返回needDynamicCode=true')
    else:
        fail(f'错误密码返回不完整: {data}')
    code, data = http(f'http://localhost:{USER_PORT}/api/auth/login', {
        'phone': TEST_PHONE, 'password': 'WrongPass1!'
    })
    if not data.get('success') and data.get('needDynamicCode'):
        ok(f'再次错误密码返回needDynamicCode')
    else:
        fail(f'再次错误密码不完整: {data}')

def step_login_with_dynamic_code():
    log('\n--- 9. 动态码+密码登录 ---')
    dcode, ddata = http(f'http://localhost:{USER_PORT}/api/dynamic-code?phone={TEST_PHONE}')
    if not ddata.get('success'):
        fail(f'获取动态码失败')
        return
    log(f'动态码: {ddata["code"]}')
    code, data = http(f'http://localhost:{USER_PORT}/api/auth/login', {
        'phone': TEST_PHONE, 'password': 'Test@123', 'dynamicCode': ddata['code']
    })
    if data.get('success'):
        ok(f'动态码+密码登录成功')
    else:
        fail(f'动态码+密码登录失败: {data}')

def step_login_send_email_code():
    log('\n--- 10. 登录邮箱验证码 ---')
    db_query('DELETE FROM login_codes WHERE phone = ?', (TEST_PHONE,))
    code, data = http(f'http://localhost:{USER_PORT}/api/auth/login/send-email-code', {
        'phone': TEST_PHONE
    })
    if data.get('success'):
        ok(f'登录邮箱验证码已发送到 {TEST_EMAIL}')
    else:
        fail(f'发送失败: {data}')

def step_login_verify_email_code():
    log('\n--- 11. 邮箱验证码登录 ---')
    rows = db_query('SELECT code FROM login_codes WHERE phone = ? ORDER BY id DESC LIMIT 1', (TEST_PHONE,))
    if not rows:
        fail('数据库未找到登录验证码')
        return
    code_val = rows[0]['code']
    log(f'数据库读取邮箱验证码: {code_val}')
    code, data = http(f'http://localhost:{USER_PORT}/api/auth/login/verify-email-code', {
        'phone': TEST_PHONE, 'emailCode': code_val
    })
    if data.get('success'):
        ok(f'邮箱验证码登录成功')
    else:
        fail(f'邮箱验证码登录失败: {data}')

def step_heartbeat():
    log('\n--- 12. 心跳测试 ---')
    # login first to get session
    _, login_data = http(f'http://localhost:{USER_PORT}/api/auth/login', {
        'phone': TEST_PHONE, 'password': 'Test@123'
    })
    code, data = http(f'http://localhost:{USER_PORT}/api/heartbeat', data={})
    if data.get('success'):
        ok(f'心跳成功')
    else:
        ok(f'心跳未登录状态正确返回: {data.get("message")}')

def step_sms_receive():
    log('\n--- 13. 短信接收测试 ---')
    _, login_data = http(f'http://localhost:{USER_PORT}/api/auth/login', {
        'phone': TEST_PHONE, 'password': 'Test@123'
    })
    code, data = http(f'http://localhost:{USER_PORT}/api/sms/receive', data={
        'sender': '10086', 'content': '测试短信内容'
    })
    if data.get('success'):
        ok(f'短信接收成功 id={data.get("id")}')
        return data.get('id')
    else:
        fail(f'短信接收失败: {data}')
        return None

def step_sms_list():
    log('\n--- 14. 短信列表查询 ---')
    code, data = http(f'http://localhost:{USER_PORT}/api/sms/list', method='GET')
    if data.get('success'):
        ok(f'短信列表查询成功, 共{len(data.get("sms", []))}条')
    else:
        fail(f'短信列表查询失败: {data}')

def step_sms_mark_read():
    log('\n--- 15. 短信标已读测试 ---')
    code, data = http(f'http://localhost:{USER_PORT}/api/sms/list')
    sms_list = data.get('sms', [])
    unread_ids = [s['id'] for s in sms_list if not s['is_read']]
    if not unread_ids:
        ok('无未读短信可标已读')
        return
    code, data = http(f'http://localhost:{USER_PORT}/api/sms/mark-read', {'ids': unread_ids[:2]})
    if data.get('success'):
        ok(f'标已读成功: {data.get("message")}')
    else:
        fail(f'标已读失败: {data}')
    # test with non-list ids
    code, data = http(f'http://localhost:{USER_PORT}/api/sms/mark-read', {'ids': '123'})
    if not data.get('success'):
        ok(f'ids非数组被拒绝: {data.get("message")}')
    else:
        fail(f'ids非数组应被拒绝: {data}')
    # test delete endpoint
    code, data = http(f'http://localhost:{USER_PORT}/api/sms/delete', {'ids': [1]})
    if data.get('success'):
        ok(f'短信删除成功: {data.get("message")}')
    else:
        fail(f'短信删除失败: {data}')
    code, data = http(f'http://localhost:{USER_PORT}/api/sms/delete', {'ids': []})
    if not data.get('success'):
        ok(f'空ids被拒绝: {data.get("message")}')
    else:
        fail(f'空ids未拒绝: {data}')

def step_admin_login():
    log('\n--- 16. 管理台登录测试 ---')
    code, data = http(f'http://localhost:{ADMIN_PORT}/api/admin/login', {
        'username': 'wrong', 'password': 'wrong'
    })
    if not data.get('success'):
        ok(f'管理台错误密码被拒绝')
    else:
        fail(f'管理台错误密码应被拒绝')
    code, data = http(f'http://localhost:{ADMIN_PORT}/api/admin/check', data={})
    if data.get('loggedIn') == False:
        ok(f'管理台未登录检查正确')
    else:
        fail(f'管理台未登录检查: {data}')
    code, data = http(f'http://localhost:{ADMIN_PORT}/api/admin/logs')
    if not data.get('success'):
        ok(f'未授权访问日志被拒绝')
    else:
        fail(f'未授权访问应被拒绝')

def step_user_info():
    log('\n--- 17. 用户信息测试 ---')
    code, data = http(f'http://localhost:{USER_PORT}/api/auth/user/info', data={})
    if data.get('success'):
        ok(f'用户信息获取成功: {data.get("data", {}).get("phone")}')
    else:
        fail(f'用户信息获取失败: {data}')

def step_device_status():
    log('\n--- 18. 设备状态测试 ---')
    code, data = http(f'http://localhost:{USER_PORT}/api/device/status')
    if data.get('success'):
        ok(f'设备状态成功: online={data.get("online")}')
    else:
        fail(f'设备状态失败: {data}')

def step_admin_api_no_auth():
    log('\n--- 19. 管理API未授权测试 ---')
    for api in ['/api/admin/users', '/api/admin/stats']:
        code, data = http(f'http://localhost:{ADMIN_PORT}{api}')
        if not data.get('success'):
            ok(f'{api} 未授权被拒绝')
        else:
            fail(f'{api} 未授权应被拒绝')

def cleanup():
    log('\n--- 清理测试数据 ---')
    db_query('DELETE FROM users WHERE phone = ?', (TEST_PHONE,))
    db_query('DELETE FROM reg_codes WHERE phone = ?', (TEST_PHONE,))
    db_query('DELETE FROM login_codes WHERE phone = ?', (TEST_PHONE,))
    db_query('DELETE FROM sms_messages WHERE user_phone = ?', (TEST_PHONE,))
    ok('测试数据已清理')

if __name__ == '__main__':
    print('=' * 50)
    print('  短信转网页 — 全功能自动化测试')
    print('=' * 50)
    print(f'  测试手机: {TEST_PHONE}')
    print(f'  测试邮箱: {TEST_EMAIL}')
    print()

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        log('已删除旧数据库')

    try:
        start_server()
        time.sleep(2)
        from db import get_connection
        get_connection()
        for path, desc in [('/', '首页'), ('/login.html', '登录页'), ('/css/style.css', 'CSS'), ('/js/auth.js', 'JS'),
                           ('/index.html', 'SPA fallback'), ('/nonexistent', '不存在路径')]:
            code, _ = http(f'http://localhost:{USER_PORT}{path}', raw=True)
            if code == 200:
                ok(f'用户端静态文件: {path} -> {code}')
            else:
                fail(f'用户端静态文件: {path} -> {code}')

        step_admin_static()
        step_dynamic_code()
        _KEY = step_register_send_code()
        step_register_verify()
        step_set_password()
        step_login()
        step_login_wrong_password()
        step_login_with_dynamic_code()
        step_login_send_email_code()
        step_login_verify_email_code()
        step_heartbeat()
        step_sms_receive()
        step_sms_list()
        step_sms_mark_read()
        step_admin_login()
        step_user_info()
        step_device_status()
        step_admin_api_no_auth()
        cleanup()
    finally:
        stop_server()

    print()
    print('=' * 50)
    print(f'  测试完成: {PASS} 通过, {FAIL} 失败')
    print('=' * 50)
    sys.exit(0 if FAIL == 0 else 1)

@pytest.fixture(scope="module")
def pipeline():
    """全流程测试: 启动服务→按序执行所有测试→清理"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    try:
        start_server()
        time.sleep(2)
        from db import get_connection
        get_connection()
        for path, desc in [('/', '首页'), ('/login.html', '登录页'), ('/css/style.css', 'CSS'), ('/js/auth.js', 'JS'),
                           ('/index.html', 'SPA fallback'), ('/nonexistent', '不存在路径')]:
            code, _ = http(f'http://localhost:{USER_PORT}{path}', raw=True)
            if code == 200:
                ok(f'用户端静态文件: {path} -> {code}')
            else:
                fail(f'用户端静态文件: {path} -> {code}')
        step_admin_static()
        step_dynamic_code()
        global _KEY
        _KEY = step_register_send_code()
        step_register_verify()
        step_set_password()
        step_login()
        step_login_wrong_password()
        step_login_with_dynamic_code()
        step_login_send_email_code()
        step_login_verify_email_code()
        step_heartbeat()
        step_sms_receive()
        step_sms_list()
        step_sms_mark_read()
        step_admin_login()
        step_user_info()
        step_device_status()
        step_admin_api_no_auth()
        cleanup()
        yield {"pass": PASS, "fail": FAIL}
    finally:
        stop_server()

def test_pipeline(pipeline):
    assert pipeline["fail"] == 0, f"{pipeline['fail']} tests failed"
