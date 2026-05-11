# Ozon UTM statistics

Скрипт создаёт отчёт Ozon Performance API по аналитике внешнего трафика
`TRAFFIC_SOURCES`, ждёт готовности отчёта и преобразует результат в
`pandas.DataFrame`.

## Запуск

### В Jupyter Notebook

Установите проект из GitHub:

```python
%pip uninstall -y ozon-api
%pip install --upgrade --force-reinstall --no-cache-dir git+https://github.com/IvanBibanin/ozon_api.git@main
```

После установки перезапустите kernel в Jupyter Notebook.

Если запускаете ноутбук из локальной папки репозитория:

```python
%pip install -e .
```

В следующей ячейке укажите ключи и получите отчёт как датафрейм:

```python
from ozon_utm_statistics import OzonUtmStatisticsClient

client = OzonUtmStatisticsClient(
    client_id="ваш_client_id",
    client_secret="ваш_client_secret",
)

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

### Загрузка в PostgreSQL

Если перед вставкой нужно удалить старые строки, выполните свой SQL через
`sql_query()`, а затем вставьте датафрейм.

```python
from ozon_utm_statistics import to_postgresql

postgres = to_postgresql(
    host="localhost",
    port=5432,
    user="postgres",
    password="password",
    database="database",
    schema="ozon",
)

postgres.create_table(table_name="utm_statistics", data=df)
postgres.sql_query("""
DELETE FROM ozon."utm_statistics"
WHERE "Дата" BETWEEN '2026-05-01' AND '2026-05-10'
""")

postgres.insert_into_table(table_name="utm_statistics", data=df)
```

Ozon ограничивает период отчёта внешнего трафика тремя месяцами.
