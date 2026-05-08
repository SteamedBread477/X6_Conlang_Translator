"""Controllers 包：MVVM-lite 视图模型层。

每个 controller 拥有一类 UI 子系统的状态 + 行为，向 MainWindow 暴露 build_page()
返回 QWidget，由 MainWindow 装入 tab。controller 通过 self._mw 引用 MainWindow
访问跨子系统的共享资源（语言上下文、词库写盘、状态栏等）。

当前 controller：
  - AskController：语言大师对话页签
"""
