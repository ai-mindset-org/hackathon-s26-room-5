"""Судья приёмки по смыслу: python3 -m judge [папка-examples] [--only 01,05] [--json out.json]

Раннер сверяет отчёт с expected.md по якорям (ключи, числа, детали) и не видит
лишних находок, хотя половина приёмки 02/03 – про их отсутствие. Судья отдаёт
пару «ожидаемое + отчёт» модели и получает по каждому примеру: какие факты
покрыты, какие пропущены, что лишнее, вердикт.

Ключей не нужно: судья ходит через CLI, который есть у каждого в комнате
по условиям входа – `claude -p` или `codex exec`. Выбор: JUDGE_BACKEND=claude|codex
(по умолчанию claude, если стоит, иначе codex), модель: JUDGE_MODEL.

Итог: «прошло N из M» по смыслу. Последнее слово – за заказчиком, как в README.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.__main__ import run                        # noqa: E402
from core.loader import load_expected                # noqa: E402
from core.report import render                       # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
TIMEOUT = int(os.environ.get("JUDGE_TIMEOUT", "240"))
MARK = {"прошёл": "✓", "частично": "~", "провал": "✗"}


def backend_name() -> str:
    b = os.environ.get("JUDGE_BACKEND")
    if b:
        return b
    if shutil.which("claude"):
        return "claude"
    if shutil.which("codex"):
        return "codex"
    return ""


def clean_env() -> dict:
    """Судью часто запускают из-под Claude Code или Codex: переменные вложенной
    сессии (CLAUDECODE, CLAUDE_CODE_*) заставляют дочерний claude падать."""
    return {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}


def ask(prompt: str, backend: str) -> tuple[str, str]:
    """Возвращает (текст ответа, модель, если известна)."""
    model = os.environ.get("JUDGE_MODEL", "")
    # временная папка: чтобы CLI не подхватил CLAUDE.md/AGENTS.md репозитория
    with tempfile.TemporaryDirectory(prefix="judge-") as cwd:
        if backend == "claude":
            cmd = ["claude", "-p", "--output-format", "json", "--no-session-persistence",
                   "--disallowedTools", "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Agent"]
            # --bare не читает Keychain, поэтому только при ключе в окружении
            if os.environ.get("ANTHROPIC_API_KEY"):
                cmd.append("--bare")
            if model:
                cmd += ["--model", model]
            out = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                 timeout=TIMEOUT, cwd=cwd, env=clean_env())
            try:
                data = json.loads(out.stdout)
            except ValueError:
                raise RuntimeError((out.stderr or out.stdout).strip()[-300:] or f"claude: код {out.returncode}")
            if data.get("is_error") or out.returncode != 0:
                raise RuntimeError(str(data.get("result", ""))[:300] or out.stderr.strip()[-300:] or f"claude: код {out.returncode}")
            used = ", ".join((data.get("modelUsage") or {}).keys()) or model
            return data.get("result", ""), used
        if backend == "codex":
            last = Path(cwd) / "last.txt"
            cmd = ["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "-C", cwd, "-o", str(last)]
            if model:
                cmd += ["-m", model]
            cmd.append("-")
            out = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                 timeout=TIMEOUT, cwd=cwd, env=clean_env())
            text = last.read_text(encoding="utf-8") if last.exists() else ""
            if not text:
                raise RuntimeError(out.stderr.strip()[-300:] or f"codex: код {out.returncode}")
            return text, model or "codex по умолчанию"
    raise RuntimeError("нет ни claude, ни codex в PATH; задай JUDGE_BACKEND")


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("в ответе судьи нет JSON")
    return json.loads(text[start:end + 1])


def build_prompt(example_dir: Path, expected: str, report) -> str:
    parts = [PROMPT, "", f"=== ПРИМЕР: {example_dir.name} ===", "",
             "=== ОЖИДАЕМОЕ (expected.md) ===", expected.strip(), "",
             "=== ОТЧЁТ ИНСТРУМЕНТА ===", render(report, title=example_dir.name).strip()]
    if report.artifacts:
        parts += ["", "=== АРТЕФАКТЫ НА ВЫХОДЕ ==="]
        for name, body in report.artifacts.items():
            parts += [f"--- {name} ---", body[:4000]]
    return "\n".join(parts)


def judge_example(example_dir: Path, backend: str) -> dict:
    row = {"example": example_dir.name}
    report = run(example_dir, quiet=True)
    expected = load_expected(example_dir)
    if not report.checked_by:
        row.update(status="НЕ ПРОВЕРЕНО", details="ни один модуль не взялся")
        return row
    if not expected.strip():
        row.update(status="НЕТ EXPECTED", details=f"{len(report.findings)} находок, сверять не с чем")
        return row
    try:
        text, model = ask(build_prompt(example_dir, expected, report), backend)
        verdict = parse_json(text)
    except Exception as exc:                          # судья упал – это не провал примера
        row.update(status="СУДЬЯ НЕ ОТВЕТИЛ", details=str(exc)[:200])
        return row
    facts = verdict.get("facts") or []
    covered = verdict.get("covered") or []
    missed = verdict.get("missed") or []
    extra = verdict.get("extra") or []
    soft = verdict.get("soft_extra") or []
    v = str(verdict.get("verdict", "")).strip().lower()
    if v not in MARK:
        v = "провал" if extra or len(covered) * 2 < len(facts) else ("частично" if missed or soft else "прошёл")
    bits = [f"факты {len(covered)}/{len(facts)}"]
    if missed:
        bits.append("пропущено: " + "; ".join(m[:70] for m in missed[:3]))
    if extra:
        bits.append("лишнее: " + "; ".join(e[:70] for e in extra[:3]))
    if soft:
        bits.append(f"вопросов не по делу: {len(soft)}")
    row.update(status=v.upper(), verdict=v, details=" · ".join(bits), model=model,
               facts=facts, covered=covered, missed=missed, extra=extra, soft_extra=soft,
               note=verdict.get("note", ""))
    return row


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    only = None
    json_out = None
    for i, a in enumerate(argv):
        if a == "--only" and i + 1 < len(argv):
            only = argv[i + 1].split(",")
            args = [x for x in args if x != argv[i + 1]]
        if a == "--json" and i + 1 < len(argv):
            json_out = Path(argv[i + 1])
            args = [x for x in args if x != argv[i + 1]]
    root = Path(args[0]) if args else REPO_ROOT / "examples"
    backend = backend_name()
    if not backend:
        print("Судье нужен claude или codex в PATH (JUDGE_BACKEND=claude|codex)", file=sys.stderr)
        return 2

    examples = sorted(d for d in root.iterdir() if d.is_dir() and not d.name.startswith("."))
    if only:
        examples = [d for d in examples if any(d.name.startswith(o.strip()) for o in only)]
    if not examples:
        print(f"В {root} нет примеров", file=sys.stderr)
        return 2

    print(f"Судья приёмки по смыслу · {len(examples)} примеров · {backend}", flush=True)
    with ThreadPoolExecutor(max_workers=min(4, len(examples))) as pool:
        rows = list(pool.map(lambda d: judge_example(d, backend), examples))

    passed = 0
    models = set()
    for r in rows:
        v = r.get("verdict")
        mark = MARK.get(v, "–") if v else ("?" if r["status"] == "СУДЬЯ НЕ ОТВЕТИЛ" else "–")
        passed += v == "прошёл"
        if r.get("model"):
            models.add(r["model"])
        print(f"  {mark} {r['example']:<32} {r['status']:<15} {r['details']}")
        if r.get("note"):
            print(f"      {r['note']}")
    print(f"\nПРОШЛО {passed} ИЗ {len(rows)} по смыслу" + (f" · судил {', '.join(sorted(models))}" if models else ""))
    print("Раннер по якорям (python3 -m runner) считает покрытие; судья добавляет пропуски и лишнее.\n"
          "Вердикт «решило / не решило» остаётся за заказчиком.")
    if json_out:
        json_out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Подробности: {json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
