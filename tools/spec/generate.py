"""Реестр правил в спецификацию — из кода, а не руками.

    python3 tools/spec/generate.py            # перезаписать раздел
    python3 tools/spec/generate.py --check    # сверить, не разошлось ли

Зачем генератор, а не просто написать таблицу. Спека, которую правят
руками, расходится с кодом на второй правке и дальше врёт молча —
а врущая спека хуже отсутствующей: по ней принимают решения. Здесь
раздел «Реестр правил» собирается из самих модулей, поэтому разойтись
не может, а `--check` показывает расхождение до того, как его увидит
заказчик.

Модуль объявляет правила так:

    RULES = [{"id": ..., "что": ..., "источник": ..., "важность": ...,
              "не_нарушение": ...}]
    RUNTIME_ONLY = ["что статически проверить нельзя"]

Модуль без RULES не выкидывается и не замалчивается — он попадает
в спеку строкой «правила не объявлены». Пустая клетка видна, забытая — нет.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from core.registry import discover                      # noqa: E402

SPEC = REPO / "docs" / "СПЕЦИФИКАЦИЯ.md"
START = "<!-- РЕЕСТР-ПРАВИЛ:начало — раздел собирается tools/spec/generate.py, руками не править -->"
END = "<!-- РЕЕСТР-ПРАВИЛ:конец -->"


def build() -> str:
    lines = [START, ""]
    modules = sorted(discover(), key=lambda m: m.NAME)

    declared = [m for m in modules if getattr(m, "RULES", None)]
    silent = [m for m in modules if not getattr(m, "RULES", None)]

    total = sum(len(m.RULES) for m in declared)
    lines.append(f"Модулей: **{len(modules)}**, из них объявили правила: **{len(declared)}**. "
                 f"Всего правил: **{total}**.")
    lines.append("")

    for module in declared:
        lines.append(f"### `{module.NAME}`")
        lines.append("")
        lines.append("| Правило | Что проверяет | Чьи это слова | Важность | Что НЕ нарушение |")
        lines.append("|---|---|---|---|---|")
        for rule in module.RULES:
            lines.append(
                f"| `{rule['id']}` | {rule['что']} | {rule.get('источник', '—')} "
                f"| {rule.get('важность', '—')} | {rule.get('не_нарушение', '—')} |"
            )
        lines.append("")
        runtime = getattr(module, "RUNTIME_ONLY", [])
        if runtime:
            lines.append("**Проверить статически нельзя:**")
            lines += [f"- {item}" for item in runtime]
            lines.append("")

    if silent:
        lines.append("### Модули без объявленных правил")
        lines.append("")
        lines.append("Работают, но свои правила в спеку не отдают — читать можно только код.")
        lines.append("")
        for module in silent:
            first = (module.__doc__ or "").strip().splitlines()
            lines.append(f"- `{module.NAME}` — {first[0] if first else 'без описания'}")
        lines.append("")

    lines.append(END)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not SPEC.exists():
        print(f"Нет файла {SPEC.relative_to(REPO)} — сперва напишите рукописную часть", file=sys.stderr)
        return 2

    text = SPEC.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print("В спецификации нет маркеров раздела реестра", file=sys.stderr)
        return 2

    head, _, rest = text.partition(START)
    _, _, tail = rest.partition(END)
    updated = head + build() + tail

    if "--check" in argv:
        if updated != text:
            print("РАСХОЖДЕНИЕ: спецификация отстала от кода.")
            print("Починить: python3 tools/spec/generate.py")
            return 1
        print("Спецификация совпадает с кодом.")
        return 0

    SPEC.write_text(updated, encoding="utf-8")
    print(f"Обновлено: {SPEC.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
