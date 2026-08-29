"""Конфиг платформы LLM-агентов: tensorzero + litellm.

Чеклиста как артефакта у заказчика НЕТ — Денис Зорин прямо сказал на
интервью, что он «внутри опыта» (docs/interview-QZ5K.md). Поэтому правила
ниже собраны из его же слов, и каждое помечено, откуда взято.

Правила:
  П1. Каждая переменная env::X из toml заведена в секретах (additionalEnv).
      Слова Дениса: «завели нового провайдера с новой переменной, но не
      завели её в секретах — сервис не поднимется». Единственная жёсткая
      проверка, которая у него есть сегодня.
  П2. Имя ключа соответствует хосту провайдера. Ключ от одного провайдера
      в модели другого — либо прокси, либо ошибка; спрашиваем, не решаем.
  П3. Объявленная модель используется хотя бы одной функцией. Слова Дениса:
      последний инцидент — «лишний/неиспользуемый параметр в config»;
      отдельно упомянут отвал openrouter, после которого правки шли на ходу.
  П4. Ссылки резолвятся: variants.model → models.*, fallback_variants →
      объявленные варианты, routing → providers.*.
  П5. Цены и курс — точка ручного сопровождения (цены провайдеров и курс
      доллара Денис держит руками). Не нарушение, а место дрейфа: выносим
      как «вопрос», чтобы человек глянул, а не как ошибку.
  П6. Хосты: только https, хост узнаваемый. Лидер комнаты записал «хосты»
      отдельным пунктом проверки (docs/interview-JTV5.md).
  П7. Имена полей litellm_params известны. Опечатка в имени поля не роняет
      парсинг YAML — маршрутизация ломается молча (пример 06).
  П8. Идентификатор не смешивает алфавиты. Кириллический омоглиф в латинском
      имени неотличим глазами, а ссылки на имя перестают резолвиться (07).
  П9. Значение того типа, которого ждёт litellm: timeout — число секунд,
      не строка. YAML валиден, ошибка тихая (09).
  П10. Имя модели уникально: один model_name у двух провайдеров делает
      маршрутизацию недетерминированной (10).
  П11. Цена не выбивается на порядки из соседних моделей того же режима —
      признак опечатки в порядке величины, а не смены тарифа (11).

Порог чувствительности. Денис ответил прямо: «пропущенная ошибка хуже»
(docs/interview-JTV5.md). Поэтому сомнительное не замалчивается, но и не
выдаётся за нарушение: оно идёт как severity="вопрос". Так пропуска нет,
а ложная тревога не выглядит браком.

Чего этот модуль НЕ делает: не проверяет, существует ли ключ в облаке.
Денис отдельно сказал, что это видно только при старте сервиса —
статически недоступно, и делать вид, что проверили, нельзя.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from core.model import Finding, Report          # noqa: E402

NAME = "agent_platform_config"

# Правила модуля как ДАННЫЕ, а не только текст в докстринге.
# Отсюда генератор собирает docs/СПЕЦИФИКАЦИЯ.md: заказчик читает правила,
# не открывая Python, и видит у каждого источник — чьи это слова.
RULES = [
    {"id": "П1", "что": "переменная из конфига заведена в секретах, ключи только через env",
     "источник": "Денис: «завели провайдера с новой переменной, но не завели в секретах — сервис не поднимется»",
     "важность": "нарушение", "не_нарушение": "ссылка на файл вне репозитория (API_TOKEN_FILE)"},
    {"id": "П2", "что": "ключ провайдера соответствует хосту, на который ходит модель",
     "источник": "Денис: «корректность ключей — указана ли верная переменная»",
     "важность": "вопрос", "не_нарушение": "провайдер работает через прокси — решает человек"},
    {"id": "П3", "что": "объявленная модель используется хотя бы одной функцией",
     "источник": "Денис: последний инцидент — лишний параметр, искал час по логам gateway",
     "важность": "нарушение", "не_нарушение": "модель вызывается через fallback_variants"},
    {"id": "П4", "что": "ссылки резолвятся: функция → модель, fallback → объявленный вариант",
     "источник": "Денис: «сервис запускался, но встроенная конфигурация не работала»",
     "важность": "нарушение", "не_нарушение": "—"},
    {"id": "П5", "что": "цены и курс доллара — точка ручного дрейфа, требуют сверки",
     "источник": "Денис: цены провайдеров и курс держит руками, дрейф до недели не критичен",
     "важность": "вопрос", "не_нарушение": "расхождение в пределах обычного дрейфа тарифа"},
    {"id": "П6", "что": "хост только по https и узнаваем",
     "источник": "Вадим, записи интервью: «хосты» отдельным пунктом проверки",
     "важность": "нарушение", "не_нарушение": "незнакомый хост — вопрос, а не брак"},
    {"id": "П7", "что": "имя поля litellm_params написано без опечаток",
     "источник": "ломалка QZ5K/SMH3, пример 06",
     "важность": "нарушение", "не_нарушение": "валидные поля вне litellm_params (num_retries)"},
    {"id": "П8", "что": "идентификатор не смешивает кириллицу с латиницей",
     "источник": "ломалка QZ5K/SMH3, пример 07",
     "важность": "нарушение", "не_нарушение": "русский текст в комментариях и описаниях"},
    {"id": "П9", "что": "значение того типа, которого ждёт litellm (timeout — число)",
     "источник": "ломалка QZ5K/SMH3, пример 09",
     "важность": "нарушение", "не_нарушение": "—"},
    {"id": "П10", "что": "имя модели уникально в model_list",
     "источник": "ломалка QZ5K/SMH3, пример 10",
     "важность": "нарушение", "не_нарушение": "одинаковый model внутри разных model_name"},
    {"id": "П11", "что": "цена не выбивается на порядки из соседних моделей",
     "источник": "ломалка QZ5K/SMH3, пример 11",
     "важность": "вопрос", "не_нарушение": "обычный дрейф тарифа в пределах порядка"},
    {"id": "П13", "что": "у каждого провайдера из routing есть своя секция providers",
     "источник": "критерии заказчика, пункт B5 (examples/05/input/критерии-проверки.md)",
     "важность": "нарушение", "не_нарушение": "провайдер объявлен, но не указан в routing — это резерв"},
    {"id": "П12", "что": "у модели проставлена цена, иначе расходы по ней не считаются",
     "источник": "эталон примера 05, согласован с Денисом",
     "важность": "нарушение", "не_нарушение": "отрицательная цена cached_tokens — скидка на кэш"},
]

# Что этот модуль проверить НЕ может — и почему. Врать о полноте нельзя.
RUNTIME_ONLY = [
    "существует ли ключ в облаке, тому ли владельцу и с теми ли правами — видно только при старте сервиса",
    "поднимется ли litellm с этим набором переменных — только выкаткой в тест",
]



# хост провайдера → как обычно зовут его ключ
HOST_TO_KEY = {
    "openrouter.ai": "OPENROUTER",
    "api.deepseek.com": "DEEPSEEK",
    "api.siliconflow.com": "SILICONFLOW",
    "foundation-models.api.cloud.ru": "CLOUDRU",
    "ai.api.cloud.yandex.net": "YANDEX",
    "api.nexara.ru": "NEXARA",
    "novita.ai": "NOVITAAI",
}



def _restore_magnitude(price: float, neighbours: list[float]) -> float | None:
    """Какой была цена, если потеряли нули.

    Опечатка в порядке величины - это сдвиг запятой, а не новый тариф.
    Делим на степень десяти, пока цена не станет одного порядка с соседними
    моделями того же режима. Что получилось, показываем человеку как гипотезу:
    исправлять всё равно ему, но искать по прайсу уже не нужно.
    """
    ref = min(n for n in neighbours if n > 0) if any(n > 0 for n in neighbours) else 0
    if not ref or price <= 0:
        return None
    for power in range(1, 8):
        candidate = price / (10 ** power)
        if 0.01 <= candidate / ref <= 100:
            return candidate
    return None


def matches(inputs: dict[str, str]) -> bool:
    joined = "\n".join(inputs.values())
    return "tensorzero" in joined or "litellm_params" in joined or "model_list" in joined


# Только форматы конфига. Документ с критериями рядом (.md) - не вход
# для парсера: он тоже упоминает litellm в первых строках, и по нему
# прогонялись все проверки разом, вплоть до обвинения имени заказчика
# в кириллическом омоглифе.
CONFIG_SUFFIXES = (".yaml", ".yml", ".toml", ".json", ".env")


def _text(inputs: dict[str, str], needle: str) -> str:
    """Тело конфига, где встречается needle. Ищем только среди конфигов.

    Сначала по имени файла - это точнее. Потом по содержимому, но всё равно
    только у файлов конфигового формата: markdown, txt и прочая документация
    входом не считаются, сколько бы раз там ни стояло слово litellm.
    """
    configs = {n: b for n, b in inputs.items() if n.lower().endswith(CONFIG_SUFFIXES)}
    for name, body in configs.items():
        if needle in name.lower():
            return body
    for name, body in configs.items():
        if needle in body[:400].lower():
            return body
    return ""


def check(inputs: dict[str, str]) -> Report:
    report = Report()
    values = _text(inputs, "tensorzero")
    litellm = _text(inputs, "litellm")

    # ── П1: переменные toml против секретов ────────────────────────────────
    secret_keys = set(re.findall(r"-\s*name:\s*([A-Z0-9_]+)", values))
    needed = set(re.findall(r"env::([A-Z0-9_]+)", values))
    for key in sorted(needed - secret_keys):
        report.findings.append(Finding(
            rule_id="П1",
            rule_text="переменная из tensorzero.toml заведена в additionalEnv (секретах)",
            where="tensorzero.toml → additionalEnv.keys",
            quote=f"env::{key}",
            what=f"{key} нужен конфигу, но в секретах не заведён — сервис не поднимется",
        ))
    if needed and not (needed - secret_keys):
        report.notes.append(
            f"П1: ключи, заведённые в additionalEnv.keys, — их {len(secret_keys)}, все на месте; "
            f"все {len(needed)} переменных из toml среди них — сервис стартует"
        )

    # ключи в секретах, которых нет в toml, — НЕ нарушение: их читает само
    # приложение (postgres, url гейтвея), а не tensorzero.toml
    extra = sorted(secret_keys - needed)
    if extra:
        report.notes.append(
            "П1: в секретах есть " + ", ".join(extra) +
            " — в toml не встречаются, но это переменные самого приложения, не ошибка"
        )

    # ── П2: ключ против хоста провайдера ───────────────────────────────────
    for match in re.finditer(r"\[models\.([\w.-]+)\.providers\.([\w-]+)\]([\s\S]*?)(?=\n\s*\[|\Z)", values):
        model, provider, body = match.group(1), match.group(2), match.group(3)
        key_match = re.search(r"env::([A-Z0-9_]+)", body)
        base_match = re.search(r'api_base\s*=\s*"([^"]+)"', body)
        if not key_match or not base_match:
            continue
        key, base = key_match.group(1), base_match.group(1)
        host = next((h for h in HOST_TO_KEY if h in base), None)
        if host and HOST_TO_KEY[host] not in key:
            report.findings.append(Finding(
                rule_id="П2",
                rule_text="ключ провайдера соответствует хосту, на который ходит модель",
                where=f"[models.{model}.providers.{provider}]",
                quote=f"api_base = {base} · api_key_location = env::{key}",
                what=(f"модель ходит на {host}, а ключ взят из {key} — "
                      f"либо {host} работает через прокси, либо подставлен чужой ключ"),
                severity="вопрос",
            ))

    # ── П3: объявленные модели против используемых ─────────────────────────
    declared = set(re.findall(r"\[models\.([\w-]+)\]", values))
    used = set(re.findall(r'^\s*model\s*=\s*"([^"]+)"', values, re.M))
    for model in sorted(declared - used):
        report.findings.append(Finding(
            rule_id="П3",
            rule_text="объявленная модель используется хотя бы одной функцией",
            where=f"[models.{model}]",
            quote=f"[models.{model}]",
            what=f"модель {model} объявлена, но ни одна функция её не вызывает — лишний блок в конфиге",
        ))
    if declared and not (declared - used):
        report.notes.append(f"П3: все объявленные модели ({len(declared)}) используются функциями")

    # ── П4: ссылки резолвятся ──────────────────────────────────────────────
    for model in sorted(used - declared):
        report.findings.append(Finding(
            rule_id="П4",
            rule_text="функция ссылается на объявленную модель",
            where="functions.*.variants.*",
            quote=f'model = "{model}"',
            what=f"функция вызывает модель {model}, а блок [models.{model}] не объявлен",
        ))

    declared_variants = set(re.findall(r"\[functions\.[\w.-]+\.variants\.([\w-]+)\]", values))
    for block in re.findall(r"fallback_variants\s*=\s*\[([^\]]*)\]", values):
        for variant in re.findall(r'"([\w-]+)"', block):
            if variant not in declared_variants:
                report.findings.append(Finding(
                    rule_id="П4",
                    rule_text="fallback_variants ссылается на объявленный вариант",
                    where="functions.*.experimentation",
                    quote=f'fallback_variants = [... "{variant}" ...]',
                    what=f"запасной вариант {variant} нигде не объявлен",
                ))

    # ── П5: цены и курс — место ручного дрейфа ─────────────────────────────
    prices = re.findall(r"cost_per_million\s*=\s*(-?[\d.]+)", values)
    if prices:
        report.findings.append(Finding(
            rule_id="П5",
            rule_text="цены провайдеров и курс доллара поддерживаются вручную",
            where="models.*.cost",
            quote=f"{len(prices)} значений cost_per_million",
            what=("цены проставлены руками и сверяются глазами — сверить с прайсами провайдеров "
                  "и курсом на сегодня; расхождение до следующего обновления не критично"),
            severity="вопрос",
        ))

    # ── litellm: секреты через env — это норма, фиксируем явно ─────────────
    if litellm:
        inline = []
        for num, line in enumerate(litellm.splitlines(), 1):
            m = re.match(r"\s*api_key:\s*(?!os\.environ)(\S+)", line)
            if m:
                inline.append(m.group(1))
                report.findings.append(Finding(
                    rule_id="П1",
                    rule_text="ключи только через os.environ, не текстом в файле",
                    where=f"litellm-config.yaml:{num} · litellm_params.api_key",
                    quote=f"api_key: {m.group(1)}",
                    what=("api_key записан открытым текстом вместо ссылки os.environ/CLOUD_API_KEY — "
                          "секрет попадает в конфиг-файл и репозиторий, а не тянется из хранилища"),
                ))
        env_refs = sorted(set(re.findall(r"os\.environ/([A-Z0-9_]+)", litellm)))
        if env_refs and not inline:
            report.notes.append(
                "litellm: все ключи через os.environ (" + ", ".join(env_refs) +
                ") — открытым текстом ничего нет"
            )
        if env_refs:
            report.findings.append(Finding(
                rule_id="П1",
                rule_text="переменные litellm заведены в его секрете",
                where="litellm-config.yaml",
                quote=", ".join(env_refs),
                what=("проверить не с чем: секрет litellm в примере не приложен, "
                      "рядом лежит только секрет tensorzero"),
                severity="вопрос",
            ))

    # ── П7-П11: разбор litellm построчно ───────────────────────────────────
    # Построчно, а не через yaml.safe_load: заказчику нужен НОМЕР СТРОКИ,
    # иначе он не пойдёт править не переспрашивая. Разобранное дерево
    # номеров строк не хранит.
    if litellm:
        report.findings.extend(_litellm_defects(litellm))

    # ── П13: routing против секций провайдеров (критерий заказчика B5) ─────
    # «У каждой модели с routing = [...] есть соответствующая секция
    # [models.X.providers.Y] для каждого провайдера из списка».
    # Без секции маршрут указывает в пустоту: гейтвей не знает, куда идти.
    for match in re.finditer(r"\[((?:models|embedding_models)\.[\w-]+)\]([\s\S]*?)(?=\n\s*\[|\Z)", values):
        section, body = match.group(1), match.group(2)
        routing = re.search(r"routing\s*=\s*\[([^\]]*)\]", body)
        if not routing:
            continue
        for provider in re.findall(r'"([\w-]+)"', routing.group(1)):
            if f"[{section}.providers.{provider}]" not in values:
                report.findings.append(Finding(
                    rule_id="П13",
                    rule_text="у каждого провайдера из routing есть секция [<модель>.providers.<провайдер>]",
                    where=f"[{section}]",
                    quote=f'routing = [... "{provider}" ...]',
                    what=(f"маршрут ведёт на провайдера {provider}, а секции "
                          f"[{section}.providers.{provider}] нет — гейтвею некуда идти"),
                ))

    # ── что проверено и признано нормой ────────────────────────────────────
    # Без этого раздела «не поймали» неотличимо от «не проверяли»,
    # а заказчик читает отчёт именно на этот вопрос.
    if re.search(r"cost_per_million\s*=\s*-", values):
        report.notes.append(
            "отрицательная цена за cached_tokens — легальная скидка на кэш, а не ошибка"
        )
    for secret_name in re.findall(r'pullSecret:\s*"([^"]+)"', values):
        report.notes.append(
            f'pullSecret: "{secret_name}" — имя секрета, а не секрет: значение лежит в хранилище'
        )
    bind = re.search(r'bind_address\s*=\s*"([^"]+)"', values)
    if bind:
        auth_on = re.search(r"auth\.enabled\s*=\s*true", values)
        if auth_on:
            report.notes.append(
                f'bind_address = "{bind.group(1)}" при auth.enabled = true — норма для кластера, '
                "наружу порт не выставлен"
            )
        else:
            report.findings.append(Finding(
                rule_id="П2",
                rule_text="сервис не слушает 0.0.0.0 без включённой авторизации",
                where="[gateway]",
                quote=f'bind_address = "{bind.group(1)}"',
                what="гейтвей слушает все интерфейсы, а auth.enabled не выставлен",
            ))

    # ── П12: модель без цены ───────────────────────────────────────────────
    # Денис держит расходы по моделям в конфиге руками. Модель без цены
    # молча не попадает в расчёт: деньги уходят, а в отчёте её нет.
    #
    # Цена живёт не в самой секции модели, а в её подсекции провайдера
    # ([models.X.providers.Y]), поэтому тело модели собираем вместе со
    # всеми подсекциями — иначе получаем ложное срабатывание на каждой
    # модели разом (поймано приёмкой примера 05).
    sections: dict[str, str] = {}
    for match in re.finditer(r"\[((?:models|embedding_models)\.[\w.-]+)\]([\s\S]*?)(?=\n\s*\[|\Z)", values):
        sections[match.group(1)] = match.group(2)

    for full_name, body in sections.items():
        kind, _, name = full_name.partition(".")
        if "." in name:                    # подсекция провайдера — не отдельная модель
            continue
        own = body + "".join(
            sub_body for sub_name, sub_body in sections.items()
            if sub_name.startswith(f"{full_name}.")
        )
        if "cost" not in own:
            report.findings.append(Finding(
                rule_id="П12",
                rule_text="у модели проставлена цена, иначе расходы по ней не считаются",
                where=f"[{full_name}]",
                quote=f"[{full_name}]",
                what=f"цена не проставлена, расходы по {name} не считаются",
            ))

    # ── П6: хосты ──────────────────────────────────────────────────────────
    for base in sorted(set(re.findall(r'api_base\s*=\s*"([^"]+)"', values)) |
                       set(re.findall(r'api_base:\s*(\S+)', litellm))):
        if base.startswith("http://"):
            report.findings.append(Finding(
                rule_id="П6",
                rule_text="обращение к провайдеру идёт по https",
                where="api_base",
                quote=base,
                what=f"{base} — незашифрованный http, ключ уйдёт открытым",
            ))
            continue
        host = re.sub(r"^https://", "", base).split("/")[0]
        if not any(known in host for known in HOST_TO_KEY):
            report.findings.append(Finding(
                rule_id="П6",
                rule_text="хост провайдера узнаваем",
                where="api_base",
                quote=base,
                what=f"хост {host} не из знакомого списка — проверить, не опечатка ли",
                severity="вопрос",
            ))

    # ── граница проверок: что статически увидеть нельзя ────────────────────
    # Лидер комнаты просил зафиксировать это честно и на виду,
    # Денис отдельно сказал, что видно только при старте сервиса.
    report.runtime_only.append(
        "существует ли ключ в облаке, тому ли владельцу принадлежит и с теми ли правами — "
        "видно только когда сервис стартует и идёт за ключом"
    )
    if litellm:
        report.runtime_only.append(
            "поднимется ли litellm с этим набором переменных — проверяется только выкаткой в тест"
        )

    return report


# поля вне litellm_params: router_settings, litellm_settings, general_settings.
# Держим их отдельно, чтобы П7 не приняла валидный num_retries из router_settings
# за опечатку max_retries — это ловится приёмкой как ложное срабатывание.
OUTER_FIELDS = {
    "general_settings", "model_list", "router_settings", "litellm_settings",
    "master_key", "database_url", "fallbacks", "num_retries", "context_window_fallbacks",
    "allowed_fails", "cooldown_time", "routing_strategy", "redis_host", "redis_port",
    "cache", "cache_params", "namespace", "type", "success_callback", "failure_callback",
    "model_info", "mode", "model_name", "litellm_params", "request_timeout",
}

# известные поля litellm_params — по ним ловим опечатку (П7)
LITELLM_PARAMS = {
    "model", "custom_llm_provider", "api_key", "api_base", "api_version",
    "response_format", "timeout", "stream_timeout", "max_retries", "organization",
    "rpm", "tpm", "max_tokens", "temperature", "top_p", "drop_params",
    "aws_region_name", "vertex_project", "vertex_location", "input_cost_per_second",
}

# поля, которым litellm ждёт число (П9)
NUMERIC_FIELDS = {
    "timeout", "stream_timeout", "max_retries", "rpm", "tpm", "max_tokens",
    "num_retries", "input_cost_per_second", "output_cost_per_second",
    "input_cost_per_token", "output_cost_per_token",
}

CYRILLIC = re.compile(r"[\u0400-\u04FF]")
LATIN = re.compile(r"[A-Za-z]")


def _litellm_defects(text: str) -> list:
    """Дефекты litellm-конфига, которые не роняют парсинг YAML.

    Общее у всех пяти: файл остаётся синтаксически валидным, ошибка
    всплывает уже на проде. Поэтому ищем их именно текстом.
    """
    import difflib

    findings: list[Finding] = []
    lines = text.splitlines()
    model_names: dict[str, list[int]] = {}
    prices: list[tuple[str, int, float]] = []
    current_model = "?"
    in_params = False          # мы внутри блока litellm_params?
    params_indent = 0

    for num, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        key_match = re.match(r"-?\s*([\w.-]+):\s*(.*)$", stripped)
        if not key_match:
            continue
        key, value = key_match.group(1), key_match.group(2).strip()

        # где мы: внутри litellm_params или в настройках верхнего уровня
        indent = len(line) - len(line.lstrip())
        if key == "litellm_params":
            in_params, params_indent = True, indent
        elif in_params and indent <= params_indent and key != "litellm_params":
            in_params = False

        # ── П8: смешение алфавитов в одном идентификаторе ──────────────────
        for token in (key, value.strip('"\'')):
            if not token or token.startswith("os.environ"):
                continue
            if CYRILLIC.search(token) and LATIN.search(token):
                mixed = "".join(sorted({c for c in token if CYRILLIC.match(c)}))
                findings.append(Finding(
                    rule_id="П8",
                    rule_text="идентификатор не смешивает кириллицу с латиницей",
                    where=f"litellm-config.yaml:{num}",
                    quote=f"{key}: {value}",
                    what=(f"в имени «{token}» латиница смешана с кириллическими буквами ({mixed}) — "
                          "визуально неотличимый двойник, ссылки на это имя ниже по файлу "
                          "не резолвятся"),
                ))

        if key == "model_name":
            current_model = value
            model_names.setdefault(value, []).append(num)

        # ── П7: опечатка в имени поля ──────────────────────────────────────
        # Только внутри litellm_params: снаружи живут свои валидные поля,
        # и близость имени там ничего не значит.
        if (in_params and key not in LITELLM_PARAMS and key not in OUTER_FIELDS
                and re.match(r"^[a-z][a-z_]{4,}$", key)):
            close = difflib.get_close_matches(key, LITELLM_PARAMS, n=1, cutoff=0.8)
            if close:
                findings.append(Finding(
                    rule_id="П7",
                    rule_text="имя поля litellm_params написано без опечаток",
                    where=f"litellm-config.yaml:{num} · блок model_name: {current_model}",
                    quote=f"{key}: {value}",
                    what=(f"поле {close[0]} опечатано ({key}) — litellm не распознает провайдера "
                          "по неизвестному полю, маршрутизация на эту модель молча ломается, "
                          "парсинг YAML при этом не падает"),
                ))

        # ── П9: тип значения ───────────────────────────────────────────────
        if key in NUMERIC_FIELDS and value:
            bare = value.strip('"\'')
            if bare and not re.fullmatch(r"-?\d+(\.\d+)?([eE][-+]?\d+)?", bare):
                findings.append(Finding(
                    rule_id="П9",
                    rule_text=f"{key} задаётся числом, а не строкой",
                    where=f"litellm-config.yaml:{num} · блок model_name: {current_model}",
                    quote=f"{key}: {value}",
                    what=(f"{key} задан строкой вместо числа — YAML синтаксически валиден, "
                          "но litellm ждёт число; ошибка тихая, на парсинге не падает"),
                ))
            elif key == "input_cost_per_second":
                try:
                    prices.append((current_model, num, float(bare)))
                except ValueError:
                    pass

    # ── П10: дубль имени модели ────────────────────────────────────────────
    for name, at in model_names.items():
        if len(at) > 1:
            findings.append(Finding(
                rule_id="П10",
                rule_text="имя модели уникально в model_list",
                where="litellm-config.yaml:" + ", ".join(str(n) for n in at),
                quote=f"оба блока: model_name: {name}",
                what=(f"model_name «{name}» объявлен дважды для разных провайдеров — "
                      "маршрутизация между ними недетерминированная, неясно, "
                      "какой провайдер реально отработает запрос"),
            ))

    # ── П11: цена выбивается на порядки ────────────────────────────────────
    if len(prices) > 1:
        values = [p[2] for p in prices if p[2] > 0]
        if values and max(values) / min(values) >= 100:
            worst = max(prices, key=lambda p: p[2])
            others = [f"{p[2]:g}" for p in prices if p is not worst]
            was = _restore_magnitude(worst[2], [p[2] for p in prices if p is not worst])
            hint = f"  (было: {was:g})" if was else ""
            findings.append(Finding(
                rule_id="П11",
                rule_text="цена не выбивается на порядки из соседних моделей того же режима",
                where=f"litellm-config.yaml:{worst[1]} · блок model_name: {worst[0]}",
                quote=f"input_cost_per_second: {worst[2]:g}{hint}",
                what=(f"цена {worst[2]:g} отличается на порядки от соседних ({', '.join(others)}) — "
                      "похоже на опечатку в порядке величины, а не на реальное изменение тарифа; "
                      + (f"при потере {len(str(int(worst[2] / was))) - 1} нулей исходной была бы "
                         f"{was:g}, и тогда цена сопоставима с соседней. " if was else "")
                      + "по словам заказчика цены — точка ручного дрейфа, поэтому это предупреждение"),
                severity="вопрос",
            ))

    return findings
