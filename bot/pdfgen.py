from datetime import date
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONTS = Path(__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("DV", FONTS / "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVB", FONTS / "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DVB", italic="DV", boldItalic="DVB")

TYPES = {
    "kp": "Коммерческое предложение",
    "invoice": "Счёт на оплату",
    "act": "Акт выполненных работ",
}
VAT_LABELS = {"none": "Без НДС", "20in": "НДС 20% (в т.ч.)", "20top": "НДС 20%"}

_U = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_UF = ["", "одна", "две"] + _U[3:]
_TEENS = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
          "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят",
         "восемьдесят", "девяносто"]
_HUND = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот",
         "восемьсот", "девятьсот"]


def plural(n, forms):
    n = abs(n) % 100
    if 10 < n < 20:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


def _triad(n, fem):
    words = [_HUND[n // 100]]
    t = n % 100
    if 10 <= t < 20:
        words.append(_TEENS[t - 10])
    else:
        words += [_TENS[t // 10], (_UF if fem else _U)[t % 10]]
    return [w for w in words if w]


def amount_in_words(total):
    kop = round(total * 100)
    rub, kop = divmod(kop, 100)
    if rub == 0:
        words = ["ноль"]
    else:
        words = []
        scales = [(10**9, False, ("миллиард", "миллиарда", "миллиардов")),
                  (10**6, False, ("миллион", "миллиона", "миллионов")),
                  (10**3, True, ("тысяча", "тысячи", "тысяч"))]
        rest = rub
        for size, fem, forms in scales:
            n, rest = divmod(rest, size)
            if n:
                words += _triad(n, fem) + [plural(n, forms)]
        words += _triad(rest, False)
    text = " ".join(words)
    text = text[0].upper() + text[1:]
    return f"{text} {plural(rub, ('рубль', 'рубля', 'рублей'))} {kop:02d} {plural(kop, ('копейка', 'копейки', 'копеек'))}"


def money(x):
    return f"{x:,.2f}".replace(",", " ").replace(".", ",") + " ₽"


def calc(items, vat):
    sub = sum(i["qty"] * i["price"] for i in items)
    vat_sum, total = 0.0, sub
    if vat == "20in":
        vat_sum = sub * 20 / 120
    elif vat == "20top":
        vat_sum = sub * 0.2
        total = sub + vat_sum
    return sub, vat_sum, total


def build_pdf(doc_type, number, seller, client, items, vat, footer=None, doc_date=None):
    doc_date = doc_date or date.today()
    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"{TYPES[doc_type]} № {number}")
    st = ParagraphStyle("n", fontName="DV", fontSize=10, leading=14)
    small = ParagraphStyle("s", parent=st, fontSize=8, textColor=colors.grey)
    h1 = ParagraphStyle("h", parent=st, fontName="DVB", fontSize=16, leading=20, spaceAfter=4)
    bold = ParagraphStyle("b", parent=st, fontName="DVB")

    def esc(s):
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")

    story = [Paragraph(f"{TYPES[doc_type]} № {number}", h1),
             Paragraph(f"от {doc_date:%d.%m.%Y}", st), Spacer(1, 8 * mm)]
    who = "Исполнитель" if doc_type != "invoice" else "Поставщик"
    whom = "Заказчик" if doc_type != "invoice" else "Покупатель"
    parties = Table([[Paragraph(f"<b>{who}</b><br/>{esc(seller)}", st),
                      Paragraph(f"<b>{whom}</b><br/>{esc(client)}", st)]],
                    colWidths=[87 * mm, 87 * mm])
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("FONTNAME", (0, 0), (-1, -1), "DV")]))
    story += [parties, Spacer(1, 8 * mm)]

    rows = [["№", "Наименование", "Кол-во", "Цена", "Сумма"]]
    for n, i in enumerate(items, 1):
        qty = f"{i['qty']:g}".replace(".", ",")
        rows.append([str(n), Paragraph(esc(i["name"]), st), qty, money(i["price"]), money(i["qty"] * i["price"])])
    t = Table(rows, colWidths=[10 * mm, 82 * mm, 18 * mm, 32 * mm, 32 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "DV"), ("FONTNAME", (0, 0), (-1, 0), "DVB"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [t, Spacer(1, 4 * mm)]

    sub, vat_sum, total = calc(items, vat)
    tot = [["Итого:", money(sub)]]
    if vat == "none":
        tot.append(["Без НДС", ""])
    else:
        tot.append([VAT_LABELS[vat] + ":", money(vat_sum)])
    tot.append(["Всего к оплате:", money(total)])
    tt = Table(tot, colWidths=[142 * mm, 32 * mm])
    tt.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "DV"), ("FONTNAME", (0, -1), (-1, -1), "DVB"),
                            ("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 10)]))
    story += [tt, Spacer(1, 4 * mm),
              Paragraph(f"Всего наименований {len(items)}, на сумму {money(total)}", st),
              Paragraph(amount_in_words(total), bold), Spacer(1, 14 * mm)]

    if doc_type == "act":
        story.append(Paragraph("Вышеперечисленные услуги выполнены полностью и в срок. "
                               "Заказчик претензий по объёму, качеству и срокам оказания услуг не имеет.", st))
        story.append(Spacer(1, 12 * mm))
        sig = Table([[Paragraph(f"{who}: ____________", st), Paragraph(f"{whom}: ____________", st)]],
                    colWidths=[87 * mm, 87 * mm])
    else:
        sig = Table([[Paragraph(f"{who}: ____________", st)]], colWidths=[174 * mm])
    story.append(sig)
    if footer:
        story += [Spacer(1, 16 * mm), Paragraph(esc(footer), small)]
    pdf.build(story)
    return buf.getvalue(), total
