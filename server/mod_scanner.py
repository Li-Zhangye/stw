import os
import re
import ast
import base64

SEVERITY_COLORS = {}
SEVERITY_WEIGHT = {'high': 10, 'medium': 5, 'low': 2, 'info': 0}

SCANNER_DIR = os.path.dirname(os.path.abspath(__file__))

EXT_PATTERNS = {
    '.py': [
        (10, 'eval() 调用', r'\beval\s*\('),
        (10, 'exec() 调用', r'\bexec\s*\('),
        (9, 'os.system() shell 执行', r'\bos\.system\s*\('),
        (9, 'os.popen() 管道执行', r'\bos\.popen\s*\('),
        (8, 'subprocess shell=True', r'subprocess\.\w+\s*\([^)]*shell\s*=\s*True'),
        (8, 'subprocess.Popen 无限制', r'subprocess\.Popen\s*\('),
        (9, 'os.remove/unlink 文件删除', r'\bos\.(remove|unlink)\s*\('),
        (8, 'shutil.rmtree 目录删除', r'\bshutil\.rmtree\s*\('),
        (8, 'pickle.load() 反序列化', r'\bpickle\.load(?:s)?\s*\('),
        (8, 'shelve.open() 持久化', r'\bshelve\.open\s*\('),
        (7, 'compile() 动态编译', r'\bcompile\s*\('),
        (7, '__import__() 动态导入', r'\b__import__\s*\('),
        (7, 'open() 写模式', r'open\s*\([^)]*["\']w'),
        (6, 'open() 追加模式', r'open\s*\([^)]*["\']a'),
        (6, 'os.chmod() 权限修改', r'\bos\.chmod\s*\('),
        (6, 'os.chown() 所有者修改', r'\bos\.chown\s*\('),
        (5, 'os.environ 环境变量', r'\bos\.environ\b'),
        (5, 'os.walk() 目录遍历', r'\bos\.walk\s*\('),
        (5, 'os.makedirs() 目录创建', r'\bos\.makedirs\s*\('),
        (4, 'glob() 文件匹配', r'\bglob\.glob\s*\('),
        (4, 'fnmatch 文件匹配', r'\bfnmatch\.'),
        (3, 'sys.path 修改', r'\bsys\.path\.(insert|append|remove)\s*\('),
        (3, 'os.getcwd/chdir 工作目录', r'\bos\.(getcwd|chdir)\s*\('),
        (2, 'os.path 大量操作', r'\bos\.path\.(join|exists|isfile|isdir)\s*\('),
        (5, '临时文件创建', r'\btempfile\.'),
        (4, 'base64 编解码', r'\bbase64\.(b64encode|b64decode|b32|b16)'),
        (1, 'print() 调试输出', r'\bprint\s*\('),
        (1, 'logging 日志', r'\blogging\.'),
    ],
    '.js': [
        (10, 'eval() 执行代码', r'\beval\s*\('),
        (10, 'Function() 构造器', r'\bnew\s+Function\s*\('),
        (9, 'document.write() 注入', r'\bdocument\.write\s*\('),
        (9, 'innerHTML 赋值', r'\.innerHTML\s*='),
        (8, 'setTimeout 字符串', r'setTimeout\s*\(\s*["\']'),
        (8, 'setInterval 字符串', r'setInterval\s*\(\s*["\']'),
        (7, 'fetch() 外部请求', r'\bfetch\s*\('),
        (7, 'XMLHttpRequest 请求', r'\bXMLHttpRequest\b'),
        (6, 'localStorage 存储', r'\blocalStorage\.'),
        (6, 'sessionStorage 存储', r'\bsessionStorage\.'),
        (5, 'document.cookie', r'\bdocument\.cookie\b'),
        (4, 'window.open 弹窗', r'\bwindow\.open\s*\('),
        (4, 'location 操作', r'\blocation\.(href|assign|replace)'),
        (3, 'console.log 调试', r'\bconsole\.log\s*\('),
    ],
    '.sh': [
        (10, 'rm -rf 危险删除', r'rm\s+[-][^r]*r\s*'),
        (9, 'eval 动态执行', r'\beval\b'),
        (8, 'wget/curl 下载执行', r'(wget|curl)\s+.*\|'),
        (8, '>/dev/null 隐藏输出', r'>\s*/dev/null'),
        (7, 'sudo 提权', r'\bsudo\b'),
        (7, 'chmod 777', r'chmod\s+777\s*'),
        (6, '>/dev/tcp 网络', r'>\s*/dev/tcp/'),
        (5, 'mkfifo 命名管道', r'\bmkfifo\b'),
        (5, 'mknod 设备节点', r'\bmknod\b'),
    ],
    '.php': [
        (10, 'eval() 执行', r'\beval\s*\('),
        (10, 'assert() 执行', r'\bassert\s*\('),
        (9, 'system() shell 执行', r'\bsystem\s*\('),
        (9, 'exec() 执行', r'\bexec\s*\('),
        (9, 'shell_exec() 执行', r'\bshell_exec\s*\('),
        (9, 'passthru() 执行', r'\bpassthru\s*\('),
        (8, 'popen() 管道', r'\bpopen\s*\('),
        (8, 'include/require 动态', r'(include|require)\s*\$'),
        (7, 'file_put_contents 写', r'\bfile_put_contents\s*\('),
        (7, 'fwrite/fputs 写文件', r'\bf(write|puts)\s*\('),
        (6, 'unlink 文件删除', r'\bunlink\s*\('),
        (6, 'chmod 权限修改', r'\bchmod\s*\('),
        (5, '$_GET/$_POST/$_REQUEST', r'\$_)(GET|POST|REQUEST)'),
        (4, 'mysql_query 查询', r'\bmysql_query\b'),
        (3, 'error_reporting 关闭', r'\berror_reporting\s*\(\s*0\s*\)'),
    ],
    '.c': [
        (8, 'system() 调用', r'\bsystem\s*\('),
        (8, 'popen() 管道', r'\bpopen\s*\('),
        (7, 'exec 系列', r'\bexec[lv]p?\s*\('),
        (6, 'fopen 写模式', r'\bfopen\s*\([^)]*["\']w'),
        (6, 'remove() 删除', r'\bremove\s*\('),
        (5, 'gets() 缓冲区溢出', r'\bgets\s*\('),
        (5, 'strcpy 溢出', r'\bstrcpy\s*\('),
        (5, 'sprintf 溢出', r'\bsprintf\s*\('),
        (4, 'scanf 无限制', r'\bscanf\s*\('),
        (4, 'malloc 内存分配', r'\bmalloc\s*\('),
    ],
    '.cpp': [
        (8, 'system() 调用', r'\bsystem\s*\('),
        (8, 'popen() 管道', r'\bpopen\s*\('),
        (7, 'exec 系列', r'\bexec[lv]p?\s*\('),
        (6, 'fopen 写模式', r'\bfopen\s*\([^)]*["\']w'),
        (6, 'remove() 删除', r'\bremove\s*\('),
        (5, 'gets() 缓冲区溢出', r'\bgets\s*\('),
        (5, 'strcpy 溢出', r'\bstrcpy\s*\('),
        (4, 'cin >> 输入', r'\bcin\s*>>'),
        (4, 'new 动态分配', r'\bnew\s+\w+'),
    ],
    '.html': [
        (7, 'inline script', r'<script\b[^>]*>'),
        (5, 'onclick/onload 事件', r'\bon\w+\s*='),
        (4, 'iframe 嵌入', r'<iframe\b'),
        (3, 'data: URI', r'data:\s*\w+/\w+;base64'),
    ],
}

ALLOWLIST_PATTERNS = {
    '.py': [
        r'os\.path\.join\(DATA_DIR',
        r'os\.path\.join\(MOD_DIR',
        r'os\.path\.join\(PUBLIC_DIR',
        r'os\.makedirs\(.*exist_ok=True\)',
        r'print\s*\(f["\'].*["\']\)',
        r'logging\.getLogger',
        r'logging\.basicConfig',
    ],
    '.js': [
        r'console\.log\(["\']',
        r'\.innerHTML\s*=\s*["\'][^"\'<>]*["\']',
    ],
}

DANGEROUS_FILE_EXTENSIONS = {
    '.py': 'Python 脚本',
    '.pyc': 'Python 字节码',
    '.js': 'JavaScript',
    '.sh': 'Shell 脚本',
    '.php': 'PHP 脚本',
    '.pl': 'Perl 脚本',
    '.rb': 'Ruby 脚本',
    '.lua': 'Lua 脚本',
    '.exe': 'Windows 可执行',
    '.dll': 'Windows 动态库',
    '.so': 'Linux 共享库',
    '.elf': 'Linux 可执行',
    '.bin': '二进制文件',
}

def _is_likely_binary(filepath):
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(1024)
        return b'\x00' in chunk
    except Exception:
        return True

def _parse_python_ast(filepath):
    try:
        with open(filepath, 'rb') as f:
            content = f.read()
        tree = ast.parse(content, filename=filepath)
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    fn = node.func.id
                    if fn in ('eval', 'exec', '__import__'):
                        issues.append((node.lineno, 10, f'ast 检测: {fn}() 调用'))
                    elif fn == 'compile':
                        issues.append((node.lineno, 7, 'ast 检测: compile() 动态编译'))
                elif isinstance(node.func, ast.Attribute):
                    fn = node.func.attr
                    if fn in ('system', 'popen'):
                        issues.append((node.lineno, 9, f'ast 检测: {fn}() 系统调用'))
                    elif fn in ('remove', 'unlink', 'rmtree'):
                        issues.append((node.lineno, 8, f'ast 检测: {fn}() 文件删除'))
        return issues
    except SyntaxError:
        return [(0, 5, 'Python 语法错误，无法完整分析')]
    except Exception:
        return []

def _check_allowlisted(content, ext):
    patterns = ALLOWLIST_PATTERNS.get(ext, [])
    if not patterns:
        return []
    result = []
    for pat in patterns:
        if re.search(pat, content):
            result.append(pat)
    return result

def scan_file(filepath):
    issues = []
    _, ext = os.path.splitext(filepath)
    ext = ext.lower()

    if not os.path.isfile(filepath):
        return {'file': filepath, 'binary': False, 'issues': [], 'summary': {'high': 0, 'medium': 0, 'low': 0, 'info': 0, 'total': 0, 'score': 0}}

    is_binary = _is_likely_binary(filepath)

    if is_binary:
        severity = 8 if ext in DANGEROUS_FILE_EXTENSIONS else 5
        desc = DANGEROUS_FILE_EXTENSIONS.get(ext, f'二进制文件')
        if os.access(filepath, os.X_OK) and not filepath.endswith('.so'):
            issues.append((0, 10, f'可执行二进制文件'))
        else:
            issues.append((0, severity, f'{desc}（无法扫描源码）'))

        summary = {'high': 0, 'medium': 0, 'low': 0, 'info': 0, 'total': 0, 'score': 0}
        total_score = 0
        for lineno, weight, desc in issues:
            if weight >= 8:
                summary['high'] += 1
            elif weight >= 5:
                summary['medium'] += 1
            elif weight >= 2:
                summary['low'] += 1
            else:
                summary['info'] += 1
            total_score += weight
        summary['total'] = len(issues)
        summary['score'] = total_score

        return {'file': filepath, 'binary': True, 'issues': issues, 'summary': summary}

    if ext not in EXT_PATTERNS:
        return {'file': filepath, 'binary': False, 'issues': [], 'summary': {'high': 0, 'medium': 0, 'low': 0, 'info': 0, 'total': 0, 'score': 0}}

    try:
        with open(filepath, 'rb') as f:
            content_bytes = f.read()
        content = content_bytes.decode('utf-8', errors='replace')
    except Exception:
        return {'file': filepath, 'binary': False, 'issues': [(0, 5, '无法读取文件')], 'summary': {'high': 0, 'medium': 1, 'low': 0, 'info': 0, 'total': 1, 'score': 5}}

    ast_issues = []
    if ext == '.py':
        ast_issues = _parse_python_ast(filepath)

    re_issues = []
    for pattern_weight, pattern_desc, pattern_re in EXT_PATTERNS.get(ext, []):
        for m in re.finditer(pattern_re, content, re.MULTILINE):
            lineno = content[:m.start()].count('\n') + 1
            re_issues.append((lineno, pattern_weight, f'[{pattern_desc}]'))

    seen = set()
    for lineno, weight, desc in ast_issues + re_issues:
        key = (lineno, desc)
        if key not in seen:
            seen.add(key)
            issues.append((lineno, weight, desc))

    allowlisted = _check_allowlisted(content, ext)
    if allowlisted:
        issues = [(l, w, d) for l, w, d in issues
                  if not any(re.search(ap, d) for ap in allowlisted)
                  and not any(re.search(ap, content.split('\n')[l-1] if 0 < l <= len(content.split('\n')) else '') for ap in allowlisted)]

    issues.sort(key=lambda x: (x[0] > 0, x[0]))

    summary = {'high': 0, 'medium': 0, 'low': 0, 'info': 0, 'total': 0, 'score': 0}
    total_score = 0
    highest_found = 0
    for lineno, weight, desc in issues:
        if weight >= 8:
            summary['high'] += 1
        elif weight >= 5:
            summary['medium'] += 1
        elif weight >= 2:
            summary['low'] += 1
        else:
            summary['info'] += 1
        total_score += weight
        if weight > highest_found:
            highest_found = weight

    summary['total'] = len(issues)
    summary['score'] = total_score
    summary['highest'] = highest_found

    return {'file': filepath, 'binary': False, 'issues': issues, 'summary': summary}


def scan_directory(mod_dir, all_files=True):
    results = []
    for root, _, files in os.walk(mod_dir):
        if os.path.commonpath([root, SCANNER_DIR]) == SCANNER_DIR:
            continue
        for fname in files:
            if fname.startswith('.') or fname.startswith('priorities'):
                continue
            fp = os.path.join(root, fname)
            if not os.path.isfile(fp):
                continue
            result = scan_file(fp)
            if result['issues'] or (all_files and not result['binary']):
                result['relpath'] = os.path.relpath(fp, mod_dir)
                results.append(result)
    return results


def score_to_grade(score):
    if score >= 30:
        return 'F'
    if score >= 20:
        return 'D'
    if score >= 10:
        return 'C'
    if score >= 5:
        return 'B'
    if score >= 1:
        return 'A'
    return 'S'


def format_results(results):
    if not results:
        return '无发现问题'

    total_score = sum(r['summary']['score'] for r in results)
    total_high = sum(r['summary']['high'] for r in results)
    total_medium = sum(r['summary']['medium'] for r in results)
    lines = []
    lines.append(f'-- Mod 安全扫描报告 --')
    lines.append(f'   扫描文件: {len(results)}')
    lines.append(f'   安全问题: {total_high} 高 / {total_medium} 中 / {sum(r["summary"]["low"] for r in results)} 低')
    lines.append(f'   安全评分: {total_score} 分 (等级 {score_to_grade(total_score)})')
    for r in results:
        rel = r.get('relpath', os.path.basename(r['file']))
        s = r['summary']
        if r.get('binary'):
            desc = ' | '.join(d for _, _, d in r['issues'])
            lines.append(f'  [!] {rel} [二进制: {s["high"]}高/{s["medium"]}中] {desc}')
        elif s['total'] > 0:
            sev_tags = []
            for sev, label, _ in [('high', '高', ''), ('medium', '中', ''), ('low', '低', '')]:
                if s[sev] > 0:
                    sev_tags.append(f'{s[sev]} {label}')
            lines.append(f"  [{rel}] {' '.join(sev_tags)} 评分 {s['score']}")
            for lineno, weight, desc in r['issues'][:10]:
                sev = '高' if weight >= 8 else ('中' if weight >= 5 else ('低' if weight >= 2 else '信息'))
                loc = f'第{lineno}行' if lineno > 0 else ''
                lines.append(f'    [{sev}] {desc} {loc}')
            if len(r['issues']) > 10:
                lines.append(f'    ... 还有 {len(r["issues"]) - 10} 个问题')
        else:
            lines.append(f'  [OK] {rel} [安全]')

    return '\n'.join(lines)
