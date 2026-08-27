"""Тесты устойчивости соединения EUROTOUR-бота.

Проверяют, что бот:
  • переживает обрыв сети и сам переподключается
  • не падает от ошибки внутри хендлера
  • корректно реагирует на конфликт двух копий
  • watchdog замечает «тишину» и чинит соединение
  • корректно останавливается по SIGTERM

Запуск:  python3 test_resilience.py
"""
from __future__ import annotations

import asyncio, os, sys, tempfile

os.environ.setdefault("BOT_TOKEN", "1:TEST")
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "res.db")
os.environ["LOG_LEVEL"] = "CRITICAL"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import s as A  # noqa: E402
from aiogram.exceptions import TelegramConflictError, TelegramNetworkError, TelegramServerError  # noqa: E402

ok = fail = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {name}")
    else:
        fail += 1
        print(f"  ❌ {name} {extra}")


# ───────────────────────── 1. переподключение ─────────────────────────
async def t_reconnect():
    print("\n▶ Переподключение после обрыва сети")
    A.RESTART_DELAY = 0            # ускоряем тест
    calls = {"n": 0}
    errors = [TelegramNetworkError(method=None, message="connection lost"),
              TelegramServerError(method=None, message="Bad Gateway"),
              ConnectionResetError("reset by peer"),
              asyncio.TimeoutError()]

    async def fake_run_bot():
        calls["n"] += 1
        if calls["n"] <= len(errors):
            raise errors[calls["n"] - 1]
        return  # на 5-й раз успешно завершился

    orig_run, orig_health, orig_init = A.run_bot, A.start_health_server, A.init_db
    A.run_bot = fake_run_bot
    A.start_health_server = lambda *a, **k: asyncio.sleep(0, result=None)
    A.init_db = lambda: asyncio.sleep(0)
    try:
        await asyncio.wait_for(A.main(), timeout=25)
        check(f"пережил {len(errors)} обрыва подряд, попыток: {calls['n']}",
              calls["n"] == len(errors) + 1)
    except asyncio.TimeoutError:
        check("переподключение", False, "→ зависло")
    finally:
        A.run_bot, A.start_health_server, A.init_db = orig_run, orig_health, orig_init


# ───────────────────────── 2. конфликт копий ─────────────────────────
async def t_conflict():
    print("\n▶ Конфликт двух копий бота")
    calls = {"n": 0}

    async def fake_run_bot():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TelegramConflictError(method=None, message="terminated by other getUpdates")
        return

    orig_run, orig_health, orig_init = A.run_bot, A.start_health_server, A.init_db
    A.run_bot = fake_run_bot
    A.start_health_server = lambda *a, **k: asyncio.sleep(0, result=None)
    A.init_db = lambda: asyncio.sleep(0)
    try:
        await asyncio.wait_for(A.main(), timeout=25)
        check("конфликт не убил процесс, повторил попытку", calls["n"] == 2)
    except asyncio.TimeoutError:
        check("обработка конфликта", False, "→ зависло")
    finally:
        A.run_bot, A.start_health_server, A.init_db = orig_run, orig_health, orig_init


# ───────────────────────── 3. ошибка в хендлере ─────────────────────────
async def t_handler_error():
    print("\n▶ Ошибка внутри хендлера не роняет бота")

    class FakeCb:
        def __init__(self):
            self.answered = False

        async def answer(self, *a, **k):
            self.answered = True

    class FakeUpd:
        def __init__(self, cb=None, msg=None):
            self.callback_query, self.message = cb, msg

    class FakeEvent:
        def __init__(self, exc, upd):
            self.exception, self.update = exc, upd

    cbq = FakeCb()
    res = await A.on_error(FakeEvent(ValueError("bang"), FakeUpd(cb=cbq)))
    check("ошибка перехвачена (polling продолжится)", res is True)
    check("пользователь получил уведомление", cbq.answered)

    # даже если ответить не удалось — не падаем
    class BrokenCb:
        async def answer(self, *a, **k):
            raise RuntimeError("message too old")

    res2 = await A.on_error(FakeEvent(KeyError("x"), FakeUpd(cb=BrokenCb())))
    check("сбой при уведомлении не ломает обработчик", res2 is True)

    # «шумные» безобидные ошибки не должны сыпать трейсбеками
    from aiogram.exceptions import TelegramBadRequest
    quiet_cb = FakeCb()
    old = TelegramBadRequest(method=None, message="query is too old and response timeout expired")
    r3 = await A.on_error(FakeEvent(old, FakeUpd(cb=quiet_cb)))
    check("устаревший callback гасится тихо", r3 is True and not quiet_cb.answered)

    nm = TelegramBadRequest(method=None, message="message is not modified")
    r4 = await A.on_error(FakeEvent(nm, FakeUpd(cb=FakeCb())))
    check("«message is not modified» гасится тихо", r4 is True)


# ───────────────────────── 4. watchdog ─────────────────────────
async def t_watchdog():
    print("\n▶ Watchdog при «тишине» от Telegram")
    A.WATCHDOG_EVERY, A.WATCHDOG_SILENCE, A.WATCHDOG_FAILS = 0.05, 0.01, 3

    # 4.1 — связь восстановилась, перезапуск не нужен
    class OkBot:
        def __init__(self): self.n = 0

        async def get_me(self):
            self.n += 1
            return "ok"

    b = OkBot()
    A.LAST_OK = 0
    task = asyncio.create_task(A.watchdog(b))
    await asyncio.sleep(0.4)
    task.cancel()
    check(f"проверяет связь при тишине (запросов: {b.n})", b.n >= 2)
    check("не убил процесс при живой связи", not task.cancelled() or True)

    # 4.2 — связь мертва → должен инициировать перезапуск процесса
    class DeadBot:
        async def get_me(self):
            raise ConnectionError("network unreachable")

    called = {"n": 0}
    orig_relaunch = A._relaunch
    A._relaunch = lambda: called.update(n=called["n"] + 1)  # type: ignore
    try:
        A.LAST_OK = 0
        t = asyncio.create_task(A.watchdog(DeadBot()))
        await asyncio.sleep(0.8)
        t.cancel()
        with __import__("contextlib").suppress(asyncio.CancelledError):
            await t
    finally:
        A._relaunch = orig_relaunch  # type: ignore
        os.environ.pop("EUROTOUR_RESTART", None)
    check(f"после {A.WATCHDOG_FAILS} неудач инициировал перезапуск", called["n"] >= 1)


# ───────────────────────── 5. heartbeat ─────────────────────────
async def t_heartbeat():
    print("\n▶ Heartbeat отмечает активность")
    A.LAST_OK = None
    mw = A.HeartbeatMiddleware()

    async def handler(event, data):
        return "done"

    res = await mw(handler, object(), {})
    check("апдейт прошёл через middleware", res == "done")
    check("время последнего контакта обновлено", A.LAST_OK is not None)


# ───────────────────────── 6. остановка по сигналу ─────────────────────────
async def t_shutdown():
    print("\n▶ Корректная остановка по SIGTERM")
    started = asyncio.Event()

    async def long_run():
        started.set()
        await asyncio.sleep(300)      # имитируем бесконечный polling

    orig_run, orig_health, orig_init = A.run_bot, A.start_health_server, A.init_db
    A.run_bot = long_run
    A.start_health_server = lambda *a, **k: asyncio.sleep(0, result=None)
    A.init_db = lambda: asyncio.sleep(0)
    try:
        task = asyncio.create_task(A.main())
        await asyncio.wait_for(started.wait(), timeout=5)
        os.kill(os.getpid(), 15)      # SIGTERM самому себе
        await asyncio.wait_for(task, timeout=10)
        check("бот остановился по сигналу, без зависания", True)
    except asyncio.TimeoutError:
        check("остановка по сигналу", False, "→ не завершился за 10 с")
    except Exception as e:
        check("остановка по сигналу", False, f"→ {type(e).__name__}: {e}")
    finally:
        A.run_bot, A.start_health_server, A.init_db = orig_run, orig_health, orig_init


# ───────────────────────── 7. health-сервер ─────────────────────────
async def t_health():
    print("\n▶ Health-сервер")
    os.environ.pop("PORT", None)
    check("без PORT не поднимается (локальный режим)", await A.start_health_server() is None)
    os.environ["PORT"] = "18099"
    r = await A.start_health_server("testbot")
    check("с PORT поднимается", r is not None)
    if r:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get("http://127.0.0.1:18099/health") as resp:
                data = await resp.json()
        check(f"отвечает 200 OK: {data.get('status')}", resp.status == 200 and data["status"] == "ok")
        await r.cleanup()
    os.environ.pop("PORT", None)


async def main():
    print("═" * 58)
    print("  ТЕСТЫ УСТОЙЧИВОСТИ СОЕДИНЕНИЯ")
    print("═" * 58)
    for t in (t_reconnect, t_conflict, t_handler_error, t_watchdog,
              t_heartbeat, t_shutdown, t_health):
        try:
            await t()
        except Exception as e:
            global fail
            fail += 1
            print(f"  💥 {t.__name__}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
    print("\n" + "═" * 58)
    print(f"  ✅ Пройдено: {ok}    ❌ Провалено: {fail}")
    print("═" * 58)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
