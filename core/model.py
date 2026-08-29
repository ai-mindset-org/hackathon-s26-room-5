"""Контракт комнаты 5: как выглядит одна находка и результат прогона.

Структуры взяты из docs/plan-J2PL.md (PR #1, смержен) без изменений —
чтобы модули, написанные по тому плану, подключались без переделок.
"""

from dataclasses import dataclass, field


@dataclass
class Finding:
    """Одно расхождение артефакта с правилом.

    `where` и `quote` обязательны: заказчик должен пойти править,
    не переспрашивая. Отчёт без адреса и цитаты бесполезен.
    """

    rule_id: str           # "п.3", "правило 1" — как в чеклисте заказчика
    rule_text: str         # текст правила дословно
    where: str             # "spec.md:3" или "вал-102 · диаметр_мм"
    quote: str             # цитата из артефакта — то самое место
    what: str              # что не так, одной фразой
    severity: str = "нарушение"   # "нарушение" | "вопрос"


@dataclass
class Report:
    """Что модуль отдаёт ядру.

    `artifacts` нужен обезличивателю: он отдаёт не находки, а файлы
    (обезличенный текст и mapping.json). Остальные модули оставляют пустым.
    """

    findings: list[Finding] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)   # что модуль проверил и счёл нормой
    checked_by: list[str] = field(default_factory=list)  # какие модули реально отработали

    def __bool__(self) -> bool:
        return bool(self.findings or self.artifacts)
