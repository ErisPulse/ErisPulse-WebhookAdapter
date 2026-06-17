# ErisPulse Webhook Adapter

[English](#english) | [中文](#中文)

---

<a id="english"></a>

## English

ErisPulse's **Webhook universal bridge adapter** (a low-code universal bridge). It is a bidirectional bridge adapter: it ingests messages from any external system into ErisPulse via HTTP, while forwarding messages emitted by ErisPulse modules to any target system via HTTP.

### Adapter Positioning

Each "account" is an independent **webhook bridge configuration**:

| Direction | Description |
|-----------|-------------|
| **Inbound (External → ErisPulse)** | External systems POST events to the webhook route registered by the adapter via HTTP; the adapter converts them into standard OneBot12 events and dispatches them |
| **Outbound (ErisPulse → External)** | When a module calls `adapter.Send.To(...).Text(...)`, the adapter POSTs the message to the account's configured `outgoing_url` (i.e., "the user subscribes a webhook to another system, providing a send API") |

One account = one inbound path + one outbound URL + one authentication secret.

### Installation

```bash
epsdk install

# Select `Adapter` to install the `Webhook` adapter
```

### Configuration

Configuration is located in the `[WebhookAdapter]` section of `config.toml`, or via the Dashboard's adapter configuration:

```toml
[WebhookAdapter.accounts.default]
bot_id = "webhook_bot"
callback_path = "/webhook/default"
outgoing_url = "https://example.com/api/receive"   # Module messages will be POSTed here
secret = "my-secret-key"                            # Authentication secret (empty = no verification)
detail_type = "private"                             # Default session type
enabled = true

# Multiple bridge accounts can be configured
[WebhookAdapter.accounts.discord_bridge]
bot_id = "discord_bot_123"
callback_path = "/webhook/discord"
outgoing_url = "https://my-discord-relay.example.com/send"
secret = "another-secret"
detail_type = "group"
enabled = true
```

#### Field Description

| Field | Default | Description |
|-------|---------|-------------|
| `bot_id` | `webhook_bot` | The bot identity ID represented by this bridge (written into the event's `self.user_id`) |
| `callback_path` | `/webhook/{account}` | Inbound path; supports the `{account}` placeholder (auto-replaced with the account name) |
| `outgoing_url` | `""` | Outbound target URL; empty means inbound only, no sending |
| `secret` | `""` | Authentication secret; empty means no inbound request verification |
| `detail_type` | `private` | Default session type, used when the inbound body does not specify `detail_type` |

### Inbound Protocol (External → ErisPulse)

#### HTTP Request

External systems POST to `{callback_path}/{account}` with a JSON body:

```json
{
  "user_id": "xxx",
  "user_nickname": "username",
  "group_id": "optional, group/channel ID",
  "detail_type": "private or group",
  "message": [{"type": "text", "data": {"text": "content"}}],
  "raw": {}
}
```

- When `detail_type` is not provided, the account's configured default is used
- `group_id` is only provided for group sessions
- `message` is an array of standard OneBot12 message segments
- `raw` is optional and stored as-is in `webhook_raw.raw`

#### Authentication

If the account has a `secret` configured, inbound requests must carry the secret (one of the following):

- Header: `X-Webhook-Secret: {secret}`
- Query: `?secret={secret}`

No verification is performed when `secret` is empty.

#### Health Check (GET)

On receiving a GET request, returns `{"status":"ok","account":"account_name"}`, which can be used for health checks.

#### Inbound Example

```bash
curl -X POST http://localhost:8000/webhook/default \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: my-secret-key" \
  -d '{
    "user_id": "u123",
    "user_nickname": "test_user",
    "detail_type": "private",
    "message": [{"type": "text", "data": {"text": "hello"}}]
  }'
```

Response:

```json
{"status": "ok"}
```

#### Converted OneBot12 Event

```json
{
  "id": "auto-generated",
  "time": 1700000000,
  "type": "message",
  "detail_type": "private",
  "platform": "webhook",
  "self": {"platform": "webhook", "user_id": "webhook_bot"},
  "user_id": "u123",
  "user_nickname": "test_user",
  "message": [{"type": "text", "data": {"text": "hello"}}],
  "webhook_raw": {},
  "webhook_account": "default",
  "webhook_raw_type": "message"
}
```

### Outbound Protocol (ErisPulse → External)

When a module calls `Send`, the adapter POSTs the message to the account's `outgoing_url`:

```json
{
  "target_type": "private|group|user",
  "target_id": "xxx",
  "account": "account_name",
  "message": [{"type": "text", "data": {"text": "content"}}],
  "timestamp": 1234567890
}
```

Request header (if `secret` is configured):

```
X-Webhook-Secret: {secret}
```

The adapter normalizes the response returned by the outbound target into a standard response format: it extracts the `message_id` field from the response JSON.

#### Send Example

```python
from ErisPulse import sdk

# Send text (using the default account)
await sdk.adapter.webhook.Send.To("user", "target_user_id").Text("hello")

# Send via a specific account
await sdk.adapter.webhook.Send.To("group", "group_123").Using("discord_bridge").Text("group message")

# Raw JSON passthrough
await sdk.adapter.webhook.Send.To("user", "u1").Json({"custom": "data"})

# OneBot12 raw message segments
await sdk.adapter.webhook.Send.To("user", "u1").Raw_ob12([
    {"type": "text", "data": {"text": "hello"}}
])
```

### Use Cases

#### Scenario 1: Integrating Your Own System

Your business system pushes user messages to ErisPulse via webhook for processing, then receives them back:

1. Configure an account with `callback_path` pointing to your inbound path, and `outgoing_url` pointing to your receiving API
2. The business system POSTs user messages to `callback_path`
3. After ErisPulse modules process them, reply messages are POSTed to `outgoing_url`

#### Scenario 2: Bridging Non-Natively Supported Platforms

Through an intermediate relay script, connect other platforms (such as self-built IM or enterprise internal systems) to ErisPulse without developing a full adapter.

#### Scenario 3: Webhook Relay

Act as a message relay: aggregate multiple webhook sources into ErisPulse for unified processing, then dispatch to multiple targets.

### Documentation

- [Platform Features](platform-features.md) — Inbound/outbound protocol details and field mappings

### License

MIT

---

<a id="中文"></a>

## 中文

ErisPulse 的 **Webhook 通用桥接适配器**（低代码万能桥）。它是一个双向桥接适配器：把任意外部系统的消息通过 HTTP 接入 ErisPulse，同时把 ErisPulse 模块发出的消息通过 HTTP 转发给任意目标系统。

### 适配器定位

每个「账户」即一个独立的 **webhook 桥接配置**：

| 方向 | 说明 |
|------|------|
| **入站（外部 → ErisPulse）** | 外部系统通过 HTTP POST 把事件发到适配器注册的 webhook 路由，适配器转换为 OneBot12 标准事件并分发 |
| **出站（ErisPulse → 外部）** | 模块调用 `adapter.Send.To(...).Text(...)` 时，适配器把消息 POST 到账户配置的 `outgoing_url`（即"用户订阅 webhook 到其他系统，提供发送 api"） |

一个账户 = 一个入站路径 + 一个出站 URL + 一个鉴权密钥。

### 安装

```bash
epsdk install

# 选择 `适配器` 安装 `Webhook` 适配器
```

### 配置

配置位于 `config.toml` 的 `[WebhookAdapter]` 段，或通过Dashboard的`适配器配置进行配置`：

```toml
[WebhookAdapter.accounts.default]
bot_id = "webhook_bot"
callback_path = "/webhook/default"
outgoing_url = "https://example.com/api/receive"   # 模块发消息会 POST 到这里
secret = "my-secret-key"                            # 鉴权密钥（留空则不校验）
detail_type = "private"                             # 默认会话类型
enabled = true

# 可以配置多个桥接账户
[WebhookAdapter.accounts.discord_bridge]
bot_id = "discord_bot_123"
callback_path = "/webhook/discord"
outgoing_url = "https://my-discord-relay.example.com/send"
secret = "another-secret"
detail_type = "group"
enabled = true
```

#### 字段说明

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `bot_id` | `webhook_bot` | 该桥接代表的机器人身份 ID（写入事件的 `self.user_id`） |
| `callback_path` | `/webhook/{account}` | 入站路径，支持 `{account}` 占位符（自动替换为账户名） |
| `outgoing_url` | `""` | 出站目标 URL，留空则仅入站不发送 |
| `secret` | `""` | 鉴权密钥，留空则不校验入站请求 |
| `detail_type` | `private` | 默认会话类型，入站 body 未指定 `detail_type` 时使用 |

### 入站协议（外部 → ErisPulse）

#### HTTP 请求

外部系统 POST 到 `{callback_path}/{account}`，body 为 JSON：

```json
{
  "user_id": "xxx",
  "user_nickname": "用户名",
  "group_id": "可选，群组/频道ID",
  "detail_type": "private 或 group",
  "message": [{"type": "text", "data": {"text": "内容"}}],
  "raw": {}
}
```

- `detail_type` 未提供时使用账户配置的默认值
- `group_id` 仅在群组会话时提供
- `message` 为 OneBot12 标准消息段数组
- `raw` 可选，原样存入 `webhook_raw.raw`

#### 鉴权

如果账户配置了 `secret`，入站请求需携带密钥（二选一）：

- Header：`X-Webhook-Secret: {secret}`
- Query：`?secret={secret}`

`secret` 留空时不校验。

#### 健康检查（GET）

收到 GET 请求时返回 `{"status":"ok","account":"账户名"}`，可用于健康检查。

#### 入站示例

```bash
curl -X POST http://localhost:8000/webhook/default \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: my-secret-key" \
  -d '{
    "user_id": "u123",
    "user_nickname": "测试用户",
    "detail_type": "private",
    "message": [{"type": "text", "data": {"text": "你好"}}]
  }'
```

响应：

```json
{"status": "ok"}
```

#### 转换后的 OneBot12 事件

```json
{
  "id": "自动生成",
  "time": 1700000000,
  "type": "message",
  "detail_type": "private",
  "platform": "webhook",
  "self": {"platform": "webhook", "user_id": "webhook_bot"},
  "user_id": "u123",
  "user_nickname": "测试用户",
  "message": [{"type": "text", "data": {"text": "你好"}}],
  "webhook_raw": {},
  "webhook_account": "default",
  "webhook_raw_type": "message"
}
```

### 出站协议（ErisPulse → 外部）

模块调用 `Send` 时，适配器把消息 POST 到账户的 `outgoing_url`：

```json
{
  "target_type": "private|group|user",
  "target_id": "xxx",
  "account": "账户名",
  "message": [{"type": "text", "data": {"text": "内容"}}],
  "timestamp": 1234567890
}
```

请求头（若配置了 `secret`）：

```
X-Webhook-Secret: {secret}
```

适配器会把出站目标返回的响应标准化为标准响应格式：从响应 JSON 中提取 `message_id` 字段。

#### 发送示例

```python
from ErisPulse import sdk

# 发送文本（使用默认账户）
await sdk.adapter.webhook.Send.To("user", "target_user_id").Text("你好")

# 指定账户发送
await sdk.adapter.webhook.Send.To("group", "group_123").Using("discord_bridge").Text("群消息")

# 原始 JSON 透传
await sdk.adapter.webhook.Send.To("user", "u1").Json({"custom": "data"})

# OneBot12 原始消息段
await sdk.adapter.webhook.Send.To("user", "u1").Raw_ob12([
    {"type": "text", "data": {"text": "hello"}}
])
```

### 使用场景

#### 场景一：接入自有系统

你的业务系统通过 webhook 把用户消息推给 ErisPulse 处理，处理后再回传：

1. 配置一个账户，`callback_path` 指向你的入站路径，`outgoing_url` 指向你的接收 API
2. 业务系统把用户消息 POST 到 `callback_path`
3. ErisPulse 模块处理后，回复消息会 POST 到 `outgoing_url`

#### 场景二：桥接非原生支持的平台

通过中间转发脚本，把其他平台（如自建 IM、企业内部系统）接入 ErisPulse，无需开发完整适配器。

#### 场景三：Webhook 中继

作为消息中继，把多个 webhook 源汇聚到 ErisPulse 统一处理，再分发给多个目标。

### 文档

- [平台特性说明](platform-features.md) — 入站/出站协议详解与字段映射

### 许可证

MIT
