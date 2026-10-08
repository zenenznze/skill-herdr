#!/usr/bin/env bash
# 将指定 workspace 中的多个 pane 整理为一个 pane 一个 tab。
# 用法：scripts/panes-to-tabs.sh --current；或 scripts/panes-to-tabs.sh --workspace <workspace-id>。
# 要求：运行在 HERDR_ENV=1 的 Herdr pane 内；重复执行幂等且不切换焦点。
set -euo pipefail

usage() {
    cat >&2 <<'EOF'
用法：
  panes-to-tabs.sh --current
  panes-to-tabs.sh --workspace <workspace-id>
  panes-to-tabs.sh --workspace <workspace-id> --dry-run
EOF
}

workspace=""
dry_run=0
while (($#)); do
    case "$1" in
        --current)
            [[ -z "$workspace" ]] || { echo "不能同时指定 --current 和 workspace" >&2; exit 2; }
            workspace=current
            shift
            ;;
        --workspace)
            [[ $# -ge 2 ]] || { usage; exit 2; }
            [[ -z "$workspace" ]] || { echo "workspace 只能指定一次" >&2; exit 2; }
            workspace="$2"
            shift 2
            ;;
        --dry-run)
            dry_run=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage
            exit 2
            ;;
    esac
done

[[ "${HERDR_ENV:-}" = 1 ]] || {
    echo "必须在 Herdr 管理的 pane 内运行（HERDR_ENV=1）" >&2
    exit 1
}
command -v herdr >/dev/null 2>&1 || { echo "找不到 herdr" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "找不到 python3" >&2; exit 1; }
[[ -n "$workspace" ]] || { usage; exit 2; }

if [[ "$workspace" = current ]]; then
    current_json="$(herdr pane current --current)"
    workspace="$(printf '%s' "$current_json" | python3 -c '
import json, sys
pane = json.load(sys.stdin).get("result", {}).get("pane", {})
workspace = pane.get("workspace_id")
if not workspace:
    raise SystemExit("当前 pane 响应中没有 workspace_id")
print(workspace)
')"
fi

pane_json="$(herdr pane list --workspace "$workspace")"
tab_json="$(herdr tab list --workspace "$workspace")"
mapfile -t move_records < <(printf '%s' "$pane_json" | python3 -c '
import base64, json, sys

tabs = json.loads(sys.argv[1]).get("result", {}).get("tabs")
if not isinstance(tabs, list):
    raise SystemExit("tab list 响应中没有 tabs 数组")
tab_labels = {tab.get("tab_id"): tab.get("label", "") for tab in tabs}

panes = json.load(sys.stdin).get("result", {}).get("panes")
if not isinstance(panes, list):
    raise SystemExit("pane list 响应中没有 panes 数组")

kept = set()
for pane in panes:
    pane_id = pane.get("pane_id")
    tab_id = pane.get("tab_id")
    if not pane_id or not tab_id:
        raise SystemExit("pane list 中缺少 pane_id 或 tab_id")
    if tab_id in kept:
        labels = (pane.get("label", ""), tab_labels.get(tab_id, ""))
        encoded_labels = [base64.b64encode(value.encode()).decode() for value in labels]
        print("\t".join((pane_id, *encoded_labels)))
    else:
        kept.add(tab_id)
' "$tab_json")

decode_label() {
    if [[ -n "$1" ]]; then
        printf '%s' "$1" | base64 --decode
    fi
}

if ((dry_run)); then
    printf 'workspace=%s panes=%d to_new_tabs=%d\n' "$workspace" "$(printf '%s' "$pane_json" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["result"]["panes"]))')" "${#move_records[@]}"
    printf '%s\n' "${move_records[@]}"
    exit 0
fi

for record in "${move_records[@]}"; do
    IFS=$'\t' read -r pane_id pane_label_b64 tab_label_b64 <<< "$record"
    pane_label="$(decode_label "$pane_label_b64")"
    tab_label="$(decode_label "$tab_label_b64")"
    move_json="$(herdr pane move "$pane_id" --new-tab --workspace "$workspace" --no-focus)"
    read -r moved_pane_id new_tab_id < <(printf '%s' "$move_json" | python3 -c '
import json, sys
move = json.load(sys.stdin).get("result", {}).get("move_result", {})
pane_id = move.get("pane", {}).get("pane_id")
tab_id = move.get("created_tab", {}).get("tab_id")
if not pane_id or not tab_id:
    raise SystemExit("pane move 响应中缺少移动后的 pane_id 或新 tab_id")
print(pane_id, tab_id)
')
    if [[ -n "$pane_label" ]]; then
        herdr pane rename "$moved_pane_id" "$pane_label" >/dev/null
    fi
    if [[ -n "$tab_label" ]]; then
        herdr tab rename "$new_tab_id" "$tab_label" >/dev/null
    fi
done

final_json="$(herdr tab list --workspace "$workspace")"
printf '%s' "$final_json" | python3 -c '
import json, sys

tabs = json.load(sys.stdin).get("result", {}).get("tabs")
if not isinstance(tabs, list):
    raise SystemExit("tab list 响应中没有 tabs 数组")
invalid = [tab.get("tab_id", "?") for tab in tabs if tab.get("pane_count") != 1]
if invalid:
    raise SystemExit("仍有多 pane tab: " + ", ".join(invalid))
print(f"workspace={sys.argv[1]} tabs={len(tabs)} moved={sys.argv[2]}")
' "$workspace" "${#move_records[@]}"
