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

### В Jupyter Notebook

Сначала установите проект из папки репозитория:

```python
%pip install -e .
```

Если пакет уже был установлен раньше, обновите его принудительно:

```python
%pip install --force-reinstall --no-cache-dir git+https://github.com/IvanBibanin/ozon_api.git
```

В следующей ячейке укажите ключи и скачайте отчёт:

```python
from ozon_utm_statistics import OzonCredentials, OzonUtmStatisticsClient

credentials = OzonCredentials(
    client_id="ваш_client_id",
    client_secret="ваш_client_secret",
)
client = OzonUtmStatisticsClient(credentials)

file_path = client.download_utm_statistics(
    date_from="2026-05-01",
    date_to="2026-05-10",
    output="reports/utm_2026-05-01_2026-05-10.csv",
)

file_path
```

Если отчёт уже создан и есть UUID:

```python
file_path = client.download_utm_statistics(
    date_from="2026-05-01",
    date_to="2026-05-10",
    uuid="0c159c60-ab92-46d9-9a6b-d225dbf5c7b1",
    output="reports",
)
```

### Из консоли

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
