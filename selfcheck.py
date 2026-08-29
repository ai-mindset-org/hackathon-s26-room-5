#!/usr/bin/env python3
"""Самопроверка инструмента.

  python3 selfcheck.py            быстрый прогон: приёмка + 40 генераций
  python3 selfcheck.py --runs 50  глубже: по 50 генераций на каждый вид
  python3 selfcheck.py --seed 17  разобрать один конкретный прогон

Что делает. Сначала гоняет приёмочные примеры. Потом генератор подкладывает
артефакты с заранее известными дефектами и приманками, а инструмент их
проверяет. Каждое расхождение печатается с номером seed, чтобы его можно
было воспроизвести одной командой и починить.

Считается три вида проблем:
  пропуск       дефект заложен, инструмент промолчал — это дыра в проверке
  ложная        сработал на приманке — это хуже пропуска, убивает доверие
  сверх плана   нашёл то, чего не закладывали. Не всегда ошибка: генератор
                мог создать дефект случайно. Смотреть глазами.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import registry                                   # noqa: E402
from core.loader import load_inputs                          # noqa: E402
from runner.__main__ import check_example                    # noqa: E402
from generator.compare import compare, compare_anonymizer    # noqa: E402
from generator.defects import KINDS, generate                # noqa: E402

GREEN, RED, YELLOW, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def run_inputs(files: dict[str, str]) -> dict:
    mods = registry.pick(files)
    reports = [m.check(files) for m in mods]
    findings = []
    artifacts = {}
    from dataclasses import asdict
    for r in reports:
        for f in r.findings:
            d = asdict(f)
            d.setdefault("hint", "")
            d["line"] = _line_of(d, files)
            findings.append(d)
        artifacts.update(r.artifacts)
    return {"findings": findings, "artifacts": artifacts,
            "checkers": [m.NAME for m in mods], "reports": reports}


def _line_of(f: dict, files: dict[str, str]) -> int:
    head = f["where"].split("·")[0].strip()
    if ":" in head:
        _, _, num = head.rpartition(":")
        if num.isdigit():
            return int(num)
    quote = (f.get("quote") or "").strip().splitlines()
    if quote:
        for text in files.values():
            if quote[0] and quote[0] in text:
                return text.count("\n", 0, text.index(quote[0])) + 1
    return 0


def check_acceptance() -> tuple[int, int, list[str]]:
    """Официальная приёмка комнаты: тот же runner, что гоняют на демо."""
    ok, total, bad = 0, 0, []
    for folder in sorted((ROOT / "examples").iterdir()):
        if not folder.is_dir():
            continue
        total += 1
        status, details = check_example(folder)
        if status == "ПРОШЁЛ":
            ok += 1
        else:
            bad.append(f"{folder.name}: {status} — {details}")
    return ok, total, bad


def fuzz(kind: str, runs: int, defects: int, verbose_seed: int | None) -> list[dict]:
    problems = []
    seeds = [verbose_seed] if verbose_seed is not None else range(1, runs + 1)
    for seed in seeds:
        g = generate(kind, defects=defects, seed=seed)
        res = run_inputs(g["files"])
        cmp = (compare_anonymizer(g, res["artifacts"]) if kind == "pii"
               else compare(g, res["findings"]))
        for row in cmp["plan"]:
            if row["status"] == "пропущено":
                problems.append({"kind": kind, "seed": seed, "type": "пропуск",
                                 "text": f"{row['rule_id']} · {row['what']}",
                                 "line": row["line"], "src": row["text"]})
        for row in cmp["extra"]:
            f = row["finding"]
            problems.append({"kind": kind, "seed": seed,
                             "type": "ложная" if row["status"] == "ложная" else "сверх плана",
                             "text": f"{f['rule_id']} · {f['what']}",
                             "line": f.get("line", 0), "src": f.get("quote", ""),
                             "why": row.get("bait_why", "")})
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="самопроверка инструмента")
    ap.add_argument("--runs", type=int, default=10, help="генераций на каждый вид")
    ap.add_argument("--defects", type=int, default=4)
    ap.add_argument("--seed", type=int, help="разобрать один прогон")
    ap.add_argument("--kind", choices=list(KINDS), help="только один вид артефакта")
    args = ap.parse_args()

    print("САМОПРОВЕРКА")
    print("=" * 74)

    ok, total, bad = check_acceptance()
    mark = GREEN if ok == total else RED
    print(f"\n1. Приёмочные примеры: {mark}{ok} из {total}{OFF}")
    for b in bad:
        print(f"   {RED}✗{OFF} {b}")

    kinds = [args.kind] if args.kind else list(KINDS)
    all_problems: list[dict] = []
    print(f"\n2. Генератор дефектов: по {args.runs} прогонов на вид, "
          f"{args.defects} дефекта в каждом")
    for kind in kinds:
        problems = fuzz(kind, args.runs, args.defects, args.seed)
        all_problems += problems
        c = Counter(p["type"] for p in problems)
        line = f"   {KINDS[kind][0]:32}"
        if not problems:
            print(f"{line} {GREEN}чисто{OFF}")
        else:
            parts = []
            if c["пропуск"]:
                parts.append(f"{RED}пропусков {c['пропуск']}{OFF}")
            if c["ложная"]:
                parts.append(f"{RED}ложных {c['ложная']}{OFF}")
            if c["сверх плана"]:
                parts.append(f"{YELLOW}сверх плана {c['сверх плана']}{OFF}")
            print(f"{line} " + " · ".join(parts))

    hard = [p for p in all_problems if p["type"] in ("пропуск", "ложная")]
    soft = [p for p in all_problems if p["type"] == "сверх плана"]

    if hard:
        print(f"\n3. Что чинить — {len(hard)} шт.")
        seen = set()
        for p in hard:
            key = (p["kind"], p["type"], p["text"][:60])
            if key in seen:
                continue
            seen.add(key)
            print(f"\n   {RED}{p['type'].upper()}{OFF} · {p['kind']} · seed {p['seed']}")
            print(f"   {p['text']}")
            if p.get("src"):
                print(f"   {DIM}строка {p['line']}: {p['src'][:90]}{OFF}")
            if p.get("why"):
                print(f"   {DIM}приманка: {p['why']}{OFF}")
            print(f"   {DIM}повторить: python3 selfcheck.py --kind {p['kind']} "
                  f"--seed {p['seed']}{OFF}")
    else:
        print(f"\n3. {GREEN}Пропусков и ложных тревог нет.{OFF}")

    if soft:
        seen = set()
        rows = []
        for p in soft:
            key = (p["kind"], p["text"][:60])
            if key not in seen:
                seen.add(key)
                rows.append(p)
        print(f"\n4. Сверх плана — {len(soft)} шт., {len(rows)} видов. "
              f"{DIM}Не обязательно ошибка: смотреть глазами.{OFF}")
        for p in rows[:8]:
            print(f"   {YELLOW}·{OFF} {p['kind']} seed {p['seed']}: {p['text'][:88]}")

    print("\n" + "=" * 74)
    verdict = (f"{GREEN}ЧИСТО{OFF}" if not hard and ok == total else f"{RED}ЕСТЬ ЧТО ЧИНИТЬ{OFF}")
    print(f"ИТОГ: приёмка {ok}/{total} · пропусков "
          f"{sum(1 for p in hard if p['type'] == 'пропуск')} · ложных "
          f"{sum(1 for p in hard if p['type'] == 'ложная')} → {verdict}")
    return 0 if (not hard and ok == total) else 1


if __name__ == "__main__":
    raise SystemExit(main())
