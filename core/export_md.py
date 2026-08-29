"""Полная выгрузка результата проверки в Markdown.

В файл уходит всё, что человек видит на экране, и ещё немного: правила,
по которым шла проверка, исходные файлы построчно с пометками и построчная
сверка с ожиданиями. Смысл простой - отчёт пересылают и читают без
инструмента, поэтому в нём не должно быть ссылок на то, чего в нём нет.
"""
from __future__ import annotations

from datetime import datetime


def _fence(text: str, lang: str = "") -> str:
    return f"```{lang}\n" + (text or "").rstrip() + "\n```"


def verdict_of(violations: int, questions: int) -> tuple[str, str]:
    """Короткий вердикт человеческим языком.

    Инструмент не блокирует сдачу и не ставит штамп «годен». Он говорит
    ровно одно: есть ли места, которые надо посмотреть до сдачи.
    """
    if violations:
        return (f"Перед сдачей есть что исправить: {violations} наруш"
                f"{'ение' if violations == 1 else 'ения' if violations < 5 else 'ений'}",
                "Ниже каждое нарушение с точным местом и цитатой. "
                "Решение, править или пропустить, за вами.")
    if questions:
        return (f"Нарушений нет, но {questions} мест"
                f"{'о требует' if questions == 1 else 'а требуют' if questions < 5 else ' требуют'}"
                " вашего решения",
                "Машина не берётся утверждать, что это ошибки: посмотрите глазами.")
    return ("Замечаний нет",
            "Все правила проверены, расхождений не найдено. "
            "Что именно проверено, смотрите в разделе «Проверено и признано нормой».")


def _finding_block(f: dict, n: int) -> list[str]:
    out = [f"#### {n}. {f['what']}", ""]
    out.append(f"- **Пункт правил:** {f['rule_id']}")
    out.append(f"- **Правило:** {f['rule_text']}")
    out.append(f"- **Где:** `{f['where']}`")
    if f.get("hint"):
        out.append(f"- **Что сделать:** {f['hint']}")
    out.append("")
    if f.get("quote"):
        out.append("Место в артефакте:")
        out.append("")
        out.append(_fence(f["quote"]))
        out.append("")
    return out


def to_markdown(title: str, result: dict, compare: dict | None = None,
                generated: dict | None = None, acceptance: dict | None = None) -> str:
    findings = result.get("findings", [])
    viol = [f for f in findings if f["severity"] == "нарушение"]
    ques = [f for f in findings if f["severity"] == "вопрос"]
    checked = result.get("checked", [])
    notes = result.get("notes", [])
    artifacts = result.get("artifacts", {})
    sources = result.get("sources") or {}
    checkers = result.get("checkers", [])

    verdict, explain = verdict_of(len(viol), len(ques))
    out: list[str] = [f"# Отчёт проверки — {title}", ""]

    # ── вердикт и сводка
    out += [f"## {verdict}", "", explain, ""]
    out += ["| Показатель | Значение |", "|---|---|"]
    out.append(f"| Нарушений | **{len(viol)}** |")
    out.append(f"| Вопросов к человеку | {len(ques)} |")
    out.append(f"| Проверок прошло чисто | {len(checked)} |")
    if notes:
        out.append(f"| Машина не проверяла | {len(notes)} |")
    if acceptance:
        got, total = acceptance["score"]
        out.append(f"| Сверка с ожиданиями | {got} из {total} |")
    if compare:
        s = compare["score"]
        out.append(f"| Заложено дефектов | {s['planted']} |")
        out.append(f"| Из них поймано | {s['found']} |")
        out.append(f"| Ложных тревог | {s['false_alarms']} |")
    out.append(f"| Проверяли модулями | {', '.join(c['title'] for c in checkers) or '—'} |")
    out.append(f"| Дата и время | {datetime.now().strftime('%d.%m.%Y, %H:%M')} |")
    out.append("")
    out.append("Решение «пропускать или нет» остаётся за человеком: "
               "инструмент делает видимым, а не блокирует.")
    out.append("")

    # ── что было на входе
    out += ["## Что проверяли", ""]
    if sources:
        out += ["| Файл | Строк | Размер |", "|---|---|---|"]
        for name, text in sources.items():
            out.append(f"| `{name}` | {len(text.splitlines())} | {len(text)} символов |")
        out.append("")
    else:
        out += ["Исходные файлы не переданы в отчёт.", ""]

    # ── по каким правилам
    rules: dict[str, str] = {}
    for f in findings:
        rules.setdefault(f["rule_id"], f["rule_text"])
    if rules:
        out += ["## Правила, по которым нашлись расхождения", ""]
        out += ["| Пункт | Правило |", "|---|---|"]
        for rid, rtext in rules.items():
            out.append(f"| {rid} | {rtext} |")
        out.append("")

    # ── сверка с планом генератора
    if compare:
        s = compare["score"]
        out += ["## Заложено против найденного", ""]
        out.append("Файл собран генератором: часть строк — дефекты, часть — приманки, "
                   "на которые срабатывать нельзя. Что заложено, известно заранее.")
        out.append("")
        out += ["| Итог | Что было заложено | Где |", "|---|---|---|"]
        for p in compare["plan"]:
            mark = "**найдено**" if p["status"] == "найдено" else "**ПРОПУЩЕНО**"
            out.append(f"| {mark} | {p['what']} | строка {p['line']}: `{p['text']}` |")
        out.append("")
        if compare.get("bait"):
            out += ["Приманки — на них срабатывать нельзя:", ""]
            out += ["| Строка | Что там | Почему это не нарушение |", "|---|---|---|"]
            for b in compare["bait"]:
                out.append(f"| {b['line']} | `{b['text']}` | {b['why']} |")
            out.append("")
        if compare["extra"]:
            out += ["Находки вне плана:", ""]
            for e in compare["extra"]:
                f = e["finding"]
                tail = f" — села на приманку: {e['bait_why']}" if e.get("bait_why") else ""
                out.append(f"- **{e['status']}** · {f['what']} · `{f['where']}`{tail}")
            out.append("")
        out.append(f"Итого: заложено {s['planted']}, поймано {s['found']}, "
                   f"пропущено {s['missed']}, ложных тревог {s['false_alarms']}.")
        out.append("")

    # ── нарушения и вопросы
    if viol:
        out += [f"## Нарушения — {len(viol)}", "",
                "Факт установлен машиной: правило нарушено.", ""]
        for i, f in enumerate(viol, start=1):
            out += _finding_block(f, i)
    if ques:
        out += [f"## Вопросы — {len(ques)}", "",
                "Похоже на нарушение, но машина не берётся утверждать. Решает человек.", ""]
        for i, f in enumerate(ques, start=1):
            out += _finding_block(f, i)
    if not viol and not ques:
        out += ["## Расхождений не найдено", "",
                "Инструмент прошёл по всем правилам и ничего не нашёл. "
                "Что именно проверено — в следующем разделе.", ""]

    # ── что признано нормой
    if checked:
        out += [f"## Проверено и признано нормой — {len(checked)}", "",
                "Это места, которые инструмент посмотрел и счёл в порядке. "
                "Раздел нужен, чтобы было видно охват: без него отчёт врёт молчанием.", ""]
        out += [f"- {c}" for c in checked]
        out.append("")

    # ── чего машина не касалась
    if notes:
        out += ["## Машина не проверяла — смотреть глазами", "",
                "Инструмент честно говорит, чего он не умеет, вместо того чтобы "
                "выдавать непроверенное за проверенное.", ""]
        out += [f"- {n}" for n in notes]
        out.append("")

    # ── сверка с ожиданиями заказчика
    if acceptance:
        got, total = acceptance["score"]
        out += [f"## Сверка с ожиданиями — {got} из {total}", "",
                "Что обязано было найтись и на что срабатывать нельзя. "
                "Ложная тревога проваливает проверку так же, как пропуск.", ""]
        out += ["| | Проверка | Почему так |", "|---|---|---|"]
        for c in acceptance["checks"]:
            mark = "сошлось" if c["ok"] else "**НЕ СОШЛОСЬ**"
            why = c.get("why") or ""
            if c.get("got"):
                why = (why + f" (факт: {c['got']})").strip()
            out.append(f"| {mark} | {c['text']} | {why} |")
        out.append("")

    # ── выданные файлы
    if artifacts:
        out += ["## Файлы на выходе", ""]
        for name, content in artifacts.items():
            out += [f"### {name}", "", _fence(content), ""]

    # ── исходники построчно
    if sources:
        marks: dict[str, dict[int, str]] = {}
        for f in findings:
            if f.get("file") and f.get("line"):
                marks.setdefault(f["file"], {})[f["line"]] = (
                    "!" if f["severity"] == "нарушение" else "?")
        out += ["## Инспект — исходные файлы построчно", "",
                "Слева от номера строки: `!` — нарушение, `?` — вопрос к человеку.", ""]
        for name, text in sources.items():
            out += [f"### {name}", "", "```"]
            for i, line in enumerate(text.split("\n"), start=1):
                out.append(f"{marks.get(name, {}).get(i, ' ')} {i:>3} | {line}")
            out += ["```", ""]

    out += ["---", "",
            f"Отчёт собран инструментом «Проверка артефакта до сдачи» "
            f"{datetime.now().strftime('%d.%m.%Y в %H:%M')}. "
            f"Инструмент делает расхождения видимыми; решение остаётся за человеком."]
    return "\n".join(out)
