# 功能包与构建

## 工作空间

TalosOS 的**工作空间**是指包含 `.talos_ws` 标记文件的任何目录。标准布局：

```
my_ws/
  .talos_ws
  src/
    pkg_a/  (package.yaml, CMakeLists.txt, src/, include/)
    pkg_b/
  build/       (自动生成)
  install/     (自动生成)
```

延续 ROS1 的顺手习惯——**不需要手动** `touch .talos_ws`：

```bash
mkdir -p ~/catkin_style_ws/src
cd ~/catkin_style_ws/src
talos pkg create my_pkg             # 自动初始化工作空间
```

## 包清单 `package.yaml`

```yaml
name: my_pkg
version: 0.1.0
description: My robotics utility
depends:
  - talosos
executables:
  - my_pkg_node
```

`name` 必填；`executables:` 仅作信息字段，用于 `talos run <pkg> <exe>` 的
Tab 补全，并告诉使用者该包对外提供哪些可执行文件。

## `talos pkg`

```bash
talos pkg create <name>               # 在 src/ 下创建新包骨架
talos pkg create <name> --with-node   # 同时生成 src/<name>_node.cc 模板
talos pkg list                        # 每行一个包名
talos pkg list --verbose              # 包名、版本、路径
talos pkg list --json                 # 机器可读
```

## `talos build`

```bash
talos build                 # 构建工作空间中所有包
talos build my_pkg          # 指定单包
talos build -j8             # 传递给 cmake --build -j 8
talos build --build-type Debug
```

每个包在 `build/<pkg>/` 下做外部构建，并安装到 `install/<pkg>/lib/<pkg>/…`。
工作空间的 `install/` 会被自动加入 `CMAKE_PREFIX_PATH`，便于包之间互相 `find_package`。

## `talos run`

```bash
talos run my_pkg my_pkg_node              # 在当前工作空间的 install 中执行
talos run my_pkg my_pkg_node --foo bar    # 多余参数透传给子进程
```

可执行文件的查找顺序：

1. `<ws>/install/lib/<pkg>/<exe>`
2. `<ws>/install/bin/<exe>`
3. `<ws>/build/<pkg>/<exe>`（未安装的回退）

运行前 `<ws>/install/lib` 会被前置到 `LD_LIBRARY_PATH`，因此共享库依赖能够
无需额外配置即找到。
