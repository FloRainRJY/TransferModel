from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QPushButton,
    QGroupBox,
    QMessageBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
)

from transfermodel.models import ServerSettings
from transfermodel.storage import load_settings, save_settings


class SettingsTab(QWidget):
    settings_saved = Signal(object)  # ServerSettings

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        server_group = QGroupBox("服务器设置")
        form = QFormLayout(server_group)
        form.setSpacing(10)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("127.0.0.1")
        form.addRow("监听地址", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(8080)
        form.addRow("监听端口", self.port_spin)

        self.log_combo = QComboBox()
        self.log_combo.addItems(["info", "debug", "warning", "error", "critical"])
        form.addRow("日志级别", self.log_combo)

        layout.addWidget(server_group)

        save_btn = QPushButton("保存设置")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._on_save)
        save_btn.setMaximumWidth(120)

        note = QLabel("修改端口后需要重启代理才能生效")
        note.setStyleSheet("color: #f9e2af; font-size: 12px;")

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(note)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    def _load(self):
        settings = load_settings()
        self.host_edit.setText(settings.listen_host)
        self.port_spin.setValue(settings.listen_port)
        self.log_combo.setCurrentText(settings.log_level)

    def _on_save(self):
        settings = ServerSettings(
            listen_host=self.host_edit.text().strip() or "127.0.0.1",
            listen_port=self.port_spin.value(),
            log_level=self.log_combo.currentText(),
        )
        save_settings(settings)
        self.settings_saved.emit(settings)
        QMessageBox.information(self, "提示", "设置已保存")

    def refresh(self):
        self._load()
