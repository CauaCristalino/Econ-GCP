"""Logs estruturados em JSON, no formato que o Cloud Logging entende (severity/message)."""

import json
import logging
import sys
from datetime import UTC, datetime

# Atributos que todo LogRecord já tem; o que sobrar veio do `extra=` de quem logou.
_ATRIBUTOS_PADRAO = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entrada: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for chave, valor in record.__dict__.items():
            if chave not in _ATRIBUTOS_PADRAO:
                entrada[chave] = valor
        if record.exc_info:
            entrada["exception"] = self.formatException(record.exc_info)
        return json.dumps(entrada, ensure_ascii=False, default=str)


def configurar_logging(nivel: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    raiz = logging.getLogger()
    raiz.handlers = [handler]
    raiz.setLevel(nivel)
