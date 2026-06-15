import time
import uuid
from typing import Any, Dict, List, Optional


class WebhookConverter:
    """
    Webhook 事件转换器

    将外部系统通过 HTTP POST 提交的 JSON 转换为 OneBot12 标准事件。

    核心原则：
    1. 严格兼容：所有标准字段完全遵循 OneBot12 规范
    2. 明确扩展：桥接特有信息使用 webhook_ 前缀
    3. 数据完整：原始请求 body 完整保留在 webhook_raw 字段中
    4. 时间统一：所有时间戳为 10 位 Unix 时间戳（秒级）
    """

    def __init__(self, bot_id: str = "webhook_bot"):
        self.bot_id = bot_id

    def convert(
        self,
        raw_body: Dict[str, Any],
        account_name: str = "",
        detail_type_default: str = "private",
    ) -> Optional[Dict[str, Any]]:
        """
        将入站 JSON body 转换为 OneBot12 标准事件

        :param raw_body: 外部系统 POST 的 JSON（已解析为 dict）
        :param account_name: 所属账户名（写入 webhook_account）
        :param detail_type_default: 账户默认会话类型（body 未指定时使用）
        :return: OneBot12 标准事件 dict，无效输入返回 None
        """
        if not isinstance(raw_body, dict):
            return None

        detail_type = raw_body.get("detail_type") or detail_type_default or "private"
        group_id = raw_body.get("group_id")

        message: List[dict] = raw_body.get("message", [])
        if not isinstance(message, list):
            message = []

        event: Dict[str, Any] = {
            "id": str(uuid.uuid4().int)[:16],
            "time": int(time.time()),
            "type": "message",
            "detail_type": detail_type,
            "platform": "webhook",
            "self": {
                "platform": "webhook",
                "user_id": self.bot_id,
            },
            "user_id": str(raw_body.get("user_id", "")),
            "message": message,
            "webhook_raw": raw_body,
            "webhook_account": account_name,
            "webhook_raw_type": raw_body.get("type", "message"),
        }

        user_nickname = raw_body.get("user_nickname")
        if user_nickname:
            event["user_nickname"] = str(user_nickname)

        if group_id:
            event["group_id"] = str(group_id)

        # alt_message：若 body 显式提供则透传
        alt_message = raw_body.get("alt_message")
        if alt_message:
            event["alt_message"] = str(alt_message)

        return event
