# Комната 5 · Проверка артефакта до сдачи

<!-- aim-public-links:start -->
[Лабы AI Mindset](https://aimindset.org/?utm_source=website&utm_medium=article&utm_campaign=start&utm_content=github-hackathon-s26-room-5#learning) · [База знаний](https://base.aimindset.org/?utm_source=website&utm_medium=article&utm_campaign=start&utm_content=github-hackathon-s26-room-5)
<!-- aim-public-links:end -->

Хакатон AI Mindset S26 «Чужая боль» · 29.08.2026 · 10:00–14:00 CET

## Задача

Перед сдачей артефакт проверяется глазами: чертежи перед производством,
раздаточные материалы, конфиги и доступы. Ошибка стоит дорого, проверка
скучная, правила проверки живут в опыте проверяющего.

**Строим:** инструмент, который берёт артефакт (документ, таблицу, конфиг,
описание чертежа) и явный чеклист правил и отдаёт отчёт о расхождениях
с точным указанием мест: что нарушено, где, какой пункт чеклиста. Решение
«пропускать или нет» остаётся за человеком — инструмент делает видимым.

Боли заказчиков: проверка чертежей перед производством (ежедневно); обезличивание
данных перед передачей наружу и обратный маппинг; рутина администрирования платформы
агентов — доступы, ключи, конфиги, бюджеты.

## Как работаем с кодом

- **Fork → ветка → PR.** Агент делает это сам: `gh repo fork ai-mindset-org/hackathon-s26-room-5 --clone`,
  ветка `КОД-УЧАСТНИКА/что-делаю`, `gh pr create --fill`. Мержит лидер комнаты.
- **Один участник — один модуль или папка.** Кто что берёт — решаем в комнате,
  фиксируем issues. Так PR не дерутся между собой.
- Конфликт: `git remote add upstream https://github.com/ai-mindset-org/hackathon-s26-room-5` →
  `git pull --rebase upstream main`.
- Интервью с заказчиками кладём в `docs/interview-КОД.md`.
- **Секретов в репозитории не бывает.** Репо публичный. `.env` в `.gitignore`,
  ключи живут только на вашей машине.
- После каждого мержа гоняем `examples/` — они и есть приёмка.

## Приёмка

В `examples/` лежат входы с ожидаемым результатом (собраны из болей заказчиков). Итог демо: «прошло N из M» + вердикт заказчиков
«решило / не решило». Частичный результат — тоже результат.

## Кто в комнате

Комната, зум и чекин — [hackathon-live.aimindset.org](https://hackathon-live.aimindset.org/?utm_source=website&utm_medium=article&utm_campaign=start&utm_content=github-hackathon-s26-room-5) (блок «мой код»)
Голосование и итоги — [hackathon-live.aimindset.org/vote](https://hackathon-live.aimindset.org/vote/?utm_source=website&utm_medium=article&utm_campaign=start&utm_content=github-hackathon-s26-room-5)
Инструкция агенту — [hackathon-live.aimindset.org/skill/HACKATHON.md](https://hackathon-live.aimindset.org/skill/HACKATHON.md?utm_source=website&utm_medium=article&utm_campaign=start&utm_content=github-hackathon-s26-room-5)
