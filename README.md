# xd_bot (Геминика)

Discord-бот: управление Spotify/Voicemeeter, live-статус, экспорт истории сервера.

## Запуск
1. `pip install -r requirements.txt`
2. Скопировать `.env.example` в `.env` и заполнить:
    DISCORD_TOKEN=...
    DISCORD_BOT_OWNER_ID=...
    DISCORD_SERVER_FOR_EXPORT_ID=... # для кнопки экспорта в трее
    VM_OUTPUT_DEVICE=...             # обязательно — точное имя выхода Voicemeeter, бот не стартует без него
    BRIDGE_TOKEN=... # опционально, для AHK-моста
3. `python main.py` (добавь `--console`, если нужно видеть логи в окне)

## Настройка под своё окружение

Всё, что раньше было зашито в коде под конкретную машину, теперь читается
из `.env` (см. `.env.example` — там же и дефолты). Коротко:

| Переменная | Зачем |
|---|---|
| `VM_DLL_PATH` | путь к `VoicemeeterRemote64.dll`; пусто = автопоиск (обычный Voicemeeter / Banana / Potato, с `(x86)` и без) |
| `VM_STRIP_INDEX` | номер страйпа Voicemeeter, которым управляет бот (используется и Python-ботом, и AHK-скриптом) |
| `VM_MIN_DB` / `VM_MAX_DB` | **не личная настройка** — это собственные пределы фейдера Voicemeeter (-60/12 dB), дальше слайдер физически не двигается ни в одной редакции. Меняй, только если хочешь сузить диапазон бота *внутри* этих границ — шире выставить бессмысленно, Voicemeeter всё равно обрежет сам |
| `VM_OUTPUT_DEVICE` | обязателен, без дефолта: у Banana/Potato/обычного Voicemeeter имена разные, тихая подстановка чужого дефолта раньше приводила к рабочему без звука стриму без единой ошибки |
| `VOLUME_CEILING_DEFAULT` | дефолтный потолок громкости для не-владельцев при первом запуске |
| `VOLUME_STEP_DB` | шаг кнопок ➕/➖ и `/vadd` `/vrem` без аргумента |
| `FADE_STEP_DB` / `FADE_MAX_STEPS` / `FADE_STEP_DELAY_SECONDS` | кривая плавного изменения громкости |
| `COMMAND_PREFIX` | префикс `!`-команд |
| `DEFAULT_LOCALE` | `ru` или `default` (англ.) — язык там, где нет `interaction.locale` (обычные `!`-команды) |
| `PRESENCE_UPDATE_INTERVAL_SECONDS` | частота обновления presence-статуса |
| `EMBED_COLOR` | цвет embed'а `/now` (hex без `#`) |
| `SPOTIFY_IDLE_TITLES_EXTRA` | список через запятую — доп. заголовки "ничего не играет" для не-русского клиента Spotify (по умолчанию распознаётся только `"Музыка без помех"`) |
| `WEB_HOST` / `WEB_PORT` | адрес FastAPI-моста для AHK; **AHK-скрипт читает `WEB_PORT` из того же `.env`**, так что менять нужно только в одном месте |
| `FFMPEG_BEFORE_ARGS` / `FFMPEG_AFTER_ARGS` | параметры ffmpeg для радио-стрима |

AHK-скрипт (`AHK/xd_Spotify_Control.ahk`) сам читает `.env` из корня проекта
для `VM_DLL_PATH`, `VM_STRIP_INDEX`, `VM_MIN_DB`/`VM_MAX_DB`, `WEB_PORT` и
`BRIDGE_TOKEN` — их не нужно дублировать руками в скрипте. Горячие клавиши
(Numpad0, NumpadAdd и т.д.) остаются захардкожены в самом `.ahk`-файле —
это специфика AutoHotkey, меняются прямо в файле по месту.

### exporter.py
`_recheck_recent_messages` (перепроверка правок/удалений при повторном
запуске) теперь настраивается флагами:
```
python exporter.py <guild_id> --recheck-limit 200 --recheck-max-age-hours 3
```

### legend_builder.py
Порог "спрашивать описание только у того, что встретилось N+ раз" уже был
параметризован: `python legend_builder.py --min-count 3`.

## Данные
Все настройки, токен (если не через `.env`) и экспортированные материалы
хранятся в `data/` и `exports/` рядом с кодом.
