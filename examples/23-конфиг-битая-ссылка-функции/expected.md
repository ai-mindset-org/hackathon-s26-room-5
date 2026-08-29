# Ожидаемый отчёт

Нарушение: Функция ссылается на необъявленную модель deepseek-deepseek-v4-flash-missing (П4).

Место: functions.*.variants.* → model.

Цитата: `model = "deepseek-deepseek-v4-flash-missing"`

Что не так: вариант функции вызывает модель deepseek-deepseek-v4-flash-missing, а блок [models.deepseek-deepseek-v4-flash-missing] нигде не объявлен — битая ссылка. Правило П4.

Ключевая проверка: инструмент должен указать именно это место и процитировать именно это значение — не общий «конфиг не соответствует».
