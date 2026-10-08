#!/usr/bin/env python3
"""回归测试：按名称聚焦必须使用唯一的单 pane tab。"""
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("focus-pane-by-label.py")
SPEC = importlib.util.spec_from_file_location("focus_pane", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FocusTargetTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "result": {
                "snapshot": {
                    "tabs": [
                        {"tab_id": "w1:t1", "workspace_id": "w1", "label": "财务"},
                        {"tab_id": "w2:t1", "workspace_id": "w2", "label": "财务"},
                        {"tab_id": "w1:t2", "workspace_id": "w1", "label": "代码"},
                    ],
                    "panes": [
                        {"pane_id": "w1:p1", "tab_id": "w1:t1", "cwd": "/finance"},
                        {"pane_id": "w2:p1", "tab_id": "w2:t1", "cwd": "/other"},
                        {"pane_id": "w1:p2", "tab_id": "w1:t2", "cwd": "/code"},
                    ],
                }
            }
        }

    def test_workspace_filter_selects_real_ids(self):
        tab, pane = MODULE.find_target(self.snapshot, "财务", "w1")
        self.assertEqual(tab["tab_id"], "w1:t1")
        self.assertEqual(pane["pane_id"], "w1:p1")

    def test_duplicate_label_is_rejected(self):
        with self.assertRaisesRegex(MODULE.FocusError, "多个匹配"):
            MODULE.find_target(self.snapshot, "财务")

    def test_missing_label_is_rejected(self):
        with self.assertRaisesRegex(MODULE.FocusError, "没有唯一匹配"):
            MODULE.find_target(self.snapshot, "不存在")

    def test_multi_pane_tab_is_rejected(self):
        snapshot = {
            "result": {
                "snapshot": {
                    "tabs": [{"tab_id": "w1:t1", "workspace_id": "w1", "label": "代码"}],
                    "panes": [
                        {"pane_id": "w1:p1", "tab_id": "w1:t1"},
                        {"pane_id": "w1:p2", "tab_id": "w1:t1"},
                    ],
                }
            }
        }
        with self.assertRaisesRegex(MODULE.FocusError, "不是单 pane tab"):
            MODULE.find_target(snapshot, "代码")


if __name__ == "__main__":
    unittest.main()
