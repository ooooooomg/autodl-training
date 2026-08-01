"""Send a WeChat push notification via wxpusher.

Usage:
    python wxpush.py "message title" "message content"
    python wxpush.py check          # verify credentials by sending a test message

Config: edit WXPUSHER_TOKEN and WXPUSHER_UID below (or set via env vars).
Get credentials at https://wxpusher.zjiecode.com/ (register, then appToken + uid).
"""
import json
import os
import sys
import urllib.request

# Fill these in (or set env WXPUSHER_TOKEN / WXPUSHER_UID):
WXPUSHER_TOKEN = os.environ.get("WXPUSHER_TOKEN", "")
WXPUSHER_UID = os.environ.get("WXPUSHER_UID", "")

API = "https://wxpusher.zjiecode.com/api/send/message"


def send(title, content):
    if not WXPUSHER_TOKEN or not WXPUSHER_UID:
        print("ERROR: WXPUSHER_TOKEN / WXPUSHER_UID not set", file=sys.stderr)
        return 2
    payload = {
        "appToken": WXPUSHER_TOKEN,
        "content": f"<h3>{title}</h3><p>{content}</p>",
        "contentType": 2,
        "uids": [WXPUSHER_UID],
    }
    req = urllib.request.Request(
        API, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
        print(body)
        return 0
    except Exception as e:
        print(f"ERROR sending: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "check":
        sys.exit(send("推送测试", "这是一条测试消息，来自训练进度监控。"))
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    title = sys.argv[1]
    content = sys.argv[2]
    sys.exit(send(title, content))
