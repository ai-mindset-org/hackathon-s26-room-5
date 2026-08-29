#!/usr/bin/env python3
"""Генератор эталонных «сломанных» примеров litellm-конфига.

Не завязан на конкретный файл Дениса — мутации ищут паттерны (regex) в любом
litellm-config.yaml похожей формы (model_list → litellm_params/model_info) и
описывают найденное в expected.md динамически, по факту найденного и
делают конкретную мутацию, а не по прописанным заранее значениям из одного
файла. Дефолтный вход — examples/05-конфиг-платформы-агентов/ (от Дениса),
но им же можно скормить любой другой litellm-config.yaml через --config.

Каждый дефект — отдельный examples/<N>-.../ с input/ и expected.md, в
формате комнаты (examples/README.md).

Запуск:
  python3 tools/config-mutator/generate.py
  python3 tools/config-mutator/generate.py --config path/to/other.yaml --out-prefix 20
"""

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG = ROOT / "examples/05-конфиг-платформы-агентов/input/litellm-config.yaml"

# Кириллические буквы, визуально неотличимые от латинских в большинстве шрифтов.
CYRILLIC_LOOKALIKES = {"c": "с", "o": "о", "e": "е", "a": "а", "p": "р", "x": "х"}


class MutationSkipped(Exception):
    """Паттерн мутации не найден в данном конфиге — пропускаем кейс."""


def to_cyrillic(word: str) -> str:
    return "".join(CYRILLIC_LOOKALIKES.get(ch, ch) for ch in word)


# ── каждая мутация: (text) -> (mutated_text, детали для expected.md) ────────

def mutate_typo_provider_field(text: str) -> tuple[str, dict]:
    match = re.search(r"^(\s*)custom_llm_provider(:\s*\S+)$", text, re.M)
    if not match:
        raise MutationSkipped
    indent, rest = match.group(1), match.group(2)
    mutated = text[:match.start()] + f"{indent}custom_llm_provder{rest}" + text[match.end():]
    return mutated, {
        "title": "Опечатка в поле custom_llm_provider",
        "where": "первый попавшийся блок litellm_params",
        "quote": f"custom_llm_provder{rest.strip()}",
        "what": (
            "поле custom_llm_provider опечатано (custom_llm_provder) — litellm "
            "не распознает провайдера по неизвестному полю; маршрутизация на эту "
            "модель молча ломается, парсинг YAML при этом не падает"
        ),
    }


def mutate_cyrillic_model_name(text: str) -> tuple[str, dict]:
    match = re.search(r"^(\s*-\s*model_name:\s*)([\w.-]+)\s*$", text, re.M)
    if not match:
        raise MutationSkipped
    original_name = match.group(2)
    if original_name not in text[match.end():]:
        # имя больше нигде не встречается (нет fallback/другой ссылки на него) —
        # тогда дефект не будет наблюдаемым, кейс бессмысленный
        raise MutationSkipped
    mutated_name = to_cyrillic(original_name)
    if mutated_name == original_name:
        raise MutationSkipped
    mutated = text[:match.start()] + match.group(1) + mutated_name + text[match.end():]
    return mutated, {
        "title": "Кириллический омоглиф в имени модели",
        "where": "model_list[0].model_name против ссылок на это имя ниже по файлу",
        "quote": f"model_name: {mutated_name}  (было: {original_name})",
        "what": (
            f"имя модели заменено на визуально неотличимый двойник с кириллицей "
            f"({mutated_name!r} вместо {original_name!r}); все ссылки на "
            f"{original_name!r} ниже по файлу (fallback и т.п.) не резолвятся — "
            f"строки выглядят одинаково глазами, но различаются кодировкой символов"
        ),
    }


def mutate_inline_secret(text: str) -> tuple[str, dict]:
    match = re.search(r"^(\s*)api_key:\s*os\.environ/(\w+)\s*$", text, re.M)
    if not match:
        raise MutationSkipped
    indent, var_name = match.group(1), match.group(2)
    fake_key = "sk-live-a1b2c3d4e5f6"
    mutated = text[:match.start()] + f"{indent}api_key: {fake_key}" + text[match.end():]
    return mutated, {
        "title": "Ключ записан открытым текстом вместо os.environ",
        "where": "первый найденный litellm_params.api_key",
        "quote": f"api_key: {fake_key}",
        "what": (
            f"api_key записан открытым текстом вместо ссылки os.environ/{var_name} — "
            "секрет попадает в конфиг-файл/репозиторий, а не тянется из хранилища. "
            "Контрольный кейс: единственный из набора, который уже должен ловить "
            "checkers/agent_platform_config/checker.py (правило П1)"
        ),
    }


def mutate_timeout_type(text: str) -> tuple[str, dict]:
    match = re.search(r"^(\s*timeout:\s*)(\d+)\s*$", text, re.M)
    if not match:
        raise MutationSkipped
    prefix, value = match.group(1), match.group(2)
    mutated = text[:match.start()] + f'{prefix}"{value}s"' + text[match.end():]
    return mutated, {
        "title": "Таймаут строкой вместо числа",
        "where": "первый найденный litellm_params.timeout",
        "quote": f'timeout: "{value}s"  (было число: {value})',
        "what": (
            "timeout задан строкой вместо числа секунд — YAML синтаксически "
            "валиден, но litellm ждёт число; типовая «тихая» ошибка, которая не "
            "падает на этапе парсинга конфига"
        ),
    }


def mutate_duplicate_model_name(text: str) -> tuple[str, dict]:
    names = re.findall(r"^\s*-\s*model_name:\s*([\w.-]+)\s*$", text, re.M)
    if len(names) < 2:
        raise MutationSkipped
    first_name, second_name = names[0], names[1]
    # заменяем второе вхождение имени на первое
    pattern = re.compile(rf"^(\s*-\s*model_name:\s*){re.escape(second_name)}\s*$", re.M)
    mutated, count = pattern.subn(rf"\g<1>{first_name}", text, count=1)
    if count == 0:
        raise MutationSkipped
    return mutated, {
        "title": "Дублирующееся имя модели у двух разных провайдеров",
        "where": "model_list[0].model_name и model_list[1].model_name",
        "quote": f"оба блока: model_name: {first_name}  (второй был: {second_name})",
        "what": (
            f"model_name {first_name!r} объявлен дважды для разных провайдеров — "
            "маршрутизация между ними становится недетерминированной, неясно, "
            "какой провайдер реально отработает запрос"
        ),
    }


def mutate_inflated_price(text: str) -> tuple[str, dict]:
    match = re.search(r"^(\s*input_cost_per_second:\s*)([\d.]+)\s*$", text, re.M)
    if not match:
        raise MutationSkipped
    prefix, value = match.group(1), match.group(2)
    inflated = float(value) * 1000
    mutated = text[:match.start()] + f"{prefix}{inflated}" + text[match.end():]
    return mutated, {
        "title": "Цена модели на порядки выше реальной (стухший тариф)",
        "where": "первый найденный model_info.input_cost_per_second",
        "quote": f"input_cost_per_second: {inflated}  (было: {value})",
        "what": (
            f"цена выросла в 1000 раз ({value} → {inflated}) — похоже на опечатку "
            "в порядке величины, а не на реальное изменение тарифа провайдера. "
            "НЕ жёсткое нарушение (по словам Дениса цены — точка ручного дрейфа), "
            "но расхождение на порядки достойно как минимум предупреждения, в "
            "отличие от обычного дрейфа тарифа"
        ),
    }


YAML_MUTATIONS = [
    ("опечатка-в-провайдере", mutate_typo_provider_field),
    ("кириллица-омоглиф", mutate_cyrillic_model_name),
    ("секрет-в-открытую", mutate_inline_secret),
    ("неверный-тип-таймаута", mutate_timeout_type),
    ("дублирующаяся-модель", mutate_duplicate_model_name),
    ("устаревшая-цена", mutate_inflated_price),
]

# Обратная совместимость: старые вызовы кода/тестов ждали имя MUTATIONS.
MUTATIONS = YAML_MUTATIONS


# ── мутации для tensorzero.toml (внутри k8s test-values.yaml) ───────────────
#
# По прямой просьбе заказчика (Дениса) — не произвольные баги, а по одному
# на каждый жёсткий пункт его же чек-листа (examples/05-.../input/
# критерии-проверки.md, он же checkers/agent_platform_config/checker.py:
# П1, П2, П3, П4, П6). П5 (цены/курс) сюда не входит — заказчик сам считает
# это не нарушением, а точкой ручного дрейфа, ломать тут нечего.
#
# Каждая мутация — одна точечная правка (одно значение), не разгром файла:
# заказчик прямо просил не ломать конфиг «прям совсем».

def mutate_toml_secret_missing(text: str) -> tuple[str, dict]:
    """П1: ссылка env::VAR есть в toml, а сам VAR убран из additionalEnv.keys."""
    env_vars = re.findall(r"env::([A-Z0-9_]+)", text)
    if not env_vars:
        raise MutationSkipped
    target = env_vars[0]
    pattern = re.compile(
        rf"^[ \t]*-\s*name:\s*{re.escape(target)}\s*\n[ \t]*key:\s*{re.escape(target)}\s*\n",
        re.M,
    )
    mutated, count = pattern.subn("", text, count=1)
    if count == 0:
        raise MutationSkipped
    return mutated, {
        "title": f"Секрет {target} убран из additionalEnv (П1)",
        "where": "gateway.additionalEnv.keys",
        "quote": f"env::{target}",
        "what": (
            f"tensorzero.toml ссылается на env::{target}, но запись в "
            f"additionalEnv.keys удалена — переменная нигде не заведена, "
            f"сервис не поднимется. Правило П1, единственная сегодня жёсткая "
            f"проверка у заказчика."
        ),
    }


def mutate_toml_wrong_provider_key(text: str) -> tuple[str, dict]:
    """П2: ключ одного провайдера подставлен в блок другого.

    Это не выдуманный класс ошибки — ровно так был найден реальный баг в
    боевом конфиге заказчика (examples/05: yandex-модель с NOVITAAI_API_KEY).
    """
    blocks = list(re.finditer(
        r"\[models\.[\w.-]+\.providers\.[\w-]+\]([\s\S]*?)(?=\n\s*\[|\Z)", text
    ))
    found = [(m, km.group(1)) for m in blocks
             if (km := re.search(r"env::([A-Z0-9_]+)", m.group(1)))]
    distinct = [(m, key) for m, key in found if key != found[0][1]]
    if not distinct:
        raise MutationSkipped
    target_match, target_key = found[0]
    _, intruder_key = distinct[0]
    start, end = target_match.span(1)
    mutated_body = target_match.group(1).replace(f"env::{target_key}", f"env::{intruder_key}", 1)
    mutated = text[:start] + mutated_body + text[end:]
    return mutated, {
        "title": f"Ключ другого провайдера ({intruder_key}) подставлен вместо {target_key} (П2)",
        "where": "models.*.providers.* → api_key_location",
        "quote": f"env::{intruder_key}",
        "what": (
            f"модель берёт ключ {intruder_key}, а исходно использовала "
            f"{target_key} — либо осознанный прокси, либо перепутанный ключ "
            f"при copy-paste. Правило П2: сомнительно, но не всегда ошибка — "
            f"это «вопрос», не жёсткое нарушение."
        ),
    }


def mutate_toml_unused_model(text: str) -> tuple[str, dict]:
    """П3: объявлена модель, которую не вызывает ни одна функция."""
    match = re.search(r"^(\s*)\[functions\.", text, re.M)
    if not match:
        raise MutationSkipped
    indent = match.group(1)
    ghost = (
        f"{indent}[models.ghost-unused-model]\n"
        f'{indent}routing = ["ghost"]\n'
        f"{indent}[models.ghost-unused-model.providers.ghost]\n"
        f'{indent}type = "openai"\n'
        f'{indent}api_base = "https://api.deepseek.com"\n'
        f'{indent}model_name = "ghost-model"\n'
        f'{indent}api_key_location = "env::DEEPSEEK_API_KEY"\n\n'
    )
    mutated = text[:match.start()] + ghost + text[match.start():]
    return mutated, {
        "title": "Модель объявлена, но не используется ни одной функцией (П3)",
        "where": "models.ghost-unused-model",
        "quote": "[models.ghost-unused-model]",
        "what": (
            "блок модели добавлен, но ни функция его не вызывает — лишний "
            "блок в конфиге, ровно тот тип проблемы, что был в реальном "
            "инциденте заказчика с лишним параметром. Правило П3."
        ),
    }


def mutate_toml_broken_function_ref(text: str) -> tuple[str, dict]:
    """П4: functions.*.variants.*.model ссылается на необъявленную модель."""
    match = re.search(r'^(\s*model\s*=\s*")([\w.-]+)(")\s*$', text, re.M)
    if not match:
        raise MutationSkipped
    original = match.group(2)
    broken = original + "-missing"
    mutated = text[:match.start()] + match.group(1) + broken + match.group(3) + text[match.end():]
    return mutated, {
        "title": f"Функция ссылается на необъявленную модель {broken} (П4)",
        "where": "functions.*.variants.* → model",
        "quote": f'model = "{broken}"',
        "what": (
            f"вариант функции вызывает модель {broken}, а блок "
            f"[models.{broken}] нигде не объявлен — битая ссылка. Правило П4."
        ),
    }


def mutate_toml_insecure_host(text: str) -> tuple[str, dict]:
    """П6: обращение к провайдеру идёт по http вместо https."""
    match = re.search(r'api_base\s*=\s*"https://([^"]+)"', text)
    if not match:
        raise MutationSkipped
    old = match.group(0)
    new = old.replace("https://", "http://", 1)
    mutated = text.replace(old, new, 1)
    return mutated, {
        "title": "Обращение к провайдеру по http вместо https (П6)",
        "where": "models.*.providers.* → api_base",
        "quote": f"http://{match.group(1)}",
        "what": (
            f"хост {match.group(1)} указан по http — ключ и запросы уходят "
            "незашифрованными. Правило П6."
        ),
    }


TOML_MUTATIONS = [
    ("секрет-не-в-env", mutate_toml_secret_missing),
    ("чужой-ключ-провайдера", mutate_toml_wrong_provider_key),
    ("неиспользуемая-модель", mutate_toml_unused_model),
    ("битая-ссылка-функции", mutate_toml_broken_function_ref),
    ("http-вместо-https", mutate_toml_insecure_host),
]


def is_toml_config(text: str) -> bool:
    """Отличаем tensorzero.toml (внутри test-values.yaml) от litellm-config.yaml."""
    return "tensorzero.toml" in text or bool(re.search(r"^\s*\[models\.", text, re.M))


def build_expected_md(details: dict) -> str:
    return (
        f"# Ожидаемый отчёт\n\n"
        f"Нарушение: {details['title']}.\n\n"
        f"Место: {details['where']}.\n\n"
        f"Цитата: `{details['quote']}`\n\n"
        f"Что не так: {details['what']}\n\n"
        f"Ключевая проверка: инструмент должен указать именно это место и "
        f"процитировать именно это значение — не общий «конфиг не соответствует».\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                         help="litellm-config.yaml, который ломаем (по умолчанию — пример Дениса)")
    parser.add_argument("--out-prefix", type=int, default=6,
                         help="с какого номера начинать examples/<N>-... (по умолчанию 6)")
    args = parser.parse_args()

    base_text = args.config.read_text(encoding="utf-8")
    mutations = TOML_MUTATIONS if is_toml_config(base_text) else YAML_MUTATIONS

    # Файл правил, по которым живёт этот конфиг, лежит рядом с ним.
    # Кладём копию в каждый сгенерированный кейс: правила должны ехать
    # с артефактом, а не оставаться знанием в головах (решение комнаты).
    rules_src = args.config.parent / "критерии-проверки.md"

    written, skipped = 0, []
    for offset, (slug_suffix, mutate_fn) in enumerate(mutations):
        try:
            mutated_text, details = mutate_fn(base_text)
        except MutationSkipped:
            skipped.append(slug_suffix)
            continue

        n = args.out_prefix + offset
        case_dir = ROOT / "examples" / f"{n:02d}-конфиг-{slug_suffix}"
        input_dir = case_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        (input_dir / args.config.name).write_text(mutated_text, encoding="utf-8")
        if rules_src.is_file():
            (input_dir / rules_src.name).write_text(
                rules_src.read_text(encoding="utf-8"), encoding="utf-8")
        (case_dir / "expected.md").write_text(build_expected_md(details), encoding="utf-8")
        print(f"написано: examples/{case_dir.name}/")
        written += 1

    if skipped:
        print(f"пропущено (паттерн не найден во входном файле): {', '.join(skipped)}")
    print(f"итого сгенерировано кейсов: {written}/{len(mutations)}")


if __name__ == "__main__":
    main()
