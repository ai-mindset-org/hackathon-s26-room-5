"""Ядро комнаты 5 — контракт, загрузка входов, подхват модулей, отчёт."""

from .model import Finding, Report
from .loader import load_inputs, load_expected
from .registry import discover, pick
from .report import render

__all__ = ["Finding", "Report", "load_inputs", "load_expected", "discover", "pick", "render"]
