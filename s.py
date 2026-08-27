#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EUROTOUR Support Bot  ·  aiogram 3  ·  ОДИН ФАЙЛ, готовий до хостингу
═════════════════════════════════════════════════════════════════════

ЩО ЦЕ
  Клієнт бачить: привітання, вибір мови, розділи, контакти, кнопку
  «Написати зараз». Жодних згадок про панель.
  Адмін (ADMIN_ID) бачить приховану панель: конструктор кнопок і сторінок,
  редактор текстів, медіа, звернення, користувачі, розсилка, мови,
  статистика, налаштування, адміни, бекап, живе редагування.

ЯК ЗАПУСТИТИ
  1) вставити токен нижче (або задати змінну BOT_TOKEN)
  2) python3 s.py
  Бібліотеки бот встановить сам при першому запуску.

ХОСТИНГ
  • Start command:  python3 s.py
  • Змінні: BOT_TOKEN, OWNER_ID (не обовʼязково — можна вписати в код)
  • ⚠️ ГОЛОВНЕ: підключіть постійний диск (volume) і вкажіть DB_PATH,
    напр. DB_PATH=/data/eurotour.db — інакше при редеплої дані зникнуть.
    Бот сам знайде /data, /var/data, /mnt/data, якщо вони існують.

ЗБЕРЕЖЕННЯ ДАНИХ (виправлено)
  • SQLite у режимі WAL + synchronous=FULL — записане не втрачається
    навіть при раптовому вимкненні чи kill -9
  • checkpoint при кожній зупинці та перед плановим перезапуском
  • автоматична копія БД раз на годину (3 копії по колу)

САМОПЕРЕЗАПУСК
  Рівно раз на 6 годин процес тихо перезапускається (профілактика
  витоків памʼяті). Дані зберігаються, повідомлень нікому не надсилається.
  Змінити: RESTART_HOURS=12   ·  вимкнути: RESTART_HOURS=0
"""
from __future__ import annotations

import asyncio, csv, hashlib, html, io, json, logging, os, re, signal, sys, time
from contextlib import suppress
from typing import Any, Optional, Sequence

# ════════════════ АВТОВСТАНОВЛЕННЯ БІБЛІОТЕК ════════════════
# Скрипт сам ставить усе потрібне при першому запуску.
# Нічого встановлювати вручну не треба — просто: python3 s.py
_REQUIRED = [
    ("aiogram", "aiogram>=3.13,<4"),      # (що імпортуємо, що ставимо)
    ("aiosqlite", "aiosqlite"),
    ("aiohttp", "aiohttp"),
]


def _ensure_packages() -> None:
    """Перевіряє наявність бібліотек і ставить відсутні через pip."""
    import importlib.util
    import subprocess

    missing = [pkg for mod, pkg in _REQUIRED if importlib.util.find_spec(mod) is None]
    if not missing:
        return

    print("📦 Встановлюю потрібні бібліотеки: " + ", ".join(missing))
    print("   (це робиться лише один раз, зачекайте 10–60 секунд)\n")

    base = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q"]
    # варіанти на випадок «externally-managed-environment» чи відсутності прав
    for extra in ([], ["--break-system-packages"], ["--user"], ["--user", "--break-system-packages"]):
        try:
            subprocess.check_call(base + extra + missing)
            break
        except subprocess.CalledProcessError:
            continue
        except Exception as e:                       # pip узагалі недоступний
            print(f"⚠️  pip не спрацював: {e}")
            break

    # оновити шляхи, щоб щойно встановлене стало видимим без перезапуску
    import site
    with suppress(Exception):
        for p in site.getsitepackages() + [site.getusersitepackages()]:
            if p not in sys.path:
                sys.path.append(p)
    importlib.invalidate_caches()

    still = [pkg for mod, pkg in _REQUIRED if importlib.util.find_spec(mod) is None]
    if still:
        raise SystemExit(
            "\n❌ Не вдалося встановити: " + ", ".join(still) + "\n\n"
            "Встановіть вручну однією командою:\n\n"
            '    pip install "aiogram>=3.13,<4" aiosqlite aiohttp\n\n'
            "Якщо помилка «externally-managed-environment», додайте --break-system-packages\n")
    print("✅ Бібліотеки встановлено.\n")


_ensure_packages()
# ════════════════════════════════════════════════════════════

import aiosqlite
from aiohttp import ClientError
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import (TelegramBadRequest, TelegramConflictError, TelegramForbiddenError,
                                TelegramNetworkError, TelegramRetryAfter, TelegramServerError,
                                TelegramUnauthorizedError)
from aiogram.filters import Command, CommandStart
from aiogram.types import (BotCommand, BotCommandScopeChat, BufferedInputFile, CallbackQuery,
                           KeyboardButton, KeyboardButtonRequestChat, ReplyKeyboardMarkup,
                           ReplyKeyboardRemove,
                           InlineKeyboardButton, InlineKeyboardMarkup, Message)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                                                                          ║
# ║   👇👇👇   ВСТАВТЕ ТОКЕН БОТА СЮДИ, МІЖ ЛАПКАМИ   👇👇👇                 ║
# ║                                                                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

TOKEN = ""   # ← на GitHub береться з секрету BOT_TOKEN (Settings → Secrets)

ADMIN_ID = 7906546417   # ← ваш Telegram ID (тільки він бачить панель)

# ── ЧЕРЕЗ СКІЛЬКИ ГОДИН БОТ ТИХО ПЕРЕЗАПУСКАЄ САМ СЕБЕ ──
#    6 = кожні 6 годин рівно (дані НЕ втрачаються, нікому не пишеться)
#    0 = вимкнути самоперезапуск
RESTART_EVERY_HOURS = 6

# ┌──────────────────────────────────────────────────────────────────────────┐
# │  ПРИКЛАД, як має виглядати заповнено:                                    │
# │                                                                          │
# │      TOKEN = "8154302197:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"             │
# │      ADMIN_ID = 7906546417                                               │
# │                                                                          │
# │  Де взяти токен: Telegram → @BotFather → /newbot (або /mybots →          │
# │  оберіть бота → API Token). Скопіюйте рядок і вставте між лапками.       │
# │                                                                          │
# │  ⚠️ Токен — це пароль від бота. Нікому його не показуйте.                │
# └──────────────────────────────────────────────────────────────────────────┘

# ════════════════════════════ КОНФІГ ════════════════════════════
# Значення вище можна перевизначити змінними оточення (не обовʼязково).
BOT_TOKEN = (os.getenv("BOT_TOKEN") or TOKEN).strip()
OWNER_ID = int(os.getenv("OWNER_ID") or ADMIN_ID)


def _db_path() -> str:
    """Шлях до БД.

    ⚠️ НАЙВАЖЛИВІШЕ ДЛЯ ХОСТИНГУ: тека має ПЕРЕЖИВАТИ перезапуск і редеплой.
    Якщо БД лежить поруч із кодом, при кожному оновленні коду вона зникає
    разом з усіма налаштуваннями — саме через це «стирався весь прогрес».
    Рішення: підключіть постійний диск і задайте DB_PATH=/data/eurotour.db
    """
    if os.getenv("DB_PATH"):
        return os.getenv("DB_PATH")            # type: ignore[return-value]
    # типові постійні томи хостингів (Railway / Render / Fly / Amvera …)
    for vol in ("/data", "/var/data", "/mnt/data", "/persistent", "/storage"):
        if os.path.isdir(vol) and os.access(vol, os.W_OK):
            return os.path.join(vol, "eurotour.db")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "eurotour.db")


DB_PATH = _db_path()

# автоперезапуск раз на N годин (0 = вимкнено)
RESTART_HOURS = float(os.getenv("RESTART_HOURS") or RESTART_EVERY_HOURS)

LANGS = {"uk": "🇺🇦 Українська", "ru": "🇷🇺 Русский", "pl": "🇵🇱 Polski", "en": "🇬🇧 English"}
FLAG = {"uk": "🇺🇦", "ru": "🇷🇺", "pl": "🇵🇱", "en": "🇬🇧"}
UP = {"uk": "UA", "ru": "RU", "pl": "PL", "en": "EN"}
CAP_LIMIT, TXT_LIMIT, HIST_KEEP, BC_DELAY = 1024, 4096, 10, 0.05
ROLES = {"owner": "👑 Власник", "full": "🛠 Повний доступ", "tickets": "📨 Тільки звернення"}

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("eurotour")

db: aiosqlite.Connection = None      # type: ignore
CFG: dict[str, str] = {}             # кэш настроек
class _States(dict):
    """Стан діалогу, який САМ зберігається в БД.

    Працює як звичайний dict (ST[uid] = ..., ST.pop(uid)), але кожна зміна
    одразу пишеться в таблицю states. Тому після перезапуску людина
    продовжує з того ж місця: недописане звернення, крок редагування тощо.
    """

    def __setitem__(self, uid, val):
        super().__setitem__(uid, val)
        _persist_state(uid, val)

    def pop(self, uid, *a):
        _persist_state(uid, None)
        return super().pop(uid, *a)

    def __delitem__(self, uid):
        _persist_state(uid, None)
        super().__delitem__(uid)


ST: _States = _States()              # состояния ввода {user_id: {...}}
ELANG: dict[int, str] = {}           # язык редактирования у админа
LIVE: set[int] = set()               # админы в режиме живого редактирования
LASTMSG: dict[int, float] = {}       # антиспам

# ════════════════════════════ БАЗА ════════════════════════════
SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, parent INTEGER DEFAULT 1, typ TEXT DEFAULT 'page',
  target TEXT DEFAULT '', pos INTEGER DEFAULT 0, roww INTEGER DEFAULT 2,
  hidden INTEGER DEFAULT 0, draft INTEGER DEFAULT 0, views INTEGER DEFAULT 0, sys TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS tr(node INTEGER, lang TEXT, label TEXT DEFAULT '', body TEXT DEFAULT '',
  mtype TEXT DEFAULT '', mid TEXT DEFAULT '', machine INTEGER DEFAULT 0, PRIMARY KEY(node,lang));
-- кеш перекладів, щоб не смикати мережу двічі за той самий текст
CREATE TABLE IF NOT EXISTS trcache(h TEXT, lang TEXT, txt TEXT, PRIMARY KEY(h,lang));
CREATE TABLE IF NOT EXISTS sys(k TEXT, lang TEXT, v TEXT, PRIMARY KEY(k,lang));
CREATE TABLE IF NOT EXISTS cfg(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, uname TEXT, name TEXT, lang TEXT DEFAULT 'uk',
  created INTEGER, seen INTEGER, banned INTEGER DEFAULT 0, msgs INTEGER DEFAULT 0, lset INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, body TEXT,
  mtype TEXT DEFAULT '', mid TEXT DEFAULT '', status TEXT DEFAULT 'new', tag TEXT DEFAULT '',
  created INTEGER, mgr TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS hist(id INTEGER PRIMARY KEY AUTOINCREMENT, node INTEGER, lang TEXT,
  body TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS trash(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, data TEXT);
CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY, role TEXT DEFAULT 'full', name TEXT DEFAULT '');
-- стан діалогу (що юзер/адмін зараз вводить) — щоб прогрес не губився при перезапуску
CREATE TABLE IF NOT EXISTS states(uid INTEGER PRIMARY KEY, data TEXT, elang TEXT DEFAULT '', ts INTEGER);
"""

SYS_DEF = {
    "langsel": {"uk": "🇺🇦 <b>EUROTOUR</b>\n\nОберіть мову / Выберите язык\nChoose language / Wybierz język",
                "ru": "🇺🇦 <b>EUROTOUR</b>\n\nОберіть мову / Выберите язык\nChoose language / Wybierz język",
                "pl": "🇺🇦 <b>EUROTOUR</b>\n\nОберіть мову / Выберите язык\nChoose language / Wybierz język",
                "en": "🇺🇦 <b>EUROTOUR</b>\n\nОберіть мову / Выберите язык\nChoose language / Wybierz język"},
    "ask": {"uk": "✍️ Напишіть ваше повідомлення одним повідомленням.\nМожна текст, фото або документ.",
            "ru": "✍️ Напишите ваше сообщение одним сообщением.\nМожно текст, фото или документ.",
            "pl": "✍️ Napisz swoją wiadomość w jednej wiadomości.\nMoże być tekst, zdjęcie lub dokument.",
            "en": "✍️ Send us your message in a single message.\nText, photo or document is fine."},
    "sent": {"uk": "✅ <b>Повідомлення надіслано!</b>\nМенеджер відповість вам особисто.",
             "ru": "✅ <b>Сообщение отправлено!</b>\nМенеджер ответит вам лично.",
             "pl": "✅ <b>Wiadomość wysłana!</b>\nMenedżer odpowie osobiście.",
             "en": "✅ <b>Message sent!</b>\nOur manager will reply personally."},
    "unknown": {"uk": "Не зовсім зрозумів 🤔 Ось головне меню:", "ru": "Не совсем понял 🤔 Вот главное меню:",
                "pl": "Nie rozumiem 🤔 Oto menu główne:", "en": "I didn't get that 🤔 Here is the main menu:"},
    "blocked": {"uk": "🚫 Ваш доступ до бота обмежено.", "ru": "🚫 Ваш доступ к боту ограничен.",
                "pl": "🚫 Twój dostęp jest ograniczony.", "en": "🚫 Your access is restricted."},
    "spam": {"uk": "🐌 Зачекайте трохи перед наступним повідомленням.", "ru": "🐌 Подождите немного перед следующим сообщением.",
             "pl": "🐌 Poczekaj chwilę przed kolejną wiadomością.", "en": "🐌 Please wait a moment before sending again."},
    "maint": {"uk": "🔧 Ведуться технічні роботи. Спробуйте трохи пізніше.", "ru": "🔧 Ведутся технические работы. Попробуйте позже.",
              "pl": "🔧 Trwają prace techniczne. Spróbuj później.", "en": "🔧 Maintenance in progress. Please try later."},
    "answer": {"uk": "💬 <b>Відповідь від менеджера:</b>", "ru": "💬 <b>Ответ от менеджера:</b>",
               "pl": "💬 <b>Odpowiedź od menedżera:</b>", "en": "💬 <b>Reply from our manager:</b>"},
    "back": {"uk": "⬅️ Назад", "ru": "⬅️ Назад", "pl": "⬅️ Wstecz", "en": "⬅️ Back"},
    "home": {"uk": "🏠 Головне меню", "ru": "🏠 Главное меню", "pl": "🏠 Menu główne", "en": "🏠 Main menu"},
    "cancel": {"uk": "❌ Скасувати", "ru": "❌ Отменить", "pl": "❌ Anuluj", "en": "❌ Cancel"},
}
CFG_DEF = {"chat_id": "", "notify": "1", "confirm": "1", "files": "1", "spam": "20",
           "maint": "0", "backbtn": "1", "deflang": "uk", "langs": "uk,ru,pl,en",
           "autotr": "1"}          # автопереклад правок на інші мови

GREET = {"uk": "👋 <b>Вітаємо!</b>\n\nEUROTOUR — пасажирські перевезення Україна ⇄ Європа.\nКомфорт, пунктуальність, безпека.\n\nОберіть розділ 👇",
         "ru": "👋 <b>Добро пожаловать!</b>\n\nEUROTOUR — пассажирские перевозки Украина ⇄ Европа.\nКомфорт, пунктуальность, безопасность.\n\nВыберите раздел 👇",
         "pl": "👋 <b>Witamy!</b>\n\nEUROTOUR — przewozy pasażerskie Ukraina ⇄ Europa.\nKomfort, punktualność, bezpieczeństwo.\n\nWybierz sekcję 👇",
         "en": "👋 <b>Welcome!</b>\n\nEUROTOUR — passenger transport Ukraine ⇄ Europe.\nComfort, punctuality, safety.\n\nChoose a section 👇"}

SEED = [  # (typ, target, roww, sys, {lang:(label, body)})
    ("page", "", 2, "about", {
        "uk": ("ℹ️ Про нас", "ℹ️ <b>Про нас</b>\n\nEUROTOUR — пасажирські перевезення між Україною та Європою.\nКомфортні автобуси, досвідчені водії, зручні маршрути."),
        "ru": ("ℹ️ О нас", "ℹ️ <b>О нас</b>\n\nEUROTOUR — пассажирские перевозки между Украиной и Европой.\nКомфортные автобусы, опытные водители, удобные маршруты."),
        "pl": ("ℹ️ O nas", "ℹ️ <b>O nas</b>\n\nEUROTOUR — przewozy pasażerskie między Ukrainą a Europą."),
        "en": ("ℹ️ About us", "ℹ️ <b>About us</b>\n\nEUROTOUR — passenger transport between Ukraine and Europe.")}),
    ("page", "", 2, "contact", {
        "uk": ("📞 Зв'язок", "📞 <b>Зв'язок з нами</b>\n\nМи на зв'язку та відповімо особисто.\n\n👤 Менеджер: Дмитро\n💬 Telegram: @pereviznyk_support\n📱 Телефон: +380 00 000 00 00\n\nНапишіть нам прямо тут — повідомлення одразу потрапить до менеджера."),
        "ru": ("📞 Связь", "📞 <b>Связь с нами</b>\n\nМы на связи и ответим лично.\n\n👤 Менеджер: Дмитрий\n💬 Telegram: @pereviznyk_support\n📱 Телефон: +380 00 000 00 00\n\nНапишите нам прямо здесь — сообщение сразу попадёт к менеджеру."),
        "pl": ("📞 Kontakt", "📞 <b>Kontakt z nami</b>\n\n👤 Menedżer: Dmytro\n💬 Telegram: @pereviznyk_support\n📱 Telefon: +380 00 000 00 00"),
        "en": ("📞 Contact", "📞 <b>Contact us</b>\n\n👤 Manager: Dmytro\n💬 Telegram: @pereviznyk_support\n📱 Phone: +380 00 000 00 00")}),
    ("url", "https://t.me/pereviznyk_support", 2, "site",
     {l: ({"uk": "🌐 Сайт", "ru": "🌐 Сайт", "pl": "🌐 Strona", "en": "🌐 Website"}[l], "") for l in LANGS}),
    ("url", "https://t.me/pereviznyk_support", 2, "channel",
     {l: ({"uk": "📢 Канал", "ru": "📢 Канал", "pl": "📢 Kanał", "en": "📢 Channel"}[l], "") for l in LANGS}),
    ("lang", "", 2, "lang",
     {l: ({"uk": "🌍 Мова", "ru": "🌍 Язык", "pl": "🌍 Język", "en": "🌍 Language"}[l], "") for l in LANGS}),
]
SEED_FORM = {"uk": "✍️ Написати зараз", "ru": "✍️ Написать сейчас", "pl": "✍️ Napisz teraz", "en": "✍️ Write to us now"}


async def qa(sql: str, *a) -> list[aiosqlite.Row]:
    async with db.execute(sql, a) as c:
        return list(await c.fetchall())


async def q1(sql: str, *a) -> Optional[aiosqlite.Row]:
    async with db.execute(sql, a) as c:
        return await c.fetchone()


_WCNT = 0          # лічильник записів для періодичного checkpoint


async def ex(sql: str, *a) -> int:
    cur = await db.execute(sql, a)
    await db.commit()
    # Важливі зміни (правки адміна, нові користувачі, звернення) одразу
    # зливаємо з WAL у сам файл БД — щоб раптове вбивство процесу
    # на хостингу не з'їло останні дії.
    if sql[:6].upper() in ("INSERT", "UPDATE", "DELETE"):
        global _WCNT
        _WCNT += 1
        if _WCNT % 5 == 0:                        # не частіше, ніж раз на 5 записів
            with suppress(Exception):
                await db.execute("PRAGMA wal_checkpoint(PASSIVE)")
    return cur.lastrowid or 0


async def scalar(sql: str, *a) -> int:
    r = await q1(sql, *a)
    return int(r[0]) if r and r[0] is not None else 0


def _persist_state(uid: int, val) -> None:
    """Фонове збереження стану діалогу (не блокує обробку повідомлення)."""
    if db is None:
        return

    async def _w():
        with suppress(Exception):
            if val is None:
                await db.execute("DELETE FROM states WHERE uid=?", (uid,))
            else:
                await db.execute(
                    "INSERT INTO states(uid,data,elang,ts) VALUES(?,?,?,?) "
                    "ON CONFLICT(uid) DO UPDATE SET data=excluded.data,ts=excluded.ts",
                    (uid, json.dumps(val, ensure_ascii=False), ELANG.get(uid, ""), now()))
            await db.commit()
    with suppress(RuntimeError):
        asyncio.get_running_loop().create_task(_w())


async def load_states() -> None:
    """Підняти стани діалогів після перезапуску — прогрес не губиться."""
    with suppress(Exception):
        n = 0
        for r in await qa("SELECT uid,data,elang FROM states WHERE ts>?", now() - 86400):
            with suppress(Exception):
                dict.__setitem__(ST, r["uid"], json.loads(r["data"]))
                if r["elang"]:
                    ELANG[r["uid"]] = r["elang"]
                n += 1
        # прибрати старе, щоб таблиця не росла
        await ex("DELETE FROM states WHERE ts<?", now() - 86400)
        if n:
            log.info("Відновлено незавершених діалогів: %s", n)


async def init_db() -> None:
    global db
    # ── БД зберігається у постійній теці (див. DB_PATH) ──
    folder = os.path.dirname(os.path.abspath(DB_PATH))
    if folder:
        os.makedirs(folder, exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    # ── ЗАХИСТ ДАНИХ ВІД ВТРАТИ ПРИ ПЕРЕЗАПУСКУ/ЗБОЇ ──
    # WAL: запис не втрачається навіть при раптовому kill процесу
    await db.execute("PRAGMA journal_mode=WAL")
    # FULL: кожен commit фізично скидається на диск
    await db.execute("PRAGMA synchronous=FULL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA busy_timeout=10000")
    await db.executescript(SCHEMA)
    await db.commit()
    log.info("БД: %s (journal=%s)", DB_PATH,
             (await (await db.execute("PRAGMA journal_mode")).fetchone())[0])
    for k, v in CFG_DEF.items():
        await db.execute("INSERT OR IGNORE INTO cfg(k,v) VALUES(?,?)", (k, v))
    for k, d in SYS_DEF.items():
        for l, v in d.items():
            await db.execute("INSERT OR IGNORE INTO sys(k,lang,v) VALUES(?,?,?)", (k, l, v))
    await db.execute("INSERT OR IGNORE INTO admins(id,role,name) VALUES(?,?,?)", (OWNER_ID, "owner", "Owner"))
    await db.commit()
    for r in await qa("SELECT k,v FROM cfg"):
        CFG[r["k"]] = r["v"]
    # корінь має існувати завжди
    if not await q1("SELECT id FROM nodes WHERE id=1"):
        await db.execute("INSERT OR IGNORE INTO nodes(id,parent,typ,roww,sys) VALUES(1,0,'root',2,'root')")
        await db.commit()
    # привітання — якщо його немає для якоїсь мови
    for l, t in GREET.items():
        await db.execute("INSERT OR IGNORE INTO tr(node,lang,label,body) VALUES(1,?,'',?)", (l, t))
    await db.commit()
    # Розділи створюємо, якщо корінь ПОРОЖНІЙ. Раніше перевірявся лише корінь,
    # тому при частково відновленій базі меню лишалось без кнопок.
    if not await q1("SELECT id FROM nodes WHERE parent=1 LIMIT 1"):
        for i, (typ, tgt, rw, sysk, trs) in enumerate(SEED):
            nid = await ex("INSERT INTO nodes(parent,typ,target,pos,roww,sys) VALUES(1,?,?,?,?,?)",
                           typ, tgt, i, rw, sysk)
            for l, (lab, body) in trs.items():
                await db.execute("INSERT OR IGNORE INTO tr(node,lang,label,body) VALUES(?,?,?,?)", (nid, l, lab, body))
            await db.commit()
            if sysk == "contact":                                     # кнопка «Написать сейчас»
                fid = await ex("INSERT INTO nodes(parent,typ,pos,roww,sys) VALUES(?,'form',0,1,'form')", nid)
                for l, lab in SEED_FORM.items():
                    await db.execute("INSERT OR IGNORE INTO tr(node,lang,label) VALUES(?,?,?)", (fid, l, lab))
                await db.commit()


# ═══════════════════ АВТОПЕРЕКЛАД ═══════════════════
# Адмін пише текст однією мовою — бот сам перекладає на інші.
# Ручні переклади ніколи не перезаписуються (machine=0 — недоторканий).

_TR_LOCK = asyncio.Lock()


def _protect(text: str) -> tuple[str, dict]:
    """Ховає HTML-теги й посилання, щоб перекладач їх не зіпсував."""
    keep: dict = {}

    def sub(m):
        i = f"\ue000{len(keep)}\ue001"        # службовий символ, перекладач його не чіпає
        keep[i] = m.group(0)
        return i

    out = re.sub(r"<[^>]+>|https?://\S+|@[\w_]{3,}|\+?\d[\d\s()\-]{6,}", sub, text)
    return out, keep


def _restore(text: str, keep: dict) -> str:
    for i, v in keep.items():
        text = text.replace(i, v)
    # перекладачі іноді ламають службові символи
    return re.sub(r"\ue000\s*(\d+)\s*\ue001", lambda m: keep.get(f"\ue000{m.group(1)}\ue001", ""), text)


def _tr_sync(text: str, to: str, frm: str) -> str:
    """Синхронний переклад: пробуємо кілька безкоштовних сервісів по черзі."""
    import urllib.parse
    import urllib.request
    UA = {"User-Agent": "Mozilla/5.0"}

    def gtx():
        q = urllib.parse.urlencode({"client": "dict-chrome-ex", "sl": frm, "tl": to, "q": text})
        r = urllib.request.Request("https://clients5.google.com/translate_a/t?" + q, headers=UA)
        d = json.loads(urllib.request.urlopen(r, timeout=20).read().decode())
        if isinstance(d, list):
            return "".join(x if isinstance(x, str) else x[0] for x in d)
        return str(d)

    def gtx2():
        q = urllib.parse.urlencode({"client": "gtx", "sl": frm, "tl": to, "dt": "t", "q": text})
        r = urllib.request.Request("https://translate.googleapis.com/translate_a/single?" + q, headers=UA)
        d = json.loads(urllib.request.urlopen(r, timeout=20).read().decode())
        return "".join(p[0] for p in d[0] if p[0])

    def mymemory():
        q = urllib.parse.urlencode({"q": text, "langpair": f"{frm}|{to}"})
        r = urllib.request.Request("https://api.mymemory.translated.net/get?" + q, headers=UA)
        d = json.loads(urllib.request.urlopen(r, timeout=20).read().decode())
        return d["responseData"]["translatedText"]

    for fn in (gtx, gtx2, mymemory):
        with suppress(Exception):
            res = (fn() or "").strip()
            if res and res.lower() != text.lower():
                return res
    return ""


async def translate(text: str, to: str, frm: str) -> str:
    """Переклад із кешем. Порожній рядок = не вдалося (тоді текст не чіпаємо)."""
    text = (text or "").strip()
    if not text or to == frm:
        return ""
    h = hashlib.md5(f"{frm}|{text}".encode()).hexdigest()
    row = await q1("SELECT txt FROM trcache WHERE h=? AND lang=?", h, to)
    if row:
        return row["txt"]
    safe, keep = _protect(text)
    async with _TR_LOCK:                       # не бомбимо сервіс паралельними запитами
        res = await asyncio.get_running_loop().run_in_executor(None, _tr_sync, safe, to, frm)
    if not res:
        return ""
    res = _restore(res, keep)
    with suppress(Exception):
        await ex("INSERT OR REPLACE INTO trcache(h,lang,txt) VALUES(?,?,?)", h, to, res)
    return res


async def autotranslate_node(nid: int, src_lang: str) -> int:
    """Розкидає текст вузла на всі інші мови. Повертає кількість перекладених."""
    if CFG.get("autotr", "1") != "1":
        return 0
    src = await q1("SELECT label,body FROM tr WHERE node=? AND lang=?", nid, src_lang)
    if not src:
        return 0
    done = 0
    for lang in langs_on():
        if lang == src_lang:
            continue
        cur = await q1("SELECT label,body,machine FROM tr WHERE node=? AND lang=?", nid, lang)
        # не чіпаємо те, що адмін переклав руками
        if cur and not cur["machine"] and (cur["label"] or cur["body"]):
            continue
        lab = await translate(src["label"], lang, src_lang) if src["label"] else ""
        bod = await translate(src["body"], lang, src_lang) if src["body"] else ""
        if not lab and not bod:
            continue
        await ex("INSERT INTO tr(node,lang,label,body,machine) VALUES(?,?,?,?,1) "
                 "ON CONFLICT(node,lang) DO UPDATE SET label=?,body=?,machine=1",
                 nid, lang, lab or (cur["label"] if cur else ""), bod or (cur["body"] if cur else ""),
                 lab or (cur["label"] if cur else ""), bod or (cur["body"] if cur else ""))
        done += 1
    if done:
        log.info("Автопереклад вузла %s з %s → %s мов", nid, src_lang, done)
    return done


async def setcfg(k: str, v: str) -> None:
    CFG[k] = v
    await ex("INSERT INTO cfg(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=?", k, v, v)


def langs_on() -> list[str]:
    return [l for l in CFG.get("langs", "uk").split(",") if l in LANGS] or ["uk"]


async def T(key: str, lang: str) -> str:
    r = await q1("SELECT v FROM sys WHERE k=? AND lang=?", key, lang)
    if r:
        return r["v"]
    r = await q1("SELECT v FROM sys WHERE k=? AND lang=?", key, CFG.get("deflang", "uk"))
    return r["v"] if r else SYS_DEF.get(key, {}).get("uk", key)

# ════════════════════════════ УТИЛИТЫ ════════════════════════════
def kb(rows: Sequence[Sequence[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


def B(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def U(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def grid(items: list[InlineKeyboardButton], w: int) -> list[list[InlineKeyboardButton]]:
    w = max(1, min(3, w))
    return [items[i:i + w] for i in range(0, len(items), w)]


def esc(s: Any) -> str:
    return html.escape(str(s or ""), quote=False)


def uname(u: aiosqlite.Row | dict) -> str:
    un = (u["uname"] if isinstance(u, aiosqlite.Row) else u.get("uname")) or ""
    return f"@{un}" if un else "@ немає"


def I(v: Any, default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def now() -> int:
    return int(time.time())


def ts(v: int) -> str:
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(v or 0))


def media_of(m: Message) -> tuple[str, str]:
    if m.photo:
        return "photo", m.photo[-1].file_id
    if m.video:
        return "video", m.video.file_id
    if m.animation:
        return "animation", m.animation.file_id
    if m.document:
        return "document", m.document.file_id
    if m.audio:
        return "audio", m.audio.file_id
    if m.voice:
        return "voice", m.voice.file_id
    return "", ""


def body_of(m: Message) -> str:
    return (m.html_text if (m.text or m.caption) else "") or ""


async def is_admin(uid: int) -> Optional[str]:
    if uid == OWNER_ID:
        return "owner"
    r = await q1("SELECT role FROM admins WHERE id=?", uid)
    return r["role"] if r else None


async def can(uid: int, what: str) -> bool:
    role = await is_admin(uid)
    if not role:
        return False
    if role in ("owner", "full"):
        return role == "owner" or what != "admins"
    return what in ("tickets", "users")


async def send_content(bot: Bot, chat: int, text: str, markup: Optional[InlineKeyboardMarkup],
                       mtype: str = "", mid: str = "") -> Optional[Message]:
    """Отправка с учётом лимитов: длинная подпись → медиа отдельно, текст следом."""
    try:
        if mtype and mid:
            send = {"photo": bot.send_photo, "video": bot.send_video, "animation": bot.send_animation,
                    "document": bot.send_document, "audio": bot.send_audio, "voice": bot.send_voice}.get(mtype)
            if send:
                if text and len(text) <= CAP_LIMIT:
                    return await send(chat, mid, caption=text, reply_markup=markup)
                await send(chat, mid)
                if not text:
                    return await bot.send_message(chat, "⠀", reply_markup=markup) if markup else None
        if not text:
            text = "⠀"
        return await bot.send_message(chat, text[:TXT_LIMIT], reply_markup=markup,
                                      disable_web_page_preview=True)
    except TelegramBadRequest as e:
        log.warning("send_content: %s", e)
        return await bot.send_message(chat, esc(text)[:TXT_LIMIT], reply_markup=markup,
                                      disable_web_page_preview=True)


async def render(ev: Message | CallbackQuery, text: str, markup: Optional[InlineKeyboardMarkup],
                 mtype: str = "", mid: str = "") -> None:
    """Показать экран: правим текущее сообщение, если можно, иначе шлём новое."""
    bot = ev.bot
    src = getattr(ev, "message", None)          # CallbackQuery → сообщение с кнопками
    if src is not None or not hasattr(ev, "chat"):
        msg = src
        if msg is None:
            return
        if not mtype and not (msg.photo or msg.video or msg.document or msg.animation or msg.audio):
            try:
                await msg.edit_text(text[:TXT_LIMIT] or "⠀", reply_markup=markup,
                                    disable_web_page_preview=True)
                return
            except TelegramBadRequest as e:
                if "message is not modified" in str(e).lower():
                    return
        try:
            await msg.delete()
        except TelegramBadRequest:
            pass
        await send_content(bot, msg.chat.id, text, markup, mtype, mid)
    else:
        await send_content(bot, ev.chat.id, text, markup, mtype, mid)


async def touch_user(m: Message) -> aiosqlite.Row:
    """Створює або оновлює користувача одним атомарним запитом.

    UPSERT замість SELECT+INSERT: при одночасних /start немає гонки
    та помилки «UNIQUE constraint failed: users.id».
    """
    u = m.from_user
    await ex("INSERT INTO users(id,uname,name,lang,created,seen) VALUES(?,?,?,?,?,?) "
             "ON CONFLICT(id) DO UPDATE SET uname=excluded.uname, name=excluded.name, "
             "seen=excluded.seen, banned=CASE users.banned WHEN 2 THEN 0 ELSE users.banned END",
             u.id, u.username or "", u.full_name or "", CFG.get("deflang", "uk"), now(), now())
    return await q1("SELECT * FROM users WHERE id=?", u.id)  # type: ignore


async def ulang(uid: int) -> str:
    r = await q1("SELECT lang FROM users WHERE id=?", uid)
    l = r["lang"] if r else CFG.get("deflang", "uk")
    return l if l in langs_on() else CFG.get("deflang", "uk")

# ════════════════════════════ РЕНДЕР КЛИЕНТСКИХ ЭКРАНОВ ════════════════════════════
async def node_tr(nid: int, lang: str) -> aiosqlite.Row | dict:
    r = await q1("SELECT * FROM tr WHERE node=? AND lang=?", nid, lang)
    if r and (r["label"] or r["body"] or r["mid"]):
        return r
    d = await q1("SELECT * FROM tr WHERE node=? AND lang=?", nid, CFG.get("deflang", "uk"))
    if d:
        return d
    a = await q1("SELECT * FROM tr WHERE node=? LIMIT 1", nid)
    return a or {"label": "", "body": "", "mtype": "", "mid": ""}


async def children(nid: int, admin: bool) -> list[aiosqlite.Row]:
    sql = "SELECT * FROM nodes WHERE parent=?" + ("" if admin else " AND hidden=0 AND draft=0") + " ORDER BY pos,id"
    return await qa(sql, nid)


async def build_kb(nid: int, lang: str, admin: bool, live: bool) -> InlineKeyboardMarkup:
    node = await q1("SELECT * FROM nodes WHERE id=?", nid)
    if not node:
        return kb([])
    items: list[InlineKeyboardButton] = []
    for c in await children(nid, admin):
        t = await node_tr(c["id"], lang)
        label = t["label"] or "•"
        if admin and (c["draft"] or c["hidden"]):
            label = ("📝 " if c["draft"] else "🔕 ") + label
        typ, tgt = c["typ"], (c["target"] or "")
        try:
            if typ == "url" and tgt.startswith(("http://", "https://", "tg://")):
                items.append(U(label, tgt))
            elif typ == "phone" and tgt:
                items.append(U(label, "tel:" + tgt.replace(" ", "")))
            else:
                items.append(B(label, f"n:{c['id']}"))
        except Exception:
            items.append(B(label, f"n:{c['id']}"))
    rows = grid(items, node["roww"] or 2)
    if nid != 1 and CFG.get("backbtn", "1") == "1":
        parent = node["parent"] or 1
        rows.append([B(await T("back", lang), "home" if parent == 1 else f"n:{parent}")])
    if live and admin:
        rows.append([B("✏️ Текст", f"p:txt:{nid}"), B("🖼 Фото", f"p:med:{nid}"),
                     B("🔘 Кнопки", f"p:btn:{nid}")])
        rows.append([B("🌍 " + UP.get(lang, lang), f"p:sec"), B("👁 Вимкнути режим", "p:liveoff")])
    elif admin and nid == 1:
        rows.append([B("⚙️ Панель", "p:home")])
    return kb(rows)


async def show_node(ev: Message | CallbackQuery, nid: int, uid: int) -> None:
    lang = await ulang(uid)
    node = await q1("SELECT * FROM nodes WHERE id=?", nid)
    if not node:
        await render(ev, await T("unknown", lang), await build_kb(1, lang, bool(await is_admin(uid)), uid in LIVE))
        return
    admin = bool(await is_admin(uid))
    t = await node_tr(nid, lang)
    text = t["body"] or ""
    if nid != 1:
        await ex("UPDATE nodes SET views=views+1 WHERE id=?", nid)
    markup = await build_kb(nid, lang, admin, uid in LIVE)
    if not text and nid != 1:
        parent_t = await node_tr(nid, lang)
        text = parent_t["label"] or "•"
    await render(ev, text, markup, t["mtype"] or "", t["mid"] or "")


async def lang_menu(lang: str) -> InlineKeyboardMarkup:
    rows = grid([B(LANGS[l], f"l:{l}") for l in langs_on()], 2)
    rows.append([B(await T("back", lang), "home")])
    return kb(rows)

# ════════════════════════════ РОУТЕР КЛИЕНТА ════════════════════════════
user_r = Router()


@user_r.message(CommandStart())
async def cmd_start(m: Message) -> None:
    if m.chat.type != "private":
        return
    ST.pop(m.from_user.id, None)
    u = await touch_user(m)
    if u["banned"] == 1:
        return
    if CFG.get("maint", "0") == "1" and not await is_admin(m.from_user.id):
        await m.answer(await T("maint", await ulang(m.from_user.id)))
        return
    if len(langs_on()) > 1 and not u["lset"]:
        await m.answer(await T("langsel", CFG.get("deflang", "uk")),
                       reply_markup=kb(grid([B(LANGS[l], f"l:{l}") for l in langs_on()], 2)))
        return
    await show_node(m, 1, m.from_user.id)


@user_r.message(Command("myid"), F.chat.type == "private")
async def cmd_myid(m: Message) -> None:
    await m.answer(f"🆔 Ваш ID: <code>{m.from_user.id}</code>\n💬 Chat ID: <code>{m.chat.id}</code>")


@user_r.callback_query(F.data.startswith("l:"), F.message.chat.type == "private")
async def cb_lang(c: CallbackQuery) -> None:
    lang = c.data.split(":", 1)[1]
    if lang in langs_on():
        await ex("UPDATE users SET lang=?,lset=1 WHERE id=?", lang, c.from_user.id)
    await c.answer("✅")
    await show_node(c, 1, c.from_user.id)


@user_r.callback_query(F.data == "home", F.message.chat.type == "private")
async def cb_home(c: CallbackQuery) -> None:
    ST.pop(c.from_user.id, None)
    await c.answer()
    await show_node(c, 1, c.from_user.id)


@user_r.callback_query(F.data == "cancel", F.message.chat.type == "private")
async def cb_cancel(c: CallbackQuery) -> None:
    ST.pop(c.from_user.id, None)
    await c.answer("❌")
    await show_node(c, 1, c.from_user.id)


@user_r.callback_query(F.data.startswith("n:"), F.message.chat.type == "private")
async def cb_node(c: CallbackQuery) -> None:
    uid = c.from_user.id
    try:
        nid = int(c.data.split(":", 1)[1])
    except ValueError:
        await c.answer(); return
    node = await q1("SELECT * FROM nodes WHERE id=?", nid)
    if not node:
        await c.answer("Розділ недоступний", show_alert=True); return
    lang = await ulang(uid)
    typ = node["typ"]
    if typ == "lang":
        await c.answer()
        await render(c, await T("langsel", lang), await lang_menu(lang)); return
    if typ == "form":
        ST[uid] = {"k": "form"}
        await c.answer()
        await render(c, await T("ask", lang),
                     kb([[B(await T("cancel", lang), "cancel")]])); return
    if typ == "goto":
        try:
            await c.answer(); await show_node(c, int(node["target"] or 1), uid); return
        except ValueError:
            await c.answer(); return
    if typ == "loc" and node["target"]:
        try:
            la, lo = node["target"].split(",")
            await c.bot.send_location(c.message.chat.id, float(la), float(lo))
            await c.answer(); return
        except Exception:
            await c.answer("⚠️"); return
    if typ == "file":
        t = await node_tr(nid, lang)
        if t["mid"]:
            await send_content(c.bot, c.message.chat.id, t["body"] or "", None, t["mtype"], t["mid"])
            await c.answer(); return
    await c.answer()
    await show_node(c, nid, uid)

# ────────────────── приём обращения ──────────────────
async def deliver_ticket(bot: Bot, m: Message, u: aiosqlite.Row) -> None:
    lang = await ulang(u["id"])
    mtype, mid = media_of(m)
    if mtype and CFG.get("files", "1") != "1":
        mtype, mid = "", ""
    body = body_of(m)
    if not body and not mid:
        await m.answer(await T("ask", lang)); return
    tid = await ex("INSERT INTO tickets(uid,body,mtype,mid,status,created) VALUES(?,?,?,?, 'new', ?)",
                   u["id"], body, mtype, mid, now())
    await ex("UPDATE users SET msgs=msgs+1 WHERE id=?", u["id"])
    total = await scalar("SELECT COUNT(*) FROM tickets WHERE uid=?", u["id"])
    un = f"@{u['uname']}" if u["uname"] else "@ немає (пише через бота)"
    head = (f"📨 <b>НОВЕ ЗВЕРНЕННЯ #{tid}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 {esc(m.from_user.full_name)}\n"
            f"🔗 {esc(un)}\n"
            f"🆔 <code>{u['id']}</code>\n"
            f"🌍 Мова: {FLAG.get(lang,'')} {UP.get(lang, lang)}\n"
            f"🕐 {ts(now())}\n"
            f"📊 Звернень від нього: {total}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💬 {body or '(медіа без тексту)'}")
    markup = kb([[B("✍️ Відповісти", f"p:t:r:{tid}"), B("👤 Профіль", f"p:t:c:{tid}")],
                 [B("✅ Опрацьовано", f"p:t:done:{tid}")]])
    targets: list[int] = []
    if CFG.get("chat_id"):
        try:
            targets.append(int(CFG["chat_id"]))
        except ValueError:
            pass
    if not targets or CFG.get("notify", "1") == "1":
        if OWNER_ID not in targets:
            targets.append(OWNER_ID)
    for t in targets:
        try:
            await send_content(bot, t, head, markup, mtype, mid)
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            log.warning("ticket→%s: %s", t, e)
    if CFG.get("confirm", "1") == "1":
        await m.answer(await T("sent", lang), reply_markup=kb([[B(await T("home", lang), "home")]]))


@user_r.message(F.chat.type == "private")
async def any_private(m: Message) -> None:
    uid = m.from_user.id
    u = await touch_user(m)
    if u["banned"] == 1:
        await m.answer(await T("blocked", await ulang(uid))); return
    admin = bool(await is_admin(uid))
    if CFG.get("maint", "0") == "1" and not admin:
        ST.pop(uid, None)
        await m.answer(await T("maint", await ulang(uid))); return
    st = ST.get(uid)
    if st and st.get("k") == "form":
        gap = int(CFG.get("spam", "20") or 0)
        if gap and now() - LASTMSG.get(uid, 0) < gap and not await is_admin(uid):
            await m.answer(await T("spam", await ulang(uid))); return
        LASTMSG[uid] = now()
        ST.pop(uid, None)
        await deliver_ticket(m.bot, m, u); return
    if st:                                   # ввод для админ-панели
        await admin_input(m, st); return
    lang = await ulang(uid)
    await m.answer(await T("unknown", lang),
                   reply_markup=await build_kb(1, lang, admin, uid in LIVE))

# ════════════════════════════ АДМИН-ПАНЕЛЬ ════════════════════════════
adm_r = Router()
BOTTOM = lambda back: [B("⬅️ Назад", back), B("🏠 Панель", "p:home"), B("❌ Вихід", "p:exit")]


def el(uid: int) -> str:
    return ELANG.get(uid, CFG.get("deflang", "uk"))


async def crumb(nid: int, lang: str) -> str:
    path, cur, guard = [], nid, 0
    while cur and cur != 1 and guard < 10:
        n = await q1("SELECT parent FROM nodes WHERE id=?", cur)
        t = await node_tr(cur, lang)
        path.append(t["label"] or f"#{cur}")
        cur = n["parent"] if n else 0
        guard += 1
    return "⚙️ Панель › " + " › ".join(reversed(path)) if path else "⚙️ Панель"


async def panel_home(ev, uid: int) -> None:
    role = await is_admin(uid) or ""
    new = await scalar("SELECT COUNT(*) FROM tickets WHERE status='new'")
    users = await scalar("SELECT COUNT(*) FROM users")
    today = await scalar("SELECT COUNT(*) FROM users WHERE created>?", now() - 86400)
    txt = (f"⚙️ <b>Панель управління EUROTOUR</b>\n\n"
           f"🔴 Нових звернень: <b>{new}</b>\n"
           f"👥 Користувачів: <b>{users}</b> (+{today} за добу)\n"
           f"🌍 Мова редагування: {FLAG.get(el(uid),'')} {UP.get(el(uid), el(uid))}\n"
           f"🎭 Роль: {ROLES.get(role, role)}")
    if role == "tickets":
        rows = [[B("📨 Звернення" + (f" 🔴{new}" if new else ""), "p:t:list:new:0"), B("👥 Користувачі", "p:u:0")],
                [B("❌ Вийти", "p:exit")]]
    else:
        rows = [[B("📄 Розділи бота", "p:sec"), B("👁 Живе редагування", "p:live")],
                [B("📨 Звернення" + (f" 🔴{new}" if new else ""), "p:t:list:new:0"), B("👥 Користувачі", "p:u:0")],
                [B("📢 Розсилка", "p:b:menu"), B("📊 Статистика", "p:stat")],
                [B("🌍 Мови", "p:langs"), B("🖼 Медіа", "p:medial")],
                [B("⚙️ Налаштування", "p:s:menu"), B("👮 Адміни", "p:a:list")],
                [B("💾 Бекап", "p:bk"), B("❌ Вийти", "p:exit")]]
    await render(ev, txt, kb(rows))


async def sec_menu(ev, uid: int) -> None:
    lang = el(uid)
    rows = [[B("🌳 Дерево бота", "p:tree")],
            [B("👋 Привітання", "p:n:1"), B("🔘 Головне меню", "p:btn:1")]]
    kids = await children(1, True)
    line = []
    for c in kids:
        t = await node_tr(c["id"], lang)
        line.append(B(t["label"] or f"#{c['id']}", f"p:n:{c['id']}"))
    rows += grid(line, 2)
    rows.append([B("⚙️ Службові повідомлення", "p:sys"), B("➕ Створити розділ", "p:add:1")])
    rows.append([B(f"🌍 Мова: {UP.get(lang, lang)}", "p:elang")])
    rows.append(BOTTOM("p:home"))
    await render(ev, f"⚙️ Панель › 📄 <b>Розділи</b>\n\nОберіть розділ для редагування.\n"
                     f"Мова редагування: {FLAG.get(lang,'')} {UP.get(lang, lang)}", kb(rows))


async def tree_view(ev, uid: int) -> None:
    lang = el(uid)
    lines: list[str] = ["🏠 <b>Головне меню</b>"]
    marks = {"page": "📄", "menu": "📂", "url": "🔗", "form": "⚡", "phone": "📞",
             "loc": "📍", "file": "📎", "goto": "↩️", "lang": "⚙️"}
    btns: list[InlineKeyboardButton] = []

    async def walk(pid: int, prefix: str) -> None:
        kids = await children(pid, True)
        for i, c in enumerate(kids):
            last = i == len(kids) - 1
            t = await node_tr(c["id"], lang)
            flag = " 📝" if c["draft"] else (" 🔕" if c["hidden"] else "")
            lines.append(f"{prefix}{'└─' if last else '├─'} {esc(t['label'] or '•')} "
                         f"{marks.get(c['typ'], '•')}{flag}")
            btns.append(B(t["label"] or f"#{c['id']}", f"p:n:{c['id']}"))
            await walk(c["id"], prefix + ("   " if last else "│  "))

    await walk(1, "")
    rows = grid(btns[:30], 2)
    rows.append([B("➕ Додати розділ", "p:add:1"), B("🔀 Порядок", "p:btn:1")])
    rows.append(BOTTOM("p:sec"))
    body = "\n".join(lines) or "порожньо"
    await render(ev, f"⚙️ Панель › 📄 Розділи › 🌳 <b>Дерево</b>\n\n{body}\n\n"
                     f"<i>📄 текст · 📂 підменю · 🔗 посилання · ⚡ форма · 📝 чернетка · 🔕 приховано</i>", kb(rows))


async def node_editor(ev, uid: int, nid: int) -> None:
    lang = el(uid)
    n = await q1("SELECT * FROM nodes WHERE id=?", nid)
    if not n:
        await panel_home(ev, uid); return
    t = await node_tr(nid, lang)
    status = "📝 чернетка" if n["draft"] else ("🔕 приховано" if n["hidden"] else "✅ опубліковано")
    prev = (t["body"] or "—")
    prev = prev[:400] + ("…" if len(prev) > 400 else "")
    kids = await scalar("SELECT COUNT(*) FROM nodes WHERE parent=?", nid)
    txt = (f"{await crumb(nid, lang)}\n\n"
           f"🏷 Кнопка: <b>{esc(t['label'] or '—')}</b>\n"
           f"🔧 Тип: <code>{n['typ']}</code>   ·   Статус: {status}\n"
           f"🌍 Мова: {FLAG.get(lang,'')} {UP.get(lang, lang)}   ·   👁 Показів: {n['views']}\n"
           f"🖼 Медіа: {t['mtype'] or '—'}   ·   🔘 Кнопок усередині: {kids}\n"
           f"{'🔗 Ціль: <code>'+esc(n['target'])+'</code>' if n['target'] else ''}\n"
           f"━━━━━━━━━━━━━━━━━━\n{prev}")
    rows = [[B("✏️ Змінити текст", f"p:txt:{nid}"), B("➕ Дописати", f"p:app:{nid}")],
            [B("🖼 Медіа", f"p:med:{nid}"), B("🔘 Кнопки", f"p:btn:{nid}")],
            [B("🏷 Назва кнопки", f"p:lbl:{nid}"), B("🔗 Тип/ціль", f"p:typ:{nid}")],
            [B("👁 Перегляд", f"p:prev:{nid}"), B("🌍 Переклади", f"p:tr:{nid}")],
            [B("📋 Копіювати", f"p:copy:{nid}"), B("↩️ Історія", f"p:hist:{nid}")]]
    if n["id"] != 1:
        rows.append([B("🚀 Опублікувати" if n["draft"] else ("👁 Показати" if n["hidden"] else "🔕 Приховати"),
                       f"p:vis:{nid}"), B("🗑 Видалити", f"p:del:{nid}")])
    back = "p:sec" if (n["parent"] or 1) == 1 else f"p:n:{n['parent']}"
    rows.append(BOTTOM(back))
    await render(ev, txt, kb(rows))


async def buttons_view(ev, uid: int, nid: int) -> None:
    lang = el(uid)
    n = await q1("SELECT * FROM nodes WHERE id=?", nid)
    if not n:
        await panel_home(ev, uid); return
    kids = await children(nid, True)
    marks = {"page": "📄 сторінка", "menu": "📂 підменю", "url": "🔗 посилання", "form": "⚡ форма",
             "phone": "📞 телефон", "loc": "📍 гео", "file": "📎 файл", "goto": "↩️ перехід", "lang": "⚙️ мова"}
    lines, btns = [], []
    for i, c in enumerate(kids, 1):
        t = await node_tr(c["id"], lang)
        st = "📝" if c["draft"] else ("🔕" if c["hidden"] else "✅")
        lines.append(f"{i}. {esc(t['label'] or '•')} — {marks.get(c['typ'],c['typ'])} {st}")
        btns.append(B(f"{i}️⃣" if i < 10 else str(i), f"p:n:{c['id']}"))
    rows = grid(btns, 4)
    rows.append([B("➕ Додати кнопку", f"p:add:{nid}"), B("🔀 Порядок", f"p:ord:{nid}")])
    rows.append([B(f"🔢 У ряд: {n['roww']}", f"p:roww:{nid}"),
                 B(f"⬅️ Кнопка «Назад»: {'ON' if CFG.get('backbtn','1')=='1' else 'OFF'}", "p:s:backbtn")])
    rows.append([B("👁 Перегляд", f"p:prev:{nid}")])
    rows.append(BOTTOM(f"p:n:{nid}" if nid != 1 else "p:sec"))
    head = "🏠 Головне меню" if nid == 1 else esc((await node_tr(nid, lang))["label"])
    await render(ev, f"⚙️ Панель › 🔘 <b>Кнопки</b> — {head}\n\n" + ("\n".join(lines) or "Кнопок ще немає."), kb(rows))


async def order_view(ev, uid: int, nid: int) -> None:
    lang = el(uid)
    kids = await children(nid, True)
    rows = []
    for c in kids:
        t = await node_tr(c["id"], lang)
        rows.append([B((t["label"] or "•")[:20], f"p:n:{c['id']}"),
                     B("⬆️", f"p:mv:{c['id']}:u"), B("⬇️", f"p:mv:{c['id']}:d")])
    rows.append(BOTTOM(f"p:btn:{nid}"))
    await render(ev, "⚙️ Панель › 🔀 <b>Порядок кнопок</b>\n\nПересуньте кнопки стрілками.", kb(rows))


async def move(nid: int, direction: str) -> None:
    n = await q1("SELECT * FROM nodes WHERE id=?", nid)
    if not n:
        return
    sibs = await qa("SELECT * FROM nodes WHERE parent=? ORDER BY pos,id", n["parent"])
    ids = [s["id"] for s in sibs]
    if nid not in ids:
        return
    i = ids.index(nid)
    j = i - 1 if direction == "u" else i + 1
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
    for p, x in enumerate(ids):
        await db.execute("UPDATE nodes SET pos=? WHERE id=?", (p, x))
    await db.commit()


async def save_body(nid: int, lang: str, body: str) -> None:
    old = await q1("SELECT body FROM tr WHERE node=? AND lang=?", nid, lang)
    if old and old["body"]:
        await ex("INSERT INTO hist(node,lang,body,ts) VALUES(?,?,?,?)", nid, lang, old["body"], now())
        await ex("DELETE FROM hist WHERE node=? AND lang=? AND id NOT IN "
                 "(SELECT id FROM hist WHERE node=? AND lang=? ORDER BY id DESC LIMIT ?)",
                 nid, lang, nid, lang, HIST_KEEP)
    await ex("INSERT INTO tr(node,lang,body,machine) VALUES(?,?,?,0) "
             "ON CONFLICT(node,lang) DO UPDATE SET body=?,machine=0", nid, lang, body, body)
    # цей текст написав адмін — розкидаємо переклад на інші мови у фоні
    with suppress(RuntimeError):
        asyncio.get_running_loop().create_task(autotranslate_node(nid, lang))


async def del_subtree(nid: int) -> None:
    ids, stack = [], [nid]
    while stack:
        cur = stack.pop()
        ids.append(cur)
        for c in await qa("SELECT id FROM nodes WHERE parent=?", cur):
            stack.append(c["id"])
    dump = {"nodes": [dict(r) for r in await qa(
        f"SELECT * FROM nodes WHERE id IN ({','.join('?'*len(ids))})", *ids)],
        "tr": [dict(r) for r in await qa(
            f"SELECT * FROM tr WHERE node IN ({','.join('?'*len(ids))})", *ids)]}
    await ex("INSERT INTO trash(ts,data) VALUES(?,?)", now(), json.dumps(dump, ensure_ascii=False))
    ph = ",".join("?" * len(ids))
    await ex(f"DELETE FROM tr WHERE node IN ({ph})", *ids)
    await ex(f"DELETE FROM nodes WHERE id IN ({ph})", *ids)


async def copy_node(nid: int, parent: int) -> int:
    n = await q1("SELECT * FROM nodes WHERE id=?", nid)
    if not n:
        return 0
    pos = await scalar("SELECT COALESCE(MAX(pos),-1)+1 FROM nodes WHERE parent=?", parent)
    new = await ex("INSERT INTO nodes(parent,typ,target,pos,roww,hidden,draft) VALUES(?,?,?,?,?,0,1)",
                   parent, n["typ"], n["target"], pos, n["roww"])
    for t in await qa("SELECT * FROM tr WHERE node=?", nid):
        await db.execute("INSERT INTO tr(node,lang,label,body,mtype,mid) VALUES(?,?,?,?,?,?)",
                         (new, t["lang"], (t["label"] or "") + " (копія)", t["body"], t["mtype"], t["mid"]))
    await db.commit()
    for c in await qa("SELECT id FROM nodes WHERE parent=? ORDER BY pos", nid):
        await copy_node(c["id"], new)
    return new

# ────────────────── обращения ──────────────────
async def tickets_list(ev, uid: int, status: str, page: int) -> None:
    per = 8
    total = await scalar("SELECT COUNT(*) FROM tickets WHERE status=?", status)
    rows_db = await qa("SELECT t.*,u.uname,u.name,u.lang FROM tickets t LEFT JOIN users u ON u.id=t.uid "
                       "WHERE t.status=? ORDER BY t.id DESC LIMIT ? OFFSET ?", status, per, page * per)
    names = {"new": "🔴 Нові", "work": "🟡 В роботі", "closed": "✅ Закриті"}
    lines, btns = [], []
    for r in rows_db:
        un = f"@{r['uname']}" if r["uname"] else f"(без @) {esc(r['name'] or r['uid'])}"
        lines.append(f"#{r['id']} {esc(un)} · {ts(r['created'])} · {FLAG.get(r['lang'] or 'uk','')}")
        btns.append(B(f"#{r['id']}", f"p:t:c:{r['id']}"))
    rows = grid(btns, 4)
    nav = []
    if page > 0:
        nav.append(B("◀️", f"p:t:list:{status}:{page-1}"))
    nav.append(B(f"{page+1}/{max(1,(total+per-1)//per)}", "p:noop"))
    if (page + 1) * per < total:
        nav.append(B("▶️", f"p:t:list:{status}:{page+1}"))
    rows.append(nav)
    rows.append([B("🔴 Нові", "p:t:list:new:0"), B("🟡 В роботі", "p:t:list:work:0"),
                 B("✅ Закриті", "p:t:list:closed:0")])
    rows.append([B("🔍 Пошук", "p:t:find"), B("📥 Експорт CSV", "p:t:exp")])
    rows.append(BOTTOM("p:home"))
    await render(ev, f"⚙️ Панель › 📨 <b>Звернення</b> — {names.get(status,status)} ({total})\n\n"
                     + ("\n".join(lines) or "Порожньо."), kb(rows))


async def ticket_card(ev, uid: int, tid: int) -> None:
    r = await q1("SELECT t.*,u.uname,u.name,u.lang,u.created AS ucreated,u.banned FROM tickets t "
                 "LEFT JOIN users u ON u.id=t.uid WHERE t.id=?", tid)
    if not r:
        await tickets_list(ev, uid, "new", 0); return
    hist = await qa("SELECT id,body,created FROM tickets WHERE uid=? ORDER BY id DESC LIMIT 5", r["uid"])
    hl = "\n".join(f"• {ts(h['created'])} — {esc((h['body'] or '')[:60])}" for h in hist)
    un = f"@{r['uname']}" if r["uname"] else "@ немає"
    stat = {"new": "🔴 Нове", "work": "🟡 В роботі", "closed": "✅ Закрито"}.get(r["status"], r["status"])
    txt = (f"⚙️ Панель › 📨 <b>Звернення #{tid}</b>\n\n"
           f"👤 {esc(r['name'])}\n🔗 {esc(un)}\n🆔 <code>{r['uid']}</code>\n"
           f"🌍 {FLAG.get(r['lang'] or 'uk','')} {UP.get(r['lang'] or 'uk','UA')}\n"
           f"📅 Перший контакт: {ts(r['ucreated'])}\n🏷 Статус: {stat}"
           f"{' · Мітка: '+esc(r['tag']) if r['tag'] else ''}\n"
           f"{'👤 Взяв: '+esc(r['mgr']) if r['mgr'] else ''}\n"
           f"━━━━━━━━━━━━━━━━━━\n💬 {esc(r['body'] or '(медіа)')}\n\n"
           f"📜 <b>Історія:</b>\n{hl}")
    rows = [[B("✍️ Відповісти", f"p:t:r:{tid}")],
            [B("🟡 В роботу", f"p:t:work:{tid}"), B("✅ Закрити", f"p:t:done:{tid}")],
            [B("🏷 Мітка", f"p:t:tag:{tid}"),
             B("🚫 Розблокувати" if r["banned"] == 1 else "🚫 Заблокувати", f"p:t:ban:{tid}")]]
    if r["uname"]:
        rows.append([U("💬 Відкрити діалог", f"https://t.me/{r['uname']}")])
    rows.append(BOTTOM(f"p:t:list:{r['status']}:0"))
    await render(ev, txt, kb(rows), r["mtype"] or "", r["mid"] or "")


async def users_view(ev, uid: int, page: int) -> None:
    per = 10
    total = await scalar("SELECT COUNT(*) FROM users")
    act = await scalar("SELECT COUNT(*) FROM users WHERE seen>?", now() - 7 * 86400)
    wrote = await scalar("SELECT COUNT(DISTINCT uid) FROM tickets")
    banned = await scalar("SELECT COUNT(*) FROM users WHERE banned=1")
    byl = {r["lang"]: r["c"] for r in await qa("SELECT lang,COUNT(*) c FROM users GROUP BY lang")}
    ls = " · ".join(f"{FLAG.get(k,k)} {v}" for k, v in byl.items())
    rows_db = await qa("SELECT * FROM users ORDER BY seen DESC LIMIT ? OFFSET ?", per, page * per)
    lines = [f"{FLAG.get(u['lang'],'')} {esc(u['name'] or u['id'])} {esc(uname(u))} · {ts(u['seen'])}"
             + (" 🚫" if u["banned"] else "") for u in rows_db]
    rows = []
    nav = []
    if page > 0:
        nav.append(B("◀️", f"p:u:{page-1}"))
    nav.append(B(f"{page+1}/{max(1,(total+per-1)//per)}", "p:noop"))
    if (page + 1) * per < total:
        nav.append(B("▶️", f"p:u:{page+1}"))
    rows.append(nav)
    rows.append([B("🔍 Пошук", "p:u:find"), B("📥 Експорт CSV", "p:u:exp")])
    rows.append(BOTTOM("p:home"))
    await render(ev, f"⚙️ Панель › 👥 <b>Користувачі</b>\n\n"
                     f"Всього: <b>{total}</b> · активних за 7 днів: {act}\n"
                     f"Писали в підтримку: {wrote} · заблоковано: {banned}\n"
                     f"Мови: {ls}\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines), kb(rows))


async def settings_view(ev, uid: int) -> None:
    chat = CFG.get("chat_id") or "—"
    on = lambda k, d="1": "✅ увімк." if CFG.get(k, d) == "1" else "⬜ вимк."
    txt = (f"⚙️ Панель › ⚙️ <b>Налаштування</b>\n\n"
           f"📥 Чат для звернень: <code>{esc(chat)}</code>\n"
           f"🔔 Дублювати власнику: {on('notify')}\n"
           f"✅ Підтвердження клієнту: {on('confirm')}\n"
           f"📎 Приймати файли: {on('files')}\n"
           f"⬅️ Кнопка «Назад»: {on('backbtn')}\n"
           f"🐌 Антиспам: {CFG.get('spam','20')} сек\n"
           f"🔧 Технічний режим: {on('maint','0')}\n"
           f"🌐 Автопереклад правок: {on('autotr')}")
    rows = [[B("📥 Змінити чат", "p:s:chat"), B("🧪 Тест", "p:s:test")],
            [B("🔔 Дублювання", "p:s:notify"), B("✅ Підтвердження", "p:s:confirm")],
            [B("📎 Файли", "p:s:files"), B("⬅️ Кнопка «Назад»", "p:s:backbtn")],
            [B("🐌 Антиспам", "p:s:spam"), B("🔧 Техрежим", "p:s:maint")],
            [B("🌐 Автопереклад", "p:s:autotr")],
            BOTTOM("p:home")]
    await render(ev, txt, kb(rows))


async def stats_view(ev, uid: int) -> None:
    users = await scalar("SELECT COUNT(*) FROM users")
    d1 = await scalar("SELECT COUNT(*) FROM users WHERE created>?", now() - 86400)
    d7 = await scalar("SELECT COUNT(*) FROM users WHERE created>?", now() - 7 * 86400)
    tk = await scalar("SELECT COUNT(*) FROM tickets")
    tnew = await scalar("SELECT COUNT(*) FROM tickets WHERE status='new'")
    t7 = await scalar("SELECT COUNT(*) FROM tickets WHERE created>?", now() - 7 * 86400)
    top = await qa("SELECT id,views FROM nodes WHERE id<>1 ORDER BY views DESC LIMIT 5")
    lang = el(uid)
    tl = []
    for i, r in enumerate(top, 1):
        t = await node_tr(r["id"], lang)
        tl.append(f"{i}. {esc(t['label'] or '#'+str(r['id']))} — {r['views']}")
    await render(ev, f"⚙️ Панель › 📊 <b>Статистика</b>\n\n"
                     f"👥 Користувачів: <b>{users}</b>\n   +{d1} за добу · +{d7} за тиждень\n"
                     f"📨 Звернень: <b>{tk}</b> (🔴 {tnew} нових)\n   +{t7} за тиждень\n\n"
                     f"🔥 <b>Популярні розділи:</b>\n" + ("\n".join(tl) or "—"),
                 kb([[B("📥 Експорт користувачів", "p:u:exp"), B("📥 Експорт звернень", "p:t:exp")],
                     BOTTOM("p:home")]))


async def langs_view(ev, uid: int) -> None:
    on = langs_on()
    lines, btns = [], []
    total = await scalar("SELECT COUNT(*) FROM nodes")
    for l in LANGS:
        filled = await scalar("SELECT COUNT(*) FROM tr WHERE lang=? AND (label<>'' OR body<>'')", l)
        pct = int(filled * 100 / total) if total else 0
        lines.append(f"{LANGS[l]} — {'✅ увімк.' if l in on else '⬜ вимк.'} · заповнено {pct}%")
        btns.append(B(f"{FLAG[l]} {'✅' if l in on else '⬜'}", f"p:lt:{l}"))
    rows = grid(btns, 4)
    rows.append([B(f"🔄 За умовчанням: {UP.get(CFG.get('deflang','uk'), 'UA')}", "p:defl")])
    rows.append([B("📋 Скопіювати UA в усі", "p:cpall")])
    rows.append(BOTTOM("p:home"))
    await render(ev, "⚙️ Панель › 🌍 <b>Мови</b>\n\n" + "\n".join(lines), kb(rows))


async def admins_view(ev, uid: int) -> None:
    rows_db = await qa("SELECT * FROM admins ORDER BY id")
    lines = [f"{ROLES.get(a['role'],a['role'])} · <code>{a['id']}</code> {esc(a['name'])}" for a in rows_db]
    rows = [[B("➕ Додати", "p:a:add")]]
    for a in rows_db:
        if a["id"] != OWNER_ID:
            rows.append([B(f"🎭 {a['id']}", f"p:a:role:{a['id']}"), B("🗑", f"p:a:del:{a['id']}")])
    rows.append(BOTTOM("p:home"))
    await render(ev, "⚙️ Панель › 👮 <b>Адміни</b>\n\n" + "\n".join(lines) +
                 "\n\n<i>Додати: перешліть повідомлення від користувача або надішліть його ID.</i>", kb(rows))


async def broadcast_menu(ev, uid: int) -> None:
    total = await scalar("SELECT COUNT(*) FROM users WHERE banned=0")
    wrote = await scalar("SELECT COUNT(DISTINCT uid) FROM tickets")
    new7 = await scalar("SELECT COUNT(*) FROM users WHERE created>? AND banned=0", now() - 7 * 86400)
    rows = [[B(f"👥 Всім ({total})", "p:b:aud:all")],
            [B(f"📨 Хто писав ({wrote})", "p:b:aud:wrote"), B(f"🆕 Нові за 7 днів ({new7})", "p:b:aud:new7")]]
    rows += grid([B(f"{FLAG[l]} {UP[l]}", f"p:b:aud:l_{l}") for l in langs_on()], 4)
    rows.append(BOTTOM("p:home"))
    await render(ev, "⚙️ Панель › 📢 <b>Розсилка</b>\n\nКому надсилаємо?", kb(rows))


async def audience(kind: str) -> list[int]:
    if kind == "all":
        rs = await qa("SELECT id FROM users WHERE banned=0")
    elif kind == "wrote":
        rs = await qa("SELECT DISTINCT t.uid AS id FROM tickets t "
                      "JOIN users u ON u.id=t.uid WHERE u.banned=0")
    elif kind == "new7":
        rs = await qa("SELECT id FROM users WHERE created>? AND banned=0", now() - 7 * 86400)
    elif kind.startswith("l_"):
        rs = await qa("SELECT id FROM users WHERE lang=? AND banned=0", kind[2:])
    else:
        rs = []
    return [r["id"] for r in rs]


async def do_broadcast(bot: Bot, admin_id: int, ids: list[int], text: str, mtype: str, mid: str,
                       status_msg: Optional[Message]) -> None:
    ok = fail = 0
    for i, u in enumerate(ids, 1):
        try:
            await send_content(bot, u, text, None, mtype, mid)
            ok += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await send_content(bot, u, text, None, mtype, mid); ok += 1
            except Exception:
                fail += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            fail += 1
            await ex("UPDATE users SET banned=2 WHERE id=?", u)
        except Exception as e:
            fail += 1
            log.warning("broadcast %s: %s", u, e)
        if status_msg and i % 25 == 0:
            try:
                await status_msg.edit_text(f"📤 Надіслано {i}/{len(ids)} · ✅{ok} ❌{fail}")
            except TelegramBadRequest:
                pass
        await asyncio.sleep(BC_DELAY)
    if status_msg:
        try:
            await status_msg.edit_text(f"✅ <b>Розсилку завершено</b>\n\nДоставлено: {ok}\nНе доставлено: {fail}",
                                       reply_markup=kb([[B("🏠 Панель", "p:home")]]))
        except TelegramBadRequest:
            pass


async def sys_menu(ev, uid: int) -> None:
    lang = el(uid)
    keys = [("ask", "✍️ Запит повідомлення"), ("sent", "✅ Підтвердження"), ("unknown", "❓ Незрозумілий ввід"),
            ("blocked", "🚫 Заблокованому"), ("spam", "🐌 Антиспам"), ("maint", "🔧 Техроботи"),
            ("langsel", "🌍 Вибір мови"), ("answer", "💬 Шапка відповіді"), ("back", "⬅️ Кнопка Назад"),
            ("home", "🏠 Кнопка Меню"), ("cancel", "❌ Кнопка Скасувати")]
    rows = grid([B(t, f"p:sysx:{k}") for k, t in keys], 2)
    rows.append(BOTTOM("p:sec"))
    await render(ev, f"⚙️ Панель › ⚙️ <b>Службові повідомлення</b>\nМова: {FLAG.get(lang,'')} {UP.get(lang,lang)}\n\n"
                     "Оберіть, що редагувати.", kb(rows))

# ════════════════════════════ ВВОД ТЕКСТА ДЛЯ ПАНЕЛИ ════════════════════════════
async def admin_input(m: Message, st: dict) -> None:
    uid = m.from_user.id
    if not await is_admin(uid):
        ST.pop(uid, None); return
    k = st.get("k")
    lang = el(uid)
    text = body_of(m)
    mtype, mid = media_of(m)

    if k == "txt":
        nid = st["node"]
        if not text and not mid:
            await m.answer("⚠️ Надішліть текст."); return
        await save_body(nid, lang, text)
        ST.pop(uid, None)
        await m.answer("✅ Текст збережено.")
        await node_editor(m, uid, nid); return

    if k == "appn":
        try:
            n = int((m.text or "").strip())
        except ValueError:
            await m.answer("⚠️ Надішліть номер рядка цифрою."); return
        mode = st["mode"]
        t = await node_tr(st["node"], lang)
        lines = (t["body"] or "").split("\n")
        if not (1 <= n <= len(lines)):
            await m.answer(f"⚠️ Рядок має бути від 1 до {len(lines)}."); return
        if mode == "del":
            del lines[n - 1]
            await save_body(st["node"], lang, "\n".join(lines))
            ST.pop(uid, None)
            await m.answer("✅ Рядок видалено.")
            await node_editor(m, uid, st["node"]); return
        ST[uid] = {"k": "app", "node": st["node"], "mode": mode, "n": n}
        await m.answer("✍️ Тепер надішліть текст фрагмента.",
                       reply_markup=kb([[B("❌ Скасувати", f"p:n:{st['node']}")]])); return

    if k == "app":
        if not text:
            await m.answer("⚠️ Надішліть текст."); return
        nid, mode = st["node"], st["mode"]
        t = await node_tr(nid, lang)
        cur = t["body"] or ""
        lines = cur.split("\n") if cur else []
        if mode == "top":
            new = text + ("\n" + cur if cur else "")
        elif mode == "bot":
            new = (cur + "\n" if cur else "") + text
        elif mode == "after":
            lines.insert(st["n"], text); new = "\n".join(lines)
        elif mode == "repl":
            lines[st["n"] - 1] = text; new = "\n".join(lines)
        else:
            new = text
        await save_body(nid, lang, new)
        ST.pop(uid, None)
        await m.answer("✅ Збережено.")
        await node_editor(m, uid, nid); return

    if k == "med":
        if not mid:
            await m.answer("⚠️ Надішліть фото, відео, GIF, аудіо або документ."); return
        await ex("INSERT INTO tr(node,lang,mtype,mid) VALUES(?,?,?,?) "
                 "ON CONFLICT(node,lang) DO UPDATE SET mtype=?,mid=?", st["node"], lang, mtype, mid, mtype, mid)
        ST.pop(uid, None)
        await m.answer(f"✅ Медіа ({mtype}) збережено.")
        await node_editor(m, uid, st["node"]); return

    if k == "lbl":
        lab = (m.text or "").strip()
        if not lab:
            await m.answer("⚠️ Надішліть текст підпису."); return
        warn = "\n⚠️ Довгий підпис — на вузьких екранах обріжеться." if len(lab) > 24 else ""
        await ex("INSERT INTO tr(node,lang,label,machine) VALUES(?,?,?,0) "
                 "ON CONFLICT(node,lang) DO UPDATE SET label=?,machine=0",
                 st["node"], lang, lab[:64], lab[:64])
        with suppress(RuntimeError):
            asyncio.get_running_loop().create_task(autotranslate_node(st["node"], lang))
        ST.pop(uid, None)
        await m.answer(f"✅ Підпис збережено: [ {esc(lab[:64])} ]{warn}")
        await node_editor(m, uid, st["node"]); return

    if k == "sys":
        if not text:
            await m.answer("⚠️ Надішліть текст."); return
        await ex("INSERT INTO sys(k,lang,v) VALUES(?,?,?) ON CONFLICT(k,lang) DO UPDATE SET v=?",
                 st["key"], lang, text, text)
        ST.pop(uid, None)
        await m.answer("✅ Службовий текст оновлено.")
        await sys_menu(m, uid); return

    if k == "wiz_label":
        lab = (m.text or "").strip()
        if not lab:
            await m.answer("⚠️ Надішліть підпис кнопки."); return
        st["label"] = lab[:64]
        typ = st["typ"]
        if typ in ("page", "menu"):
            st["k"] = "wiz_body"
            await m.answer("📝 <b>Крок 3/4</b> — надішліть текст сторінки.\nМожна одразу з фото.",
                           reply_markup=kb([[B("⏭ Без тексту", "p:wskip"), B("❌ Скасувати", "p:sec")]]))
        elif typ == "url":
            st["k"] = "wiz_target"
            await m.answer("🔗 <b>Крок 3/4</b> — надішліть посилання (https://…).")
        elif typ == "phone":
            st["k"] = "wiz_target"
            await m.answer("📞 <b>Крок 3/4</b> — надішліть номер у форматі +380XXXXXXXXX.")
        elif typ == "loc":
            st["k"] = "wiz_target"
            await m.answer("📍 <b>Крок 3/4</b> — надішліть геолокацію або координати «50.45,30.52».")
        elif typ == "file":
            st["k"] = "wiz_target"
            await m.answer("📎 <b>Крок 3/4</b> — надішліть файл/фото, який отримуватиме клієнт.")
        elif typ == "goto":
            st["k"] = "wiz_target"
            await m.answer("↩️ <b>Крок 3/4</b> — надішліть ID розділу (дивіться в 🌳 Дереві).")
        else:  # form
            await wiz_finish(m, uid, st)
        return

    if k == "wiz_body":
        st["body"], st["mtype"], st["mid"] = text, mtype, mid
        await wiz_finish(m, uid, st); return

    if k == "wiz_target":
        typ = st["typ"]
        val = (m.text or "").strip()
        if typ == "url":
            if not val.startswith(("http://", "https://", "tg://")):
                await m.answer("⚠️ Посилання має починатись з https:// або tg://"); return
        elif typ == "phone":
            digits = val.replace(" ", "").replace("-", "")
            if not digits.startswith("+") or not digits[1:].isdigit():
                await m.answer("⚠️ Формат: +380XXXXXXXXX"); return
            val = digits
        elif typ == "loc":
            if m.location:
                val = f"{m.location.latitude},{m.location.longitude}"
            else:
                try:
                    la, lo = val.split(",")
                    float(la); float(lo)
                except Exception:
                    await m.answer("⚠️ Надішліть геолокацію або «50.45,30.52»"); return
        elif typ == "file":
            if not mid:
                await m.answer("⚠️ Надішліть файл або фото."); return
            st["mtype"], st["mid"], val = mtype, mid, ""
        elif typ == "goto":
            if not val.isdigit() or not await q1("SELECT 1 FROM nodes WHERE id=?", int(val)):
                await m.answer("⚠️ Такого розділу немає."); return
            if int(val) == st["parent"]:
                await m.answer("⚠️ Не можна посилатись сам на себе."); return
        st["target"] = val
        await wiz_finish(m, uid, st); return

    if k == "settgt":
        nid, typ = st["node"], st["typ"]
        val = (m.text or "").strip()
        if typ == "url" and not val.startswith(("http://", "https://", "tg://")):
            await m.answer("⚠️ Посилання має починатись з https:// або tg://"); return
        if typ == "phone":
            val = val.replace(" ", "").replace("-", "")
            if not (val.startswith("+") and val[1:].isdigit()):
                await m.answer("⚠️ Формат: +380XXXXXXXXX"); return
        if typ == "loc":
            if m.location:
                val = f"{m.location.latitude},{m.location.longitude}"
            else:
                try:
                    la, lo = val.split(","); float(la); float(lo)
                except Exception:
                    await m.answer("⚠️ Надішліть геолокацію або «50.45,30.52»"); return
        if typ == "goto":
            if not val.isdigit() or not await q1("SELECT 1 FROM nodes WHERE id=?", int(val)):
                await m.answer("⚠️ Такого розділу немає."); return
            if int(val) == nid:
                await m.answer("⚠️ Не можна посилатись сам на себе."); return
        if typ == "file":
            if not mid:
                await m.answer("⚠️ Надішліть файл або фото."); return
            await ex("INSERT INTO tr(node,lang,mtype,mid) VALUES(?,?,?,?) "
                     "ON CONFLICT(node,lang) DO UPDATE SET mtype=?,mid=?", nid, lang, mtype, mid, mtype, mid)
            val = ""
        await ex("UPDATE nodes SET target=? WHERE id=?", val, nid)
        ST.pop(uid, None)
        await m.answer("✅ Ціль оновлено.")
        await node_editor(m, uid, nid); return

    if k == "bc_text":
        if not text and not mid:
            await m.answer("⚠️ Надішліть текст або фото."); return
        st.update({"k": "bc_ready", "body": text, "mtype": mtype, "mid": mid})
        ids = await audience(st["aud"])
        await m.answer(f"👁 <b>Перегляд розсилки</b>\nОтримувачів: <b>{len(ids)}</b>")
        await send_content(m.bot, m.chat.id, text, kb([[B("📤 Надіслати", "p:b:go")],
                                                       [B("✏️ Переробити", f"p:b:aud:{st['aud']}"),
                                                        B("❌ Скасувати", "p:home")]]), mtype, mid)
        return

    if k == "reply":
        if not text and not mid:
            await m.answer("⚠️ Надішліть текст відповіді."); return
        t = await q1("SELECT * FROM tickets WHERE id=?", st["tid"])
        if not t:
            ST.pop(uid, None); await m.answer("⚠️ Звернення не знайдено."); return
        lg = await ulang(t["uid"])
        try:
            await send_content(m.bot, t["uid"], f"{await T('answer', lg)}\n\n{text}",
                               kb([[B(await T("home", lg), "home")]]), mtype, mid)
            await ex("UPDATE tickets SET status='work',mgr=? WHERE id=?",
                     f"@{m.from_user.username}" if m.from_user.username else str(uid), st["tid"])
            await m.answer("✅ Відповідь надіслано клієнту.")
        except TelegramForbiddenError:
            await m.answer("⚠️ Клієнт заблокував бота — доставити не вдалося.")
        except TelegramBadRequest as e:
            await m.answer(f"⚠️ Не вдалося надіслати: {esc(e)}")
        ST.pop(uid, None); return

    if k == "chat":
        cid = None
        if m.forward_from_chat:
            cid = m.forward_from_chat.id
        elif (m.text or "").strip().lstrip("-").isdigit():
            cid = int((m.text or "").strip())
        if cid is None:
            await m.answer("⚠️ Перешліть повідомлення з потрібного чату або надішліть його ID."); return
        await setcfg("chat_id", str(cid))
        ST.pop(uid, None)
        await m.answer(f"✅ Чат для звернень: <code>{cid}</code>")
        await settings_view(m, uid); return

    if k == "spam":
        v = (m.text or "").strip()
        if not v.isdigit():
            await m.answer("⚠️ Надішліть число секунд (0 — вимкнути)."); return
        await setcfg("spam", v)
        ST.pop(uid, None)
        await m.answer(f"✅ Антиспам: {v} сек.")
        await settings_view(m, uid); return

    if k == "tag":
        await ex("UPDATE tickets SET tag=? WHERE id=?", (m.text or "")[:32], st["tid"])
        ST.pop(uid, None)
        await m.answer("✅ Мітку збережено.")
        await ticket_card(m, uid, st["tid"]); return

    if k == "find_t":
        term = f"%{(m.text or '').strip()}%"
        rs = await qa("SELECT t.id,t.created,u.uname,u.name FROM tickets t LEFT JOIN users u ON u.id=t.uid "
                      "WHERE t.body LIKE ? OR u.uname LIKE ? OR u.name LIKE ? OR CAST(t.uid AS TEXT) LIKE ? "
                      "ORDER BY t.id DESC LIMIT 20", term, term, term, term)
        ST.pop(uid, None)
        lines = [f"#{r['id']} {esc('@'+r['uname'] if r['uname'] else r['name'])} · {ts(r['created'])}" for r in rs]
        await m.answer("🔍 <b>Результати:</b>\n" + ("\n".join(lines) or "нічого не знайдено"),
                       reply_markup=kb(grid([B(f"#{r['id']}", f"p:t:c:{r['id']}") for r in rs], 4) +
                                       [BOTTOM("p:home")])); return

    if k == "find_u":
        term = f"%{(m.text or '').strip()}%"
        rs = await qa("SELECT * FROM users WHERE uname LIKE ? OR name LIKE ? OR CAST(id AS TEXT) LIKE ? LIMIT 20",
                      term, term, term)
        ST.pop(uid, None)
        lines = [f"{FLAG.get(u['lang'],'')} {esc(u['name'])} {esc(uname(u))} · <code>{u['id']}</code>" for u in rs]
        await m.answer("🔍 <b>Результати:</b>\n" + ("\n".join(lines) or "нічого не знайдено"),
                       reply_markup=kb([BOTTOM("p:home")])); return

    if k == "admin_add":
        aid = None
        if m.forward_from:
            aid, nm = m.forward_from.id, m.forward_from.full_name
        elif (m.text or "").strip().isdigit():
            aid, nm = int((m.text or "").strip()), ""
        if not aid:
            await m.answer("⚠️ Перешліть повідомлення від користувача або надішліть ID."); return
        await ex("INSERT INTO admins(id,role,name) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=?",
                 aid, "tickets", nm, nm)
        ST.pop(uid, None)
        await m.answer(f"✅ Додано: <code>{aid}</code> (роль: тільки звернення).")
        await admins_view(m, uid); return

    if k == "restore":
        if not m.document:
            await m.answer("⚠️ Надішліть файл бекапу (.json)."); return
        try:
            f = await m.bot.get_file(m.document.file_id)
            buf = await m.bot.download_file(f.file_path)
            data = json.loads(buf.read().decode("utf-8"))
            await db.execute("DELETE FROM nodes"); await db.execute("DELETE FROM tr")
            await db.execute("DELETE FROM sys"); await db.execute("DELETE FROM cfg")
            for tbl in ("nodes", "tr", "sys", "cfg"):
                for row in data.get(tbl, []):
                    cols = ",".join(row.keys())
                    ph = ",".join("?" * len(row))
                    await db.execute(f"INSERT INTO {tbl}({cols}) VALUES({ph})", tuple(row.values()))
            await db.commit()
            CFG.clear()
            for r in await qa("SELECT k,v FROM cfg"):
                CFG[r["k"]] = r["v"]
            ST.pop(uid, None)
            await m.answer("✅ Конфігурацію відновлено з бекапу.")
        except Exception as e:
            await m.answer(f"⚠️ Помилка відновлення: {esc(e)}")
        return

    ST.pop(uid, None)
    await m.answer("Скасовано.")


async def wiz_finish(m: Message, uid: int, st: dict) -> None:
    parent = st["parent"]
    pos = await scalar("SELECT COALESCE(MAX(pos),-1)+1 FROM nodes WHERE parent=?", parent)
    prow = await q1("SELECT roww FROM nodes WHERE id=?", parent)
    nid = await ex("INSERT INTO nodes(parent,typ,target,pos,roww,draft) VALUES(?,?,?,?,?,1)",
                   parent, st["typ"], st.get("target", ""), pos, (prow["roww"] if prow else 2))
    lang = el(uid)
    for l in langs_on():
        await db.execute("INSERT OR IGNORE INTO tr(node,lang,label,body,mtype,mid) VALUES(?,?,?,?,?,?)",
                         (nid, l, st["label"], st.get("body", "") if l == lang else "",
                          st.get("mtype", "") if l == lang else "", st.get("mid", "") if l == lang else ""))
    await db.commit()
    ST.pop(uid, None)
    await m.answer(f"✅ Кнопку створено як <b>чернетку</b>.\nПеревірте та натисніть «🚀 Опублікувати».")
    await node_editor(m, uid, nid)

# ── користувач обрав чат нативним вибором Telegram ──
@adm_r.message(F.chat_shared, F.chat.type == "private")
async def on_chat_shared(m: Message) -> None:
    """Спрацьовує, коли адмін обрав чат кнопкою «Вибрати групу/канал»."""
    uid = m.from_user.id
    if not await is_admin(uid):
        return
    sh = m.chat_shared
    cid = sh.chat_id
    title = getattr(sh, "title", "") or ""
    uname = getattr(sh, "username", "") or ""
    await setcfg("chat_id", str(cid))
    ST.pop(uid, None)

    name = f"<b>{esc(title)}</b>" if title else f"<code>{cid}</code>"
    if uname:
        name += f" (@{esc(uname)})"
    await m.answer(f"✅ Звернення надходитимуть у {name}", reply_markup=ReplyKeyboardRemove())

    # одразу перевіряємо, чи бот справді може туди писати
    try:
        await m.bot.send_message(cid, "✅ <b>EUROTOUR</b>\nЦей чат обрано для звернень клієнтів.")
        await m.answer("🧪 Перевірка пройшла: повідомлення в чат доставлено.")
    except Exception as e:
        await m.answer(f"⚠️ Чат збережено, але надіслати туди не вдалося:\n<code>{esc(e)}</code>\n\n"
                       "Додайте бота в чат і дайте право писати повідомлення.")
    await settings_view(m, uid)


@adm_r.message(F.text == "❌ Скасувати", F.chat.type == "private")
async def on_pick_cancel(m: Message) -> None:
    if not await is_admin(m.from_user.id):
        return
    ST.pop(m.from_user.id, None)
    await m.answer("❌ Скасовано.", reply_markup=ReplyKeyboardRemove())
    await settings_view(m, m.from_user.id)


# ════════════════════════════ CALLBACK ПАНЕЛИ ════════════════════════════
@adm_r.message(Command("panel"), F.chat.type == "private")
async def cmd_panel(m: Message) -> None:
    if not await is_admin(m.from_user.id):
        return                                   # молча, без подсказок
    ST.pop(m.from_user.id, None)
    await panel_home(m, m.from_user.id)


@adm_r.callback_query(F.data.startswith("p:"), F.message.chat.type == "private")
async def panel_cb(c: CallbackQuery) -> None:
    uid = c.from_user.id
    if not await is_admin(uid):
        await c.answer()                          # тихо игнорируем чужих
        return
    p = c.data.split(":")
    sec = p[1] if len(p) > 1 else "home"
    arg = p[2] if len(p) > 2 else ""
    arg2 = p[3] if len(p) > 3 else ""
    arg3 = p[4] if len(p) > 4 else ""
    lang = el(uid)
    await c.answer()

    # ── общее ──
    if sec == "home":
        ST.pop(uid, None); await panel_home(c, uid); return
    if sec == "noop":
        return
    if sec == "exit":
        ST.pop(uid, None); LIVE.discard(uid); await show_node(c, 1, uid); return
    if sec == "live":
        LIVE.add(uid)
        await render(c, "👁 <b>Живе редагування увімкнено</b>\n\nХодіть по боту як клієнт — під кожним "
                        "екраном буде службовий рядок.",
                     kb([[B("▶️ Почати з головного меню", "p:livego")], BOTTOM("p:home")])); return
    if sec == "livego":
        await show_node(c, 1, uid); return
    if sec == "liveoff":
        LIVE.discard(uid); await panel_home(c, uid); return
    if sec == "elang":
        order = langs_on()
        ELANG[uid] = order[(order.index(lang) + 1) % len(order)] if lang in order else order[0]
        await sec_menu(c, uid); return

    # ── разделы / узлы ──
    if sec == "sec":
        await sec_menu(c, uid); return
    if sec == "tree":
        await tree_view(c, uid); return
    if sec == "n":
        if not I(arg):
            await sec_menu(c, uid); return
        await node_editor(c, uid, I(arg)); return
    if sec == "btn":
        await buttons_view(c, uid, I(arg)); return
    if sec == "ord":
        await order_view(c, uid, I(arg)); return
    if sec == "mv":
        await move(I(arg), arg2)
        n = await q1("SELECT parent FROM nodes WHERE id=?", I(arg))
        await order_view(c, uid, n["parent"] if n else 1); return
    if sec == "roww":
        n = await q1("SELECT roww FROM nodes WHERE id=?", I(arg))
        await ex("UPDATE nodes SET roww=? WHERE id=?", (n["roww"] % 3) + 1 if n else 2, I(arg))
        await buttons_view(c, uid, I(arg)); return
    if sec == "txt":
        ST[uid] = {"k": "txt", "node": I(arg)}
        t = await node_tr(I(arg), lang)
        await render(c, f"✏️ <b>Новий текст розділу</b>\nМова: {FLAG.get(lang,'')} {UP.get(lang,lang)}\n\n"
                        f"Поточний:\n━━━━━━\n{t['body'] or '—'}\n━━━━━━\n\nНадішліть новий текст "
                        f"(форматування Telegram зберігається).",
                     kb([[B("❌ Скасувати", f"p:n:{arg}")]])); return
    if sec == "app":
        t = await node_tr(I(arg), lang)
        lines = (t["body"] or "").split("\n")
        numbered = "\n".join(f"{i+1} │ {esc(l)}" for i, l in enumerate(lines[:30]))
        await render(c, f"➕ <b>Дописати</b>\n\n{numbered or '(порожньо)'}\n\nКуди вставити фрагмент?",
                     kb([[B("⬆️ На початок", f"p:appm:{arg}:top"), B("⬇️ У кінець", f"p:appm:{arg}:bot")],
                         [B("🎯 Після рядка №", f"p:appm:{arg}:after"),
                          B("✂️ Замінити рядок №", f"p:appm:{arg}:repl")],
                         [B("🗑 Видалити рядок №", f"p:appm:{arg}:del")],
                         BOTTOM(f"p:n:{arg}")])); return
    if sec == "appm":
        if arg2 in ("top", "bot"):
            ST[uid] = {"k": "app", "node": I(arg), "mode": arg2}
            await render(c, "✍️ Надішліть текст фрагмента.", kb([[B("❌ Скасувати", f"p:n:{arg}")]]))
        else:
            ST[uid] = {"k": "appn", "node": I(arg), "mode": arg2}
            await render(c, "🔢 Надішліть номер рядка.", kb([[B("❌ Скасувати", f"p:n:{arg}")]]))
        return
    if sec == "med":
        t = await node_tr(I(arg), lang)
        ST[uid] = {"k": "med", "node": I(arg)}
        await render(c, f"🖼 <b>Медіа розділу</b>\nПоточне: {t['mtype'] or '—'}\n\n"
                        f"Надішліть фото, відео, GIF, аудіо або документ.\n"
                        f"<i>Якщо текст довший за 1024 символи — медіа піде окремим повідомленням.</i>",
                     kb([[B("🗑 Видалити медіа", f"p:medel:{arg}")], [B("❌ Скасувати", f"p:n:{arg}")]])); return
    if sec == "medel":
        await ex("UPDATE tr SET mtype='',mid='' WHERE node=? AND lang=?", I(arg), lang)
        ST.pop(uid, None); await node_editor(c, uid, I(arg)); return
    if sec == "lbl":
        ST[uid] = {"k": "lbl", "node": I(arg)}
        await render(c, "🏷 Надішліть новий підпис кнопки (1–3 слова + емодзі).",
                     kb([[B("❌ Скасувати", f"p:n:{arg}")]])); return
    if sec == "typ":
        n = await q1("SELECT * FROM nodes WHERE id=?", I(arg))
        await render(c, f"🔗 <b>Тип кнопки</b>: <code>{n['typ'] if n else '?'}</code>\n"
                        f"Ціль: <code>{esc(n['target']) if n else ''}</code>\n\nОберіть новий тип:",
                     kb([[B("📄 Сторінка", f"p:sett:{arg}:page"), B("📂 Підменю", f"p:sett:{arg}:menu")],
                         [B("🔗 Посилання", f"p:sett:{arg}:url"), B("✍️ Форма", f"p:sett:{arg}:form")],
                         [B("📞 Телефон", f"p:sett:{arg}:phone"), B("📍 Гео", f"p:sett:{arg}:loc")],
                         [B("📎 Файл", f"p:sett:{arg}:file"), B("↩️ Перехід", f"p:sett:{arg}:goto")],
                         BOTTOM(f"p:n:{arg}")])); return
    if sec == "sett":
        nid = I(arg)
        await ex("UPDATE nodes SET typ=? WHERE id=?", arg2, nid)
        if arg2 in ("url", "phone", "loc", "goto", "file"):
            ST[uid] = {"k": "settgt", "node": nid, "typ": arg2}
            hint = {"url": "https://example.com", "phone": "+380XXXXXXXXX", "loc": "геолокацію або «50.45,30.52»",
                    "goto": "ID розділу з 🌳 Дерева", "file": "файл або фото"}[arg2]
            await render(c, f"🔗 Надішліть нову ціль: {hint}", kb([[B("❌ Скасувати", f"p:n:{nid}")]])); return
        await node_editor(c, uid, nid); return
    if sec == "vis":
        n = await q1("SELECT draft,hidden FROM nodes WHERE id=?", I(arg))
        if n and n["draft"]:
            await ex("UPDATE nodes SET draft=0 WHERE id=?", I(arg))
        elif n and n["hidden"]:
            await ex("UPDATE nodes SET hidden=0 WHERE id=?", I(arg))
        else:
            await ex("UPDATE nodes SET hidden=1 WHERE id=?", I(arg))
        await node_editor(c, uid, I(arg)); return
    if sec == "del":
        n = await q1("SELECT * FROM nodes WHERE id=?", I(arg))
        if not n or n["id"] == 1:
            await panel_home(c, uid); return
        kids = await scalar("SELECT COUNT(*) FROM nodes WHERE parent=?", I(arg))
        await render(c, f"⚠️ <b>Видалити розділ?</b>\n\nРазом з ним видаляться вкладені кнопки: {kids}\n"
                        f"Копію буде збережено в кошику на 30 днів.",
                     kb([[B("🗑 Так, видалити", f"p:delok:{arg}")], [B("❌ Скасувати", f"p:n:{arg}")]])); return
    if sec == "delok":
        n = await q1("SELECT parent FROM nodes WHERE id=?", I(arg))
        parent = n["parent"] if n else 1
        await del_subtree(I(arg))
        await render(c, "🗑 Видалено. Копія збережена в кошику.", kb([[B("⬅️ Далі", f"p:btn:{parent}")]])); return
    if sec == "copy":
        n = await q1("SELECT parent FROM nodes WHERE id=?", I(arg))
        new = await copy_node(I(arg), n["parent"] if n else 1)
        await node_editor(c, uid, new); return
    if sec == "prev":
        n = await q1("SELECT * FROM nodes WHERE id=?", I(arg))
        t = await node_tr(I(arg), lang)
        await send_content(c.bot, c.message.chat.id, t["body"] or "(без тексту)",
                           await build_kb(I(arg), lang, False, False), t["mtype"] or "", t["mid"] or "")
        await c.message.answer("👆 Так це побачить клієнт.",
                               reply_markup=kb([[B("⬅️ До розділу", f"p:n:{arg}")]])); return
    if sec == "tr":
        rows = []
        for l in LANGS:
            t = await q1("SELECT label,body FROM tr WHERE node=? AND lang=?", I(arg), l)
            mark = "✅" if t and (t["label"] or t["body"]) else "⚠️"
            rows.append(B(f"{FLAG[l]} {UP[l]} {mark}", f"p:trl:{arg}:{l}"))
        await render(c, "🌍 <b>Переклади розділу</b>\n\nОберіть мову для редагування:",
                     kb(grid(rows, 2) + [[B("📋 Скопіювати поточну в усі", f"p:trc:{arg}")], BOTTOM(f"p:n:{arg}")])); return
    if sec == "trl":
        ELANG[uid] = arg2
        await node_editor(c, uid, I(arg)); return
    if sec == "trc":
        src = await q1("SELECT * FROM tr WHERE node=? AND lang=?", I(arg), lang)
        if src:
            for l in LANGS:
                if l != lang:
                    await db.execute("INSERT INTO tr(node,lang,label,body,mtype,mid) VALUES(?,?,?,?,?,?) "
                                     "ON CONFLICT(node,lang) DO UPDATE SET label=?,body=?,mtype=?,mid=?",
                                     (I(arg), l, src["label"], src["body"], src["mtype"], src["mid"],
                                      src["label"], src["body"], src["mtype"], src["mid"]))
            await db.commit()
        await node_editor(c, uid, I(arg)); return
    if sec == "hist":
        hs = await qa("SELECT * FROM hist WHERE node=? AND lang=? ORDER BY id DESC LIMIT ?",
                      I(arg), lang, HIST_KEEP)
        lines = [f"{i+1}. {ts(h['ts'])} — {esc((h['body'] or '')[:50])}" for i, h in enumerate(hs)]
        rows = grid([B(f"↩️ {i+1}", f"p:histr:{arg}:{h['id']}") for i, h in enumerate(hs)], 4)
        rows.append(BOTTOM(f"p:n:{arg}"))
        await render(c, "↩️ <b>Історія версій</b>\n\n" + ("\n".join(lines) or "Історія порожня."), kb(rows)); return
    if sec == "histr":
        h = await q1("SELECT * FROM hist WHERE id=?", I(arg2))
        if h:
            await save_body(I(arg), lang, h["body"])
        await node_editor(c, uid, I(arg)); return
    if sec == "add":
        ST[uid] = {"k": "wiz_type", "parent": I(arg)}
        await render(c, "➕ <b>Нова кнопка · Крок 1/4</b>\n\nЩо робитиме кнопка?",
                     kb([[B("📄 Сторінка", f"p:wt:{arg}:page"), B("📂 Підменю", f"p:wt:{arg}:menu")],
                         [B("🔗 Посилання", f"p:wt:{arg}:url"), B("✍️ Форма звернення", f"p:wt:{arg}:form")],
                         [B("📞 Телефон", f"p:wt:{arg}:phone"), B("📍 Геолокація", f"p:wt:{arg}:loc")],
                         [B("📎 Файл", f"p:wt:{arg}:file"), B("↩️ Перехід у розділ", f"p:wt:{arg}:goto")],
                         BOTTOM(f"p:btn:{arg}")])); return
    if sec == "wt":
        ST[uid] = {"k": "wiz_label", "parent": I(arg), "typ": arg2}
        await render(c, f"➕ <b>Крок 2/4 — Підпис кнопки</b>\nТип: <code>{arg2}</code>\n\n"
                        f"Надішліть текст, який буде на кнопці.\n"
                        f"💡 1–3 слова + емодзі. Приклад: 🚌 Наші переваги",
                     kb([[B("❌ Скасувати", f"p:btn:{arg}")]])); return
    if sec == "wskip":
        st = ST.get(uid)
        if st and st.get("k") == "wiz_body":
            st.update({"body": "", "mtype": "", "mid": ""})
            await wiz_finish(c.message, uid, st)
        return

    # ── служебные тексты ──
    if sec == "sys":
        await sys_menu(c, uid); return
    if sec == "sysx":
        cur = await T(arg, lang)
        ST[uid] = {"k": "sys", "key": arg}
        await render(c, f"⚙️ <b>{arg}</b> · {FLAG.get(lang,'')} {UP.get(lang,lang)}\n\n"
                        f"Поточний текст:\n━━━━━━\n{cur}\n━━━━━━\n\nНадішліть новий.",
                     kb([[B("❌ Скасувати", "p:sys")]])); return

    # ── обращения ──
    if sec == "t":
        if arg == "list":
            await tickets_list(c, uid, arg2 or "new", int(arg3 or 0)); return
        if arg == "c":
            await ticket_card(c, uid, I(arg2)); return
        if arg == "r":
            ST[uid] = {"k": "reply", "tid": I(arg2)}
            await c.message.answer(f"✍️ Надішліть відповідь для звернення #{arg2}. "
                                   f"Вона піде клієнту від імені бота.",
                                   reply_markup=kb([[B("❌ Скасувати", "p:home")]])); return
        if arg == "work":
            await ex("UPDATE tickets SET status='work',mgr=? WHERE id=?",
                     f"@{c.from_user.username}" if c.from_user.username else str(uid), I(arg2))
            await ticket_card(c, uid, I(arg2)); return
        if arg == "done":
            await ex("UPDATE tickets SET status='closed',mgr=? WHERE id=?",
                     f"@{c.from_user.username}" if c.from_user.username else str(uid), I(arg2))
            if c.message and c.message.chat.type != "private":
                try:
                    await c.message.edit_reply_markup(
                        reply_markup=kb([[B(f"✔️ Закрив: @{c.from_user.username or uid}", "p:noop")]]))
                except TelegramBadRequest:
                    pass
                return
            await ticket_card(c, uid, I(arg2)); return
        if arg == "tag":
            ST[uid] = {"k": "tag", "tid": I(arg2)}
            await c.message.answer("🏷 Надішліть текст мітки."); return
        if arg == "ban":
            t = await q1("SELECT uid FROM tickets WHERE id=?", I(arg2))
            if t:
                u = await q1("SELECT banned FROM users WHERE id=?", t["uid"])
                await ex("UPDATE users SET banned=? WHERE id=?", 0 if (u and u["banned"] == 1) else 1, t["uid"])
            await ticket_card(c, uid, I(arg2)); return
        if arg == "find":
            ST[uid] = {"k": "find_t"}
            await c.message.answer("🔍 Надішліть @юзернейм, ім'я, ID або слово з тексту."); return
        if arg == "exp":
            rs = await qa("SELECT t.id,t.uid,u.uname,u.name,t.body,t.status,t.tag,t.created "
                          "FROM tickets t LEFT JOIN users u ON u.id=t.uid ORDER BY t.id")
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["id", "user_id", "username", "name", "text", "status", "tag", "date"])
            for r in rs:
                w.writerow([r["id"], r["uid"], r["uname"], r["name"], (r["body"] or "").replace("\n", " "),
                            r["status"], r["tag"], ts(r["created"])])
            await c.message.answer_document(
                BufferedInputFile(buf.getvalue().encode("utf-8-sig"), "tickets.csv"), caption="📥 Звернення")
            return

    # ── пользователи ──
    if sec == "u":
        if arg == "find":
            ST[uid] = {"k": "find_u"}
            await c.message.answer("🔍 Надішліть @юзернейм, ім'я або ID."); return
        if arg == "exp":
            rs = await qa("SELECT * FROM users ORDER BY id")
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["id", "username", "name", "lang", "created", "last_seen", "messages", "banned"])
            for r in rs:
                w.writerow([r["id"], r["uname"], r["name"], r["lang"], ts(r["created"]),
                            ts(r["seen"]), r["msgs"], r["banned"]])
            await c.message.answer_document(
                BufferedInputFile(buf.getvalue().encode("utf-8-sig"), "users.csv"), caption="📥 Користувачі")
            return
        await users_view(c, uid, I(arg)); return

    # ── рассылка ──
    if sec == "b":
        if arg == "menu":
            await broadcast_menu(c, uid); return
        if arg == "aud":
            ids = await audience(arg2)
            ST[uid] = {"k": "bc_text", "aud": arg2}
            await render(c, f"📢 <b>Розсилка</b>\nОтримувачів: <b>{len(ids)}</b>\n\n"
                            f"Надішліть текст (можна з фото).",
                         kb([[B("❌ Скасувати", "p:home")]])); return
        if arg == "go":
            st = ST.get(uid)
            if not st or st.get("k") != "bc_ready":
                await panel_home(c, uid); return
            ids = await audience(st["aud"])
            ST.pop(uid, None)
            sm = await c.message.answer(f"📤 Починаю розсилку на {len(ids)} користувачів…")
            asyncio.create_task(do_broadcast(c.bot, uid, ids, st["body"], st["mtype"], st["mid"], sm))
            return

    # ── настройки ──
    if sec == "s":
        if arg == "menu":
            await settings_view(c, uid); return
        if arg in ("notify", "confirm", "files", "backbtn", "maint", "autotr"):
            await setcfg(arg, "0" if CFG.get(arg, "1") == "1" else "1")
            await settings_view(c, uid); return
        if arg == "chat":
            ST[uid] = {"k": "chat"}
            # Нативний вибір: Telegram сам покаже список ваших груп/каналів.
            # Кнопка живе на звичайній (reply) клавіатурі — інакше API не дозволяє.
            picker = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="👥 Вибрати групу",
                                    request_chat=KeyboardButtonRequestChat(
                                        request_id=1, chat_is_channel=False,
                                        bot_is_member=True,
                                        request_title=True, request_username=True))],
                    [KeyboardButton(text="📢 Вибрати канал",
                                    request_chat=KeyboardButtonRequestChat(
                                        request_id=2, chat_is_channel=True,
                                        bot_is_member=True,
                                        request_title=True, request_username=True))],
                    [KeyboardButton(text="❌ Скасувати")],
                ],
                resize_keyboard=True, one_time_keyboard=True,
                input_field_placeholder="Оберіть чат кнопкою нижче")
            await c.answer()
            await c.message.answer(
                "📥 <b>Чат для звернень</b>\n\n"
                "Натисніть кнопку внизу — Telegram покаже список ваших чатів, "
                "просто оберіть потрібний.\n\n"
                "<i>Показуються лише ті чати, де бот уже є учасником. "
                "Якщо потрібного немає — спершу додайте бота в той чат.</i>",
                reply_markup=picker)
            return
        if arg == "spam":
            ST[uid] = {"k": "spam"}
            await render(c, f"🐌 Поточний інтервал: {CFG.get('spam','20')} сек.\nНадішліть нове число (0 — вимкнути).",
                         kb([[B("❌ Скасувати", "p:s:menu")]])); return
        if arg == "test":
            cid = CFG.get("chat_id")
            if not cid:
                await c.message.answer("⚠️ Чат не налаштовано."); return
            try:
                await c.bot.send_message(int(cid), "🧪 <b>Тест EUROTOUR</b>\nЗв'язок із чатом працює ✅")
                await c.message.answer("✅ Тестове повідомлення надіслано.")
            except Exception as e:
                await c.message.answer(f"⚠️ Не вдалося: {esc(e)}\n\nПеревірте, що бот доданий у чат.")
            return

    # ── языки ──
    if sec == "langs":
        await langs_view(c, uid); return
    if sec == "lt":
        on = langs_on()
        if arg in on and len(on) > 1:
            on.remove(arg)
        elif arg not in on:
            on.append(arg)
        await setcfg("langs", ",".join(on))
        await langs_view(c, uid); return
    if sec == "defl":
        on = langs_on()
        cur = CFG.get("deflang", "uk")
        await setcfg("deflang", on[(on.index(cur) + 1) % len(on)] if cur in on else on[0])
        await langs_view(c, uid); return
    if sec == "cpall":
        for n in await qa("SELECT id FROM nodes"):
            src = await q1("SELECT * FROM tr WHERE node=? AND lang='uk'", n["id"])
            if not src:
                continue
            for l in LANGS:
                if l == "uk":
                    continue
                cur = await q1("SELECT label,body FROM tr WHERE node=? AND lang=?", n["id"], l)
                if cur and (cur["label"] or cur["body"]):
                    continue
                await db.execute("INSERT INTO tr(node,lang,label,body,mtype,mid) VALUES(?,?,?,?,?,?) "
                                 "ON CONFLICT(node,lang) DO UPDATE SET label=?,body=?",
                                 (n["id"], l, src["label"], src["body"], src["mtype"], src["mid"],
                                  src["label"], src["body"]))
        await db.commit()
        await langs_view(c, uid); return

    # ── медиа/статистика/админы/бэкап ──
    if sec == "medial":
        rows, line = [], []
        for n in await qa("SELECT id FROM nodes ORDER BY id"):
            t = await node_tr(n["id"], lang)
            mark = "🖼" if t["mid"] else "▫️"
            line.append(B(f"{mark} {(t['label'] or '👋 Привітання')[:18]}", f"p:med:{n['id']}"))
        rows = grid(line, 2)
        rows.append(BOTTOM("p:home"))
        await render(c, "🖼 <b>Медіа</b>\n\nОберіть розділ, щоб додати або замінити фото/відео.", kb(rows)); return
    if sec == "stat":
        await stats_view(c, uid); return
    if sec == "a":
        if not await can(uid, "admins"):
            await c.message.answer("Недостатньо прав."); return
        if arg == "list":
            await admins_view(c, uid); return
        if arg == "add":
            ST[uid] = {"k": "admin_add"}
            await render(c, "➕ Перешліть повідомлення від користувача або надішліть його ID.",
                         kb([[B("❌ Скасувати", "p:a:list")]])); return
        if arg == "role":
            a = await q1("SELECT role FROM admins WHERE id=?", I(arg2))
            order = ["tickets", "full"]
            new = order[(order.index(a["role"]) + 1) % 2] if a and a["role"] in order else "tickets"
            await ex("UPDATE admins SET role=? WHERE id=?", new, I(arg2))
            await admins_view(c, uid); return
        if arg == "del":
            if I(arg2) != OWNER_ID:
                await ex("DELETE FROM admins WHERE id=?", I(arg2))
            await admins_view(c, uid); return
    if sec == "bk":
        if arg == "make" or not arg:
            data = {t: [dict(r) for r in await qa(f"SELECT * FROM {t}")] for t in ("nodes", "tr", "sys", "cfg")}
            raw = json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
            await c.message.answer_document(
                BufferedInputFile(raw, f"eurotour_backup_{time.strftime('%Y%m%d_%H%M')}.json"),
                caption="💾 Бекап конфігурації бота",
                reply_markup=kb([[B("📥 Відновити з файлу", "p:bk:restore")], BOTTOM("p:home")]))
            return
        if arg == "restore":
            ST[uid] = {"k": "restore"}
            await c.message.answer("📥 Надішліть файл бекапу (.json).\n⚠️ Поточна конфігурація буде замінена.",
                                   reply_markup=kb([[B("❌ Скасувати", "p:home")]])); return

    await panel_home(c, uid)


@adm_r.message(F.chat.type.in_({"group", "supergroup"}))
async def group_msg(m: Message) -> None:
    """У групі бот НЕ показує меню й панель.

    Єдине, що він тут робить, — приймає відповідь менеджера клієнту
    (коли той натиснув «✍️ Відповісти» під зверненням). Усе інше
    ігнорується повністю: бот у чаті мовчить.
    """
    if not m.from_user:
        return
    st = ST.get(m.from_user.id)
    # реагуємо лише на очікувану відповідь клієнту, і лише від адміна
    if st and st.get("k") in ("reply", "tag") and await is_admin(m.from_user.id):
        await admin_input(m, st)

# ════════════════════════════ ЗАПУСК ════════════════════════════
async def start_health_server(username: str = ""):
    """Мінівеб-сервер для безкоштовних хостингів (Render/Koyeb/Railway).

    Вони вимагають відкритий HTTP-порт і «пінгують» його, щоб сервіс не заснув.
    Локально просто нічого не робить, якщо порт зайнятий.
    """
    port = int(os.getenv("PORT", "0"))
    if not port:
        return None
    try:
        from aiohttp import web
    except ImportError:
        return None

    async def health(_req):
        return web.json_response({"status": "ok", "bot": username, "ts": now()})

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "0.0.0.0", port).start()
        log.info("Health-сервер на порту %s", port)
        return runner
    except OSError as e:
        log.warning("Health-сервер не піднявся: %s", e)
        await runner.cleanup()
        return None


# ── налаштування стійкості ──
WATCHDOG_EVERY = 60       # як часто перевіряти звʼязок, сек
WATCHDOG_SILENCE = 180    # після якої тиші робити контрольний запит, сек
WATCHDOG_FAILS = 3        # скільки невдач поспіль → перезапуск процесу
# IPV4=0 у змінних оточення — не форсувати IPv4 (якщо хостинг лише на IPv6)
FORCE4 = os.getenv("IPV4", "1").strip() not in ("0", "no", "false", "")


def make_session() -> AiohttpSession:
    """Сесія, стійка до проблем мережі на хостингу.

    Головна причина «Cannot connect to host api.telegram.org:443» —
    хостинг віддає IPv6-адресу, а справжнього IPv6 у нього немає:
    зʼєднання просто не встановлюється. Тому змушуємо ходити через IPv4
    і збільшуємо запас часу на зʼєднання.
    """
    import socket
    import ssl as _ssl
    try:
        import certifi
        ctx = _ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = _ssl.create_default_context()

    s = AiohttpSession(timeout=60)
    init = {
        "ssl": ctx,
        "limit": 100,
        "ttl_dns_cache": 300,
        "force_close": False,
        "enable_cleanup_closed": True,
    }
    # IPv4 форсуємо ЛИШЕ якщо IPv4-адреса справді резолвиться.
    # Інакше (буває на деяких хостингах) жорсткий AF_INET сам обриває звʼязок —
    # тоді лишаємо автовибір, хай система обере IPv6.
    if FORCE4 is not False:
        try:
            socket.getaddrinfo("api.telegram.org", 443, family=socket.AF_INET)
            init["family"] = socket.AF_INET
        except Exception:
            log.warning("IPv4 недоступний — використовую автовибір адреси.")
    s._connector_init = init
    # проксі, якщо хостинг без прямого доступу до Telegram
    px = os.getenv("PROXY", "").strip()
    if px:
        with suppress(Exception):
            s._setup_proxy_connector(px)
            log.info("Використовую проксі: %s", px)
    return s


RESTART_DELAY = 5         # пауза перед внутрішнім перепідключенням, сек
CONFLICTS = 0             # лічильник помилок Conflict (друга копія бота)
FATAL: list[str] = []     # текст фатальної помилки для показу користувачу
NETOK: list[int] = []     # ознака успішного зʼєднання (скидає лічильник збоїв)


class Fatal(Exception):
    """Причина, через яку бот не може працювати (показуємо людині без трейсбека)."""

LAST_OK: Optional[float] = None       # час останнього успішного контакту з Telegram


@adm_r.errors()
@user_r.errors()
async def on_error(event) -> bool:
    """Глобальний перехоплювач: жодна помилка в хендлері не вбиває бота."""
    exc = getattr(event, "exception", None)
    upd = getattr(event, "update", None)
    text = str(exc)

    # ── нешкідливі помилки: пишемо коротко, без трейсбека ──
    QUIET = ("query is too old", "message is not modified", "message to edit not found",
             "message can't be deleted", "message to delete not found",
             "bot was blocked by the user", "user is deactivated",
             "chat not found", "MESSAGE_ID_INVALID")
    if any(q.lower() in text.lower() for q in QUIET):
        log.info("Пропущено (не критично): %s", text[:120])
        return True

    if isinstance(exc, TelegramRetryAfter):
        log.warning("Ліміт Telegram: чекаю %s с", exc.retry_after)
        await asyncio.sleep(exc.retry_after + 1)
        return True

    log.error("Помилка в хендлері: %s: %s", type(exc).__name__, exc, exc_info=exc)
    # спробувати чемно повідомити користувача, але не падати, якщо не вийде
    try:
        cb = getattr(upd, "callback_query", None)
        if cb is not None:
            await cb.answer("⚠️ Сталася помилка, спробуйте ще раз", show_alert=False)
        else:
            msg = getattr(upd, "message", None)
            if msg is not None and getattr(msg.chat, "type", "") == "private":
                await msg.answer("⚠️ Сталася технічна помилка. Спробуйте ще раз або натисніть /start")
    except Exception:
        pass
    return True     # помилка оброблена — polling продовжується


class HeartbeatMiddleware(BaseMiddleware):
    """Відмічає час кожного успішно отриманого апдейта (для watchdog)."""

    async def __call__(self, handler, event, data):
        global LAST_OK
        LAST_OK = time.monotonic()
        return await handler(event, data)


async def watchdog(bot: Bot) -> None:
    """Сторож усередині процесу.

    Якщо Telegram довго мовчить — робить контрольний getMe. Якщо і він не
    відповідає кілька разів поспіль, процес завершується з ненульовим кодом,
    і зовнішній перезапуск (run.sh / systemd) підіймає бота заново.
    """
    global LAST_OK
    fails = 0
    while True:
        await asyncio.sleep(WATCHDOG_EVERY)
        # ⚠️ саме `is None`, а не `or`: LAST_OK == 0 теж валідне значення
        base = LAST_OK if LAST_OK is not None else time.monotonic()
        silence = time.monotonic() - base
        if silence < WATCHDOG_SILENCE:
            continue
        try:
            await asyncio.wait_for(bot.get_me(), timeout=25)
            LAST_OK = time.monotonic()
            fails = 0
            log.debug("watchdog: звʼязок живий (тиша %.0f с)", silence)
        except Exception as e:
            fails += 1
            log.warning("watchdog: Telegram не відповідає (%s/%s): %s: %s",
                        fails, WATCHDOG_FAILS, type(e).__name__, e)
            if fails >= WATCHDOG_FAILS:
                log.error("watchdog: зʼєднання втрачено — перезапуск процесу")
                await _safe_close_db()
                os.environ["EUROTOUR_RESTART"] = "1"
                _relaunch()


async def _safe_close_db() -> None:
    """Гарантовано скидає всі дані на диск перед перезапуском."""
    with suppress(Exception):
        if db:
            await db.commit()
            await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            await db.close()
            log.info("БД збережено перед перезапуском.")


async def autobackup_loop() -> None:
    """Часто скидає дані на диск, раз на годину — повна копія.

    Кожні 60 с робиться checkpoint: усе, що встигли натиснути користувачі
    й наредагувати адмін, фізично лежить у файлі БД. Тому навіть раптове
    вбивство процесу (як на GitHub Actions) не з'їдає прогрес.
    """
    tick = 0
    while True:
        await asyncio.sleep(60)
        tick += 1
        with suppress(Exception):
            if not db:
                continue
            await db.commit()
            await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")   # ⬅ щохвилини
            if tick % 60 == 0:                                    # раз на годину
                dst = f"{DB_PATH}.bak{int(time.time()) % 3}"      # ротація 3 копій
                async with aiosqlite.connect(dst) as target:
                    await db.backup(target)
                log.debug("Автобекап БД → %s", dst)


async def scheduled_restart(hours: float) -> None:
    """Плановий перезапуск рівно раз на N годин.

    Профілактика витоків памʼяті та «підвисань» довгих зʼєднань.
    Тихо: жодних повідомлень користувачам чи адміну.
    БД не чіпається — усі дані лишаються на місці.
    """
    if hours <= 0:
        return
    await asyncio.sleep(hours * 3600)
    log.info("Плановий перезапуск (%s год). Дані збережено.", hours)
    await _safe_close_db()
    os.environ["EUROTOUR_RESTART"] = "1"
    _relaunch()


async def run_bot() -> None:
    """Один цикл життя бота: підняти, працювати, коректно закрити."""
    global LAST_OK, CONFLICTS
    CONFLICTS = 0
    session = make_session()
    bot = Bot(BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.update.outer_middleware(HeartbeatMiddleware())
    # Роутери — глобальні обʼєкти, а Dispatcher створюється заново при кожному
    # перепідключенні. aiogram забороняє чіпляти вже приєднаний роутер
    # ("Router is already attached"), тому спершу відвʼязуємо їх від старого.
    for _r in (adm_r, user_r):
        with suppress(Exception):
            if _r.parent_router is not None:
                old = _r.parent_router
                if _r in old.sub_routers:
                    old.sub_routers.remove(_r)
                _r._parent_router = None
    dp.include_router(adm_r)      # панель первым: перехватывает p:* и /panel
    dp.include_router(user_r)
    try:
        me = await asyncio.wait_for(bot.get_me(), timeout=30)
    except TelegramUnauthorizedError:
        with suppress(Exception):
            await session.close()
        raise Fatal("\n❌ Невірний BOT_TOKEN. Візьміть новий у @BotFather.\n")
    except BaseException:
        # ⬅ будь-який збій (найчастіше мережа): обовʼязково закрити сесію,
        # інакше кожна спроба лишає «Unclosed client session» і течуть сокети.
        with suppress(Exception):
            await session.close()
        raise
    LAST_OK = time.monotonic()
    NETOK.append(1)                 # сигнал main(): зʼєднання встановлено
    log.info("Бот @%s запущено. Owner=%s, БД=%s", me.username, OWNER_ID, DB_PATH)
    try:
        await bot.set_my_commands([BotCommand(command="start", description="Почати")])
        for a in await qa("SELECT id FROM admins"):
            try:
                await bot.set_my_commands(
                    [BotCommand(command="start", description="Почати"),
                     BotCommand(command="panel", description="Панель"),
                     BotCommand(command="myid", description="Мій ID")],
                    scope=BotCommandScopeChat(chat_id=a["id"]))
            except TelegramBadRequest:
                pass
    except Exception as e:
        log.warning("set_my_commands: %s", e)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception as e:
        log.warning("delete_webhook: %s", e)
    # ── Витіснення попередньої копії бота ──
    # Якщо десь ще живе стара копія на цьому ж токені, Telegram віддає Conflict.
    # Робимо кілька спроб перехопити канал getUpdates: нове з'єднання
    # витісняє старе, щойно в того завершиться довгий запит.
    for i in range(1, 7):
        try:
            await bot.get_updates(offset=-1, timeout=0, request_timeout=20)
            break
        except TelegramConflictError:
            if i == 1:
                log.warning("⚠️  Токен зайнятий іншою копією бота. "
                            "Перехоплюю канал (спроба %s з 6)…", i)
            else:
                log.warning("… ще одна спроба перехопити канал (%s з 6)", i)
            await asyncio.sleep(5)
        except Exception:
            break
    else:
        await session.close()
        raise Fatal(
            "\n╔════════════════════════════════════════════════════════════╗\n"
            "║  ⚠️  БОТ УЖЕ ЗАПУЩЕНИЙ В ІНШОМУ МІСЦІ                      ║\n"
            "╚════════════════════════════════════════════════════════════╝\n\n"
            "Один і той самий токен не можна використовувати двічі.\n\n"
            "Що зробити:\n"
            "  1. Зупиніть стару копію бота (на хостингу чи на компʼютері).\n"
            "  2. Зачекайте 10 секунд.\n"
            "  3. Запустіть знову: python3 s.py\n\n"
            "Якщо бот крутиться на хостингу — вимкніть його там,\n"
            "або запускайте лише в одному місці.\n")
    # aiogram сам «ковтає» Conflict і крутиться вічно — ловимо це через лог
    # і зупиняємо бота з нормальним поясненням замість нескінченних помилок.
    class _ConflictWatch(logging.Handler):
        def emit(self, rec: logging.LogRecord) -> None:
            global CONFLICTS
            msg = rec.getMessage()
            if "TelegramConflictError" in msg:
                CONFLICTS += 1
                if CONFLICTS == 3:
                    log.error("⚠️  Токен зайнятий іншою копією бота — зупиняюсь.")
                    with suppress(RuntimeError):
                        loop.call_soon_threadsafe(conflict_ev.set)
            elif "Update id=" in msg or "Start polling" in msg:
                CONFLICTS = 0                       # реально працюємо — скидаємо

    loop = asyncio.get_running_loop()
    conflict_ev = asyncio.Event()
    cwatch = _ConflictWatch()
    logging.getLogger("aiogram.dispatcher").addHandler(cwatch)

    guard = asyncio.create_task(watchdog(bot))
    timer = asyncio.create_task(scheduled_restart(RESTART_HOURS))
    saver = asyncio.create_task(autobackup_loop())
    try:
        poll = asyncio.create_task(dp.start_polling(
            bot,
            polling_timeout=30,
            handle_signals=False,          # сигналами керує main()
            close_bot_session=False,
            allowed_updates=["message", "callback_query"],
        ))
        clash = asyncio.create_task(conflict_ev.wait())
        done, _ = await asyncio.wait({poll, clash}, return_when=asyncio.FIRST_COMPLETED)
        if clash in done:                  # запущена друга копія бота
            with suppress(Exception):
                await dp.stop_polling()
            poll.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await poll
            raise Fatal(
                "\n╔════════════════════════════════════════════════════════════╗\n"
                "║  ⚠️  БОТ УЖЕ ЗАПУЩЕНИЙ В ІНШОМУ МІСЦІ                      ║\n"
                "╚════════════════════════════════════════════════════════════╝\n\n"
                "Один токен не можна використовувати двічі одночасно.\n\n"
                "Що зробити:\n"
                "  1. Зупиніть стару копію (на хостингу або на компʼютері).\n"
                "  2. Зачекайте 10 секунд.\n"
                "  3. Запустіть знову: python3 s.py\n")
        clash.cancel()
        with suppress(asyncio.CancelledError):
            await clash
        await poll                         # підніме виняток, якщо був
    finally:
        logging.getLogger("aiogram.dispatcher").removeHandler(cwatch)
        for t in (guard, timer, saver):
            t.cancel()
            with suppress(asyncio.CancelledError):
                await t
        with suppress(Exception):
            await session.close()


async def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit(
            "\n╔════════════════════════════════════════════════════════════╗\n"
            "║  ❌ ТОКЕН НЕ ВСТАВЛЕНО                                     ║\n"
            "╚════════════════════════════════════════════════════════════╝\n\n"
            "Відкрийте файл bot.py, знайдіть на початку рядок:\n\n"
            '    TOKEN = ""\n\n'
            "і вставте між лапками токен від @BotFather:\n\n"
            '    TOKEN = "8154302197:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"\n\n'
            "Потім збережіть файл і запустіть знову: python3 bot.py\n")

    await init_db()
    await load_states()          # відновити незавершені діалоги користувачів

    # На хостингу процес часто стартує раніше, ніж підніметься мережа.
    # Тихо чекаємо до 60 с, щоб не сипати помилками на старті.
    for i in range(12):
        try:
            import socket
            await asyncio.get_running_loop().getaddrinfo(
                "api.telegram.org", 443, family=socket.AF_INET)
            break
        except Exception:
            if i == 0:
                log.info("Чекаю на мережу…")
            await asyncio.sleep(5)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    runner = await start_health_server()
    attempt = 0
    netfail = 0               # поспіль невдалих спроб зʼєднання
    try:
        while not stop.is_set():
            attempt += 1
            try:
                NETOK.clear()
                worker = asyncio.create_task(run_bot())
                waiter = asyncio.create_task(stop.wait())
                done, _ = await asyncio.wait({worker, waiter},
                                             return_when=asyncio.FIRST_COMPLETED)
                if waiter in done:                       # прийшов Ctrl+C / SIGTERM
                    worker.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await worker
                    break
                waiter.cancel()
                with suppress(asyncio.CancelledError):
                    await waiter
                await worker                              # підніме виняток, якщо був
                log.info("Polling завершився штатно.")
                break
            except Fatal as e:               # друга копія / поганий токен
                FATAL.append(str(e))
                break
            except SystemExit as e:
                FATAL.append(str(e or ""))
                break
            except asyncio.CancelledError:
                break
            except TelegramConflictError:
                log.error("⚠️  Цей самий токен використовує інша копія бота. "
                          "Зупиніть її. Нова спроба через 15 с…")
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=15)
            except (TelegramNetworkError, TelegramServerError, ClientError,
                    asyncio.TimeoutError, OSError) as e:
                if NETOK:
                    netfail = 0        # цього разу бот таки піднявся
                netfail += 1
                delay = min(RESTART_DELAY * min(attempt, 6), 60)
                log.warning("🌐 Немає звʼязку з Telegram (%s). Спроба %s, повтор через %s с…",
                            type(e).__name__, netfail, delay)
                if netfail == 5:
                    log.error(
                        "\n─────────────────────────────────────────────\n"
                        "Бот 5 разів поспіль не зміг зʼєднатися з api.telegram.org.\n"
                        "Найчастіші причини:\n"
                        "  • хостинг має лише IPv6 → запустіть з IPV4=0\n"
                        "      IPV4=0 python3 s.py\n"
                        "  • хостинг блокує Telegram → підключіть проксі:\n"
                        "      PROXY=http://user:pass@host:port\n"
                        "  • немає інтернету або DNS на сервері\n"
                        "Бот продовжує спроби — щойно звʼязок зʼявиться, запрацює сам.\n"
                        "─────────────────────────────────────────────")
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=delay)
            except Exception as e:
                log.exception("⚠️  Збій (%s: %s). Бот сам перезапуститься через %s с. "
                              "Дані збережені.", type(e).__name__, e, RESTART_DELAY)
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=RESTART_DELAY)
    finally:
        log.info("Зупинка…")
        if runner:
            with suppress(Exception):
                await runner.cleanup()
        if db:
            with suppress(Exception):
                await db.commit()                              # дозаписати незбережене
                await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                await db.close()
                log.info("БД коректно закрито, дані збережено.")
        if FATAL:
            print(FATAL[0])


# ── самоперезапуск процесу (працює і на хостингу, і локально) ──
def _relaunch() -> None:
    """Замінює поточний процес новим тим самим ботом.

    Використовується після планового перезапуску (раз на 6 годин) та після
    аварії звʼязку. Не потребує зовнішнього сторожа — тому працює
    на будь-якому хостингу «з коробки».
    """
    log.info("Перезапуск процесу…")
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])


if __name__ == "__main__":
    # 43 — плановий перезапуск, 42 — втрата звʼязку (обидва лікуються перезапуском)
    if os.environ.pop("EUROTOUR_RESTART", "") == "1":
        log.info("Продовжую роботу після перезапуску. Дані на місці.")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Зупинено")
    except SystemExit as e:
        msg = str(e or "")
        if msg and msg not in ("0", "42", "43", "None"):
            print(msg)                      # інструкція користувачу (токен / друга копія)
        else:
            print("\n👋 Зупинено")
    except Exception as e:                  # нічого не має падати «мовчки»
        print(f"\n❌ Помилка запуску: {type(e).__name__}: {e}\n")
        import traceback
        traceback.print_exc()
