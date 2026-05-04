"""app.services 包：业务服务层。

把"读 + 业务规则 + 写"这一类粘合逻辑从 UI 与底层 IO 之间隔出来，
让 controllers / dialogs 只跟服务对话，避免重复实现。

当前服务：
  - lexicon_writer：词库写盘的唯一入口（含主词库 JSON 与审计 sidecar）
"""
