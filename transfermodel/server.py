import asyncio
import logging

from PySide6.QtCore import QThread, Signal
import uvicorn

from transfermodel.app import create_app


logger = logging.getLogger("transfermodel.server")


class ProxyServer(QThread):
    server_started = Signal(int)
    server_stopped = Signal()
    server_error = Signal(str)

    def __init__(self, host: str, port: int, log_level: str = "info"):
        super().__init__()
        self._host = host
        self._port = port
        self._log_level = log_level
        self._server: uvicorn.Server | None = None

    def run(self):
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
            app = create_app()
            config = uvicorn.Config(
                app=app,
                host=self._host,
                port=self._port,
                log_level=self._log_level,
                log_config={
                    "version": 1,
                    "disable_existing_loggers": False,
                    "loggers": {
                        "uvicorn": {
                            "handlers": [],
                            "propagate": True,
                        },
                        "uvicorn.access": {
                            "handlers": [],
                            "propagate": True,
                        },
                        "uvicorn.error": {
                            "handlers": [],
                            "propagate": True,
                        },
                    },
                },
            )
            self._server = uvicorn.Server(config)
            logger.info("Proxy server starting on %s:%s", self._host, self._port)
            self.server_started.emit(self._port)
            self._server.run()
        except Exception as e:
            logger.error("Server error: %s", e)
            self.server_error.emit(str(e))
        finally:
            logger.info("Proxy server stopped")
            self.server_stopped.emit()

    def stop(self):
        if self._server:
            self._server.should_exit = True
