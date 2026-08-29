"""Прогон приёмки: python3 -m runner [папка-examples] [--verbose]

Печатает по строке на пример и итог «прошло N из M».

ЧЕСТНО О СВЕРКЕ. `expected.md` написан прозой, и сверять его с отчётом
машина может только приблизительно. Поэтому автосверка идёт по ЯКОРЯМ —
конкретным фактам, которые заказчик назвал в expected: номера правил,
имена ключей, номиналы, детали, плейсхолдеры. Если якорь есть в отчёте,
факт считается покрытым.

Это подсказка комнате, где красное, а не приговор. Последнее слово
о «решило / не решило» — за заказчиком, так записано в README приёмки.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.__main__ import run                        # noqa: E402
from core.loader import load_expected                # noqa: E402
from core.report import render                       # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

# якорь = конкретный факт, который заказчик назвал в expected.md
ANCHOR_PATTERNS = (
    r"`([^`\n]+)`",                    # всё, что заказчик взял в обратные кавычки
    r"\b([A-Z][A-Z0-9_]{3,})\b",       # DB_URL, BIND_HOST, PERSON-1, INV-0042
    r"\b(\d+[.,]\d+)\b",               # 25.03, 11.96, 12.00
    r"\b([а-яё]+-\d+)\b",              # вал-102, фланец-7
)

# служебные слова, которые встречаются в expected, но фактами не являются
STOP_ANCHORS = {"expected.md", "input", "json", "md", "csv", "txt"}


# в expected.md составитель дописывает к цитате пояснение вида
# «  (было: 0.00015)» — это знание оригинала, которого у инструмента нет.
# Факт — до пояснения, иначе сверка требует невозможного.
ANCHOR_TAIL = re.compile(r"\s{2,}\((?:было|второй был|раньше)[^)]*\)\s*$")


def anchors(expected: str) -> list[str]:
    # Преамбула expected.md — про то, откуда взялись правила («собраны
    # из интервью 29.08»). Это метаданные составителя, а не факты
    # проверяемого файла: требовать их от отчёта бессмысленно.
    # Режем всё до первого раздела, если разделы вообще есть.
    if re.search(r"^## ", expected, re.M):
        expected = expected[re.search(r"^## ", expected, re.M).start():]

    found: list[str] = []
    for pattern in ANCHOR_PATTERNS:
        for match in re.findall(pattern, expected):
            token = ANCHOR_TAIL.sub("", match.strip()).strip()
            if len(token) < 3 or token.lower() in STOP_ANCHORS:
                continue
            if token not in found:
                found.append(token)
    return found


def check_example(example_dir: Path, verbose: bool = False) -> tuple[str, str]:
    """Возвращает (статус, подробности)."""
    report = run(example_dir, quiet=not verbose)
    expected = load_expected(example_dir)
    text = render(report, title=example_dir.name)

    if not report.checked_by:
        return "НЕ ПРОВЕРЕНО", "ни один модуль не взялся — кусок ещё не написан"

    if not expected:
        return "ОТЧЁТ ЕСТЬ", f"{len(report.findings)} находок, expected.md отсутствует"

    wanted = anchors(expected)
    missing = [a for a in wanted if a not in text]
    covered = len(wanted) - len(missing)

    if verbose:
        print("\n" + text + "\n")

    if not wanted:
        return "ОТЧЁТ ЕСТЬ", "в expected.md нет якорей для автосверки — смотреть глазами"
    if not missing:
        return "ПРОШЁЛ", f"якорей покрыто {covered}/{len(wanted)}, находок {len(report.findings)}"
    return "ЧАСТИЧНО", f"якорей покрыто {covered}/{len(wanted)}, не найдено: {', '.join(missing[:4])}"


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv or "-v" in argv
    args = [a for a in argv[1:] if not a.startswith("-")]
    root = Path(args[0]) if args else REPO_ROOT / "examples"

    examples = sorted(d for d in root.iterdir() if d.is_dir())
    if not examples:
        print(f"В {root} нет примеров", file=sys.stderr)
        return 2

    print(f"Приёмка комнаты 5 · {len(examples)} примеров\n")
    passed = 0
    for example in examples:
        status, details = check_example(example, verbose=verbose)
        mark = {"ПРОШЁЛ": "✓", "ЧАСТИЧНО": "~", "НЕ ПРОВЕРЕНО": "·"}.get(status, "?")
        if status == "ПРОШЁЛ":
            passed += 1
        print(f"  {mark} {example.name:<28} {status:<14} {details}")

    print(f"\nПРОШЛО {passed} ИЗ {len(examples)}")
    print("\nАвтосверка идёт по якорям из expected.md и является подсказкой,")
    print("а не вердиктом: «решило / не решило» в конце дня говорит заказчик.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
