"""app.models 包：纯数据模型层。

存放只承载状态、不依赖 PyQt 与 IO 的 dataclass，用作 view 与 service 之间的契约。
当前模型：
  - pending_words：语言大师候选词的结构化模型 + store
"""
