#!/usr/bin/env python3
"""Перевірка ключів AI-провайдерів. Запуск:
   GROQ_KEY=gsk_... GEMINI_KEY=AIza... OPENROUTER_KEY=sk-or-... python3 check_keys.py
"""
import json, os, urllib.request, urllib.error

P = [("Groq", os.getenv("GROQ_KEY", ""),
      "https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-20b"),
     ("Gemini", os.getenv("GEMINI_KEY", ""),
      "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
      "gemini-3.5-flash"),
     ("OpenRouter", os.getenv("OPENROUTER_KEY", ""),
      "https://openrouter.ai/api/v1/chat/completions",
      "inclusionai/ling-3.0-flash-vl:free")]

for name, key, url, model in P:
    if not key:
        print(f"{name:<12} — ключа немає (пропускаю)")
        continue
    body = json.dumps({"model": model,
                       "messages": [{"role": "user", "content": "Скажи одне слово: працює"}],
                       "max_tokens": 200}).encode()
    hdr = {"Authorization": "Bearer " + key, "Content-Type": "application/json",
           "User-Agent": "Mozilla/5.0"}
    try:
        r = urllib.request.urlopen(
            urllib.request.Request(url, data=body, headers=hdr), timeout=60)
        m = json.load(r)["choices"][0]["message"]
        txt = ((m.get("content") or m.get("reasoning") or "").strip())[:40]
        print(f"{name:<12} ✅ працює → {txt!r}")
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:150]
        print(f"{name:<12} ❌ HTTP {e.code}: {msg}")
    except Exception as e:
        print(f"{name:<12} ❌ {type(e).__name__}: {e}")
