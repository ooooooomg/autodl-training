#!/usr/bin/env bash
# ============================================================================
# 远程训练启动模板（部署到服务器后执行）
# 用法：上传到服务器 /root/autodl-tmp/PROJ/ 后：bash start_train.sh
#
# 修改以下训练命令以匹配你的项目：
#   --data_dir / --max_samples / 权重路径 / --output_dir
#   --batch_size / --epochs / 其他参数
#
# 关键：nohup + & 使训练独立于 SSH 会话，本机关机也不中断。
# ============================================================================
set -euo pipefail
cd /root/autodl-tmp/PROJ

# AutoDL 的 python 不在 PATH，用完整路径（或取消注释下面一行）
export PATH=/root/miniconda3/bin:$PATH

echo "=== Starting training ==="
echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader)"

# 训练完成后自动关闭实例（可选，避免按量计费空转）：
# nohup bash -c 'python train.py ...; source /root/autodl-tmp/auto_shutdown.sh' &

nohup python train.py \
  --data_dir ./DATA --max_samples 100000 \
  --checkpoint ./weights/init.pt \
  --output_dir ./checkpoints --batch_size 4 --image_size 1024 \
  --epochs 10 \
  --num_workers 8 --device cuda > ./train.log 2>&1 &

echo "TRAIN_PID: $!"
echo "Started at $(date)"
