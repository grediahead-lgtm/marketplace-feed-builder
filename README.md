# marketplace-feed-builder

Turns a **simple product table (CSV)** into a **Prom.ua import file (XLSX)** and a report of everything that breaks Prom's field limits, with the line number of your table for each problem. Python standard library only, runs locally, no internet, no account.

## Why
Prom's import format is strict (two sheets, long Ukrainian column names, limits on names, codes, descriptions) and a wrong file is rejected or imported half-broken. This tool checks your table first and writes the file in the documented format.

## Input: `products.csv`
Comma or semicolon, UTF-8. Required columns: `sku`, `price`, and `name_uk` or `name_ru`. Optional: `name_ru`, `description_uk`, `description_ru` (Prom needs a description), `currency` (default UAH), `stock` (`yes/no/+/-`, or a number), `photos` (links separated by comma, `;`, `|` or space), `group`, `vendor`, `keywords_uk`, `keywords_ru`, and any number of characteristic columns named `param:Name` or `param:Name|unit` (for example `param:Вага|кг`). See `examples/products.csv` (fake data).

## What it does
- Checks every row and **skips only rows with errors**, listing each one: empty or repeated `sku`, code longer than 25 characters or with forbidden characters, price that is not a number above zero (`1 250,50` and `1.234,56` are read correctly), name over 110 (ru) / 130 (uk) characters, description over 12160, search queries over 1024, photo links that are not `http(s)://`.
- Warnings for things that are allowed but worth a look: no photos, no group, unclear stock value, Russian text copied from the Ukrainian one.
- Groups are numbered from your `group` column; products without a group go to «Без групи».
- Writes `prom-import.xlsx` with the two sheets Prom describes («Export Products Sheet», «Export Groups Sheet»; characteristics as repeated blocks) and `report.md`.

## Quick start
```bash
PYTHONPATH=src python3 -m feed_builder examples/products.csv --out out
# --currency UAH  --no-copy (do not copy Ukrainian into the Russian fields)  --strict (exit code 2 if any row has an error)
```
Tests: `python3 -m unittest discover -s tests` (no internet).

## Limits (read this)
- **Not tested by a real upload.** The columns and limits follow Prom's support article «Import via Excel (XLS/XLSX/CSV)» as read on 2026-10-13. Importing a file in a seller account needs a paid Prom plan, which the author did not buy, so the file has not been accepted by Prom itself. Try it on a few products first, and re-read the article: Prom may change the format.
- It does **not** check that photo links open, that product names suit Prom's categories, or the rights to the photos.
- Russian fields: Prom asks for both languages. By default the Ukrainian text is copied into empty Russian fields (and reported); use `--no-copy` to leave them empty.
- One product per row, no variants grouping, no update of existing products (no `Унікальний_ідентифікатор`), no discounts.
- CSV input only; the table is never changed.

MIT license.

---

# marketplace-feed-builder (українською)

Перетворює просту таблицю товарів (CSV) на файл імпорту Prom.ua (XLSX) і звіт про всі порушення лімітів Prom із номерами рядків вашої таблиці. Лише стандартна бібліотека Python.

**Запуск:** `PYTHONPATH=src python3 -m feed_builder products.csv --out out`. Рядки з помилками пропускаються й описуються у `report.md`.

**Важливо:** файл зроблено за документацією Prom (стан на 13.10.2026), але реальним імпортом **не перевірено**: імпорт у кабінеті продавця потребує платного тарифу. Спершу спробуйте на кількох товарах.
