DARK_STYLE = """
QMainWindow {
    background-color: #1e1e2e;
    color: #cdd6f4;
}
QTabWidget::pane {
    border: 1px solid #313244;
    background-color: #1e1e2e;
}
QTabBar::tab {
    background-color: #181825;
    color: #6c7086;
    padding: 10px 20px;
    border: 1px solid #313244;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #1e1e2e;
    color: #cdd6f4;
    border-bottom: 2px solid #89b4fa;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #45475a;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton#primaryBtn {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    font-weight: bold;
}
QPushButton#primaryBtn:hover {
    background-color: #b4d0fb;
}
QPushButton#startBtn {
    background-color: #a6e3a1;
    color: #1e1e2e;
    border: none;
    font-weight: bold;
    font-size: 16px;
    padding: 12px 32px;
    border-radius: 8px;
}
QPushButton#startBtn:hover {
    background-color: #c0f0bc;
}
QPushButton#stopBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
    border: none;
    font-weight: bold;
    font-size: 16px;
    padding: 12px 32px;
    border-radius: 8px;
}
QPushButton#stopBtn:hover {
    background-color: #f7a8c8;
}
QPushButton#dangerBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
    border: none;
}
QPushButton#dangerBtn:hover {
    background-color: #f7a8c8;
}
QTableWidget {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #313244;
    gridline-color: #313244;
    border-radius: 6px;
}
QTableWidget::item {
    padding: 6px 10px;
}
QTableWidget::item:selected {
    background-color: #45475a;
}
QHeaderView::section {
    background-color: #313244;
    color: #a6adc8;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #45475a;
    font-weight: bold;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px;
    font-size: 13px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #89b4fa;
}
QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #181825;
    color: #cdd6f4;
    selection-background-color: #45475a;
}
QCheckBox {
    color: #cdd6f4;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #45475a;
    background-color: #181825;
}
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}
QLabel {
    color: #cdd6f4;
}
QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    border-top: 1px solid #313244;
    padding: 4px 12px;
}
QGroupBox {
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QScrollBar:vertical {
    background-color: #181825;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QMenu {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #45475a;
}
QLabel#proxyUrlLabel {
    color: #a6e3a1;
    font-family: monospace;
    font-size: 16px;
    padding: 8px;
    background-color: #181825;
    border: 1px solid #45475a;
    border-radius: 6px;
}
QLabel#statValue {
    color: #89b4fa;
    font-size: 28px;
    font-weight: bold;
}
QLabel#statLabel {
    color: #a6adc8;
    font-size: 12px;
}
"""
