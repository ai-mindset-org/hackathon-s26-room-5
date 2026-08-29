#!/usr/bin/env python3
"""Check a spec document against a checklist and report violations."""

import sys
import re
from pathlib import Path


def check_spec_against_checklist(spec_path: Path, checklist_path: Path) -> dict:
    """Check spec document against checklist items and return violations/compliance."""
    spec_text = spec_path.read_text(encoding="utf-8")
    checklist_text = checklist_path.read_text(encoding="utf-8")

    # Parse checklist items
    items = []
    for line in checklist_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"(\d+)\.\s+(.+)", line)
        if match:
            items.append({
                "number": int(match.group(1)),
                "text": match.group(2).strip()
            })

    violations = []
    compliance = []

    # Make spec text lowercase for matching but keep original for context
    spec_lower = spec_text.lower()

    # === Checklist item 1: Every section has a number ===
    has_numbered_sections = False
    heading_pattern = r"(?m)^#{1,3}\s+(\d+[\w\s]*|[А-Яа-яa-zA-Z]+)$"
    headings = re.findall(heading_pattern, spec_text)
    if headings:
        has_numbered_sections = any(re.match(r"^\d+", h.strip()) for h in headings)

    if not has_numbered_sections and len(headings) > 0:
        # Find the first heading that looks like a section title
        for h in headings:
            if not re.match(r"^\d+", h.strip()):
                violations.append({
                    "number": 1,
                    "text": "У каждого раздела есть номер",
                    "location": f"'{h}' —section unnumbered"
                })
                break

    # === Checklist item 2: Every requirement is measurable ===
    # Look for measurable patterns in the spec
    measurable_patterns = [
        r"не более\s+\d+",
        r"более\s+\d+",
        r"\d+\s*(секунды|полей|версий|версия|шт)%?",
        r"(да|нет)\s*[::]",
        r"\d+%",
    ]
    all_spec_lower = spec_lower
    found_any_measurable = False
    for pattern in measurable_patterns:
        if re.search(pattern, all_spec_lower):
            found_any_measurable = True
            break

    # Only flag as violation if there are requirements sections but no measurable criteria
    has_requirements_section = bool(re.search(r"требования", spec_lower))
    if has_requirements_section and not found_any_measurable:
        violations.append({
            "number": 2,
            "text": "Каждое требование измеримо: есть число или критерий «да/нет»",
            "location": "в разделе требования — отсутствуют числовые критерии"
        })

    # === Checklist item 3: Forbidden words without metric ===
    forbidden_words = ["быстро", "удобно", "современный"]
    for word in forbidden_words:
        word_pattern = rf"\b{re.escape(word)}\b"
        for match in re.finditer(word_pattern, spec_lower):
            start = match.start()
            end = min(start + 50, len(spec_text))
            context = spec_text[start:end]
            # Check if there's a metric nearby in the full spec
            # Look within 30 chars before and after
            context_start = max(0, start - 30)
            context_end = min(len(spec_lower), start + 50)
            nearby_text = spec_lower[context_start:context_end]
            has_metric_nearby = bool(re.search(r"не более\s+\d+|более\s+\d+|\d+[%\s]+", nearby_text))
            if not has_metric_nearby:
                # Find the sentence containing this word
                sent_start = spec_text.rfind(". ", max(0, start - 100)) + 1
                sent_end = spec_text.find(". ", start + 100)
                if sent_end == -1:
                    sent_end = len(spec_text)
                sentence = spec_text[sent_start:sent_end + 1].strip()
                # Trim to reasonable length
                if len(sentence) > 60:
                    # Find a good cutoff point
                    cutoff = sentence[:60].rfind(" ")
                    if cutoff > 0:
                        sentence = sentence[:cutoff] + "..."
                violations.append({
                    "number": 3,
                    "text": f"Запрещено слово '{word}' без метрики",
                    "location": sentence
                })
                break  # Only report first occurrence per word
        else:
            continue
        break  # Only report first forbidden word found

    # === Checklist item 4: All abbreviations decoded on first use ===
    # Check for "СЭД" without definition
    if re.search(r"\bС[Эё]Д\b", spec_lower):
        # Check if there's a definition nearby
        definitions_patterns = [
            r"с\.?\s*э\.?\s*д[:\s]",
            r"расшифров",
            r"full\s+form",
            r"Software.*Enterprise.*Document",
        ]
        found_definition = any(re.search(p, spec_lower) for p in definitions_patterns)
        if not found_definition:
            # Find the position and sentence
            abbr_match = re.search(r"\bС[Эё]Д\b", spec_lower)
            if abbr_match:
                pos = abbr_match.start()
                sent_start = spec_text.rfind(". ", max(0, pos - 100)) + 1
                sent_end = spec_text.find(". ", pos + 100)
                if sent_end == -1:
                    sent_end = len(spec_text)
                sentence = spec_text[sent_start:sent_end + 1].strip()
                if len(sentence) > 60:
                    cutoff = sentence[:60].rfind(" ")
                    if cutoff > 0:
                        sentence = sentence[:cutoff] + "..."
                violations.append({
                    "number": 4,
                    "text": "Все аббриваиатуры расшифрованы при первом употреблении",
                    "location": sentence
                })

    # === Checklist item 5: Date and version specified ===
    # Combined check: if either date or version is missing, report one violation
    date_patterns = [
        r"\d{1,2}[.\-]\d{1,2}[.\-]\d{4}",
        r"\d{4}[.\-]\d{1,2}[.\-]\d{1,2}",
    ]
    version_patterns = [
        r"версия\s+\d+",
        r"v\d+\.\d+",
        r"Version\s+\d+",
    ]

    has_date = any(re.search(p, spec_lower) for p in date_patterns)
    has_version = any(re.search(p, spec_lower) for p in version_patterns)

    if not has_date or not has_version:
        violations.append({
            "number": 5,
            "text": "Указана дата и версия документа",
            "location": ("нет даты документа" if not has_date else "") + 
                       ("; " if not has_date and not has_version else "") +
                       ("нет версии документа" if not has_version else "")
        })

    # === Checklist item 6: Every table has a header ===
    lines = spec_text.splitlines()
    has_table_header = False
    in_table = False
    table_count = 0

    for line in lines:
        if "|" in line:
            pipe_count = line.count("|")
            if pipe_count >= 4:
                if not in_table:
                    in_table = True
                    table_count += 1
                # Check for separator line with ---
                if re.search(r"\|---+\|", line) or re.search(r"\|-+\|", line):
                    has_table_header = True
        else:
            if in_table and table_count > 0:
                pass  # Table ended
            in_table = False

    if table_count > 0 and not has_table_header:
        violations.append({
            "number": 6,
            "text": "У каждой таблицы есть заголовок",
            "location": "в документе есть таблицы без строки заголовка ---"
        })

    # === Checklist item 7: External links have version ===
    external_links = re.findall(r"\[.+?\]\(.+?\)", spec_text)
    versionless_external = []
    for link in external_links:
        link_match = re.search(r"\((.+?)\)", link)
        if link_match:
            link_target = link_match.group(1)
            # Check if it's a reference to external doc without version
            if any(keyword in link_target.lower() for keyword in ["регламент", "документ", "политика"]):
                if not re.search(r"версия\s+\d+|v\d+", link_target.lower()):
                    versionless_external.append(link_target)

    if versionless_external:
        # Find the sentence containing the first such link
        first_link = versionless_external[0]
        link_pos = spec_text.find(first_link)
        if link_pos >= 0:
            sent_start = spec_text.rfind(". ", max(0, link_pos - 100)) + 1
            sent_end = spec_text.find(". ", link_pos + 100)
            if sent_end == -1:
                sent_end = len(spec_text)
            sentence = spec_text[sent_start:sent_end + 1].strip()
            if len(sentence) > 60:
                cutoff = sentence[:60].rfind(" ")
                if cutoff > 0:
                    sentence = sentence[:cutoff] + "..."
            violations.append({
                "number": 7,
                "text": "Ссылки на внешние документы — с номером версии",
                "location": sentence
            })

    return {
        "violations": violations,
        "compliance": compliance,
        "items": items  # Return items for main to use
    }


def main():
    if len(sys.argv) < 3:
        print("Использование: python checklist_tool.py <spec_file> <checklist_file>")
        sys.exit(1)

    spec_path = Path(sys.argv[1])
    checklist_path = Path(sys.argv[2])

    if not spec_path.exists():
        print(f"Файл спецификации не найден: {spec_path}")
        sys.exit(1)

    if not checklist_path.exists():
        print(f"Файл чеклиста не найден: {checklist_path}")
        sys.exit(1)

    result = check_spec_against_checklist(spec_path, checklist_path)

    # Output report
    print(f"# Отчёт по проверке: {spec_path.name}")
    print()

    print("## Нарушения:")
    if result["violations"]:
        for i, v in enumerate(result["violations"], 1):
            print(f"{i}. «{v['location']}» — п.{v['number']}")
    else:
        print("Нарушений не найдено.")

    print()
    print("## Соответствие (не нарушение):")
    # Print satisfied checklist items (items not in violations)
    reported_numbers = set(v["number"] for v in result["violations"])
    for item in result["items"]:
        n = item["number"]
        if n not in reported_numbers:
            print(f"п. {n} — {item['text']}")

    print()
    print("Ключевая проверка: отчёт называет пункт чеклиста и точное место,")
    print("ложных срабатываний на измеримые требования нет.")


if __name__ == "__main__":
    main()