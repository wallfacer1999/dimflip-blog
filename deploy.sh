#!/bin/bash
set -e
export PATH="/bin:/sbin:/usr/bin:/usr/sbin:/opt/homebrew/bin:/usr/local/bin:$PATH"

NO_OPEN=0
DO_CLEAN=0

for arg in "$@"; do
  case "$arg" in
    --no-open) NO_OPEN=1 ;;
    --clean) DO_CLEAN=1 ;;
  esac
done

NAS_USER="Kkk-48shb_ah"
NAS_PASS=$(security find-generic-password -a "$NAS_USER" -s nas_mount -w)
NAS_IP="192.168.31.117"
NAS_SHARE="web"
MOUNT_PATH="/Volumes/web"
BLOG_PATH="/Users/linf/Documents/code/hexo-blog"
BLOG_URL="https://dimflip.xyz"

echo "🚀 检查 NAS 是否挂载..."

if mount | grep -q "$MOUNT_PATH"; then
    echo "✅ NAS 已挂载在 $MOUNT_PATH"
else
    echo "📂 尝试挂载 NAS 共享..."
    mkdir -p "$MOUNT_PATH"
    mount_smbfs "//$NAS_USER:$NAS_PASS@$NAS_IP/$NAS_SHARE" "$MOUNT_PATH"

    if mount | grep -q "$MOUNT_PATH"; then
        echo "✅ 挂载成功！"
    else
        echo "❌ 挂载失败，请检查 NAS 地址、用户名、密码"
        exit 1
    fi
fi

echo "📂 切换到 Hexo 博客目录..."
cd "$BLOG_PATH" || { echo "❌ 找不到博客目录！"; exit 1; }

if [ "$DO_CLEAN" -eq 1 ]; then
    echo "🧹 清理旧缓存..."
    hexo clean
fi

echo "⚙️ 生成博客静态文件..."
hexo g

echo "🚚 部署到 NAS 中..."
rsync -ahv --delete ./public/ "$MOUNT_PATH/"

echo "✅ 部署完成！"
echo "$BLOG_URL"

if [ "$NO_OPEN" -eq 0 ]; then
    open "$BLOG_URL"
fi
