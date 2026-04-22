# Launch 启动文件

`talos launch` 执行一个 YAML 文件，同时拉起多节点；按下 Ctrl+C 即可一键停掉
整张图。

## 最小示例

```yaml
# src/image_demo/launch/image_demo.launch.yaml
nodes:
  - name: image_subscriber
    package: image_demo
    executable: image_subscriber
    args: ["3"]

  - name: image_publisher
    package: image_demo
    executable: image_publisher
    args:
      - /opt/talosos/share/samples/image.png
      - "2.0"
    env:
      TALOS_LOG_COLOR: "1"
```

运行：

```bash
talos launch image_demo image_demo.launch.yaml
# 或直接传路径：
talos launch ./src/image_demo/launch/image_demo.launch.yaml
# 只预览不启动：
talos launch image_demo image_demo.launch.yaml --dry-run
```

## launch 帮你做了什么

- 每个节点的 stdout 以 `[<name>]` 前缀并用不同颜色区分。
- 所有子进程的 `LD_LIBRARY_PATH` 都前置 `<ws>/install/lib`。
- Ctrl+C 转发：先给所有子进程发 `SIGINT`，最多等待 3 秒；若未退出，升级为
  `SIGTERM`，再不退出就 `SIGKILL`。
- 每个节点退出时都打印其返回码。

## 字段说明

| 字段               | 类型          | 必填 | 说明 |
| ------------------ | ------------- | ---- | ---- |
| `package`          | string        | ✅   | 拥有该可执行文件的工作空间包 |
| `executable`       | string        | ✅   | 安装后的可执行文件名 |
| `name`             | string        |      | 默认与 `executable` 相同；launch 文件内唯一 |
| `args`             | list[str]     |      | 透传给子进程的命令行参数 |
| `env`              | map           |      | 合并到 launcher 环境变量之上 |

后续阶段会加入 `restart: true`、`remap:`、`include:` 等特性。
