"""Product table (CSV) -> rows for the Prom.ua import file, plus a list of problems.

Field limits and column names follow Prom's support article "Import via Excel (XLS/XLSX/CSV)"
(checked 2026-10-13): name_ru up to 110, name_uk up to 130, description up to 12160, search queries
up to 1024, product code up to 25 characters. Prom may change them: check the current article.
"""
import csv
import io
import re
from decimal import Decimal, InvalidOperation

LIM_NAME_RU, LIM_NAME_UK, LIM_DESC, LIM_QUERIES, LIM_CODE, LIM_GROUP = 110, 130, 12160, 1024, 25, 100
CODE_OK = re.compile(r"^[0-9A-Za-zА-Яа-яІіЇїЄєҐґ\-_./ ]+$")
PRODUCT_COLS = ["Код_товару", "Назва_позиції", "Назва_позиції_укр", "Пошукові_запити", "Пошукові_запити_укр", "Опис",
                "Опис_укр", "Тип_товару", "Ціна", "Валюта", "Одиниця_виміру", "Мінімальний_обсяг_замовлення",
                "Кількість", "Посилання_зображення", "Наявність", "Виробник", "Номер_групи", "Назва_групи",
                "Ідентифікатор_товару"]
CHAR_COLS = ["Назва_Характеристики", "Одиниця_виміру_Характеристики", "Значення_Характеристики"]
GROUP_COLS = ["Номер_групи", "Назва_групи", "Назва_групи_укр", "Ідентифікатор_групи", "Номер_батьківської_групи"]
YES = {"", "yes", "y", "+", "true", "in stock", "так", "є", "в наявності", "да", "1"}
NO = {"no", "n", "-", "false", "out of stock", "ні", "немає", "нет", "0"}


def read_table(text):
    """CSV text -> (header, [(line_number, dict)]). The header is line 1; comma or semicolon is detected."""
    text = text.lstrip("﻿")
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") > first.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        return [], []
    head = [h.strip() for h in rows[0]]
    out = []
    for i, r in enumerate(rows[1:], start=2):
        if any(c.strip() for c in r):
            out.append((i, {head[j].lower() if not head[j].lower().startswith("param:") else head[j]: (r[j].strip() if j < len(r) else "") for j in range(len(head))}))
    return head, out


def parse_price(s):
    t = re.sub(r"[^\d,.\-]", "", (s or "").replace("\xa0", ""))
    if not t:
        return None
    if "," in t and "." in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        t = t.replace("," if dec == "." else ".", "").replace(dec, ".")
    else:
        t = t.replace(",", ".")
    try:
        v = Decimal(t)
    except InvalidOperation:
        return None
    return v if v > 0 else None


def price_number(v):
    return int(v) if v == v.to_integral_value() else float(v)


def photo_list(s):
    return [p for p in re.split(r"[\s,;|]+", s or "") if p]


def stock_values(s):
    """-> (availability sign, quantity or None, warning or None)"""
    t = (s or "").strip().lower()
    if t in YES:
        return "+", None, None
    if t in NO:
        return "-", None, None
    if t.isdigit():
        n = int(t)
        return ("+" if n > 0 else "-"), (n if n > 0 else None), None
    return "+", None, "stock %r is not understood, treated as in stock" % s


def build(rows, currency="UAH", copy_uk_to_ru=True):
    """rows: [(line, dict)]. Returns (products, groups, problems); problems: (line, 'error'|'warning', text)."""
    problems, products, seen, groups = [], [], {}, {}

    def add(line, level, msg):
        problems.append((line, level, msg))

    for line, r in rows:
        sku = r.get("sku", "")
        before = len([p for p in problems if p[1] == "error"])
        if not sku:
            add(line, "error", "sku is empty (row skipped)")
            continue
        if len(sku) > LIM_CODE or not CODE_OK.match(sku):
            add(line, "error", "sku %r: up to %d characters, only letters, digits and - _ . / space" % (sku, LIM_CODE))
        if sku in seen:
            add(line, "error", "sku %r repeats line %d (row skipped)" % (sku, seen[sku]))
            continue
        seen[sku] = line
        uk, ru = r.get("name_uk", ""), r.get("name_ru", "")
        d_uk, d_ru = r.get("description_uk", ""), r.get("description_ru", "")
        if not (uk or ru):
            add(line, "error", "%s: name_uk or name_ru is required" % sku)
        if not (d_uk or d_ru):
            add(line, "error", "%s: a description is required by Prom (description_uk or description_ru)" % sku)
        copied = []
        if copy_uk_to_ru:
            if uk and not ru:
                ru, copied = uk, copied + ["name"]
            if d_uk and not d_ru:
                d_ru, copied = d_uk, copied + ["description"]
        if copied:
            add(line, "warning", "%s: Russian %s copied from the Ukrainian text" % (sku, " and ".join(copied)))
        if len(ru) > LIM_NAME_RU:
            add(line, "error", "%s: name_ru is %d characters, Prom allows %d" % (sku, len(ru), LIM_NAME_RU))
        if len(uk) > LIM_NAME_UK:
            add(line, "error", "%s: name_uk is %d characters, Prom allows %d" % (sku, len(uk), LIM_NAME_UK))
        for label, text in (("description_ru", d_ru), ("description_uk", d_uk)):
            if len(text) > LIM_DESC:
                add(line, "error", "%s: %s is %d characters, Prom allows %d" % (sku, label, len(text), LIM_DESC))
        price = parse_price(r.get("price", ""))
        if price is None:
            add(line, "error", "%s: price %r is not a number above zero" % (sku, r.get("price", "")))
        photos = photo_list(r.get("photos", ""))
        bad = [p for p in photos if not re.match(r"^https?://\S+$", p)]
        if bad:
            add(line, "error", "%s: photo link %r must start with http:// or https://" % (sku, bad[0]))
        if not photos:
            add(line, "warning", "%s: no photos" % sku)
        q_uk, q_ru = r.get("keywords_uk", ""), r.get("keywords_ru", "")
        for label, q in (("keywords_uk", q_uk), ("keywords_ru", q_ru)):
            if len(q) > LIM_QUERIES:
                add(line, "error", "%s: %s is %d characters, Prom allows %d" % (sku, label, len(q), LIM_QUERIES))
        sign, qty, warn = stock_values(r.get("stock", ""))
        if warn:
            add(line, "warning", "%s: %s" % (sku, warn))
        group = r.get("group", "")
        if not group:
            add(line, "warning", "%s: no group, put into «Без групи»" % sku)
            group = "Без групи"
        if len(group) > LIM_GROUP:
            add(line, "error", "%s: group name is %d characters, Prom allows %d" % (sku, len(group), LIM_GROUP))
        chars = []
        for key, val in r.items():
            if key.startswith("param:") and val:
                name, _, unit = key[6:].partition("|")
                chars.append((name.strip(), unit.strip(), val))
        if len([p for p in problems if p[1] == "error"]) > before:
            continue
        gnum = groups.setdefault(group, len(groups) + 1)
        products.append({
            "Код_товару": sku, "Назва_позиції": ru, "Назва_позиції_укр": uk, "Пошукові_запити": q_ru or "",
            "Пошукові_запити_укр": q_uk or "", "Опис": d_ru, "Опис_укр": d_uk, "Тип_товару": "r",
            "Ціна": price_number(price), "Валюта": r.get("currency") or currency, "Одиниця_виміру": "шт.",
            "Мінімальний_обсяг_замовлення": 1, "Кількість": qty if qty is not None else "",
            "Посилання_зображення": ", ".join(photos), "Наявність": sign, "Виробник": r.get("vendor", ""),
            "Номер_групи": gnum, "Назва_групи": group, "Ідентифікатор_товару": sku, "_chars": chars})
    glist = [[n, g, g, "", ""] for g, n in groups.items()]
    return products, glist, problems


def to_sheets(products, glist):
    nchars = max((len(p["_chars"]) for p in products), default=0)
    header = PRODUCT_COLS + CHAR_COLS * nchars
    data = []
    for p in products:
        row = [p[c] for c in PRODUCT_COLS]
        for i in range(nchars):
            row += list(p["_chars"][i]) if i < len(p["_chars"]) else ["", "", ""]
        data.append(row)
    return {"Export Products Sheet": (header, data), "Export Groups Sheet": (GROUP_COLS, glist)}
