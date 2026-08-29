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


def matches(inputs: dict[str, str]) -> bool:
    joined = "\n".join(inputs.values())
    return "tensorzero" in joined or "litellm_params" in joined or "model_list" in joined


def _text(inputs: dict[str, str], needle: str) -> str:
    for name, body in inputs.items():
        if needle in name.lower() or needle in body[:400].lower():
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
            f"П1: все переменные toml заведены в секретах ({len(needed)} шт.) — сервис стартует"
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
                where=f"models.{model}.providers.{provider}",
                quote=f'api_base = "{base}" · api_key_location = "env::{key}"',
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
            where=f"models.{model}",
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
        inline = re.findall(r"api_key:\s*(?!os\.environ)(\S+)", litellm)
        for value in inline:
            report.findings.append(Finding(
                rule_id="П1",
                rule_text="ключи только через os.environ, не текстом в файле",
                where="litellm model_list",
                quote=f"api_key: {value}",
                what="ключ записан в файл открытым текстом",
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

    return report
