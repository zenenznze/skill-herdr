---
name: troubleshoot
description: >-
  herdr 常见错误与排查：CLI 退出码与错误格式、agent_prompt_stalled、blocked、
  wait 超时、读不到输出的 alternate screen 场景、目标不确定。
---

# 错误处理与排查

## 退出码与错误格式

- CLI 服务器错误：stderr 上输出 JSON，退出码 1。
- CLI 语法错误：退出码 2。
- 探测只用于非破坏命令；绝不省略参数探测会真实执行的嵌套命令
  （如 `workspace create`）。

## 常见错误对照

| 现象 | 处理 |
| --- | --- |
| `agent_prompt_stalled` | 从非工作状态发起的 prompt 5 秒内无生命周期变化。先 `agent get` / `agent read` 确认状态再决定下一步，不要无差别重发。 |
| `blocked` | agent 在审批/提问 UI。检查 `agent get` 与 `agent read`，对症发输入（`send-keys` 或 prompt）。 |
| wait 超时 | 先 `agent get` + `agent read` 读现场再判断；不要盲目再 prompt。`start-pi-agent-workspace.py` 会自动输出 `status=timeout`、`agent_task_result=unknown` 并保留资源；退出码 3 表示结果不确定，不是 agent 任务失败。 |
| 读不到完整输出 | 典型 alternate screen 场景。加大 `--lines` 无效，改用写文件回退方案（见 `modules/pane/MODULE.md`）。 |
| `unknown option` | 参数名不存在或拼错。`herdr --help` 查证；本技能没有 `--skills`，正确选项是单数 `--skill`（打印 agent 技能文件）。 |
| 目标不确定 | 省略目标可能命中用户或其他客户端的聚焦面板。改用 `--current`、显式 pane ID 或唯一 agent 名。 |
| 等待依赖 UI 焦点 | `idle`/`done` 依赖 tab 被聚焦 UI 见过；聚焦 tab 或用 focus 命令标记已见（CLI 读取不标记）。 |

## 排查顺序

1. 前置校验 `test "${HERDR_ENV:-}" = 1`，确认本 agent 在 Herdr 内。
2. `herdr agent get <name>` 或 `herdr pane current --current` 确认目标存在且
   状态正确。
3. `agent read` / `pane read` 看现场输出。
4. 对症发输入或修正目标；不要无差别重发 prompt。
