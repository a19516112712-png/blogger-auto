#!/usr/bin/env python3
"""Agnes AI connectivity diagnostic script."""
import os
import sys
import time
import traceback

from openai import OpenAI

API_KEY = os.getenv("AGNES_API_KEY", "sk-test-dummy-key")
BASE_URL = "https://apihub.agnes-ai.com/v1"
MODEL = os.getenv("AGNES_MODEL", "gpt-4o-mini")

print("=" * 60)
print("Agnes AI Connectivity Diagnostic")
print("=" * 60)
print(f"API_KEY exists: {bool(os.getenv('AGNES_API_KEY'))}")
print(f"API_KEY length:  {len(API_KEY)} chars")
print(f"BASE_URL:        {BASE_URL}")
print(f"MODEL:           {MODEL}")
print()

# --- Step 1: DNS resolution ---
print("--- Step 1: DNS resolution ---")
import socket
host = "apihub.agnes-ai.com"
try:
    ip = socket.gethostbyname(host)
    print(f"✅ DNS resolved: {host} → {ip}")
except socket.gaierror as e:
    print(f"❌ DNS FAILED: {host} — {e}")
    print()
    print("ROOT CAUSE: Domain 'apihub.agnes-ai.com' does not exist.")
    print("The OpenAI client cannot connect because the hostname doesn't resolve.")
    sys.exit(1)

# --- Step 2: TCP connectivity ---
print()
print("--- Step 2: TCP connectivity (port 443) ---")
import ssl
try:
    sock = socket.create_connection((host, 443), timeout=10)
    ctx = ssl.create_default_context()
    ssock = ctx.wrap_socket(sock, server_hostname=host)
    print(f"✅ TLS handshake OK: {ssock.version()}")
    ssock.close()
except Exception as e:
    print(f"❌ TLS FAILED: {e}")
    # Continue anyway — the OpenAI client may handle retries

# --- Step 3: OpenAI client init ---
print()
print("--- Step 3: OpenAI client initialization ---")
try:
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    print(f"✅ Client created")
    print(f"   client.base_url: {client.base_url}")
except Exception as e:
    print(f"❌ Client init FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

# --- Step 4: API call ---
print()
print("--- Step 4: chat.completions.create ---")
start = time.time()
try:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "Say hello in one short sentence."}],
        max_tokens=50,
        timeout=30,
    )
    elapsed = (time.time() - start) * 1000
    print(f"✅ API call succeeded ({elapsed:.0f}ms)")
    print(f"   Response: {response.choices[0].message.content}")
    print(f"   Model used: {response.model}")
    print(f"   Usage: {response.usage}")
except Exception as e:
    elapsed = (time.time() - start) * 1000
    print(f"❌ API call FAILED ({elapsed:.0f}ms)")
    print(f"   Exception type: {type(e).__name__}")
    print(f"   Exception args: {e.args}")
    print()
    print("   Full traceback:")
    traceback.print_exc()
    
    # Try to extract HTTP status
    if hasattr(e, 'response'):
        print(f"\n   HTTP response: {e.response}")
    if hasattr(e, 'status_code'):
        print(f"   HTTP status_code: {e.status_code}")
    if hasattr(e, 'body'):
        print(f"   Response body: {e.body}")

print()
print("=" * 60)
