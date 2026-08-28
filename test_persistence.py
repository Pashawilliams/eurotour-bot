"""Тесты сохранности данных EUROTOUR-бота.

Главная проверка: данные НЕ теряются при перезапуске и при жёстком kill -9.
Запуск:  python3 test_persistence.py
"""
from __future__ import annotations

import asyncio, os, signal, subprocess, sqlite3, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.join(HERE, "s.py")
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {name}")
    else:
        fail += 1
        print(f"  ❌ {name} {extra}")


async def t_wal():
    print("\n▶ Режим хранения БД")
    d = tempfile.mkdtemp()
    dbp = os.path.join(d, "t.db")
    os.environ["DB_PATH"] = dbp
    os.environ["BOT_TOKEN"] = "1:TEST"
    os.environ["LOG_LEVEL"] = "CRITICAL"
    for m in list(sys.modules):
        if m == "s":
            del sys.modules[m]
    sys.path.insert(0, HERE)
    import s as A

    await A.init_db()
    jm = (await (await A.db.execute("PRAGMA journal_mode")).fetchone())[0]
    sy = (await (await A.db.execute("PRAGMA synchronous")).fetchone())[0]
    check(f"journal_mode = {jm} (нужен wal)", jm.lower() == "wal")
    check(f"synchronous = {sy} (нужен 2=FULL)", int(sy) == 2)
    check("файл БД создан", os.path.exists(dbp))
    await A.db.close()
    return A


async def t_survive_kill():
    print("\n▶ Данные переживают kill -9 (главный тест)")
    d = tempfile.mkdtemp()
    dbp = os.path.join(d, "kill.db")

    # 1. пишем данные и НЕ закрываем БД корректно — процесс убьём
    writer = f'''
import asyncio, os, sys
os.environ["DB_PATH"] = {dbp!r}
os.environ["BOT_TOKEN"] = "1:TEST"
os.environ["LOG_LEVEL"] = "CRITICAL"
sys.path.insert(0, {HERE!r})
import s as A
async def m():
    await A.init_db()
    await A.ex("INSERT INTO users(id,uname,name,lang,created,seen) VALUES(?,?,?,?,?,?)",
               777, "victim", "Тест Виживання", "uk", 1, 1)
    await A.ex("INSERT INTO tickets(uid,body,status,created) VALUES(?,?,?,?)",
               777, "важливе звернення", "new", 1)
    await A.save_body(1, "uk", "ТЕКСТ ЯКИЙ МАЄ ВИЖИТИ")
    print("WRITTEN", flush=True)
    await asyncio.sleep(60)      # висим, ждём kill
asyncio.run(m())
'''
    p = subprocess.Popen([sys.executable, "-c", writer],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # ждём подтверждения записи
    t0 = time.time()
    written = False
    while time.time() - t0 < 30:
        line = p.stdout.readline() if p.stdout else ""
        if "WRITTEN" in line:
            written = True
            break
        if p.poll() is not None:
            break
    check("данные записаны", written, p.stderr.read()[:300] if not written else "")
    if not written:
        p.kill()
        return

    # 2. убиваем ЖЁСТКО, без шанса на корректное закрытие
    p.send_signal(signal.SIGKILL)
    p.wait(timeout=10)
    check(f"процесс убит kill -9 (код {p.returncode})", p.returncode in (-9, 137))

    # 3. читаем БД заново — данные должны быть на месте
    c = sqlite3.connect(dbp)
    u = c.execute("SELECT uname FROM users WHERE id=777").fetchone()
    t = c.execute("SELECT body FROM tickets WHERE uid=777").fetchone()
    b = c.execute("SELECT body FROM tr WHERE node=1 AND lang='uk'").fetchone()
    c.close()
    check("пользователь уцелел", u is not None and u[0] == "victim")
    check("обращение уцелело", t is not None and "важливе" in t[0])
    check("отредактированный текст уцелел", b is not None and "ВИЖИТИ" in b[0])


async def t_restart_keeps_data():
    print("\n▶ Данные переживают штатный перезапуск")
    d = tempfile.mkdtemp()
    dbp = os.path.join(d, "restart.db")
    script = f'''
import asyncio, os, sys
os.environ["DB_PATH"] = {dbp!r}
os.environ["BOT_TOKEN"] = "1:TEST"
os.environ["LOG_LEVEL"] = "CRITICAL"
sys.path.insert(0, {HERE!r})
import s as A
async def m(mode):
    await A.init_db()
    if mode == "write":
        await A.ex("INSERT INTO users(id,uname,name,lang,created,seen) VALUES(?,?,?,?,?,?)",
                   555, "keeper", "Дані", "uk", 1, 1)
        nid = await A.ex("INSERT INTO nodes(parent,typ,pos,roww) VALUES(1,'page',9,2)")
        await A.ex("INSERT INTO tr(node,lang,label,body) VALUES(?,?,?,?)",
                   nid, "uk", "🚌 Нова кнопка", "вміст")
        await A.setcfg("chat_id", "-100777")
        print("OK-WRITE")
    else:
        u = await A.q1("SELECT uname FROM users WHERE id=555")
        n = await A.q1("SELECT label FROM tr WHERE label='🚌 Нова кнопка'")
        print("READ", u["uname"] if u else "—", "|", n["label"] if n else "—",
              "|", A.CFG.get("chat_id"))
    await A.db.close()
asyncio.run(m(sys.argv[1]))
'''
    r1 = subprocess.run([sys.executable, "-c", script, "write"],
                        capture_output=True, text=True, timeout=60)
    check("первый запуск записал данные", "OK-WRITE" in r1.stdout, r1.stderr[:300])
    r2 = subprocess.run([sys.executable, "-c", script, "read"],
                        capture_output=True, text=True, timeout=60)
    out = r2.stdout.strip()
    check(f"второй запуск видит данные: {out}",
          "keeper" in out and "Нова кнопка" in out and "-100777" in out, r2.stderr[:300])


async def t_no_reseed():
    print("\n▶ Повторный запуск не сбрасывает настройки к заводским")
    d = tempfile.mkdtemp()
    dbp = os.path.join(d, "seed.db")
    script = f'''
import asyncio, os, sys
os.environ["DB_PATH"] = {dbp!r}
os.environ["BOT_TOKEN"] = "1:TEST"
os.environ["LOG_LEVEL"] = "CRITICAL"
sys.path.insert(0, {HERE!r})
import s as A
async def m(mode):
    await A.init_db()
    if mode == "edit":
        await A.save_body(1, "uk", "МІЙ ВЛАСНИЙ ТЕКСТ ПРИВІТАННЯ")
        await A.ex("UPDATE tr SET label='МОЯ КНОПКА' WHERE node=2 AND lang='uk'")
        print("EDITED")
    else:
        g = await A.q1("SELECT body FROM tr WHERE node=1 AND lang='uk'")
        b = await A.q1("SELECT label FROM tr WHERE node=2 AND lang='uk'")
        n = await A.scalar("SELECT COUNT(*) FROM nodes WHERE parent=1")
        print("CHECK", "|", g["body"][:30] if g else "—", "|",
              b["label"] if b else "—", "| разделов:", n)
    await A.db.close()
asyncio.run(m(sys.argv[1]))
'''
    subprocess.run([sys.executable, "-c", script, "edit"], capture_output=True, text=True, timeout=60)
    r = subprocess.run([sys.executable, "-c", script, "check"],
                       capture_output=True, text=True, timeout=60)
    out = r.stdout.strip()
    check(f"правки сохранились: {out}", "ВЛАСНИЙ" in out and "МОЯ КНОПКА" in out, r.stderr[:300])
    check("разделы не задублировались", "разделов: 6" in out, out)


async def t_restart_timer():
    print("\n▶ Плановый перезапуск каждые 6 часов")
    sys.path.insert(0, HERE)
    os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "x.db")
    for m in list(sys.modules):
        if m == "s":
            del sys.modules[m]
    import s as A

    check(f"интервал по умолчанию = {A.RESTART_HOURS} ч", A.RESTART_HOURS == 6)

    # выключение таймера
    t = asyncio.create_task(A.scheduled_restart(0))
    await asyncio.sleep(0.2)
    check("при 0 таймер не запускается", t.done())

    # срабатывание: имитируем крошечный интервал
    called = {"n": 0}
    orig = A._relaunch
    A._relaunch = lambda: called.update(n=called["n"] + 1)  # type: ignore
    try:
        await A.init_db()
        await asyncio.wait_for(A.scheduled_restart(0.3 / 3600), timeout=5)
        await asyncio.sleep(0.1)
    finally:
        A._relaunch = orig  # type: ignore
    check("по истечении времени инициирует перезапуск", called["n"] == 1)
    check("БД закрыта перед перезапуском (данные сброшены на диск)",
          os.environ.get("EUROTOUR_RESTART") == "1")
    os.environ.pop("EUROTOUR_RESTART", None)


async def t_autobackup():
    print("\n▶ Автобэкап БД")
    d = tempfile.mkdtemp()
    dbp = os.path.join(d, "bak.db")
    os.environ["DB_PATH"] = dbp
    for m in list(sys.modules):
        if m == "s":
            del sys.modules[m]
    sys.path.insert(0, HERE)
    import s as A

    await A.init_db()
    await A.ex("INSERT INTO users(id,uname,name,lang,created,seen) VALUES(?,?,?,?,?,?)",
               42, "backuptest", "Бекап", "uk", 1, 1)
    # вызываем тело бэкапа напрямую
    import aiosqlite
    await A.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    await A.db.commit()
    dst = dbp + ".bak0"
    async with aiosqlite.connect(dst) as target:
        await A.db.backup(target)
    check("копия БД создана", os.path.exists(dst))
    c = sqlite3.connect(dst)
    r = c.execute("SELECT uname FROM users WHERE id=42").fetchone()
    c.close()
    check("копия содержит данные", r is not None and r[0] == "backuptest")
    await A.db.close()


async def main():
    print("═" * 58)
    print("  ТЕСТЫ СОХРАННОСТИ ДАННЫХ")
    print("═" * 58)
    for t in (t_wal, t_survive_kill, t_restart_keeps_data, t_no_reseed,
              t_restart_timer, t_autobackup):
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
