"""Конфиг против правил безопасности.

Боль: перед выкаткой конфиг смотрят глазами. Секрет открытым текстом,
включённый debug, открытый наружу порт - цена ошибки высокая.

Главная ловушка примера: API_TOKEN_FILE=/etc/app/token - это НЕ секрет,
а ссылка на файл вне репозитория, то есть правило соблюдено. Модуль,
который кричит на такое, человек выключит на третий день.
"""
from __future__ import annotations

import re

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent.parent))
from core.model import Report  # noqa: E402
from checkers._finding import Finding  # noqa: E402

NAME = "config_env"
TITLE = "Конфиг против правил безопасности"

# Правила приходят из файла заказчика (security-rules.md) и разбираются
# по нумерации. Здесь объявлено то, что модуль умеет проверять машинно.
RULES = [
    {"id": "правило 1", "что": "секретов в файле нет — только ссылки на env или файл вне репозитория",
     "источник": "security-rules.md заказчика, пункт 1",
     "важность": "нарушение",
     "не_нарушение": "API_TOKEN_FILE=/etc/app/token — путь к файлу, а не сам секрет"},
    {"id": "правило 2", "что": "сервис не слушает 0.0.0.0 без пометки «публичный» в комментарии",
     "источник": "security-rules.md заказчика, пункт 2",
     "важность": "нарушение",
     "не_нарушение": "0.0.0.0 с комментарием «публичный» — решение принято осознанно"},
    {"id": "правило 3", "что": "отладочный режим выключен перед выкаткой",
     "источник": "security-rules.md заказчика, пункт 3",
     "важность": "нарушение", "не_нарушение": "DEBUG=false"},
    {"id": "правило 4", "что": "у нестандартного порта есть комментарий, что на нём живёт",
     "источник": "security-rules.md заказчика, пункт 4",
     "важность": "нарушение",
     "не_нарушение": "общеизвестные порты (443, 5432, 6379 и подобные) пояснения не требуют"},
]

RUNTIME_ONLY = [
    "жив ли сервис на указанном порту — видно только при запуске",
    "действителен ли секрет, на который ссылается переменная",
]

# Порты, которые не требуют пояснения: их узнают в лицо.
WELL_KNOWN_PORTS = {
    20, 21, 22, 23, 25, 53, 80, 110, 143, 389, 443, 465, 587, 636, 993, 995,
    1433, 1521, 3000, 3306, 5000, 5432, 5672, 6379, 8000, 8080, 8443, 9000, 9200, 27017,
}

# Имя переменной говорит: внутри не сам секрет, а путь к нему или имя источника.
POINTER_SUFFIXES = ("_FILE", "_PATH", "_ENV", "_SECRET_NAME", "_SECRETNAME", "_REF", "_LOCATION")

SECRET_NAME_HINTS = ("PASSWORD", "PASSWD", "SECRET", "TOKEN", "APIKEY", "API_KEY",
                     "PRIVATE_KEY", "ACCESS_KEY", "MASTER_KEY", "CREDENTIAL")

# Ссылка на внешнее хранилище, а не значение: os.environ/X, env::X, ${X}, vault:...
POINTER_VALUE = re.compile(
    r"^(os\.environ/|env::|\$\{|\$[A-Z_]|vault:|secret:|file:|/[\w./-]+$|[a-z]+:///?)", re.I)


def matches(inputs: dict[str, str]) -> bool:
    has_env = any(n.lower().endswith((".env", ".ini", ".cfg", ".conf", ".properties"))
                  or n.lower() in ("app.env", ".env") for n in inputs)
    has_rules = any("rule" in n.lower() or "правил" in n.lower() for n in inputs)
    return has_env and has_rules


def _parse_rules(text: str) -> dict[int, str]:
    """Нумерованный список правил из markdown -> {номер: текст}."""
    rules: dict[int, str] = {}
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)[.)]\s+(.*\S)", line)
        if m:
            rules[int(m.group(1))] = m.group(2).strip()
    return rules


def _rule(rules: dict[int, str], n: int, fallback: str) -> tuple[str, str]:
    return (f"правило {n}", rules.get(n, fallback))


def _looks_like_secret(key: str, value: str) -> bool:
    """Значение содержит сам секрет, а не ссылку на него."""
    if not value:
        return False
    # пароль внутри строки подключения ловим первым: postgres://user:PASS@host
    # это секрет, даже если значение похоже на ссылку по схеме
    if re.search(r"://[^/\s:]+:[^/\s@]+@", value):
        return True
    if POINTER_VALUE.match(value.strip()):
        return False
    if key.upper().endswith(POINTER_SUFFIXES):
        return False
    if any(h in key.upper() for h in SECRET_NAME_HINTS):
        # длинная непробельная строка похожа на сам ключ
        return bool(re.fullmatch(r"\S{8,}", value.strip()))
    return False


def check(inputs: dict[str, str]) -> Report:
    rep = Report()

    env_name = next((n for n in inputs if n.lower().endswith(".env")
                     or n.lower() in ("app.env", ".env")), None)
    rules_name = next((n for n in inputs if "rule" in n.lower() or "правил" in n.lower()), None)
    if not env_name:
        rep.runtime_only.append("не нашёл файл конфига")
        return rep

    rules = _parse_rules(inputs[rules_name]) if rules_name else {}
    env_text = inputs[env_name]

    r1 = _rule(rules, 1, "Секретов в файле нет - только ссылки на файлы/env вне репозитория.")
    r2 = _rule(rules, 2, "Сервисы не слушают 0.0.0.0, если в комментарии явно не сказано «публичный».")
    r3 = _rule(rules, 3, "DEBUG выключен.")
    r4 = _rule(rules, 4, "У каждого нестандартного порта - комментарий, что на нём живёт.")

    lines = env_text.splitlines()
    for i, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        # комментарий той же строки или строки над ней - место, где живёт пояснение
        own_comment = raw.split("#", 1)[1].strip() if "#" in raw.split("=", 1)[-1] else ""
        # Комментарий над строкой засчитываем, только если он относится
        # именно к ней. Шапка файла в первой строке пояснением к порту
        # не является - иначе первая же настройка считается описанной.
        above = lines[i - 2].strip() if i >= 3 else ""
        comment = " ".join(x for x in (own_comment, above if above.startswith("#") else "") if x)
        where = f"{env_name}:{i}"

        # правило 1 - секрет открытым текстом
        if _looks_like_secret(key, value):
            shown = re.sub(r"(://[^/\s:]+:)([^/\s@]+)(@)", r"\1***\3", line)
            rep.findings.append(Finding(
                rule_id=r1[0], rule_text=r1[1], where=where, quote=shown,
                what=f"в {key} лежит сам секрет открытым текстом",
                hint="вынести в переменную окружения или файл вне репозитория"))
        elif (key.upper().endswith(POINTER_SUFFIXES) or POINTER_VALUE.match(value)) \
                and any(h in key.upper() for h in SECRET_NAME_HINTS):
            rep.notes.append(f"{where}: {key} - ссылка на внешнее хранилище, не секрет")

        # правило 2 - слушаем на всех интерфейсах
        if "0.0.0.0" in value and "публичн" not in comment.lower() and "public" not in comment.lower():
            rep.findings.append(Finding(
                rule_id=r2[0], rule_text=r2[1], where=where, quote=line,
                what="сервис слушает 0.0.0.0, в комментарии нет пометки «публичный»",
                hint="указать конкретный интерфейс или пометить комментарием «публичный»"))

        # правило 3 - отладочный режим
        if re.fullmatch(r"[A-Z_]*DEBUG[A-Z_]*", key.upper()) and value.lower() in ("true", "1", "yes", "on"):
            rep.findings.append(Finding(
                rule_id=r3[0], rule_text=r3[1], where=where, quote=line,
                what="отладочный режим включён", hint="DEBUG=false перед выкаткой"))

        # правило 4 - нестандартный порт без пояснения
        if "PORT" in key.upper() and value.isdigit():
            port = int(value)
            if port not in WELL_KNOWN_PORTS and not comment:
                rep.findings.append(Finding(
                    rule_id=r4[0], rule_text=r4[1], where=where, quote=line,
                    what=f"порт {port} нестандартный, комментария о том, что на нём живёт, нет",
                    hint="дописать комментарий в строке над портом"))
            elif port in WELL_KNOWN_PORTS:
                rep.notes.append(f"{where}: порт {port} общеизвестный, пояснение не нужно")

    rep.notes.append(f"разобрано строк конфига: {sum(1 for l in lines if l.strip() and not l.strip().startswith('#'))}")
    return rep
