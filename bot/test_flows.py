"""Сквозные тесты диалогов бота с поддельным Telegram API (без сети)."""
import asyncio
import io
import os
import sys
import tempfile
import traceback

os.environ["DOCBLITZ_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["ADMIN_ID"] = "999"

import pymupdf
from telegram import Update
from telegram.ext import ExtBot

import bot as B
import db
from pdfgen import amount_in_words, build_pdf, calc

RESULTS = []


def check(name, cond, info=""):
    RESULTS.append((name, bool(cond), info))


class FakeBot(ExtBot):
    def __init__(self):
        super().__init__(token="1:TEST")
        with self._unfrozen():
            self.calls = []
            self._mid = 100

    async def _do_post(self, endpoint, data, **kw):
        if endpoint == "getMe":
            return {"id": 1, "is_bot": True, "first_name": "DocBlitz", "username": "DocBlitz_bot"}
        rec = {"m": endpoint, **{k: v for k, v in data.items()}}
        if endpoint == "sendDocument":
            f = data["document"]
            rec["pdf"] = f.input_file_content if hasattr(f, "input_file_content") else None
            rec["filename"] = getattr(f, "filename", None)
        self.calls.append(rec)
        if endpoint.startswith("send") or endpoint.startswith("edit") or endpoint == "forwardMessage":
            with self._unfrozen():
                self._mid += 1
            return {"message_id": self._mid, "date": 0, "chat": {"id": int(data.get("chat_id", 1)), "type": "private"},
                    "text": data.get("text", "")}
        return True


class User:
    def __init__(self, app, bot, uid):
        self.app, self.bot, self.uid, self.n = app, bot, uid, 0

    def _base(self):
        self.n += 1
        return {"message_id": self.n, "date": 0, "chat": {"id": self.uid, "type": "private"},
                "from": {"id": self.uid, "is_bot": False, "first_name": "T"}}

    async def _send(self, upd):
        start = len(self.bot.calls)
        await self.app.process_update(Update.de_json(upd, self.bot))
        return self.bot.calls[start:]

    async def text(self, t):
        m = self._base()
        m["text"] = t
        if t.startswith("/"):
            m["entities"] = [{"type": "bot_command", "offset": 0, "length": len(t.split()[0])}]
        return await self._send({"update_id": self.n, "message": m})

    async def press(self, data):
        msg = self._base()
        msg["text"] = "x"
        msg["from"] = {"id": 1, "is_bot": True, "first_name": "B"}
        return await self._send({"update_id": self.n, "callback_query": {
            "id": str(self.n), "chat_instance": "c", "data": data, "message": msg,
            "from": {"id": self.uid, "is_bot": False, "first_name": "T"}}})

    async def pay(self, payload="pro30", stars=150):
        r1 = await self._send({"update_id": self.n, "pre_checkout_query": {
            "id": "pq", "from": {"id": self.uid, "is_bot": False, "first_name": "T"}, "currency": "XTR",
            "total_amount": stars, "invoice_payload": payload}})
        if payload != "pro30":
            return r1
        m = self._base()
        m["successful_payment"] = {"currency": "XTR", "total_amount": stars, "invoice_payload": payload,
                                   "telegram_payment_charge_id": f"ch{self.uid}{self.n}",
                                   "provider_payment_charge_id": ""}
        return r1 + await self._send({"update_id": self.n, "message": m})


def texts(calls):
    return " | ".join(str(c.get("text", c.get("caption", c["m"]))) for c in calls)


def pdf_text(calls):
    for c in calls:
        if c["m"] == "sendDocument" and c.get("pdf"):
            doc = pymupdf.open(stream=c["pdf"], filetype="pdf")
            return "\n".join(p.get_text() for p in doc), len(doc), c
    return "", 0, None


SELLER = "ИП Петров Алексей Сергеевич\nИНН 771234567890\nр/с 40802810000000000001, АО «Банк», БИК 044525974"


async def make_doc(u, typ="invoice", client="ООО «Ромашка»\nИНН 7701234567",
                   items="Разработка лендинга; 1; 25000\nПоддержка; 3; 3500", vat="none", extra=None):
    await u.text("/new")
    await u.press(f"type:{typ}")
    await u.text(client)
    await u.text(items)
    await u.press(f"vat:{vat}")
    return await (u.text(extra) if extra else u.press("extra:skip"))


async def flows():
    fb = FakeBot()
    app = B.build_app(None, bot=fb)
    await app.initialize()
    await B.post_init(app)
    check("Запуск: команды и описание бота устанавливаются",
          any(c["m"] == "setMyCommands" for c in fb.calls))

    u = User(app, fb, 10)
    r = await u.text("/start")
    check("/start: приветствие и меню", "DocBlitz" in texts(r) and "reply_markup" in r[0])

    r = await u.text("/new")
    check("Новый документ без реквизитов: сначала просит реквизиты", "Реквизиты — это" in texts(r))
    r = await u.text("🗂 История")
    check("Кнопка «История» во время ввода реквизитов не сохраняется как реквизиты (баг из ручного теста)",
          db.get_seller(10) is None and "Документов пока нет" in texts(r), texts(r))
    r = await u.text("Вася")
    check("После выхода по кнопке обычный текст не считается реквизитами",
          db.get_seller(10) is None and "Не понял" in texts(r), texts(r))
    check("Непонятный текст пересылается админу", any(c["m"] == "forwardMessage" for c in r))

    await u.text("/new")
    r = await u.text("Вася")
    check("Слишком короткие реквизиты: сохраняет и советует добавить ИНН и счёт",
          db.get_seller(10) == "Вася" and "Совет" in texts(r) and "Какой документ" in texts(r))
    await u.text("/cancel")
    await u.text("⚙️ Реквизиты")
    r = await u.text(SELLER)
    check("Смена реквизитов через кнопку, без совета", db.get_seller(10) == SELLER and "Совет" not in texts(r))

    await u.text("/new")
    await u.press("type:invoice")
    await u.text("ООО «Ромашка» & <Co>\nИНН 7701234567")
    r = await u.text("просто текст без цены")
    check("Позиции без цены: понятная ошибка и повторный запрос", "Не смог разобрать" in texts(r))
    r = await u.text("Товар; abc")
    check("Цена буквами: ошибка", "Не смог разобрать" in texts(r))
    r = await u.text("Товар; 0; 100")
    check("Количество 0: ошибка", "Не смог разобрать" in texts(r))
    r = await u.text("Товар; 1; -100")
    check("Отрицательная цена: ошибка", "Не смог разобрать" in texts(r))
    r = await u.text("Разработка лендинга; 1; 25 000 ₽\n\nНастройка рекламы; 12000,50\nПоддержка | 3 | 3500 руб.")
    check("Пробелы, ₽, «руб.», запятая, пустые строки, разделитель |: принимаются", "НДС?" in texts(r), texts(r))
    r = await u.press("vat:20top")
    check("После НДС: шаг скидки и комментария с кнопкой «Пропустить»", "Пропустить" in str(r))
    r = await u.press("extra:skip")
    txt, pages, c = pdf_text(r)
    check("Счёт с НДС сверху: PDF отправлен", c is not None)
    check("PDF: реквизиты, клиент со спецсимволами, сумма 2 позиций + НДС",
          "ИП Петров" in txt and "Ромашка» & <Co>" in txt and "57 000,60" in txt, txt[:300])
    check("PDF: сумма прописью", "Пятьдесят семь тысяч рублей 60 копеек" in txt)
    check("PDF: подпись @DocBlitz_bot для бесплатного тарифа", "@DocBlitz_bot" in txt and "Telegram" not in txt)
    check("Имя файла без запрещённых символов", c and "/" not in c["filename"] and '"' not in c["filename"], c and c["filename"])
    check("Подпись к файлу: остаток бесплатных", "Осталось бесплатных в этом месяце: 4" in c["caption"])

    await u.press("vat:none")
    r = await u.press("extra:skip")
    check("Повторное нажатие старой кнопки НДС не создаёт дубль и не роняет бота",
          not any(x["m"] == "sendDocument" for x in r) and len(db.history(10)) == 1)

    r = await make_doc(u, "invoice")
    txt, _, _ = pdf_text(r)
    check("Нумерация счетов растёт: № 2", "Счёт на оплату № 2" in txt)
    r = await make_doc(u, "act", vat="20in")
    txt, _, _ = pdf_text(r)
    check("Акт: свой номер № 1, две подписи, НДС в т.ч.",
          "Акт выполненных работ № 1" in txt and "Заказчик: ____" in txt and "в т.ч." in txt)
    r = await make_doc(u, "kp", vat="20top", extra="Скидка 10%\nСрок: 10 рабочих дней.\nПредоплата 50%.")
    txt, _, _ = pdf_text(r)
    check("КП со скидкой 10% и комментарием: скидка до НДС, итог 38 340 ₽",
          "Коммерческое предложение № 1" in txt and "Скидка 10%" in txt and "38 340,00" in txt
          and "Срок: 10 рабочих дней." in txt and "Предоплата 50%." in txt, txt[-400:])

    long_items = "\n".join(f"Очень длинное название услуги номер {i} с подробным описанием работ, "
                           f"которое не помещается в одну строку таблицы; {i}; {i * 1000}" for i in range(1, 61))
    r = await make_doc(u, "invoice", items=long_items)
    txt, pages, _ = pdf_text(r)
    check("60 позиций с длинными названиями: многостраничный PDF без падения", pages >= 2, f"страниц: {pages}")
    check("Лимит: после 5 документов бесплатных 0", db.used_this_month(10) == 5)

    r = await u.text("/new")
    check("6-й документ: предлагает Pro и выставляет счёт на 150 звёзд",
          any(x["m"] == "sendInvoice" and x["currency"] == "XTR" and "150" in str(x["prices"]) for x in r)
          and "закончились" in texts(r))

    r = await u.pay("fake")
    check("Оплата с чужим payload отклоняется", any(x["m"] == "answerPreCheckoutQuery" and not x["ok"] for x in r))
    r = await u.pay()
    check("Оплата Stars: Pro включается, админ получает уведомление",
          db.is_pro(10) and any(x["m"] == "sendMessage" and x["chat_id"] == 999 for x in r), texts(r))
    r = await make_doc(u)
    txt, _, c = pdf_text(r)
    check("Pro: документ сверх лимита создаётся, без подписи бота", c and "@DocBlitz_bot" not in txt)
    until = db.pro_until(10)
    await u.pay()
    check("Повторная оплата продлевает Pro на 30 дней", round((db.pro_until(10) - until) / 86400) == 30)

    r = await u.text("🗂 История")
    check("История показывает документы", texts(r).count("₽") >= 5)
    r = await u.text("/stats")
    check("/stats недоступна обычному пользователю", not r)
    adm = User(app, fb, 999)
    r = await adm.text("/stats")
    check("/stats для админа: пользователи, документы, звёзды", "Звёзд получено: 300" in texts(r), texts(r))

    u2 = User(app, fb, 20)
    await u2.text("/new")
    await u2.text(SELLER)
    await u2.press("type:invoice")
    r = await u2.text("/demo")
    check("Команда /demo посреди диалога присылает пример", any(x["m"] == "sendDocument" for x in r))
    r = await u2.press("vat:none")
    check("Кнопка из прерванного диалога ничего не ломает", not any(x["m"] == "sendDocument" for x in r))
    check("Данные разных пользователей не смешиваются", db.history(20) == [] and len(db.history(10)) == 6)

    u3 = User(app, fb, 30)
    await u3.text("/settings")
    await u3.text("ИП Эмодзи 😀 Тестов\nИНН 1")
    r = await make_doc(u3, client="Клиент 🚀", items="Услуга ✨; 1; 1000")
    txt, _, c = pdf_text(r)
    check("Эмодзи вырезаются из PDF, текст остаётся", c is not None and "😀" not in txt and "ИП Эмодзи Тестов" in txt
          and "Услуга" in txt, txt[:200])
    await app.shutdown()


def unit():
    cases = {0: "Ноль рублей 00 копеек", 0.99: "Ноль рублей 99 копеек", 1: "Один рубль 00 копеек",
             2: "Два рубля 00 копеек", 11: "Одиннадцать рублей 00 копеек", 21: "Двадцать один рубль 00 копеек",
             111: "Сто одиннадцать рублей 00 копеек", 1000: "Одна тысяча рублей 00 копеек",
             2000: "Две тысячи рублей 00 копеек", 5000: "Пять тысяч рублей 00 копеек",
             21000: "Двадцать одна тысяча рублей 00 копеек",
             1_000_000: "Один миллион рублей 00 копеек",
             1_234_567.89: "Один миллион двести тридцать четыре тысячи пятьсот шестьдесят семь рублей 89 копеек",
             2_000_000_001: "Два миллиарда один рубль 00 копеек", 10.01: "Десять рублей 01 копейка",
             3.02: "Три рубля 02 копейки"}
    bad = [f"{k} → «{amount_in_words(k)}»" for k, v in cases.items() if amount_in_words(k) != v]
    check(f"Сумма прописью: {len(cases)} случаев (0, копейки, 11, 21, тысячи, миллионы, миллиарды)", not bad, "; ".join(bad))
    items = [{"name": "a", "qty": 1, "price": 100}]
    check("НДС: без / 20% в т.ч. / 20% сверху",
          calc(items, "none") == (100, 0, 100) and round(calc(items, "20in")[1], 2) == 16.67
          and calc(items, "20top")[2] == 120)
    check("Дробное количество 1,5 и цена с копейками", B.parse_items("Часы; 1,5; 999,99")[0] == {"name": "Часы", "qty": 1.5, "price": 999.99})
    check("Цена 0 допускается (бесплатная позиция)", B.parse_items("Бонус; 0")[0]["price"] == 0)
    check("Разбор доп. шага: «скидка 5,5 %» + комментарий; комментарий без скидки",
          B.parse_extra("скидка 5,5 %\nОплата в течение 3 дней") == (5.5, "Оплата в течение 3 дней")
          and B.parse_extra("Скидка постоянным клиентам") == (0, "Скидка постоянным клиентам"))
    check("Скидка больше 100% ограничивается 100%", B.parse_extra("скидка 150")[0] == 100)
    pdf, _ = build_pdf("invoice", 1, "", "", [{"name": "x", "qty": 1, "price": 1}], "none")
    check("Пустые реквизиты и клиент: PDF всё равно строится", pdf.startswith(b"%PDF"))


def report():
    ok = sum(r[1] for r in RESULTS)
    lines = [f"ОТЧЁТ: АВТОТЕСТЫ @DocBlitz_bot\nПройдено {ok} из {len(RESULTS)}\n"]
    for name, passed, info in RESULTS:
        lines.append(("✅ " if passed else "❌ ") + name + ("" if passed or not info else f"\n   → {info[:200]}"))
    return "\n".join(lines), ok == len(RESULTS)


if __name__ == "__main__":
    unit()
    try:
        asyncio.run(flows())
    except Exception:
        check("Сценарии выполнились без исключений", False, traceback.format_exc()[-300:])
    text, all_ok = report()
    print(text)
    sys.exit(0 if all_ok else 1)
