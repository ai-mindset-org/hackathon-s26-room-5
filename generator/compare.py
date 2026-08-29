"""Сверка: что заложили против того, что инструмент нашёл.

Три исхода на каждый заложенный дефект и два на каждую находку:

  найдено      дефект заложен и пойман
  пропущено    дефект заложен, инструмент промолчал
  ложная       находка села на приманку — то, на что срабатывать нельзя
  сверх плана  находка не из плана и не на приманке: генератор мог создать
               дефект случайно, поэтому это не провал, а повод посмотреть глазами
"""
from __future__ import annotations


def _same_line(a: int, b: int, slack: int = 1) -> bool:
    return a and b and abs(a - b) <= slack


def _overlap(text_a: str, text_b: str) -> bool:
    """Есть ли у двух строк общий значимый кусок."""
    a, b = (text_a or "").strip(), (text_b or "").strip()
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    # общее «слово» длиннее пяти символов: имя переменной, деталь, аббревиатура
    tokens_a = {t for t in _tokens(a) if len(t) > 5}
    return any(t in b for t in tokens_a)


def _tokens(s: str) -> list[str]:
    out, cur = [], ""
    for ch in s:
        if ch.isalnum() or ch in "_-.":
            cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out



def _all_parts_match(planted_text: str, where: str) -> bool:
    """Все смысловые части заложенной строки есть в адресе находки.

    Для таблиц адрес смысловой: «вал-102 · диаметр_мм». Совпадения одной
    детали мало - у неё несколько параметров, и находка сопоставилась бы
    не с тем. Требуем и деталь, и параметр разом, числа не считаем:
    в адресе их нет.
    """
    parts = [t for t in _tokens(planted_text)
             if len(t) > 3 and not t.replace(".", "").replace("-", "").isdigit()]
    return bool(parts) and all(t in where for t in parts)


def compare(generated: dict, findings: list[dict]) -> dict:
    planted = generated["planted"]
    bait = generated["bait"]

    used: set[int] = set()
    plan_rows = []

    def _match(p: dict, strict: bool) -> int | None:
        """Ищем находку под заложенный дефект.

        Два прохода. Сначала строгий: правило совпало. Только потом мягкий,
        по месту и тексту. Иначе находка достаётся первому подходящему
        дефекту, а настоящий владелец остаётся «пропущенным» - на этом
        сверка врала про пункт 5 в каждой спецификации.
        """
        for i, f in enumerate(findings):
            if i in used:
                continue
            same_rule = f["rule_id"].lower() == p["rule_id"].lower()
            near = _same_line(f.get("line", 0), p["line"])
            similar = (_overlap(p["text"], f.get("quote", ""))
                       or _overlap(p["text"], f.get("where", "")))
            if strict and same_rule and (near or similar):
                return i
            # Мягкий проход: правило названо иначе, чем у нас в плане.
            # Модуль допусков пишет rule_id «вне допуска», а план говорит
            # «допуск» - сходство по месту и тексту тут надёжнее имени.
            # Номер строки не требуем: у таблиц адрес смысловой
            # («вал-102 · диаметр_мм»), строки в нём нет вовсе.
            if not strict and _all_parts_match(p["text"], f.get("where", "")):
                return i
            if not strict and similar and near:
                return i
        return None

    for p in planted:
        hit = _match(p, strict=True)
        if hit is None:
            hit = _match(p, strict=False)
        if hit is None:
            # обезличиватель не выдаёт находок: считаем попаданием, если
            # человека в выданном тексте больше нет
            plan_rows.append({**p, "status": "пропущено", "found": None})
        else:
            used.add(hit)
            plan_rows.append({**p, "status": "найдено", "found": findings[hit]})

    extra_rows = []
    for i, f in enumerate(findings):
        if i in used:
            continue
        on_bait = next((b for b in bait
                        if _same_line(f.get("line", 0), b["line"], 0)
                        or _overlap(b["text"], f.get("quote", ""))), None)
        extra_rows.append({
            "finding": f,
            "status": "ложная" if on_bait else "сверх плана",
            "bait_why": on_bait["why"] if on_bait else "",
        })

    found = sum(1 for r in plan_rows if r["status"] == "найдено")
    false_alarms = sum(1 for r in extra_rows if r["status"] == "ложная")
    return {
        "plan": plan_rows,
        "extra": extra_rows,
        "bait": bait,
        "score": {
            "planted": len(plan_rows),
            "found": found,
            "missed": len(plan_rows) - found,
            "false_alarms": false_alarms,
            "beyond_plan": len(extra_rows) - false_alarms,
            "baits": len(bait),
        },
    }


def compare_anonymizer(generated: dict, artifacts: dict[str, str]) -> dict:
    """Обезличиватель не выдаёт находок: сверяем по выданному тексту."""
    anon = artifacts.get("anonymized.txt", "")
    plan_rows = []
    for p in generated["planted"]:
        # в заложенной строке было имя — проверяем, что его больше нет
        name = p["what"].split(" и его")[0].strip()
        gone = name and name not in anon
        plan_rows.append({**p, "status": "найдено" if gone else "пропущено",
                          "found": None})
    extra_rows = []
    for b in generated["bait"]:
        # приманка должна остаться в тексте нетронутой
        tokens = [t for t in _tokens(b["text"]) if "-" in t and any(c.isdigit() for c in t)]
        broken = [t for t in tokens if t not in anon]
        if broken:
            extra_rows.append({
                "finding": {"rule_id": "лишнее обезличивание", "where": f"строка {b['line']}",
                            "quote": b["text"], "what": f"пропало из текста: {', '.join(broken)}",
                            "severity": "нарушение", "rule_text": b["why"],
                            "line": b["line"], "file": "report.txt", "hint": ""},
                "status": "ложная", "bait_why": b["why"]})
    found = sum(1 for r in plan_rows if r["status"] == "найдено")
    return {
        "plan": plan_rows, "extra": extra_rows, "bait": generated["bait"],
        "score": {"planted": len(plan_rows), "found": found,
                  "missed": len(plan_rows) - found,
                  "false_alarms": len(extra_rows), "beyond_plan": 0,
                  "baits": len(generated["bait"])},
    }
