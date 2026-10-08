# herdr1 —— Windows (Git Bash) 侧入口
# 默认使用共享/default Session；设置 mode=per-dir 才按目录隔离。
# 本文件可 source，也可安装为 ~/.local/bin/herdr1。
herdr1() {
    local win uname hash session mode status
    local max_lifetime=${LCMD_MAX_LIFETIME:-0}
    mode=single
    local mode_file="${HOME}/.config/herdr/session-mode"
    if [ -f "$mode_file" ]; then
        mode="$(grep -E '^[[:space:]]*mode[[:space:]]*=' "$mode_file" 2>/dev/null | tail -n 1 | cut -d= -f2- | tr -d '[:space:]')"
        [ -n "$mode" ] || mode=single
    fi
    session=""
    if [ "$mode" = per-dir ]; then
        win="$(cygpath -w "$PWD" 2>/dev/null || printf '%s' "$PWD")"
        uname="$(printf '%s' "$(basename "$(cygpath -u "$win" 2>/dev/null || printf '%s' "$PWD")")" | tr -cs '[:alnum:]_-' '-')"
        hash="$(printf '%s' "$win" | sha256sum | cut -c1-8)"
        session="${uname}-${hash}"
    fi
    (
        unset HERDR_SESSION HERDR_SOCKET_PATH HERDR_PANE_ID HERDR_TAB_ID HERDR_WORKSPACE_ID
        while true; do
            if [ -n "$session" ]; then
                if [ "$max_lifetime" -gt 0 ] 2>/dev/null; then
                    HERDR_SESSION="$session" timeout -s KILL "$max_lifetime" herdr "$@" <&0
                else
                    HERDR_SESSION="$session" herdr "$@" <&0
                fi
            elif [ "$max_lifetime" -gt 0 ] 2>/dev/null; then
                timeout -s KILL "$max_lifetime" herdr "$@" <&0
            else
                herdr "$@" <&0
            fi
            status=$?
            if [ "$status" -lt 128 ] || [ "$status" -eq 130 ] || [ "$status" -eq 143 ]; then return "$status"; fi
            if ! [ -t 0 ] || ! : >/dev/tty 2>/dev/null; then return "$status"; fi
            reset 2>/dev/null || stty sane 2>/dev/null || true
            sleep 1 2>/dev/null || return 0
        done
    )
}
herdr() { herdr1 "$@"; }
alias herdr-ls='command herdr session list'
alias herdr-open='command herdr session attach'
alias herdr-stop='command herdr session stop'
alias herdr-del='command herdr session delete'
if [ "${BASH_SOURCE[0]}" = "$0" ]; then herdr1 "$@"; exit $?; fi
