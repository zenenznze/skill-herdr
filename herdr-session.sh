# herdr session 配置片段（Bash / Zsh 通用；由 install.sh 追加进 rc 标记块）
#
# 两种模式，由设备本地 ~/.config/herdr/session-mode 的 mode 键控制：
#   mode=single（缺省）只用唯一默认 Session，所有目录共用一个实例。
#                       配套 config.toml [terminal] new_cwd = "follow"（默认值）
#   mode=per-dir        每个目录固定进入同名命名 Session（<目录名>-<路径短哈希>），
#                       不同目录完全隔离。配套 config.toml [terminal] new_cwd = "current"
#
# 保存当前 Pane 上下文供 pi 会话绑定。
#
# 不要在这里清除 HERDR_* 身份变量：Herdr 官方 Pi integration 依赖
# HERDR_ENV、HERDR_SOCKET_PATH 和 HERDR_PANE_ID 把 PI_SESSION_FILE/ID 上报给
# Herdr，供 server/snapshot 冷恢复时执行精确的 `pi --session <path>`。
# 嵌套调用 herdr 时的路由变量只在 _herdr_run 的子 shell 内清除，避免把当前
# pane 的 Session 串给另一个 Herdr client，同时不破坏 agent identity 上报。
_HERDR_PARENT_PANE_ID="${HERDR_PANE_ID:-}"

# 读模式文件：<key> 的值；文件不存在或键缺失时返回 <default>
_herdr_config() {
    local f="$HOME/.config/herdr/session-mode" v=""
    if [ -f "$f" ]; then
        v="$(grep -E "^[[:space:]]*$1[[:space:]]*=" "$f" 2>/dev/null | tail -n 1 | cut -d= -f2- | tr -d '[:space:]')"
    fi
    printf '%s' "${v:-$2}"
}

herdr() {
    local path name hash session mode
    # 仅显式设置正数时定时重启；默认禁用，避免健康 client 每小时被强杀。
    local max_lifetime=${LCMD_MAX_LIFETIME:-0}
    mode="$(_herdr_config mode single)"
    session=""
    if [ "$mode" != "single" ]; then
        path="$(pwd -P)"
        name="$(printf '%s' "$(basename "$path")" | tr -cs '[:alnum:]_-' '-')"
        hash="$(printf '%s' "$path" | sha256sum | cut -c1-8)"
        session="${name}-${hash}"
    fi
    _herdr_run "$session" "$@"
}

# 自愈循环主体：$1 为目标 Session 名（空 = single 模式，用全局默认 Session），
# 其余参数原样透传给 herdr。
_herdr_run() {
    local session="$1"; shift
    local snap status herdr_pid watchdog_pid max_lifetime path
    max_lifetime=${LCMD_MAX_LIFETIME:-0}

    (
        # 在 herdr 窗格内调用时，清除指向当前 Session 的环境变量，
        # 保证严格按模式/当前目录选择或启动 Session（子 shell 内生效，不影响外层）。
        unset HERDR_SESSION HERDR_SOCKET_PATH HERDR_PANE_ID HERDR_TAB_ID HERDR_WORKSPACE_ID

        # 纯 attach（无参数）且 per-dir 模式时：若 Session 服务器已在运行、且没有标签页落在
        # 当前目录（残留 ~ 标签页 / 全部关完的状态），先补一个聚焦标签页，
        # 保证重新进入看到的就是当前目录，而不是恢复出来的旧目录。
        # single 模式不需要；默认 Session 恢复原有标签页即可。
        if [ "$#" -eq 0 ] && [ -n "$session" ]; then
            snap="$(HERDR_SESSION="$session" command herdr api snapshot 2>/dev/null)" || snap=""
            if [ -n "$snap" ] && ! printf '%s' "$snap" | grep -Fq "\"cwd\":\"$path\""; then
                HERDR_SESSION="$session" command herdr tab create --cwd "$path" --focus >/dev/null 2>&1 \
                    || HERDR_SESSION="$session" command herdr workspace create --cwd "$path" --focus >/dev/null 2>&1
            fi
        fi

        # 自愈循环（与 herdr1 脚本一致）：herdr 0.8.0 在终端被拆除时会因
        # stderr 写 EIO panic 成 SIGABRT（上游 herdrdev/herdr#2424），导致
        # 终端停在 raw 模式、画面冻结无法操作。被信号杀死后自动 reset 终端
        # 并在 1 秒内重连；正常退出不重启；终端已死（EIO）直接退出不空转；
        # sleep 期间按 Ctrl-C 可取消重连回到 shell；只有显式设置正数
        # LCMD_MAX_LIFETIME 时才由 watchdog SIGKILL（137）触发定时重连。
        # stdin 必须 <&0 保持终端：非交互 bash 会把后台任务的 stdin 重定向到
        # /dev/null，herdr 输入线程会 EOF 退出（2026-08-11 修复，见 herdr1 头注）。
        while true; do
            if [ -n "$session" ]; then
                HERDR_SESSION="$session" command herdr "$@" <&0 &
            else
                command herdr "$@" <&0 &
            fi
            herdr_pid=$!
            watchdog_pid=""
            if [ "$max_lifetime" -gt 0 ] 2>/dev/null; then
                (
                    sleep "$max_lifetime"
                    kill -KILL "$herdr_pid" 2>/dev/null
                ) </dev/null >/dev/null 2>&1 &
                watchdog_pid=$!
            fi
            wait "$herdr_pid"
            status=$?
            [ -n "$watchdog_pid" ] && kill "$watchdog_pid" 2>/dev/null
            if [ "$status" -lt 128 ] || [ "$status" -eq 130 ] || [ "$status" -eq 143 ]; then
                return "$status"
            fi
            if ! [ -t 0 ] || ! : >/dev/tty 2>/dev/null; then
                return "$status"
            fi
            reset 2>/dev/null || stty sane 2>/dev/null || true
            sleep 1 2>/dev/null || return 0
        done
    )
}

# 由 Pane ID 派生稳定的 pi session-id：同一个 Pane 恒定得到同一个 ID，
# 不同 Pane / 新建 Pane 得到不同 ID。pi 的 session 按工作目录存储，因此
# 实际隔离粒度是「目录 × Pane」。
_herdr_pane_session_id() {
    printf 'herdr-%s' "$(printf '%s' "$1" | sha256sum | cut -c1-12)"
}

# 正常恢复链（pi-resume=on）：在 herdr Pane 内裸启动 `pi` 等价于
# `pi --session-id herdr-<Pane派生ID>`——精确续本 Pane 在当前 Pi project
# bucket 中的会话（没有则新建），不会捡到同目录其他 Pane 的历史。
# Pi 的实际 session path 由官方 herdr-agent-state integration 上报给 Herdr；
# Herdr server / snapshot 冷恢复时由 native agent_session 指针恢复原会话。
# 因此这里的 session-id 是默认会话的确定性种子，不是唯一持久身份。
# 实际隔离粒度是「Pane × Pi project」；不把 cwd 再哈希进 ID。
# Pane 外裸 `pi` 全新开始；任何带参数的调用原样透传（pi -r 选历史 /
# pi --no-session 临时不开会话均不受影响）；`command pi` 绕过本包装。
pi() {
    if [ "$#" -gt 0 ]; then
        command pi "$@"
        return
    fi
    if [ "$(_herdr_config pi-resume on)" != "on" ]; then
        command pi
        return
    fi
    local pane="${_HERDR_PARENT_PANE_ID:-${HERDR_PANE_ID:-}}"
    if [ -z "$pane" ]; then
        command pi
        return
    fi
    command pi --session-id "$(_herdr_pane_session_id "$pane")"
}

# Session 管理快捷命令（command herdr 绕过包装函数，操作全局 Session 列表）
alias herdr-ls='command herdr session list'        # 查看所有 Session
alias herdr-open='command herdr session attach'    # 进入某个 Session: herdr-open <名称>
alias herdr-stop='command herdr session stop'      # 停止（保留状态）: herdr-stop <名称>
alias herdr-del='command herdr session delete'     # 彻底删除: herdr-del <名称>
