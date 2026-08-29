"""Замеры против допусков: measured.csv × tolerances.csv.

Образец подключения модуля к ядру — два метода, никакой регистрации
в общем файле. Чистая арифметика, без LLM: результат воспроизводим
и объясним числом, а не мнением модели.

Главная тонкость примера — НЕСИММЕТРИЧНЫЙ допуск. Толщина 11.96 при
номинале 12.00 с допуском +0.10/−0.05 даёт границы [11.95, 12.10],
то есть 11.96 — НЕ брак. Модуль, который считает допуск симметричным,
поднимает ложную тревогу и проваливает приёмку так же, как модуль,
который не ловит ничего.
"""

import csv
import io
from decimal import Decimal, InvalidOperation

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from core.model import Finding, Report          # noqa: E402

NAME = "tolerances"

RULES = [
    {"id": "вне допуска", "что": "замер лежит между нижней и верхней границей допуска",
     "источник": "боль заказчика: проверка чертежей перед производством",
     "важность": "нарушение",
     "не_нарушение": "несимметричный допуск: 11.96 при 12.00 +0.10/−0.05 — в норме, низ 11.95"},
    {"id": "допуск не найден", "что": "на каждый замер есть строка в таблице допусков",
     "источник": "там же", "важность": "вопрос", "не_нарушение": "—"},
    {"id": "нечитаемое число", "что": "значение и номинал разбираются как числа",
     "источник": "там же", "важность": "вопрос", "не_нарушение": "запятая как разделитель дроби"},
]

RUNTIME_ONLY = []

MEASURED = "measured.csv"
TOLERANCES = "tolerances.csv"


def matches(inputs: dict[str, str]) -> bool:
    """Мой вход — только если есть обе таблицы: замеры и допуски."""
    names = {Path(n).name for n in inputs}
    return MEASURED in names and TOLERANCES in names


def _by_name(inputs: dict[str, str], filename: str) -> str:
    for name, body in inputs.items():
        if Path(name).name == filename:
            return body
    return ""


def _rows(body: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(body.strip())))


def _dec(value: str) -> Decimal | None:
    try:
        return Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def _fmt(value: Decimal, raw: str | None = None) -> str:
    """Печатаем число так, как оно записано в исходной таблице.

    Конструктор читает «25.00», а не «25»: хвостовые нули в номинале —
    это запись точности, а не мусор. Поэтому исходная строка в приоритете.
    """
    if raw is not None and raw.strip():
        return raw.strip().replace(",", ".")
    return format(value, "f")


def check(inputs: dict[str, str]) -> Report:
    report = Report()

    measured = _rows(_by_name(inputs, MEASURED))
    tolerances = _rows(_by_name(inputs, TOLERANCES))
    if not measured or not tolerances:
        return report

    spec: dict[tuple[str, str], dict[str, str]] = {
        (r.get("деталь", "").strip(), r.get("параметр", "").strip()): r for r in tolerances
    }

    for row in measured:
        part = row.get("деталь", "").strip()
        param = row.get("параметр", "").strip()
        where = f"{part} · {param}"
        value = _dec(row.get("значение", ""))

        rule = spec.get((part, param))
        if rule is None:
            report.findings.append(Finding(
                rule_id="допуск не найден",
                rule_text="для каждого замера в таблице допусков есть строка",
                where=where,
                quote=f"{row.get('значение', '')}",
                what=f"{where}: замер есть, допуска на него нет",
                severity="вопрос",
            ))
            continue

        nominal = _dec(rule.get("номинал", ""))
        plus = _dec(rule.get("допуск_плюс", "")) or Decimal(0)
        minus = _dec(rule.get("допуск_минус", "")) or Decimal(0)
        if value is None or nominal is None:
            report.findings.append(Finding(
                rule_id="нечитаемое число",
                rule_text="значение и номинал — числа",
                where=where,
                quote=f"значение={row.get('значение','')} номинал={rule.get('номинал','')}",
                what=f"{where}: не удалось прочитать число",
                severity="вопрос",
            ))
            continue

        # границы считаем раздельно — допуск бывает несимметричным
        low, high = nominal - minus, nominal + plus
        nom_s = _fmt(nominal, rule.get("номинал"))
        plus_s = _fmt(plus, rule.get("допуск_плюс"))
        minus_s = _fmt(minus, rule.get("допуск_минус"))
        band = f"{nom_s} +{plus_s}/−{minus_s}" if plus != minus else f"{nom_s} ± {plus_s}"
        val_s = _fmt(value, row.get("значение"))

        if value < low:
            report.findings.append(Finding(
                rule_id="вне допуска",
                rule_text=f"{param}: {band} → границы [{_fmt(low)}, {_fmt(high)}]",
                where=where,
                quote=val_s,
                what=f"{where}: {val_s} при {band} — вне допуска ({_fmt(low - value)} ниже нижней границы)",
            ))
        elif value > high:
            report.findings.append(Finding(
                rule_id="вне допуска",
                rule_text=f"{param}: {band} → границы [{_fmt(low)}, {_fmt(high)}]",
                where=where,
                quote=val_s,
                what=f"{where}: {val_s} при {band} — вне допуска (+{_fmt(value - high)} сверх)",
            ))
        else:
            report.notes.append(
                f"{where}: {val_s} при {band} → в допуске (границы {_fmt(low)}…{_fmt(high)})"
            )

    return report
