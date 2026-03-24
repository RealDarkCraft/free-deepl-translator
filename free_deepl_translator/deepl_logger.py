import logging
import sys


class Logger:
    """Simple logger with a configurable debug level."""

    def __init__(self, debug: bool = False):
        self._logger = logging.getLogger("deepl")
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
            self._logger.addHandler(handler)
        self._logger.setLevel(logging.DEBUG if debug else logging.WARNING)

    def Error(self, error: object) -> None:
        self._logger.error(str(error))

    def Warning(self, warning: object) -> None:
        self._logger.warning(str(warning))

    def Info(self, info: object) -> None:
        self._logger.info(str(info))
