import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ErisPulse.Core import client, router
from ErisPulse.Core.Bases.adapter import BaseAdapter
from ErisPulse.Core.config import config as config_mgr
from ErisPulse.Core.Event import register_event_mixin, unregister_platform_event_methods
from ErisPulse.runtime.config_schema import BotAccountConfig, dict_to_dataclass
from ErisPulse.Core.i18n import i18n

from .Converter import WebhookConverter


@dataclass
class WebhookAccountConfig(BotAccountConfig):
    """Webhook 桥接账户配置：一个账户 = 一个入站路径 + 一个出站 URL + 鉴权密钥"""

    bot_id: str = field(
        default="webhook_bot",
        metadata={
            "description": {"i18n": "webhook.bot_id", "default": "Bot 身份 ID（由此桥接表示）"},
            "required": False,
            "ui": {"widget": "text", "group": "basic", "order": 1},
        },
    )
    callback_path: str = field(
        default="/webhook/{account}",
        metadata={
            "description": {"i18n": "webhook.callback_path", "default": "入站回调路径（支持 {account} 占位符）"},
            "required": False,
            "ui": {"widget": "text", "group": "connection", "order": 2},
        },
    )
    outgoing_url: str = field(
        default="",
        metadata={
            "description": {"i18n": "webhook.outgoing_url", "default": "出站目标 URL（模块发送消息时 POST 到此地址）"},
            "required": False,
            "ui": {"widget": "text", "group": "connection", "order": 3},
        },
    )
    secret: str = field(
        default="",
        metadata={
            "description": {"i18n": "webhook.secret", "default": "鉴权密钥（留空则禁用验证）"},
            "required": False,
            "secret": True,
            "ui": {"widget": "password", "group": "basic", "order": 4},
        },
    )
    detail_type: str = field(
        default="private",
        metadata={
            "description": {"i18n": "webhook.detail_type", "default": "默认会话类型（body 未指定 detail_type 时使用）"},
            "required": False,
            "ui": {"widget": "text", "group": "basic", "order": 5},
        },
    )


WebhookAccountConfig._schema_meta = {
    "group_labels": {
        "basic": {"i18n": "webhook.group.basic", "default": "基本设置"},
        "connection": {"i18n": "webhook.group.connection", "default": "连接设置"},
    }
}  # type: ignore[attr-defined]


class WebhookEventMixin:
    """Webhook 事件扩展方法"""

    def get_raw_data(self) -> dict:
        """获取原始请求 body"""
        return self.get("webhook_raw", {}) or {}

    def get_detail_type(self) -> str:
        """获取会话类型（private/group 等）"""
        return self.get("detail_type", "private")

    def get_webhook_account(self) -> str:
        """获取产生该事件的账户名"""
        return self.get("webhook_account", "")


register_event_mixin("webhook", WebhookEventMixin)


class WebhookAdapter(BaseAdapter):
    """
    Webhook 通用桥接适配器

    双向桥接：
    - 入站：外部系统 POST 到 {callback_path}，转换为 OneBot12 事件分发
    - 出站：模块 Send 时，POST 消息到账户的 outgoing_url
    """

    _platform = "webhook"
    AccountConfigClass = WebhookAccountConfig

    class Send(BaseAdapter.Send):
        def Text(self, text: str):
            return self.Raw_ob12([{"type": "text", "data": {"text": text}}])

        def Image(self, file):
            return self.Raw_ob12([{"type": "image", "data": {"file": file}}])

        def Raw_ob12(self, message: list, **kwargs):
            async def _do_send():
                segments = self._apply_modifiers(message)
                ctx = self.send_context
                return await self._adapter.call_api(
                    endpoint="send_message",
                    _account_id=ctx.get("account_id"),
                    target_type=ctx.get("target_type"),
                    target_id=ctx.get("target_id"),
                    message=segments,
                    **kwargs,
                )

            return asyncio.create_task(_do_send())

        def Json(self, data):
            """
            原始 JSON 透传：将任意 JSON 数据作为消息段发送
            """
            return self.Raw_ob12([{"type": "json", "data": {"raw": data}}])

    def __init__(self, sdk_ref=None):
        super().__init__(sdk_ref)
        self._converters: Dict[str, WebhookConverter] = {}
        self._running = False
        self._registered_routes: List[str] = []
        self._register_i18n()

    def _register_i18n(self):
        """注册配置字段与日志消息的 i18n 翻译"""
        try:
            from ErisPulse.runtime.config_schema import register_config_i18n
            register_config_i18n(WebhookAccountConfig, "zh-CN", domain="webhook")
            register_config_i18n(WebhookAccountConfig, "en", {
                "webhook.bot_id": "Bot identity ID represented by this bridge",
                "webhook.callback_path": "Inbound callback path (supports {account} placeholder)",
                "webhook.outgoing_url": "Outbound target URL (when a module sends a message, it is POSTed to this address)",
                "webhook.secret": "Auth secret (leave empty to disable verification)",
                "webhook.detail_type": "Default session type (used when detail_type is not specified in the body)",
                "webhook.group.basic": "Basic",
                "webhook.group.connection": "Connection",
            }, domain="webhook")
        except Exception:
            pass

        zh_CN = {
            "webhook.old_config_detected": "检测到旧格式配置，建议迁移到多账户格式",
            "webhook.migration_hint": "迁移方法：将现有配置移动到 WebhookAdapter.accounts.default 下",
            "webhook.temp_load_old_config": "已临时加载旧配置为默认账户，请尽快迁移到多账户格式",
            "webhook.no_config_create_default": "未找到配置文件，创建默认桥接账户配置",
            "webhook.save_default_failed": "保存默认桥接账户配置失败: {error}",
            "webhook.accounts_loaded": "Webhook适配器初始化完成，共加载 {count} 个桥接账户",
            "webhook.unknown_account": "未知账户",
            "webhook.auth_failed": "账户 {name} webhook 鉴权失败",
            "webhook.auth_failed_msg": "鉴权失败",
            "webhook.invalid_json": "账户 {name} 收到无效JSON: {error}",
            "webhook.invalid_json_msg": "无效的JSON body",
            "webhook.body_not_object": "body 必须是 JSON 对象",
            "webhook.emit_failed": "账户 {name} 分发事件失败: {error}",
            "webhook.emit_failed_msg": "事件分发失败",
            "webhook.cannot_resolve_account": "无法解析账户",
            "webhook.no_outgoing_url": "账户 {name} 未配置 outgoing_url，无法发送消息",
            "webhook.no_outgoing_url_msg": "未配置 outgoing_url，无法发送出站消息",
            "webhook.outbound_debug": "Webhook出站: 账户={name} -> {url}",
            "webhook.outbound_failed": "Webhook出站请求失败({name}): {error}",
            "webhook.outbound_failed_msg": "出站请求失败: {error}",
            "webhook.unsupported_endpoint": "不支持的API端点: {endpoint}",
            "webhook.no_enabled_accounts": "Webhook适配器没有已启用的账户",
            "webhook.route_register_failed": "账户 {name} 注册路由 {path} 失败: {error}",
            "webhook.emit_connect_failed": "账户 {name} emit connect 失败: {error}",
            "webhook.outbound_not_configured": "(未配置，仅入站)",
            "webhook.account_started": "Webhook账户 {name} 已启动: GET/POST {path} | 出站 {outgoing}",
            "webhook.adapter_started": "Webhook适配器启动完成，共 {count} 个桥接账户",
            "webhook.unregister_route_failed": "注销路由 {path} 失败: {error}",
            "webhook.adapter_shutdown": "Webhook适配器已关闭",
        }
        en = {
            "webhook.old_config_detected": "Old format config detected, please migrate to multi-account format",
            "webhook.migration_hint": "Migration: move existing config under WebhookAdapter.accounts.default",
            "webhook.temp_load_old_config": "Temporarily loaded old config as default account, please migrate to multi-account format ASAP",
            "webhook.no_config_create_default": "No config found, creating default bridge account config",
            "webhook.save_default_failed": "Failed to save default bridge account config: {error}",
            "webhook.accounts_loaded": "Webhook adapter initialized, loaded {count} bridge account(s)",
            "webhook.unknown_account": "Unknown account",
            "webhook.auth_failed": "Account {name} webhook auth failed",
            "webhook.auth_failed_msg": "Authentication failed",
            "webhook.invalid_json": "Account {name} received invalid JSON: {error}",
            "webhook.invalid_json_msg": "Invalid JSON body",
            "webhook.body_not_object": "body must be a JSON object",
            "webhook.emit_failed": "Account {name} failed to emit event: {error}",
            "webhook.emit_failed_msg": "Event dispatch failed",
            "webhook.cannot_resolve_account": "Cannot resolve account",
            "webhook.no_outgoing_url": "Account {name} has no outgoing_url configured, cannot send message",
            "webhook.no_outgoing_url_msg": "outgoing_url not configured, cannot send outbound message",
            "webhook.outbound_debug": "Webhook outbound: account={name} -> {url}",
            "webhook.outbound_failed": "Webhook outbound request failed ({name}): {error}",
            "webhook.outbound_failed_msg": "Outbound request failed: {error}",
            "webhook.unsupported_endpoint": "Unsupported API endpoint: {endpoint}",
            "webhook.no_enabled_accounts": "Webhook adapter has no enabled accounts",
            "webhook.route_register_failed": "Account {name} failed to register route {path}: {error}",
            "webhook.emit_connect_failed": "Account {name} emit connect failed: {error}",
            "webhook.outbound_not_configured": "(not configured, inbound only)",
            "webhook.account_started": "Webhook account {name} started: GET/POST {path} | outbound {outgoing}",
            "webhook.adapter_started": "Webhook adapter started, {count} bridge account(s) total",
            "webhook.unregister_route_failed": "Failed to unregister route {path}: {error}",
            "webhook.adapter_shutdown": "Webhook adapter shut down",
        }
        try:
            i18n.register("zh-CN", zh_CN, domain="webhook")
            i18n.register("en", en, domain="webhook")
        except Exception:
            pass

    def _get_config_key(self) -> str:
        return "WebhookAdapter"

    def _load_accounts(self) -> dict:
        key = "WebhookAdapter.accounts"
        data = config_mgr.getConfig(key)

        if not data:
            old_config = config_mgr.getConfig("WebhookAdapter")
            if old_config and (
                "callback_path" in old_config or "outgoing_url" in old_config
            ):
                self.logger.warning(
                    i18n.t("webhook.old_config_detected", default="检测到旧格式配置，建议迁移到多账户格式")
                )
                self.logger.warning(
                    i18n.t("webhook.migration_hint", default="迁移方法：将现有配置移动到 WebhookAdapter.accounts.default 下")
                )
                data = {
                    "default": {
                        "bot_id": old_config.get("bot_id", "webhook_bot"),
                        "callback_path": old_config.get(
                            "callback_path", "/webhook/{account}"
                        ),
                        "outgoing_url": old_config.get("outgoing_url", ""),
                        "secret": old_config.get("secret", ""),
                        "detail_type": old_config.get("detail_type", "private"),
                        "enabled": True,
                    }
                }
                self.logger.warning(
                    i18n.t("webhook.temp_load_old_config", default="已临时加载旧配置为默认账户，请尽快迁移到多账户格式")
                )
            else:
                self.logger.info(
                    i18n.t("webhook.no_config_create_default", default="未找到配置文件，创建默认桥接账户配置")
                )
                data = {
                    "default": {
                        "bot_id": "webhook_bot",
                        "callback_path": "/webhook/{account}",
                        "outgoing_url": "",
                        "secret": "",
                        "detail_type": "private",
                        "enabled": True,
                    }
                }
                try:
                    config_mgr.setConfig(key, data)
                except Exception as e:
                    self.logger.error(i18n.t("webhook.save_default_failed", error=e, default="保存默认桥接账户配置失败: {error}"))

        accounts = {}
        for name, account_data in data.items():
            if not isinstance(account_data, dict):
                continue

            instance = dict_to_dataclass(WebhookAccountConfig, account_data)
            instance.name = name
            accounts[name] = instance

        self.logger.info(i18n.t("webhook.accounts_loaded", count=len(accounts), default="Webhook适配器初始化完成，共加载 {count} 个桥接账户"))
        return accounts

    def _get_converter(self, account_name: str) -> WebhookConverter:
        """获取指定账户的转换器（懒加载）"""
        if account_name not in self._converters:
            account = self.accounts.get(account_name)
            bot_id = account.bot_id if account else "webhook_bot"
            self._converters[account_name] = WebhookConverter(bot_id)
        return self._converters[account_name]

    def _resolve_callback_path(self, account_name: str, account) -> str:
        """解析账户的实际回调路径，替换 {account} 占位符"""
        path = account.callback_path or "/webhook/{account}"
        return path.replace("{account}", account_name)

    def _make_health_handler(self, account_name: str):
        async def health_check(request):
            return {"status": "ok", "account": account_name}

        return health_check

    def _make_webhook_handler(self, account_name: str):
        async def webhook_receiver(request):
            account = self.accounts.get(account_name)
            if not account:
                return self._json_error(i18n.t("webhook.unknown_account", default="未知账户"), 404)

            # 鉴权
            if account.secret:
                provided = (
                    request.headers.get("X-Webhook-Secret")
                    or request.query_params.get("secret")
                    or ""
                )
                if provided != account.secret:
                    self.logger.warning(i18n.t("webhook.auth_failed", name=account_name, default="账户 {name} webhook 鉴权失败"))
                    return self._json_error(i18n.t("webhook.auth_failed_msg", default="鉴权失败"), 401)

            # 解析 body
            try:
                body = await request.json()
            except Exception as e:
                self.logger.warning(i18n.t("webhook.invalid_json", name=account_name, error=e, default="账户 {name} 收到无效JSON: {error}"))
                return self._json_error(i18n.t("webhook.invalid_json_msg", default="无效的JSON body"), 400)

            if not isinstance(body, dict):
                return self._json_error(i18n.t("webhook.body_not_object", default="body 必须是 JSON 对象"), 400)

            converter = self._get_converter(account_name)
            event = converter.convert(
                body,
                account_name=account_name,
                detail_type_default=account.detail_type,
            )

            if event:
                try:
                    from ErisPulse.Core import adapter as adapter_mgr

                    await adapter_mgr.emit(event)
                except Exception as e:
                    self.logger.error(i18n.t("webhook.emit_failed", name=account_name, error=e, default="账户 {name} 分发事件失败: {error}"))
                    return self._json_error(i18n.t("webhook.emit_failed_msg", default="事件分发失败"), 500)

            return {"status": "ok"}

        return webhook_receiver

    @staticmethod
    def _json_error(message: str, status: int):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status,
            content={"status": "error", "message": message},
        )

    async def call_api(self, endpoint: str, _account_id: str = None, **params):
        account_name, account = self._resolve_account(_account_id)

        if endpoint in ("send_message", "send_msg"):
            if not account:
                return self.make_error(retcode=10002, message=i18n.t("webhook.cannot_resolve_account", default="无法解析账户"))

            if not account.outgoing_url:
                self.logger.error(
                    i18n.t("webhook.no_outgoing_url", name=account_name, default="账户 {name} 未配置 outgoing_url，无法发送消息")
                )
                return self.make_error(
                    retcode=10002,
                    message=i18n.t("webhook.no_outgoing_url_msg", default="未配置 outgoing_url，无法发送出站消息"),
                )

            target_type = params.get("target_type") or account.detail_type or "private"
            target_id = params.get("target_id", "")
            message = params.get("message", [])

            payload = {
                "target_type": target_type,
                "target_id": target_id,
                "account": account_name,
                "message": message,
                "timestamp": int(time.time()),
            }

            headers = {}
            if account.secret:
                headers["X-Webhook-Secret"] = account.secret

            try:
                self.logger.debug(
                    i18n.t("webhook.outbound_debug", name=account_name, url=account.outgoing_url, default="Webhook出站: 账户={name} -> {url}")
                )
                resp = await client.post(
                    account.outgoing_url, json=payload, headers=headers
                )
                try:
                    raw = await resp.json()
                except Exception:
                    raw = {}

                message_id = ""
                if isinstance(raw, dict):
                    message_id = str(raw.get("message_id", ""))

                return self.make_response(
                    data=raw if isinstance(raw, dict) else None,
                    message_id=message_id,
                    raw=raw,
                )
            except Exception as e:
                self.logger.error(i18n.t("webhook.outbound_failed", name=account_name, error=e, default="Webhook出站请求失败({name}): {error}"))
                return self.make_error(
                    retcode=33001,
                    message=i18n.t("webhook.outbound_failed_msg", error=str(e), default="出站请求失败: {error}"),
                    raw=None,
                )

        return self.make_error(
            retcode=10002,
            message=i18n.t("webhook.unsupported_endpoint", endpoint=endpoint, default="不支持的API端点: {endpoint}"),
        )

    async def start(self):
        self._running = True
        self._registered_routes = []

        if not self.enabled_accounts:
            self.logger.warning(i18n.t("webhook.no_enabled_accounts", default="Webhook适配器没有已启用的账户"))
            return

        for account_name, account in self.enabled_accounts.items():
            path = self._resolve_callback_path(account_name, account)

            health_handler = self._make_health_handler(account_name)
            receive_handler = self._make_webhook_handler(account_name)

            try:
                router.register_http_route(
                    "webhook", path, health_handler, methods=["GET"]
                )
                router.register_http_route(
                    "webhook", path, receive_handler, methods=["POST"]
                )
            except Exception as e:
                self.logger.error(i18n.t("webhook.route_register_failed", name=account_name, path=path, error=e, default="账户 {name} 注册路由 {path} 失败: {error}"))
                continue

            self._registered_routes.append(path)

            try:
                await self.emit_meta(
                    "connect",
                    account.bot_id,
                    user_name="WebhookBot",
                    nickname=f"Webhook({account_name})",
                )
            except Exception as e:
                self.logger.warning(i18n.t("webhook.emit_connect_failed", name=account_name, error=e, default="账户 {name} emit connect 失败: {error}"))

            outgoing = account.outgoing_url or i18n.t("webhook.outbound_not_configured", default="(未配置，仅入站)")
            self.logger.info(
                i18n.t("webhook.account_started", name=account_name, path=path, outgoing=outgoing, default="Webhook账户 {name} 已启动: GET/POST {path} | 出站 {outgoing}")
            )

        self.logger.info(
            i18n.t("webhook.adapter_started", count=len(self._registered_routes), default="Webhook适配器启动完成，共 {count} 个桥接账户")
        )

    async def shutdown(self):
        self._running = False

        for path in self._registered_routes:
            try:
                router.unregister_http_route("webhook", path)
            except Exception as e:
                self.logger.debug(i18n.t("webhook.unregister_route_failed", path=path, error=e, default="注销路由 {path} 失败: {error}"))
        self._registered_routes.clear()

        for account_name, account in self.enabled_accounts.items():
            try:
                await self.emit_meta("disconnect", account.bot_id)
            except Exception:
                pass

        try:
            unregister_platform_event_methods("webhook")
        except Exception:
            pass

        self.logger.info(i18n.t("webhook.adapter_shutdown", default="Webhook适配器已关闭"))
