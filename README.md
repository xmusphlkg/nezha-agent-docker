# Nezha Agent Docker 项目

## 项目简介
本项目通过 Docker 容器化技术部署 Nezha Agent，以便于在各种环境中快速、轻松地启动和管理 Nezha 监控系统的 Agent 组件。

## 功能特性
- **容器化部署**：简化 Nezha Agent 的部署和配置过程，确保环境一致性。
- **环境变量配置**：通过环境变量灵活配置，确保配置的安全性和灵活性。

## 使用方法

### 构建镜像

如果您希望自己构建 Nezha Agent 镜像，可以使用以下命令：

```bash
docker build -t nezha-agent .
```

### 拉取镜像
从 Docker Hub 拉取最新的 Nezha Agent 镜像：

```bash
docker pull kanggle/nezha-agent
```

如果无法拉取可以尝试使用国内镜像源：

https://www.wanpeng.life/2989.html

### 运行容器
使用以下命令来运行 Nezha Agent 容器，确保替换 `<your_client_secret>` 和 `<your_server>` 为实际的配置值：

```bash
docker run -d \
  -e CLIENT_SECRET='<your_client_secret>' \
  -e SERVER='<your_server>' \
  kanggle/nezha-agent
```

### 配置参数

以下表格列出了所有可配置的环境变量，它们的默认值以及是否为必填项：


| 参数名                      | 描述                           | 必须的 | 默认值            |
|---------------------------|--------------------------------|-------|-------------------|
| `CLIENT_SECRET`           | 客户端密钥，用于 Nezha 服务器的认证 | 是    | *无默认值，必须提供* |
| `SERVER`                  | Nezha 服务器的地址和端口           | 是    | *无默认值，必须提供* |
| `DEBUG`                   | 启用调试模式                       | 否    | `true`           |
| `DISABLE_AUTO_UPDATE`     | 禁用自动更新                       | 是   | `true`           |
| `DISABLE_COMMAND_EXECUTE` | 禁用命令执行                       | 否    | `false`           |
| `DISABLE_FORCE_UPDATE`    | 禁用强制更新                       | 是    | `true`        |
| `DISABLE_NAT`             | 禁用 NAT                          | 否    | `false`           |
| `DISABLE_SEND_QUERY`      | 禁用发送查询                       | 否    | `false`           |
| `GPU`                     | 启用 GPU 监控                      | 否    | `false`           |
| `INSECURE_TLS`            | 启用不安全的 TLS                   | 否    | `false`           |
| `IP_REPORT_PERIOD`        | IP 报告周期（秒）                  | 否    | `1800`            |
| `REPORT_DELAY`            | 报告延迟（秒）                     | 否    | `3`               |
| `SELF_UPDATE_PERIOD`      | 自更新周期（秒）                   | 否    | `0`               |
| `SKIP_CONNECTION_COUNT`   | 跳过连接计数                       | 否    | `false`           |
| `SKIP_PROCS_COUNT`        | 跳过进程计数                       | 否    | `false`           |
| `TEMPERATURE`             | 启用温度监控                       | 否    | `false`           |
| `TLS`                     | 启用 TLS                           | 否    | `false`           |
| `USE_GITEE_TO_UPGRADE`    | 使用 Gitee 进行升级                | 否    | `false`           |
| `USE_IPV6_COUNTRY_CODE`   | 使用 IPv6 国家代码                 | 否    | `false`           |


## 项目源码

https://github.com/nezhahq/agent