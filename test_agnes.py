#!/usr/bin/env python3
"""Agnes AI connectivity diagnostic — tests both supported models."""
import os
import sys
import time
import traceback

from openai import OpenAI

API_KEY = os.getenv("AGNES_API_KEY", "sk-test-dummy-key")
BASE_URL = "https://apihub.agnes-ai.com/v1"

MODELS_TO_TEST = [
    os.getenv("AGNES_MODEL", "Agnes 2.0 Flash"),
    "Agnes 2.0 Flash",
    "Agnes 1.5 Flash",
]

print("=" * 60)
print("Agnes AI Connectivity Diagnostic")
print("=" * 60)
print(f"API_KEY exists: {bool(os.getenv('AGNES_API_KEY'))}")
print(f"BASE_URL:        {BASE_URL}")
print()

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

found = False
for model in MODELS_TO_TEST:
    print(f"--- Testing model: {model} ---")
    start = time.time()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say hello in one short sentence."}],
            max_tokens=50,
            timeout=30,
        )
        elapsed = (time.time() - start) * 1000
        print(f"✅ SUCCESS ({elapsed:.0f}ms)")
        print(f"   Response: {response.choices[0].message.content}")
        print(f"   Model used: {response.model}")
        print(f"   Usage: {response.usage}")
        found = True
        break
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        status = getattr(e, 'status_code', '?')
        body = getattr(e, 'body', str(e)[:200]) if hasattr(e, 'body') else str(e)[:200]
        print(f"❌ FAILED ({elapsed:.0f}ms) — HTTP {status}: {body}")

print()
if found:
    print("=" * 60)
    print(f"✅ Connection OK — using model: {model}")
else:
    print("=" * 60)
    print("❌ All models failed")
    sys.exit(1)
