import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal


class LogSignal(QObject):
    emitted = Signal(str)


_log_signal = LogSignal()
_did_setup = False


def setup_logging(data_dir: str | Path):
    global _did_setup
    if _did_setup:
        return _log_signal
    _did_setup = True

    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # File handler
    file_handler = logging.FileHandler(
        data_path / "proxy.log", encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    root.addHandler(file_handler)

    # Qt signal handler — routes logs to the UI
    qt_handler = _QtLogHandler()
    qt_handler.setLevel(logging.INFO)
    qt_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(qt_handler)

    return _log_signal


def get_signal() -> LogSignal:
    return _log_signal


class _QtLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            _log_signal.emitted.emit(msg)
        except Exception:
            pass
