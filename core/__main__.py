"""CLI: python3 -m core <папка-примера-или-артефакта>

Показывает, какие модули взялись за вход, и печатает единый отчёт.
"""

import sys
from pathlib import Path

from .loader import load_inputs
from .model import Report
from .registry import pick
from .report import render, render_chat


def run(target: Path, quiet: bool = False) -> Report:
    inputs = load_inputs(target)
    if not inputs:
        if not quiet:
            print(f"Нечего проверять: в {target} нет текстовых файлов", file=sys.stderr)
        return Report()

    merged = Report()
    modules = pick(inputs)
    if not modules and not quiet:
        print(f"  (ни один модуль не взялся за вход: {', '.join(inputs)})", file=sys.stderr)

    for module in modules:
        try:
            result = module.check(inputs)
        except Exception as exc:
            print(f"  ⚠ {module.NAME}.check() упал: {exc}", file=sys.stderr)
            continue
        if result is None:
            continue
        merged.findings.extend(result.findings)
        merged.artifacts.update(result.artifacts)
        merged.notes.extend(result.notes)
        merged.runtime_only.extend(result.runtime_only)
        merged.checked_by.append(module.NAME)
    return merged


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    target = Path([a for a in argv[1:] if not a.startswith("-")][0])
    if not target.exists():
        print(f"Нет такой папки: {target}", file=sys.stderr)
        return 2
    report = run(target)
    if "--chat" in argv:
        print(render_chat(report, target.name))
    else:
        print(render(report, title=f"Отчёт: {target.name}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
