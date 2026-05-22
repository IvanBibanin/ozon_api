# Ozon UTM statistics

Python-пакет для работы с отчетом Ozon Performance API по внешнему трафику `TRAFFIC_SOURCES`.

Пакет умеет:

- получать access token Ozon Performance API;
- создавать отчет по UTM / внешнему трафику;
- ждать готовности отчета;
- скачивать отчет и преобразовывать его в `pandas.DataFrame`;
- очищать длинные названия колонок;
- сохранять данные в PostgreSQL через отдельный пакет `to_postgresql`.

## Установка в Jupyter Notebook

```python
%pip uninstall -y ozon-api
%pip install --upgrade --force-reinstall --no-cache-dir git+https://github.com/IvanBibanin/ozon_api.git@main
%pip install --upgrade --force-reinstall --no-cache-dir git+https://github.com/IvanBibanin/to_postgresql.git@main
```

После установки перезапустите kernel Jupyter, чтобы Python точно взял свежую версию модулей.

Если запускаете ноутбук из локальной папки репозитория:

```python
%pip install -e .
```

## Импорт

```python
from ozon_utm_statistics import OzonUtmStatisticsClient
from to_postgresql import ToPostgreSQL
```

Для совместимости также можно импортировать старое имя:

```python
from to_postgresql import to_postgresql
```

## Получить отчет Ozon в DataFrame

```python
from ozon_utm_statistics import OzonUtmStatisticsClient

client = OzonUtmStatisticsClient(
    client_id="ВАШ_CLIENT_ID",
    client_secret="ВАШ_CLIENT_SECRET",
)

df = client.get_utm_statistics(
    date_from="2026-05-01",
    date_to="2026-05-02",
)

df.head()
```

Не храните `client_id`, `client_secret` и пароли в ноутбуке или репозитории. Лучше брать их из переменных окружения:

```python
import os

client = OzonUtmStatisticsClient(
    client_id=os.getenv("OZON_CLIENT_ID"),
    client_secret=os.getenv("OZON_CLIENT_SECRET"),
)
```

## Если отчет уже создан

Если у вас уже есть UUID отчета, можно не создавать новый отчет, а сразу дождаться и скачать существующий:

```python
df = client.get_utm_statistics(
    date_from="2026-05-01",
    date_to="2026-05-02",
    uuid="0c159c60-ab92-46d9-9a6b-d225dbf5c7b1",
)
```

## Посмотреть колонки

```python
df.columns.tolist()
```

Красиво по одной строке:

```python
for column in df.columns:
    print(column)
```

В Jupyter можно отключить сокращение колонок:

```python
import pandas as pd

pd.set_option("display.max_columns", None)
```

## Сохранить в Excel

```python
df.to_excel("ozon_utm_statistics.xlsx", index=False)
```

В конкретную папку:

```python
df.to_excel("/Users/ivan/Downloads/ozon_utm_statistics.xlsx", index=False)
```

## Подключение к PostgreSQL

PostgreSQL-helper вынесен в отдельный пакет `to_postgresql`. Установите его отдельно из `https://github.com/IvanBibanin/to_postgresql`.

```python
from to_postgresql import ToPostgreSQL

postgres = ToPostgreSQL(
    host="your-postgres-host",
    port=5432,
    user="your-user",
    password="your-password",
    database="postgres",
)
```

Или через совместимое старое имя:

```python
from to_postgresql import to_postgresql

postgres = to_postgresql(
    host="your-postgres-host",
    port=5432,
    user="your-user",
    password="your-password",
    database="postgres",
)
```

## Создать таблицу

```python
postgres.create_table(data=df, table_name="МИШИДО", schema="overon")
```

Метод создает схему, если ее нет, и таблицу, если ее нет:

```sql
CREATE SCHEMA IF NOT EXISTS "overon";
CREATE TABLE IF NOT EXISTS "overon"."МИШИДО" (...);
```

Важно: `CREATE TABLE IF NOT EXISTS` не меняет уже существующую таблицу. Если в DataFrame появились новые колонки, нужно пересоздать таблицу или добавить колонки через `ALTER TABLE`.

## Повторная загрузка без дублей

Перед повторной вставкой удалите старые строки за нужный период, потом вставьте свежий DataFrame.

```python
date_from = "2026-05-01"
date_to = "2026-05-02"

postgres.sql_query(
    f'DELETE FROM "overon"."МИШИДО" '
    f"WHERE \"Дата\" BETWEEN DATE '{date_from}' AND DATE '{date_to}'"
)

postgres.insert_into_table(data=df, table_name="МИШИДО", schema="overon")
```

Можно написать без f-string:

```python
postgres.sql_query(
    'DELETE FROM "overon"."МИШИДО" '
    'WHERE "Дата" BETWEEN DATE \'2026-05-01\' AND DATE \'2026-05-02\''
)
```

## Полный пример для Jupyter

```python
from ozon_utm_statistics import OzonUtmStatisticsClient
from to_postgresql import to_postgresql


client = OzonUtmStatisticsClient(
    client_id="ВАШ_CLIENT_ID",
    client_secret="ВАШ_CLIENT_SECRET",
)

date_from = "2026-05-01"
date_to = "2026-05-02"

df = client.get_utm_statistics(
    date_from=date_from,
    date_to=date_to,
)

ozon_to_pg = to_postgresql(
    port=6543,
    host="your-postgres-host",
    user="your-user",
    password="your-password",
    database="postgres",
)

ozon_to_pg.create_table(data=df, table_name="МИШИДО", schema="overon")

ozon_to_pg.sql_query(
    f'DELETE FROM "overon"."МИШИДО" '
    f"WHERE \"Дата\" BETWEEN DATE '{date_from}' AND DATE '{date_to}'"
)

ozon_to_pg.insert_into_table(data=df, table_name="МИШИДО", schema="overon")
```

## Частая ошибка с датами в SQL

Неправильно:

```python
date_from = "2026-05-01"
date_to = "2026-05-02"

postgres.sql_query(
    f'delete from overon.МИШИДО where "Дата" between {date_from} and {date_to}'
)
```

Так в PostgreSQL уходит SQL без кавычек вокруг дат:

```sql
delete from overon.МИШИДО where "Дата" between 2026-05-01 and 2026-05-02
```

PostgreSQL воспринимает `2026-05-01` как арифметику `2026 - 05 - 01`, то есть как integer. Поэтому появляется ошибка:

```text
operator does not exist: date >= integer
```

Правильно:

```python
postgres.sql_query(
    'DELETE FROM "overon"."МИШИДО" '
    'WHERE "Дата" BETWEEN DATE \'2026-05-01\' AND DATE \'2026-05-02\''
)
```

Или через переменные:

```python
postgres.sql_query(
    f'DELETE FROM "overon"."МИШИДО" '
    f"WHERE \"Дата\" BETWEEN DATE '{date_from}' AND DATE '{date_to}'"
)
```

Правило:

- даты и строки в SQL пишутся в одинарных кавычках: `DATE '2026-05-01'`;
- имена схем, таблиц и колонок пишутся в двойных кавычках: `"overon"."МИШИДО"`, `"Дата"`.

## Ограничения текущей версии

- `ToPostgreSQL` создает `DATE` только для колонок `date` и `Дата`.
- Остальные колонки создаются как `TEXT`.
- `create_table()` не добавляет новые колонки в уже существующую таблицу.
- `insert_into_table()` делает обычный `INSERT`, без `UPSERT`.
- Для повторной загрузки нужно заранее удалить старые строки за период.

## Структура репозитория

```text
ozon_utm_statistics.py  # Ozon Performance API client и преобразование отчета в DataFrame
setup.py                # установка пакета из GitHub
README.md               # документация и примеры
```
