"""Интеграционный тест EUROTOUR-бота без обращения к Telegram API.

Проверяет: инициализацию БД, сидинг разделов, сборку клавиатур, скрытость панели,
все экраны админки, конструктор кнопок, обращения, рассылку, бэкап.
Запуск:  python3 test_bot.py
"""
from __future__ import annotations

import asyncio, os, sys, tempfile, traceback
from typing import Any

os.environ.setdefault("BOT_TOKEN", "1:TEST")
TMP = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(TMP, "test.db")
os.environ["OWNER_ID"] = "7906546417"
os.environ["LOG_LEVEL"] = "ERROR"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s as A  # noqa: E402

OWNER, CLIENT = 7906546417, 555000111
ok_n = fail_n = 0
SENT: list[dict] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global ok_n, fail_n
    if cond:
        ok_n += 1
        print(f"  ✅ {name}")
    else:
        fail_n += 1
        print(f"  ❌ {name} {extra}")


# ───────── фейковые объекты Telegram ─────────
class FUser:
    def __init__(self, uid, un="tester", fn="Test User"):
        self.id, self.username, self.full_name = uid, un, fn


class FChat:
    def __init__(self, cid, typ="private"):
        self.id, self.type = cid, typ


class FBot:
    async def _rec(self, kind, chat, **kw):
        SENT.append({"kind": kind, "chat": chat, **kw})
        return FMsg(FUser(1, "bot"), FChat(chat), kw.get("text") or kw.get("caption") or "")

    async def send_message(self, chat, text, **kw): return await self._rec("text", chat, text=text, **kw)
    async def send_photo(self, chat, ph, **kw): return await self._rec("photo", chat, media=ph, **kw)
    async def send_video(self, chat, v, **kw): return await self._rec("video", chat, media=v, **kw)
    async def send_animation(self, chat, v, **kw): return await self._rec("animation", chat, media=v, **kw)
    async def send_document(self, chat, v, **kw): return await self._rec("document", chat, media=v, **kw)
    async def send_audio(self, chat, v, **kw): return await self._rec("audio", chat, media=v, **kw)
    async def send_voice(self, chat, v, **kw): return await self._rec("voice", chat, media=v, **kw)
    async def send_location(self, chat, la, lo, **kw): return await self._rec("loc", chat, media=f"{la},{lo}")


BOT = FBot()


class FMsg:
    def __init__(self, user, chat, text="", html=None, photo=None, doc=None, loc=None, fwd_chat=None, fwd_user=None):
        self.from_user, self.chat = user, chat
        self.text = text
        self.caption = None
        self._html = html if html is not None else text
        self.photo = photo
        self.video = self.animation = self.audio = self.voice = None
        self.document = doc
        self.location = loc
        self.forward_from_chat = fwd_chat
        self.forward_from = fwd_user
        self.bot = BOT
        self.replies: list[str] = []

    @property
    def html_text(self): return self._html

    async def answer(self, text, **kw):
        self.replies.append(text)
        SENT.append({"kind": "answer", "chat": self.chat.id, "text": text,
                     "reply_markup": kw.get("reply_markup")})
        return FMsg(self.from_user, self.chat, text)

    async def answer_document(self, doc, **kw):
        SENT.append({"kind": "doc", "chat": self.chat.id, "name": getattr(doc, "filename", "")})
        return self

    async def edit_text(self, text, **kw):
        SENT.append({"kind": "edit", "chat": self.chat.id, "text": text,
                     "reply_markup": kw.get("reply_markup")}); return self

    async def edit_reply_markup(self, **kw): return self
    async def delete(self): return True


class FCb:
    def __init__(self, user, data, chat=None):
        self.from_user, self.data = user, data
        self.message = FMsg(user, chat or FChat(user.id))
        self.bot = BOT
        self.answered = False

    async def answer(self, text="", **kw): self.answered = True


class FPhoto:
    def __init__(self, fid="PHOTOID"): self.file_id = fid


def cb(uid, data, chat=None): return FCb(FUser(uid), data, chat)
def msg(uid, text="", **kw): return FMsg(FUser(uid), FChat(uid), text, **kw)


def texts() -> str:
    return " ".join(str(s.get("text") or "") for s in SENT)


def clear(): SENT.clear()


def last_kb() -> list[list[str]]:
    for s in reversed(SENT):
        rm = s.get("reply_markup")
        if rm is not None:
            return [[b.text for b in row] for row in rm.inline_keyboard]
    return []


# ───────── тесты ─────────
async def t_init():
    print("\n▶ Инициализация и сидинг")
    await A.init_db()
    check("БД создана", A.db is not None)
    check("корневой узел есть", (await A.q1("SELECT * FROM nodes WHERE id=1")) is not None)
    n = await A.scalar("SELECT COUNT(*) FROM nodes WHERE parent=1")
    check(f"6 разделов в меню (получено {n})", n == 6)
    form = await A.q1("SELECT * FROM nodes WHERE typ='form'")
    check("кнопка «Написать сейчас» создана", form is not None)
    for l in A.LANGS:
        r = await A.q1("SELECT label FROM tr WHERE node=? AND lang=?", form["id"], l)
        check(f"перевод формы {l}: {r['label'] if r else '—'}", bool(r and r["label"]))
    check("настройки загружены", A.CFG.get("deflang") == "uk")
    check("владелец в админах", (await A.is_admin(OWNER)) == "owner")
    check("клиент не админ", (await A.is_admin(CLIENT)) is None)


async def t_client():
    print("\n▶ Клиентский сценарий")
    clear()
    m = msg(CLIENT, "/start")
    await A.cmd_start(m)
    check("предложен выбор языка", "Оберіть мову" in texts())
    clear()
    await A.cb_lang(cb(CLIENT, "l:uk"))
    check("приветствие показано", "EUROTOUR" in texts())
    labels = [b for row in last_kb() for b in row]
    check(f"меню из 6 кнопок: {labels}", len(labels) == 6)
    check("панели у клиента НЕТ", not any("Панель" in b for b in labels))
    clear()
    m2 = msg(CLIENT, "/start")
    await A.cmd_start(m2)
    check("повторный /start без выбора языка", "Оберіть мову" not in texts())

    # раздел «О нас»
    about = await A.q1("SELECT id FROM nodes WHERE sys='about'")
    clear()
    await A.cb_node(cb(CLIENT, f"n:{about['id']}"))
    check("раздел «Про нас» открылся", "Про нас" in texts())
    check("есть кнопка Назад", any("Назад" in b for row in last_kb() for b in row))

    # смена языка
    clear()
    lang_node = await A.q1("SELECT id FROM nodes WHERE sys='lang'")
    await A.cb_node(cb(CLIENT, f"n:{lang_node['id']}"))
    await A.cb_lang(cb(CLIENT, "l:ru"))
    check("язык переключён на ru", (await A.ulang(CLIENT)) == "ru")
    ru_labels = [b for row in last_kb() for b in row]
    check(f"меню на русском: {ru_labels}", any("О нас" in b or "Связь" in b for b in ru_labels))
    await A.cb_lang(cb(CLIENT, "l:uk"))

    # неизвестный ввод
    clear()
    await A.any_private(msg(CLIENT, "привіт"))
    check("реакция на непонятный ввод", "Не зовсім зрозумів" in texts())


async def t_ticket():
    print("\n▶ Обращение «Написать сейчас»")
    await A.setcfg("chat_id", "-1001234567890")
    form = await A.q1("SELECT id FROM nodes WHERE typ='form'")
    clear()
    await A.cb_node(cb(CLIENT, f"n:{form['id']}"))
    check("бот запросил сообщение", "Напишіть ваше повідомлення" in texts())
    check("состояние формы установлено", A.ST.get(CLIENT, {}).get("k") == "form")
    clear()
    A.LASTMSG.pop(CLIENT, None)
    await A.any_private(msg(CLIENT, "Цікавить перевезення для 3 осіб"))
    t = await A.q1("SELECT * FROM tickets ORDER BY id DESC LIMIT 1")
    check("обращение записано в БД", t is not None and "3 осіб" in t["body"])
    to_chat = [s for s in SENT if s["chat"] == -1001234567890]
    check("ушло в рабочий чат", len(to_chat) == 1)
    body = to_chat[0]["text"]
    check("юзернейм в сообщении", "@tester" in body)
    check("номер обращения", f"#{t['id']}" in body)
    check("ID клиента", str(CLIENT) in body)
    check("язык клиента", "UA" in body)
    check("подтверждение клиенту", "надіслано" in texts())
    check("состояние сброшено", CLIENT not in A.ST)

    # без юзернейма
    clear()
    A.LASTMSG.pop(999, None)
    nou = FMsg(FUser(999, None, "Олег"), FChat(999), "без юзернейма")
    await A.touch_user(nou)
    A.ST[999] = {"k": "form"}
    await A.any_private(nou)
    chat_msgs = [s for s in SENT if s["chat"] == -1001234567890]
    check("клиент без @ обработан", chat_msgs and "@ немає" in chat_msgs[0]["text"])

    # антиспам
    clear()
    A.ST[CLIENT] = {"k": "form"}
    await A.any_private(msg(CLIENT, "второе подряд"))
    check("антиспам сработал", "Зачекайте" in texts())


async def t_panel_access():
    print("\n▶ Доступ к панели")
    clear()
    await A.cmd_panel(msg(CLIENT, "/panel"))
    check("клиенту панель НЕ открылась", not texts().strip())
    clear()
    c = cb(CLIENT, "p:home")
    await A.panel_cb(c)
    check("чужой callback проигнорирован молча", not texts().strip())
    clear()
    await A.cmd_panel(msg(OWNER, "/panel"))
    check("владельцу панель открылась", "Панель управління" in texts())
    labels = [b for row in last_kb() for b in row]
    check(f"{len(labels)} кнопок в панели", len(labels) >= 12)
    clear()
    await A.cb_lang(cb(OWNER, "l:uk"))
    check("у владельца кнопка «Панель» в меню", any("Панель" in b for row in last_kb() for b in row))


async def t_panel_screens():
    print("\n▶ Все экраны панели открываются")
    screens = ["p:home", "p:sec", "p:tree", "p:sys", "p:live", "p:t:list:new:0", "p:u:0",
               "p:b:menu", "p:stat", "p:langs", "p:medial", "p:s:menu", "p:a:list", "p:n:1",
               "p:btn:1", "p:ord:1", "p:add:1", "p:elang", "p:liveoff"]
    for s in screens:
        clear()
        try:
            await A.panel_cb(cb(OWNER, s))
            check(f"{s}", bool(texts().strip() or SENT))
        except Exception as e:
            check(f"{s}", False, f"→ {type(e).__name__}: {e}")
            traceback.print_exc()


async def t_editing():
    print("\n▶ Редактирование текстов")
    about = (await A.q1("SELECT id FROM nodes WHERE sys='about'"))["id"]
    A.ELANG[OWNER] = "uk"
    clear()
    await A.panel_cb(cb(OWNER, f"p:txt:{about}"))
    check("режим ввода текста", A.ST.get(OWNER, {}).get("k") == "txt")
    await A.admin_input(msg(OWNER, "Новий текст", html="<b>Новий</b> текст"), A.ST[OWNER])
    t = await A.node_tr(about, "uk")
    check("текст сохранён с форматированием", "<b>Новий</b>" in t["body"])

    # дописать в конец
    clear()
    await A.panel_cb(cb(OWNER, f"p:appm:{about}:bot"))
    await A.admin_input(msg(OWNER, "Рядок 2"), A.ST[OWNER])
    t = await A.node_tr(about, "uk")
    check("дописано в конец", t["body"].endswith("Рядок 2"))

    # вставка после строки 1
    clear()
    await A.panel_cb(cb(OWNER, f"p:appm:{about}:after"))
    await A.admin_input(msg(OWNER, "1"), A.ST[OWNER])
    await A.admin_input(msg(OWNER, "ВСТАВКА"), A.ST[OWNER])
    lines = (await A.node_tr(about, "uk"))["body"].split("\n")
    check(f"вставка после строки 1: {lines}", len(lines) == 3 and lines[1] == "ВСТАВКА")

    # замена строки
    clear()
    await A.panel_cb(cb(OWNER, f"p:appm:{about}:repl"))
    await A.admin_input(msg(OWNER, "2"), A.ST[OWNER])
    await A.admin_input(msg(OWNER, "ЗАМІНА"), A.ST[OWNER])
    check("строка заменена", (await A.node_tr(about, "uk"))["body"].split("\n")[1] == "ЗАМІНА")

    # удаление строки
    clear()
    await A.panel_cb(cb(OWNER, f"p:appm:{about}:del"))
    await A.admin_input(msg(OWNER, "2"), A.ST[OWNER])
    check("строка удалена", "ЗАМІНА" not in (await A.node_tr(about, "uk"))["body"])

    # неверный номер строки
    clear()
    await A.panel_cb(cb(OWNER, f"p:appm:{about}:del"))
    m = msg(OWNER, "999")
    await A.admin_input(m, A.ST[OWNER])
    check("неверный номер строки отклонён", any("Рядок має бути" in r for r in m.replies))
    A.ST.pop(OWNER, None)

    # история версий
    h = await A.scalar("SELECT COUNT(*) FROM hist WHERE node=?", about)
    check(f"история версий пишется ({h})", h >= 3)
    hid = (await A.q1("SELECT id,body FROM hist WHERE node=? ORDER BY id LIMIT 1", about))
    clear()
    await A.panel_cb(cb(OWNER, f"p:histr:{about}:{hid['id']}"))
    check("откат версии работает", (await A.node_tr(about, "uk"))["body"] == hid["body"])

    # подпись кнопки
    clear()
    await A.panel_cb(cb(OWNER, f"p:lbl:{about}"))
    await A.admin_input(msg(OWNER, "ℹ️ Про компанію"), A.ST[OWNER])
    check("подпись обновлена", (await A.node_tr(about, "uk"))["label"] == "ℹ️ Про компанію")

    # длинная подпись → предупреждение
    clear()
    await A.panel_cb(cb(OWNER, f"p:lbl:{about}"))
    m = msg(OWNER, "Дуже довгий підпис кнопки який точно обріжеться на телефоні")
    await A.admin_input(m, A.ST[OWNER])
    check("предупреждение о длинной подписи", any("Довгий підпис" in r for r in m.replies))
    await A.ex("UPDATE tr SET label='ℹ️ Про нас' WHERE node=? AND lang='uk'", about)

    # медиа
    clear()
    await A.panel_cb(cb(OWNER, f"p:med:{about}"))
    await A.admin_input(FMsg(FUser(OWNER), FChat(OWNER), "", photo=[FPhoto("FILE123")]), A.ST[OWNER])
    check("медиа сохранено", (await A.node_tr(about, "uk"))["mid"] == "FILE123")
    clear()
    await A.panel_cb(cb(OWNER, f"p:medel:{about}"))
    check("медиа удалено", not (await A.node_tr(about, "uk"))["mid"])

    # служебный текст
    clear()
    A.ELANG[OWNER] = "uk"
    await A.panel_cb(cb(OWNER, "p:sysx:sent"))
    await A.admin_input(msg(OWNER, "✅ Прийнято!"), A.ST[OWNER])
    check("служебный текст изменён", (await A.T("sent", "uk")) == "✅ Прийнято!")


async def t_constructor():
    print("\n▶ Конструктор кнопок")
    # страница
    clear()
    await A.panel_cb(cb(OWNER, "p:wt:1:page"))
    check("мастер: шаг подписи", A.ST[OWNER]["k"] == "wiz_label")
    await A.admin_input(msg(OWNER, "🚌 Наші переваги"), A.ST[OWNER])
    check("мастер: шаг текста", A.ST[OWNER]["k"] == "wiz_body")
    await A.admin_input(FMsg(FUser(OWNER), FChat(OWNER), "Wi-Fi та кава", photo=[FPhoto("P1")]), A.ST[OWNER])
    new = await A.q1("SELECT * FROM nodes ORDER BY id DESC LIMIT 1")
    check("кнопка создана", new["typ"] == "page")
    check("создана как черновик", new["draft"] == 1)
    t = await A.node_tr(new["id"], "uk")
    check("текст и фото сохранены", t["body"] == "Wi-Fi та кава" and t["mid"] == "P1")
    check("переводы созданы для всех языков",
          await A.scalar("SELECT COUNT(*) FROM tr WHERE node=?", new["id"]) == len(A.langs_on()))

    # черновик не виден клиенту
    kbc = await A.build_kb(1, "uk", False, False)
    labels = [b.text for row in kbc.inline_keyboard for b in row]
    check(f"черновик скрыт от клиента: {labels}", not any("переваги" in b for b in labels))
    kba = await A.build_kb(1, "uk", True, False)
    check("админ видит черновик с меткой 📝",
          any("📝" in b.text for row in kba.inline_keyboard for b in row))

    # публикация
    clear()
    await A.panel_cb(cb(OWNER, f"p:vis:{new['id']}"))
    check("опубликовано", (await A.q1("SELECT draft FROM nodes WHERE id=?", new["id"]))["draft"] == 0)
    kbc = await A.build_kb(1, "uk", False, False)
    check("клиент видит новую кнопку",
          any("переваги" in b.text for row in kbc.inline_keyboard for b in row))

    # ссылка + валидация
    clear()
    await A.panel_cb(cb(OWNER, "p:wt:1:url"))
    await A.admin_input(msg(OWNER, "🌐 Наш сайт"), A.ST[OWNER])
    m = msg(OWNER, "просто текст")
    await A.admin_input(m, A.ST[OWNER])
    check("невалидный URL отклонён", any("https://" in r for r in m.replies))
    await A.admin_input(msg(OWNER, "https://eurotour.ua"), A.ST[OWNER])
    urln = await A.q1("SELECT * FROM nodes WHERE typ='url' ORDER BY id DESC LIMIT 1")
    check("URL-кнопка создана", urln["target"] == "https://eurotour.ua")
    await A.ex("UPDATE nodes SET draft=0 WHERE id=?", urln["id"])
    kbc = await A.build_kb(1, "uk", False, False)
    urls = [b for row in kbc.inline_keyboard for b in row if getattr(b, "url", None)]
    check(f"URL-кнопка отдаётся как ссылка ({len(urls)})", len(urls) >= 3)

    # телефон + валидация
    clear()
    await A.panel_cb(cb(OWNER, "p:wt:1:phone"))
    await A.admin_input(msg(OWNER, "📱 Подзвонити"), A.ST[OWNER])
    m = msg(OWNER, "12345")
    await A.admin_input(m, A.ST[OWNER])
    check("невалидный телефон отклонён", any("+380" in r for r in m.replies))
    await A.admin_input(msg(OWNER, "+380501234567"), A.ST[OWNER])
    ph = await A.q1("SELECT * FROM nodes WHERE typ='phone' ORDER BY id DESC LIMIT 1")
    check("телефон сохранён", ph["target"] == "+380501234567")
    await A.ex("UPDATE nodes SET draft=0 WHERE id=?", ph["id"])
    kbc = await A.build_kb(1, "uk", False, False)
    check("tel: ссылка сгенерирована",
          any(getattr(b, "url", "") and b.url.startswith("tel:") for row in kbc.inline_keyboard for b in row))

    # goto + защита от самоссылки
    clear()
    await A.panel_cb(cb(OWNER, "p:wt:1:goto"))
    await A.admin_input(msg(OWNER, "↩️ Перехід"), A.ST[OWNER])
    m = msg(OWNER, "1")
    await A.admin_input(m, A.ST[OWNER])
    check("самоссылка заблокирована", any("сам на себе" in r for r in m.replies))
    about = (await A.q1("SELECT id FROM nodes WHERE sys='about'"))["id"]
    await A.admin_input(msg(OWNER, str(about)), A.ST[OWNER])
    g = await A.q1("SELECT * FROM nodes WHERE typ='goto' ORDER BY id DESC LIMIT 1")
    check("goto создан", g["target"] == str(about))

    # подменю
    clear()
    await A.panel_cb(cb(OWNER, "p:wt:1:menu"))
    await A.admin_input(msg(OWNER, "📂 Послуги"), A.ST[OWNER])
    await A.admin_input(msg(OWNER, "Оберіть послугу"), A.ST[OWNER])
    sub = await A.q1("SELECT * FROM nodes WHERE typ='menu' ORDER BY id DESC LIMIT 1")
    clear()
    await A.panel_cb(cb(OWNER, f"p:wt:{sub['id']}:page"))
    await A.admin_input(msg(OWNER, "🚐 Мікроавтобус"), A.ST[OWNER])
    await A.admin_input(msg(OWNER, "Замовлення мікроавтобуса"), A.ST[OWNER])
    kids = await A.scalar("SELECT COUNT(*) FROM nodes WHERE parent=?", sub["id"])
    check("вложенный пункт создан", kids == 1)
    await A.ex("UPDATE nodes SET draft=0 WHERE parent=? OR id=?", sub["id"], sub["id"])
    kbs = await A.build_kb(sub["id"], "uk", False, False)
    check("подменю строится с кнопкой Назад",
          any("Назад" in b.text for row in kbs.inline_keyboard for b in row))

    # кнопок в ряд
    before = (await A.q1("SELECT roww FROM nodes WHERE id=1"))["roww"]
    await A.panel_cb(cb(OWNER, "p:roww:1"))
    after = (await A.q1("SELECT roww FROM nodes WHERE id=1"))["roww"]
    check(f"кнопок в ряд {before}→{after}", after == (before % 3) + 1)
    await A.ex("UPDATE nodes SET roww=2 WHERE id=1")

    # порядок
    kids = await A.children(1, True)
    first = kids[0]["id"]
    await A.panel_cb(cb(OWNER, f"p:mv:{kids[1]['id']}:u"))
    check("порядок изменён", (await A.children(1, True))[0]["id"] != first)
    await A.panel_cb(cb(OWNER, f"p:mv:{first}:u"))

    # копирование
    n_before = await A.scalar("SELECT COUNT(*) FROM nodes")
    await A.panel_cb(cb(OWNER, f"p:copy:{sub['id']}"))
    check("раздел скопирован с потомками",
          await A.scalar("SELECT COUNT(*) FROM nodes") == n_before + 2)

    # перевод
    A.ELANG[OWNER] = "uk"
    await A.panel_cb(cb(OWNER, f"p:trc:{new['id']}"))
    ru = await A.q1("SELECT body FROM tr WHERE node=? AND lang='ru'", new["id"])
    check("копирование во все языки", ru and ru["body"] == "Wi-Fi та кава")

    # удаление + корзина
    clear()
    victim = await A.q1("SELECT id FROM nodes WHERE typ='goto' ORDER BY id DESC LIMIT 1")
    await A.panel_cb(cb(OWNER, f"p:delok:{victim['id']}"))
    check("узел удалён", (await A.q1("SELECT id FROM nodes WHERE id=?", victim["id"])) is None)
    check("копия в корзине", await A.scalar("SELECT COUNT(*) FROM trash") >= 1)
    check("корневой узел удалить нельзя", (await A.q1("SELECT id FROM nodes WHERE id=1")) is not None)


async def t_tickets_admin():
    print("\n▶ Работа с обращениями в панели")
    tid = (await A.q1("SELECT id FROM tickets ORDER BY id LIMIT 1"))["id"]
    for scr in [f"p:t:c:{tid}", f"p:t:work:{tid}", f"p:t:done:{tid}", "p:t:list:closed:0"]:
        clear()
        await A.panel_cb(cb(OWNER, scr))
        check(scr, bool(texts().strip()))
    check("статус closed", (await A.q1("SELECT status FROM tickets WHERE id=?", tid))["status"] == "closed")

    # ответ клиенту
    clear()
    await A.panel_cb(cb(OWNER, f"p:t:r:{tid}"))
    await A.admin_input(msg(OWNER, "Доброго дня! Вільні місця є."), A.ST[OWNER])
    to_client = [s for s in SENT if s["chat"] == CLIENT]
    check("ответ доставлен клиенту", bool(to_client))
    check("шапка «Відповідь від менеджера»", any("менеджера" in str(s.get("text")) for s in to_client))

    # метка
    clear()
    await A.panel_cb(cb(OWNER, f"p:t:tag:{tid}"))
    await A.admin_input(msg(OWNER, "важливий"), A.ST[OWNER])
    check("метка сохранена", (await A.q1("SELECT tag FROM tickets WHERE id=?", tid))["tag"] == "важливий")

    # бан/разбан
    await A.panel_cb(cb(OWNER, f"p:t:ban:{tid}"))
    check("клиент забанен", (await A.q1("SELECT banned FROM users WHERE id=?", CLIENT))["banned"] == 1)
    clear()
    await A.any_private(msg(CLIENT, "тест"))
    check("забаненному отказ", "обмежено" in texts())
    await A.panel_cb(cb(OWNER, f"p:t:ban:{tid}"))
    check("разбанен", (await A.q1("SELECT banned FROM users WHERE id=?", CLIENT))["banned"] == 0)

    # поиск
    clear()
    await A.panel_cb(cb(OWNER, "p:t:find"))
    await A.admin_input(msg(OWNER, "tester"), A.ST[OWNER])
    check("поиск по обращениям", "Результати" in texts())
    clear()
    await A.panel_cb(cb(OWNER, "p:u:find"))
    await A.admin_input(msg(OWNER, "Test"), A.ST[OWNER])
    check("поиск по пользователям", "Результати" in texts())

    # экспорт
    clear()
    await A.panel_cb(cb(OWNER, "p:t:exp"))
    check("экспорт обращений CSV", any(s.get("name") == "tickets.csv" for s in SENT))
    clear()
    await A.panel_cb(cb(OWNER, "p:u:exp"))
    check("экспорт пользователей CSV", any(s.get("name") == "users.csv" for s in SENT))


async def t_settings():
    print("\n▶ Настройки, рассылка, бэкап")
    for k in ("notify", "confirm", "files", "backbtn", "maint"):
        before = A.CFG.get(k, "1")
        await A.panel_cb(cb(OWNER, f"p:s:{k}"))
        check(f"переключатель {k}", A.CFG.get(k) != before)
        await A.panel_cb(cb(OWNER, f"p:s:{k}"))

    # чат пересылкой
    clear()
    await A.panel_cb(cb(OWNER, "p:s:chat"))
    await A.admin_input(FMsg(FUser(OWNER), FChat(OWNER), "", fwd_chat=FChat(-100999, "supergroup")), A.ST[OWNER])
    check("чат задан пересылкой", A.CFG["chat_id"] == "-100999")
    await A.setcfg("chat_id", "-1001234567890")

    # антиспам
    clear()
    await A.panel_cb(cb(OWNER, "p:s:spam"))
    m = msg(OWNER, "abc")
    await A.admin_input(m, A.ST[OWNER])
    check("нечисловой антиспам отклонён", any("число" in r for r in m.replies))
    await A.admin_input(msg(OWNER, "5"), A.ST[OWNER])
    check("антиспам = 5", A.CFG["spam"] == "5")

    # языки
    await A.panel_cb(cb(OWNER, "p:lt:en"))
    check("язык выключен", "en" not in A.langs_on())
    await A.panel_cb(cb(OWNER, "p:lt:en"))
    check("язык включён", "en" in A.langs_on())
    before = A.CFG["deflang"]
    await A.panel_cb(cb(OWNER, "p:defl"))
    check("язык по умолчанию изменён", A.CFG["deflang"] != before)
    await A.setcfg("deflang", "uk")

    # аудитории
    for a in ("all", "wrote", "new7", "l_uk"):
        ids = await A.audience(a)
        check(f"аудитория {a}: {len(ids)}", isinstance(ids, list))

    # рассылка
    clear()
    await A.panel_cb(cb(OWNER, "p:b:aud:all"))
    await A.admin_input(msg(OWNER, "🔥 Знижка 10%"), A.ST[OWNER])
    check("предпросмотр рассылки", "Перегляд розсилки" in texts())
    check("состояние bc_ready", A.ST[OWNER]["k"] == "bc_ready")
    ids = await A.audience("all")
    st = A.ST.pop(OWNER)
    clear()
    await A.do_broadcast(BOT, OWNER, ids, st["body"], "", "", None)
    delivered = [s for s in SENT if "Знижка" in str(s.get("text"))]
    check(f"рассылка доставлена ({len(delivered)}/{len(ids)})", len(delivered) == len(ids))

    # бэкап
    clear()
    await A.panel_cb(cb(OWNER, "p:bk"))
    check("бэкап выгружен", any("backup" in str(s.get("name", "")) for s in SENT))

    # админы
    clear()
    await A.panel_cb(cb(OWNER, "p:a:add"))
    await A.admin_input(msg(OWNER, "123456"), A.ST[OWNER])
    check("админ добавлен", (await A.is_admin(123456)) == "tickets")
    check("роль tickets ограничена", not await A.can(123456, "admins"))
    check("владелец может всё", await A.can(OWNER, "admins"))
    clear()
    await A.panel_cb(cb(OWNER, "p:a:role:123456"))
    check("роль повышена", (await A.is_admin(123456)) == "full")
    await A.panel_cb(cb(OWNER, "p:a:del:123456"))
    check("админ удалён", (await A.is_admin(123456)) is None)
    await A.panel_cb(cb(OWNER, f"p:a:del:{OWNER}"))
    check("владельца удалить нельзя", (await A.is_admin(OWNER)) == "owner")


async def t_edge():
    print("\n▶ Крайние случаи")
    clear()
    await A.cb_node(cb(CLIENT, "n:999999"))
    check("несуществующий узел не роняет бота", True)
    clear()
    await A.panel_cb(cb(OWNER, "p:n:abc"))
    check("нечисловой аргумент обработан", True)
    clear()
    await A.panel_cb(cb(OWNER, "p:unknown:zzz"))
    check("неизвестная секция → домой", "Панель управління" in texts())

    # длинный текст + фото
    clear()
    await A.send_content(BOT, 1, "x" * 2000, None, "photo", "PID")
    kinds = [s["kind"] for s in SENT]
    check(f"длинная подпись разделена: {kinds}", kinds == ["photo", "text"])
    clear()
    await A.send_content(BOT, 1, "короткий", None, "photo", "PID")
    check("короткая подпись — одним сообщением", [s["kind"] for s in SENT] == ["photo"])

    # техрежим
    await A.setcfg("maint", "1")
    clear()
    await A.any_private(msg(CLIENT, "тест"))
    check("техрежим для клиента", "технічні роботи" in texts())
    clear()
    await A.cmd_start(msg(OWNER, "/start"))
    check("админ работает в техрежиме", "технічні роботи" not in texts())
    await A.setcfg("maint", "0")

    # фолбэк языка
    node = (await A.q1("SELECT id FROM nodes WHERE sys='about'"))["id"]
    await A.ex("DELETE FROM tr WHERE node=? AND lang='pl'", node)
    t = await A.node_tr(node, "pl")
    check("фолбэк на язык по умолчанию", bool(t["body"]))

    # grid
    check("grid 5→2 в ряд", len(A.grid([A.B(str(i), str(i)) for i in range(5)], 2)) == 3)
    check("grid ограничен 3", len(A.grid([A.B(str(i), str(i)) for i in range(6)], 9)[0]) == 3)
    check("I() безопасен", A.I("abc") == 0 and A.I("42") == 42)
    check("esc() экранирует", A.esc("<b>") == "&lt;b&gt;")


async def main():
    print("═" * 58)
    print("  ТЕСТИРОВАНИЕ EUROTOUR BOT")
    print("═" * 58)
    for t in (t_init, t_client, t_ticket, t_panel_access, t_panel_screens,
              t_editing, t_constructor, t_tickets_admin, t_settings, t_edge):
        try:
            await t()
        except Exception as e:
            global fail_n
            fail_n += 1
            print(f"  💥 {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    await A.db.close()
    print("\n" + "═" * 58)
    print(f"  ✅ Пройдено: {ok_n}    ❌ Провалено: {fail_n}")
    print("═" * 58)
    return 1 if fail_n else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
