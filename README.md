# xd_bot (Геминика)

Discord-бот: управление Spotify/Voicemeeter, live-статус, экспорт истории сервера.

## Запуск
1. `pip install -r requirements.txt`
2. Создать `.env` в корне проекта:
    DISCORD_TOKEN=...
    DISCORD_BOT_OWNER_ID=...
    DISCORD_SERVER_FOR_EXPORT_ID=... # для кнопки экспорта в трее
    BRIDGE_TOKEN=... # опционально, для AHK-моста
3. `python main.py` (добавь `--console`, если нужно видеть логи в окне)

## Данные
Все настройки, токен (если не через `.env`) и экспортированные материалы
хранятся в `data/` и `exports/` рядом с кодом.