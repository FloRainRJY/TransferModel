from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QTextEdit,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QLabel,
    QMessageBox,
)
import httpx

from transfermodel import config
from transfermodel.models import UpstreamProvider


class ProviderDialog(QDialog):
    saved = Signal(object)  # emits UpstreamProvider

    def __init__(self, parent=None, provider: UpstreamProvider | None = None):
        super().__init__(parent)
        self._provider = provider
        self._editing = provider is not None
        self.setWindowTitle("编辑提供商" if self._editing else "添加提供商")
        self.setMinimumWidth(520)
        self._build_ui()
        if self._editing:
            self._load_provider()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：我的 Anthropic 上游")
        form.addRow("名称 *", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["anthropic", "openai"])
        form.addRow("API 类型", self.type_combo)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://api.anthropic.com")
        form.addRow("上游 URL *", self.url_edit)

        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText(
            "留空则不修改" if self._editing else "sk-ant-..."
        )
        form.addRow("API Key" + ("" if self._editing else " *"), self.key_edit)

        self.models_edit = QTextEdit()
        self.models_edit.setPlaceholderText("每行一个模型名\n例如：\nclaude-sonnet-4-20250514\nclaude-opus-4-20250514")
        self.models_edit.setMaximumHeight(100)
        form.addRow("模型列表 *", self.models_edit)

        self.default_model_edit = QLineEdit()
        self.default_model_edit.setPlaceholderText("可选，默认模型")
        form.addRow("默认模型", self.default_model_edit)

        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(1, 100)
        self.priority_spin.setValue(config.DEFAULT_PROVIDER_PRIORITY)
        form.addRow("优先级", self.priority_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 600)
        self.timeout_spin.setValue(config.DEFAULT_PROVIDER_TIMEOUT)
        self.timeout_spin.setSuffix(" 秒")
        form.addRow("超时", self.timeout_spin)

        self.enabled_check = QCheckBox("启用")
        self.enabled_check.setChecked(True)
        form.addRow("状态", self.enabled_check)

        layout.addLayout(form)

        self.test_output = QTextEdit()
        self.test_output.setReadOnly(True)
        self.test_output.setMaximumHeight(200)
        self.test_output.setStyleSheet(
            "QTextEdit { background-color: #181825; color: #cdd6f4; border: 1px solid #45475a; border-radius: 6px; }"
        )
        layout.addWidget(self.test_output)

        btn_layout = QHBoxLayout()
        test_btn = QPushButton("测试连接")
        test_btn.clicked.connect(self._on_test)
        btn_layout.addWidget(test_btn)
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _load_provider(self):
        p = self._provider
        self.name_edit.setText(p.name)
        self.type_combo.setCurrentText(p.api_type)
        self.url_edit.setText(p.base_url)
        self.models_edit.setPlainText("\n".join(p.models))
        if p.default_model:
            self.default_model_edit.setText(p.default_model)
        self.priority_spin.setValue(p.priority)
        self.timeout_spin.setValue(p.timeout_seconds)
        self.enabled_check.setChecked(p.enabled)

    def _on_test(self):
        provider = self._build_provider()
        base = provider.base_url.rstrip("/")
        api_type = provider.api_type
        key = provider.api_key
        key_masked = key[:8] + "****" + key[-4:] if len(key) > 12 else "****"
        headers = {}
        if api_type == "anthropic":
            headers["x-api-key"] = key
            headers["anthropic-version"] = config.ANTHROPIC_VERSION
            auth_method = f"x-api-key: {key_masked}"
        else:
            headers["authorization"] = f"Bearer {key}"
            auth_method = f"Authorization: Bearer {key_masked}"

        test_model = provider.models[0] if provider.models else "unknown"
        if api_type == "anthropic":
            msgs_url = f"{base}/v1/messages"
            test_body = {"model": test_model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}
        else:
            msgs_url = f"{base}/chat/completions"
            test_body = {"model": test_model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}

        lines = [
            f"URL: {msgs_url}",
            f"认证: {auth_method}",
            f"模型: {test_model}",
            "",
            "正在发送请求...",
        ]

        def show(text: str, color: str):
            self.test_output.setPlainText(text)
            self.test_output.setStyleSheet(
                f"QTextEdit {{ background-color: #181825; color: {color}; border: 1px solid #45475a; border-radius: 6px; }}"
            )

        show("\n".join(lines), "#f9e2af")

        try:
            resp = httpx.post(
                msgs_url, headers=headers, json=test_body,
                timeout=config.TEST_CONNECTION_TIMEOUT,
            )
            status = resp.status_code
            body = resp.text[:500]

            if status < 400:
                lines[-1] = f"连接成功! (HTTP {status})"
                show("\n".join(lines), "#a6e3a1")
                return

            lines[-1] = f"上游返回 HTTP {status}:"
            lines.append(body)

            if status in (401, 403):
                lines.append("")
                lines.append("请检查：")
                lines.append("1. API Key 是否正确（去平台重新复制）")
                lines.append("2. Key 前后不要有空格")
                lines.append("3. 确认 Key 未被撤销或过期")
            elif status == 404:
                lines.append("")
                lines.append("404 说明上游地址或路径不对：")
                lines.append("DeepSeek Anthropic → https://api.deepseek.com/anthropic")
                lines.append("DeepSeek OpenAI  → https://api.deepseek.com/v1")

            show("\n".join(lines), "#fab387")
        except httpx.TimeoutException:
            lines[-1] = "连接超时 (15秒)"
            show("\n".join(lines), "#f38ba8;")
        except Exception as e:
            lines[-1] = f"连接失败: {type(e).__name__}: {e}"
            show("\n".join(lines), "#f38ba8;")

    def _on_save(self):
        name = self.name_edit.text().strip()
        url = self.url_edit.text().strip()
        key = self.key_edit.text().strip()
        models_text = self.models_edit.toPlainText().strip()

        if not name:
            QMessageBox.warning(self, "验证失败", "名称不能为空")
            return
        if not url:
            QMessageBox.warning(self, "验证失败", "上游 URL 不能为空")
            return
        if not models_text:
            QMessageBox.warning(self, "验证失败", "模型列表不能为空")
            return
        if not self._editing and not key:
            QMessageBox.warning(self, "验证失败", "API Key 不能为空")
            return

        provider = self._build_provider()
        self.saved.emit(provider)
        self.accept()

    def _build_provider(self) -> UpstreamProvider:
        models = [
            m.strip()
            for m in self.models_edit.toPlainText().strip().split("\n")
            if m.strip()
        ]
        kwargs = dict(
            name=self.name_edit.text().strip(),
            api_type=self.type_combo.currentText(),
            base_url=self.url_edit.text().strip(),
            models=models,
            default_model=self.default_model_edit.text().strip() or None,
            priority=self.priority_spin.value(),
            enabled=self.enabled_check.isChecked(),
            timeout_seconds=self.timeout_spin.value(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        if self._editing:
            kwargs["id"] = self._provider.id
            kwargs["created_at"] = self._provider.created_at
            kwargs["api_key"] = (
                self.key_edit.text().strip() or self._provider.api_key
            )
        else:
            kwargs["api_key"] = self.key_edit.text().strip()
        return UpstreamProvider(**kwargs)
