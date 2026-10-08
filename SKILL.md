---
name: herdr
description: >-
  控制和配置 Herdr 终端工作区管理器（workspace/tab/pane）：查看布局与状态、
  新建独立 space/workspace 并为初始 pane 设置工作目录、按名称快速直达已有 pane/tab、定位面板和 agent、
  当主控需要新开终端/tab/space 让另一 Agent 执行并回当前对话验收时先重命名主控 tab、为执行 tab 使用任务语义名并在验收后标记完成态，
  在目标 cwd 的新 workspace 中直接使用 root pane 或新建独立 tab 启动 Pi agent、提交 prompt、读取最终输出并安全处理 blocked/等待超时，或在兄弟面板
  并行启动 coding agent、派活并等待完成、按键控制、读取输出与排查
  blocked/卡住问题；也用于安装按目录 Session 配置、切换 single/
  per-dir 模式、配置 pi 自动续会话，以及维护个人快捷键偏好；还用于按 pane 当前目录
  把当前或整个实例的标签页按 pane 当前目录整理到对应的 space/workspace，必要时创建缺少的 space。当用户
  明确提到 Herdr、herdr 命令、Session、面板、标签页、快捷键或配置，或要求整理分屏、让每个
  pane 独立成 tab、按目录整理、整理所有标签页时使用；仅因任务能从后台终端或并行中受益时不使用。
  运行控制命令前必须确认 HERDR_ENV=1。
  典型请求包括：用 herdr 开一个并行 reviewer agent、在 herdr session 里跑测试并读输出、
  split 一个 pane、start a codex agent in a sibling pane、wait for the agent to finish、
  agent blocked、读不到 herdr pane 输出；在新机器配置 herdr、per-directory session、
  single session、pi 自动恢复、升级配置，以及配置 herdr 快捷键偏好。
  也包括：让 herdr 里另一个 agent 看看这个 diff、herdr 的 agent 卡在 blocked 了帮我看看、
  并行跑几个 agent 分别检查不同文件、按名称或名为某名称聚焦 pane、我的设备要切成单 session 模式。
---

<!-- ASM_SKILL_UPDATE_GATE:START -->
## Mandatory startup update gate

Before this skill performs operational work, resolve the real path of this
`SKILL.md` and its owning Git checkout, then run:

```bash
python3 <agent-skills-dir>/skills/asm/bin/skill_update_gate.py run --skill <absolute-path-to-this-SKILL.md>
```

Continue only when the gate reports `status: ready`. If it fast-forwards the
checkout, re-read this skill and every changed module or executable that will
be used. Stop for dirty, ahead, diverged, detached, wrong-origin,
missing-upstream, fetch-failed, or non-fast-forward state; never stash, reset,
merge, force-pull, overwrite, or execute stale skill-owned code. A network-only
failure permits only an explicitly read-only request marked freshness-unverified.
Run the gate once per checkout per activation; sibling skills in the same
checkout reuse the result.
<!-- ASM_SKILL_UPDATE_GATE:END -->
# Herdr（终端工作区与配置）

Herdr 把终端组织成 workspace → tab → pane，识别面板内运行的 coding agent，
并通过 `herdr` CLI 暴露当前 session。本技能同时提供 Herdr 的操作能力和可复用
的 Session/快捷键配置；它们属于同一个 Herdr 工作流。

## 用户个人偏好（可选）

用户偏好优先使用 Herdr 官方默认主题与颜色（当前默认为 Catppuccin Mocha），
尤其是激活 pane 的高亮颜色；这只是跨机器复用时的默认偏好，不是强制规则。
仅当用户谈到主题、颜色、对比度或激活 pane 显示时，才提示或询问是否保持官方默认；
不要在无关对话中重复提示。用户明确选择其他主题或颜色时，以用户选择为准。

## 触发条件（Use when）

- 用户明确提到 Herdr / herdr 命令、session、面板、标签页或工作区
- 要求检查或控制面板、标签页、工作区、命令、或另一个 agent
- 要新建一个 space/workspace，并让其中的初始 pane 进入指定目录
- 要在目标 cwd 新建 workspace，复用 root pane 或创建独立 tab 启动 Pi agent、提交 prompt、等待并回读结果
- 要按 pane 当前目录整理当前 workspace 或整个实例的标签页到对应 space/workspace，必要时创建缺少的 space
- 想在兄弟面板并行运行 agent / 命令并读取输出
- 要在新机器安装或升级 Herdr 配置、切换 single/per-dir Session
- 要让裸 `pi` 自动恢复会话、排查 Session 串目录、冻结自愈或输入失效
- 要配置或复用 Herdr 个人快捷键偏好

## 不适用场景

- 仅因任务“能从后台终端 / 委派 / 并行中受益”而使用，无用户明确要求
- 前置校验失败（不在 Herdr 管理的面板内）
- 委派类任务已有专用技能（`delegate-code-execution`），Herdr 不替代委派协议

## 高频快捷路径：当前目录新建并聚焦 Space

用户说“新建当前目录的 space 并聚焦”时，直接执行以下固定路径，不先查 help：

```bash
test "${HERDR_ENV:-}" = 1 || exit 1
target_dir="$PWD"
test -d "$target_dir" || exit 1
herdr workspace create --cwd "$target_dir" --label "$(basename "$target_dir")" --focus
```

从返回 JSON 读取并报告 `.result.workspace.workspace_id`、
`.result.tab.tab_id`、`.result.root_pane.pane_id` 和 `cwd`。`--focus` 已经完成聚焦，
无需再调用 `herdr workspace focus`；只有不希望切换焦点时才用 `--no-focus`。

## 高频快捷路径：把每个 agent 重命名为中文

用户说“重命名每一个 agent”或类似表达时，默认含义是修改用户在侧栏看到的
**tab 显示名称**，不是修改 Herdr 的内部 agent name：

1. 先读取一次 `herdr api snapshot`，以其中当前仍存在的 tab、pane、cwd 和 agent 为准；
2. 对任务不明确的 pane，用 `herdr agent read <pane-id> --source recent-unwrapped --lines 120`
   读取现场并概括其当前任务；
3. 用简短、可辨识的**中文任务名称**执行 `herdr tab rename <tab-id> <中文名称>`；
4. 除非用户明确要求修改内部调用标识，不执行 `herdr agent rename`。内部 agent name 受
   `[a-z][a-z0-9_-]{0,31}` 限制，不等于用户可见的 tab 名称；
5. 执行前后都以新 snapshot 为准；读取期间已经退出、消失的 pane/tab 直接跳过，不让
   单个 `agent_not_found` 中断其他 tab 的改名；最后回读所有存活 tab 验证中文名称。

当同一请求还要求 Space 名称“按照真实目录”时，使用 snapshot 中 pane 的真实 `cwd`，
而不是根据任务、仓库猜测或沿用旧标签。一个 workspace 内所有 pane 的真实目录相同时，
将 workspace 重命名为该目录的 basename（例如 `C:\Users\<user>` → `<user>`）；存在多个不同
目录时，走“按目录自动归属 workspace”的整批预览与确认流程，不把整个 workspace 粗暴
命名为任意一个 pane 的目录。

## 高频快捷路径：按名称直达已有 pane/tab

用户说“聚焦到 `<名称>` 这个 pane/tab”时，默认按整个实例做名称精确匹配，直接运行技能仓库内的脚本：

```bash
python3 scripts/focus-pane-by-label.py "<名称>"
```

脚本会先读取一次 `herdr api snapshot`，只接受**唯一且只包含一个 pane 的 tab**，
再用 snapshot 返回的真实 `tab_id` 执行 `herdr tab focus`。它会输出并校验
`workspace_id`、`tab_id`、`pane_id`、`cwd` 和 `focused`；名称不存在、重复或对应
多 pane tab 时拒绝操作。重复名称可在确认真实 workspace ID 后限定范围：

```bash
python3 scripts/focus-pane-by-label.py "<名称>" --workspace "<workspace-id>"
```

Herdr 当前没有按标签直接聚焦任意 pane 的 CLI；本快捷路径依赖默认的“一 pane 一个
tab”布局。若目标是多 pane tab，先按真实 pane ID 读取现场，再使用方向型 pane 控制，
不要猜测 ID。

## 前置校验（控制命令铁律）

发出任何控制命令前，先验证本 agent 运行在 Herdr 管理的面板内：

```bash
test "${HERDR_ENV:-}" = 1
```

校验失败：说明不在 Herdr 内并停止；不得从 Herdr 外部检查或控制聚焦的
session。校验通过：PATH 中的 `herdr` 二进制只与本 session 通信。纯配置检查、
文件安装和 `herdr --help` 等非控制操作不需要操作面板。

## 入口路由

| 用户意图 | 加载 |
| --- | --- |
| 布局模型、ID 语义、agent 状态、发现面板/agent、创建 workspace/space | `modules/inspect/MODULE.md` |
| 按 pane 当前目录整理当前 workspace 或整个实例的标签页到对应 workspace，必要时创建 space | `modules/inspect/MODULE.md` |
| 启动 / 提示 / 等待 / 回读 / 按键控制 coding agent；新 workspace 中的 Pi 编排 | `modules/agent/MODULE.md` |
| 兄弟面板跑普通命令、等待输出、读取输出 | `modules/pane/MODULE.md` |
| 命令失败、stall / blocked、读不到输出 | `modules/troubleshoot/MODULE.md` |
| Session、shell 包装、安装、模式或个人快捷键配置 | `modules/config/MODULE.md` |

## 全局不变量（所有模块必须遵守）

1. **CLI 即权威** — 语法以本机 `herdr --help` 和各命令组输出为准。用命令组不带
   子命令做发现（`herdr agent`、`herdr pane` 等）；绝不跑裸 `herdr` 做发现
   （会启动/附加 TUI）。探测只用非破坏命令，不探测会真实执行的嵌套命令。
2. **ID 从 JSON 读** — workspace、tab、pane 是稳定不透明句柄；只从命令 JSON
   响应解析，不按侧栏顺序或示例猜测。
3. **显式目标** — 单个面板或单个 workspace 操作用 `--current`、显式 pane ID 或唯一
   agent 名；实例级整理必须显式使用 `--all`（或省略范围让脚本安全默认全实例），不依赖
   用户或其他客户端的聚焦面板。
4. **后台用 --no-focus** — 除非用户明确要求切换上下文焦点。
5. **不清理未创建之物** — 不关闭用户或其他客户端创建的 workspace / tab / pane /
   session，除非用户明确要求。
6. **两个禁止** — 不跑 `herdr server stop`（除非用户明确要停服务及其面板进程）；
   不 kill 主 herdr 进程。实验用命名测试 session 隔离。
7. **继承调用者上下文** — 默认在当前 workspace 创建独立 tab、沿用调用者 cwd，
   不新建 workspace / worktree，也不使用 `pane split`，除非用户明确要求该拓扑。
8. **主控先命名，再创建执行终端** — 当用户要求另一个 Agent 在新 tab / workspace /
   space 执行并回到当前对话验收时，必须先用当前 `HERDR_TAB_ID` 把主控 tab 改成
   “主控 + 具体任务”的语义名称，再创建任何执行 workspace/tab/pane。执行终端也必须使用
   具体任务语义名，禁止保留数字、`reviewer`、`worker`、`agent` 等不透明名称；此顺序适用于
   确定性脚本、当前 workspace 新 tab 和手工编排，不得事后补做。
9. **验收后标记完成态** — 执行 Agent 落定且经原主控独立验收后，先把执行 tab 改成
   “完成 + 具体任务”或等价自然语义，再按清理规则决定关闭或保留；主控 tab 始终保留
   可辨识的主控身份与任务名称。`done`、`idle` 或 Agent 自报完成不等于已验收。
10. **配置源分层** — `herdr-session.sh` 是 shell 包装的唯一源；
   `config/herdr/config.toml` 是个人偏好模板。设备运行时配置仍放在用户配置目录，
   不把 token、私钥或机器私密路径写入仓库。
9. **显示名称与内部名称分离** — 用户口语里的“agent 名称”默认指侧栏可见的 tab 标签；
   中文命名使用 `tab rename`。只有用户明确说“内部 agent name / 调用标识”时才使用
   `agent rename`，不得因内部名称不支持中文而拒绝给 tab 使用中文名称。

## 默认布局（重要）

- 默认采用“一 pane 一个 tab”：新建兄弟工作面板时使用 `tab create`，不要使用
  `pane split`；除非用户明确要求“分屏 / split”，否则不改变这个默认拓扑。
- 需要把已有分屏批量整理成独立 tab 时，运行仓库内的
  `scripts/panes-to-tabs.sh --current`，或指定 `--workspace <workspace-id>`；脚本只
  移动 pane、恢复或统一名称、使用 `--no-focus`，并在结束时验证每个 tab 只有一个 pane；移动时会保留
  原 tab 标签。按目录整理只依据 pane 的真实 `cwd`，不读取 agent 输出或自动改名 tab。
- `pane split` 仅是用户明确要求分屏时的例外，不是“新建一个 pane”的默认实现。

## 批量布局脚本

```bash
# 当前 Herdr workspace：保留每个现有 tab 的一个 pane，其余 pane 各自移到新 tab
scripts/panes-to-tabs.sh --current

# 指定 workspace；预览将要移动的 pane，不执行修改
scripts/panes-to-tabs.sh --workspace <workspace-id> --dry-run
```

“整理”只把布局归属和目录标签放入同一份计划：pane 按真实 `cwd` 使用可读目录标签，已有
tab 标签保持不变，不读取 agent 输出，也不根据回答自动改名。需要创建的
space/workspace/tab/pane、跨 workspace 移动和目录标签更新由同一次脚本运行统一执行并验证。

脚本使用 CLI JSON 返回的真实 ID，重复执行幂等；不要按侧栏顺序猜 ID，也不要把
多个独立的 `pane move` 操作改写成依赖焦点的手工命令串。

“整理”需要按语境路由：

- “一 pane 一个 tab”“不要分屏”“拆分多面板” → 使用 `panes-to-tabs.sh`，只调整 tab 布局。
- “按目录整理”“整理所有标签页/整个实例”“归属到对应 space”或未限定范围的“整理” → 使用
  `organize-panes-by-directory.py`，按 pane 的真实 cwd 创建或移动到对应 workspace，
  并使用目录推导的 pane 标签、保留已有 tab 标签。

## 按目录自动归属 workspace

先决定范围，再生成**一个覆盖完整范围的计划并直接执行**；裸“整理”不得默认缩小成当前
workspace，也不需要执行前二次确认：

- 用户明确说“当前 workspace” → 使用 `--current`；
- 用户明确指定 workspace → 使用 `--workspace <workspace-id>`；
- 用户说“整理”“所有标签页”“整个实例”“所有 workspace”，但没有限定范围
  → 使用 `--all`，覆盖整个 Herdr 实例。

用户明确要求整理后直接运行，不再预览并等待二次确认；只有用户明确要求预览时才使用
`--dry-run`：

```bash
# 整理整个实例并直接执行所有新建 workspace 与跨 workspace 移动
scripts/organize-panes-by-directory.py --all

# 仅在用户明确要求预览时使用
scripts/organize-panes-by-directory.py --all --dry-run
```

脚本按 pane 的真实 `cwd` 推导 workspace 名称；不存在则创建（新 workspace 的初始
root pane 会保留）。目录名唯一时直接使用目录名；若多个不同路径的末级目录同名，必须
用可读的完整路径区分（例如 `Z:\projects` → `Z-projects`、
`C:\Users\account\projects` → `C-Users-account-projects`），不得追加哈希、随机码或其他
无法从路径直接理解的代码。全实例模式会先读取所有 workspace，再统一计算目标、冲突和计划；
不能把多个 workspace 的整理拆成多个未关联的操作。计划会列出每个 pane、源 workspace、
目标 workspace、cwd、pane 标签、原 tab 标签和新建项；
执行后会验证归属、目录标签和原 tab 标签。若已有多个同名 workspace，脚本不再中止：保留 Herdr `number` 最小（通常最早创建）
的 workspace，若编号缺失或相同则按 `workspace_id` 稳定排序；把其他同名 workspace 的
pane 全部移入保留项，再关闭已经清空的重复 workspace。迁移、关闭、跨 workspace 移动、
新建/合并 workspace 以及同一批次内的全部结构操作由一次运行统一完成。执行仍使用 `--new-tab --no-focus`，
不会默认产生分屏。

## 相关技能

- `dev`：仓库验证、提交、推送和交付闭环；本仓库的配置脚本改动仍走 dev。
- `joe-agent`：安装、暴露、同步和治理技能，不替代本技能的 Herdr 操作。
- `delegate-code-execution`：有界委派协议；Herdr 只负责终端布局与并行运行。
