# Ozon UTM statistics downloader

Скрипт создаёт отчёт Ozon Performance API по аналитике внешнего трафика
`TRAFFIC_SOURCES`, ждёт готовности отчёта и скачивает файл по ссылке из API.

## Подготовка

Нужны `Client ID` и `Client Secret` именно от `Performance API`.

```bash
export OZON_PERFORMANCE_CLIENT_ID="..."
export OZON_PERFORMANCE_CLIENT_SECRET="..."
```

## Запуск

```bash
python3 ozon_utm_statistics.py --date-from 2026-05-01 --date-to 2026-05-10
```

Можно установить проект как локальную CLI-команду:

```bash
python3 -m pip install -e .
ozon-utm-statistics --date-from 2026-05-01 --date-to 2026-05-10
```

По умолчанию файл сохранится в папку `reports`. Можно указать файл или папку:

```bash
python3 ozon_utm_statistics.py \
  --date-from 2026-05-01 \
  --date-to 2026-05-10 \
  --output reports/utm_2026-05-01_2026-05-10.csv
```

Если отчёт уже создан и есть UUID:

```bash
python3 ozon_utm_statistics.py \
  --date-from 2026-05-01 \
  --date-to 2026-05-10 \
  --uuid "0c159c60-ab92-46d9-9a6b-d225dbf5c7b1"
```

Ozon ограничивает период отчёта внешнего трафика тремя месяцами.
