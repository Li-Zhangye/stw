#!/usr/bin/env bash
set -e

AUTO=0
for arg in "$@"; do
    case "$arg" in -y|--yes|--auto|-f) AUTO=1 ;; esac
done

if [ -t 1 ]; then
    RED=$(printf '\033[91m'); GREEN=$(printf '\033[92m'); YELLOW=$(printf '\033[93m')
    CYAN=$(printf '\033[96m'); BOLD=$(printf '\033[1m'); RESET=$(printf '\033[0m')
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; RESET=''
fi
ok()   { printf "  %s[OK]%s %s\n" "$GREEN" "$RESET" "$1"; }
fail() { printf "  %s[FAIL]%s %s\n" "$RED" "$RESET" "$1"; }
warn() { printf "  %s[!]%s %s\n" "$YELLOW" "$RESET" "$1"; }
info() { printf "  %s[i]%s %s\n" "$CYAN" "$RESET" "$1"; }

HAS_TTY=0; [ -t 0 ] && HAS_TTY=1

read_input() {
    local var="$1" prompt="$2" default="$3" val
    if [ "$HAS_TTY" = "1" ]; then
        read -p "$prompt" val
    else
        read -p "$prompt" val </dev/tty
    fi
    [ -z "$val" ] && val="$default"
    printf -v "$var" "%s" "$val"
}

_yes_no() {
    local msg="$1" def="${2:-yes}" color="${3:-$BOLD}" ans prompt
    if [ "$def" = "yes" ]; then
        prompt="y/yes"
        local neg="n/no"
    else
        prompt="n/no"
        local neg="y/yes"
    fi
    printf "  %s[?]%s %s%s%s (%s, %s): " "$color" "$RESET" "$color" "$msg" "$RESET" "$prompt" "$neg"
    if [ "$HAS_TTY" = "1" ]; then
        read -r ans
    else
        read -r ans </dev/tty
    fi
    ans=$(echo "$ans" | tr '[:upper:]' '[:lower:]')
    [ -z "$ans" ] && ans="$def"
    [ "$ans" = "yes" ] || [ "$ans" = "y" ] || [ "$ans" = "true" ] || [ "$ans" = "1" ]
}

random_str()  { tr -dc 'A-Za-z0-9!@#$%' < /dev/urandom 2>/dev/null | head -c"${1:-12}" || echo "sms2web"; }
random_port() { shuf -i 1024-65000 -n 1 2>/dev/null || echo $(( RANDOM % 60000 + 1024 )); }

GITEE="https://gitee.com/li-zhangye/stw/raw/main"
GITHUB="https://raw.githubusercontent.com/Li-Zhangye/stw/refs/heads/main"

clear 2>/dev/null || true
echo ""
echo "短信转网页 (SMS2Web) 安装脚本"
echo ""

# ----- 1. 协议 -----
if [ "$AUTO" = "0" ]; then
    echo "阅读以下协议:"
    echo "  1. 本软件为开源免费软件，遵循 MIT 协议"
    echo "  2. 您自行承担使用本软件的一切风险和责任"
    echo "  3. 请勿将本软件用于非法用途"
    echo ""
    if ! _yes_no "是否同意上述协议?" "no" "$RED"; then
        echo ""
        fail "您拒绝了协议，安装终止"
        exit 1
    fi
fi

# ----- 2. 环境检测 -----
echo ""
info "检测系统环境..."

distro_id=""; distro_ver=""; distro_pretty=""; distro_codename=""
pkg_update=""; pkg_install=""
if [ -f /etc/os-release ]; then
    . /etc/os-release
    distro_id="$ID"; distro_ver="$VERSION_ID"; distro_pretty="$PRETTY_NAME"
    distro_codename="$VERSION_CODENAME"
fi
arch=$(uname -m)

if [ -z "$distro_codename" ] && [ -f /etc/debian_version ]; then
    case "$distro_ver" in
        14|14.*) distro_codename="forky" ;;
        13|13.*) distro_codename="trixie" ;;
        12|12.*) distro_codename="bookworm" ;;
        11|11.*) distro_codename="bullseye" ;;
        10|10.*) distro_codename="buster" ;;
        9|9.*)   distro_codename="stretch" ;;
    esac
fi

is_termux=0
[ -n "$PREFIX" ] && [ -d "$PREFIX" ] && is_termux=1

echo "  系统: ${distro_pretty:-$(uname -s)} $arch"
[ -n "$distro_codename" ] && echo "  版本代号: $distro_codename"

DEBIAN_CODES="stretch buster bullseye bookworm trixie forky"
UBUNTU_CODES="focal jammy noble oracular plucky torvalds"
ALL_CODES="$DEBIAN_CODES $UBUNTU_CODES"

case "$distro_id" in
    debian|ubuntu)
        pkg_update="apt-get update -y"
        pkg_install="apt-get install -y"
        if [ -n "$distro_codename" ]; then
            ok "系统已识别: $distro_id $distro_ver ($distro_codename)"
        fi
        apt_files=""
        [ -f /etc/apt/sources.list ] && apt_files="/etc/apt/sources.list"
        if [ -d /etc/apt/sources.list.d ]; then
            for f in /etc/apt/sources.list.d/*.list; do
                [ -f "$f" ] && apt_files="$apt_files $f"
            done
        fi
        found_wrong=""
        for sf in $apt_files; do
            while IFS= read -r line; do
                case "$line" in
                    \#*) continue ;;
                    *)
                        for code in $ALL_CODES; do
                            if [ "$code" != "$distro_codename" ] && echo "$line" | grep -qw "$code" 2>/dev/null; then
                                found_wrong="$code"
                                break 2
                            fi
                        done
                        ;;
                esac
            done < "$sf"
            [ -n "$found_wrong" ] && break
        done
        if [ -n "$found_wrong" ]; then
            warn "软件源包含版本 \"$found_wrong\"，当前系统为 \"$distro_codename\"，可能导致 apt 安装失败"
            if _yes_no "是否备份并替换 sources.list 中的版本代号为 $distro_codename?" "no"; then
                bak_dir="/etc/apt/sources.list.d/backup"
                mkdir -p "$bak_dir" 2>/dev/null || bak_dir="/root/apt_backup"
                mkdir -p "$bak_dir" 2>/dev/null || true
                for sf in $apt_files; do
                    [ ! -f "$sf" ] && continue
                    cp "$sf" "$bak_dir/$(basename "$sf").bak" 2>/dev/null && info "已备份: $sf"
                    sed -i "s/\b$found_wrong\b/$distro_codename/g" "$sf" 2>/dev/null && info "已修复: $sf"
                done
                info "修复完成，建议执行: apt update"
            fi
        fi
        ;;
    centos|rhel|fedora|almalinux|rocky)
        pkg_update="dnf makecache -y"
        pkg_install="dnf install -y"
        command -v dnf >/dev/null 2>&1 || { pkg_update="yum makecache -y"; pkg_install="yum install -y"; }
        ;;
    alpine)
        pkg_update="apk update"
        pkg_install="apk add"
        ;;
    arch|manjaro)
        pkg_update="pacman -Sy"
        pkg_install="pacman -S --noconfirm"
        ;;
    opensuse*|suse)
        pkg_update="zypper refresh"
        pkg_install="zypper install -y"
        ;;
    *)
        if command -v apt-get >/dev/null 2>&1; then
            pkg_update="apt-get update -y"; pkg_install="apt-get install -y"
        elif command -v dnf >/dev/null 2>&1; then
            pkg_update="dnf makecache -y"; pkg_install="dnf install -y"
        elif command -v apk >/dev/null 2>&1; then
            pkg_update="apk update"; pkg_install="apk add"
        fi
        ;;
esac

if [ -z "$pkg_install" ]; then
    fail "不支持当前系统，请手动安装 python3 后重试"
    exit 1
fi
ok "包管理器: $(echo "$pkg_install" | awk '{print $1}')"

# ----- 3. 安装系统依赖 -----
info "检查系统依赖..."
need_install=""
python_cmd=""
for cmd in python3 python; do
    command -v "$cmd" >/dev/null 2>&1 && { python_cmd="$cmd"; break; }
done
[ -z "$python_cmd" ] && need_install="$need_install python3"
for cmd in curl wget; do
    command -v "$cmd" >/dev/null 2>&1 && { dl_cmd="$cmd"; break; }
done
[ -z "$dl_cmd" ] && need_install="$need_install curl"

if [ -n "$need_install" ]; then
    warn "需要安装:${need_install}"
    $pkg_update
    $pkg_install $need_install
    for cmd in python3 python; do
        command -v "$cmd" >/dev/null 2>&1 && { python_cmd="$cmd"; break; }
    done
    if [ -z "$python_cmd" ]; then
        fail "Python 安装失败，请手动安装"
        exit 1
    fi
fi

py_ver=$($python_cmd --version 2>&1 | grep -oP '\d+\.\d+')
if [ -n "$py_ver" ]; then
    major="${py_ver%.*}"; minor="${py_ver#*.}"
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 8 ]; }; then
        fail "Python $py_ver 版本过低，需要 3.8+"
        exit 1
    fi
fi
ok "Python: $($python_cmd --version 2>&1)"
PYTHON="$python_cmd"

# 检查 Python sqlite3 模块
if ! $PYTHON -c "import sqlite3" 2>/dev/null; then
    warn "Python sqlite3 模块缺失"
    case "$distro_id" in
        debian|ubuntu) $pkg_update; $pkg_install python3-pip ;;
        alpine) $pkg_install py3-sqlite3 ;;
    esac
    if ! $PYTHON -c "import sqlite3" 2>/dev/null; then
        fail "无法安装 sqlite3 模块，请手动安装"
        exit 1
    fi
    ok "sqlite3 模块已安装"
fi

# ----- 3.5 安装 openssl 命令行工具 -----
if ! command -v openssl >/dev/null 2>&1; then
    can_install=0
    if [ "$AUTO" = "0" ]; then
        _yes_no "openssl 未安装，是否安装?(用于生成 SSL 证书)" "yes" && can_install=1
    else
        can_install=1
    fi
    if [ "$can_install" = "1" ]; then
        $pkg_update 2>/dev/null || true
        if [ "$is_termux" = "1" ]; then
            # Termux: openssl 二进制在 openssl-tool 包
            if ! $pkg_install openssl-tool 2>/dev/null; then
                warn "安装 openssl-tool 失败，尝试切换 Termux 镜像为清华源..."
                cp "$PREFIX/etc/apt/sources.list" "$PREFIX/etc/apt/sources.list.bak" 2>/dev/null || true
                sed -i 's@^\(deb.*stable main\)$@#\1\ndeb https://mirrors.tuna.tsinghua.edu.cn/termux/termux-packages-24 stable main@' "$PREFIX/etc/apt/sources.list"
                $pkg_update 2>/dev/null || true
                $pkg_install openssl-tool 2>/dev/null || $pkg_install openssl 2>/dev/null || true
            fi
        else
            $pkg_install openssl 2>/dev/null || true
        fi
    fi
fi

# ----- 4. 选择下载节点 -----
echo ""
info "选择下载节点..."

location=""
if command -v curl >/dev/null 2>&1; then
    location=$(curl -fL -s --connect-timeout 5 "https://ipapi.co/country" 2>/dev/null || echo "")
fi
if [ -z "$location" ] && command -v wget >/dev/null 2>&1; then
    location=$(wget -qO- --timeout=5 "https://ipapi.co/country" 2>/dev/null || echo "")
fi

rec_gitee=0; rec_github=0
case "$location" in
    CN|HK|MO|TW) rec_gitee=1 ;;
    *)            rec_github=1 ;;
esac

echo "  请选择下载源码的节点:"
if [ "$rec_gitee" = "1" ]; then
    echo "    1) Gitee (国内)  ← 推荐"
else
    echo "    1) Gitee (国内)"
fi
if [ "$rec_github" = "1" ]; then
    echo "    2) GitHub (国际)  ← 推荐"
else
    echo "    2) GitHub (国际)"
fi

if [ "$AUTO" = "1" ]; then
    [ "$rec_gitee" = "1" ] && node_choice=1 || node_choice=2
else
    read_input node_choice "  选择 (1/2): " "${rec_gitee:-0}"
fi

case "$node_choice" in
    1) source_url="$GITEE"; fallback_url="$GITHUB"; ok "节点: Gitee (国内)" ;;
    2) source_url="$GITHUB"; fallback_url="$GITEE"; ok "节点: GitHub (国际)" ;;
    *) fail "无效选择"; exit 1 ;;
esac

# ----- 5. 安装目录 -----
echo ""
[ "$is_termux" = "1" ] && default_dir="$HOME/stw" || default_dir="/opt/stw"
if [ "$AUTO" = "1" ]; then
    target_dir="$default_dir"
else
    read_input target_dir "安装目录 [$default_dir]: " "$default_dir"
fi

DATA_SUBDIR="tmp/data"  # 用户数据在 $target_dir/$DATA_SUBDIR 下

# ----- 5.5 检测已有安装 + 数据备份 -----
if [ -f "$target_dir/stw" ] && [ -f "$target_dir/server/server.py" ]; then
    echo ""
    warn "检测到已有安装: $target_dir"
    if [ "$AUTO" = "0" ]; then
        if ! _yes_no "是否删除并重新安装?" "no" "$RED"; then
            info "已取消"
            exit 0
        fi
        if _yes_no "是否保留现有数据?(config/database/邮件配置/SSL证书/美化配置)" "yes"; then
            backup_dir="/tmp/stw-backup-$$"
            info "备份数据到 $backup_dir ..."
            if [ -d "$target_dir/$DATA_SUBDIR" ]; then
                mkdir -p "$backup_dir/data"
                cp -r "$target_dir/$DATA_SUBDIR"/* "$backup_dir/data/" 2>/dev/null || true
                ok "数据已备份"
            fi
            if [ -d "$target_dir/mod" ]; then
                mkdir -p "$backup_dir/mod"
                cp -r "$target_dir/mod"/* "$backup_dir/mod/" 2>/dev/null || true
                ok "mod 已备份"
            fi
        fi
        echo ""
        info "删除旧安装..."
    fi
    rm -rf "$target_dir" 2>/dev/null || true
    mkdir -p "$target_dir"
fi

# ----- 6. 端口配置 -----
echo ""
u_port=19672
a_port=19673
if [ "$AUTO" = "0" ]; then
    read_input _tmp "用户端端口 (1-65535) [$u_port]: " "$u_port"
    u_port="$_tmp"
    read_input _tmp "管理端端口 (1-65535) [$a_port]: " "$a_port"
    a_port="$_tmp"
fi

# ----- 7. 管理员配置 -----
echo ""
admin_user=$(random_str 8)
admin_pass=$(random_str 16)
if [ "$AUTO" = "0" ]; then
    read_input _tmp "管理员用户名 [$admin_user]: " "$admin_user"
    admin_user="$_tmp"
    read_input _tmp "管理员密码 (回车随机生成): " ""
    if [ -n "$_tmp" ]; then
        admin_pass="$_tmp"
        while [ ${#admin_pass} -lt 8 ]; do
            warn "密码至少8位"
            read_input admin_pass "管理员密码: " "$(random_str 16)"
        done
    fi
fi

# ----- 8. SSL -----
echo ""
ssl_enabled=1
if [ "$AUTO" = "0" ]; then
    if ! _yes_no "是否启用 HTTPS（自签名证书）?" "yes"; then
        ssl_enabled=0
    fi
fi

# ----- 9. 确认 -----
if [ "$AUTO" = "0" ]; then
    echo ""
    echo "安装配置:"
    echo "  安装目录: $target_dir"
    echo "  用户端口: $u_port"
    echo "  管理端口: $a_port"
    echo "  管理员:   $admin_user"
    echo "  HTTPS:    $([ "$ssl_enabled" = "1" ] && echo "是" || echo "否")"
    echo ""
    if ! _yes_no "确认安装?" "yes"; then
        info "安装已取消"
        exit 0
    fi
fi
echo ""

# ----- 10. 下载 -----
info "安装位置: $target_dir"
mkdir -p "$target_dir"
cd "$target_dir"

info "下载源码包..."
dl_ok=1
if command -v curl >/dev/null 2>&1; then
    curl -fL --progress-bar "$source_url/stw.tar.gz" -o "stw.tar.gz" && dl_ok=0
    [ "$dl_ok" != "0" ] && { curl -fL --progress-bar "$fallback_url/stw.tar.gz" -o "stw.tar.gz" && dl_ok=0; }
else
    wget --show-progress "$source_url/stw.tar.gz" -O "stw.tar.gz" && dl_ok=0
    [ "$dl_ok" != "0" ] && { wget --show-progress "$fallback_url/stw.tar.gz" -O "stw.tar.gz" && dl_ok=0; }
fi
if [ "$dl_ok" != "0" ]; then
    fail "下载失败，请检查网络"
    exit 1
fi
ok "下载完成"
tar xzf "stw.tar.gz" || { fail "解压失败"; exit 1; }
rm -f "stw.tar.gz"
ok "解压完成"

# 恢复备份
if [ -n "$backup_dir" ] && [ -d "$backup_dir/data" ]; then
    info "恢复备份数据..."
    mkdir -p "$target_dir/$DATA_SUBDIR"
    cp -r "$backup_dir/data"/* "$target_dir/$DATA_SUBDIR/" 2>/dev/null || true
    ok "数据已恢复"
    if [ -d "$backup_dir/mod" ]; then
        cp -r "$backup_dir/mod"/* "$target_dir/mod/" 2>/dev/null || true
        ok "mod 已恢复"
    fi
    rm -rf "$backup_dir"
fi

# ----- 11. 目录准备 -----
for d in tmp/data mod/public mod/server mod/plugins; do
    mkdir -p "$d" 2>/dev/null
done

# ----- 12. 生成配置 (仅缺失时生成) -----
need_managers=0; need_config=0
[ ! -f "$target_dir/$DATA_SUBDIR/managers.json" ] && need_managers=1
[ ! -f "$target_dir/$DATA_SUBDIR/config.json" ] && need_config=1

if [ "$need_managers" = "1" ]; then
    if ! $PYTHON -c "
import hashlib, secrets, sys, os, json, time
pwd = sys.argv[1]
salt = secrets.token_hex(16)
h = hashlib.pbkdf2_hmac('sha256', pwd.encode(), salt.encode(), 600000).hex()
stored = salt + ':' + h

data_dir = os.path.join(os.getcwd(), 'tmp', 'data')
os.makedirs(data_dir, exist_ok=True)
managers = [{
    'username': sys.argv[2],
    'password_hash': stored,
    'level': 3,
    'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'created_by': 'system'
}]
mp = os.path.join(data_dir, 'managers.json')
json.dump(managers, open(mp, 'w'), ensure_ascii=False, indent=2)
os.chmod(mp, 0o600)
" "$admin_pass" "$admin_user"; then
        fail "生成管理人员失败"
        exit 1
    fi
fi

if [ "$need_config" = "1" ]; then
    $PYTHON -c "
import json,sys
d = {
  'force_user_port': int(sys.argv[1]),
  'force_admin_port': int(sys.argv[2]),
  'registration_enabled': True,
  'daily_sms_limit': 0,
  'language': 'zh'
}
json.dump(d, open('tmp/data/config.json','w'), indent=2, ensure_ascii=False)
" "$u_port" "$a_port"
fi

# 如果 SSL 开启且 config 已存在（恢复备份），更新 ssl_enabled 字段
if [ "$ssl_enabled" = "1" ] && [ -f "$target_dir/$DATA_SUBDIR/config.json" ]; then
    $PYTHON -c "
import json
d = json.load(open('tmp/data/config.json'))
if d.get('ssl_enabled') != True:
    d['ssl_enabled'] = True
    json.dump(d, open('tmp/data/config.json','w'), indent=2, ensure_ascii=False)
"
fi

if [ "$ssl_enabled" = "1" ]; then
    cert_dir="$target_dir/$DATA_SUBDIR/ssl"
    mkdir -p "$cert_dir"

    if command -v openssl >/dev/null 2>&1; then
        ok "openssl 就绪"
        if [ -f "$cert_dir/server.key" ] && [ -f "$cert_dir/server.crt" ]; then
            ok "SSL 证书已存在，跳过生成"
        else
            if openssl req -x509 -newkey rsa:2048 \
                -keyout "$cert_dir/server.key" \
                -out "$cert_dir/server.crt" \
                -days 3650 -nodes \
                -subj "/CN=SMS2Web/O=SMS2Web/C=CN"; then
                ok "SSL 自签名证书已生成"
            else
                warn "openssl 生成证书失败，将使用 HTTP"
                ssl_enabled=0
            fi
        fi
    else
        warn "openssl 不可用，将使用 HTTP"
        ssl_enabled=0
    fi
fi

# CA 证书（SSL 连接验证）
info "检查 CA 证书..."
if $PYTHON -c "import ssl; ssl.create_default_context()" 2>/dev/null; then
    ok "CA 证书就绪"
else
    warn "CA 证书未安装，尝试安装..."
    for pkg in ca-certificates ca-certificates-bundle; do
        $pkg_install "$pkg" >/dev/null 2>&1 && break || true
    done
    if $PYTHON -c "import ssl; ssl.create_default_context()" 2>/dev/null; then
        ok "CA 证书已安装"
    else
        warn "CA 证书未安装，SSL 连接验证可能失败（不影响服务端 HTTPS 运行）"
    fi
fi

proto="http"
[ "$ssl_enabled" = "1" ] && proto="https"

detect_ip() {
    for cmd in "hostname -I" "ip addr show 2>/dev/null | grep 'inet ' | grep -v 127.0.0.1 | awk '{print \$2}' | cut -d/ -f1 | head -1" "curl -fsL --connect-timeout 3 ifconfig.me 2>/dev/null" "wget -qO- --timeout=3 ifconfig.me 2>/dev/null"; do
        local ip
        ip=$(eval "$cmd" 2>/dev/null | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -1)
        [ -n "$ip" ] && { echo "$ip"; return; }
    done
    echo ""
}
server_ip=$(detect_ip)
cat > "$target_dir/$DATA_SUBDIR/admin_credentials.txt" << EOF
============================================
  短信转网页 - 管理控制台账号信息
============================================
  安装目录: $target_dir
  用户端口: $u_port
  管理端口: $a_port
  $( [ -n "$server_ip" ] && echo " 服务器IP: $server_ip" )
  用户名:   $admin_user
  密  码:   $admin_pass
============================================
  $( [ -n "$server_ip" ] && echo "管理后台: ${proto}://${server_ip}:$a_port/console.html" || echo "管理后台: 端口 $a_port" )
  $( [ -n "$server_ip" ] && echo "用户端:   ${proto}://${server_ip}:$u_port/" || echo "用户端:   端口 $u_port" )
============================================
  提示: 运行 stw 进入管理菜单
============================================
EOF

# ----- 13. 注册 stw 命令 -----
if [ "$is_termux" = "1" ]; then
    mkdir -p "$PREFIX/bin" 2>/dev/null || true
    ln -sf "$target_dir/stw" "$PREFIX/bin/stw" 2>/dev/null || true
else
    if [ -f "/usr/local/bin/stw" ]; then
        linked=$(readlink "/usr/local/bin/stw" 2>/dev/null || echo "")
        [ "$linked" != "$target_dir/stw" ] && ln -sf "$target_dir/stw" /usr/local/bin/stw 2>/dev/null || true
    else
        ln -sf "$target_dir/stw" /usr/local/bin/stw 2>/dev/null || true
    fi
fi

# ----- 14. 防火墙 -----
echo ""
if [ "$AUTO" = "0" ]; then
    if _yes_no "是否放行防火墙端口? (用户端:$u_port 管理端:$a_port)" "yes"; then
        do_fw=1
    else
        do_fw=0
    fi
else
    do_fw=1
fi
if [ "$do_fw" = "1" ]; then
    info "放行端口..."
    if command -v ufw >/dev/null 2>&1; then
        ufw allow "$u_port/tcp" 2>/dev/null && ok "ufw 已放行 $u_port" || warn "ufw 放行失败"
        ufw allow "$a_port/tcp" 2>/dev/null && ok "ufw 已放行 $a_port" || warn "ufw 放行失败"
    elif command -v firewall-cmd >/dev/null 2>&1; then
        firewall-cmd --permanent --add-port="$u_port/tcp" 2>/dev/null
        firewall-cmd --permanent --add-port="$a_port/tcp" 2>/dev/null
        firewall-cmd --reload 2>/dev/null && ok "firewalld 已放行端口 ($u_port, $a_port)" || warn "firewalld 放行失败"
    elif command -v iptables >/dev/null 2>&1; then
        iptables -A INPUT -p tcp --dport "$u_port" -j ACCEPT 2>/dev/null
        iptables -A INPUT -p tcp --dport "$a_port" -j ACCEPT 2>/dev/null
        ok "iptables 已放行端口 ($u_port, $a_port)" || warn "iptables 放行失败"
    else
        warn "未检测到防火墙工具，请手动放行端口: $u_port $a_port"
    fi
fi

# ----- 15. 启动服务 -----
echo ""
info "启动服务..."
cd "$target_dir"
DATA_DIR="$target_dir/$DATA_SUBDIR" MOD_DIR="$target_dir/mod" nohup $PYTHON server/server.py > "$target_dir/$DATA_SUBDIR/server.log" 2>&1 &
spid=$!
echo "$spid" > "$target_dir/$DATA_SUBDIR/server.pid"
sleep 2
if kill -0 "$spid" 2>/dev/null; then
    ok "服务已启动 (PID $spid)"
else
    fail "服务启动失败，查看日志: $target_dir/$DATA_SUBDIR/server.log"
fi

# ----- 16. 完成 -----
echo ""
printf "%s安装完成%s\n" "$GREEN" "$RESET"
echo ""
echo "  安装目录: $target_dir"
echo "  端口: 用户端 $u_port / 管理端 $a_port"
echo "  用户名: $admin_user"
echo "  密  码: $admin_pass"
echo ""
info "凭据已保存: $target_dir/$DATA_SUBDIR/admin_credentials.txt"
echo ""
