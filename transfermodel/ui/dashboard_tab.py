from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QGroupBox,
    QGridLayout,
    QApplication,
)

from transfermodel import config
from transfermodel.storage import load_providers
from transfermodel.usage_tracker import get_tracker


class DashboardTab(QWidget):
    POLL_MS = config.DASHBOARD_POLL_MS

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_usage)
        self._timer.start(self.POLL_MS)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- Server control ---
        ctrl_group = QGroupBox("代理服务器")
        ctrl_layout = QVBoxLayout(ctrl_group)
        ctrl_layout.setSpacing(10)

        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.start_stop_btn = QPushButton("▶ 启动代理")
        self.start_stop_btn.setObjectName("startBtn")
        self.start_stop_btn.setMinimumSize(200, 48)
        ctrl_layout.addLayout(btn_layout)
        btn_layout.addWidget(self.start_stop_btn)

        url_layout = QHBoxLayout()
        url_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.url_display = QLabel("127.0.0.1:8080")
        self.url_display.setObjectName("proxyUrlLabel")
        copy_btn = QPushButton("复制")
        copy_btn.setMaximumWidth(60)
        copy_btn.clicked.connect(self._copy_url)
        url_layout.addWidget(QLabel("代理地址："))
        url_layout.addWidget(self.url_display)
        url_layout.addWidget(copy_btn)
        ctrl_layout.addLayout(url_layout)
        layout.addWidget(ctrl_group)

        # --- Current request ---
        cur_group = QGroupBox("当前请求")
        cur_grid = QGridLayout(cur_group)
        cur_grid.setSpacing(8)

        headers = ["", "输入 Token", "缓存命中", "缓存写入", "输出 Token"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setStyleSheet("color: #a6adc8; font-size: 11px; font-weight: bold;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cur_grid.addWidget(lbl, 0, col)

        self.cur_model = QLabel("—")
        self.cur_model.setStyleSheet("color: #f9e2af; font-size: 12px;")
        self.cur_input = QLabel("0")
        self.cur_cache_r = QLabel("0")
        self.cur_cache_w = QLabel("0")
        self.cur_output = QLabel("0")

        for lbl in [self.cur_input, self.cur_cache_r, self.cur_cache_w, self.cur_output]:
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #cdd6f4; font-size: 18px; font-weight: bold;")

        cur_grid.addWidget(self.cur_model, 1, 0)
        cur_grid.addWidget(self.cur_input, 1, 1)
        cur_grid.addWidget(self.cur_cache_r, 1, 2)
        cur_grid.addWidget(self.cur_cache_w, 1, 3)
        cur_grid.addWidget(self.cur_output, 1, 4)
        layout.addWidget(cur_group)

        # --- Running totals ---
        total_group = QGroupBox("会话总计")
        total_layout = QVBoxLayout(total_group)
        total_grid = QGridLayout()
        total_grid.setSpacing(8)

        for col, h in enumerate(["输入 Token", "缓存命中", "缓存写入", "输出 Token", "请求数"]):
            lbl = QLabel(h)
            lbl.setStyleSheet("color: #a6adc8; font-size: 11px; font-weight: bold;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            total_grid.addWidget(lbl, 0, col)

        self.total_input = QLabel("0")
        self.total_cache_r = QLabel("0")
        self.total_cache_w = QLabel("0")
        self.total_output = QLabel("0")
        self.total_requests = QLabel("0")

        for lbl in [self.total_input, self.total_cache_r, self.total_cache_w,
                     self.total_output, self.total_requests]:
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #89b4fa; font-size: 24px; font-weight: bold;")

        total_grid.addWidget(self.total_input, 1, 0)
        total_grid.addWidget(self.total_cache_r, 1, 1)
        total_grid.addWidget(self.total_cache_w, 1, 2)
        total_grid.addWidget(self.total_output, 1, 3)
        total_grid.addWidget(self.total_requests, 1, 4)
        total_layout.addLayout(total_grid)

        reset_btn = QPushButton("清零总计")
        reset_btn.setFixedWidth(90)
        reset_btn.setStyleSheet("padding: 4px 10px;")
        reset_btn.clicked.connect(self._reset_totals)
        total_layout.addWidget(reset_btn, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(total_group)

        # --- Guide ---
        guide_group = QGroupBox("快速配置指引")
        guide_layout = QVBoxLayout(guide_group)
        guide_text = QLabel(
            "<b>Claude Code:</b> "
            "<code>export ANTHROPIC_BASE_URL=http://127.0.0.1:8080</code><br>"
            "<b>OpenAI CLI / Codex:</b> "
            "<code>export OPENAI_BASE_URL=http://127.0.0.1:8080/v1</code>"
        )
        guide_text.setWordWrap(True)
        guide_layout.addWidget(guide_text)
        layout.addWidget(guide_group)

    # --- polling ---

    def _poll_usage(self):
        tracker = get_tracker()
        snap = tracker.get_snapshot()

        if snap.active:
            self.cur_model.setText(f"{snap.model}")
            self.cur_input.setText(str(snap.input_tokens))
            self.cur_cache_r.setText(str(snap.cache_read))
            self.cur_cache_w.setText(str(snap.cache_write))
            self.cur_output.setText(str(snap.output_tokens))
        else:
            if self.cur_model.text() != "—":
                self.cur_model.setText("—")
                self.cur_input.setText("0")
                self.cur_cache_r.setText("0")
                self.cur_cache_w.setText("0")
                self.cur_output.setText("0")

        totals = tracker.get_totals()
        self.total_input.setText(str(totals["total_input"]))
        self.total_cache_r.setText(str(totals["total_cache_read"]))
        self.total_cache_w.setText(str(totals["total_cache_write"]))
        self.total_output.setText(str(totals["total_output"]))
        self.total_requests.setText(str(totals["request_count"]))

    def _reset_totals(self):
        get_tracker().reset_totals()

    # --- server control ---

    def set_running(self, running: bool, host: str, port: int):
        self._running = running
        if running:
            self.start_stop_btn.setText("■ 停止代理")
            self.start_stop_btn.setObjectName("stopBtn")
        else:
            self.start_stop_btn.setText("▶ 启动代理")
            self.start_stop_btn.setObjectName("startBtn")
        self.start_stop_btn.style().unpolish(self.start_stop_btn)
        self.start_stop_btn.style().polish(self.start_stop_btn)
        self.url_display.setText(f"{host}:{port}")

    def connect_toggle(self, callback):
        try:
            self.start_stop_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self.start_stop_btn.clicked.connect(callback)

    def _copy_url(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(f"http://{self.url_display.text()}")

    def refresh(self):
        providers = load_providers()
        self._poll_usage()
