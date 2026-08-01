"""SSH/SFTP helper for remote GPU servers (AutoDL / any SSH host).

Generic: credentials come from environment variables or the config block below.
Never hard-code real credentials in this file.

Usage:
    python ssh_helper.py exec "<command>"        # run a remote command
    python ssh_helper.py put <local> <remote>    # upload a file
    python ssh_helper.py get <remote> <local>    # download a file
    python ssh_helper.py check                   # connectivity + GPU + disk check

Environment variables:
    SSH_HOST / SSH_PORT / SSH_USER / SSH_PASSWORD  (or edit the config block)
"""
import os
import sys
import paramiko

# ===================== 配置区（优先用环境变量，其次此处占位） =====================
HOST = os.environ.get("SSH_HOST", "YOUR_SERVER_HOST")
PORT = int(os.environ.get("SSH_PORT", "22"))
USER = os.environ.get("SSH_USER", "root")
PASSWORD = os.environ.get("SSH_PASSWORD", "YOUR_PASSWORD")
# =============================================================================


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD,
              timeout=20, banner_timeout=30, auth_timeout=30)
    return c


def exec_cmd(c, cmd, timeout=300):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def main():
    if "YOUR_" in PASSWORD or "YOUR_" in HOST:
        print("ERROR: SSH credentials not configured. "
              "Set SSH_HOST/SSH_PORT/SSH_USER/SSH_PASSWORD env vars or edit the config block.")
        sys.exit(1)

    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    action = args[0]
    if action == "check":
        c = connect()
        print("=== CONNECTED ===")
        rc, out, err = exec_cmd(c, "nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv; echo ---; df -h /root /data 2>/dev/null; echo ---; python3 --version; echo ---; free -h | head -2")
        print(out)
        if err.strip():
            print("STDERR:", err[:500])
        c.close()
    elif action == "exec":
        cmd = " ".join(args[1:])
        c = connect()
        rc, out, err = exec_cmd(c, cmd)
        print(out)
        if err.strip():
            print("STDERR:", err[:1000])
        print(f"[exit={rc}]")
        c.close()
    elif action == "put":
        local, remote = args[1], args[2]
        c = connect()
        sftp = c.open_sftp()
        sftp.put(local, remote)
        print(f"uploaded {local} -> {remote}")
        sftp.close()
        c.close()
    elif action == "get":
        remote, local = args[1], args[2]
        c = connect()
        sftp = c.open_sftp()
        sftp.get(remote, local)
        print(f"downloaded {remote} -> {local}")
        sftp.close()
        c.close()
    else:
        print(f"Unknown action: {action}")
        print(__doc__)


if __name__ == "__main__":
    main()
