# AutoDL 服务器管理速查

本文件沉淀 AutoDL 云服务器实战中踩过的坑与常用命令，供 `autodl-training` skill 使用。

## 环境要点

- **Python 不在 PATH**：AutoDL 镜像的 conda 在 `/root/miniconda3/bin/python`。SSH 登录后 `python` 不可用，需用完整路径或 `export PATH=/root/miniconda3/bin:$PATH`。
- **torch 版本**：镜像自带 torch（可能较旧，如 1.10+cu113）。用 `pip install` 补装 `timm opencv-python pycocotools scipy PyYAML`。
- **版本兼容**：检查训练代码是否用了高版本 API（如 `torch.load(weights_only=...)` 是 2.0+）。优先保证代码兼容服务器 torch，不要升级服务器 torch（可能破坏镜像）。

## 磁盘布局

- **系统盘**：30GB，装镜像，不要放大数据。
- **数据盘**：`/root/autodl-tmp`，大数据放这里（模型、数据集）。
- **公共存储**：`/autodl-pub/data`，含常见数据集（COCO/ImageNet 等，常为 zip）。
- **控制面板磁盘显示有刷新延迟**：以服务器 `df -h` 为准。

## 常用命令

```bash
# GPU / 显存
nvidia-smi --query-gpu=name,memory.total,utilization.gpu --format=csv

# 磁盘
df -h /root/autodl-tmp

# 依赖检查
/root/miniconda3/bin/python -c "import torch,timm,cv2; print(torch.__version__)"

# 后台训练（nohup，本机关机不影响）
cd /root/autodl-tmp/PROJ
nohup python train.py ... > train.log 2>&1 &
```

## 计费

- **按量计费**：开机即计费（含传输、空闲、训练）。不同机型价格不同（高配 GPU 通常 ￥2-10/时）。
- 训练前先估算时长，充值预留余量（余额不足会停机，中断训练）。
- 余额只能在 AutoDL **网页控制台**查看，服务器内无法查询。

## 常见坑

1. **Windows 上传文件**：python subprocess 调 `tar` 会用错（Git Bash tar vs Windows tar），用 `python tarfile` 打包。
2. **大文件传输**：SFTP 约 1MB/s（共享带宽），2GB+ 文件需约 40 分钟。传输中面板显示可能不变，以 `stat -c %s` 确认在增长。
3. **SSH 断连**：所有长任务用 nohup 后台 + 日志文件；监控脚本读日志文件而非依赖实时 SSH。
4. **checkpoint 约定**：监控脚本假设训练产出 `stage1_epoch*`、`stage2_epoch*`、`steps.jsonl`、`epoch_summary.json`、`train_summary.json`。训练脚本命名不同时需改 `monitor_server.py`。
