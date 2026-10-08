#!/usr/bin/env python3
"""按 tab 标签快速聚焦其承载的 pane。

Herdr 当前没有按标签直接 focus 的 CLI；脚本先读取一次只读 snapshot，
用真实 tab/pane ID 做唯一匹配，再执行 tab focus，避免按侧栏顺序猜 ID。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any


class FocusError(RuntimeError):
    """可向用户展示的安全失败。"""


def cli(*args: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["herdr", *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        raise FocusError(f"无法运行 herdr：{exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"退出码 {completed.returncode}"
        raise FocusError(f"herdr {' '.join(args)} 失败：{detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise FocusError(f"herdr {' '.join(args)} 未返回有效 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise FocusError(f"herdr {' '.join(args)} 返回格式错误")
    return payload


def find_target(
    snapshot: dict[str, Any], label: str, workspace_id: str | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = snapshot.get("result")
    data = result.get("snapshot") if isinstance(result, dict) else None
    tabs = data.get("tabs") if isinstance(data, dict) else None
    panes = data.get("panes") if isinstance(data, dict) else None
    if not isinstance(tabs, list) or not isinstance(panes, list):
        raise FocusError("snapshot 中缺少 tabs 或 panes 数组")

    pane_by_tab: dict[str, list[dict[str, Any]]] = {}
    for pane in panes:
        if isinstance(pane, dict) and isinstance(pane.get("tab_id"), str):
            pane_by_tab.setdefault(pane["tab_id"], []).append(pane)

    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for tab in tabs:
        if not isinstance(tab, dict) or tab.get("label") != label:
            continue
        if workspace_id is not None and tab.get("workspace_id") != workspace_id:
            continue
        tab_id = tab.get("tab_id")
        tab_panes = pane_by_tab.get(tab_id, [])
        if not isinstance(tab_id, str) or len(tab_panes) != 1:
            raise FocusError(
                f"标签“{label}”对应的 tab 不是单 pane tab；请改用明确的 pane/tab ID"
            )
        matches.append((tab, tab_panes[0]))

    if not matches:
        scope = f"workspace {workspace_id}" if workspace_id else "整个实例"
        raise FocusError(f"{scope}中没有唯一匹配的标签“{label}”")
    if len(matches) > 1:
        locations = ", ".join(
            f"{tab.get('workspace_id', '?')}/{tab.get('tab_id', '?')}"
            for tab, _ in matches
        )
        raise FocusError(f"标签“{label}”有多个匹配：{locations}；请用 --workspace 消歧")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按唯一 tab 标签聚焦其单独承载的 pane（全实例精确匹配）"
    )
    parser.add_argument("label", help="tab 标签；一 pane 一个 tab 时即为 pane 名")
    parser.add_argument("--workspace", help="只在指定 workspace 内匹配")
    args = parser.parse_args()

    if os.environ.get("HERDR_ENV") != "1":
        print("必须在 Herdr 管理的 pane 内运行（HERDR_ENV=1）", file=sys.stderr)
        return 1

    try:
        snapshot = cli("api", "snapshot")
        tab, pane = find_target(snapshot, args.label, args.workspace)
        focused = cli("tab", "focus", tab["tab_id"])
    except (FocusError, KeyError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    focused_tab = focused.get("result", {}).get("tab", {})
    if focused_tab.get("focused") is not True:
        print("错误：herdr tab focus 未确认目标 tab 已聚焦", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "label": args.label,
                "workspace_id": tab.get("workspace_id"),
                "tab_id": tab.get("tab_id"),
                "pane_id": pane.get("pane_id"),
                "cwd": pane.get("cwd"),
                "focused": focused_tab.get("focused", True),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
