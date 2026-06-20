import re
import secrets
import hashlib
import hmac
import string

PHONE_REGEX = re.compile(r'^1[3-9]\d{9}$')
EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

def is_valid_phone(phone):
    return bool(PHONE_REGEX.match(phone))

def is_valid_email(email):
    return bool(EMAIL_REGEX.match(email))

def is_valid_password(password):
    if not password or len(password) < 8 or len(password) > 32:
        return False
    has_digit = bool(re.search(r'[0-9]', password))
    has_lower = bool(re.search(r'[a-z]', password))
    has_upper = bool(re.search(r'[A-Z]', password))
    has_special = bool(re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:\'",.<>?/~`]', password))
    return has_digit and has_lower and has_upper and has_special

def get_password_error():
    return '密码必须包含数字、大小写字母、特殊符号，长度8-32位'

def generate_code(length=6):
    return ''.join(secrets.choice(string.digits) for _ in range(length))

def generate_key():
    return secrets.token_hex(32)

def hash_password(password):
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 600000)
    return salt + ':' + pwd_hash.hex()

def check_password(password, stored):
    salt, pwd_hash = stored.split(':', 1)
    computed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 600000)
    return hmac.compare_digest(computed.hex(), pwd_hash)

def sanitize_html(text):
    if not isinstance(text, str):
        return ''
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#x27;')
