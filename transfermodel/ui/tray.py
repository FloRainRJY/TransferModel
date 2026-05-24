from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication


def _load_icon(name: str) -> QIcon:
    import os
    from pathlib import Path

    pkg_dir = Path(__file__).resolve().parent.parent
    icon_path = pkg_dir / "resources" / name
    if icon_path.exists():
        return QIcon(str(icon_path))
    return QApplication.style().standardIcon(
        QApplication.style().StandardPixmap.SP_ComputerIcon
    )


class SystemTray(QSystemTrayIcon):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIcon(_load_icon("icon_tray.png"))
        self.setToolTip("TransferModel - 本地 LLM 代理")
        self._build_menu()

    def _build_menu(self):
        self.menu = QMenu()

        self.show_action = QAction("显示主窗口")
        self.show_action.triggered.connect(self._on_show)
        self.menu.addAction(self.show_action)

        self.toggle_server_action = QAction("启动代理")
        self.menu.addAction(self.toggle_server_action)

        self.menu.addSeparator()

        quit_action = QAction("退出")
        quit_action.triggered.connect(self._on_quit)
        self.menu.addAction(quit_action)

        self.setContextMenu(self.menu)
        self.activated.connect(self._on_activated)

    def set_server_running(self, running: bool):
        self.toggle_server_action.setText("停止代理" if running else "启动代理")

    def connect_toggle_server(self, callback):
        self.toggle_server_action.triggered.disconnect()
        self.toggle_server_action.triggered.connect(callback)

    def connect_show(self, callback):
        self.show_action.triggered.disconnect()
        self.show_action.triggered.connect(callback)

    def _on_show(self):
        pass  # connected externally

    def _on_quit(self):
        QApplication.quit()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            pass  # connected externally

    def connect_double_click(self, callback):
        self.activated.disconnect()
        self.activated.connect(
            lambda reason: callback()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick
            else None
        )
