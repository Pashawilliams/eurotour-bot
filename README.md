# EUROTOUR — Telegram support bot

Багатомовний (UA / RU / PL / EN) бот підтримки: розділи з інформацією,
контакти, звернення до менеджера та прихована адмін-панель із конструктором
кнопок і сторінок — усе редагується прямо в Telegram, без програміста.

Увесь бот — **один файл `s.py`**.

---

## Запуск на GitHub Actions

1. Токен уже збережено в **Settings → Secrets and variables → Actions**:

   | Секрет | Що це |
   |---|---|
   | `BOT_TOKEN` | токен від [@BotFather](https://t.me/BotFather) |
   | `OWNER_ID`  | Telegram ID власника |

   Значення секретів не видно нікому — навіть в логах вони замінюються на `***`.

2. **Actions → EUROTOUR bot → Run workflow**

---

## Запуск на своєму сервері (рекомендовано)

```bash
python3 s.py
```

Бібліотеки бот встановить сам при першому запуску.
Токен — у змінній `BOT_TOKEN` або в рядку `TOKEN` на початку файлу.

### Змінні оточення

| Змінна | Призначення |
|---|---|
| `BOT_TOKEN` | токен бота |
| `OWNER_ID` | Telegram ID власника |
| `DB_PATH` | шлях до бази, напр. `/data/eurotour.db` |
| `RESTART_HOURS` | самоперезапуск, годин (`0` — вимкнути) |
| `PROXY` | `http://user:pass@host:port`, якщо Telegram заблоковано |
| `IPV4` | `0` — не форсувати IPv4 (для IPv6-хостингів) |

### systemd

```ini
[Unit]
Description=EUROTOUR bot
After=network-online.target

[Service]
WorkingDirectory=/opt/eurotour
Environment=BOT_TOKEN=xxx
Environment=DB_PATH=/opt/eurotour/eurotour.db
ExecStart=/usr/bin/python3 /opt/eurotour/s.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## Перша настройка

**⚙️ Панель → ⚙️ Налаштування → 📥 Змінити чат** — переслати повідомлення
з групи, куди мають падати звернення. Поки чат не задано, вони йдуть
власнику в особисті.

## Тести

```bash
python test_bot.py          # 150 тестів функціоналу
python test_resilience.py   #  16 тестів стійкості
python test_persistence.py  #  18 тестів збереження даних
```
