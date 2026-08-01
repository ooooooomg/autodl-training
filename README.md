# autodl-training — AutoDL 云 GPU 训练部署与监控

一个 Claude Code skill：在 AutoDL（或其他 SSH 可达的 GPU 服务器）上完成训练部署和监控。从一次完整的云训练实战中沉淀，覆盖从代码上传到训练完成的全部流程。

## 安装

```bash
git clone https://github.com/ooooooomg/autodl-training.git
cp -r autodl-training/autodl-training ~/.claude/skills/
pip install -r ~/.claude/skills/autodl-training/requirements.txt
```

skill 在触发条件匹配时自动加载，也可显式调用 `/autodl-training`。

## 功能

| 问题 | 方案 |
|------|------|
| 本机显存不够，需云 GPU 训练 | SSH 检查 → 环境配置 → 代码上传 → 权重/数据上传 → nohup 启动训练 |
| 大数据（10GB+）上传慢、易中断 | `scripts/upload_data.py` 分片断点续传 |
| Windows 下打包上传失败 | 用 python `tarfile` 而非 subprocess 调 tar |
| 训练数十小时需自动监控 | `scripts/monitor_server.py` 服务器端常驻，每小时检查推送 |
| 需及时知道训练异常 | 自动检测 OOM / NaN / Traceback / 梯度爆炸，微信推送 ⚠️ 警示 |
| 需把进度推到手机 | `scripts/wxpush.py` 封装 wxpusher API |
| 本机关机后训练进度丢失 | 训练和监控都用 nohup 跑在服务器上，独立于本机 |
| 配置一次后全流程自动 | `scripts/orchestrator.py`：等传输 → 启动训练 → 启动监控 |

## 文件结构

```
autodl-training/
├── SKILL.md                       # 主文档：交互流程 + 各 Step 操作
├── requirements.txt               # paramiko
├── scripts/
│   ├── ssh_helper.py              # SSH/SFTP 连接、命令执行、文件传输
│   ├── upload_data.py             # 分片数据上传（断点续传）
│   ├── wxpush.py                  # wxpusher 微信推送
│   ├── monitor_server.py          # 服务器端每小时训练监控
│   ├── orchestrator.py            # 全自动：等传输 → 启动训练 → 启动监控
│   └── start_train.sh             # 远程训练启动模板
└── references/
    └── autodl-server-guide.md     # AutoDL 服务器速查（环境/磁盘/计费/常见坑）
```

## 使用

触发 skill 后，Claude 会先询问服务器、推送凭据、训练命令等配置，然后自动执行。也可以手动运行各脚本。

详见 `autodl-training/SKILL.md` 的"触发后先收集配置"和"首次使用需要配置的项"。

## 许可

MIT
