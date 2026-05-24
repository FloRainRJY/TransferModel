from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QAbstractItemView,
)

from transfermodel.storage import load_providers, save_providers
from transfermodel.ui.provider_dialog import ProviderDialog


class ProvidersTab(QWidget):
    providers_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        add_btn = QPushButton("+ 添加提供商")
        add_btn.setObjectName("primaryBtn")
        add_btn.clicked.connect(self._on_add)
        toolbar.addWidget(add_btn)

        edit_btn = QPushButton("编辑")
        edit_btn.clicked.connect(self._on_edit)
        toolbar.addWidget(edit_btn)

        delete_btn = QPushButton("删除")
        delete_btn.setObjectName("dangerBtn")
        delete_btn.clicked.connect(self._on_delete)
        toolbar.addWidget(delete_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["名称", "类型", "上游地址", "模型", "优先级", "启用", "操作"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 50)
        self.table.setColumnWidth(6, 70)
        self.table.verticalHeader().hide()
        self.table.cellDoubleClicked.connect(lambda row, col: self._on_edit())
        layout.addWidget(self.table)

    def _load_data(self):
        self.table.setRowCount(0)
        providers = load_providers()
        for i, p in enumerate(providers):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(p.name))
            self.table.setItem(
                i, 1, QTableWidgetItem("Anthropic" if p.api_type == "anthropic" else "OpenAI")
            )
            self.table.setItem(i, 2, QTableWidgetItem(p.base_url))
            self.table.setItem(
                i, 3, QTableWidgetItem(", ".join(p.models[:3]) + ("..." if len(p.models) > 3 else ""))
            )
            self.table.setItem(i, 4, QTableWidgetItem(str(p.priority)))
            enabled_item = QTableWidgetItem("✓" if p.enabled else "✗")
            enabled_item.setForeground(
                Qt.GlobalColor.green if p.enabled else Qt.GlobalColor.red
            )
            self.table.setItem(i, 5, enabled_item)

            toggle_btn = QPushButton("禁用" if p.enabled else "启用")
            toggle_btn.setFixedWidth(56)
            toggle_btn.setStyleSheet("padding: 2px 6px; font-size: 12px;")
            toggle_btn.clicked.connect(
                lambda checked, pid=p.id: self._on_toggle(pid)
            )
            self.table.setCellWidget(i, 6, toggle_btn)

            self.table.setRowHeight(i, 36)

    def _get_selected_provider_id(self) -> str | None:
        rows = set()
        for idx in self.table.selectedIndexes():
            rows.add(idx.row())
        if len(rows) != 1:
            return None
        row = list(rows)[0]
        providers = load_providers()
        if row < len(providers):
            return providers[row].id
        return None

    def _on_add(self):
        dlg = ProviderDialog(self)
        dlg.saved.connect(self._on_saved)
        dlg.exec()

    def _on_edit(self):
        pid = self._get_selected_provider_id()
        if not pid:
            QMessageBox.information(self, "提示", "请先选择一个提供商")
            return
        providers = load_providers()
        provider = next((p for p in providers if p.id == pid), None)
        if not provider:
            return
        dlg = ProviderDialog(self, provider)
        dlg.saved.connect(self._on_saved)
        dlg.exec()

    def _on_delete(self):
        pid = self._get_selected_provider_id()
        if not pid:
            QMessageBox.information(self, "提示", "请先选择一个提供商")
            return
        reply = QMessageBox.question(
            self, "确认删除", "确定要删除这个提供商吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        providers = load_providers()
        providers = [p for p in providers if p.id != pid]
        save_providers(providers)
        self._load_data()
        self.providers_changed.emit()

    def _on_toggle(self, pid: str):
        providers = load_providers()
        for p in providers:
            if p.id == pid:
                p.enabled = not p.enabled
                break
        save_providers(providers)
        self._load_data()
        self.providers_changed.emit()

    def _on_saved(self, provider):
        providers = load_providers()
        found = False
        for i, p in enumerate(providers):
            if p.id == provider.id:
                providers[i] = provider
                found = True
                break
        if not found:
            providers.append(provider)
        save_providers(providers)
        self._load_data()
        self.providers_changed.emit()

    def refresh(self):
        self._load_data()
