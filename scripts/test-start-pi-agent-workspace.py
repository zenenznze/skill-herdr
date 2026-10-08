#!/usr/bin/env python3
"""Mock 回归测试：新 workspace 中启动 Pi agent 的确定性编排。"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("start-pi-agent-workspace.py")
SPEC = importlib.util.spec_from_file_location("start_pi_agent_workspace", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def response(result: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["herdr"], returncode=0, stdout=json.dumps({"result": result}), stderr=""
    )


class FakeHerdr:
    def __init__(self, responses: list[subprocess.CompletedProcess[str]]) -> None:
        self.responses = list(responses)
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if command[1:3] == ["tab", "rename"]:
            return response({"type": "tab_renamed"})
        if not self.responses:
            raise AssertionError(f"unexpected command: {command}")
        return self.responses.pop(0)


class OrchestrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = mock.patch.dict(os.environ, {"HERDR_TAB_ID": "control:t1"}, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def config(
        self,
        cwd: str,
        *,
        focus: bool = False,
        use_workspace_root: bool = False,
        result_lines: int = 120,
    ) -> object:
        return MODULE.Config(
            cwd=cwd,
            workspace_label="task-space",
            agent_name="requested-agent",
            tab_label="执行-修复登录回归",
            controller_tab_label="主控-修复登录回归",
            completed_tab_label="完成-修复登录回归",
            prompt="Run the requested task.",
            wait_timeout_ms=45000,
            focus_workspace=focus,
            use_workspace_root=use_workspace_root,
            result_lines=result_lines,
        )

    def test_uses_json_ids_and_returned_agent_name_without_split(self) -> None:
        with tempfile.TemporaryDirectory() as cwd:
            fake = FakeHerdr(
                [
                    response(
                        {
                            "type": "workspace_created",
                            "workspace": {"workspace_id": "w9"},
                            "tab": {"tab_id": "w9:t1", "workspace_id": "w9"},
                            "root_pane": {
                                "pane_id": "w9:p1",
                                "workspace_id": "w9",
                                "tab_id": "w9:t1",
                                "cwd": cwd,
                            },
                        }
                    ),
                    response(
                        {
                            "type": "tab_created",
                            "tab": {"tab_id": "w9:t2", "workspace_id": "w9"},
                            "root_pane": {
                                "pane_id": "w9:p2",
                                "workspace_id": "w9",
                                "tab_id": "w9:t2",
                                "cwd": cwd,
                            },
                        }
                    ),
                    response(
                        {
                            "type": "agent_started",
                            "agent": {
                                "name": "returned-agent",
                                "workspace_id": "w9",
                                "tab_id": "w9:t2",
                                "pane_id": "w9:p2",
                                "agent_status": "idle",
                            },
                            "argv": ["pi"],
                        }
                    ),
                    response(
                        {
                            "type": "agent_prompted",
                            "agent": {
                                "name": "returned-agent",
                                "pane_id": "w9:p2",
                                "agent_status": "done",
                            },
                        }
                    ),
                    response(
                        {
                            "type": "agent_read",
                            "source": "recent-unwrapped",
                            "text": "task result",
                        }
                    ),
                ]
            )
            with mock.patch.dict(os.environ, {"HERDR_ENV": "1"}, clear=False), mock.patch.object(
                MODULE.subprocess, "run", side_effect=fake
            ):
                report, exit_code = MODULE.orchestrate(self.config(cwd))

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "settled")
        self.assertEqual(report["agent_task_result"], "done")
        self.assertEqual(report["resources"]["workspace"]["workspace_id"], "w9")
        self.assertEqual(report["resources"]["agent_tab"]["tab_id"], "w9:t2")
        self.assertEqual(report["resources"]["agent"]["name"], "returned-agent")
        self.assertEqual(
            fake.commands,
            [
                ["herdr", "tab", "rename", "control:t1", "主控-修复登录回归"],
                [
                    "herdr",
                    "workspace",
                    "create",
                    "--cwd",
                    cwd,
                    "--label",
                    "task-space",
                    "--no-focus",
                ],
                [
                    "herdr",
                    "tab",
                    "create",
                    "--workspace",
                    "w9",
                    "--cwd",
                    cwd,
                    "--label",
                    "执行-修复登录回归",
                    "--no-focus",
                ],
                [
                    "herdr",
                    "agent",
                    "start",
                    "requested-agent",
                    "--kind",
                    "pi",
                    "--pane",
                    "w9:p2",
                ],
                [
                    "herdr",
                    "agent",
                    "prompt",
                    "returned-agent",
                    "Run the requested task.",
                    "--wait",
                    "--timeout",
                    "45000",
                ],
                [
                    "herdr",
                    "agent",
                    "read",
                    "returned-agent",
                    "--source",
                    "recent-unwrapped",
                    "--lines",
                    "120",
                ],
            ],
        )
        flattened = [part for command in fake.commands for part in command]
        self.assertNotIn("split", flattened)
        self.assertNotIn("close", flattened)

    def test_can_reuse_workspace_root_pane_without_creating_empty_tab(self) -> None:
        with tempfile.TemporaryDirectory() as cwd:
            config = self.config(cwd, use_workspace_root=True, result_lines=40)
            fake = FakeHerdr(
                [
                    response(
                        {
                            "type": "workspace_created",
                            "workspace": {"workspace_id": "w5"},
                            "tab": {"tab_id": "w5:t1", "workspace_id": "w5"},
                            "root_pane": {
                                "pane_id": "w5:p1",
                                "workspace_id": "w5",
                                "tab_id": "w5:t1",
                                "cwd": cwd,
                            },
                        }
                    ),
                    response(
                        {
                            "type": "agent_started",
                            "agent": {
                                "name": "actual-agent",
                                "workspace_id": "w5",
                                "tab_id": "w5:t1",
                                "pane_id": "w5:p1",
                                "agent_status": "idle",
                            },
                        }
                    ),
                    response(
                        {
                            "type": "agent_prompted",
                            "agent": {
                                "name": "actual-agent",
                                "pane_id": "w5:p1",
                                "agent_status": "done",
                            },
                        }
                    ),
                    response({"type": "agent_read", "text": "done output"}),
                ]
            )
            with mock.patch.dict(os.environ, {"HERDR_ENV": "1"}, clear=False), mock.patch.object(
                MODULE.subprocess, "run", side_effect=fake
            ):
                report, exit_code = MODULE.orchestrate(config)

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["request"]["agent_placement"], "workspace_root")
        self.assertEqual(report["resources"]["agent_pane"]["pane_id"], "w5:p1")
        self.assertNotIn(["herdr", "tab", "create"], [command[:3] for command in fake.commands])
        self.assertEqual(
            fake.commands[:3],
            [
                ["herdr", "tab", "rename", "control:t1", "主控-修复登录回归"],
                ["herdr", "workspace", "create", "--cwd", cwd, "--label", "task-space", "--no-focus"],
                ["herdr", "tab", "rename", "w5:t1", "执行-修复登录回归"],
            ],
        )
        self.assertEqual(fake.commands[-1][-1], "40")

    def test_timeout_gets_diagnostics_and_preserves_resources(self) -> None:
        with tempfile.TemporaryDirectory() as cwd:
            timeout = subprocess.CompletedProcess(
                args=["herdr"],
                returncode=1,
                stdout="",
                stderr=json.dumps(
                    {"id": "cli:agent:prompt", "error": {"code": "timeout", "message": "wait expired"}}
                ),
            )
            fake = FakeHerdr(
                [
                    response(
                        {
                            "type": "workspace_created",
                            "workspace": {"workspace_id": "w7"},
                            "tab": {"tab_id": "w7:t1", "workspace_id": "w7"},
                            "root_pane": {
                                "pane_id": "w7:p1",
                                "workspace_id": "w7",
                                "tab_id": "w7:t1",
                                "cwd": cwd,
                            },
                        }
                    ),
                    response(
                        {
                            "type": "tab_created",
                            "tab": {"tab_id": "w7:t2", "workspace_id": "w7"},
                            "root_pane": {
                                "pane_id": "w7:p2",
                                "workspace_id": "w7",
                                "tab_id": "w7:t2",
                                "cwd": cwd,
                            },
                        }
                    ),
                    response(
                        {
                            "type": "agent_started",
                            "agent": {
                                "name": "actual-agent",
                                "workspace_id": "w7",
                                "tab_id": "w7:t2",
                                "pane_id": "w7:p2",
                                "agent_status": "idle",
                            },
                            "argv": ["pi"],
                        }
                    ),
                    timeout,
                    response(
                        {
                            "type": "agent_info",
                            "agent": {
                                "name": "actual-agent",
                                "pane_id": "w7:p2",
                                "agent_status": "working",
                            },
                        }
                    ),
                    response(
                        {
                            "type": "agent_read",
                            "source": "recent-unwrapped",
                            "text": "still working",
                        }
                    ),
                ]
            )
            with mock.patch.dict(os.environ, {"HERDR_ENV": "1"}, clear=False), mock.patch.object(
                MODULE.subprocess, "run", side_effect=fake
            ):
                report, exit_code = MODULE.orchestrate(self.config(cwd, focus=True))

        self.assertEqual(exit_code, MODULE.EXIT_INCONCLUSIVE)
        self.assertEqual(report["status"], "timeout")
        self.assertEqual(report["agent_task_result"], "unknown")
        self.assertTrue(report["resources_preserved"])
        self.assertEqual(fake.commands[1][-1], "--focus")
        self.assertEqual(fake.commands[-2], ["herdr", "agent", "get", "actual-agent"])
        self.assertEqual(
            fake.commands[-1],
            [
                "herdr",
                "agent",
                "read",
                "actual-agent",
                "--source",
                "recent-unwrapped",
                "--lines",
                "120",
            ],
        )
        flattened = [part for command in fake.commands for part in command]
        self.assertNotIn("close", flattened)
        self.assertNotIn("kill", flattened)
        self.assertEqual(
            [stage["stage"] for stage in report["stages"][-3:]],
            ["prompt_wait", "diagnostics_agent_get", "diagnostics_agent_read"],
        )

    def test_requires_exact_herdr_env_value(self) -> None:
        with tempfile.TemporaryDirectory() as cwd, mock.patch.dict(
            os.environ, {"HERDR_ENV": "true"}, clear=False
        ), mock.patch.object(MODULE.subprocess, "run") as run:
            report, exit_code = MODULE.orchestrate(self.config(cwd))
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["stages"][0]["error"]["code"], "invalid_herdr_env")
        run.assert_not_called()

    def test_prompt_file_is_read_as_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as cwd:
            prompt_file = Path(cwd, "prompt.md")
            prompt_file.write_text("完成指定任务并报告结果。", encoding="utf-8")
            config = MODULE.parse_args(
                [
                    "--cwd",
                    cwd,
                    "--workspace-label",
                    "space",
                    "--agent-name",
                    "pi-task",
                    "--tab-label",
                    "执行-整理依赖",
                    "--prompt-file",
                    str(prompt_file),
                    "--wait-timeout",
                    "9000",
                    "--focus-workspace",
                ]
            )
        self.assertEqual(config.prompt, "完成指定任务并报告结果。")
        self.assertEqual(config.wait_timeout_ms, 9000)
        self.assertTrue(config.focus_workspace)
        self.assertFalse(config.use_workspace_root)
        self.assertEqual(config.result_lines, 120)
        self.assertEqual(config.controller_tab_label, "主控-执行-整理依赖")
        self.assertEqual(config.completed_tab_label, "完成-执行-整理依赖")

    def test_rejects_opaque_execution_label_before_any_command(self) -> None:
        with tempfile.TemporaryDirectory() as cwd, mock.patch.dict(
            os.environ, {"HERDR_ENV": "1"}, clear=False
        ), mock.patch.object(MODULE.subprocess, "run") as run:
            config = MODULE.Config(
                cwd=cwd,
                workspace_label="task-space",
                agent_name="requested-agent",
                tab_label="worker",
                controller_tab_label="主控-修复登录回归",
                completed_tab_label="完成-修复登录回归",
                prompt="Run the requested task.",
                wait_timeout_ms=45000,
                focus_workspace=False,
                use_workspace_root=False,
                result_lines=120,
            )
            report, exit_code = MODULE.orchestrate(config)
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["stages"][0]["error"]["code"], "invalid_tab_label")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
