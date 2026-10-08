---
name: agent
description: >-
  在现成 shell 面板中启动 coding agent、提交提示、等待生命周期状态、按键
  控制与读取 agent 输出的完整流程。
---

# 启动与协调 coding agent

## 目标与命名规则

- agent 命令接受唯一存活 agent 名，或承载该 agent 的 pane ID；不接受
  terminal ID 或裸的 agent 种类标签。
- 名称匹配 `[a-z][a-z0-9_-]{0,31}` 且须在存活 agent 中唯一；名称跟随当前
  面板占用者，agent 退出、被释放或被替换时清除。
- `agent start` 要求现成的可用 shell 面板：位于交互提示符、shell 本身在前台、
  无前台命令/编辑器/agent 在跑。它从不创建、分割或移动布局。

## 用户可见名称与内部名称

- 用户说“重命名每一个 agent”时，默认修改承载 agent 的 **tab 显示名称**，使用
  `herdr tab rename <tab-id> <中文任务名称>`；中文是默认命名语言。
- 不要把这句话自动解释成 `herdr agent rename`。该命令修改的是用于 CLI 定位的内部
  agent name，只接受 `[a-z][a-z0-9_-]{0,31}`；仅在用户明确要求内部调用标识时使用。
- 先用一次 snapshot 锁定当前存活对象；任务不明确时读取各 pane 的近期输出，再生成简短、
  可辨识的中文任务名。改名时逐个处理 snapshot 中仍存活的 tab；某个 pane 已退出则跳过，
  继续处理其余对象，最后重新读取 snapshot 验证。
- 同时调整 space 名称时，以 pane 的真实 `cwd` 为依据。所有 pane 同目录时使用目录 basename；
  多目录时转交 `modules/inspect/MODULE.md` 的按目录整理流程，不根据 tab 任务名猜 space 名。

## 编排契约：控制层与执行层分工

把 Herdr 视为**控制平面**，把 Pi/Codex 等视为**执行平面**。控制 Agent 不把“启动成功”
或生命周期 `done` 当成任务已验收；完整闭环是：

1. **封装任务上下文**：子 Agent 不自动继承当前对话。prompt 至少写明目标、必须加载的
   skill/规则、可信输入来源、时间或身份边界、允许写入范围、验收输出和禁止项；不要只写
   “继续刚才的事”。涉及“当前日期”“用户本人”“已有资料”时必须明确来源与防误用条件。
2. **先命名主控，再创建执行终端**：从当前 `HERDR_TAB_ID` 读取主控 tab，先执行
   `herdr tab rename "$HERDR_TAB_ID" "主控-<具体任务>"`；成功后才能创建 workspace/tab。
   执行 tab 使用“执行-<具体任务>”等透明名称，禁止数字、`reviewer`、`worker`、`agent`
   等默认角色名。新 workspace 只跑一个 Agent 时，复用 `workspace create` 返回的 root pane，
   避免留下空 tab；只有还要保留 root shell 或继续增加 Agent 时才新建 tab。
3. **稳定派活**：只使用同次 JSON 返回的真实 ID 和 `agent start` 返回的真实 agent name。
4. **读取结果**：落定后回读 `recent-unwrapped`；`done` 只表示生命周期落定，不证明回答
   完整、文件正确或验收通过。
5. **独立验收**：只读任务检查回答是否覆盖要求；文件任务回到 owning repo 检查 diff、测试
   和 Git 边界。`blocked`、timeout、读回失败都属于 inconclusive，先取状态与输出再处理。
6. **验收后先标记完成态，再主动清理**：验收终端逐一读取每个执行终端的状态和最终输出，按任务标准确认结果已整合或无需保留，且不存在 `blocked`、`unknown`、未交付修改、待修正或其他未决事项。`done`、`idle`、退出码和 Agent 自报完成均不能单独授权关闭。只有通过独立验收后，才先执行 `herdr tab rename <execution-tab-id> "完成-<具体任务>"`，再由验收终端关闭或按用户要求保留对应 tab/pane；主控 tab 保留“主控-<具体任务>”语义名。
7. **复核完整拓扑并最终汇报**：所有执行终端处理后，再检查全实例 workspace/tab/pane/agent 拓扑，关闭不再需要的空 shell、转发终端和任务创建的 workspace，只保留原验收/汇报终端及用户明确要求保留的终端。最终必须从原验收终端逐项报告验收结论、关闭对象及理由、保留对象、阻断，以及“当前是否可以清理/是否已完成清理”；不得让用户另开窗口追问清理状态。
8. **报告资源与证据**：报告 workspace/tab/pane/agent ID、最终状态、关键结果或阻断；不要只说
   “Agent 已启动”。

## 多步骤顺序委派：单动作执行对话

当用户明确要求把一个多步目标按依赖顺序拆到多个对话，或指定某一步由独立对话完成时：

- 先按用户给定的顺序识别当前已解锁的一步。前置步骤尚未达到用户验收条件时，
  不启动依赖它的后续执行对话，也不提前做后续变更。
- 每个新开的执行对话只承接一个有界、可验收的动作/交付物。Prompt 写清该步目标、
  必要前提、允许写入范围、验收输出和禁止的后续事项；必要的本步门禁与验证属于
  该动作，不要把后续交付也塞进 prompt，或要求子对话自动接着往下做。
- 子 Agent 落定后，原控制对话回读结果并按权威现场独立验收；`done`、Agent 自报完成
  或用户对后续步骤的预先描述都不替代验收。若结果 blocked、unknown 或仍有未决事项，
  停止依赖链并报告阻断，不跳过前置步骤。
- 前一步验收通过后，回到原控制对话按用户顺序恢复，只启动或执行当前已解锁的下一步；
  不重做已经完成的动作。若用户指定后续步骤留在原对话完成，就由原对话继续，
  不把它追加给刚完成的子对话。
- 这里的“一个动作”指一个用户可验收的主要交付边界，不是限制该执行对话完成本步所需的
  门禁、读取和验证；此规则仅适用于用户明确要求的分对话/顺序委派，不改变普通任务的默认布局。

## 确定性快捷路径：新 workspace 中启动 Pi

当请求同时指定目标 cwd、workspace 标签、agent 名、tab 标签、prompt 和等待
超时时，使用仓库脚本，不手工拼接多条控制命令：

```bash
python3 scripts/start-pi-agent-workspace.py \
  --cwd /absolute/project \
  --workspace-label login-fix \
  --agent-name login-fix \
  --tab-label 执行-修复登录回归 \
  --controller-tab-label 主控-修复登录回归 \
  --completed-tab-label 完成-修复登录回归 \
  --prompt-file /path/to/prompt.md \
  --wait-timeout 120000 \
  --use-workspace-root-pane \
  --result-lines 120 \
  --no-focus-workspace
```

`--prompt` 与 `--prompt-file` 必须二选一；默认不聚焦，也可改为
`--focus-workspace`。脚本严格要求 `HERDR_ENV=1`，从同次 JSON 读取真实 ID。
单 Agent workspace 推荐 `--use-workspace-root-pane`；不传时保持兼容行为，另建
`--new-agent-tab`。`--controller-tab-label` 与 `--completed-tab-label` 省略时分别从
`--tab-label` 派生 `主控-...` / `完成-...`；脚本会在 `workspace create` 前先重命名
当前 `HERDR_TAB_ID`，并拒绝数字、`reviewer`、`worker` 等不透明执行标签。完成态标签只
作为验收后的明确契约写入报告，不能在脚本等待落定时自动套用，因为落定不等于主控验收。
Pi 启动成功后，prompt 目标改用 `agent start` JSON 返回的真实
agent name。全程不 split，也不关闭任何资源。

输出是一个 JSON 阶段报告。正常落定后会按 `--result-lines` 自动执行
`agent read --source recent-unwrapped`，把最终输出证据纳入阶段报告；控制 Agent 仍需按
任务验收标准判断内容是否合格。若状态为 `blocked`，脚本额外读取 `agent get` 并返回退出码
3；`prompt --wait` 超时时也会读取状态与近期输出，保留新建资源并返回退出码 3、
`status=timeout`、`agent_task_result=unknown`。这些都表示结果不确定，不等于执行任务失败。

## 默认布局（除非用户明确要求其他拓扑/位置）

- 默认：当前 workspace 下的新 tab + 当前工作目录；不新建 workspace /
  worktree / 其他 cwd，也不使用分屏。
- 保留调用者 cwd，用户焦点不动：

```bash
herdr tab rename "$HERDR_TAB_ID" "主控-检查支付回归"
herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$PWD" --label "执行-检查支付回归" --no-focus
```

第一条命令成功是第二条命令的前置条件；不能先创建执行 tab 再补主控名称。

从返回的 `.result.root_pane.pane_id` 读取新 tab 的 pane ID。
只有用户明确要求“分屏 / split”时，才改用 `pane split`。

## 启动

```bash
herdr agent start payment-check --kind codex --pane <returned-pane-id>
```

- kind 用用户要求的种类；`herdr agent`（不带子命令）列出已装 kind 与选项。
- 原生 agent 参数放 `--` 之后：
  `herdr agent start payment-check --kind codex --pane <id> -- <agent-args...>`
- `agent start` 直到检测到预期 agent 且认为可交互输入才返回；默认 30 秒
  启动超时。

## 派活与等待

```bash
herdr agent prompt payment-check "Review the current diff and report only actionable findings." --wait --timeout 120000
```

- `agent prompt` 原子提交文本并编码 Enter，同时尊重面板的 bracketed-paste
  模式。
- **Git Bash/MSYS 斜杠命令铁律**：发送 `/accounts`、`/reload`、`/model` 等
  以 `/` 开头的 TUI 命令时，MSYS 会把参数误改写为 Windows 路径（例如
  `/accounts` → `C:/Program Files/Git/accounts`）。必须对该次 CLI 调用禁用
  参数路径转换：

  ```bash
  MSYS_NO_PATHCONV=1 herdr agent prompt reviewer "/accounts" --wait --timeout 120000
  ```

  发送后立即用 `agent read` 验证屏幕中仍是原始斜杠命令；若出现 Windows
  路径，判定为调用层失败，不得据此诊断目标插件、命令或 Agent。
- 普通 agent 工作 `--wait` 足够：等待首个落定的 idle / done / blocked 状态；
  不要用 `--until` 重复这些默认值。
- 从非工作状态发起的 prompt 必须在 5 秒内观察到生命周期变化，否则返回
  `agent_prompt_stalled`。该等待跟踪生命周期状态而非单轮；若 agent 已在
  工作，当前轮的完成也可能满足它。
- `--until` 仅用于特定状态流程，如等一个正在运行的 agent 请求输入：

```bash
herdr agent wait payment-check --until blocked --timeout 120000
```

不带 `--until` 的独立 `agent wait` 与 `prompt --wait` 的落定默认一致。

## 交互控制与读取

```bash
herdr agent send-keys payment-check esc
herdr agent send-keys payment-check ctrl+c
herdr agent get payment-check
herdr agent read payment-check --source recent-unwrapped --lines 120
```

- `send-keys` 先校验全部按键再写任何字节；用逻辑键名（esc、ctrl+c 等）。
- wait 失败或返回 `blocked` 时，先看 `agent get` 与 `agent read` 再决定发
  什么输入；只有刻意做裸终端控制时才用 pane 面。
