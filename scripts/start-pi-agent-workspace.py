#!/usr/bin/env python3
"""在新 Herdr workspace 的独立 tab 中启动 Pi、提交 prompt 并等待。

脚本只创建资源，不执行清理。Herdr 返回 timeout 时保留 workspace/tab/agent，
读取 agent 状态与近期输出，并把结果标记为 inconclusive，而不是 agent 任务失败。
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


EXIT_ERROR = 1
EXIT_INCONCLUSIVE = 3
AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
OPAQUE_TAB_LABEL_RE = re.compile(r"^(?:\d+|reviewer|worker|agent|pi|shell|tab)$", re.IGNORECASE)


@dataclass(frozen=True)
class Config:
    cwd: str
    workspace_label: str
    agent_name: str
    tab_label: str
    controller_tab_label: str
    completed_tab_label: str
    prompt: str
    wait_timeout_ms: int
    focus_workspace: bool
    use_workspace_root: bool
    result_lines: int


class OrchestrationError(RuntimeError):
    def __init__(self, stage: str, code: str, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.message = message
        self.detail = detail

    def as_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail is not None:
            error["detail"] = self.detail
        return error


def parse_json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def error_body(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    for text in (completed.stderr, completed.stdout):
        payload = parse_json(text.strip())
        error = payload.get("error") if payload else None
        if isinstance(error, dict):
            return {
                "code": str(error.get("code") or "herdr_error"),
                "message": str(error.get("message") or "herdr command failed"),
            }
    detail = completed.stderr.strip() or completed.stdout.strip()
    return {
        "code": "herdr_error",
        "message": detail or f"herdr exited with code {completed.returncode}",
    }


def run_herdr(stage: str, *args: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    command = ["herdr", *args]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        raise OrchestrationError(stage, "herdr_exec_failed", str(exc)) from exc
    if completed.returncode != 0:
        return None, error_body(completed)
    payload = parse_json(completed.stdout)
    if payload is None:
        raise OrchestrationError(
            stage,
            "invalid_herdr_json",
            "herdr command did not return a JSON object",
        )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise OrchestrationError(
            stage,
            "invalid_herdr_result",
            "herdr JSON response is missing result object",
        )
    return result, None


def run_herdr_text(stage: str, *args: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    command = ["herdr", *args]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        raise OrchestrationError(stage, "herdr_exec_failed", str(exc)) from exc
    if completed.returncode != 0:
        return None, error_body(completed)
    return {"text": completed.stdout}, None


def require_string(container: dict[str, Any], key: str, stage: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value:
        raise OrchestrationError(
            stage,
            "missing_json_field",
            f"herdr response is missing a non-empty {key}",
        )
    return value


def require_equal(stage: str, field: str, actual: str, expected: str) -> None:
    if actual != expected:
        raise OrchestrationError(
            stage,
            "json_target_mismatch",
            f"herdr returned an unexpected {field}",
            {"expected": expected, "actual": actual},
        )


def require_cwd(stage: str, container: dict[str, Any], expected: str) -> str:
    cwd = require_string(container, "cwd", stage)
    try:
        matches = Path(cwd).resolve() == Path(expected).resolve()
    except OSError:
        matches = cwd == expected
    if not matches:
        raise OrchestrationError(
            stage,
            "cwd_mismatch",
            "herdr returned a pane cwd different from the requested cwd",
            {"expected": expected, "actual": cwd},
        )
    return cwd


def add_stage(
    report: dict[str, Any],
    stage: str,
    status: str,
    *,
    target: dict[str, Any] | None = None,
    result: Any = None,
    error: dict[str, Any] | None = None,
) -> None:
    entry: dict[str, Any] = {"stage": stage, "status": status}
    if target is not None:
        entry["target"] = target
    if result is not None:
        entry["result"] = result
    if error is not None:
        entry["error"] = error
    report["stages"].append(entry)


def base_report(config: Config) -> dict[str, Any]:
    return {
        "status": "running",
        "agent_task_result": "unknown",
        "resources_preserved": True,
        "request": {
            "cwd": config.cwd,
            "workspace_label": config.workspace_label,
            "agent_name": config.agent_name,
            "tab_label": config.tab_label,
            "controller_tab_label": config.controller_tab_label,
            "completed_tab_label": config.completed_tab_label,
            "wait_timeout_ms": config.wait_timeout_ms,
            "focus_workspace": config.focus_workspace,
            "agent_placement": "workspace_root" if config.use_workspace_root else "new_tab",
            "result_lines": config.result_lines,
        },
        "resources": {},
        "stages": [],
    }


def require_semantic_tab_label(label: str, field: str) -> None:
    normalized = label.strip()
    if not normalized or OPAQUE_TAB_LABEL_RE.fullmatch(normalized):
        raise OrchestrationError(
            "preflight",
            f"invalid_{field}",
            f"{field.replace('_', ' ')} must describe the concrete task, not a number or generic role",
            label,
        )


def validate(config: Config) -> None:
    if os.environ.get("HERDR_ENV") != "1":
        raise OrchestrationError(
            "preflight",
            "invalid_herdr_env",
            "must run inside a Herdr-managed pane with HERDR_ENV=1",
        )
    cwd = Path(config.cwd)
    if not cwd.is_absolute() or not cwd.is_dir():
        raise OrchestrationError(
            "preflight",
            "invalid_cwd",
            "cwd must be an existing absolute directory",
            config.cwd,
        )
    if not os.environ.get("HERDR_TAB_ID"):
        raise OrchestrationError(
            "preflight",
            "missing_controller_tab_id",
            "HERDR_TAB_ID is required to rename the controller tab before creating execution resources",
        )
    if not config.workspace_label:
        raise OrchestrationError("preflight", "invalid_workspace_label", "workspace label must not be empty")
    require_semantic_tab_label(config.tab_label, "tab_label")
    require_semantic_tab_label(config.controller_tab_label, "controller_tab_label")
    require_semantic_tab_label(config.completed_tab_label, "completed_tab_label")
    if not AGENT_NAME_RE.fullmatch(config.agent_name):
        raise OrchestrationError(
            "preflight",
            "invalid_agent_name",
            "agent name must match [a-z][a-z0-9_-]{0,31}",
        )
    if not config.prompt:
        raise OrchestrationError("preflight", "empty_prompt", "prompt must not be empty")
    if config.wait_timeout_ms <= 0:
        raise OrchestrationError(
            "preflight", "invalid_wait_timeout", "wait timeout must be greater than zero"
        )
    if not 1 <= config.result_lines <= 1000:
        raise OrchestrationError(
            "preflight", "invalid_result_lines", "result lines must be between 1 and 1000"
        )


def diagnostic_call(
    report: dict[str, Any], stage: str, agent_name: str, *args: str, text_output: bool = False
) -> bool:
    try:
        runner = run_herdr_text if text_output else run_herdr
        result, error = runner(stage, *args)
    except OrchestrationError as exc:
        result, error = None, exc.as_dict()
    add_stage(
        report,
        stage,
        "ok" if error is None else "error",
        target={"agent_name": agent_name},
        result=result,
        error=error,
    )
    return error is None


def collect_diagnostics(report: dict[str, Any], agent_name: str, result_lines: int) -> None:
    # 两次调用互相独立：即使 get 失败或返回坏 JSON，也必须继续执行 read。
    diagnostic_call(
        report,
        "diagnostics_agent_get",
        agent_name,
        "agent",
        "get",
        agent_name,
    )
    diagnostic_call(
        report,
        "diagnostics_agent_read",
        agent_name,
        "agent",
        "read",
        agent_name,
        "--source",
        "recent-unwrapped",
        "--lines",
        str(result_lines),
        text_output=True,
    )


def orchestrate(config: Config) -> tuple[dict[str, Any], int]:
    report = base_report(config)
    try:
        validate(config)
        add_stage(report, "preflight", "ok")

        controller_tab_id = os.environ["HERDR_TAB_ID"]
        rename_result, rename_error = run_herdr(
            "controller_tab_rename",
            "tab",
            "rename",
            controller_tab_id,
            config.controller_tab_label,
        )
        if rename_error is not None:
            raise OrchestrationError(
                "controller_tab_rename", rename_error["code"], rename_error["message"]
            )
        add_stage(
            report,
            "controller_tab_rename",
            "ok",
            target={"tab_id": controller_tab_id},
            result={"label": config.controller_tab_label},
        )
        report["resources"]["controller_tab"] = {
            "tab_id": controller_tab_id,
            "label": config.controller_tab_label,
        }

        focus_flag = "--focus" if config.focus_workspace else "--no-focus"
        workspace_result, workspace_error = run_herdr(
            "workspace_create",
            "workspace",
            "create",
            "--cwd",
            config.cwd,
            "--label",
            config.workspace_label,
            focus_flag,
        )
        if workspace_error is not None:
            raise OrchestrationError(
                "workspace_create",
                workspace_error["code"],
                workspace_error["message"],
            )
        assert workspace_result is not None
        workspace = workspace_result.get("workspace")
        initial_tab = workspace_result.get("tab")
        root_pane = workspace_result.get("root_pane")
        if not all(isinstance(value, dict) for value in (workspace, initial_tab, root_pane)):
            raise OrchestrationError(
                "workspace_create",
                "missing_json_field",
                "workspace create response must include workspace, tab, and root_pane objects",
            )
        workspace_id = require_string(workspace, "workspace_id", "workspace_create")
        initial_tab_id = require_string(initial_tab, "tab_id", "workspace_create")
        root_pane_id = require_string(root_pane, "pane_id", "workspace_create")
        require_equal(
            "workspace_create",
            "tab.workspace_id",
            require_string(initial_tab, "workspace_id", "workspace_create"),
            workspace_id,
        )
        require_equal(
            "workspace_create",
            "root_pane.workspace_id",
            require_string(root_pane, "workspace_id", "workspace_create"),
            workspace_id,
        )
        require_equal(
            "workspace_create",
            "root_pane.tab_id",
            require_string(root_pane, "tab_id", "workspace_create"),
            initial_tab_id,
        )
        root_pane_cwd = require_cwd("workspace_create", root_pane, config.cwd)
        report["resources"]["workspace"] = {
            "workspace_id": workspace_id,
            "label": workspace.get("label", config.workspace_label),
            "focused": workspace.get("focused"),
        }
        report["resources"]["initial_tab"] = {"tab_id": initial_tab_id}
        report["resources"]["initial_root_pane"] = {
            "pane_id": root_pane_id,
            "cwd": root_pane_cwd,
        }
        add_stage(
            report,
            "workspace_create",
            "ok",
            result={
                "workspace_id": workspace_id,
                "tab_id": initial_tab_id,
                "root_pane_id": root_pane_id,
            },
        )

        if config.use_workspace_root:
            root_rename_result, root_rename_error = run_herdr(
                "agent_tab_rename",
                "tab",
                "rename",
                initial_tab_id,
                config.tab_label,
            )
            if root_rename_error is not None:
                raise OrchestrationError(
                    "agent_tab_rename", root_rename_error["code"], root_rename_error["message"]
                )
            add_stage(
                report,
                "agent_tab_rename",
                "ok",
                target={"tab_id": initial_tab_id},
                result={"label": config.tab_label},
            )
            agent_tab_id = initial_tab_id
            agent_pane_id = root_pane_id
            agent_pane_cwd = root_pane_cwd
            report["resources"]["agent_tab"] = {
                "tab_id": agent_tab_id,
                "label": config.tab_label,
            }
            report["resources"]["agent_pane"] = {
                "pane_id": agent_pane_id,
                "cwd": agent_pane_cwd,
            }
            add_stage(
                report,
                "agent_pane_select",
                "ok",
                target={"workspace_id": workspace_id},
                result={"placement": "workspace_root", "tab_id": agent_tab_id, "pane_id": agent_pane_id},
            )
        else:
            tab_result, tab_error = run_herdr(
                "agent_tab_create",
                "tab",
                "create",
                "--workspace",
                workspace_id,
                "--cwd",
                config.cwd,
                "--label",
                config.tab_label,
                "--no-focus",
            )
            if tab_error is not None:
                raise OrchestrationError("agent_tab_create", tab_error["code"], tab_error["message"])
            assert tab_result is not None
            agent_tab = tab_result.get("tab")
            agent_pane = tab_result.get("root_pane")
            if not isinstance(agent_tab, dict) or not isinstance(agent_pane, dict):
                raise OrchestrationError(
                    "agent_tab_create",
                    "missing_json_field",
                    "tab create response must include tab and root_pane objects",
                )
            agent_tab_id = require_string(agent_tab, "tab_id", "agent_tab_create")
            agent_pane_id = require_string(agent_pane, "pane_id", "agent_tab_create")
            require_equal(
                "agent_tab_create",
                "tab.workspace_id",
                require_string(agent_tab, "workspace_id", "agent_tab_create"),
                workspace_id,
            )
            require_equal(
                "agent_tab_create",
                "root_pane.workspace_id",
                require_string(agent_pane, "workspace_id", "agent_tab_create"),
                workspace_id,
            )
            require_equal(
                "agent_tab_create",
                "root_pane.tab_id",
                require_string(agent_pane, "tab_id", "agent_tab_create"),
                agent_tab_id,
            )
            agent_pane_cwd = require_cwd("agent_tab_create", agent_pane, config.cwd)
            report["resources"]["agent_tab"] = {
                "tab_id": agent_tab_id,
                "label": agent_tab.get("label", config.tab_label),
            }
            report["resources"]["agent_pane"] = {
                "pane_id": agent_pane_id,
                "cwd": agent_pane_cwd,
            }
            add_stage(
                report,
                "agent_tab_create",
                "ok",
                target={"workspace_id": workspace_id},
                result={"tab_id": agent_tab_id, "root_pane_id": agent_pane_id},
            )

        start_result, start_error = run_herdr(
            "agent_start",
            "agent",
            "start",
            config.agent_name,
            "--kind",
            "pi",
            "--pane",
            agent_pane_id,
        )
        if start_error is not None:
            raise OrchestrationError("agent_start", start_error["code"], start_error["message"])
        assert start_result is not None
        agent = start_result.get("agent")
        if not isinstance(agent, dict):
            raise OrchestrationError(
                "agent_start", "missing_json_field", "agent start response must include agent object"
            )
        returned_agent_name = require_string(agent, "name", "agent_start")
        returned_pane_id = require_string(agent, "pane_id", "agent_start")
        require_equal("agent_start", "agent.pane_id", returned_pane_id, agent_pane_id)
        require_equal(
            "agent_start",
            "agent.tab_id",
            require_string(agent, "tab_id", "agent_start"),
            agent_tab_id,
        )
        require_equal(
            "agent_start",
            "agent.workspace_id",
            require_string(agent, "workspace_id", "agent_start"),
            workspace_id,
        )
        report["resources"]["agent"] = {
            "name": returned_agent_name,
            "kind": agent.get("agent") or "pi",
            "pane_id": returned_pane_id,
        }
        add_stage(
            report,
            "agent_start",
            "ok",
            target={"pane_id": agent_pane_id},
            result={
                "agent_name": returned_agent_name,
                "pane_id": returned_pane_id,
                "agent_status": agent.get("agent_status"),
            },
        )

        prompt_result, prompt_error = run_herdr(
            "prompt_wait",
            "agent",
            "prompt",
            returned_agent_name,
            config.prompt,
            "--wait",
            "--timeout",
            str(config.wait_timeout_ms),
        )
        if prompt_error is not None:
            code = prompt_error.get("code", "herdr_error")
            add_stage(
                report,
                "prompt_wait",
                "timeout" if code == "timeout" else "error",
                target={"agent_name": returned_agent_name},
                error=prompt_error,
            )
            if code in {"timeout", "agent_prompt_stalled"}:
                collect_diagnostics(report, returned_agent_name, config.result_lines)
                report["status"] = "timeout" if code == "timeout" else "inconclusive"
                report["agent_task_result"] = "unknown"
                return report, EXIT_INCONCLUSIVE
            raise OrchestrationError("prompt_wait", code, prompt_error["message"])

        assert prompt_result is not None
        prompted_agent = prompt_result.get("agent")
        if not isinstance(prompted_agent, dict):
            raise OrchestrationError(
                "prompt_wait",
                "missing_json_field",
                "agent prompt response must include agent object",
            )
        settled_name = require_string(prompted_agent, "name", "prompt_wait")
        if settled_name != returned_agent_name:
            raise OrchestrationError(
                "prompt_wait",
                "agent_name_mismatch",
                "agent prompt returned a different agent name",
                {"expected": returned_agent_name, "actual": settled_name},
            )
        agent_status = prompted_agent.get("agent_status")
        add_stage(
            report,
            "prompt_wait",
            "settled",
            target={"agent_name": returned_agent_name},
            result={"agent_name": settled_name, "agent_status": agent_status},
        )
        result_read_ok = diagnostic_call(
            report,
            "result_read",
            returned_agent_name,
            "agent",
            "read",
            returned_agent_name,
            "--source",
            "recent-unwrapped",
            "--lines",
            str(config.result_lines),
            text_output=True,
        )
        report["agent_task_result"] = agent_status if isinstance(agent_status, str) else "unknown"
        if agent_status == "blocked":
            diagnostic_call(
                report,
                "blocked_agent_get",
                returned_agent_name,
                "agent",
                "get",
                returned_agent_name,
            )
            report["status"] = "blocked" if result_read_ok else "inconclusive"
            return report, EXIT_INCONCLUSIVE
        if not result_read_ok:
            report["status"] = "inconclusive"
            return report, EXIT_INCONCLUSIVE
        report["status"] = "settled"
        return report, 0
    except OrchestrationError as exc:
        if not any(stage["stage"] == exc.stage and stage["status"] == "error" for stage in report["stages"]):
            add_stage(report, exc.stage, "error", error=exc.as_dict())
        report["status"] = "failed"
        report["agent_task_result"] = "unknown"
        return report, EXIT_ERROR


def parse_args(argv: list[str] | None = None) -> Config:
    parser = argparse.ArgumentParser(
        description="在新 Herdr workspace 的独立 tab 中启动 Pi agent、提交 prompt 并等待"
    )
    parser.add_argument("--cwd", required=True, help="新 workspace 与 agent tab 的绝对工作目录")
    parser.add_argument("--workspace-label", required=True, help="新 workspace/Space 标签")
    parser.add_argument("--agent-name", required=True, help="唯一 agent 名")
    parser.add_argument("--tab-label", required=True, help="承载 Pi agent 的任务语义 tab 标签")
    parser.add_argument(
        "--controller-tab-label",
        help="创建执行终端前设置的主控 tab 语义标签（默认：主控-<tab-label>）",
    )
    parser.add_argument(
        "--completed-tab-label",
        help="主控验收通过后应设置的执行 tab 完成态标签（默认：完成-<tab-label>）",
    )
    prompt = parser.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt", help="直接提交的 prompt 文本")
    prompt.add_argument("--prompt-file", help="UTF-8 prompt 文件路径")
    parser.add_argument(
        "--wait-timeout",
        required=True,
        type=int,
        metavar="MS",
        help="prompt --wait 的超时毫秒数",
    )
    placement = parser.add_mutually_exclusive_group()
    placement.add_argument(
        "--use-workspace-root-pane",
        action="store_true",
        dest="use_workspace_root",
        help="直接在 workspace create 返回的初始 pane 启动 Pi，避免留下空 tab",
    )
    placement.add_argument(
        "--new-agent-tab",
        action="store_false",
        dest="use_workspace_root",
        help="为 Pi 新建独立 tab（兼容默认）",
    )
    parser.set_defaults(use_workspace_root=False)
    parser.add_argument(
        "--result-lines",
        type=int,
        default=120,
        metavar="N",
        help="任务落定后自动回读的近期输出行数（默认 120，范围 1-1000）",
    )
    focus = parser.add_mutually_exclusive_group()
    focus.add_argument(
        "--focus-workspace",
        action="store_true",
        help="创建时聚焦新 workspace（默认不聚焦）",
    )
    focus.add_argument(
        "--no-focus-workspace",
        action="store_false",
        dest="focus_workspace",
        help="创建时不聚焦新 workspace（默认）",
    )
    parser.set_defaults(focus_workspace=False)
    args = parser.parse_args(argv)

    cwd = str(Path(args.cwd).expanduser().resolve())
    if args.prompt_file is not None:
        try:
            prompt_text = Path(args.prompt_file).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            parser.error(f"cannot read --prompt-file: {exc}")
    else:
        prompt_text = args.prompt
    controller_tab_label = args.controller_tab_label or f"主控-{args.tab_label}"
    completed_tab_label = args.completed_tab_label or f"完成-{args.tab_label}"
    return Config(
        cwd=cwd,
        workspace_label=args.workspace_label,
        agent_name=args.agent_name,
        tab_label=args.tab_label,
        controller_tab_label=controller_tab_label,
        completed_tab_label=completed_tab_label,
        prompt=prompt_text,
        wait_timeout_ms=args.wait_timeout,
        focus_workspace=args.focus_workspace,
        use_workspace_root=args.use_workspace_root,
        result_lines=args.result_lines,
    )


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    report, exit_code = orchestrate(config)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
