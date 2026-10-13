import io
import os
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

from feed_builder.__main__ import main  # noqa: E402
from feed_builder.core import build, parse_price, photo_list, read_table, stock_values, to_sheets  # noqa: E402
from feed_builder.xlsx import col, write_xlsx  # noqa: E402

HEAD = "sku,name_uk,name_ru,description_uk,description_ru,price,currency,stock,photos,group,vendor,keywords_uk,param:Розмір,param:Вага|кг\n"


def run(rows, **kw):
    _, r = read_table(HEAD + rows)
    return build(r, **kw)


class Basics(unittest.TestCase):
    def test_price(self):
        self.assertEqual(str(parse_price("1 250,50")), "1250.50")
        self.assertEqual(str(parse_price("1.234,56")), "1234.56")
        self.assertEqual(str(parse_price("120 грн")), "120")
        for bad in ("", "abc", "0", "-5", None):
            self.assertIsNone(parse_price(bad))

    def test_stock(self):
        self.assertEqual(stock_values("")[0], "+")
        self.assertEqual(stock_values("так")[0], "+")
        self.assertEqual(stock_values("no")[0], "-")
        self.assertEqual(stock_values("12"), ("+", 12, None))
        self.assertEqual(stock_values("0")[0], "-")
        self.assertIsNotNone(stock_values("maybe")[2])

    def test_photos_and_columns(self):
        self.assertEqual(photo_list("http://a/1.jpg | http://a/2.jpg, http://a/3.jpg"), ["http://a/1.jpg", "http://a/2.jpg", "http://a/3.jpg"])
        self.assertEqual(col(0), "A")
        self.assertEqual(col(26), "AA")

    def test_table_semicolon_bom(self):
        head, rows = read_table("﻿sku;name_uk\nA;x\n\nB;y\n")
        self.assertEqual(head, ["sku", "name_uk"])
        self.assertEqual([(n, r["sku"]) for n, r in rows], [(2, "A"), (4, "B")])


class Build(unittest.TestCase):
    def test_good_row_and_ru_copy(self):
        p, g, probs = run("A-1,Назва,,Опис,,100,,5,https://x/1.jpg,Група,Бренд,,,\n")
        self.assertEqual(len(p), 1)
        row = p[0]
        self.assertEqual(row["Назва_позиції"], "Назва")  # copied from Ukrainian
        self.assertEqual(row["Ціна"], 100)
        self.assertEqual((row["Наявність"], row["Кількість"]), ("+", 5))
        self.assertTrue(any("copied" in m for _, lv, m in probs))
        self.assertEqual(g, [[1, "Група", "Група", "", ""]])

    def test_no_copy_keeps_russian_empty(self):
        p, _, probs = run("A-1,Назва,,Опис,,100,,,https://x/1.jpg,Г,,,,\n", copy_uk_to_ru=False)
        self.assertEqual(p[0]["Назва_позиції"], "")

    def test_errors_skip_the_row_with_line_numbers(self):
        p, _, probs = run("A-1,Назва,,Опис,,abc,,,,Г,,,,\nB-2,Назва2,,Опис2,,50,,,https://x/1.jpg,Г,,,,\n")
        self.assertEqual([x["Код_товару"] for x in p], ["B-2"])
        self.assertIn((2, "error"), [(l, lv) for l, lv, _ in probs])

    def test_duplicate_sku_and_empty_sku(self):
        p, _, probs = run("A,Н,,О,,10,,,https://x/1.jpg,Г,,,,\nA,Н2,,О2,,10,,,https://x/1.jpg,Г,,,,\n,Н3,,О3,,10,,,,,,,,\n")
        self.assertEqual(len(p), 1)
        msgs = [m for _, _, m in probs]
        self.assertTrue(any("repeats line 2" in m for m in msgs))
        self.assertTrue(any("sku is empty" in m for m in msgs))

    def test_prom_limits(self):
        long_ru, long_uk = "я" * 111, "я" * 131
        p, _, probs = run("A,%s,%s,О,О,10,,,https://x/1.jpg,Г,,,,\n" % (long_uk, long_ru))
        self.assertEqual(p, [])
        msgs = " ".join(m for _, _, m in probs)
        self.assertIn("name_ru is 111", msgs)
        self.assertIn("name_uk is 131", msgs)
        _, _, probs = run("%s,Н,,О,,10,,,https://x/1.jpg,Г,,,,\n" % ("K" * 26))
        self.assertTrue(any("up to 25" in m for _, _, m in probs))
        _, _, probs = run("A,Н,,%s,,10,,,https://x/1.jpg,Г,,,,\n" % ("о" * 12161))
        self.assertTrue(any("12161" in m for _, _, m in probs))

    def test_description_and_photo_rules(self):
        _, _, probs = run("A,Н,,,,10,,,ftp://x/1.jpg,Г,,,,\n")
        msgs = " ".join(m for _, _, m in probs)
        self.assertIn("description is required", msgs)
        self.assertIn("must start with http", msgs)

    def test_groups_are_numbered_and_default(self):
        p, g, probs = run("A,Н,,О,,10,,,https://x/1.jpg,Лежаки,,,,\nB,Н,,О,,10,,,https://x/1.jpg,Одяг,,,,\nC,Н,,О,,10,,,https://x/1.jpg,Лежаки,,,,\nD,Н,,О,,10,,,https://x/1.jpg,,,,,\n")
        self.assertEqual([x["Номер_групи"] for x in p], [1, 2, 1, 3])
        self.assertEqual([r[1] for r in g], ["Лежаки", "Одяг", "Без групи"])

    def test_groups_come_only_from_exported_rows(self):
        p, g, _ = run("A,Н,,,,10,,,https://x/1.jpg,Лише для помилкового,,,,\nB,Н,,О,,10,,,https://x/1.jpg,Добрий,,,,\n")
        self.assertEqual([x["Код_товару"] for x in p], ["B"])
        self.assertEqual([r[1] for r in g], ["Добрий"])

    def test_parameters_become_blocks(self):
        p, _, _ = run("A,Н,,О,,10,,,https://x/1.jpg,Г,,,M,2.5\nB,Н,,О,,10,,,https://x/1.jpg,Г,,,,\n")
        self.assertEqual(p[0]["_chars"], [("Розмір", "", "M"), ("Вага", "кг", "2.5")])
        header, data = to_sheets(p, [])["Export Products Sheet"]
        self.assertEqual(header[-6:], ["Назва_Характеристики", "Одиниця_виміру_Характеристики", "Значення_Характеристики"] * 2)
        self.assertEqual(data[0][-3:], ["Вага", "кг", "2.5"])
        self.assertEqual(data[1][-3:], ["", "", ""])


class Files(unittest.TestCase):
    def test_xlsx_structure_and_xml_safety(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.xlsx")
            write_xlsx(path, {"A": (["h"], [["<b>&\x00x"]]), "B": (["h2"], [[1.5]])})
            z = zipfile.ZipFile(path)
            self.assertIn("xl/worksheets/sheet2.xml", z.namelist())
            xml = z.read("xl/worksheets/sheet1.xml").decode()
            self.assertIn("&lt;b&gt;&amp;x", xml)
            self.assertNotIn("\x00", xml)

    def test_cli_example(self):
        with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()):
            code = main([os.path.join(ROOT, "examples", "products.csv"), "--out", d])
            self.assertEqual(code, 0)
            self.assertEqual(sorted(os.listdir(d)), ["prom-import.xlsx", "report.md"])
            with open(os.path.join(d, "report.md"), encoding="utf-8") as f:
                rep = f.read()
            self.assertIn("exported: 2", rep)
            self.assertIn("line 4 [error]", rep)
            self.assertIn("line 5 [error]", rep)

    def test_cli_strict_and_missing_columns(self):
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([os.path.join(ROOT, "examples", "products.csv"), "--out", d, "--strict"]), 2)
            bad = os.path.join(d, "bad.csv")
            with open(bad, "w") as f:
                f.write("sku,price\nA,1\n")
            with self.assertRaises(SystemExit) as cm:
                main([bad, "--out", d])
            self.assertIn("missing columns", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
