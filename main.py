"""TransferModel: 本地 LLM API 桌面代理

运行: uv run python main.py
"""

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from transfermodel import config
from transfermodel.logger import setup_logging
from transfermodel.storage import _data_dir
from transfermodel.ui.main_window import MainWindow


def main():
    # Must init logging before QApplication so Qt signal handler is ready
    setup_logging(_data_dir())
    logging.getLogger("transfermodel.proxy").info("TransferModel starting")

    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName(config.APP_ORG)
    app.setQuitOnLastWindowClosed(False)

    # macOS: force dark appearance
    if sys.platform == "darwin":
        try:
            from PySide6.QtGui import QPalette, QColor
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 46))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(205, 214, 244))
            app.setPalette(palette)
        except Exception:
            pass

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
