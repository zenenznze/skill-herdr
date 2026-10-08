#!/usr/bin/env bash
# herdr-config 幂等安装脚本
# 把 herdr-session.sh 追加到 ~/.bashrc（和存在的 ~/.zshrc），带标记块便于识别/卸载。
# 用法：
#   ./install.sh          # 首次安装（已安装则跳过）
#   ./install.sh --update # 删除旧标记块后重装最新片段（升级用）
set -euo pipefail

SNIPPET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SNIPPET="$SNIPPET_DIR/herdr-session.sh"
MARKER_BEGIN="# >>> herdr per-directory sessions >>>"
MARKER_END="# <<< herdr per-directory sessions <<<"
UPDATE_MODE=0
[ "${1:-}" = "--update" ] && UPDATE_MODE=1

if [ ! -f "$SNIPPET" ]; then
    echo "[herdr] 找不到 $SNIPPET" >&2
    exit 1
fi

install_into() {
    local rc="$1"
    if grep -qF "$MARKER_BEGIN" "$rc"; then
        if [ "$UPDATE_MODE" -eq 1 ]; then
            # 删除旧标记块（含标记行本身）后重装
            awk -v b="$MARKER_BEGIN" -v e="$MARKER_END" '
                $0==b {inblock=1; next}
                $0==e {inblock=0; next}
                inblock {next}
                {print}' "$rc" > "$rc.tmp" && mv "$rc.tmp" "$rc"
            echo "[herdr] $rc 已移除旧片段，重新安装…"
        else
            echo "[herdr] $rc 已安装过，跳过（--update 可重装最新片段）"
            return 0
        fi
    fi
    {
        echo ""
        echo "$MARKER_BEGIN"
        cat "$SNIPPET"
        echo "$MARKER_END"
    } >> "$rc"
    echo "[herdr] 已写入 $rc"
}

install_into "$HOME/.bashrc"
if [ -f "$HOME/.zshrc" ]; then
    install_into "$HOME/.zshrc"
fi

# 安装 herdr1 启动入口（LightOS WebShell 复制兼容，见 README）
if [ -f "$SNIPPET_DIR/herdr1" ]; then
    install -m 0755 "$SNIPPET_DIR/herdr1" "$HOME/.local/bin/herdr1"
    echo "[herdr] 已安装 $HOME/.local/bin/herdr1"
fi

# 设备本地模式文件（不覆盖已有配置）：mode=single|per-dir、pi-resume=on|off
# 缺省 single；需要按目录隔离的设备改成 mode=per-dir。
MODE_FILE="$HOME/.config/herdr/session-mode"
if [ ! -f "$MODE_FILE" ]; then
    mkdir -p "$(dirname "$MODE_FILE")"
    cat > "$MODE_FILE" <<'EOF'
# herdr 会话模式（每台设备本地各自一份，互不同步）
# mode=single   只用一个默认 Session（所有目录共用，缺省）
# mode=per-dir  每个目录一个命名 Session
mode=single

# 裸 pi 在 herdr Pane 内绑定该 Pane 自己的会话（Pane 派生 --session-id）
pi-resume=on
EOF
    echo "[herdr] 已创建 $MODE_FILE（按需编辑 mode 行切换模式）"
fi

# claude-1.0 旧入口兼容垫片（LightOS daemon 保存的 pane 命令仍是旧名）
if [ -f "$SNIPPET_DIR/claude-1.0" ]; then
    install -m 0755 "$SNIPPET_DIR/claude-1.0" "$HOME/.local/bin/claude-1.0"
    echo "[herdr] 已安装 $HOME/.local/bin/claude-1.0（旧入口兼容垫片）"
fi

echo "[herdr] 完成。执行 source ~/.bashrc（或新开终端）使配置生效。"
