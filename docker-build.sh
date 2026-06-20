#!/usr/bin/env bash
# ==============================================================
#  SMS2Web 多架构 Docker 构建脚本
#  支持: aarch64, x86_64, armv7l, i686
#  依赖: Docker + buildx (自动安装 QEMU binfmt)
# ==============================================================
set -e

NAME="sms2web"
VERSION="${1:-latest}"
PLATFORMS="${2:-linux/arm64,linux/amd64,linux/arm/v7,linux/386}"

echo ""
echo "  SMS2Web 多架构 Docker 构建"
echo "  版本: $VERSION, 平台: $PLATFORMS"
echo ""

# 创建构建器
BUILDER="sms2web-builder"
if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
    echo "[1/3] 创建 buildx 构建器..."
    docker buildx create --name "$BUILDER" --driver docker-container --bootstrap
fi
docker buildx use "$BUILDER"

# 启用 QEMU 模拟
echo "[2/3] 启用 QEMU 跨平台模拟..."
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes 2>/dev/null || true

# 构建并推送
echo "[3/3] 构建多架构镜像..."
docker buildx build \
    --platform "$PLATFORMS" \
    --tag "${NAME}:${VERSION}" \
    --tag "${NAME}:latest" \
    --push \
    -f Dockerfile \
    .

echo ""
echo "[完成] 多架构构建完成!"
echo "  镜像: ${NAME}:${VERSION}"
echo "  平台: $PLATFORMS"
