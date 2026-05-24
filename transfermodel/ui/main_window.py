from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QStatusBar,
    QWidget,
    QApplication,
    QSystemTrayIcon,
)

from transfermodel import config
from transfermodel.storage import load_settings, load_providers
from transfermodel.ui.styles import DARK_STYLE
from transfermodel.ui.dashboard_tab import DashboardTab
from transfermodel.ui.providers_tab import ProvidersTab
from transfermodel.ui.settings_tab import SettingsTab
from transfermodel.ui.log_tab import LogTab
from transfermodel.ui.tray import SystemTray


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.APP_NAME} - 本地 LLM 代理")
        self.setMinimumSize(config.WINDOW_MIN_WIDTH, config.WINDOW_MIN_HEIGHT)
        self.resize(config.WINDOW_DEFAULT_WIDTH, config.WINDOW_DEFAULT_HEIGHT)
        self.setStyleSheet(DARK_STYLE)

        self._server_running = False
        self._server_thread = None

        self._build_tabs()
        self._build_statusbar()
        self._build_tray()
        self._connect_signals()
        self._refresh_all()

    def _build_tabs(self):
        self.tabs = QTabWidget()

        self.dashboard = DashboardTab()
        self.providers = ProvidersTab()
        self.settings = SettingsTab()
        self.logs = LogTab()

        self.tabs.addTab(self.dashboard, "仪表盘")
        self.tabs.addTab(self.providers, "提供商")
        self.tabs.addTab(self.settings, "设置")
        self.tabs.addTab(self.logs, "日志")

        self.setCentralWidget(self.tabs)

    def _build_statusbar(self):
        self.statusbar = QStatusBar()
        self.status_text = "● 代理未启动"
        self.statusbar.showMessage(self.status_text)
        self.setStatusBar(self.statusbar)

    def _build_tray(self):
        self.tray = SystemTray(self)
        self.tray.show()

    def _connect_signals(self):
        self.dashboard.connect_toggle(self._on_toggle_server)
        self.providers.providers_changed.connect(self._refresh_all)
        self.settings.settings_saved.connect(self._on_settings_saved)

        self.tray.connect_show(self._show_window)
        self.tray.connect_toggle_server(self._on_toggle_server)
        self.tray.connect_double_click(self._show_window)

    def _on_toggle_server(self):
        if self._server_running:
            self._stop_server()
        else:
            self._start_server()

    def _start_server(self):
        from transfermodel.server import ProxyServer

        settings = load_settings()
        self._server_thread = ProxyServer(
            settings.listen_host, settings.listen_port, settings.log_level
        )
        self._server_thread.server_started.connect(self._on_server_started)
        self._server_thread.server_error.connect(self._on_server_error)
        self._server_thread.start()
        self._server_running = True
        self._update_server_state()
        self.statusbar.showMessage(
            f"● 代理运行中 - {settings.listen_host}:{settings.listen_port}"
        )
        self.tray.set_server_running(True)
        # Brief wait to allow uvicorn to start
        import time
        time.sleep(0.5)

    def _stop_server(self):
        if self._server_thread:
            self._server_thread.stop()
            self._server_thread.quit()
            self._server_thread.wait(3000)
            self._server_thread = None
        self._server_running = False
        self._update_server_state()
        self.statusbar.showMessage("● 代理已停止")
        self.tray.set_server_running(False)

    def _on_server_started(self, port: int):
        self.statusbar.showMessage(
            f"● 代理运行中 - {config.DEFAULT_HOST}:{port}"
        )

    def _on_server_error(self, msg: str):
        self.statusbar.showMessage(f"⚠ 代理错误: {msg}")

    def _on_settings_saved(self, settings):
        running = self._server_running
        if running:
            self._stop_server()
            import time
            time.sleep(0.3)
            self._start_server()
        self._update_server_state()

    def _update_server_state(self):
        settings = load_settings()
        self.dashboard.set_running(
            self._server_running, settings.listen_host, settings.listen_port
        )

    def _show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _refresh_all(self):
        self.dashboard.refresh()
        self.providers.refresh()
        self.settings.refresh()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "TransferModel",
            "代理在后台运行中。右键托盘图标可退出。",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )
