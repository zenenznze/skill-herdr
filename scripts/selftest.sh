#!/usr/bin/env bash
# herdr-session.sh 自测：mock herdr/pi 断言 Session 选择、模式切换与 stdin 到达。
# 用法：./scripts/selftest.sh   （全部通过输出 ALL PASS，任一失败非零退出）
set -euo pipefail
# 自测必须与调用者所在 Herdr pane 隔离，避免继承真实 pane 身份污染“Pane 外裸 pi”断言。
unset HERDR_ENV HERDR_SOCKET_PATH HERDR_PANE_ID HERDR_TAB_ID HERDR_WORKSPACE_ID HERDR_SESSION

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNIPPET="$ROOT/herdr-session.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/bin" "$TMP/home/.config/herdr" "$TMP/work/demo"

# mock：打印关键事实（HERDR_SESSION 是否设置、参数、fd0 指向），不启动真实 herdr
cat > "$TMP/bin/herdr" <<'MOCK'
#!/usr/bin/env bash
if [ "$*" = "api snapshot" ]; then
    # Snapshot is only needed by the per-dir attach test; pi binding must not query it.
    printf '%s\n' '{"result":{"snapshot":{"panes":[]}}}'
    exit 0
fi
if [ "${1-}" = "--herdr-test-env" ]; then
    printf 'env=HERDR_ENV=%s;socket=%s;pane=%s;tab=%s;workspace=%s;session=%s\n' \
        "${HERDR_ENV-UNSET}" "${HERDR_SOCKET_PATH-UNSET}" "${HERDR_PANE_ID-UNSET}" \
        "${HERDR_TAB_ID-UNSET}" "${HERDR_WORKSPACE_ID-UNSET}" "${HERDR_SESSION-UNSET}"
    exit 0
fi
echo "session=${HERDR_SESSION-UNSET}"
echo "args=$*"
echo "fd0=$(readlink /proc/$$/fd/0)"
MOCK
cat > "$TMP/bin/pi" <<'MOCK'
#!/usr/bin/env bash
if [ "${1-}" = "--herdr-test-env" ]; then
    printf 'env=HERDR_ENV=%s;socket=%s;pane=%s;tab=%s;workspace=%s\n' \
        "${HERDR_ENV-UNSET}" "${HERDR_SOCKET_PATH-UNSET}" "${HERDR_PANE_ID-UNSET}" \
        "${HERDR_TAB_ID-UNSET}" "${HERDR_WORKSPACE_ID-UNSET}"
    exit 0
fi
echo "pi args=$*"
MOCK
chmod +x "$TMP/bin/herdr" "$TMP/bin/pi"

run_in_shell() { # $1=额外断言用的 shell 片段；stdin 由调用方控制
    HOME="$TMP/home" PATH="$TMP/bin:$PATH" bash -c "
        source '$SNIPPET'
        $1
    "
}

pass=0
check() { # $1=描述 $2=实际 $3=期望
    if [ "$2" = "$3" ]; then
        pass=$((pass+1)); echo "ok: $1"
    else
        echo "FAIL: $1"; echo "  实际: $2"; echo "  期望: $3"; exit 1
    fi
}

expected_session() { # $1=路径 → <basename>-<sha256前8>
    local p="$1"
    echo "$(basename "$p")-$(printf '%s' "$p" | sha256sum | cut -c1-8)"
}

DEMO="$TMP/work/demo"
EXP="$(expected_session "$DEMO")"

# ── 1. 缺省（无模式文件）：single，共用默认 Session ──
out="$(cd "$DEMO" && run_in_shell 'herdr' </dev/null)"
check "缺省模式不设置 HERDR_SESSION" "$(printf '%s\n' "$out" | head -1)" "session=UNSET"
check "缺省模式参数透传（无附加参数）" "$(printf '%s\n' "$out" | sed -n 2p)" "args="

# ── 2. mode=single：不注入 HERDR_SESSION（用全局默认 Session）──
printf 'mode=single\n' > "$TMP/home/.config/herdr/session-mode"
out="$(cd "$DEMO" && run_in_shell 'herdr' </dev/null)"
check "single 模式不设置 HERDR_SESSION" "$(printf '%s\n' "$out" | head -1)" "session=UNSET"
check "single 模式参数仍透传" "$(printf '%s\n' "$out" | sed -n 2p)" "args="

# ── 3. mode=per-dir：按当前目录选命名 Session ──
cat > "$TMP/home/.config/herdr/session-mode" <<'EOF'
# 注释行
mode = per-dir
EOF
out="$(cd "$DEMO" && run_in_shell 'herdr' </dev/null)"
check "per-dir 模式选中 demo 命名 Session" "$(printf '%s\n' "$out" | head -1)" "session=$EXP"

# ── 4. 输入到达断言（AGENTS.md 红线）：后台任务的 fd0 必须是调用方 stdin，
#      而不是被非交互 bash 重定向成的 /dev/null ──
printf 'marker-input\n' > "$TMP/stdin-file"
out="$(cd "$DEMO" && run_in_shell 'herdr' < "$TMP/stdin-file")"
check "herdr 后台任务 fd0 = 调用方 stdin（非 /dev/null）" \
    "$(printf '%s\n' "$out" | tail -1)" \
    "fd0=$TMP/stdin-file"

# ── 5. 正常退出（0）不自愈空转：函数应立即返回 mock 的退出码 ──
code="$(HOME="$TMP/home" PATH="$TMP/bin:$PATH" bash -c "
    cd '$DEMO'
    source '$SNIPPET'
    herdr </dev/null
    echo \$?
" | tail -1)"
check "正常退出码透传（0）" "$code" "0"

# ── 6. pi 会话绑定：Pane ID 派生 --session-id，不依赖 herdr 快照 ──
expected_pane_sid() { # $1=pane id → herdr-<sha256前12>
    printf 'herdr-%s' "$(printf '%s' "$1" | sha256sum | cut -c1-12)"
}
rm -f "$TMP/home/.config/herdr/session-mode"   # 缺省 pi-resume=on
out="$(run_in_shell 'pi' </dev/null)"
check "Pane 外裸 pi 全新开始" "$(printf '%s\n' "$out" | head -1)" "pi args="
out="$(run_in_shell 'HERDR_PANE_ID=w7:p1 pi' </dev/null)"
check "Pane 内裸 pi 绑定 Pane 派生 session-id" "$(printf '%s\n' "$out" | head -1)" \
    "pi args=--session-id $(expected_pane_sid w7:p1)"
out="$(run_in_shell 'HERDR_PANE_ID=w8:p2 pi' </dev/null)"
check "不同 Pane 派生不同 session-id" "$(printf '%s\n' "$out" | head -1)" \
    "pi args=--session-id $(expected_pane_sid w8:p2)"
out="$(HOME="$TMP/home" PATH="$TMP/bin:$PATH" HERDR_PANE_ID=w9:p3 bash -c "
    source '$SNIPPET'
    unset HERDR_PANE_ID
    pi
")"
check "source 后清除 Pane 环境仍保留绑定" "$(printf '%s\n' "$out" | head -1)" \
    "pi args=--session-id $(expected_pane_sid w9:p3)"
out="$(HOME="$TMP/home" PATH="$TMP/bin:$PATH" HERDR_ENV=1 HERDR_SOCKET_PATH=/tmp/herdr.sock \
    HERDR_PANE_ID=w7:p1 HERDR_TAB_ID=t1 HERDR_WORKSPACE_ID=w1 bash -c "
    source '$SNIPPET'
    pi --herdr-test-env
")"
check "Pi integration 身份环境保留" "$out" \
    "env=HERDR_ENV=1;socket=/tmp/herdr.sock;pane=w7:p1;tab=t1;workspace=w1"
out="$(HOME="$TMP/home" PATH="$TMP/bin:$PATH" HERDR_ENV=1 HERDR_SOCKET_PATH=/tmp/herdr.sock \
    HERDR_PANE_ID=w7:p1 HERDR_TAB_ID=t1 HERDR_WORKSPACE_ID=w1 HERDR_SESSION=stale bash -c "
    source '$SNIPPET'
    herdr --herdr-test-env
" </dev/null)"
check "嵌套 herdr 不继承当前 Session 路由" "$out" \
    "env=HERDR_ENV=1;socket=UNSET;pane=UNSET;tab=UNSET;workspace=UNSET;session=UNSET"
out="$(run_in_shell 'HERDR_PANE_ID=w7:p1 pi foo -r' </dev/null)"
check "带参 pi 原样透传" "$(printf '%s\n' "$out" | head -1)" "pi args=foo -r"
out="$(run_in_shell 'pi -r' </dev/null)"
check "无参 flag 透传（pi -r 选历史）" "$(printf '%s\n' "$out" | head -1)" "pi args=-r"
printf 'mode=single\npi-resume=off\n' > "$TMP/home/.config/herdr/session-mode"
out="$(run_in_shell 'HERDR_PANE_ID=w7:p1 pi' </dev/null)"
check "pi-resume=off 关闭会话绑定" "$(printf '%s\n' "$out" | head -1)" "pi args="

# ── 7. 管理别名可用 ──
out="$(run_in_shell 'alias herdr-ls >/dev/null && alias herdr-open >/dev/null && alias herdr-stop >/dev/null && alias herdr-del >/dev/null && echo aliases-ok' </dev/null)"
check "Session 管理别名已定义" "$(printf '%s\n' "$out" | tail -1)" "aliases-ok"

# ── 8. 健康 client 默认不被定时强杀；仍允许显式启用 watchdog ──
check "herdr-session 默认禁用定时强杀" \
    "$(grep -c 'LCMD_MAX_LIFETIME:-0' "$ROOT/herdr-session.sh")" "2"
check "herdr1 默认禁用定时强杀" \
    "$(grep -c 'LCMD_MAX_LIFETIME:-0' "$ROOT/herdr1")" "1"
check "Windows herdr1 默认禁用定时强杀" \
    "$(grep -c 'LCMD_MAX_LIFETIME:-0' "$ROOT/windows-herdr1.sh")" "1"

# ── 9. 新 workspace + 独立 tab + Pi agent 编排：全 mock，不创建真实资源 ──
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! "$PYTHON_BIN" --version >/dev/null 2>&1; then
    PYTHON_BIN=python
fi
"$PYTHON_BIN" "$ROOT/scripts/test-start-pi-agent-workspace.py"
pass=$((pass+1))
echo "ok: Pi workspace agent 编排 mock 测试"

echo "ALL PASS ($pass checks)"
