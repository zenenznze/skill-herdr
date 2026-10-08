---
name: config
description: >-
  Herdr Session、shell 包装、安装、模式和个人快捷键偏好的配置流程。
---

# Herdr 配置与个人偏好

本模块负责 Herdr 的 Session 包装、安装、设备模式和个人快捷键配置。面板、tab、
pane、agent 控制仍由其他模块负责。

## 配置源

- `herdr-session.sh`：Bash/Zsh 包装函数的唯一源。
- `install.sh`：幂等安装/升级 shell 片段、`herdr1` 和兼容入口。
- `config/herdr/config.toml`：个人偏好模板，包含可复用的快捷键；不含设备凭据。
- `~/.config/herdr/session-mode`：每台设备本地的 Herdr CWD 拓扑（single/per-dir）
  与 Pi 会话策略（pi-resume）选择；两层保持正交。
- Linux/macOS 运行配置：`~/.config/herdr/config.toml`。
- Windows 运行配置：`%APPDATA%\herdr\config.toml`，可通过 `HERDR_CONFIG_PATH` 覆盖。

个人偏好模板当前约定：

```toml
[keys]
prefix = "ctrl+b"
rename_tab = "prefix+r"
```

模板不覆盖 `[theme]` 或主题 accent，因此使用 Herdr 官方默认主题与颜色。把模板复制到运行配置前，
先备份已有配置；不要在模板中加入 token、私钥或机器路径。

## 前置校验

```bash
command -v herdr
type herdr 2>/dev/null
cat ~/.config/herdr/session-mode 2>/dev/null
```

控制运行中的 session 前，必须确认：

```bash
test "${HERDR_ENV:-}" = 1
```

## 安装或升级

升级技能仓库提供的 shell 包装：

```bash
./install.sh --update
source ~/.bashrc   # 或新开终端
```

用户说“把 Herdr 更新到最新”时还必须升级 Herdr 本体，不能只更新包装。先运行
`herdr update --help` 确认真机语法。在 Herdr pane 内直接执行更新若提示必须 detach，
不要停止 server、关闭 pane 或 kill Herdr；改用当前二进制的绝对路径，并只对更新子进程
清除 Herdr 路由变量：

```bash
herdr_bin="$(command -v herdr)"
env -u HERDR_ENV -u HERDR_SOCKET_PATH -u HERDR_PANE_ID \
  -u HERDR_TAB_ID -u HERDR_WORKSPACE_ID "$herdr_bin" update
```

Windows 安装后当前 shell 的旧绝对路径可能仍报告旧版本；从安装输出给出的 release 目录
找到新二进制并用它验证版本，不把旧进程的 `herdr --version` 误报成升级失败。若安装器提示
已安装 integrations 需要更新，用新二进制逐项执行提示的 `integration install <kind>`；
不要凭空安装未提示或未使用的 integration。运行中的 server 可以继续工作，除非用户明确
要求或新版本必须重启，否则不停止它。

首次安装会创建缺省的 `mode=single` + `pi-resume=on` 模式文件，不覆盖已有模式。
完整冷恢复还需安装 Herdr 官方 Pi integration：
`herdr integration install pi`；不要手工编辑其生成的扩展文件。

**关键实现约束：** `herdr-session.sh` 顶层必须保留 Herdr 注入的
`HERDR_ENV`、`HERDR_SOCKET_PATH`、`HERDR_PANE_ID`、`HERDR_TAB_ID` 和
`HERDR_WORKSPACE_ID`。Pi integration 用其中的身份变量把真实的
`PI_SESSION_FILE/PI_SESSION_ID` 上报给 Herdr；Herdr 才能在断电/服务重启后的
snapshot restore 中执行精确的 `pi --session <path>`。只有 `_herdr_run` 调用嵌套
Herdr 时，才在子 shell 内清除这些路由变量。改动后必须跑
`./scripts/selftest.sh` 验证这两个边界。

## Session 模式

```sh
mode=single      # 所有目录共用默认 Session（缺省）
# mode=per-dir   # 每目录一个命名 Session
pi-resume=on     # 裸 pi 在 herdr Pane 内绑定该 Pane 自己的会话
```

- `per-dir` 配合 `[terminal] new_cwd = "current"`，新建 Tab/Pane 固定在绑定目录。
- `single` 配合 `new_cwd = "follow"`，新建内容跟随源 Pane 的 cwd。
- `pi-resume=on` 时 Pane 内裸 `pi` 注入
  `pi --session-id herdr-<Pane派生ID>`：这是正常运行/手动重启的确定性绑定，
  没有本目录对应会话则新建。实际会话身份是 `(Pane, Pi project bucket)`，
  不要把 cwd 再哈希进 ID；Pane 外裸 `pi` 全新开始。
- 官方 `herdr-agent-state` integration 会上报 Pi 实际 session path/id，供
  Herdr 的 `agent_session` 做 server 重启或 snapshot restore 的冷恢复；
  这是第二条恢复链，不替代上面的 deterministic binding。新建 pane 没有已保存的
  `agent_session`，因此只会打开 shell；其中首次裸 `pi` 只按新 pane ID 创建/查找
  自己的确定性 session，不会自动拾取其他 pane 的最近对话。
- 改动运行时配置后，对每个运行中的 Session 执行：
  `HERDR_SESSION=<名称> herdr server reload-config`。

## 验证

配置脚本改动后：

```bash
./scripts/selftest.sh
```

自测必须通过 Session 选择、参数透传、stdin 到达、pi 自动续会话和管理别名检查。
此外做一次真实路径抽验：默认模式下在不同目录运行 `herdr`/`herdr1`，确认均进入
共享/default Session；切换 `mode=per-dir` 后再确认进入目录对应的命名 Session，
涉及运行中 client 时确认输入 fd 仍指向 pane PTY。

## 故障处理

- 包装未生效：`type herdr` 不是函数时，运行 `./install.sh --update` 并重新 source。
- per-dir 新建标签掉到 `$HOME`：检查 `new_cwd = "current"` 并 reload config。
- Session 绑定目录错误：停止对应 Session 后，在正确目录重新启动。
- 冻结或输入失效：先走 `modules/troubleshoot/MODULE.md`，不要关闭未创建的 pane。
