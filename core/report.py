"""Отчёт для человека: Finding[] → markdown.

Формат отвечает на вопрос заказчика «что нарушено, где, какой пункт» —
и ничего не решает за него: слово «пропускать или нет» остаётся человеку.
"""

from .model import Report

STATUS_OK = "СООТВЕТСТВУЕТ правилам"
STATUS_BAD = "НЕ СООТВЕТСТВУЕТ — расхождений: {n}"
# Ноль находок при нуле отработавших модулей — это НЕ «всё хорошо».
# Зелёный статус, которого никто не проверял, опаснее красного.
STATUS_UNCHECKED = "НЕ ПРОВЕРЕНО — ни один модуль не взялся за этот вход"


def render(report: Report, title: str = "Отчёт о расхождениях") -> str:
    lines = [f"# {title}", ""]

    # Денис Зорин на интервью просил именно статус-строку перед разбором:
    # «соответствует / не соответствует нашим правилам» (docs/interview-QZ5K.md).
    if report.findings:
        lines += [f"**Статус:** {STATUS_BAD.format(n=len(report.findings))}", ""]
    elif not report.checked_by:
        lines += [f"**Статус:** ⚠ {STATUS_UNCHECKED}", ""]
    else:
        lines += [f"**Статус:** {STATUS_OK}", ""]

    if report.checked_by:
        lines += [f"_Проверяли модули: {', '.join(report.checked_by)}_", ""]

    if report.findings:
        lines.append("## Расхождения")
        lines.append("")
        for i, f in enumerate(report.findings, 1):
            mark = "" if f.severity == "нарушение" else f" _({f.severity})_"
            lines.append(f"{i}. **{f.what}**{mark}")
            lines.append(f"   - пункт: `{f.rule_id}` — {f.rule_text}")
            lines.append(f"   - где: `{f.where}`")
            if f.quote:
                lines.append(f"   - цитата: `{f.quote}`")
        lines.append("")

    if report.notes:
        lines.append("## Проверено и признано нормой")
        lines.append("")
        lines += [f"- {n}" for n in report.notes]
        lines.append("")

    if report.runtime_only:
        # Лидер комнаты просил зафиксировать эту границу честно и на виду:
        # «часть проверок принципиально не статические — только запуском».
        lines.append("## Проверить статически НЕЛЬЗЯ — видно только при запуске")
        lines.append("")
        lines += [f"- {n}" for n in report.runtime_only]
        lines.append("")

    if report.artifacts:
        lines.append("## Файлы на выходе")
        lines.append("")
        lines += [f"- `{name}` ({len(body)} символов)" for name, body in report.artifacts.items()]
        lines.append("")

    lines.append("---")
    lines.append("_Решение «пропускать или нет» — за человеком. Инструмент делает видимым._")
    return "\n".join(lines)


def render_chat(report: Report, title: str) -> str:
    """Компактный список для Mattermost / Telegram.

    Денис на интервью просил именно это: «список ошибок в Mattermost или
    Телеграм». Простыня markdown в мессенджере нечитаема, поэтому здесь
    одна строка на находку — пункт, место, суть.
    """
    if report.findings:
        head = f"❌ {title}: НЕ СООТВЕТСТВУЕТ, расхождений {len(report.findings)}"
    elif not report.checked_by:
        head = f"⚠️ {title}: НЕ ПРОВЕРЕНО — ни один модуль не взялся"
    else:
        head = f"✅ {title}: соответствует правилам"

    lines = [head]
    for f in report.findings:
        mark = "•" if f.severity == "нарушение" else "?"
        lines.append(f"{mark} [{f.rule_id}] {f.where} — {f.what}")
    if report.runtime_only:
        lines.append("— видно только при запуске: " + "; ".join(report.runtime_only))
    return "\n".join(lines)
