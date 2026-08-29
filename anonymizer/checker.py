"""Обезличивание перед передачей наружу и обратный маппинг.

Боль: данные уходят наружу, персональное надо скрыть, а потом уметь вернуть.

Две ловушки примера:
  1. Один человек, названный дважды, получает ОДИН плейсхолдер.
  2. Идентификатор сервера INV-0042 и дата - не персональные данные, не трогаем.

Обратный прогон возвращает оригинал байт в байт. Поэтому mapping.json хранит
не только «плейсхолдер -> канон», но и каждое вхождение с его точной формой:
«Анной Соловьёвой» и «Анна Соловьёва» - один человек, но разные строки в тексте.
"""
from __future__ import annotations

import json
import re

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from checkers._finding import Finding  # noqa: E402
from core.model import Report          # noqa: E402

NAME = "anonymizer"
TITLE = "Обезличивание и обратный маппинг"

# Что НЕ персональные данные: инвентарные номера, даты, версии.
KEEP = re.compile(r"\b([A-Z]{2,}-\d+|\d{1,2}\.\d{1,2}(\.\d{2,4})?)\b")

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE = re.compile(r"(?<![\w-])(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?![\d-])")
EXT = re.compile(r"(?:добавочный|доб\.?|ext\.?)\s*(\d{2,5})", re.I)
# Русское ФИО: Имя Фамилия, оба с заглавной, кириллица, в любом падеже.
# Имя и фамилия разделены пробелом, но НЕ переводом строки: иначе
# заголовок «## Требования» и первое слово следующего абзаца
# склеиваются в несуществующего человека.
PERSON = re.compile(r"\b[А-ЯЁ][а-яё]{1,}(?:ий|ой|ей|ов|ев|ём|ом)?[ \u00A0]+[А-ЯЁ][а-яё]{2,}\b")

# Слова, которые начинают предложение и не являются именем.
NOT_A_NAME = {
    "отчёт", "отчет", "заявку", "заявка", "согласовано", "сервер", "повторный",
    "контакт", "подал", "подала", "документ", "приложение", "таблица", "раздел",
    "примечание", "итого", "дата", "версия", "пример", "внимание",
}

# Падежные окончания. «ов»/«ев» сюда НЕ входят: это часть фамилии,
# срезав их, мы развели бы «Петров» и «Петрова» по разным людям.
ENDINGS = ("ой", "ей", "ом", "ым", "ам", "ах", "ы", "и", "а", "у", "е", "ю", "я")


def matches(inputs: dict[str, str]) -> bool:
    """Берёмся за текст, где есть хоть что-то персональное.

    Раньше требовались email или телефон - и текст, где люди названы только
    по имени и добавочному, молча проходил мимо обезличивания. Это дыра:
    фамилия уходит наружу ровно так же, как почта.
    """
    if not any(n.lower().endswith((".txt", ".md")) for n in inputs):
        return False
    # Конфиг или таблица рядом означают, что артефакт - не текст, а .md лежит
    # как описание правил. Обезличивать его нечего: имя автора в критериях
    # проверки не персональные данные клиента, а подпись под инструкцией.
    if any(n.lower().endswith((".yaml", ".yml", ".env", ".csv", ".toml", ".ini"))
           for n in inputs):
        return False
    # файл правил лежит рядом с артефактом - работаем с артефактом,
    # а не отказываемся от всей папки
    name = _pick_artifact(inputs)
    if not name:
        return False
    text = inputs[name]
    if EMAIL.search(text) or PHONE.search(text) or EXT.search(text):
        return True
    blocked = [(m.start(), m.end()) for m in KEEP.finditer(text)]
    return bool(_find_persons(text, blocked))


# Файл с правилами - не артефакт: его обезличивать нельзя, иначе инструмент
# вычистит примеры из самой инструкции и объявит это работой.
RULES_HINTS = ("rule", "правил", "checklist", "чеклист", "чек-лист", "политик",
               "инструкц", "критери", "expected", "ожидаем", "readme", "howto")


def _pick_artifact(inputs: dict[str, str]) -> str:
    texts = [n for n in inputs if n.lower().endswith((".txt", ".md"))]
    real = [n for n in texts if not any(h in n.lower() for h in RULES_HINTS)]
    return (real or texts or [""])[0]


def _stem(word: str) -> str:
    """Грубая основа слова: снимаем падежное окончание. Нужна, чтобы склеить
    «Анна Соловьёва» и «Анной Соловьёвой» в одного человека."""
    w = word.lower().replace("ё", "е")
    for end in ENDINGS:
        if len(w) > len(end) + 2 and w.endswith(end):
            return w[: -len(end)]
    return w


def _key(value: str) -> str:
    """Ключ склейки форм одного имени.

    Снятия окончания мало: «петров» даёт основу «петр», а «петрова» - «петров».
    Поэтому основу ещё и подрезаем до шести букв: «петров»/«петрова» сходятся,
    а «романов»/«романенко» - нет.
    """
    return " ".join(_stem(p)[:6] for p in value.split())


def _find_persons(text: str, blocked: list[tuple[int, int]]) -> list[tuple[int, int, str]]:
    out = []
    for m in PERSON.finditer(text):
        if any(s < m.end() and m.start() < e for s, e in blocked):
            continue
        first = m.group(0).split()[0].lower().replace("ё", "е")
        if first in NOT_A_NAME:
            continue
        out.append((m.start(), m.end(), m.group(0)))
    return out


def anonymize(text: str) -> tuple[str, dict]:
    """Текст -> (обезличенный текст, mapping)."""
    blocked = [(m.start(), m.end()) for m in KEEP.finditer(text)]

    spans: list[tuple[int, int, str, str]] = []  # начало, конец, тип, исходная строка
    for m in EMAIL.finditer(text):
        spans.append((m.start(), m.end(), "EMAIL", m.group(0)))
    for m in PHONE.finditer(text):
        spans.append((m.start(), m.end(), "PHONE", m.group(0)))
    for m in EXT.finditer(text):
        spans.append((m.start(1), m.end(1), "EXT", m.group(1)))
    for s, e, val in _find_persons(text, blocked):
        spans.append((s, e, "PERSON", val))

    # вложенные и пересекающиеся куски: берём тот, что начался раньше и длиннее
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    clean: list[tuple[int, int, str, str]] = []
    for sp in spans:
        if clean and sp[0] < clean[-1][1]:
            continue
        clean.append(sp)

    counters: dict[str, int] = {}
    by_key: dict[tuple[str, str], str] = {}   # (тип, основа) -> плейсхолдер
    canon: dict[str, str] = {}                # плейсхолдер -> первая встреченная форма
    occurrences: list[dict] = []

    out, cursor = [], 0
    for start, end, kind, value in clean:
        k = (kind, _key(value) if kind == "PERSON" else value.lower())
        if k not in by_key:
            counters[kind] = counters.get(kind, 0) + 1
            by_key[k] = f"{kind}-{counters[kind]}"
            canon[by_key[k]] = value
        ph = by_key[k]
        out.append(text[cursor:start])
        out.append(ph)
        occurrences.append({"placeholder": ph, "original": value, "at": start})
        cursor = end
    out.append(text[cursor:])

    mapping = {
        "map": canon,                      # что показать человеку: PERSON-1 -> Пётр Крылов
        "occurrences": occurrences,        # чем вернуть байт в байт, включая падежи
        "kept": sorted({m.group(0) for m in KEEP.finditer(text)}),  # что намеренно не трогали
    }
    return "".join(out), mapping


def restore(anon_text: str, mapping: dict) -> str:
    """Обратный прогон: обезличенный текст + mapping -> оригинал байт в байт."""
    out, cursor = [], 0
    for occ in mapping["occurrences"]:
        idx = anon_text.find(occ["placeholder"], cursor)
        if idx < 0:
            continue
        out.append(anon_text[cursor:idx])
        out.append(occ["original"])
        cursor = idx + len(occ["placeholder"])
    out.append(anon_text[cursor:])
    return "".join(out)


def check(inputs: dict[str, str]) -> Report:
    rep = Report()
    name = _pick_artifact(inputs)
    if not name:
        rep.runtime_only.append("не нашёл текстовый файл")
        return rep

    original = inputs[name]
    anon, mapping = anonymize(original)
    back = restore(anon, mapping)

    rep.artifacts["anonymized.txt"] = anon
    rep.artifacts["mapping.json"] = json.dumps(mapping, ensure_ascii=False, indent=2)

    for ph, value in mapping["map"].items():
        times = sum(1 for o in mapping["occurrences"] if o["placeholder"] == ph)
        forms = sorted({o["original"] for o in mapping["occurrences"] if o["placeholder"] == ph})
        rep.notes.append(
            f"{ph} ← {value}" + (f" (вхождений: {times}, формы: {', '.join(forms)})" if times > 1 else ""))
    for kept in mapping["kept"]:
        rep.notes.append(f"не трогали: {kept} - не персональные данные")

    rule = "Персональные данные заменены плейсхолдерами, обратный прогон возвращает оригинал"
    if back != original:
        # покажем первое расхождение - без него чинить нечего
        i = next((i for i, (a, b) in enumerate(zip(back, original)) if a != b), min(len(back), len(original)))
        rep.findings.append(Finding(
            rule_id="обратный маппинг", rule_text=rule, where=f"{name}:символ {i}",
            quote=original[max(0, i - 30):i + 30].replace("\n", " "),
            what="обратный прогон не вернул оригинал байт в байт",
            hint="проверить пересекающиеся находки"))
    else:
        rep.notes.append("обратный прогон вернул оригинал байт в байт")

    leftovers = []
    if EMAIL.search(anon):
        leftovers.append("email")
    if PHONE.search(anon):
        leftovers.append("телефон")
    if leftovers:
        rep.findings.append(Finding(
            rule_id="полнота", rule_text=rule, where=name,
            quote=", ".join(leftovers), what="в обезличенном тексте остались персональные данные"))

    return rep
