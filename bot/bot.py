import logging
import os
import re
from datetime import datetime
from pathlib import Path

from telegram import (BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, ReplyKeyboardMarkup,
                      Update)
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, PreCheckoutQueryHandler, filters)

import db
from pdfgen import TYPES, build_pdf, money

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

HERE = Path(__file__).parent
FREE_LIMIT = 5
PRO_DAYS = 30
PRO_STARS = int(os.getenv("PRO_STARS", "150"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

SELLER, TYPE, CLIENT, ITEMS, VAT = range(5)

BTN_NEW, BTN_SELLER, BTN_HISTORY, BTN_PRO = "📄 Новый документ", "⚙️ Реквизиты", "🗂 История", "⭐ Pro"
MENU = ReplyKeyboardMarkup([[BTN_NEW], [BTN_SELLER, BTN_HISTORY, BTN_PRO]], resize_keyboard=True)

SELLER_HELP = ("Реквизиты — это ваши данные как исполнителя: имя или название ИП, ИНН, банковский счёт, "
               "контакты. Они печатаются в документе, чтобы клиент знал, кому и куда платить.\n\n"
               "Отправьте их одним сообщением, каждая строка отдельно, например:\n\n"
               "ИП Петров Алексей Сергеевич\nИНН 771234567890\n"
               "р/с 40802810000000000001, АО «Банк», БИК 044525974\n+7 900 123-45-67, petrov@mail.ru\n\n"
               "Их можно поменять в любой момент кнопкой «Реквизиты».")
ITEMS_HELP = ("Отправьте позиции, каждая с новой строки, в формате\n"
              "<code>Название; количество; цена</code>\n\nНапример:\n"
              "<code>Разработка лендинга; 1; 25000\nПоддержка сайта, месяц; 3; 3500</code>\n\n"
              "Если количество 1, можно просто <code>Название; цена</code>")


def num(s):
    s = re.sub(r"[\s₽]|руб\.?|р\.", "", s.lower()).replace(",", ".")
    return float(s)


def parse_items(text):
    items = []
    for line in filter(None, (l.strip() for l in text.splitlines())):
        parts = [p.strip() for p in re.split(r"[;|]", line)]
        if len(parts) == 2:
            name, qty, price = parts[0], 1.0, num(parts[1])
        elif len(parts) >= 3:
            name, qty, price = parts[0], num(parts[1]), num(parts[2])
        else:
            raise ValueError(line)
        if not name or qty <= 0 or price < 0:
            raise ValueError(line)
        items.append({"name": name, "qty": qty, "price": price})
    if not items:
        raise ValueError(text)
    return items


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я DocBlitz — делаю коммерческие предложения, счета и акты в PDF за минуту.\n\n"
        "Как это работает:\n1. Один раз указываете свои реквизиты.\n"
        "2. Выбираете тип документа, клиента и позиции.\n3. Получаете готовый PDF с суммой прописью.\n\n"
        f"Бесплатно — {FREE_LIMIT} документов в месяц. Посмотреть пример: /demo",
        reply_markup=MENU)


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/new — новый документ\n/settings — реквизиты\n/history — последние документы\n"
        "/demo — пример PDF\n/pro — тариф Pro\n/paysupport — вопросы по оплате\n/cancel — отменить",
        reply_markup=MENU)


async def demo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    items = [{"name": "Разработка лендинга", "qty": 1, "price": 25000},
             {"name": "Настройка рекламы в Яндекс.Директ", "qty": 1, "price": 12000},
             {"name": "Поддержка сайта, месяц", "qty": 3, "price": 3500}]
    pdf, _ = build_pdf("invoice", 1, "ИП Петров Алексей Сергеевич\nИНН 771234567890\n"
                       "р/с 40802810000000000001, АО «Банк», БИК 044525974",
                       "ООО «Ромашка»\nИНН 7701234567", items, "none",
                       footer=f"Пример документа из Telegram-бота @{ctx.bot.username}")
    await update.message.reply_document(pdf, filename="Пример_счёта.pdf",
                                        caption="Так выглядит счёт. Создать свой: /new")


async def settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cur = db.get_seller(update.effective_user.id)
    text = (f"Текущие реквизиты:\n\n{cur}\n\n" if cur else "") + SELLER_HELP
    ctx.user_data["after_seller"] = False
    await update.message.reply_text(text)
    return SELLER


async def got_seller(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    db.set_seller(update.effective_user.id, text)
    saved = (f"Запомнил ваши данные:\n\n{text}\n\nОни будут печататься в каждом документе в блоке «Исполнитель», "
             "вводить их заново не нужно. Изменить — кнопка «Реквизиты».")
    if len(text) < 20 or "\n" not in text:
        saved += "\n\nСовет: добавьте ИНН и банковский счёт — без них клиенту нечем оплатить счёт."
    if ctx.user_data.pop("after_seller", False):
        await update.message.reply_text(saved)
        return await ask_type(update, ctx)
    await update.message.reply_text(saved, reply_markup=MENU)
    return ConversationHandler.END


async def new_doc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not db.is_pro(uid) and db.used_this_month(uid) >= FREE_LIMIT:
        await update.message.reply_text(
            f"Бесплатные {FREE_LIMIT} документов в этом месяце закончились. "
            f"С Pro — без ограничений и без подписи бота.", reply_markup=MENU)
        await send_invoice(update, ctx)
        return ConversationHandler.END
    if not db.get_seller(uid):
        ctx.user_data["after_seller"] = True
        await update.message.reply_text("Сначала укажем ваши реквизиты — это один раз.\n\n" + SELLER_HELP)
        return SELLER
    return await ask_type(update, ctx)


async def ask_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(v, callback_data=f"type:{k}")] for k, v in TYPES.items()])
    await update.message.reply_text("Какой документ делаем?", reply_markup=kb)
    return TYPE


async def got_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["type"] = q.data.split(":")[1]
    await q.edit_message_text(f"Документ: {TYPES[ctx.user_data['type']]}")
    await q.message.reply_text("Кто клиент? Первая строка — название, дальше — ИНН, адрес, контакты "
                               "(по желанию).\n\nНапример:\nООО «Ромашка»\nИНН 7701234567")
    return CLIENT


async def got_client(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["client"] = update.message.text.strip()
    await update.message.reply_text(ITEMS_HELP, parse_mode="HTML")
    return ITEMS


async def got_items(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["items"] = parse_items(update.message.text)
    except ValueError:
        await update.message.reply_text("Не смог разобрать позиции.\n\n" + ITEMS_HELP, parse_mode="HTML")
        return ITEMS
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Без НДС", callback_data="vat:none")],
                               [InlineKeyboardButton("НДС 20% включён в цену", callback_data="vat:20in")],
                               [InlineKeyboardButton("НДС 20% сверху", callback_data="vat:20top")]])
    await update.message.reply_text("НДС?", reply_markup=kb)
    return VAT


async def got_vat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    vat = q.data.split(":")[1]
    uid = update.effective_user.id
    d = ctx.user_data
    number = db.next_number(uid, d["type"])
    pro = db.is_pro(uid)
    footer = None if pro else f"Документ создан в Telegram-боте @{ctx.bot.username}"
    pdf, total = build_pdf(d["type"], number, db.get_seller(uid), d["client"], d["items"], vat, footer=footer)
    client_name = d["client"].splitlines()[0]
    db.save_doc(uid, d["type"], number, client_name, total)
    await q.edit_message_text("Готово!")
    fname = f"{TYPES[d['type']]} №{number} {client_name}.pdf".replace("/", "-").replace('"', "")
    left = "" if pro else f"\nОсталось бесплатных в этом месяце: {max(FREE_LIMIT - db.used_this_month(uid), 0)}"
    await q.message.reply_document(pdf, filename=fname,
                                   caption=f"{TYPES[d['type']]} № {number} на {money(total)}{left}",
                                   reply_markup=MENU)
    d.clear()
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Отменено.", reply_markup=MENU)
    return ConversationHandler.END


async def history_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = db.history(update.effective_user.id)
    if not rows:
        await update.message.reply_text("Документов пока нет. Создать: /new", reply_markup=MENU)
        return
    lines = [f"{datetime.fromtimestamp(c):%d.%m} · {TYPES[t]} №{n} · {cl} · {money(tot)}"
             for t, n, cl, tot, c in rows]
    await update.message.reply_text("Последние документы:\n\n" + "\n".join(lines), reply_markup=MENU)


async def pro_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if db.is_pro(uid):
        until = datetime.fromtimestamp(db.pro_until(uid))
        await update.message.reply_text(f"Pro активен до {until:%d.%m.%Y}. Можно продлить заранее — дни сложатся.")
    else:
        await update.message.reply_text(
            f"Pro на {PRO_DAYS} дней:\n• безлимит документов\n• без подписи бота в PDF\n\n"
            f"Использовано в этом месяце: {db.used_this_month(uid)} из {FREE_LIMIT} бесплатных.")
    await send_invoice(update, ctx)


async def send_invoice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_invoice(
        chat_id=update.effective_chat.id, title=f"DocBlitz Pro на {PRO_DAYS} дней",
        description="Безлимит документов и PDF без подписи бота", payload="pro30",
        provider_token="", currency="XTR", prices=[LabeledPrice("Pro", PRO_STARS)])


async def precheckout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.pre_checkout_query
    if q.invoice_payload == "pro30":
        await q.answer(ok=True)
    else:
        await q.answer(ok=False, error_message="Неизвестный товар")


async def paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    p = update.message.successful_payment
    uid = update.effective_user.id
    db.add_pro(uid, PRO_DAYS, p.telegram_payment_charge_id, p.total_amount)
    until = datetime.fromtimestamp(db.pro_until(uid))
    await update.message.reply_text(f"Спасибо! Pro активен до {until:%d.%m.%Y}.", reply_markup=MENU)
    if ADMIN_ID:
        await ctx.bot.send_message(ADMIN_ID, f"Новая оплата Pro: {p.total_amount} ⭐ от {uid}")


async def paysupport(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Вопросы по оплате: опишите проблему ответным сообщением и приложите скриншот чека — "
        "администратор ответит в течение 24 часов. Если Pro не включился после оплаты, вернём звёзды.")


async def support_forward(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID and update.effective_user.id != ADMIN_ID:
        await update.message.forward(ADMIN_ID)
    await update.message.reply_text("Не понял команду. Выберите действие в меню или /help", reply_markup=MENU)


async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    s = db.stats()
    await update.message.reply_text(
        f"Пользователей: {s['users']}\nДокументов: {s['docs']}\nPro сейчас: {s['pro']}\nЗвёзд получено: {s['stars']}")


async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("new", "Новый документ"), BotCommand("settings", "Мои реквизиты"),
        BotCommand("history", "История документов"), BotCommand("demo", "Пример PDF"),
        BotCommand("pro", "Тариф Pro"), BotCommand("paysupport", "Вопросы по оплате"),
        BotCommand("help", "Помощь")])
    await app.bot.set_my_short_description("КП, счета и акты в PDF за минуту. Сумма прописью, НДС, история.")
    await app.bot.set_my_description(
        "Создаю коммерческие предложения, счета на оплату и акты выполненных работ в PDF.\n\n"
        f"Бесплатно {FREE_LIMIT} документов в месяц. Нажмите «Запустить».")


def build_app(token):
    app = Application.builder().token(token).post_init(post_init).build()
    text = filters.TEXT & ~filters.COMMAND
    conv = ConversationHandler(
        entry_points=[CommandHandler("new", new_doc), MessageHandler(filters.Regex(f"^{BTN_NEW}$"), new_doc),
                      CommandHandler("settings", settings),
                      MessageHandler(filters.Regex(f"^{BTN_SELLER}$"), settings)],
        states={SELLER: [MessageHandler(text, got_seller)],
                TYPE: [CallbackQueryHandler(got_type, pattern="^type:")],
                CLIENT: [MessageHandler(text, got_client)],
                ITEMS: [MessageHandler(text, got_items)],
                VAT: [CallbackQueryHandler(got_vat, pattern="^vat:")]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("demo", demo))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_HISTORY}$"), history_cmd))
    app.add_handler(CommandHandler("pro", pro_cmd))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_PRO}$"), pro_cmd))
    app.add_handler(CommandHandler("paysupport", paysupport))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, paid))
    app.add_handler(MessageHandler(text, support_forward))
    return app


def main():
    token = os.getenv("BOT_TOKEN") or (HERE / "token.txt").read_text(encoding="utf-8").strip()
    build_app(token).run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
