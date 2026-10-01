"""Alertas (Telegram) y latido externo (dead man's switch tipo healthchecks.io)."""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from collections import deque

log = logging.getLogger("bot.alerts")

LEVELS = {"info": logging.INFO, "warning": logging.WARNING, "critical": logging.CRITICAL}
ICONS = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}


class Alerter:
    def __init__(self, cfg, clock=time.time):
        self.cfg = cfg
        self.clock = clock
        self._last_sent: dict[str, float] = {}
        self._last_ping = 0.0
        self.sent: deque[tuple[str, str]] = deque(maxlen=200)  # últimos avisos (tests/diagnóstico)

    def send(self, level: str, text: str) -> None:
        log.log(LEVELS.get(level, logging.INFO), text)
        now = self.clock()
        key = f"{level}:{text}"
        if now - self._last_sent.get(key, -1e18) < self.cfg.dedup_seconds:
            return  # no repetir el mismo aviso una y otra vez
        if len(self._last_sent) > 1000:
            self._last_sent = {k: t for k, t in self._last_sent.items() if now - t < self.cfg.dedup_seconds}
        self._last_sent[key] = now
        self.sent.append((level, text))
        if self.cfg.telegram_token and self.cfg.telegram_chat_id:
            self._post(
                f"https://api.telegram.org/bot{self.cfg.telegram_token}/sendMessage",
                {"chat_id": self.cfg.telegram_chat_id, "text": f"{ICONS.get(level, '')} {text}"},
            )

    def ping_heartbeat(self) -> None:
        """Si el bot deja de llamar a esta URL, el servicio externo te avisa: cubre el caso
        en que el bot muere y ya no puede enviar alertas por sí mismo."""
        if not self.cfg.heartbeat_url:
            return
        now = self.clock()
        if now - self._last_ping < self.cfg.heartbeat_ping_seconds:
            return
        self._last_ping = now
        try:
            urllib.request.urlopen(self.cfg.heartbeat_url, timeout=10).close()
        except Exception as exc:  # noqa: BLE001 - un fallo del ping nunca debe tumbar el bot
            log.warning("Fallo enviando heartbeat: %s", exc)

    @staticmethod
    def _post(url: str, payload: dict) -> None:
        try:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10).close()
        except Exception as exc:  # noqa: BLE001
            log.warning("Fallo enviando alerta: %s", exc)
