# `talos` CLI 参考

运行 `talos --help` 查看顶层子命令，`talos <cmd> --help` 查看子命令参数。

## 工作空间

| 命令 | 作用 |
| ---- | ---- |
| `talos pkg create <name> [--with-node] [--description ...]` | 创建新功能包骨架。当前目录名为 `src` 时自动初始化工作空间（ROS1 风格）。 |
| `talos pkg list [--verbose] [--json]` | 列出工作空间内所有包。 |
| `talos build [pkgs...] [-j N] [--build-type Release]` | 对每个包 configure+build+install 到 `<ws>/install`。 |
| `talos run <pkg> <exe> [args...]` | 执行已安装的可执行文件，并自动注入工作空间路径。 |

## 话题工具

以下所有 topic 命令都支持 zenoh 网络参数：`--mode {peer,client,router}
--connect ENDPOINT --listen ENDPOINT --no-multicast`。

| 命令 | 说明 |
| ---- | ---- |
| `talos topic pub <key> --utf8 STR \| --hex HEX [--count N] [--rate HZ]` | 发布原始字节 payload。 |
| `talos topic echo <key> [--count N]` | 实时打印接收到的消息（十六进制摘要）。 |
| `talos topic hz <key> [--window S] [--report-period S] [--count N]` | 测量消息频率。 |
| `talos topic bw <key> [--window S] [--report-period S] [--count N]` | 测量带宽。 |
| `talos topic list [--verbose] [--timeout-ms MS]` | 通过 zenoh liveliness 列出已注册的话题。 |
| `talos topic info <key>` | 查看某一 key 的发布者集合。 |

## 服务工具

| 命令 | 说明 |
| ---- | ---- |
| `talos service call <key> --utf8 STR \| --hex HEX [--timeout-ms MS]` | 一次性调用一个服务。 |
| `talos service list` | 列出所有活动服务。 |
| `talos service info <key>` | 查看某一服务的提供者集合。 |

## Launch

| 命令 | 说明 |
| ---- | ---- |
| `talos launch <file>` | 启动一个 YAML 文件中定义的节点图。 |
| `talos launch <package> <file>` | 在某个包的 `launch/` 目录下解析 `<file>`。 |
| `talos launch ... --dry-run` | 只打印将要启动的进程，不真的执行。 |

## rqt 工具箱

| 命令 | 说明 |
| ---- | ---- |
| `talos plot <topic> --type <Msg> [--field path] [--history N]` | 实时 matplotlib 曲线。 |
| `talos viz  <topic> --type <Msg> [--renderer ...]` | 面向具体消息类型的渲染器。 |
| `talos rqt` | PyQt5 主壳，托管多个 plot/viz 子面板。 |

## Tab 补全

Bash 与 zsh 的补全脚本在 `source setup.bash` / `setup.zsh` 时自动注册。
它会补全子命令、消息类型、话题名（通过实时 `talos topic list` 获取）、
功能包名以及 `<pkg>/launch/` 下的 launch 文件名。
