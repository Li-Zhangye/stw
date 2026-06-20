import os
import hashlib
import hmac
import secrets

DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
NOTE_PATH = os.path.join(DATA_DIR, 'admin_credentials.txt')

def _generate_complex():
    upper = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    lower = 'abcdefghijklmnopqrstuvwxyz'
    digits = '0123456789'
    special = '!@#$%^&*()_+-=[]{}|;:,.<>?/~'
    all_chars = upper + lower + digits + special
    return ''.join(secrets.choice(all_chars) for _ in range(20))

def generate_admin(port, lan_ip='localhost', public_ip=None):
    username = _generate_complex()
    password = _generate_complex()
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'),
        salt.encode('utf-8'), 600000
    ).hex()
    stored = salt + ':' + pwd_hash

    lines = [
        '============================================',
        '  短信转网页 - 管理控制台账号信息',
        '  本组账号仅本次启动有效，重启后失效',
        '============================================',
        f'  内网管理: https://{lan_ip}:{port}/console.html',
    ]
    if public_ip:
        lines.append(f'  公网管理: https://{public_ip}:{port}/console.html')
    lines += [
        f'  用户名: {username}',
        f'  密  码: {password}',
        '============================================',
        '  请妥善保管此信息！',
        '  此文件包含明文密码，请勿泄露！',
        '  重启服务器后账号将自动更换',
        '============================================',
    ]
    content = '\n'.join(lines) + '\n'

    os.makedirs(os.path.dirname(NOTE_PATH), mode=0o700, exist_ok=True)
    with open(NOTE_PATH, 'w') as f:
        f.write(content)
    os.chmod(NOTE_PATH, 0o600)

    masked = password[:2] + '*' * (len(password) - 4) + password[-2:]
    print('=' * 50)
    print('  管理控制台账号（每次启动随机生成）')
    print(f'  内网管理: https://{lan_ip}:{port}/console.html')
    if public_ip:
        print(f'  公网管理: https://{public_ip}:{port}/console.html')
    print(f'  用户名: {username}')
    print(f'  密码:   {masked}')
    print('  已保存到: data/admin_credentials.txt（含完整密码）')
    print('  提示: 重启服务器后账号将自动更换')
    print('=' * 50)

    return {'username': username, 'password': password, 'password_hash': stored}

def verify_admin(username, password, creds):
    if not creds or username != creds.get('username'):
        return False
    stored = creds.get('password_hash', '')
    if ':' in stored:
        salt, pwd_hash = stored.split(':', 1)
    else:
        salt = creds['username']
        pwd_hash = stored
    computed = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'),
        salt.encode('utf-8'), 600000
    ).hex()
    return hmac.compare_digest(computed, pwd_hash)
