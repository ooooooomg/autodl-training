# autodl-training — Cloud GPU Training Deployment & Monitoring

A Claude Code skill for deploying and monitoring training on AutoDL (or any SSH-reachable GPU server). Distilled from a real cloud-training run, covering everything from code upload to training completion.

## Installation

```bash
git clone https://github.com/ooooooomg/autodl-training.git
cp -r autodl-training/autodl-training ~/.claude/skills/
pip install -r ~/.claude/skills/autodl-training/requirements.txt
```

The skill loads automatically when trigger conditions match. Can also be invoked explicitly: `/autodl-training`.

## Features

| Problem | Solution |
|------|------|
| Not enough local VRAM; need cloud GPU training | SSH check → env setup → code upload → weights/data upload → nohup training launch |
| Large data (10GB+) upload is slow and interrupt-prone | `scripts/upload_data.py` sharded upload with resume |
| Packing fails on Windows | Use python `tarfile`, not subprocess `tar` |
| Training runs for hours; want automated monitoring | `scripts/monitor_server.py` runs server-side, checks hourly and pushes |
| Want to know immediately if training goes wrong | Auto-detects OOM / NaN / Traceback / gradient explosion, pushes ⚠️ alert |
| Want progress pushed to phone | `scripts/wxpush.py` wraps the wxpusher API |
| Losing progress when local machine powers off | Training and monitoring run server-side via nohup, independent of local machine |
| "Configure once, run the whole pipeline automatically" | `scripts/orchestrator.py`: wait for uploads → start training → start monitor |

## File Structure

```
autodl-training/
├── SKILL.md                       # Main doc: interaction flow + step-by-step operations
├── requirements.txt               # paramiko
├── scripts/
│   ├── ssh_helper.py              # SSH/SFTP connect, command exec, file transfer
│   ├── upload_data.py             # Sharded data upload with resume
│   ├── wxpush.py                  # wxpusher WeChat push
│   ├── monitor_server.py          # Server-side hourly training monitor
│   ├── orchestrator.py            # Full pipeline: wait uploads → start training → start monitor
│   └── start_train.sh             # Remote training launch template
└── references/
    └── autodl-server-guide.md     # AutoDL server quick reference (env/disk/billing/pitfalls)
```

## Usage

When triggered, Claude first asks for server, push credentials, and training config, then runs the pipeline automatically. You can also run the scripts manually.

See `autodl-training/SKILL.md` → "触发后先收集配置" and "首次使用需要配置的项".

## License

MIT
