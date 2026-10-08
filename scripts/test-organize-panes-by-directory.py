#!/usr/bin/env python3
"""回归测试：全实例整理必须发现并纳入其他 workspace 的 pane。"""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("organize-panes-by-directory.py")
SPEC = importlib.util.spec_from_file_location("organize_panes", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class OrganizePlanTest(unittest.TestCase):
    def setUp(self):
        self.workspaces = [
            {"workspace_id": "wF", "label": "document"},
            {"workspace_id": "wK", "label": "projects"},
            {"workspace_id": "wO", "label": "obsidian"},
        ]
        self.tabs = {
            "wF": [{"tab_id": "wF:t1", "label": "1"}],
            "wK": [{"tab_id": "wK:t1", "label": "1"}],
            "wO": [{"tab_id": "wO:t1", "label": "2"}],
        }
        self.panes = {
            "wF": [
                {"pane_id": "wF:p1", "cwd": "/workspace/document", "tab_id": "wF:t1"},
                {"pane_id": "wF:p2", "cwd": "/workspace/document/obsidian", "tab_id": "wF:t1"},
            ],
            "wK": [
                {"pane_id": "wK:p1", "cwd": "/workspace/document/projects", "tab_id": "wK:t1"},
            ],
            "wO": [
                {"pane_id": "wO:p1", "cwd": "/workspace/document/obsidian", "tab_id": "wO:t1"},
            ],
        }

        def fake_cli(*args):
            if args == ("workspace", "list"):
                return {"result": {"workspaces": self.workspaces}}
            if args[:2] == ("tab", "list"):
                return {"result": {"tabs": self.tabs[args[args.index("--workspace") + 1]]}}
            if args[:2] == ("pane", "list"):
                return {"result": {"panes": self.panes[args[args.index("--workspace") + 1]]}}
            raise AssertionError(f"unexpected CLI call: {args}")

        MODULE.cli = fake_cli

    def test_all_scope_finds_cross_workspace_pane(self):
        plan = MODULE.discover(None)
        self.assertEqual(plan["source_workspace_label"], "整个实例")
        self.assertEqual(plan["source_workspace_ids"], ["wF", "wK", "wO"])
        moves = [action for action in plan["actions"] if action["type"] == "move_pane"]
        self.assertEqual(len(moves), 1)
        action = moves[0]
        self.assertEqual(action["pane_id"], "wF:p2")
        self.assertEqual(action["from_workspace_id"], "wF")
        self.assertEqual(action["to_workspace_id"], "wO")

    def test_current_scope_does_not_claim_instance_complete(self):
        plan = MODULE.discover(["wF"])
        self.assertEqual(plan["source_workspace_label"], "document")
        moves = [action for action in plan["actions"] if action["type"] == "move_pane"]
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0]["pane_id"], "wF:p2")

    def test_duplicate_workspace_labels_merge_into_oldest_workspace(self):
        self.workspaces = [
            {"workspace_id": "wOld", "label": "project", "number": 2},
            {"workspace_id": "wNew", "label": "project", "number": 7},
        ]
        self.tabs = {
            "wOld": [{"tab_id": "wOld:t1", "label": "kept"}],
            "wNew": [{"tab_id": "wNew:t1", "label": "moved"}],
        }
        self.panes = {
            "wOld": [
                {"pane_id": "wOld:p1", "cwd": "/workspace/project", "tab_id": "wOld:t1"},
            ],
            "wNew": [
                {"pane_id": "wNew:p1", "cwd": "/workspace/project", "tab_id": "wNew:t1"},
            ],
        }

        plan = MODULE.discover(None)
        structural = [
            action for action in plan["actions"]
            if action["type"] in {"move_pane", "close_workspace"}
        ]
        self.assertEqual(
            [action["type"] for action in structural],
            ["move_pane", "close_workspace"],
        )
        move, close = structural
        self.assertEqual(move["pane_id"], "wNew:p1")
        self.assertEqual(move["to_workspace_id"], "wOld")
        self.assertEqual(close["workspace_id"], "wNew")
        self.assertEqual(close["kept_workspace_id"], "wOld")

    def test_agent_pane_uses_directory_label_without_reading_output(self):
        self.workspaces = [{"workspace_id": "wS", "label": "projects"}]
        self.tabs = {"wS": [{"tab_id": "wS:t1", "label": "1"}]}
        self.panes = {
            "wS": [{
                "pane_id": "wS:p1",
                "cwd": "/workspace/projects",
                "tab_id": "wS:t1",
                "label": "old",
                "agent": "pi",
                "agent_status": "working",
            }],
        }

        plan = MODULE.discover(None)
        self.assertEqual([action["type"] for action in plan["actions"]], ["rename_pane"])
        self.assertEqual(plan["actions"][0]["pane_label"], "projects")

    def test_main_executes_without_secondary_confirmation(self):
        plan = {"source_workspace_label": "整个实例", "actions": []}
        with (
            mock.patch.object(MODULE, "discover", return_value=plan),
            mock.patch.object(MODULE, "print_plan") as print_plan,
            mock.patch.object(MODULE, "execute") as execute,
            mock.patch.object(MODULE.sys, "argv", [str(SCRIPT), "--all"]),
            mock.patch.dict(MODULE.os.environ, {"HERDR_ENV": "1"}),
        ):
            MODULE.main()
        print_plan.assert_called_once_with(plan)
        execute.assert_called_once_with(plan)

    def test_main_dry_run_only_prints_plan(self):
        plan = {"source_workspace_label": "整个实例", "actions": []}
        with (
            mock.patch.object(MODULE, "discover", return_value=plan),
            mock.patch.object(MODULE, "print_plan") as print_plan,
            mock.patch.object(MODULE, "execute") as execute,
            mock.patch.object(MODULE.sys, "argv", [str(SCRIPT), "--all", "--dry-run"]),
            mock.patch.dict(MODULE.os.environ, {"HERDR_ENV": "1"}),
        ):
            MODULE.main()
        print_plan.assert_called_once_with(plan)
        execute.assert_not_called()

    def test_duplicate_directory_names_use_readable_full_paths(self):
        self.workspaces = [{"workspace_id": "wS", "label": "Downloads"}]
        self.tabs = {
            "wS": [
                {"tab_id": "wS:t1", "label": "z"},
                {"tab_id": "wS:t2", "label": "c"},
            ],
        }
        self.panes = {
            "wS": [
                {"pane_id": "wS:p1", "cwd": r"Z:\\projects", "tab_id": "wS:t1"},
                {"pane_id": "wS:p2", "cwd": r"C:\\Users\\account\\projects", "tab_id": "wS:t2"},
            ],
        }

        plan = MODULE.discover(None)
        creates = [
            action["workspace_label"]
            for action in plan["actions"]
            if action["type"] == "create_workspace"
        ]
        self.assertCountEqual(creates, ["C-Users-account-projects", "Z-projects"])
        self.assertFalse(any(label.startswith("projects-") for label in creates))


if __name__ == "__main__":
    unittest.main()
