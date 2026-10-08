#!/usr/bin/env python3
# 按目录归属 workspace 并直接执行整批整理；显式传 --dry-run 时只预览。
# 用法：scripts/organize-panes-by-directory.py --all [--dry-run]。
# 范围：裸“整理”使用 --all；仅用户明确限定当前 workspace 时才使用 --current。
# 要求：运行在 HERDR_ENV=1 的 Herdr pane 内；移动和新建使用完整计划统一执行并验证。
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath


def cli(*args):
    try:
        completed = subprocess.run(
            ["herdr", *args], check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        if exc.stderr:
            print(exc.stderr.rstrip(), file=sys.stderr)
        raise SystemExit(exc.returncode or 1)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"herdr 返回不是有效 JSON: {exc}") from exc


def result(payload, key):
    value = payload.get("result", {}).get(key)
    if value is None:
        raise SystemExit(f"herdr 响应中缺少 result.{key}")
    return value


def directory_label(cwd):
    if PureWindowsPath(cwd).drive:
        return PureWindowsPath(cwd).name or "root"
    return Path(os.path.normpath(cwd)).name or "root"


def path_label(cwd):
    """Return a readable workspace label derived from the full path."""
    if PureWindowsPath(cwd).drive:
        path = PureWindowsPath(cwd)
        parts = [path.drive.rstrip(":\\/")] + [part for part in path.parts[1:] if part not in ("\\", "/")]
    else:
        path = PurePosixPath(cwd)
        parts = [part for part in path.parts if part != "/"]
    readable = "-".join(part.replace(":", "") for part in parts if part)
    return readable or "root"


def discover(source_workspace_ids=None):
    """Build one plan for one workspace or the entire Herdr instance.

    ``None`` means the entire instance.  Keeping the complete workspace list in
    the plan is important: a directory may already have a target workspace in
    another source workspace, and a partial scan would incorrectly report a
    complete organization.
    """
    workspace_list = result(cli("workspace", "list"), "workspaces")
    if not isinstance(workspace_list, list):
        raise SystemExit("workspace list 响应中没有 workspaces 数组")
    by_label = {}
    for workspace in workspace_list:
        workspace_id = workspace.get("workspace_id")
        label = workspace.get("label")
        if not workspace_id or not label:
            raise SystemExit("workspace list 中缺少 workspace_id 或 label")
        by_label.setdefault(label, []).append(workspace)

    def workspace_order(workspace):
        number = workspace.get("number")
        return (number if isinstance(number, int) else sys.maxsize,
                workspace["workspace_id"])

    # 同名 workspace 保留编号最小（通常也是最早创建）的一个；其余 workspace
    # 的 pane 全部移入保留项，并在迁移后清理空壳。workspace_id 只用于稳定打破平局。
    canonical_by_label = {
        label: min(matches, key=workspace_order)
        for label, matches in by_label.items()
    }

    if source_workspace_ids is None:
        sources = workspace_list
    else:
        wanted = set(source_workspace_ids)
        sources = [w for w in workspace_list if w.get("workspace_id") in wanted]
        missing_sources = wanted - {w.get("workspace_id") for w in sources}
        if missing_sources:
            raise SystemExit(f"找不到源 workspace: {', '.join(sorted(missing_sources))}")

    pane_records = []
    paths_by_base = {}
    for source in sources:
        source_workspace_id = source["workspace_id"]
        tabs = result(cli("tab", "list", "--workspace", source_workspace_id), "tabs")
        if not isinstance(tabs, list):
            raise SystemExit("tab list 响应中没有 tabs 数组")
        tab_labels = {}
        for tab in tabs:
            tab_id = tab.get("tab_id")
            if not tab_id:
                raise SystemExit("tab list 中缺少 tab_id")
            tab_labels[tab_id] = tab.get("label", "")

        panes = result(cli("pane", "list", "--workspace", source_workspace_id), "panes")
        if not isinstance(panes, list):
            raise SystemExit("pane list 响应中没有 panes 数组")
        for pane in sorted(panes, key=lambda item: item.get("pane_id", "")):
            pane_id = pane.get("pane_id")
            cwd = pane.get("cwd")
            tab_id = pane.get("tab_id")
            if not pane_id or not cwd or not tab_id:
                raise SystemExit("pane list 中缺少 pane_id、cwd 或 tab_id")
            base = directory_label(cwd)
            pane_records.append((
                source_workspace_id,
                pane_id,
                cwd,
                base,
                pane.get("label", ""),
                tab_labels.get(tab_id, ""),
            ))
            paths_by_base.setdefault(base, set()).add(cwd)

    def target_label(cwd, base):
        # 同名目录来自不同路径时，直接用可读的完整路径区分；不得追加哈希代码。
        if len(paths_by_base[base]) > 1:
            return path_label(cwd)
        return base

    actions = []
    missing = {}
    for (source_workspace_id, pane_id, cwd, base, pane_label,
         source_tab_label) in pane_records:
        workspace_label = target_label(cwd, base)
        matching = by_label.get(workspace_label, [])
        target = canonical_by_label.get(workspace_label) if matching else None
        if target is None:
            missing.setdefault(workspace_label, cwd)
            target_id = None
        else:
            target_id = target["workspace_id"]
        if target_id != source_workspace_id:
            actions.append({
                "type": "move_pane",
                "pane_id": pane_id,
                "cwd": cwd,
                "from_workspace_id": source_workspace_id,
                "to_workspace_id": target_id,
                "to_workspace_label": workspace_label,
                "pane_label": pane_label,
                "target_pane_label": workspace_label,
                "source_tab_label": source_tab_label,
            })
        elif pane_label != workspace_label:
            actions.append({
                "type": "rename_pane",
                "pane_id": pane_id,
                "cwd": cwd,
                "workspace_id": source_workspace_id,
                "from_pane_label": pane_label,
                "pane_label": workspace_label,
            })

    for label, cwd in sorted(missing.items()):
        actions.insert(0, {
            "type": "create_workspace",
            "cwd": cwd,
            "workspace_label": label,
        })

    source_ids = {workspace["workspace_id"] for workspace in sources}
    for label, matches in sorted(by_label.items()):
        if len(matches) < 2:
            continue
        canonical_id = canonical_by_label[label]["workspace_id"]
        for duplicate in sorted(matches, key=workspace_order):
            duplicate_id = duplicate["workspace_id"]
            if duplicate_id == canonical_id or duplicate_id not in source_ids:
                continue
            actions.append({
                "type": "close_workspace",
                "workspace_id": duplicate_id,
                "workspace_label": label,
                "kept_workspace_id": canonical_id,
            })

    if source_workspace_ids is None:
        source_workspace_id = None
        source_workspace_label = "整个实例"
    else:
        source_workspace_id = source_workspace_ids[0]
        source_workspace_label = sources[0].get("label")
    plan = {
        "source_workspace_id": source_workspace_id,
        "source_workspace_ids": [w["workspace_id"] for w in sources],
        "source_workspace_label": source_workspace_label,
        "actions": actions,
    }
    return plan


def print_plan(plan):
    source_id = plan["source_workspace_id"]
    source = plan["source_workspace_label"]
    print(f"source: {source}" + (f" ({source_id})" if source_id else ""))
    if not plan["actions"]:
        print("无需整理：所有 pane 已在目录名称对应的 workspace 中。")
    for action in plan["actions"]:
        if action["type"] == "create_workspace":
            print(f"CREATE workspace {action['workspace_label']!r} cwd={action['cwd']}")
        elif action["type"] == "close_workspace":
            print(f"CLOSE duplicate workspace {action['workspace_label']!r} "
                  f"({action['workspace_id']}); keep {action['kept_workspace_id']}")
        elif action["type"] == "rename_pane":
            print(f"RENAME pane {action['pane_id']} cwd={action['cwd']} "
                  f"{action.get('from_pane_label', '')!r} -> {action['pane_label']!r} "
                  f"in {action['workspace_id']}")
        else:
            target = action["to_workspace_label"]
            target_id = action["to_workspace_id"] or "<新建 workspace>"
            names = []
            if action.get("pane_label"):
                names.append(f"pane_label={action['pane_label']!r}")
            if action.get("target_pane_label"):
                names.append(f"target_pane_label={action['target_pane_label']!r}")
            if action.get("source_tab_label"):
                names.append(f"tab_label={action['source_tab_label']!r}")
            suffix = " " + " ".join(names) if names else ""
            print(f"MOVE pane {action['pane_id']} cwd={action['cwd']} "
                  f"{action['from_workspace_id']} -> {target} ({target_id}){suffix}")


def verify_moves(move_targets):
    for target_id, pane_id, cwd, pane_label, tab_id, tab_label in move_targets:
        panes = result(cli("pane", "list", "--workspace", target_id), "panes")
        found = next((pane for pane in panes if pane.get("pane_id") == pane_id), None)
        if found is None or found.get("cwd") != cwd or found.get("label", "") != pane_label:
            raise SystemExit(f"验证失败：pane {pane_id} 的位置、cwd 或名称不匹配")
        tab = result(cli("tab", "get", tab_id), "tab")
        if tab.get("label", "") != tab_label:
            raise SystemExit(f"验证失败：tab {tab_id} 的名称不匹配")


def execute(plan):
    created = {}
    for action in plan["actions"]:
        if action["type"] != "create_workspace":
            continue
        payload = result(cli("workspace", "create", "--cwd", action["cwd"],
                             "--label", action["workspace_label"], "--no-focus"),
                         "workspace")
        target_id = payload.get("workspace_id")
        if not target_id:
            raise SystemExit("workspace create 响应中缺少 workspace_id")
        created[action["workspace_label"]] = target_id

    move_targets = []
    for action in plan["actions"]:
        if action["type"] != "move_pane":
            continue
        target_id = action["to_workspace_id"] or created.get(action["to_workspace_label"])
        if not target_id:
            raise SystemExit(f"无法解析目标 workspace: {action['to_workspace_label']}")
        move_result = result(cli("pane", "move", action["pane_id"], "--workspace", target_id,
                                 "--new-tab", "--no-focus"), "move_result")
        moved_pane = move_result.get("pane", {})
        moved_pane_id = moved_pane.get("pane_id")
        if not moved_pane_id:
            raise SystemExit("pane move 响应中缺少移动后的 pane_id")
        created_tab = move_result.get("created_tab", {})
        created_tab_id = created_tab.get("tab_id")
        if not created_tab_id:
            raise SystemExit("pane move 响应中缺少新 tab_id")
        cli("pane", "rename", moved_pane_id, action.get("target_pane_label") or action.get("pane_label", ""))
        if action.get("source_tab_label") and created_tab_id:
            cli("tab", "rename", created_tab_id, action["source_tab_label"])
        move_targets.append((target_id, moved_pane_id, action["cwd"],
                             action.get("target_pane_label") or action.get("pane_label", ""), created_tab_id,
                             action.get("source_tab_label", "")))

    for action in plan["actions"]:
        if action["type"] == "rename_pane":
            cli("pane", "rename", action["pane_id"], action["pane_label"])

    # workspace create 必然产生 root pane；保留这个由 Herdr 创建的初始 pane，
    # 它与目标 cwd 一致，且不依赖未在本机验证的 pane close 生命周期语义。
    verify_moves(move_targets)

    close_actions = [action for action in plan["actions"]
                     if action["type"] == "close_workspace"]
    existing_ids = {
        workspace["workspace_id"]
        for workspace in result(cli("workspace", "list"), "workspaces")
    }
    closed = 0
    for action in close_actions:
        workspace_id = action["workspace_id"]
        # 移动最后一个 pane 时 Herdr 可能已经自动关闭源 workspace。
        if workspace_id in existing_ids:
            cli("workspace", "close", workspace_id)
        closed += 1

    remaining_ids = {
        workspace["workspace_id"]
        for workspace in result(cli("workspace", "list"), "workspaces")
    }
    not_closed = [action["workspace_id"] for action in close_actions
                  if action["workspace_id"] in remaining_ids]
    if not_closed:
        raise SystemExit(f"验证失败：重复 workspace 仍存在: {', '.join(not_closed)}")
    print(f"已执行：移动 {len(move_targets)} 个 pane，新建 {len(created)} 个 workspace，"
          f"合并 {closed} 个重复 workspace。")


def main():
    parser = argparse.ArgumentParser(description="按 pane cwd 整理 workspace，并使用目录标签")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--current", action="store_true", help="整理当前 pane 所在 workspace")
    scope.add_argument("--workspace", help="整理指定源 workspace")
    scope.add_argument("--all", action="store_true", help="整理整个 Herdr 实例的所有 workspace（默认）")
    parser.add_argument("--dry-run", action="store_true", help="只预览计划，不执行修改")
    args = parser.parse_args()

    if os.environ.get("HERDR_ENV") != "1":
        raise SystemExit("必须在 Herdr 管理的 pane 内运行（HERDR_ENV=1）")
    if args.all or (not args.current and args.workspace is None):
        source_workspace_ids = None
    elif args.current:
        current = result(cli("pane", "current", "--current"), "pane")
        source_workspace_id = current.get("workspace_id")
        if not source_workspace_id:
            raise SystemExit("当前 pane 响应中缺少 workspace_id")
        source_workspace_ids = [source_workspace_id]
    else:
        source_workspace_ids = [args.workspace]

    plan = discover(source_workspace_ids)
    print_plan(plan)
    if not args.dry_run:
        execute(plan)


if __name__ == "__main__":
    main()
