#!/usr/bin/env python3
"""Приложение «Проверка перед сдачей» — то же ядро, но глазами человека.

    python3 app.py

Браузер откроется сам на http://localhost:8765. Наружу ничего не уходит:
сервер слушает только localhost, файлы читаются с этой машины.

Зачем оно, если есть `python3 -m runner`. Раннер отвечает на вопрос комнаты
«прошло N из M». Заказчику нужен другой ответ: что именно не так в ЕГО файле
и где это лежит. Отсюда три вещи, которых нет в терминале:

  · перетащить свой артефакт и получить отчёт, не заводя пример в репозитории;
  · увидеть находку прямо в файле — строка подсвечена, клик ведёт к ней;
  · собрать артефакт с известными дефектами и посмотреть, что инструмент
    поймает, а что проспит: проверка на данных, которых он не видел.

Модули, ядро и приёмка — те же самые. Приложение ничего своего не считает,
оно показывает то, что вернули `core` и `runner`.
"""
from __future__ import annotations

import json
import sys
import threading
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import registry                          # noqa: E402
from core.export_md import to_markdown             # noqa: E402
from core.loader import load_inputs                # noqa: E402
from generator.compare import compare, compare_anonymizer   # noqa: E402
from generator.defects import KINDS, generate      # noqa: E402
from runner.__main__ import check_example          # noqa: E402

PORT = 8765
EXAMPLES = ROOT / "examples"


def _anchor(finding: dict, inputs: dict[str, str]) -> tuple[str, int]:
    """Найти файл и строку, к которым относится находка.

    Сначала разбираем where вида «app.env:5». Если адрес смысловой
    («вал-102 · диаметр_мм»), ищем цитату в тексте — иначе подсветить
    находку в файле нечем.
    """
    where = finding.get("where", "")
    head = where.split("·")[0].strip()
    if ":" in head:
        name, _, num = head.rpartition(":")
        if num.isdigit() and name in inputs:
            return name, int(num)
    name = head if head in inputs else next((n for n in inputs if n and n in where), "")
    quote = (finding.get("quote") or "").strip().splitlines()
    first = quote[0] if quote else ""
    if not name:
        for n, text in inputs.items():
            if first and first in text:
                return n, text.count("\n", 0, text.index(first)) + 1
        return "", 0
    text = inputs.get(name, "")
    for probe in (first, first.split("·")[0].strip(), first.split("=")[0].strip()):
        if probe and probe in text:
            return name, text.count("\n", 0, text.index(probe)) + 1
    return name, 0


def run_on(inputs: dict[str, str]) -> dict:
    """Прогнать все подходящие модули по набору файлов."""
    mods = registry.pick(inputs)
    findings: list[dict] = []
    checked: list[str] = []      # Report.notes — что проверено и признано нормой
    runtime: list[str] = []      # Report.runtime_only — чего машина не умеет
    artifacts: dict[str, str] = {}

    for mod in mods:
        report = mod.check(inputs)
        for f in report.findings:
            d = asdict(f)
            d.setdefault("hint", "")
            findings.append(d)
        checked += list(report.notes)
        runtime += list(getattr(report, "runtime_only", []))
        artifacts.update(report.artifacts)

    order = {"нарушение": 0, "вопрос": 1, "норма": 2}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), f["rule_id"], f["where"]))
    for i, f in enumerate(findings):
        f["id"] = i
        f["file"], f["line"] = _anchor(f, inputs)

    return {
        "checkers": [{"name": m.NAME, "title": getattr(m, "TITLE", m.NAME)} for m in mods],
        "files": sorted(inputs),
        "sources": inputs,
        "findings": findings,
        "checked": checked,
        "notes": runtime,
        "artifacts": artifacts,
        "counts": {
            "violations": sum(1 for f in findings if f["severity"] == "нарушение"),
            "questions": sum(1 for f in findings if f["severity"] == "вопрос"),
            "checked": len(checked),
        },
    }


def examples_list() -> list[dict]:
    out = []
    for folder in sorted(EXAMPLES.iterdir()):
        if not folder.is_dir():
            continue
        expected = folder / "expected.md"
        files = sorted(p.name for p in (folder / "input").glob("*")) \
            if (folder / "input").is_dir() else []
        out.append({
            "id": folder.name,
            "title": folder.name.split("-", 1)[-1].replace("-", " ").capitalize(),
            "files": files,
            "expected": expected.read_text(encoding="utf-8") if expected.exists() else "",
        })
    return out


def acceptance() -> dict:
    """Официальная приёмка комнаты — тот же runner, что гоняют на демо."""
    results = []
    for folder in sorted(EXAMPLES.iterdir()):
        if not folder.is_dir():
            continue
        status, details = check_example(folder)
        results.append({"example": folder.name, "status": status, "details": details,
                        "passed": status == "ПРОШЁЛ"})
    return {
        "results": results,
        "passed": sum(1 for r in results if r["passed"]),
        "total": len(results),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):    # тише в консоли
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code=200):
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, (ROOT / "ui" / "app.html").read_bytes(),
                              "text/html; charset=utf-8")
        if self.path == "/api/examples":
            return self._json(examples_list())
        if self.path == "/api/acceptance":
            return self._json(acceptance())
        if self.path == "/api/kinds":
            return self._json([{"id": k, "title": v[0], "about": v[1]} for k, v in KINDS.items()])
        return self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")

        if self.path == "/api/run-example":
            folder = EXAMPLES / payload.get("id", "")
            if not folder.is_dir():
                return self._json({"error": "нет такого примера"}, 404)
            return self._json(run_on(load_inputs(folder)))

        if self.path == "/api/run":
            files = payload.get("files") or {}
            if not files:
                return self._json({"error": "файлы не пришли"}, 400)
            return self._json(run_on(files))

        if self.path == "/api/generate":
            kind = payload.get("kind", "config")
            try:
                g = generate(kind, defects=int(payload.get("defects", 3)),
                             seed=payload.get("seed"))
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            result = run_on(g["files"])
            cmp = (compare_anonymizer(g, result["artifacts"]) if kind == "pii"
                   else compare(g, result["findings"]))
            return self._json({"generated": {k: v for k, v in g.items() if k != "files"},
                               "result": result, "compare": cmp})

        if self.path == "/api/export":
            md = to_markdown(payload.get("title", "проверка"),
                             payload.get("result") or {},
                             payload.get("compare"), payload.get("generated"),
                             payload.get("acceptance"))
            return self._send(200, md.encode("utf-8"), "text/markdown; charset=utf-8")

        return self._send(404, b"not found", "text/plain; charset=utf-8")


def main() -> int:
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}/"
    print(f"Приложение запущено: {url}")
    print("Остановить — Ctrl+C. Наружу ничего не уходит.")
    threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
