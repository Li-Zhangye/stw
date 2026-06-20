#!/usr/bin/env bash
# SMS2Web Android 编译脚本
# 用法: ./build.sh [release|debug]

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-release}"
LOG="$DIR/build_log.txt"

echo "[$(date '+%H:%M:%S')] 开始编译 ($MODE)" | tee "$LOG"

cd "$DIR"

# 检测 gradle wrapper
if [ ! -f "./gradlew" ]; then
    echo "[FAIL] 未找到 gradlew，生成中..."
    gradle wrapper 2>&1 | tee -a "$LOG"
fi

# 检查密钥库
KEYSTORE="$DIR/my-release-key.jks"
if [ ! -f "$KEYSTORE" ]; then
    echo "[WARN] 未找到密钥库，生成 debug 包..."
    echo "[WARN] 如需 release 包，创建密钥库:"
    echo "  keytool -genkey -v -keystore my-release-key.jks -keyalg RSA -keysize 2048 -validity 10000 -alias my-key"
    MODE="debug"
fi

# 检查环境变量
[ -z "$KEYSTORE_PASSWORD" ] && echo "[WARN] KEYSTORE_PASSWORD 未设置" | tee -a "$LOG"
[ -z "$KEY_PASSWORD" ] && echo "[WARN] KEY_PASSWORD 未设置" | tee -a "$LOG"

echo "[$(date '+%H:%M:%S')] 执行 ./gradlew assemble${MODE^}..." | tee -a "$LOG"
./gradlew "assemble${MODE^}" 2>&1 | tee -a "$LOG"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo "[OK] 编译成功" | tee -a "$LOG"
    APK=$(find "$DIR/app/build/outputs/apk/$MODE" -name "*.apk" 2>/dev/null | head -1)
    [ -n "$APK" ] && echo "[OK] APK: $APK" | tee -a "$LOG"
else
    echo "[FAIL] 编译失败，详情见 $LOG" | tee -a "$LOG"
    exit 1
fi
