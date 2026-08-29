"""Сверка цен в конфиге с прайсом провайдера и курсом ЦБ — критерий C8.

    python3 tools/prices/check.py examples/05-конфиг-платформы-агентов
    python3 tools/prices/check.py <папка> --offline    # без сети, только разбор

Критерий заказчика (examples/05/input/критерии-проверки.md, пункт C8):
«подтянуть актуальную цену с публичной страницы/документации провайдера;
для рублёвых провайдеров конвертировать по курсу ЦБ РФ (cbr.ru); сравнить
с ценой в конфиге. Расхождение > 5% — нарушение, ≤ 5% — норма (дрейф)».

ПОЧЕМУ ОТДЕЛЬНАЯ КОМАНДА, А НЕ ЧАСТЬ ПРИЁМКИ. Здесь единственное место
инструмента, которое ходит в сеть. Прогон examples/ обязан быть
воспроизводимым: сегодня прайс один, завтра другой, и приёмка начала бы
краснеть от чужих тарифов, а не от наших ошибок.

ГЛАВНОЕ ПРАВИЛО. Не дозвонились до источника — это НЕ «цена в порядке».
Это «сверки не было», отдельной строкой. Инструмент, который молча
не достучался и написал «всё хорошо», хуже, чем его отсутствие.
"""

import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
THRESHOLD = 0.05          # порог из критерия C8
TIMEOUT = 10

# хост провайдера → как тянуть прайс
RUBLE_HOSTS = ("cloud.ru", "yandex.net", "nexara.ru", ".ru/")


def fetch(url: str, timeout: int = TIMEOUT) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


def usd_rate() -> tuple[float, str] | None:
    """Курс доллара ЦБ РФ. None — источник недоступен, не «курс = 1»."""
    raw = fetch(CBR_URL)
    if raw is None:
        return None
    try:
        root = ET.fromstring(raw.decode("windows-1251"))
    except (ET.ParseError, UnicodeDecodeError):
        return None
    for valute in root.findall("Valute"):
        if valute.findtext("CharCode") == "USD":
            value = float(valute.findtext("Value", "0").replace(",", "."))
            nominal = float(valute.findtext("Nominal", "1"))
            if nominal:
                return value / nominal, root.get("Date", "?")
    return None


def openrouter_prices() -> dict[str, dict[str, float]] | None:
    """Прайс OpenRouter: id модели → цена за миллион токенов."""
    raw = fetch(OPENROUTER_URL)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    prices = {}
    for model in data.get("data", []):
        pricing = model.get("pricing") or {}
        try:
            prices[model["id"]] = {
                "prompt": float(pricing.get("prompt", 0)) * 1_000_000,
                "completion": float(pricing.get("completion", 0)) * 1_000_000,
            }
        except (TypeError, ValueError):
            continue
    return prices


def parse_config(text: str) -> list[dict]:
    """Модели с ценами: имя, провайдер, хост, model_name, цены за миллион."""
    found = []
    for match in re.finditer(
        r"\[models\.([\w-]+)\.providers\.([\w-]+)\]([\s\S]*?)(?=\n\s*\[|\Z)", text
    ):
        model, provider, body = match.group(1), match.group(2), match.group(3)
        costs = {}
        for pointer, value in re.findall(
            r'\{pointer\s*=\s*"([^"]+)"[^}]*cost_per_million\s*=\s*(-?[\d.]+)', body
        ):
            if pointer.endswith("prompt_tokens"):
                costs["prompt"] = float(value)
            elif pointer.endswith("completion_tokens"):
                costs["completion"] = float(value)
        if not costs:
            continue
        found.append({
            "model": model,
            "provider": provider,
            "api_base": (re.search(r'api_base\s*=\s*"([^"]+)"', body) or [None, ""])[1]
            if re.search(r'api_base\s*=\s*"([^"]+)"', body) else "",
            "model_name": (re.search(r'model_name\s*=\s*"([^"]+)"', body).group(1)
                           if re.search(r'model_name\s*=\s*"([^"]+)"', body) else ""),
            "costs": costs,
        })
    return found


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    offline = "--offline" in argv
    if not args:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2

    target = Path(args[0])
    root = target / "input" if (target / "input").is_dir() else target
    text = "\n".join(
        f.read_text(encoding="utf-8", errors="ignore")
        for f in sorted(root.rglob("*"))
        if f.is_file() and f.suffix in (".yaml", ".yml", ".toml")
    ) if root.is_dir() else target.read_text(encoding="utf-8")

    entries = parse_config(text)
    print(f"# Сверка цен · критерий C8 · порог {THRESHOLD:.0%}\n")
    if not entries:
        print("Моделей с проставленной ценой не найдено — сверять нечего.")
        return 0

    rate = None if offline else usd_rate()
    prices = None if offline else openrouter_prices()

    if offline:
        print("Режим --offline: в сеть не ходим, сверки не было.\n")
    else:
        print(f"Курс ЦБ: {'USD = %.4f ₽ на %s' % rate if rate else '⚠ НЕДОСТУПЕН'}")
        print(f"Прайс OpenRouter: {'%d моделей' % len(prices) if prices else '⚠ НЕДОСТУПЕН'}\n")

    violations = unchecked = ok = 0
    for entry in entries:
        title = f"{entry['model']} · {entry['provider']}"
        is_ruble = any(host in entry["api_base"] for host in RUBLE_HOSTS)

        if "openrouter.ai" in entry["api_base"]:
            if prices is None:
                print(f"⚠ {title}: прайс OpenRouter недоступен — СВЕРКИ НЕ БЫЛО")
                unchecked += 1
                continue
            actual = prices.get(entry["model_name"])
            if actual is None:
                print(f"⚠ {title}: модели «{entry['model_name']}» нет в прайсе — СВЕРКИ НЕ БЫЛО")
                unchecked += 1
                continue
            for kind, in_config in entry["costs"].items():
                real = actual.get(kind, 0)
                if real <= 0:
                    print(f"⚠ {title} · {kind}: у провайдера цена 0 — СВЕРКИ НЕ БЫЛО")
                    unchecked += 1
                    continue
                delta = (in_config - real) / real
                if abs(delta) > THRESHOLD:
                    print(f"✗ {title} · {kind}: в конфиге {in_config:g}, "
                          f"у провайдера {real:.5f} за миллион — расхождение {delta:+.1%}")
                    violations += 1
                else:
                    print(f"✓ {title} · {kind}: {in_config:g} против {real:.5f} — {delta:+.1%}, в пределах порога")
                    ok += 1

        elif is_ruble:
            if rate is None:
                print(f"⚠ {title}: курс ЦБ недоступен — СВЕРКИ НЕ БЫЛО")
                unchecked += 1
                continue
            pairs = ", ".join(
                f"{kind} {value:g} ≈ {value / rate[0]:.4f} $" if value else f"{kind} 0"
                for kind, value in entry["costs"].items()
            )
            print(f"? {title}: рублёвый провайдер, {pairs} по курсу {rate[0]:.4f} ₽. "
                  f"Публичного прайса не тянем — подтвердить у заказчика, рубли ли в конфиге")
            unchecked += 1

        else:
            print(f"⚠ {title}: публичный прайс для {entry['api_base'] or 'неизвестного хоста'} "
                  f"не подключён — СВЕРКИ НЕ БЫЛО")
            unchecked += 1

    print(f"\nИтог: расхождений сверх порога {violations} · в пределах порога {ok} · "
          f"НЕ СВЕРЕНО {unchecked}")
    print("«Не сверено» — это не «в порядке»: источник не ответил или не подключён.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
