# Ozon UTM statistics

Скрипт создаёт отчёт Ozon Performance API по аналитике внешнего трафика
`TRAFFIC_SOURCES`, ждёт готовности отчёта и преобразует результат в
`pandas.DataFrame`.

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

В следующей ячейке укажите ключи и получите отчёт как датафрейм:

```python
from ozon_utm_statistics import OzonCredentials, OzonUtmStatisticsClient

credentials = OzonCredentials(
    client_id="ваш_client_id",
    client_secret="ваш_client_secret",
)
client = OzonUtmStatisticsClient(credentials)

df = client.get_utm_statistics(
    date_from="2026-05-01",
    date_to="2026-05-10",
)

df
```

Если отчёт уже создан и есть UUID:

```python
df = client.get_utm_statistics(
    date_from="2026-05-01",
    date_to="2026-05-10",
    uuid="0c159c60-ab92-46d9-9a6b-d225dbf5c7b1",
)

df
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

Для вывода полной таблицы в CSV-формате в консоль добавьте `--csv`.

Если отчёт уже создан и есть UUID:

```bash
python3 ozon_utm_statistics.py \
  --date-from 2026-05-01 \
  --date-to 2026-05-10 \
  --uuid "0c159c60-ab92-46d9-9a6b-d225dbf5c7b1"
```

Ozon ограничивает период отчёта внешнего трафика тремя месяцами.
