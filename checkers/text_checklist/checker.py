"""Документ против чеклиста, написанного человеком.

Боль: спецификацию перед сдачей читают глазами по списку правил, который
живёт у проверяющего в голове или в отдельном файле.

Как устроено. Чеклист разбирается на пункты, каждый пункт по ключевым словам
опознаётся как один из типов проверки. Что не опозналось - честно попадает
в «не проверено», а не выдаётся за проверенное. Это важнее полноты: заказчик
должен видеть охват, иначе отчёт врёт молчанием.

Главное требование примера - не ловить лишнего. Измеримые требования
(«не более 2 секунд») правило соблюдают, и трогать их нельзя.
"""
from __future__ import annotations

import re

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent.parent))
from core.model import Report  # noqa: E402
from checkers._finding import Finding  # noqa: E402

NAME = "text_checklist"
TITLE = "Документ против чеклиста"

# Своих правил у модуля нет: он читает чеклист заказчика и опознаёт каждый
# пункт по формулировке. Ниже — типы проверок, которые он умеет закрывать.
RULES = [
    {"id": "запрещённые слова", "что": "оценочное слово из чеклиста стоит без числа или критерия",
     "источник": "чеклист заказчика, пункт вида «запрещены слова „быстро“, „удобно“»",
     "важность": "нарушение",
     "не_нарушение": "то же слово рядом с числом — метрика указана"},
    {"id": "нумерация разделов", "что": "у каждого заголовка есть номер",
     "источник": "чеклист заказчика", "важность": "нарушение",
     "не_нарушение": "заголовок, начинающийся с числа"},
    {"id": "аббревиатуры", "что": "аббревиатура расшифрована при первом употреблении",
     "источник": "чеклист заказчика", "важность": "нарушение",
     "не_нарушение": "общеизвестные (API, HTTP, PDF, ГОСТ) и расшифрованные в скобках"},
    {"id": "дата и версия", "что": "у документа указаны дата и версия",
     "источник": "чеклист заказчика", "важность": "нарушение", "не_нарушение": "—"},
    {"id": "заголовок таблицы", "что": "у таблицы есть название и непустая шапка",
     "источник": "чеклист заказчика", "важность": "нарушение",
     "не_нарушение": "таблица с подписью строкой выше"},
    {"id": "версия внешних ссылок", "что": "ссылка на регламент или стандарт идёт с номером версии",
     "источник": "чеклист заказчика", "важность": "нарушение",
     "не_нарушение": "ссылка, рядом с которой стоит версия или номер редакции"},
    {"id": "измеримость", "что": "требование со словом «должен» содержит число или критерий да/нет",
     "источник": "чеклист заказчика", "важность": "нарушение",
     "не_нарушение": "«не более 2 секунд», «не более 8 полей» — измеримо"},
]

RUNTIME_ONLY = [
    "пункт чеклиста, который модуль не опознал по формулировке — уходит "
    "в раздел «машина не проверяла», а не выдаётся за проверенный",
    "смысловая полнота документа: сказано ли всё, что нужно заказчику",
]

# Аббревиатуры, которые расшифровывать не просят.
COMMON_ABBR = {
    "API", "HTTP", "HTTPS", "URL", "URI", "PDF", "CSV", "JSON", "XML", "SQL", "HTML",
    "CSS", "REST", "SDK", "CLI", "UI", "UX", "ID", "IT", "PC", "OS", "RAM", "CPU",
    "ГОСТ", "СНиП", "ТЗ", "ПО", "БД", "ОС",
}

NUM = re.compile(r"\d")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
MD_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
ABBR_TOKEN = re.compile(r"\b[А-ЯЁA-Z]{2,6}\b")
DATE = re.compile(r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b")
VERSION = re.compile(r"\bверси[яию]\w*\s*[:№]?\s*[\d.]+|\bv\.?\s*\d+(\.\d+)*\b|\bред\.\s*\d+", re.I)
EXTERNAL_DOC = re.compile(
    r"\b(регламент\w*|стандарт\w*|инструкци\w*|положени\w*|политик\w*|методик\w*|"
    r"руководств\w*|ГОСТ\s*[\w.-]*|СНиП\s*[\w.-]*)\b", re.I)

# Слово-признак требования. Узко намеренно: широкий список ловит лишнее.
REQUIREMENT = re.compile(r"\b(должен|должна|должно|должны|обязан\w*|требуется)\b", re.I)


def matches(inputs: dict[str, str]) -> bool:
    has_checklist = any("чеклист" in n.lower() or "checklist" in n.lower()
                        or "чек-лист" in n.lower() for n in inputs)
    has_doc = any(n.lower().endswith(".md") and "checklist" not in n.lower()
                  and "чеклист" not in n.lower() for n in inputs)
    return has_checklist and has_doc


def parse_checklist(text: str) -> list[tuple[str, str]]:
    """Нумерованный список -> [("п.1", "текст правила"), ...]"""
    out = []
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)[.)]\s+(.*\S)", line)
        if m:
            out.append((f"п.{m.group(1)}", m.group(2).strip()))
    return out


def classify(rule: str) -> str:
    """Какой проверкой закрывается пункт чеклиста."""
    r = rule.lower()
    if "запрещен" in r and ("«" in rule or '"' in rule):
        return "banned_words"
    if "аббревиатур" in r:
        return "abbreviations"
    if "таблиц" in r and "заголов" in r:
        return "table_caption"
    if ("ссылк" in r or "внешн" in r) and "верси" in r:
        return "external_version"
    if "дата" in r and "верси" in r:
        return "doc_meta"
    if "раздел" in r and "номер" in r:
        return "section_numbering"
    if "измерим" in r or ("число" in r and "критери" in r):
        return "measurable"
    return "unknown"


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _line_no(lines: list[str], needle: str) -> int:
    for i, line in enumerate(lines, start=1):
        if needle in line:
            return i
    return 0


def _stem_ru(word: str) -> str:
    w = word.lower().replace("ё", "е")
    return w[:5] if len(w) > 5 else w


def _sentence_with(line: str, needle: str) -> str:
    """Цитируем предложение с находкой, а не всю строку.

    Иначе в цитату про нерасшифрованную аббревиатуру попадает соседнее
    измеримое требование, и человек читает отчёт как претензию к нему.
    """
    for s in SENTENCE_SPLIT.split(line):
        if needle in s:
            return s.strip()
    return line.strip()


def check(inputs: dict[str, str]) -> Report:
    rep = Report()

    cl_name = next((n for n in inputs if "чеклист" in n.lower() or "checklist" in n.lower()
                    or "чек-лист" in n.lower()), None)
    doc_name = next((n for n in inputs if n != cl_name and n.lower().endswith((".md", ".txt"))), None)
    if not cl_name or not doc_name:
        rep.runtime_only.append("нужны два файла: чеклист и проверяемый документ")
        return rep

    rules = parse_checklist(inputs[cl_name])
    doc = inputs[doc_name]
    lines = _lines(doc)
    raw: list[tuple[int, Finding]] = []   # (приоритет, находка) - для снятия дублей

    for rule_id, rule_text in rules:
        kind = classify(rule_text)

        if kind == "banned_words":
            words = re.findall(r"[«\"]([^»\"]+)[»\"]", rule_text)
            for w in words:
                stem = _stem_ru(w)
                for i, line in enumerate(lines, start=1):
                    for token in re.findall(r"\b[А-Яа-яЁё]+\b", line):
                        if _stem_ru(token) != stem:
                            continue
                        # рядом есть число - метрика указана, правило соблюдено
                        sentence = next((s for s in SENTENCE_SPLIT.split(line) if token in s), line)
                        if NUM.search(sentence):
                            rep.notes.append(f"{doc_name}:{i}: «{token}» с метрикой рядом - норма")
                            continue
                        raw.append((10, Finding(
                            rule_id=rule_id, rule_text=rule_text, where=f"{doc_name}:{i}",
                            quote=_sentence_with(line, token), what=f"«{token}» без метрики",
                            hint="заменить числом или критерием да/нет")))

        elif kind == "section_numbering":
            for i, line in enumerate(lines, start=1):
                m = MD_HEADING.match(line)
                if not m:
                    continue
                title = m.group(2)
                if not re.match(r"^\d+[.)]?\s", title):
                    raw.append((10, Finding(
                        rule_id=rule_id, rule_text=rule_text, where=f"{doc_name}:{i}",
                        quote=line.strip(), what=f"раздел «{title}» без номера",
                        hint="пронумеровать разделы сквозной нумерацией")))
                else:
                    rep.notes.append(f"{doc_name}:{i}: раздел «{title}» пронумерован")

        elif kind == "abbreviations":
            seen: set[str] = set()
            for i, line in enumerate(lines, start=1):
                for token in ABBR_TOKEN.findall(line):
                    if token in COMMON_ABBR or token in seen or token.isdigit():
                        continue
                    seen.add(token)
                    # расшифровка рядом: «СЭД (система электронного документооборота)»
                    if re.search(re.escape(token) + r"\s*[(–—-]", line):
                        rep.notes.append(f"{doc_name}:{i}: «{token}» расшифрована")
                        continue
                    raw.append((10, Finding(
                        rule_id=rule_id, rule_text=rule_text, where=f"{doc_name}:{i}",
                        quote=_sentence_with(line, token),
                        what=f"аббревиатура «{token}» не расшифрована при первом употреблении",
                        hint=f"дать расшифровку в скобках после «{token}»")))

        elif kind == "doc_meta":
            head = "\n".join(lines[:12])
            has_date, has_version = bool(DATE.search(head)), bool(VERSION.search(head))
            if not has_date or not has_version:
                missing = " и ".join(x for x, ok in (("дата", has_date), ("версия", has_version)) if not ok)
                raw.append((10, Finding(
                    rule_id=rule_id, rule_text=rule_text, where=f"{doc_name}:1",
                    quote=lines[0].strip() if lines else "",
                    what=f"у документа не указана {missing}",
                    hint="добавить строку «Версия 1.0 от 29.08.2026» под заголовком")))
            else:
                rep.notes.append(f"{doc_name}: дата и версия указаны")

        elif kind == "table_caption":
            for i, line in enumerate(lines, start=1):
                if not line.strip().startswith("|"):
                    continue
                prev = lines[i - 2].strip() if i >= 2 else ""
                if prev.startswith("|"):
                    continue  # не первая строка таблицы
                header_cells = [c.strip() for c in line.strip().strip("|").split("|")]
                empty_header = not any(header_cells)
                caption_above = bool(prev) and not prev.startswith("|")
                if empty_header or not caption_above:
                    what = "у таблицы пустая шапка" if empty_header else "у таблицы нет заголовка"
                    raw.append((10, Finding(
                        rule_id=rule_id, rule_text=rule_text, where=f"{doc_name}:{i}",
                        quote=line.strip(), what=f"{what} - непонятно, что в ней",
                        hint="назвать таблицу строкой над ней и заполнить шапку")))
                else:
                    rep.notes.append(f"{doc_name}:{i}: у таблицы есть заголовок")

        elif kind == "external_version":
            for i, line in enumerate(lines, start=1):
                for m in EXTERNAL_DOC.finditer(line):
                    around = line[max(0, m.start() - 40): m.end() + 60]
                    if VERSION.search(around) or re.search(r"№\s*[\w.-]+", around):
                        rep.notes.append(f"{doc_name}:{i}: ссылка на «{m.group(0)}» с версией")
                        continue
                    raw.append((10, Finding(
                        rule_id=rule_id, rule_text=rule_text, where=f"{doc_name}:{i}",
                        quote=_sentence_with(line, m.group(0)),
                        what=f"ссылка на «{m.group(0)}» без номера версии",
                        hint="дописать версию или номер редакции документа")))

        elif kind == "measurable":
            # узко: только явные требования («должен…») без единого числа.
            for i, line in enumerate(lines, start=1):
                for s in SENTENCE_SPLIT.split(line):
                    if not REQUIREMENT.search(s) or NUM.search(s):
                        continue
                    raw.append((5, Finding(
                        rule_id=rule_id, rule_text=rule_text, where=f"{doc_name}:{i}",
                        quote=s.strip(), what="требование без числа и без критерия да/нет",
                        hint="добавить измеримую границу")))
                if NUM.search(line) and REQUIREMENT.search(line):
                    rep.notes.append(f"{doc_name}:{i}: требование измеримо")

        else:
            rep.runtime_only.append(f"{rule_id} не проверено машиной: «{rule_text}»")

    # Одно место - одна находка. Конкретное правило вытесняет общее:
    # «быстро без метрики» точнее, чем «требование без числа».
    # На одном месте оставляем находки самого сильного правила и все они,
    # если правило одно: «быстро» и «удобным» в одной строке - две разные правки.
    top: dict[str, int] = {}
    for prio, f in raw:
        top[f.where] = max(top.get(f.where, 0), prio)
    kept = [f for prio, f in raw if prio == top[f.where]]
    for f in sorted(kept, key=lambda f: (f.rule_id, f.where, f.what)):
        rep.findings.append(f)

    # То, что измеримо, отмечаем явно - охват проверки должен быть виден.
    for i, line in enumerate(lines, start=1):
        if re.search(r"не более \d|не менее \d|не превыша\w+ \d", line, re.I):
            rep.notes.append(f"{doc_name}:{i}: «{line.strip()}» - измеримо")
    return rep
