"""Мостик к контракту комнаты.

В core.model.Finding нет поля с подсказкой «что сделать», а заказчики
на интервью просили именно её: «чтобы пойти править не переспрашивая».
Чтобы не править общий файл и не ловить конфликты в PR, подсказка
дописывается в конец what отдельной фразой.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.model import Finding as _Finding  # noqa: E402


def Finding(*, rule_id: str, rule_text: str, where: str, quote: str,
            what: str, severity: str = "нарушение", hint: str = "") -> _Finding:
    return _Finding(
        rule_id=rule_id, rule_text=rule_text, where=where, quote=quote,
        what=f"{what} → {hint}" if hint else what,
        severity=severity,
    )
