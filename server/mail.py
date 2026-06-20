import os
import json
import smtplib
import ssl
import email.utils
from email.mime.text import MIMEText

DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
CONFIG_PATH = os.path.join(DATA_DIR, 'mail_config.json')

SMTP_HOST = ''
SMTP_PORT = 465
FROM_ADDR = ''
FROM_NAME = '短信转网页'
SMTP_USER = ''
SMTP_PASS = ''
SMTP_TLS = True
SMTP_VERIFY_SSL = True

def _to_int(val, default):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def _load_config():
    global SMTP_HOST, SMTP_PORT, FROM_ADDR, FROM_NAME, SMTP_USER, SMTP_PASS, SMTP_TLS, SMTP_VERIFY_SSL

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
            SMTP_HOST = cfg.get('host', SMTP_HOST)
            SMTP_PORT = _to_int(cfg.get('port', SMTP_PORT), SMTP_PORT)
            SMTP_USER = cfg.get('user', SMTP_USER)
            SMTP_PASS = cfg.get('pass', SMTP_PASS)
            SMTP_TLS = cfg.get('tls', SMTP_TLS)
            SMTP_VERIFY_SSL = cfg.get('verify_ssl', SMTP_VERIFY_SSL)
            FROM_ADDR = cfg.get('from_addr', FROM_ADDR)
            FROM_NAME = cfg.get('from_name', FROM_NAME)
        except Exception:
            pass

    if os.environ.get('SMTP_HOST'):     SMTP_HOST = os.environ['SMTP_HOST']
    if os.environ.get('SMTP_PORT'):     SMTP_PORT = _to_int(os.environ['SMTP_PORT'], SMTP_PORT)
    if os.environ.get('SMTP_USER'):     SMTP_USER = os.environ['SMTP_USER']
    if os.environ.get('SMTP_PASS'):     SMTP_PASS = os.environ['SMTP_PASS']
    if os.environ.get('SMTP_TLS'):      SMTP_TLS = os.environ['SMTP_TLS'] == '1'
    if os.environ.get('FROM_ADDR'):     FROM_ADDR = os.environ['FROM_ADDR']
    if os.environ.get('FROM_NAME'):     FROM_NAME = os.environ['FROM_NAME']

def save_config(host, port, user, password, from_addr, from_name, use_tls, verify_ssl=True):
    cfg = {
        'host': host,
        'port': int(port),
        'user': user,
        'pass': password,
        'from_addr': from_addr,
        'from_name': from_name,
        'tls': use_tls,
        'verify_ssl': verify_ssl
    }
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, ensure_ascii=False)
    os.chmod(CONFIG_PATH, 0o600)
    print(f'[邮件] 配置已保存: {host}:{port}')
    _load_config()

def send_mail(to_addr, subject, html_content):
    _load_config()
    try:
        msg = MIMEText(html_content, 'html', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = email.utils.formataddr((FROM_NAME, FROM_ADDR))
        msg['To'] = to_addr
        msg['Date'] = email.utils.formatdate()

        if SMTP_USER and SMTP_PASS:
            if SMTP_TLS and SMTP_PORT == 465:
                ctx = ssl.create_default_context()
                if not SMTP_VERIFY_SSL:
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15, context=ctx) as server:
                    server.login(SMTP_USER, SMTP_PASS)
                    server.sendmail(FROM_ADDR, [to_addr], msg.as_string())
            else:
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                    if SMTP_TLS:
                        ctx = ssl.create_default_context()
                        if not SMTP_VERIFY_SSL:
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                        server.starttls(context=ctx)
                    server.login(SMTP_USER, SMTP_PASS)
                    server.sendmail(FROM_ADDR, [to_addr], msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                server.sendmail(FROM_ADDR, [to_addr], msg.as_string())

        print(f'[邮件] 发送成功 -> {to_addr}')
        return {'success': True}
    except ssl.SSLCertVerificationError as e:
        hint = f'SSL证书验证失败（提示：Termux请执行 pkg install ca-certificates 后重试）'
        if not SMTP_VERIFY_SSL:
            hint = f'SSL证书验证失败，且已关闭验证，请检查网络或SMTP配置'
        print(f'[邮件] SSL错误 -> {to_addr}: {e}')
        return {'success': False, 'error': f'{hint}: {e}'}
    except Exception as e:
        print(f'[邮件] 发送失败 -> {to_addr}: {e}')
        return {'success': False, 'error': str(e)}

def send_verification_code(email, code, verify_url):
    html = f'''
    <div style="max-width:600px;margin:0 auto;font-family:Arial,sans-serif;padding:20px;border:1px solid #ddd;border-radius:8px;">
      <h2 style="color:#333;">验证您的邮箱</h2>
      <p style="font-size:16px;color:#555;">您的验证码为：</p>
      <div style="text-align:center;padding:15px;margin:15px 0;background:#f5f5f5;border-radius:6px;">
        <span style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#1a73e8;">{code}</span>
      </div>
      <p style="font-size:14px;color:#777;">验证码有效期为1分钟</p>
      <p style="font-size:14px;color:#777;">或点击下方链接完成验证：</p>
      <div style="text-align:center;margin:20px 0;">
        <a href="{verify_url}" style="display:inline-block;padding:12px 30px;background:#1a73e8;color:#fff;text-decoration:none;border-radius:6px;font-size:16px;">确认验证</a>
      </div>
      <p style="font-size:12px;color:#999;">如果这不是您本人的操作，请忽略此邮件</p>
    </div>
    '''
    return send_mail(email, '验证您的邮箱 - 短信转网页', html)

def send_login_code(email, code):
    html = f'''
    <div style="max-width:600px;margin:0 auto;font-family:Arial,sans-serif;padding:20px;border:1px solid #ddd;border-radius:8px;">
      <h2 style="color:#333;">登录验证码</h2>
      <p style="font-size:16px;color:#555;">您的登录验证码为：</p>
      <div style="text-align:center;padding:15px;margin:15px 0;background:#f5f5f5;border-radius:6px;">
        <span style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#1a73e8;">{code}</span>
      </div>
      <p style="font-size:14px;color:#777;">验证码有效期为1分钟</p>
      <p style="font-size:12px;color:#999;">如果这不是您本人的操作，请忽略此邮件</p>
    </div>
    '''
    return send_mail(email, '登录验证码 - 短信转网页', html)
