from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QHBoxLayout,
    QTextEdit,
)

from transfermodel.logger import get_signal


class LogTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._signal = get_signal()
        self._signal.emitted.connect(self._on_log)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        clear_btn = QPushButton("清空")
        clear_btn.setMaximumWidth(60)
        clear_btn.clicked.connect(self._on_clear)
        toolbar.addWidget(clear_btn)

        auto_scroll_btn = QPushButton("自动滚动: ON")
        auto_scroll_btn.setMaximumWidth(120)
        auto_scroll_btn.clicked.connect(self._on_toggle_scroll)
        toolbar.addWidget(auto_scroll_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._auto_scroll = True
        self._auto_scroll_btn = auto_scroll_btn

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet(
            "QTextEdit {"
            "  background-color: #181825;"
            "  color: #a6adc8;"
            "  border: 1px solid #313244;"
            "  border-radius: 6px;"
            "  font-family: 'Menlo', 'Monaco', monospace;"
            "  font-size: 12px;"
            "}"
        )
        layout.addWidget(self.output)

    def _on_log(self, msg: str):
        self.output.append(msg)
        if self._auto_scroll:
            sb = self.output.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _on_clear(self):
        self.output.clear()

    def _on_toggle_scroll(self):
        self._auto_scroll = not self._auto_scroll
        self._auto_scroll_btn.setText(
            f"自动滚动: {'ON' if self._auto_scroll else 'OFF'}"
        )
