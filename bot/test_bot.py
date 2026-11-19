from pdfgen import amount_in_words, build_pdf, calc
from bot import parse_items, build_app

assert amount_in_words(45125) == "Сорок пять тысяч сто двадцать пять рублей 00 копеек", amount_in_words(45125)
assert amount_in_words(1001.5) == "Одна тысяча один рубль 50 копеек", amount_in_words(1001.5)
assert amount_in_words(2_000_000) == "Два миллиона рублей 00 копеек"
items = parse_items("Разработка лендинга; 1; 25 000\nНастройка рекламы; 12000\nПоддержка, месяц; 3; 3500,00 ₽")
assert [i["qty"] for i in items] == [1, 1, 3] and items[2]["price"] == 3500
assert calc(items, "none")[2] == 47500
assert calc(items, "20top")[2] == 57000
for bad in ["просто текст", "Товар; abc"]:
    try:
        parse_items(bad); raise SystemExit("should fail: " + bad)
    except ValueError:
        pass
pdf, total = build_pdf("act", 3, "ИП Петров\nИНН 7712", "ООО «Ромашка» & <Co>", items, "20in", footer="Создано в @test_bot")
assert pdf.startswith(b"%PDF") and total == 47500
open("/tmp/test_act.pdf", "wb").write(pdf)
build_app("123:TEST")
print("ok")
