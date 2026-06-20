import os
import sys
import subprocess
import shutil
import platform
import importlib.util
import re
import stat
import argparse

RED = '\033[91m'
RESET = '\033[0m'

def log_ok(msg):
    print(f'  [PASS] {msg}')

def log_fail(msg):
    print(f'  {RED}[FAIL]{RESET} {msg}')

def log_warn(msg):
    print(f'  [!] {msg}')

def log_info(msg):
    print(f'  [i] {msg}')

def log_title(msg):
    print(f'\n{msg}')
    print('-' * 50)

def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return False, '', 'command not found'
    except subprocess.TimeoutExpired:
        return False, '', 'timeout'

def ask_yes_no(prompt):
    while True:
        a = input(f'{prompt} (yes/no): ').strip().lower()
        if a in ('yes', 'y'):
            return True
        if a in ('no', 'n'):
            return False
        print('  请输入 yes 或 no')

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SERVER_DIR)
PUBLIC_DIR = os.path.join(PROJECT_DIR, 'public')
MOBILE_DIR = os.path.join(PROJECT_DIR, 'mobile', 'SmsToWeb')

DETECTED_OS = 'unknown'
OS_FAMILY = 'unknown'
PKG_MANAGER = None
PKG_INSTALL_CMD = None
PKG_UPDATE_CMD = None

FINDINGS = []

def add_finding(severity, category, message, fix=''):
    FINDINGS.append({'s': severity, 'c': category, 'm': message, 'f': fix})

def detect_os():
    global DETECTED_OS, OS_FAMILY, PKG_MANAGER, PKG_INSTALL_CMD, PKG_UPDATE_CMD

    log_title('1. 检测操作系统')

    system = platform.system().lower()
    is_termux = 'com.termux' in os.environ.get('HOME', '') or os.path.exists('/data/data/com.termux')

    if is_termux:
        DETECTED_OS = 'termux'
        OS_FAMILY = 'termux'
        PKG_MANAGER = 'pkg'
        PKG_INSTALL_CMD = ['pkg', 'install', '-y']
        PKG_UPDATE_CMD = ['pkg', 'update']
        log_ok(f'系统: Termux on Android ({platform.machine()})')
        return

    distro_id = ''
    distro_version = ''
    distro_pretty = ''
    os_release_paths = ['/etc/os-release', '/usr/lib/os-release']
    for p in os_release_paths:
        if os.path.exists(p):
            try:
                with open(p, 'r') as fh:
                    for line in fh:
                        line = line.strip()
                        if line.startswith('ID='):
                            distro_id = line.split('=', 1)[1].strip().strip('"').strip("'")
                        elif line.startswith('VERSION_ID='):
                            distro_version = line.split('=', 1)[1].strip().strip('"').strip("'")
                        elif line.startswith('PRETTY_NAME='):
                            distro_pretty = line.split('=', 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass
            if distro_id:
                break

    if not distro_pretty and os.path.exists('/etc/lsb-release'):
        try:
            with open('/etc/lsb-release', 'r') as fh:
                for line in fh:
                    if line.startswith('DISTRIB_DESCRIPTION='):
                        distro_pretty = line.split('=', 1)[1].strip().strip('"')
        except Exception:
            pass

    if system == 'linux':
        DETECTED_OS = 'linux'

        if os.path.exists('/etc/debian_version'):
            if distro_id in ('ubuntu', 'linuxmint', 'elementary', 'pop', 'zorin', 'kali', 'parrot', 'raspbian'):
                OS_FAMILY = 'debian'
            elif distro_id in ('deepin', 'uos', 'kylin'):
                OS_FAMILY = 'debian'
            else:
                OS_FAMILY = 'debian'
            PKG_MANAGER = 'apt'
            PKG_INSTALL_CMD = ['apt', 'install', '-y']
            PKG_UPDATE_CMD = ['apt', 'update']

        elif os.path.exists('/etc/arch-release') or os.path.exists('/etc/pacman.conf'):
            OS_FAMILY = 'arch'
            PKG_MANAGER = 'pacman'
            PKG_INSTALL_CMD = ['pacman', '-S', '--noconfirm']
            PKG_UPDATE_CMD = ['pacman', '-Sy']

        elif (os.path.exists('/etc/redhat-release') or os.path.exists('/etc/centos-release')
              or os.path.exists('/etc/fedora-release') or os.path.exists('/etc/rocky-release')
              or os.path.exists('/etc/almalinux-release')):
            if distro_id == 'fedora':
                OS_FAMILY = 'fedora'
            else:
                OS_FAMILY = 'rhel'
            for c in ('dnf', 'yum'):
                if shutil.which(c):
                    PKG_MANAGER = c
                    PKG_INSTALL_CMD = [c, 'install', '-y']
                    PKG_UPDATE_CMD = [c, 'makecache']
                    break

        elif os.path.exists('/etc/alpine-release'):
            OS_FAMILY = 'alpine'
            PKG_MANAGER = 'apk'
            PKG_INSTALL_CMD = ['apk', 'add']
            PKG_UPDATE_CMD = ['apk', 'update']

        elif os.path.exists('/etc/SuSE-release') or os.path.exists('/etc/products.d/openSUSE.prod'):
            OS_FAMILY = 'suse'
            PKG_MANAGER = 'zypper'
            PKG_INSTALL_CMD = ['zypper', 'install', '-y']
            PKG_UPDATE_CMD = ['zypper', 'refresh']

        elif os.path.exists('/etc/gentoo-release'):
            OS_FAMILY = 'gentoo'
            PKG_MANAGER = 'emerge'
            PKG_INSTALL_CMD = ['emerge', '--ask=n', '-v']
            PKG_UPDATE_CMD = ['emerge', '--sync']

        elif os.path.exists('/etc/void-release') or os.path.exists('/etc/xbps.d'):
            OS_FAMILY = 'void'
            PKG_MANAGER = 'xbps-install'
            PKG_INSTALL_CMD = ['xbps-install', '-y']
            PKG_UPDATE_CMD = ['xbps-install', '-Su']

        elif os.path.exists('/etc/nixos'):
            OS_FAMILY = 'nixos'
            PKG_MANAGER = 'nix-env'
            PKG_INSTALL_CMD = ['nix-env', '-iA']
            PKG_UPDATE_CMD = ['nix-channel', '--update']

        elif os.path.exists('/etc/solus-release'):
            OS_FAMILY = 'solus'
            PKG_MANAGER = 'eopkg'
            PKG_INSTALL_CMD = ['eopkg', 'install', '-y']
            PKG_UPDATE_CMD = ['eopkg', 'upgrade']

        else:
            for c in ('apt', 'dnf', 'yum', 'pacman', 'apk', 'zypper', 'emerge', 'xbps-install', 'eopkg', 'nix-env'):
                if shutil.which(c):
                    OS_FAMILY = 'linux'
                    PKG_MANAGER = c
                    break

        name_to_show = distro_pretty or f'{distro_id} {distro_version}' or 'unknown'
        log_ok(f'系统: Linux ({name_to_show.strip()}, {platform.machine()})')
        if PKG_MANAGER:
            log_ok(f'包管理器: {PKG_MANAGER}')
        else:
            log_warn('未检测到已知的包管理器')
            add_finding('WARN', '操作系统', '未检测到已知包管理器', '手动安装依赖，或设置系统 PATH')

        if OS_FAMILY == 'debian' and PKG_MANAGER == 'apt' and distro_id and distro_version:
            _check_apt_sources(distro_id, distro_version)

        return

    if system == 'darwin':
        DETECTED_OS = 'macos'
        OS_FAMILY = 'macos'
        if shutil.which('brew'):
            PKG_MANAGER = 'brew'
            PKG_INSTALL_CMD = ['brew', 'install']
            PKG_UPDATE_CMD = ['brew', 'update']
        log_ok(f'系统: macOS ({platform.machine()})')
        return

    if system == 'windows':
        DETECTED_OS = 'windows'
        OS_FAMILY = 'windows'
        log_ok(f'系统: Windows')
        log_warn('Windows环境建议手动安装依赖')
        return

    log_warn(f'未知系统: {system}')

DEBIAN_CODENAMES = {
    '1.1': 'buzz', '1.2': 'rex', '1.3': 'bo', '2.0': 'hamm',
    '2.1': 'slink', '2.2': 'potato', '3.0': 'woody', '3.1': 'sarge',
    '4.0': 'etch', '5.0': 'lenny', '6': 'squeeze', '7': 'wheezy',
    '8': 'jessie', '9': 'stretch', '10': 'buster',
    '11': 'bullseye', '12': 'bookworm', '13': 'trixie',
    '14': 'forky',
}

UBUNTU_CODENAMES = {
    '4.10': 'warty', '5.04': 'hoary', '5.10': 'breezy',
    '6.06': 'dapper', '6.10': 'edgy', '7.04': 'feisty',
    '7.10': 'gutsy', '8.04': 'hardy', '8.10': 'intrepid',
    '9.04': 'jaunty', '9.10': 'karmic', '10.04': 'lucid',
    '10.10': 'maverick', '11.04': 'natty', '11.10': 'oneiric',
    '12.04': 'precise', '12.10': 'quantal', '13.04': 'raring',
    '13.10': 'saucy', '14.04': 'trusty', '14.10': 'utopic',
    '15.04': 'vivid', '15.10': 'wily', '16.04': 'xenial',
    '16.10': 'yakkety', '17.04': 'zesty', '17.10': 'artful',
    '18.04': 'bionic', '18.10': 'cosmic', '19.04': 'disco',
    '19.10': 'eoan', '20.04': 'focal', '20.10': 'groovy',
    '21.04': 'hirsute', '21.10': 'impish', '22.04': 'jammy',
    '22.10': 'kinetic', '23.04': 'lunar', '23.10': 'mantic',
    '24.04': 'noble', '24.10': 'oracular',
    '25.04': 'plucky', '25.10': 'torvalds',
}

def _get_expected_codename(distro_id, distro_version):
    if distro_id == 'debian':
        return DEBIAN_CODENAMES.get(distro_version, '')
    if distro_id == 'ubuntu':
        return UBUNTU_CODENAMES.get(distro_version, '')
    if distro_id in ('linuxmint', 'elementary', 'pop', 'zorin'):
        if distro_id == 'linuxmint':
            mint_ubtu = {'20': 'focal', '21': 'jammy', '22': 'noble', '23': 'plucky', '24': 'torvalds'}
            major = distro_version.split('.')[0] if distro_version else ''
            return mint_ubtu.get(major, '')
        if distro_id in ('elementary', 'pop', 'zorin'):
            return UBUNTU_CODENAMES.get(distro_version, '')
    return ''

def _check_apt_sources(distro_id, distro_version):
    if distro_id not in ('debian', 'ubuntu') and distro_id not in ('linuxmint', 'elementary', 'pop', 'zorin'):
        return

    expected_codename = _get_expected_codename(distro_id, distro_version)
    if not expected_codename:
        return

    sources_files = ['/etc/apt/sources.list']
    if os.path.isdir('/etc/apt/sources.list.d'):
        try:
            for f in os.listdir('/etc/apt/sources.list.d'):
                if f.endswith('.list') and os.path.isfile(os.path.join('/etc/apt/sources.list.d', f)):
                    sources_files.append(os.path.join('/etc/apt/sources.list.d', f))
        except Exception:
            pass

    version_mismatch = False
    for sf in sources_files:
        if not os.path.isfile(sf):
            continue
        try:
            with open(sf, 'r') as f:
                content = f.read()
        except Exception:
            continue
        for line in content.split('\n'):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if 'deb ' not in stripped and 'deb-src ' not in stripped:
                continue
            for wrong in set(list(DEBIAN_CODENAMES.values()) + list(UBUNTU_CODENAMES.values())):
                if wrong != expected_codename and wrong in stripped:
                    version_mismatch = True
                    break
            if version_mismatch:
                break
        if version_mismatch:
            log_warn(f'{sf} 中包含版本 "{wrong}"，与当前系统 "{expected_codename}" 不匹配')
            break

    if version_mismatch:
        log_warn(f'系统检测到 {distro_id} {distro_version}（代号 {expected_codename}），但软件源包含其他版本')
        if ask_yes_no(f'  是否备份并修复所有 sources.list（替换为 {expected_codename}）?'):
            backup_dir = '/etc/apt/sources.list.d/backup'
            try:
                os.makedirs(backup_dir, exist_ok=True)
            except Exception:
                backup_dir = '/root/apt_sources_backup'
                try:
                    os.makedirs(backup_dir, exist_ok=True)
                except Exception:
                    backup_dir = None

            all_wrong = set(list(DEBIAN_CODENAMES.values()) + list(UBUNTU_CODENAMES.values()))
            all_wrong.discard(expected_codename)

            for sf in sources_files:
                if not os.path.isfile(sf):
                    continue
                try:
                    with open(sf, 'r') as f:
                        lines = f.readlines()
                except Exception:
                    continue

                changed = False
                new_lines = []
                for line in lines:
                    s = line.strip()
                    if s.startswith('#'):
                        new_lines.append(line)
                        continue
                    for wrong in all_wrong:
                        if wrong in s and ('deb ' in s or 'deb-src ' in s):
                            line = line.replace(wrong, expected_codename)
                            changed = True
                    new_lines.append(line)

                if changed and backup_dir:
                    import shutil as _shutil
                    try:
                        _shutil.copy2(sf, os.path.join(backup_dir, os.path.basename(sf) + '.bak'))
                        log_info(f'已备份: {sf}')
                    except Exception:
                        pass

                if changed:
                    try:
                        with open(sf, 'w') as f:
                            f.writelines(new_lines)
                        log_info(f'已修复: {sf}（版本代号统一为 {expected_codename}）')
                    except Exception:
                        log_fail(f'写入失败: {sf}，请手动修改')

            log_info('修复完成，建议执行: apt update')

def check_python():
    log_title('2. 检查 Python 环境')

    py = shutil.which('python3') or shutil.which('python')
    if not py:
        log_fail('未找到 Python')
        add_finding('FAIL', 'Python 环境', '未找到 Python', '安装 Python 3（参考下文系统对应命令）')
        if ask_yes_no('  是否安装 Python 3?'):
            if DETECTED_OS == 'termux':
                run(['pkg', 'install', '-y', 'python'])
            elif OS_FAMILY == 'debian':
                run(['apt', 'update'])
                run(['apt', 'install', '-y', 'python3', 'python3-pip'])
            elif OS_FAMILY == 'arch':
                run(['pacman', '-S', '--noconfirm', 'python', 'python-pip'])
            elif OS_FAMILY == 'rhel':
                run([PKG_MANAGER, 'install', '-y', 'python3', 'python3-pip'])
            elif OS_FAMILY == 'alpine':
                run(['apk', 'add', 'python3', 'py3-pip'])
            elif DETECTED_OS == 'macos':
                run(['brew', 'install', 'python'])
            else:
                print(f'  请手动安装 Python 3 https://python.org')
                return False
        else:
            print('  Python 3 是运行本服务的必要条件')
            return False

    py = shutil.which('python3') or shutil.which('python')
    if not py:
        log_fail('Python 安装失败，请手动安装')
        add_finding('FAIL', 'Python 环境', 'Python 安装失败', '请访问 https://python.org 手动安装')
        return False
    log_ok(f'Python: {py}')

    ok, out, _ = run([py, '--version'])
    if ok:
        log_ok(f'版本: {out}')

    ver = sys.version_info
    if ver.major < 3 or (ver.major == 3 and ver.minor < 8):
        log_fail(f'Python 版本过低 ({ver.major}.{ver.minor})，需要 3.8+')
        add_finding('FAIL', 'Python 环境', f'Python {ver.major}.{ver.minor} 过低，需要 3.8+', '升级 Python 至 3.8 或更高版本')
        return False
    log_ok(f'Python {ver.major}.{ver.minor}.{ver.micro} (满足 >= 3.8)')

    pip = shutil.which('pip3') or shutil.which('pip')
    if pip:
        log_ok(f'pip: {pip}')
    else:
        log_warn('未找到 pip')
        if ask_yes_no('  是否安装 pip?'):
            if OS_FAMILY == 'debian':
                run(['apt', 'install', '-y', 'python3-pip'])
            elif DETECTED_OS == 'termux':
                run(['pkg', 'install', '-y', 'python-pip'])
            else:
                code, _, _ = run([py, '-m', 'ensurepip', '--upgrade'])
                if not code:
                    log_warn('pip 安装失败')

    pip = shutil.which('pip3') or shutil.which('pip')
    if pip:
        log_ok('pip 就绪')
    else:
        log_warn('pip 不可用，将使用 Python 标准库')

    return True

def check_stdlib_modules():
    log_title('3. 检查 Python 标准库模块')
    required = [
        ('sqlite3', 'sqlite3', '数据库存储'),
        ('ssl', 'ssl', 'SSL/TLS 加密'),
        ('smtplib', 'smtplib', '邮件发送'),
        ('json', 'json', 'JSON 处理'),
        ('http.server', 'http.server', 'HTTP 服务器'),
        ('threading', 'threading', '多线程'),
        ('urllib.parse', 'urllib.parse', 'URL 解析'),
        ('hashlib', 'hashlib', '密码哈希 (PBKDF2)'),
        ('secrets', 'secrets', '安全随机数'),
    ]

    all_ok = True
    for name, module, purpose in required:
        spec = importlib.util.find_spec(module)
        if spec is None:
            log_fail(f'{name} ({purpose}) — 缺失')
            add_finding('FAIL', 'Python 标准库', f'{name} ({purpose}) 缺失', '请确认 Python 安装完整，或重新安装 python3 标准包')
            all_ok = False
        else:
            log_ok(f'{name} ({purpose})')

    if all_ok:
        log_ok('所有标准库模块就绪')
    else:
        log_fail('部分标准库模块缺失，请确认 Python 安装完整')
    return all_ok

def check_system_deps():
    log_title('4. 检查系统依赖')

    ca_certs_ok = False
    if DETECTED_OS == 'termux':
        ok, _, _ = run(['pkg', 'list-installed', 'ca-certificates'])
        ca_certs_ok = ok
        if not ca_certs_ok:
            log_warn('ca-certificates 未安装（SSL 证书验证可能失败）')
            if ask_yes_no('  是否安装 ca-certificates?'):
                run(['pkg', 'install', '-y', 'ca-certificates'])

    # 用 Python 实际验证 CA 证书可用性（最终标准）
    py = shutil.which('python3') or shutil.which('python')
    if py:
        ok2, _, _ = run([py, '-c', 'import ssl; ssl.create_default_context()'])
        ca_certs_ok = ok2

    if ca_certs_ok:
        log_ok('CA 证书: 就绪')
    else:
        log_warn('CA 证书: 未安装，SSL 连接可能失败')
        add_finding('WARN', '系统依赖', 'CA 证书未安装，SSL 连接可能失败', '安装 ca-certificates 包（Termux: pkg install ca-certificates）')

def check_project_structure():
    log_title('5. 检查项目结构')
    required_dirs = [
        (SERVER_DIR, 'server 目录'),
        (PUBLIC_DIR, 'public 目录（前端文件）'),
        (os.path.join(SERVER_DIR, 'data'), 'data 目录（数据存储）'),
    ]
    required_files = [
        (os.path.join(SERVER_DIR, 'server.py'), '服务端主程序'),
        (os.path.join(SERVER_DIR, 'db.py'), '数据库模块'),
        (os.path.join(SERVER_DIR, 'mail.py'), '邮件模块'),
        (os.path.join(SERVER_DIR, 'utils.py'), '工具模块'),
        (os.path.join(SERVER_DIR, 'session_store.py'), '会话存储'),
        (os.path.join(SERVER_DIR, 'dynamic_code.py'), '动态验证码'),
        (os.path.join(SERVER_DIR, 'logger.py'), '日志模块'),
        (os.path.join(SERVER_DIR, 'admin_config.py'), '管理员配置'),
        (os.path.join(PUBLIC_DIR, 'index.html'), '短信列表页'),
        (os.path.join(PUBLIC_DIR, 'login.html'), '登录页'),
        (os.path.join(PUBLIC_DIR, 'register.html'), '注册页'),
        (os.path.join(PUBLIC_DIR, 'verify.html'), '验证页'),
        (os.path.join(PUBLIC_DIR, 'forgot-password.html'), '忘记密码页'),
        (os.path.join(PUBLIC_DIR, 'set-password.html'), '设置密码页'),
        (os.path.join(PUBLIC_DIR, 'console.html'), '管理后台'),
        (os.path.join(PUBLIC_DIR, 'css', 'style.css'), '样式文件'),
        (os.path.join(PUBLIC_DIR, 'js', 'auth.js'), '前端公共脚本'),
    ]

    all_ok = True
    for path, desc in required_dirs:
        if os.path.isdir(path):
            log_ok(f'{path} ({desc})')
        else:
            try:
                os.makedirs(path, exist_ok=True)
                log_ok(f'{path} ({desc}) — 已自动创建')
            except OSError:
                log_fail(f'{path} ({desc}) — 创建失败')
                add_finding('FAIL', '项目结构', f'{desc} 创建失败: {path}', '请检查权限: mkdir -p {path}')
                all_ok = False

    for path, desc in required_files:
        if os.path.isfile(path):
            log_ok(f'{path} ({desc})')
        else:
            log_fail(f'{path} ({desc}) — 缺失')
            add_finding('FAIL', '项目结构', f'{desc} 缺失: {path}', '请确认项目文件完整，参考 Git 仓库还原')
            all_ok = False

    return all_ok

def check_file_permissions():
    log_title('6. 检查文件权限')
    warnings = 0
    data_dir = os.path.join(SERVER_DIR, 'data')
    if os.path.isdir(data_dir):
        for fname in os.listdir(data_dir):
            fpath = os.path.join(data_dir, fname)
            if os.path.isfile(fpath):
                mode = os.stat(fpath).st_mode
                if mode & stat.S_IROTH:
                    log_warn(f'{fpath} 对其他用户可读 (权限 {oct(mode & 0o777)})')
                    add_finding('WARN', '文件权限', f'{fpath} 对其他用户可读', f'执行: chmod 600 {fpath}')
                    warnings += 1

    admin_cred = os.path.join(data_dir, 'admin_credentials.txt')
    if os.path.isfile(admin_cred):
        mode = os.stat(admin_cred).st_mode
        if mode & stat.S_IROTH:
            log_warn(f'{admin_cred} 包含明文密码，对其他用户可读')
            add_finding('WARN', '文件权限', f'{admin_cred} 包含明文密码且可被其他用户读取', f'执行: chmod 600 {admin_cred}')
            warnings += 1
        else:
            log_info(f'{admin_cred} 存在（权限正常，仅所有者可读）')

    db_path = os.path.join(data_dir, 'sms.db')
    if os.path.isfile(db_path):
        mode = os.stat(db_path).st_mode
        if mode & stat.S_IROTH:
            log_warn(f'{db_path} 对其他用户可读')
            add_finding('WARN', '文件权限', f'{db_path} 对其他用户可读', f'执行: chmod 600 {db_path}')
            warnings += 1

    mail_config = os.path.join(data_dir, 'mail_config.json')
    if os.path.isfile(mail_config):
        mode = os.stat(mail_config).st_mode
        if mode & stat.S_IROTH:
            log_warn(f'{mail_config} 包含SMTP密码，对其他用户可读')
            add_finding('WARN', '文件权限', f'{mail_config} 包含SMTP密码且可被其他用户读取', f'执行: chmod 600 {mail_config}')
            warnings += 1

    if warnings == 0:
        log_ok('文件权限正常')
    return warnings

def scan_code_security():
    log_title('7. 代码安全扫描')

    code_issues = 0
    server_files = [
        os.path.join(SERVER_DIR, f)
        for f in os.listdir(SERVER_DIR)
        if f.endswith('.py') and f not in ('check_env.py', 'mod_scanner.py')
    ]

    for fpath in server_files:
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        for i, line in enumerate(content.split('\n'), 1):
            stripped = line.strip()

            if 'eval(' in stripped and 'importlib' not in stripped:
                rel = os.path.relpath(fpath, PROJECT_DIR)
                log_fail(f'{rel}:{i} — 使用了 eval()，可能有代码注入风险')
                add_finding('FAIL', '代码安全', f'{rel}:{i} — 使用了 eval()', '避免使用 eval()，改用 json.loads() 或 ast.literal_eval()')
                code_issues += 1

            if 'exec(' in stripped and 'executescript' not in stripped:
                rel = os.path.relpath(fpath, PROJECT_DIR)
                log_fail(f'{rel}:{i} — 使用了 exec()，可能有代码注入风险')
                add_finding('FAIL', '代码安全', f'{rel}:{i} — 使用了 exec()', '避免使用 exec()，改用安全替代方案')
                code_issues += 1

            if '__import__' in stripped:
                rel = os.path.relpath(fpath, PROJECT_DIR)
                log_fail(f'{rel}:{i} — 使用了 __import__，可能有代码注入风险')
                add_finding('FAIL', '代码安全', f'{rel}:{i} — 使用了 __import__', '避免使用 __import__()')
                code_issues += 1

            if stripped.startswith('print(') and 'password' in stripped.lower():
                if 'admin_config.py' not in fpath:
                    rel = os.path.relpath(fpath, PROJECT_DIR)
                    log_fail(f'{rel}:{i} — print 中可能包含密码信息')
                    add_finding('WARN', '代码安全', f'{rel}:{i} — print 输出可能包含密码', '去除 print 中的密码信息')
                    code_issues += 1

            if 'os.system(' in stripped or 'subprocess.' in stripped:
                if 'shell=True' in stripped or 'shell = True' in stripped:
                    rel = os.path.relpath(fpath, PROJECT_DIR)
                    log_fail(f'{rel}:{i} — shell=True 可能存在命令注入风险')
                    add_finding('FAIL', '代码安全', f'{rel}:{i} — shell=True 存在命令注入风险', '移除 shell=True，使用列表参数形式')
                    code_issues += 1

    if code_issues == 0:
        log_ok('Python 代码无明显的注入风险')

    log_title('8. SQL 注入检查')
    sql_issues = 0
    for fpath in server_files:
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        for i, line in enumerate(content.split('\n'), 1):
            s = line.strip()
            if re.search(r"execute\(['\"].*\{.*['\"]\s*%", s) or re.search(r"execute\(['\"].*\+", s):
                if 'execute(' in s:
                    rel = os.path.relpath(fpath, PROJECT_DIR)
                    log_warn(f'{rel}:{i} — 字符串拼接SQL: {s.strip()[:60]}')
                    add_finding('WARN', 'SQL 注入', f'{rel}:{i} — 字符串拼接 SQL', '改用参数化查询: cursor.execute("sql", (param,))')
                    sql_issues += 1

    if sql_issues == 0:
        log_ok('所有 SQL 使用参数化查询，无注入风险')

    log_title('9. XSS / 输出安全检查')
    xss_issues = 0
    html_files = []
    if os.path.isdir(PUBLIC_DIR):
        for root, _, files in os.walk(PUBLIC_DIR):
            for f in files:
                if f.endswith('.html') or f.endswith('.js'):
                    html_files.append(os.path.join(root, f))

    for fpath in html_files:
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')
        i = 0
        while i < len(lines):
            s_line = lines[i].strip()

            assign_match = re.search(r'\.innerHTML\s*\+?=', s_line)
            if not assign_match:
                i += 1
                continue

            if 'escHtml(' in s_line:
                i += 1
                continue

            stmt_start = i
            while stmt_start > 0:
                prev = lines[stmt_start - 1].strip()
                curr = lines[stmt_start].strip()
                if curr.startswith('+') or prev.endswith('+'):
                    stmt_start -= 1
                else:
                    break

            stmt_end = i
            while stmt_end + 1 < len(lines):
                nxt = lines[stmt_end + 1].strip()
                curr = lines[stmt_end].strip()
                if nxt.startswith('+') or curr.endswith('+'):
                    stmt_end += 1
                else:
                    break

            combined = ' '.join(l.strip() for l in lines[stmt_start:stmt_end + 1])

            if 'escHtml(' in combined:
                i = stmt_end + 1
                continue

            eq_pos = combined.find('=')
            if eq_pos == -1:
                i = stmt_end + 1
                continue
            rhs = combined[eq_pos + 1:].strip()

            rhs_no_str = re.sub(r"'[^']*'", '', rhs)
            rhs_no_str = re.sub(r'"[^"]*"', '', rhs_no_str)
            bare_vars = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_.]*\b', rhs_no_str)
            keywords = {'null', 'true', 'false', 'this', 'undefined', 'typeof', 'void', 'new', 'delete', 'var', 'let', 'const', 'function', 'return', 'if', 'else', 'for', 'while'}
            bare_vars = [v for v in bare_vars if v not in keywords]

            lhs = combined[:eq_pos].strip()
            lhs_vars = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_.]*\b', lhs))
            bare_vars = [v for v in bare_vars if v not in lhs_vars]

            rel = os.path.relpath(fpath, PROJECT_DIR)

            if not bare_vars:
                i = stmt_end + 1
                continue

            has_concat = '+' in rhs_no_str
            has_strings = "'" in rhs or '"' in rhs

            if has_concat and has_strings:
                log_fail(f'{rel}:{i+1} — innerHTML 拼接用户数据未使用 escHtml: {s_line[:60]}')
                add_finding('FAIL', 'XSS/输出安全', f'{rel}:{i+1} — innerHTML 拼接未使用 escHtml()', '对用户输入变量使用 escHtml() 包裹')
                xss_issues += 1
            elif not has_strings:
                log_warn(f'{rel}:{i+1} — innerHTML 赋值非纯静态字符串（建议确认已转义）: {s_line[:60]}')
                add_finding('WARN', 'XSS/输出安全', f'{rel}:{i+1} — innerHTML 赋值非纯静态字符串', '确认该变量内容已通过 escHtml() 构建，或直接使用 escHtml() 包裹')
                xss_issues += 1

            i = stmt_end + 1

    if xss_issues == 0:
        log_ok('前端输出安全，无明显的 XSS 风险')

    return code_issues + sql_issues + xss_issues

def check_network():
    log_title('10. 网络连接检查')

    targets = [
        ('smtp.qq.com', 465, 'QQ SMTP'),
        ('www.baidu.com', 443, '外网'),
    ]

    py = shutil.which('python3') or shutil.which('python')
    for host, port, name in targets:
        script = f'''
import socket
try:
    s = socket.create_connection(("{host}", {port}), timeout=5)
    s.close()
    print("ok")
except Exception as e:
    print(e)
'''
        ok, out, _ = run([py, '-c', script])
        if 'ok' in out:
            log_ok(f'{name} ({host}:{port}) — 可达')
        else:
            log_warn(f'{name} ({host}:{port}) — 不可达: {out[:60]}')
            add_finding('WARN', '网络连接', f'{name} ({host}:{port}) 不可达', '检查网络连接或防火墙设置')

def get_java_install_hint():
    hints = {
        'termux': 'pkg install openjdk-17',
        'debian': 'apt install openjdk-17-jdk',
        'arch': 'pacman -S jdk17-openjdk',
        'rhel': 'dnf install java-17-openjdk',
        'alpine': 'apk add openjdk17',
        'macos': 'brew install openjdk@17',
    }
    return hints.get(OS_FAMILY, '安装 JDK 17+ (参考 https://adoptium.net)')

def check_java():
    log_title('11. Android 编译环境检查')
    if os.path.isdir(MOBILE_DIR):
        java = shutil.which('java')
        if java:
            ok, out, _ = run([java, '-version'])
            if ok:
                log_ok(f'Java: 已安装')
            else:
                log_warn(f'Java: {out}')
                add_finding('WARN', 'Android 编译', 'Java 运行异常', '检查 Java 安装')
        else:
            log_warn('Java 未安装（Android 编译需要 JDK 17+）')
            add_finding('WARN', 'Android 编译', 'Java 未安装', get_java_install_hint())
            if DETECTED_OS == 'termux':
                log_info('  Termux 安装 JDK: pkg install openjdk-17')
            elif OS_FAMILY == 'debian':
                log_info('  安装 JDK: apt install openjdk-17-jdk')
            elif DETECTED_OS == 'macos':
                log_info('  安装 JDK: brew install openjdk@17')

        gradlew = os.path.join(MOBILE_DIR, 'gradlew')
        if os.path.isfile(gradlew):
            log_ok('Gradle wrapper 存在')
        else:
            log_warn('gradlew 不存在')
            add_finding('WARN', 'Android 编译', 'gradlew 不存在', '在 mobile/SmsToWeb/ 目录执行: gradle wrapper 生成')
    else:
        log_info('Android 项目目录不存在，跳过检查')

def write_report(env_ok, security_issues):
    report_dir = os.environ.get('DATA_DIR', SERVER_DIR)
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, 'check_report.txt')
    now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    fail_count = sum(1 for f in FINDINGS if f['s'] == 'FAIL')
    warn_count = sum(1 for f in FINDINGS if f['s'] == 'WARN')

    lines = [
        '=' * 58,
        '  短信转网页 === 环境与安全检测报告',
        '=' * 58,
        f'  检测时间: {now}',
        f'  操作系统: {DETECTED_OS} ({platform.machine()})',
        f'  项目路径: {PROJECT_DIR}',
        '-' * 58,
        f'  问题统计: {fail_count} 个严重 + {warn_count} 个警告',
        '-' * 58,
        '',
    ]

    if not FINDINGS:
        lines.append('  未发现任何问题，环境完全正常。')
    else:
        categories = {}
        for f in FINDINGS:
            categories.setdefault(f['c'], []).append(f)

        for cat, items in categories.items():
            lines.append(f'【{cat}】')
            for item in items:
                icon = {'OK': 'PASS', 'WARN': '!', 'FAIL': 'FAIL', 'INFO': 'i'}.get(item['s'], '?')
                lines.append(f'  [{icon}] {item["m"]}')
                if item['f']:
                    lines.append(f'      解决: {item["f"]}')
            lines.append('')

    lines.append('-' * 58)
    if env_ok:
        lines.append('  环境状态: PASS 正常')
    else:
        lines.append('  环境状态: FAIL 异常（请修复所有 [FAIL] 项）')
    lines.append(f'  启动命令: python3 server/server.py')
    lines.append('=' * 58)

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    log_info(f'检测报告已保存: {report_path}')

def summary(env_ok, security_issues):
    fail_count = sum(1 for f in FINDINGS if f['s'] == 'FAIL')
    warn_count = sum(1 for f in FINDINGS if f['s'] == 'WARN')
    log_title('检 测 总 结')
    if env_ok:
        log_ok('环境检测通过')
    else:
        log_fail('环境检测未通过，请修复上述问题')

    if fail_count == 0 and warn_count == 0:
        log_ok('安全检测通过，无问题')
    elif fail_count == 0:
        log_warn(f'发现 {warn_count} 个警告，建议检查')
    else:
        log_fail(f'发现 {fail_count} 个严重问题 + {warn_count} 个警告，建议修复')

    log_info(f'项目路径: {PROJECT_DIR}')
    log_info(f'启动命令: python3 server.py')
    log_info(f'检测时间: {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

FIX_ACTIONS = []

def fix_log(action):
    FIX_ACTIONS.append(action)
    log_ok(f'修复: {action}')

def fix_missing_dirs():
    log_title('修复 1/3: 创建缺失目录')
    missing_dirs = [
        (os.path.join(SERVER_DIR, 'data'), 'data 目录（数据存储）'),
    ]
    for d, desc in missing_dirs:
        if os.path.isdir(d):
            log_ok(f'{desc} 已存在: {d}')
        else:
            try:
                os.makedirs(d, mode=0o700, exist_ok=True)
                fix_log(f'创建 {desc}: {d}')
            except Exception as e:
                log_fail(f'创建 {desc} 失败: {e}')

def fix_permissions():
    log_title('修复 2/3: 修复敏感文件权限')
    data_dir = os.path.join(SERVER_DIR, 'data')
    sensitive_patterns = ['.db', '.txt', '.json']
    fixed = 0
    if os.path.isdir(data_dir):
        for fname in os.listdir(data_dir):
            fpath = os.path.join(data_dir, fname)
            if os.path.isfile(fpath) and any(fname.endswith(p) for p in sensitive_patterns):
                mode = os.stat(fpath).st_mode
                if mode & stat.S_IROTH:
                    try:
                        os.chmod(fpath, 0o600)
                        fix_log(f'修复权限 600: {fpath}')
                        fixed += 1
                    except Exception as e:
                        log_fail(f'修复权限失败 {fpath}: {e}')
    if fixed == 0:
        log_ok('无需修复，敏感文件权限正确')

def fix_system_deps():
    log_title('修复 3/3: 安装系统依赖')
    if DETECTED_OS == 'termux':
        log_info('检测到 Termux，检查 ca-certificates...')
        ok, _, _ = run(['pkg', 'list-installed', 'ca-certificates'])
        if not ok and ask_yes_no('  是否安装 ca-certificates?'):
            ok2, _, _ = run(['pkg', 'install', '-y', 'ca-certificates'])
            if ok2:
                fix_log('安装 ca-certificates')
            else:
                log_fail('安装 ca-certificates 失败')
        else:
            log_ok('ca-certificates 已安装')
    elif OS_FAMILY != 'unknown' and PKG_INSTALL_CMD:
        log_info('系统依赖检查完成（CA 证书通常已包含在系统中）')
    else:
        log_info('无法自动安装系统依赖，请手动安装')

    if os.path.isdir(MOBILE_DIR) and not shutil.which('java'):
        log_info(f'提示: {get_java_install_hint()} （编译安卓 APK 需要）')

def run_fix_mode():
    log_title('运行自动修复模式')
    fix_missing_dirs()
    fix_permissions()
    fix_system_deps()

    if FIX_ACTIONS:
        log_info(f'共执行 {len(FIX_ACTIONS)} 项修复')
    else:
        log_ok('无需修复，所有项正常')
    return len(FIX_ACTIONS)

def run_all_checks(quick=False):
    detect_os()
    py_ok = check_python()
    stdlib_ok = check_stdlib_modules()
    check_system_deps()
    structure_ok = check_project_structure()
    check_file_permissions()
    sec_issues = scan_code_security()
    if not quick:
        check_network()
    check_java()

    env_ok = py_ok and stdlib_ok and structure_ok
    write_report(env_ok, sec_issues)
    summary(env_ok, sec_issues)
    return env_ok, sec_issues

def main():
    parser = argparse.ArgumentParser(
        description='短信转网页 — 环境与安全检测工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f'示例:\n  python3 check_env.py             运行全部检测\n  python3 check_env.py --quick     跳过网络检查\n  python3 check_env.py --fix       检测并自动修复常见问题\n  python3 check_env.py --json      输出 JSON 格式结果',
    )
    parser.add_argument('--quick', action='store_true', help='快速模式（跳过网络检查）')
    parser.add_argument('--fix', action='store_true', help='检测并自动修复常见问题')
    parser.add_argument('--json', action='store_true', help='以 JSON 格式输出检测结果')
    args = parser.parse_args()

    if args.fix:
        detect_os()
        run_fix_mode()
        print()
        return

    print(f'\n=========================================')
    print(f'   短信转网页 -- 环境与安全检测')
    print(f'=========================================\n')

    env_ok, _ = run_all_checks(quick=args.quick)

    if args.json:
        import json
        print(json.dumps(FINDINGS, ensure_ascii=False, indent=2))

    if env_ok:
        print(f'\n[PASS] 环境正常，可以启动服务器')
    else:
        print(f'\n[FAIL] 环境有问题，请按上述提示修复后重试')
    print()

if __name__ == '__main__':
    main()
