---
name: inspect
description: >-
  布局模型与状态发现：workspace/tab/pane/agent 拓扑、ID 语义、生命周期状态、
  发现命令。加载本模块以确定要控制的面板或 agent 及其当前状态。
---

# 布局、ID 与状态发现

## 创建 Space 与初始 Pane（直接路径）

当用户明确要求“新建当前目录的 space 并聚焦”时，不要先运行 `herdr --help` 或逐级探测命令；技能已固定该路径，直接执行：

```bash
test "${HERDR_ENV:-}" = 1 || exit 1
target_dir="$PWD"
test -d "$target_dir" || exit 1
label="$(basename "$target_dir")"
herdr workspace create --cwd "$target_dir" --label "$label" --focus
```

`--focus` 已同时完成创建和聚焦，不需要再调用 `workspace focus`。只有用户明确要求后台创建、不切换焦点时，才使用 `--no-focus`。

执行后直接从同一次 JSON 响应读取 `workspace_id`、`tab_id`、`pane_id` 和 `cwd` 并报告；不要为确认已知语法额外运行 help。后续通用说明如下：

## 按名称直达已有 pane/tab

用户说“聚焦到 `<名称>` 这个 pane/tab”时，运行仓库内脚本：

```bash
python3 scripts/focus-pane-by-label.py "<名称>"
```

脚本先读取一次 `herdr api snapshot`，在整个实例中精确匹配 tab 标签，并要求目标
tab 恰好包含一个 pane；只有唯一匹配时才从 snapshot 读取真实 `tab_id` 并执行
`herdr tab focus`。名称重复时用已确认的 workspace ID 限定：

```bash
python3 scripts/focus-pane-by-label.py "<名称>" --workspace "<workspace-id>"
```

脚本会在不存在、重复或多 pane tab 时拒绝操作，并输出目标的 workspace/tab/pane ID
及 cwd。当前 CLI 没有按标签直接聚焦 pane 的命令；此快捷路径适用于默认的“一 pane
一个 tab”布局，多 pane tab 应改用真实 pane ID 和方向型 pane 控制。

## 通用创建规则

若该 workspace/space 是为了让另一个 Agent 执行、随后回到当前对话验收，创建前必须先
执行 `herdr tab rename "$HERDR_TAB_ID" "主控-<具体任务>"`；只有改名成功后才进入下述
workspace 创建步骤。新 workspace 的执行 tab 使用“执行-<具体任务>”等语义名称，验收通过后
改为“完成-<具体任务>”；数字、`reviewer`、`worker` 等不透明默认名不合格。纯粹新建普通
shell space、不涉及另一个 Agent 和回到主控验收时，不强加这一编排规则。

用户说“space”时按 Herdr 的 `workspace` 处理。需要创建一个独立 workspace，
并让它自带的初始 pane 进入指定目录时：

1. 先确认当前 Agent 在 Herdr 管理的 pane 内：
   `test "${HERDR_ENV:-}" = 1`。
2. 用实际目标目录执行非聚焦创建命令；目标目录必须先确认存在：

   ```bash
   target_dir="<absolute-target-directory>"
   test -d "$target_dir" || exit 1
   herdr workspace create --cwd "$target_dir" --label "<workspace-label>" --no-focus
   ```

3. 从 JSON 响应读取不透明 ID，不按侧栏顺序猜测：
   `.result.workspace.workspace_id`、`.result.tab.tab_id` 和
   `.result.root_pane.pane_id`。
4. `root_pane` 就是新 workspace 中的第一个 pane，其 `cwd` 应与目标目录一致。
   需要更多独立工作面板时，在同一 workspace 创建 tab，并从响应读取新的
   `.result.root_pane.pane_id`：

   ```bash
   herdr tab create --workspace "$workspace_id" --cwd "$target_dir" --no-focus
   ```

   只有用户明确要求分屏时，才使用返回的 pane ID 执行 `herdr pane split`。

如果用户只要求一个新 pane 而不要求新 workspace，默认仍创建同一 workspace 下的
新 tab；已有分屏需要批量整理时，使用 `scripts/panes-to-tabs.sh`，不要逐个手工移动。

目录归属整理还必须满足用户的固定规则：每个规范化 `cwd` 对应唯一一个
space/workspace；所有相同 `cwd` 的 pane 必须在同一个 workspace。pane 使用该目录对应的
可读标签，已有 tab 标签保持不变。相同 workspace 不等于相同 tab，默认使用
“一 pane 一个 tab”，不能用 `pane split` 实现目录归属。

“按目录整理”“整理所有标签页/整个实例”“归属到对应 space”都路由到本功能，
不要误用只拆分 tab 的 `panes-to-tabs.sh`。`organize-panes-by-directory.py` 的范围契约是：
用户限定“当前 workspace”时使用 `--current`；用户明确指定 workspace 时使用
`--workspace <workspace-id>`；用户说“整个实例”“所有 workspace/标签页”或只说“整理”
而未限定范围时，必须使用 `--all`。`--all` 会先读取全部真实 `workspace_id`，在一次计划中
计算全部 pane 的目标、冲突和新建项，然后直接统一执行并验证；不能把全实例整理拆成只对
当前 workspace 的隐式操作。用户明确要求预览时才追加 `--dry-run`。发现同名
workspace 时，保留 `number` 最小者（缺失或并列时按 `workspace_id`），把其余同名
workspace 的 pane 移入保留项，再关闭清空后的重复 workspace；移动、目录标签更新与关闭
必须同时列入同一个预览计划，不能因标签冲突直接中止或要求用户手工整理。

## 拓扑与 ID

- 层级：workspace → tab → pane；pane 无论是否含 agent 都存在。
- 公开 ID 是稳定不透明句柄：workspace `w1`、tab `w1:t1`、pane `w1:p1`；
  关闭的 tab / pane ID 不复用。
- 面板跨 workspace 移动后获得新的 workspace-qualified ID。移动后继续用
  `.result.move_result.pane.pane_id` 或存活的 agent 名；旧值只报在
  `.result.move_result.previous_pane_id`，仅被移动进程继承的调用者上下文
  可继续解析旧 ID，不可作通用 agent 目标。

## Agent 生命周期状态

- `idle`：agent 可接收输入，且其 tab 在聚焦的 Herdr UI 中被见过。
- `done`：后台未见工作完成后的同源 idle 状态（未被看到）。
- `blocked`：识别到审批或提问 UI。
- `unknown`：有 agent 存在但无法分类；不证明完成。

聚焦 tab、或用 focus 命令指向该面板/agent 会将其标记为"已见"；CLI 读取
不标记"已见"。`idle` 表示 UI 层面就绪，`done` 是后台工作完成后的同一底层
状态；`blocked` 需处理输入；`unknown` 不证明完成，先读现场再下结论。

## 发现命令

```bash
herdr workspace list
herdr tab list --workspace "$HERDR_WORKSPACE_ID"
herdr pane current --current
herdr pane list --workspace "$HERDR_WORKSPACE_ID"
herdr agent list
```

Herdr 向每个托管面板注入调用者上下文：

```bash
printf '%s\n' "$HERDR_WORKSPACE_ID" "$HERDR_TAB_ID" "$HERDR_PANE_ID"
```

- 优先 `--current` 定位调用面板；省略目标可能命中用户或其他客户端的聚焦
  面板，不要那样做。
- 创建响应直接给出下一步 ID：`workspace create` 返回 `.result.workspace`、
  `.result.tab`、`.result.root_pane`；`tab create` 返回 `.result.tab` 与
  `.result.root_pane`；只有明确分屏时 `pane split` 才返回 `.result.pane`。
- 按目录归属整理时，用户明确限定当前 workspace 才运行
  `scripts/organize-panes-by-directory.py --current`；用户明确指定 workspace 才使用
  `--workspace <workspace-id>`；未限定范围的“整理”默认运行
  `scripts/organize-panes-by-directory.py --all`（脚本省略范围参数时也默认全实例）。
  移动到已有 workspace 或新建 workspace 的整批动作在用户明确要求整理后直接执行；脚本会
  同时规划、执行并验证 space/workspace、tab、pane 归属和目录标签，不再要求二次确认。
  只有用户明确要求预览时才追加 `--dry-run`。
