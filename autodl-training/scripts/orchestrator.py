"""训练编排器：等待上传完成 -> 自动启动训练 -> 自动启动监控。

把"数据/权重上传 -> 启动训练 -> 每小时监控推送"串成一条自动流水线。

典型用法（本地运行，保持本机开机直到训练启动）：
    python orchestrator.py                     # 全流程自动

工作方式：
  1. 轮询服务器，直到教师权重完整 + 所有数据 shard 就绪（断点续传友好）
  2. 两者就绪后自动执行 start_train.sh（nohup 后台启动训练）
  3. 训练启动 30 秒后启动服务器端 monitor_server.py（nohup 常驻）
  4. 之后即使本机关机，训练和监控都独立运行

⚠️ 配置：先设置环境变量或改下方配置区；start_train.sh 中的训练命令需先按项目改好。
"""
import os
import subprocess
import sys
import time

import paramiko

# ===================== 配置区（修改这里） =====================
HOST = os.environ.get("SSH_HOST", "YOUR_SERVER_HOST")
PORT = int(os.environ.get("SSH_PORT", "22"))
USER = os.environ.get("SSH_USER", "root")
PASSWORD = os.environ.get("SSH_PASSWORD", "YOUR_PASSWORD")
REMOTE = "/root/autodl-tmp/PROJ"          # 服务器工作目录
TEACHER_PATH = f"{REMOTE}/weights/teacher.pth"   # 教师权重路径
TEACHER_SIZE = 0                            # 教师权重预期字节数（填 0 则只检查存在）
DATA_DIR = f"{REMOTE}/DATA"                 # 服务器数据目录
DATA_GLOB = "sa_*"                          # 数据分片目录 glob 模式（按实际数据命名修改）
TARGET_SHARDS = 0                           # 数据 shard 总数（按实际填，填 0 表示跳过数据检查）
TARGET_IMAGES = 0                           # 每个 shard 预期文件数（按实际填）

WXPUSHER_TOKEN = os.environ.get("WXPUSHER_TOKEN", "")
WXPUSHER_UID = os.environ.get("WXPUSHER_UID", "")
# ==============================================================


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD,
              timeout=20, banner_timeout=30, auth_timeout=30)
    return c


def remote(c, cmd, timeout=30):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def push(title, content):
    if not WXPUSHER_TOKEN or not WXPUSHER_UID:
        print(f"[push-skip] {title}: {content[:100]}", flush=True)
        return
    import urllib.request
    import json
    payload = {
        "appToken": WXPUSHER_TOKEN,
        "content": f"<h3>{title}</h3><pre style='white-space:pre-wrap'>{content}</pre>",
        "contentType": 2,
        "uids": [WXPUSHER_UID],
    }
    req = urllib.request.Request(
        "https://wxpusher.zjiecode.com/api/send/message",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        print(f"[push] {title}", flush=True)
    except Exception as e:
        print(f"[push-error] {e}", flush=True)


def check_teacher_ready(c):
    """教师权重是否完整（存在且大小达标）。"""
    rc, out, _ = remote(c, f'stat -c %s {TEACHER_PATH} 2>/dev/null || echo 0')
    try:
        size = int(out.strip())
    except ValueError:
        size = 0
    if TEACHER_SIZE > 0:
        return size >= TEACHER_SIZE
    return size > 0


def check_data_status(c):
    """返回 (就绪 shard 数, 缺失列表)。"""
    rc, out, _ = remote(c, f'for d in {DATA_DIR}/{DATA_GLOB}; do n=$(ls $d 2>/dev/null | wc -l); echo "$(basename $d):$n"; done')
    ready, missing = [], []
    for line in out.strip().splitlines():
        if not line.strip():
            continue
        try:
            name, n = line.split(":")
            n = int(n)
        except ValueError:
            continue
        if n >= TARGET_IMAGES:
            ready.append(name)
        else:
            missing.append(f"{name}({n})")
    return len(ready), missing


def wait_for_uploads(c):
    """轮询直到教师权重 + 所有 shard 就绪。"""
    push("训练编排器启动", "正在等待数据/权重传输完成，完成后将自动启动训练。")
    while True:
        teacher_ok = check_teacher_ready(c)
        n_ready, missing = check_data_status(c)
        print(f"[wait] teacher={'OK' if teacher_ok else '...'} "
              f"data={n_ready}/{TARGET_SHARDS}", flush=True)
        if teacher_ok and n_ready >= TARGET_SHARDS:
            push("传输完成，即将启动训练",
                 f"教师权重 ✓ 数据 {TARGET_SHARDS} shards ✓")
            return True
        time.sleep(300)  # 5 分钟检查一次


def start_training(c):
    rc, out, err = remote(c, f'cd {REMOTE} && bash start_train.sh', timeout=60)
    print(f"[start] rc={rc} out={out} err={err}", flush=True)
    return rc == 0


def start_server_monitor(c):
    rc, out, err = remote(c,
        f'cd {REMOTE} && nohup /root/miniconda3/bin/python monitor_server.py '
        f'> monitor_server.out 2>&1 & echo STARTED', timeout=30)
    return "STARTED" in out


def main():
    if "YOUR_" in PASSWORD or "YOUR_" in HOST:
        print("ERROR: 未配置 SSH 凭据。设置 SSH_HOST/SSH_PORT/SSH_USER/SSH_PASSWORD "
              "环境变量，或改脚本配置区。", file=sys.stderr)
        sys.exit(1)

    push("训练编排器启动", "自动协调流程已启动。")
    c = connect()
    ok = wait_for_uploads(c)
    if not ok:
        push("传输失败", "数据/权重传输未在预期时间完成。")
        return
    started = start_training(c)
    if started:
        push("训练已启动", "完整训练已在服务器启动。")
        time.sleep(30)
        if start_server_monitor(c):
            print("[monitor] 服务器监控已启动", flush=True)
        else:
            push("监控启动异常", "训练已启动，但服务器监控进程启动失败。")
    else:
        push("训练启动失败", "start_train.sh 执行失败，请检查服务器。")
    c.close()


if __name__ == "__main__":
    main()
