# 更新日志

所有版本更新遵循 [语义化版本控制](https://semver.org/lang/zh-CN/) 规范。

---

## [4.1.0] - 2026/07/08

### 变更

- 配置字段 metadata 迁移至新格式：`description` 支持 i18n，`webui` 键更名 `ui`
- 新增 `_schema_meta.group_labels` 分组显示名（Dashboard 分区标题）
- 启动时通过 `register_config_i18n` 注册中英文翻译
- **全面国际化**：所有日志/错误消息（含 `_json_error` 返回给 HTTP 客户端的中文消息）通过 `i18n.t()` 输出，注册 zh-CN/en 双语翻译
