"""分片数据上传到 AutoDL 服务器（断点续传）。

每个 shard：本地打包(tarfile) -> SFTP 上传 -> 服务器解压 -> 校验文件数 -> 删本地 tar。
已上传且校验通过的 shard 自动跳过。

用法：
    python upload_data.py                          # 使用脚本顶部配置
    python upload_data.py --local DATA --remote /root/autodl-tmp/PROJ/DATA
"""
import argparse
import os
import sys
import tarfile
import time

import paramiko

# ===================== 配置区（修改这里，或设置 SSH_HOST/SSH_PASSWORD 等环境变量） =====================
HOST = os.environ.get("SSH_HOST", "YOUR_SERVER_HOST")  # SSH 主机
PORT = int(os.environ.get("SSH_PORT", "22"))           # SSH 端口
USER = os.environ.get("SSH_USER", "root")              # SSH 用户名
PASSWORD = os.environ.get("SSH_PASSWORD", "YOUR_PASSWORD")  # SSH 密码
LOCAL_DATA = os.environ.get("LOCAL_DATA", "E:/path/to/DATA")  # 本地数据目录（含各 shard 子目录）
REMOTE_BASE = os.environ.get("REMOTE_DATA", "/root/autodl-tmp/PROJ/DATA")  # 服务器目标目录
SHARDS = None                            # 如 ["sa_000000","sa_000001"]；None=自动发现
EXPECTED_FILES = 0                         # 每个 shard 预期文件数（>0 时要求恰好相等；0=只要目录存在且非空）
TAR_MODE = os.environ.get("TAR_MODE", "gz")  # gz=压缩(小)/空串=纯 tar(图像等已压缩数据更快)
# ===============================================================


def connect():
    """主机密钥固定:首次连接把密钥记入 known_hosts,之后任何密钥变化
    (可能的中間人攻击)都会被拒绝。此前无条件 AutoAddPolicy + 密码认证,
    链路中间人可直接截获凭据。"""
    known_hosts = os.path.join(os.path.expanduser("~"), ".ssh", "known_hosts")
    c = paramiko.SSHClient()
    c.load_host_keys(known_hosts)
    hk = c.get_host_keys()
    known = hk.lookup(HOST) is not None or hk.lookup(f"[{HOST}]:{PORT}") is not None
    if known:
        c.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        print(f"[security] 首次连接 {HOST}:{PORT},记录主机密钥到 {known_hosts}", flush=True)
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD,
              timeout=30, banner_timeout=30, auth_timeout=30)
    if not known:
        c.save_host_keys(known_hosts)
    return c


def discover_shards():
    """自动发现本地数据目录下的 shard（子目录）。"""
    return sorted(d for d in os.listdir(LOCAL_DATA)
                  if os.path.isdir(os.path.join(LOCAL_DATA, d)))


def remote_ok(c, shard):
    """返回 True 表示该 shard 已在服务器上完整存在、可跳过。

    语义(修复):EXPECTED_FILES>0 时要求远端文件数恰好相等;=0 时要求
    目录存在且非空。旧实现里 EXPECTED_FILES=0(默认)时 `ls 不存在的目录
    | wc -l` 输出 0,恰好等于 0,于是「目录不存在」被判定为「已存在」——
    所有 shard 被跳过,数据永远传不上去(与注释「填 0 则只检查存在」相反)。"""
    shard_path = f"{REMOTE_BASE}/{shard}"
    if EXPECTED_FILES > 0:
        stdin, stdout, stderr = c.exec_command(
            f'ls "{shard_path}" 2>/dev/null | wc -l', timeout=30)
        return stdout.read().decode().strip() == str(EXPECTED_FILES)
    stdin, stdout, stderr = c.exec_command(
        f'[ -d "{shard_path}" ] && [ -n "$(ls -A "{shard_path}")" ] && echo EXISTS', timeout=30)
    return "EXISTS" in stdout.read().decode()


def pack_local(shard):
    """用 python tarfile 打包（避免 Windows tar 问题）。"""
    temp_dir = os.environ.get("TEMP", os.environ.get("TMP", "."))
    tar_path = os.path.join(temp_dir, f"{shard}.tar.gz")
    src_dir = os.path.join(LOCAL_DATA, shard)
    t0 = time.time()
    with tarfile.open(tar_path, "w:" + TAR_MODE) as tar:
        tar.add(src_dir, arcname=shard)
    print(f"    打包完成 {time.time()-t0:.0f}s", flush=True)
    return tar_path


def upload(c, local, remote):
    sftp = c.open_sftp()
    sftp.put(local, remote)
    sftp.close()


def extract_remote(c, shard):
    stdin, stdout, stderr = c.exec_command(
        f'cd "{REMOTE_BASE}" && tar -xzf "{shard}.tar.gz" && rm "{shard}.tar.gz" && echo EXTRACTED',
        timeout=300)
    out = stdout.read().decode()
    if "EXTRACTED" not in out:
        raise RuntimeError(f"解压失败: {out} {stderr.read().decode()}")


def main():
    global LOCAL_DATA, REMOTE_BASE, SHARDS
    parser = argparse.ArgumentParser(description="分片数据上传（断点续传）")
    parser.add_argument("--local", help="本地数据目录")
    parser.add_argument("--remote", help="服务器目标目录")
    args = parser.parse_args()
    if args.local:
        LOCAL_DATA = args.local
    if args.remote:
        REMOTE_BASE = args.remote

    shards = SHARDS if SHARDS else discover_shards()
    if not shards:
        print("未发现数据 shard 目录，请检查 LOCAL_DATA")
        return

    c = connect()
    c.exec_command(f'mkdir -p "{REMOTE_BASE}"', timeout=30)
    total_start = time.time()

    for idx, shard in enumerate(shards):
        t0 = time.time()
        if remote_ok(c, shard):
            print(f"[{idx+1}/{len(shards)}] {shard}: 服务器已存在，跳过", flush=True)
            continue
        print(f"[{idx+1}/{len(shards)}] {shard}: 打包...", flush=True)
        tar_path = pack_local(shard)
        print(f"[{idx+1}/{len(shards)}] {shard}: {os.path.getsize(tar_path)/1e6:.0f}MB 上传中...", flush=True)
        t_up = time.time()
        upload(c, tar_path, f"{REMOTE_BASE}/{shard}.tar.gz")
        print(f"[{idx+1}/{len(shards)}] {shard}: 上传{time.time()-t_up:.0f}s, 解压...", flush=True)
        extract_remote(c, shard)
        if not remote_ok(c, shard):
            print(f"[警告] {shard}: 校验失败", flush=True)
        try:
            os.remove(tar_path)
        except OSError:
            pass
        print(f"[{idx+1}/{len(shards)}] {shard}: 完成({time.time()-t0:.0f}s)", flush=True)

    print(f"=== 全部 {len(shards)} 个 shard 完成，耗时 {(time.time()-total_start)/3600:.1f}h ===", flush=True)
    c.close()


if __name__ == "__main__":
    main()
