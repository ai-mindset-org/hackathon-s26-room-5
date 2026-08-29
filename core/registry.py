"""Подхват модулей: ядро само обходит папки и находит checker.py.

Реестра модулей в общем файле НЕТ — по решению из docs/plan-J2PL.md.
Общий список правился бы всеми сразу и стал бы главным источником
конфликтов в PR. Добавил папку с checker.py — модуль подключён.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent

# где ищем модули: checkers/* и папки верхнего уровня, названные в плане
SEARCH_DIRS = ("checkers", "anonymizer")


def _load_module(checker_path: Path) -> ModuleType | None:
    name = f"room5_checker_{checker_path.parent.name}"
    spec = importlib.util.spec_from_file_location(name, checker_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:                       # чужой модуль упал — не роняем прогон
        print(f"  ⚠ модуль {checker_path.parent.name} не загрузился: {exc}")
        return None
    if not hasattr(module, "check"):
        print(f"  ⚠ модуль {checker_path.parent.name}: нет функции check()")
        return None
    if not hasattr(module, "NAME"):
        module.NAME = checker_path.parent.name
    return module


def discover(root: Path | None = None) -> list[ModuleType]:
    """Все модули репозитория, отсортированы по имени папки."""
    root = Path(root or REPO_ROOT)
    found: list[ModuleType] = []

    for rel in SEARCH_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        # anonymizer/checker.py — сам модуль; checkers/<имя>/checker.py — вложенные
        for checker_path in sorted(base.rglob("checker.py")):
            module = _load_module(checker_path)
            if module is not None:
                found.append(module)
    return found


def pick(inputs: dict[str, str], modules: list[ModuleType] | None = None) -> list[ModuleType]:
    """Кто из модулей берётся за этот вход.

    Модуль без matches() считается «берусь всегда» — так проще писать
    первый черновик, ядро его не отсекает.
    """
    modules = discover() if modules is None else modules
    picked = []
    for module in modules:
        matches = getattr(module, "matches", None)
        try:
            if matches is None or matches(inputs):
                picked.append(module)
        except Exception as exc:
            print(f"  ⚠ {getattr(module, 'NAME', '?')}.matches() упал: {exc}")
    return picked
