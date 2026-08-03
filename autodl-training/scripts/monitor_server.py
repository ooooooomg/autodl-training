"""服务器端训练监控：每小时检查 + wxpusher 微信推送（中文）。

部署到服务器，用 nohup 常驻运行，本机离线也能继续推送。

用法：
    nohup /root/miniconda3/bin/python monitor_server.py > monitor_server.out 2>&1 &

推送内容：GPU占用率 / 当前训练内容 / 训练进度与状态 / 异常检测。
"""
import json
import os
import re
import subprocess
import time
import urllib.request

# ===================== 配置区（修改这里） =====================
# wxpusher 凭据：优先读环境变量，未设置则用下面占位
WXPUSHER_TOKEN = os.environ.get("WXPUSHER_TOKEN", "AT_xxx")  # wxpusher appToken
WXPUSHER_UID = os.environ.get("WXPUSHER_UID", "UID_xxx")     # wxpusher uid
REMOTE = "/root/autodl-tmp/PROJ"  # 服务器工作目录
OUTPUT_DIR = "checkpoints"        # 训练输出子目录（相对 REMOTE，按实际训练脚本设置）
TRAIN_LOG = "train.log"           # 训练日志文件名（相对 REMOTE，与启动脚本一致）
STAGE1_EPOCHS = 10             # Stage1 总 epoch（按训练脚本实际配置修改）
STAGE2_EPOCHS = 1              # Stage2 总 epoch（按训练脚本实际配置修改）
CHECK_INTERVAL = 3600          # 检查间隔秒（默认 1 小时）
# 训练产物命名约定（按实际训练脚本调整）：
STAGE1_PREFIX = "stage1_epoch"   # Stage1 各 epoch checkpoint 前缀
STAGE2_PREFIX = "stage2_epoch"   # Stage2 各 epoch checkpoint 前缀
STAGE1_FINAL = "stage1_final.pth" # Stage1 最终 checkpoint 文件名
FINAL_PATTERN = "final|model"     # 最终模型文件名匹配模式（grep -E）
STAGE1_LABEL = "Stage 1"          # Stage1 显示标签
STAGE2_LABEL = "Stage 2"          # Stage2 显示标签
# ==============================================================
API = "https://wxpusher.zjiecode.com/api/send/message"


def push(title, content):
    if not WXPUSHER_TOKEN or not WXPUSHER_UID or \
       "xxx" in WXPUSHER_TOKEN or "xxx" in WXPUSHER_UID:
        print("ERROR: WXPUSHER_TOKEN / WXPUSHER_UID not configured "
              "(set env vars or edit the config block)", flush=True)
        return False
    payload = {
        "appToken": WXPUSHER_TOKEN,
        "content": f"<h3>{title}</h3><pre style='white-space:pre-wrap'>{content}</pre>",
        "contentType": 2,
        "uids": [WXPUSHER_UID],
    }
    req = urllib.request.Request(
        API, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"推送失败: {e}", flush=True)
        return False


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, timeout=30).stdout
    except Exception as e:
        return f"err:{e}"


def collect():
    data = {}
    out = f"{REMOTE}/{OUTPUT_DIR}"
    gpu_line = sh("nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total "
                  "--format=csv,noheader,nounits 2>/dev/null").strip()
    if gpu_line:
        parts = gpu_line.split(",")
        if len(parts) >= 3:
            data["gpu_util"], data["mem_used"], data["mem_total"] = \
                parts[0].strip(), parts[1].strip(), parts[2].strip()
    data["nproc"] = sh(f"ps aux | grep train | grep -v grep | wc -l").strip()
    ckpt_lines = sh(f"ls {out}/ 2>/dev/null | grep -E '{STAGE1_PREFIX}|{STAGE2_PREFIX}|{FINAL_PATTERN}'").strip().splitlines()
    data["stage1_done"] = sum(1 for l in ckpt_lines if STAGE1_PREFIX in l)
    data["stage2_done"] = sum(1 for l in ckpt_lines if STAGE2_PREFIX in l)
    data["has_stage1_final"] = sh(f"test -f {out}/{STAGE1_FINAL} && echo yes || echo no").strip()
    data["has_final"] = sh(f"ls {out}/ 2>/dev/null | grep -qE '{FINAL_PATTERN}' && echo yes || echo no").strip()
    steps = sh(f"tail -1 {out}/steps.jsonl 2>/dev/null").strip()
    if steps:
        try:
            d = json.loads(steps)
            data.update(epoch=d.get("epoch"), stage=d.get("stage"),
                        loss=d.get("loss"), time_elapsed=d.get("time_elapsed_s"),
                        grad_norm=d.get("grad_norm"), global_step=d.get("global_step"))
        except Exception:
            pass
    data["log_tail"] = sh(f"tail -30 {REMOTE}/{TRAIN_LOG} 2>/dev/null").strip()
    data["summary"] = sh(f"cat {out}/train_summary.json 2>/dev/null").strip()
    data["epoch_summary"] = sh(f"cat {out}/epoch_summary.json 2>/dev/null").strip()
    return data


def fmt_duration(s):
    if not s:
        return "?"
    return f"{int(s//3600)}小时{int((s%3600)//60)}分"


def build_text(s):
    lines = []
    if "gpu_util" in s:
        lines.append(f"🖥️ GPU 占用率: {s['gpu_util']}%")
        lines.append(f"💾 显存: {s['mem_used']}/{s['mem_total']} MB")
    else:
        lines.append("🖥️ GPU: 查询失败")
    lines.append("▶️ 训练状态: " + ("运行中" if s.get("nproc") and s["nproc"] != "0" else "未运行"))
    if s.get("has_final") == "yes":
        lines.append("🎉 训练已完成！")
    elif s.get("has_stage1_final") == "yes":
        lines.append(f"📌 当前阶段: {STAGE2_LABEL}")
        lines.append(f"   第 {s.get('epoch','?')} epoch / 共 {STAGE2_EPOCHS} epoch")
    elif s.get("stage") is not None:
        if s["stage"] == 1:
            ep = s.get("epoch", 0)
            lines.append(f"📌 当前阶段: {STAGE1_LABEL}")
            lines.append(f"   第 {ep+1} epoch / 共 {STAGE1_EPOCHS} epoch")
            lines.append(f"   已完成 checkpoint: {s['stage1_done']} 个")
        else:
            lines.append(f"📌 当前阶段: {STAGE2_LABEL}")
    else:
        log = s.get("log_tail", "")
        if "recompute" in log or "precompute" in log or "cache" in log:
            lines.append("📌 当前: 预计算特征 / 准备数据中...")
        else:
            lines.append("📌 当前: 启动中 / 数据加载中...")
    if s.get("loss") is not None:
        lines.append(f"📉 最近损失: {s['loss']:.4f}")
    if s.get("grad_norm") is not None:
        lines.append(f"📈 梯度范数: {s['grad_norm']:.1f}")
    if s.get("time_elapsed"):
        lines.append(f"⏱️ 已用时间: {fmt_duration(s['time_elapsed'])}")
    if s.get("global_step") is not None:
        lines.append(f"🔢 全局步数: {s['global_step']}")
    log = s.get("log_tail", "")
    if log:
        losses = re.findall(r"loss=([\d.]+)", log[-2000:])
        if losses:
            lines.append(f"📊 最近loss序列: {', '.join(f'{float(x):.4f}' for x in losses[-3:])}")
        for line in log.splitlines()[-10:]:
            if "Epoch" in line and "complete" in line:
                lines.append(f"✅ {line.strip()}")
    if s.get("epoch_summary"):
        try:
            es = json.loads(s["epoch_summary"])
            if isinstance(es, list) and es:
                lines.append("📋 epoch 损失历史:")
                for e in es[-5:]:
                    st = "Stage1" if e.get("stage") == 1 else "Stage2"
                    lines.append(f"   {st} ep{e.get('epoch','?')+1}: loss={e.get('avg_loss','?'):.4f}")
        except Exception:
            pass
    return "\n".join(lines)


def check_anomaly(s):
    warns = []
    text = (s.get("log_tail", "") + " " + s.get("summary", "")).lower()
    if "traceback" in text:
        warns.append("检测到 Traceback 错误")
    if "cuda out of memory" in text or "out of memory" in text:
        warns.append("显存不足 OOM")
    if "nan" in text:
        warns.append("损失出现 NaN")
    if "inf" in text:
        warns.append("损失出现 Inf")
    gn = s.get("grad_norm")
    if gn is not None and gn > 1e6:
        warns.append(f"梯度范数异常大 ({gn:.0e})，可能梯度爆炸")
    return warns


def main():
    print(f"[{time.strftime('%H:%M:%S')}] 服务器训练监控已启动", flush=True)
    push("训练监控已启动", "服务器端每小时监控已就绪，训练开始后将每小时推送进度。")
    while True:
        try:
            s = collect()
            text = build_text(s)
            warns = check_anomaly(s)
            if warns:
                title = "⚠️ 训练异常"
                text = "❗ " + "；".join(warns) + "\n\n" + text
            else:
                title = "训练进度"
            push(title, text)
            print(f"[{time.strftime('%H:%M:%S')}] 已推送: {title}", flush=True)
        except Exception as e:
            push("监控异常", f"服务器监控出错: {e}")
            print(f"[{time.strftime('%H:%M:%S')}] 错误: {e}", flush=True)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
