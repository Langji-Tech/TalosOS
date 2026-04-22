# 局域网 / 跨设备部署

TalosOS 直接借用 zenoh 的发现能力——同一个局域网上的两台机器通常**无需配置**
就能互相找到。

## 简单模式：默认多播

两台机器各自安装 TalosOS，`source setup.bash` 之后启动各自的节点即可。
zenoh 对等端通过 UDP 多播 + TCP 单播协作构建全网状会话图。

A 机（发布者）：

```bash
source /opt/talosos/setup.bash
talos run my_pkg image_publisher
```

B 机（订阅者）：

```bash
source /opt/talosos/setup.bash
talos topic list        # 应当出现 camera/image/compressed
talos viz /camera/image/compressed --type CompressedImage
```

要求：

- 局域网允许 UDP 多播（家庭/办公室 LAN 通常支持；Docker 默认 `bridge`
  以及多数云 VPC **不支持**）。
- 防火墙放行 zenoh 的发现端口（默认多播组 `224.0.0.224:7446`，以及 TCP
  传输端口 7440 段）。

## 显式端点：多播不可用时

Docker、K8s、被分段的 LAN 等场景下，可以跳过自动发现，手动指定对等端地址。

A 机，监听：

```bash
talos run my_pkg image_publisher \
  --mode peer --listen tcp/0.0.0.0:7447 --no-multicast
```

B 机，主动连接到 A 的 IP：

```bash
talos run my_pkg image_subscriber \
  --mode peer --connect tcp/<BOX_A_IP>:7447 --no-multicast
```

`--listen/--connect/--mode/--no-multicast` 这四个参数在所有与 zenoh 对
接的位置都生效：`talos topic {pub,echo,hz,bw}`、`talos service call`、
`talosos_tool` 以及 C++ / Python `NodeOptions`。

!!! note "纯单播模式下时序很关键"

    纯单播时没有 scouting。建议**先启动监听端**，再让连接端连过去；
    或者让连接端带有重试逻辑——zenoh 会在后台持续尝试建立 session，但
    在 session 未建立前发布的消息会被丢掉。

## 基于路由器的拓扑

需要一对多扇出、或跨越 NAT 时，可以在一台可达的机器上起一个 zenoh
router，其余节点都连向它：

```bash
# 路由器
# （独立的 zenoh router，用 cargo install zenohd 即可安装）
zenohd -l tcp/0.0.0.0:7447

# 任意客户端
talos run my_pkg my_node --mode client --connect tcp/<ROUTER_IP>:7447
```

## 代码里指定 NodeOptions

C++：

```cpp
talos::NodeOptions opts;
opts.mode      = "peer";
opts.listen    = {"tcp/0.0.0.0:7447"};
opts.multicast = false;
auto node = talos::Node::Create("my_node", opts);
```

Python：

```python
from talosos.runtime import Node

node = Node.create(
    "my_node",
    mode="peer",
    listen=["tcp/0.0.0.0:7447"],
    multicast=False,
)
```
