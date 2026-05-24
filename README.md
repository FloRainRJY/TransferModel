# TransferModel

本地 LLM API 桌面代理。通过图形化界面配置多个上游 LLM 提供商，将 Claude Code、Codex 等工具的请求透明转发到指定的 API 端点。**上游 API Key 只保存在本地代理中，下游工具无需接触。**

## 功能

- **多上游转发**：支持 Anthropic 和 OpenAI 两种协议，可同时配置多个提供商
- **桌面 GUI**：PySide6 原生桌面界面管理提供商，无需编辑配置文件
- **实时统计**：仪表盘实时显示输入/输出 Token 用量、缓存命中、会话总计
- **流式透传**：SSE 流式响应零缓冲转发，自动解析 token 用量
- **日志回放**：完整记录每次请求的模型、耗时、Token 明细和回复内容
- **系统托盘**：最小化到托盘后台运行，关闭窗口不退出
- **纯 Python**：零前端构建，零数据库，单命令启动

## 环境要求

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) 包管理器

## 安装与启动

### macOS

```bash
# 1. 安装 uv（如未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 进入项目目录，安装依赖
cd TransferModel
uv sync

# 3. 启动
uv run python main.py
```

首次启动 macOS 可能会提示"无法验证开发者"，去 **系统设置 → 隐私与安全性** 点击"仍要打开"。

### Windows

```powershell
# 1. 安装 uv（如未安装，PowerShell 中执行）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. 进入项目目录，安装依赖
cd TransferModel
uv sync

# 3. 启动
uv run python main.py
```

## 使用步骤

1. 启动应用，在「提供商」标签页点击「添加提供商」
2. 填写上游 API 信息：

   | 字段 | DeepSeek 示例 |
   |------|--------------|
   | API 类型 | `anthropic` |
   | 上游 URL | `https://api.deepseek.com/anthropic` |
   | API Key | `sk-xxxxxxxx` |
   | 模型列表 | `deepseek-v4-pro`（每行一个） |

3. 点击「测试连接」确认连通，然后「保存」
4. 切换到「仪表盘」，点击「启动代理」
5. 状态栏显示绿色运行状态即为就绪

![主界面仪表盘](img.png)

![提供商管理](img_1.png)

### 配置下游工具

**Claude Code（macOS / Linux）：**

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8080
export ANTHROPIC_AUTH_TOKEN=any-value      # 任意值，Key 在代理中
export ANTHROPIC_MODEL=deepseek-v4-pro
```

**Claude Code（Windows PowerShell）：**

```powershell
$env:ANTHROPIC_BASE_URL="http://127.0.0.1:8080"
$env:ANTHROPIC_AUTH_TOKEN="any-value"
$env:ANTHROPIC_MODEL="deepseek-v4-pro"
```

**Codex / OpenAI CLI：**

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8080/v1
export OPENAI_API_KEY=any-value
```

建议将以上环境变量写入 shell 配置文件（`~/.zshrc`、`~/.bashrc` 或 Windows 系统环境变量），避免每次手动设置。

## 模型路由

代理根据请求中的 `model` 字段自动匹配上游提供商。路由规则：

1. 请求路径决定协议类型：`/v1/messages` → anthropic，`/v1/chat/completions` → openai
2. 在对应协议的已启用提供商中精确匹配模型名
3. 多个匹配时选优先级最低的（数字越小越优先）
4. 无匹配返回 400，附带可用模型列表

## 配置项

所有配置通过环境变量覆盖（前缀 `TM_`），也可在应用内「设置」标签页修改端口和日志级别。

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `TM_HOST` | `127.0.0.1` | 监听地址 |
| `TM_PORT` | `8080` | 监听端口 |
| `TM_LOG_LEVEL` | `info` | 日志级别 (debug/info/warning/error) |
| `TM_DATA_DIR` | `./data` | 数据与日志存储目录 |
| `TM_PROVIDER_TIMEOUT` | `120` | 上游请求默认超时（秒） |
| `TM_PROVIDER_PRIORITY` | `10` | 新建提供商默认优先级 |
| `TM_ANTHROPIC_VERSION` | `2023-06-01` | Anthropic API 协议版本 |
| `TM_TEST_TIMEOUT` | `15` | 测试连接超时（秒） |
| `TM_POLL_MS` | `500` | 仪表盘刷新间隔（毫秒） |

示例：

```bash
# macOS / Linux
TM_PORT=9090 TM_LOG_LEVEL=debug uv run python main.py

# Windows PowerShell
$env:TM_PORT="9090"
$env:TM_LOG_LEVEL="debug"
uv run python main.py
```

## 数据存储

所有配置和日志保存在 `data/` 目录：

```
data/
├── providers.json    # 提供商配置
├── settings.json     # 服务器设置
└── proxy.log         # 请求日志
```

可设置 `TM_DATA_DIR` 环境变量自定义路径。

## 常见上游配置

| 服务商 | API 类型 | 上游 URL |
|--------|---------|----------|
| Anthropic 官方 | anthropic | `https://api.anthropic.com` |
| DeepSeek | anthropic | `https://api.deepseek.com/anthropic` |
| OpenAI 官方 | openai | `https://api.openai.com/v1` |
| 硅基流动 | openai | `https://api.siliconflow.cn/v1` |
| 通义千问 | openai | `https://dashscope.aliyuncs.com/compatible-mode/v1` |

## 项目结构

```
TransferModel/
├── main.py                    # 桌面应用入口
├── pyproject.toml             # 依赖声明
└── transfermodel/
    ├── config.py              # 统一配置（环境变量可覆盖）
    ├── models.py              # 数据模型
    ├── storage.py             # JSON 持久化
    ├── proxy.py               # 流式代理 + SSE 解析
    ├── routers_proxy.py       # 代理路由 + 模型匹配
    ├── app.py                 # FastAPI 应用工厂
    ├── server.py              # QThread 服务器管理
    ├── logger.py              # 日志系统（文件 + Qt 信号）
    ├── usage_tracker.py       # Token 用量追踪（线程安全）
    └── ui/
        ├── main_window.py     # 主窗口
        ├── dashboard_tab.py   # 仪表盘（实时统计）
        ├── providers_tab.py   # 提供商管理
        ├── provider_dialog.py # 提供商编辑对话框
        ├── settings_tab.py    # 设置
        ├── log_tab.py         # 实时日志查看
        ├── tray.py            # 系统托盘
        └── styles.py          # Catppuccin 暗色主题
```
