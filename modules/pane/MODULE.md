---
name: pane
description: >-
  在兄弟面板运行普通命令（非 agent）、等待输出匹配、按来源读取面板输出的
  完整流程，含 read source 选择与 alternate screen 回退。
---

# 普通命令与输出读取

## 开面板

若新 tab 用于另一个 Agent/执行终端并最终回到当前对话验收，先把当前主控 tab 改为
“主控-<具体任务>”，改名成功后再创建带“执行-<具体任务>”语义标签的新 tab：

```bash
herdr tab rename "$HERDR_TAB_ID" "主控-运行完整测试"
herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$PWD" --label "执行-运行完整测试" --no-focus
```

不得把顺序倒置，也不得使用数字、`reviewer`、`worker` 等不透明标签。验收通过后，把执行
 tab 改为“完成-运行完整测试”或等价完成态名称；主控 tab 保留任务与主控身份。普通命令
面板若不属于“另一个 Agent 执行并回主控验收”的流程，可仅按任务语义命名。

从 `.result.root_pane.pane_id` 读取新 tab 的 pane ID。只有用户明确要求“分屏 /
 split”时，才使用 `pane split`；已有多个分屏需要整理时，使用
`scripts/panes-to-tabs.sh` 批量处理。

## 运行与等待输出

```bash
herdr pane run <pane-id> "just test"
herdr pane wait-output <pane-id> --match "test result" --timeout 120000
```

- `pane run` 原子发送命令文本 + Enter。
- `wait-output` 立即搜索选中快照，因此已存在的输出也能匹配。`--match <text>`
  是字面子串，`--regex <pattern>` 是 Rust 正则。省略 `--timeout` 允许无限等待。

## 读取输出（来源选择）

| 来源 | 用途 |
| --- | --- |
| `visible` | 当前渲染视口 |
| `recent` | 近期渲染输出，含软换行 |
| `recent-unwrapped` | 软换行已连接；日志与逐字稿优先用它 |
| `detection` | 纯文本底部缓冲快照，用于 agent 检测 |

```bash
herdr pane read <pane-id> --source recent-unwrapped --lines 120
```

- 颜色与终端样式是证据时用 `--format ansi`，否则用 text。
- `--lines` 向宿主 scrollback 要更多行。若加大行数仍读不全完整回复，面板
  多半在 terminal alternate screen 上跑 agent——离屏行不进 Herdr 宿主
  scrollback，行数再多也无法找回。
- 该失败后的回退：让 agent 把完整回复写成 Markdown 到临时目录，只回文件
  路径，再直接读文件。仅作为回退，不要在初始 prompt 就要求文件输出。
