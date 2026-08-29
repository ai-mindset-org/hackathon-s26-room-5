"""Генератор артефактов с известными дефектами.

Зачем. Проверять инструмент на примерах, под которые он написан, нечестно:
он их видел. Генератор собирает новый артефакт из кусков, часть которых —
дефекты, а часть — приманки, на которые срабатывать нельзя. Что именно
заложено, известно заранее, поэтому после прогона видно три вещи:

  найдено   — дефект заложен и пойман
  пропущено — дефект заложен и не пойман
  лишнее    — инструмент нашёл то, чего не закладывали (ложная тревога)

Приманки нужны не меньше дефектов: проверяльщик, который кричит на нормальный
файл, человек выключит на третий день.
"""
from __future__ import annotations

import random

# ─────────────────────────── конфиг .env ───────────────────────────

ENV_DEFECTS = [
    ("правило 1", "пароль открытым текстом в строке подключения",
     "DB_URL=postgres://{user}:{pwd}@10.0.0.{n}/{db}"),
    ("правило 1", "секретный ключ значением, а не ссылкой",
     "PAYMENT_SECRET={pwd}{n}{pwd}"),
    ("правило 2", "слушает все интерфейсы без пометки «публичный»",
     "BIND_HOST=0.0.0.0"),
    ("правило 3", "отладочный режим включён",
     "DEBUG=true"),
    ("правило 4", "нестандартный порт без комментария",
     "SERVICE_PORT={port}"),
]

ENV_BAIT = [
    ("ссылка на файл вне репозитория — не секрет", "API_TOKEN_FILE=/etc/app/token"),
    ("ссылка на переменную окружения — не секрет", "SMTP_PASSWORD=${SMTP_PASSWORD}"),
    ("общеизвестный порт, пояснение не нужно", "DB_PORT=5432"),
    ("отладка выключена", "DEBUG=false"),
    ("обычная настройка", "LOG_LEVEL=info"),
    ("обычная настройка", "SMTP_HOST=smtp.example.org"),
    ("обычная настройка", "TIMEZONE=Europe/Zurich"),
]

ENV_RULES = """# Правила проверки конфига

1. Секретов в файле нет — только ссылки на файлы/env вне репозитория.
2. Сервисы не слушают 0.0.0.0, если в комментарии явно не сказано «публичный».
3. DEBUG выключен.
4. У каждого нестандартного порта — комментарий, что на нём живёт.
"""

# ─────────────────────────── спецификация ───────────────────────────

SPEC_DEFECTS = [
    ("п.3", "оценочное слово без метрики",
     "Интерфейс {system} должен быть удобным для оператора."),
    ("п.1", "раздел без номера", "## {section}"),
    ("п.4", "аббревиатура не расшифрована при первом употреблении",
     "Обмен идёт через {abbr} по внутреннему протоколу."),
    ("п.7", "ссылка на внешний документ без версии",
     "Порядок описан в регламенте эксплуатации."),
    ("п.6", "таблица без заголовка и с пустой шапкой", "| | |\n|---|---|\n| Срок | {days} дней |"),
]

SPEC_BAIT = [
    ("измеримое требование — правило соблюдено", "Время отклика — не более {sec} секунд."),
    ("измеримое требование — правило соблюдено", "Форма содержит не более {fields} полей."),
    ("аббревиатура расшифрована", "Обмен через API (программный интерфейс) по HTTPS."),
    ("раздел пронумерован", "## 2. Требования к надёжности"),
    ("ссылка с версией", "Согласно стандарту ГОСТ 34.601-90, версия 2."),
]

SPEC_CHECKLIST = """# Чеклист спецификации

1. У каждого раздела есть номер.
2. Каждое требование измеримо: есть число или критерий «да/нет».
3. Запрещены слова «быстро», «удобно», «современный» без метрики.
4. Все аббревиатуры расшифрованы при первом употреблении.
5. Указана дата и версия документа.
6. У каждой таблицы есть заголовок.
7. Ссылки на внешние документы — с номером версии.
"""

# ─────────────────────────── замеры и допуски ───────────────────────────

PARTS = ["вал", "фланец", "втулка", "шайба", "кронштейн", "ось", "муфта"]
PARAMS = [("диаметр_мм", 25.0, 0.02), ("длина_мм", 140.0, 0.5),
          ("толщина_мм", 12.0, 0.10), ("ширина_мм", 48.0, 0.15)]

# ─────────────────────────── текст с персональными данными ───────────────────────────

NAMES = [("Пётр", "Крылов"), ("Анна", "Соловьёва"), ("Сергей", "Волков"),
         ("Мария", "Зайцева"), ("Игорь", "Лебедев"), ("Ольга", "Морозова")]
PII_TEMPLATES = [
    "Заявку подал {name} (тел. {phone}, {email}).",
    "Согласовано с {name} {date}.",
    "Повторный контакт: {name}, добавочный {ext}.",
    "Ответственный за приёмку — {name}, почта {email}.",
]
PII_BAIT = [
    "Сервер {inv} перезагружен.",
    "Счёт {inv} оплачен {date}.",
    "Заказ {inv} закрыт без замечаний.",
]


def _rnd_pwd(rng: random.Random) -> str:
    return "".join(rng.choice("abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(10))


def _phone(rng: random.Random) -> str:
    return f"+7 9{rng.randint(10, 99)} {rng.randint(100, 999)}-{rng.randint(10, 99)}-{rng.randint(10, 99)}"


def _gen_env(rng: random.Random, n_defects: int) -> dict:
    defects = rng.sample(ENV_DEFECTS, min(n_defects, len(ENV_DEFECTS)))
    baits = rng.sample(ENV_BAIT, rng.randint(3, 5))

    lines = ["# конфиг сервиса, сгенерирован для проверки"]
    planted, hidden = [], []
    rows = [("defect", d) for d in defects] + [("bait", b) for b in baits]
    rng.shuffle(rows)

    for kind, item in rows:
        if kind == "defect":
            rule, what, tpl = item
            line = tpl.format(user=rng.choice(["app", "svc", "worker"]),
                              pwd=_rnd_pwd(rng), n=rng.randint(2, 40),
                              db=rng.choice(["appdb", "orders", "billing"]),
                              port=rng.choice([8912, 9911, 7443, 6120]))
            for part in line.split("\n"):
                lines.append(part)
            planted.append({"rule_id": rule, "what": what,
                            "line": len(lines), "text": line.split("\n")[0]})
        else:
            why, text = item
            lines.append(text)
            hidden.append({"why": why, "line": len(lines), "text": text})

    return {
        "files": {"app.env": "\n".join(lines) + "\n", "security-rules.md": ENV_RULES},
        "planted": planted, "bait": hidden,
    }


def _gen_spec(rng: random.Random, n_defects: int) -> dict:
    defects = rng.sample(SPEC_DEFECTS, min(n_defects, len(SPEC_DEFECTS)))
    baits = rng.sample(SPEC_BAIT, rng.randint(2, 4))

    lines = ["# Спецификация системы учёта", ""]
    planted, hidden = [], []
    # дата и версия отсутствуют намеренно — это отдельный дефект по п.5
    planted.append({"rule_id": "п.5", "what": "у документа нет даты и версии",
                    "line": 1, "text": lines[0]})
    # заголовок документа тоже без номера - объявляем это явно, иначе
    # находка выглядит как «сверх плана», хотя дефект настоящий
    planted.append({"rule_id": "п.1", "what": "заголовок документа без номера",
                    "line": 1, "text": lines[0]})

    rows = [("defect", d) for d in defects] + [("bait", b) for b in baits]
    rng.shuffle(rows)
    for kind, item in rows:
        if kind == "defect":
            rule, what, tpl = item
            text = tpl.format(system=rng.choice(["склада", "заявок", "отгрузок"]),
                              section=rng.choice(["Требования", "Ограничения", "Порядок работы"]),
                              abbr=rng.choice(["СЭД", "АСУ", "ЕИС", "МЧД"]),
                              days=rng.randint(3, 30))
            for part in text.split("\n"):
                lines.append(part)
            lines.append("")
            planted.append({"rule_id": rule, "what": what,
                            "line": len(lines) - text.count("\n") - 1,
                            "text": text.split("\n")[0]})
        else:
            why, tpl = item
            text = tpl.format(sec=rng.randint(1, 5), fields=rng.randint(5, 12))
            lines.append(text)
            lines.append("")
            hidden.append({"why": why, "line": len(lines) - 1, "text": text})

    return {
        "files": {"spec.md": "\n".join(lines), "checklist.md": SPEC_CHECKLIST},
        "planted": planted, "bait": hidden,
    }


def _gen_parts(rng: random.Random, n_defects: int) -> dict:
    measured = ["деталь,параметр,значение"]
    tolerances = ["деталь,параметр,номинал,допуск_плюс,допуск_минус"]
    planted, hidden = [], []

    names = [f"{rng.choice(PARTS)}-{rng.randint(100, 999)}" for _ in range(rng.randint(3, 5))]
    total_rows = 0
    left = n_defects
    for part in names:
        for param, nominal, tol in rng.sample(PARAMS, rng.randint(1, 3)):
            total_rows += 1
            # округляем допуск ДО расчёта значения: иначе приманка «ровно на
            # границе» после записи в файл с двумя знаками оказывается за ней,
            # и генератор сам создаёт ложную тревогу
            plus = round(tol, 2)
            minus = round(tol / 2, 2) if rng.random() < 0.4 else plus
            make_defect = left > 0 and rng.random() < 0.45
            if make_defect:
                left -= 1
                over = rng.choice([1, -1])
                value = nominal + (plus + tol) if over > 0 else nominal - (minus + tol)
                planted.append({
                    "rule_id": "допуск",
                    "what": f"{part} · {param}: {value:.3f} вне допуска",
                    "line": total_rows + 1, "text": f"{part},{param},{value:.3f}"})
            elif rng.random() < 0.35:
                # приманка: значение ровно на границе — это НЕ брак
                value = round(nominal - minus, 3)
                hidden.append({"why": "значение ровно на нижней границе — не брак",
                               "line": total_rows + 1, "text": f"{part},{param},{value:.3f}"})
            else:
                value = nominal + rng.uniform(-minus * 0.5, plus * 0.5)
                hidden.append({"why": "внутри допуска", "line": total_rows + 1,
                               "text": f"{part},{param},{value:.3f}"})
            measured.append(f"{part},{param},{value:.3f}")
            tolerances.append(f"{part},{param},{nominal:.2f},{plus:.2f},{minus:.2f}")

    return {
        "files": {"measured.csv": "\n".join(measured) + "\n",
                  "tolerances.csv": "\n".join(tolerances) + "\n"},
        "planted": planted, "bait": hidden,
    }


def _gen_pii(rng: random.Random, n_defects: int) -> dict:
    lines = ["Отчёт по обращению."]
    planted, hidden = [], []
    people = rng.sample(NAMES, min(3, n_defects if n_defects > 1 else 2))
    repeat = people[0]

    rows = []
    for first, last in people:
        tpl = rng.choice(PII_TEMPLATES)
        rows.append(("pii", (first, last), tpl))
    # то же лицо второй раз — проверяем, что плейсхолдер будет тот же
    rows.append(("pii", repeat, "Повторный контакт: {name}, добавочный {ext}."))
    for _ in range(rng.randint(1, 2)):
        rows.append(("bait", None, rng.choice(PII_BAIT)))
    rng.shuffle(rows)

    for kind, who, tpl in rows:
        inv = f"{rng.choice(['INV', 'ORD', 'ACT'])}-{rng.randint(1000, 9999)}"
        date = f"{rng.randint(1, 28):02d}.{rng.randint(1, 12):02d}"
        if kind == "pii":
            first, last = who
            text = tpl.format(name=f"{first} {last}", phone=_phone(rng),
                              email=f"{first[0].lower()}.{_translit(last)}@corp.example",
                              ext=rng.randint(100, 999), date=date)
            lines.append(text)
            planted.append({"rule_id": "персональные данные",
                            "what": f"{first} {last} и его контакты должны быть скрыты",
                            "line": len(lines), "text": text})
        else:
            text = tpl.format(inv=inv, date=date)
            lines.append(text)
            hidden.append({"why": f"{inv} и дата — не персональные данные, не трогать",
                           "line": len(lines), "text": text})

    return {"files": {"report.txt": "\n".join(lines) + "\n"},
            "planted": planted, "bait": hidden}


_TR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
       "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
       "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
       "ч": "ch", "ш": "sh", "щ": "sch", "ы": "y", "э": "e", "ю": "yu", "я": "ya",
       "ь": "", "ъ": ""}


def _translit(word: str) -> str:
    return "".join(_TR.get(c, c) for c in word.lower())


KINDS = {
    "config": ("Конфиг сервиса", "app.env и правила безопасности", _gen_env),
    "spec": ("Спецификация", "документ и чеклист из семи пунктов", _gen_spec),
    "parts": ("Замеры деталей", "таблица замеров и таблица допусков", _gen_parts),
    "pii": ("Текст с персональными данными", "отчёт, который уходит наружу", _gen_pii),
}


def generate(kind: str, defects: int = 3, seed: int | None = None) -> dict:
    """Собрать артефакт с известными дефектами.

    -> {files, planted, bait, seed, kind}
    planted - что заложено (должно найтись)
    bait    - приманки (срабатывать нельзя)
    """
    if kind not in KINDS:
        raise ValueError(f"неизвестный вид: {kind}")
    seed = seed if seed is not None else random.randrange(10_000, 99_999)
    rng = random.Random(seed)
    out = KINDS[kind][2](rng, max(1, defects))
    out["seed"] = seed
    out["kind"] = kind
    out["title"] = KINDS[kind][0]
    return out
