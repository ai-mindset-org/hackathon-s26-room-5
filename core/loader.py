"""Загрузка входов примера: папка input/ → {имя файла: содержимое}."""

from pathlib import Path

TEXT_SUFFIXES = {".md", ".txt", ".csv", ".env", ".json", ".yaml", ".yml", ".ini", ".conf", ""}


def load_inputs(example_dir: Path) -> dict[str, str]:
    """Читает example_dir/input/ (или саму папку, если input/ нет).

    Возвращает {имя файла: содержимое}. Имя — относительное, чтобы модуль
    мог опознать свой вход по названию (`matches`), не зная путей машины.
    """
    example_dir = Path(example_dir)
    root = example_dir / "input"
    if not root.is_dir():
        root = example_dir

    inputs: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            inputs[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue    # двоичное — не наш случай, модули работают с текстом
    return inputs


def load_expected(example_dir: Path) -> str:
    """Ожидаемый результат примера. Пусто, если файла нет."""
    path = Path(example_dir) / "expected.md"
    return path.read_text(encoding="utf-8") if path.is_file() else ""
