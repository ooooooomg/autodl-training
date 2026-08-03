---
name: autodl-training
description: 云 GPU 训练全流程：部署、监控、评估与报告。覆盖：SSH/SFTP 连接、环境配置、代码/权重/数据上传(断点续传)、远程启动训练(nohup后台)、每小时训练监控与异常检测、wxpusher 微信推送、训练后模型评估与论文对比、训练loss可视化、LaTeX实验笔记编译PDF。触发词：autodl、云服务器、远程训练、SSH上传、训练监控、微信推送训练进度、GPU云训练、评估模型、跑评估、实验报告、训练笔记、loss可视化、与论文对比、编译PDF。
---

# AutoDL 远程训练部署与监控

在 SSH 可达的 GPU 服务器上完成训练的部署和监控：上传代码与数据、配置环境、后台启动训练、按小时推送进度。

## 何时使用

- 需要在云 GPU 服务器上训练，本地显存不够
- 需要把本地代码、权重、数据传到远程服务器
- 需要长时间训练（数小时到数天）并自动监控
- 需要把训练进度和异常推送到微信
- 训练完成后需要评估模型质量（box-prompt / dense / detection）
- 需要把实测结果与论文数字对比、生成可视化曲线和实验笔记

## 触发后先收集配置

skill 触发后，先向用户询问下列信息，不要直接执行脚本。这些信息随用户和环境变化，无法从仓库读取：

1. SSH 服务器地址、端口
2. SSH 用户名、密码
3. wxpusher 的 `WXPUSHER_TOKEN`、`WXPUSHER_UID`（用户没有时引导到 wxpusher.zjiecode.com 注册）
4. 本地代码目录、训练脚本入口（如 `train.py`）
5. 教师权重、学生权重的本地路径
6. 训练数据本地路径
7. 训练超参：batch_size、epochs、max_samples、image_size 等（用户未指定时用默认值并确认）
8. （训练后评估）评估数据位置：COCO val / LVIS / 检测框
9. （训练后评估）论文目标数字（用于对比）
10. （训练后评估）是否生成训练曲线 / 实验笔记 PDF

用 `AskUserQuestion` 逐个询问，不要一次性堆给用户。收集完后把凭据写入环境变量（`SSH_HOST` 等），运行 `ssh_helper.py check` 和 `wxpush.py check` 验证，再按下面各 Step 执行。若走全自动，最后运行 `orchestrator.py`。

SSH 密码和 wxpusher token 只在本次会话的环境变量里用，不要写入文件、不要回显。

## 流程总览

```
Step 0: SSH 连接与服务器检查
Step 1: 服务器环境配置
Step 2: 代码上传与解压
Step 3: 权重上传
Step 4: 数据上传（分片断点续传）
Step 5: 启动训练（nohup 后台）
Step 6: 每小时监控 + 微信推送
Step 7: 训练完成后的评估
```

---

## Step 0: SSH 连接与服务器检查

前提：服务器地址/端口/用户名/密码（或密钥）；本地 `pip install -r requirements.txt`（paramiko）。

`scripts/ssh_helper.py` 提供连接、命令执行、文件传输：

```bash
python scripts/ssh_helper.py check                     # 连接 + GPU/磁盘/Python 环境
python scripts/ssh_helper.py exec "nvidia-smi; df -h"  # 执行远程命令
python scripts/ssh_helper.py put local remote          # 上传文件
python scripts/ssh_helper.py get remote local          # 下载文件
```

检查要点：
- GPU 型号、显存、驱动：`nvidia-smi`
- 磁盘：`df -h`，区分系统盘和数据盘（AutoDL 数据盘在 `/root/autodl-tmp`）
- Python：AutoDL 的 python 在 `/root/miniconda3/bin/python`，PATH 里可能没有，用完整路径
- 依赖：torch/torchvision/timm/cv2/pycocotools/scipy/yaml 是否齐全

## Step 1: 服务器环境配置

AutoDL 镜像自带 torch+CUDA，但常缺 timm/cv2/pycocotools 等：

```bash
/root/miniconda3/bin/pip install timm opencv-python pycocotools scipy PyYAML -q
```

服务器 torch 版本可能较旧（如 1.10）。检查代码是否用了 `weights_only`（torch 2.0+）、`torch.linalg` 等新 API。优先保证代码兼容服务器 torch，不要升级服务器 torch，避免破坏镜像。

## Step 2: 代码上传与解压

```bash
# 本地打包（排除数据/权重/缓存）
tar --exclude=DATA --exclude=weights --exclude=checkpoints \
    --exclude=outputs --exclude='*.zip' --exclude='__pycache__' \
    -cf code_pack.tar .

# 上传并解压
python ssh_helper.py put code_pack.tar /root/autodl-tmp/PROJ/code_pack.tar
python ssh_helper.py exec "cd /root/autodl-tmp/PROJ && tar -xf code_pack.tar"
```

Windows 下 python subprocess 调 `tar` 可能失败（Git Bash 的 tar 和 Windows 的 tar 混用），用 python `tarfile` 打包更可靠。

## Step 3: 权重上传

大文件直接用 SFTP 上传，速度约 1MB/s（共享带宽）：

```bash
python ssh_helper.py put weights/student.pt /root/autodl-tmp/PROJ/weights/
python ssh_helper.py put weights/teacher.pth /root/autodl-tmp/PROJ/weights/
```

2GB+ 的文件约需 40 分钟。传完用 `stat -c %s` 对比本地和服务器端字节数，确认完整。

## Step 4: 数据上传（分片断点续传）

大数据（10GB+）分片打包上传。`scripts/upload_data.py` 每个 shard 打包 → 上传 → 解压 → 校验文件数 → 删本地 tar。已上传且校验通过的 shard 会自动跳过，中断后重跑不浪费时间。

```bash
# 修改脚本顶部的 LOCAL_DATA / REMOTE_BASE / SHARDS / EXPECTED_FILES
python scripts/upload_data.py
```

## Step 5: 启动训练（nohup 后台）

模板：`scripts/start_train.sh`。先改里面的训练命令（`--data_dir`、`--max_samples`、权重路径、`--output_dir`、`--batch_size`、epoch 数等），再上传执行：

```bash
python ssh_helper.py put scripts/start_train.sh /root/autodl-tmp/PROJ/start_train.sh
python ssh_helper.py exec "cd /root/autodl-tmp/PROJ && bash start_train.sh"
```

`nohup ... &` 让训练不依赖 SSH 会话，本机关机也不中断。日志重定向到 `train.log`，与监控脚本的 `TRAIN_LOG` 保持一致。

建议先在本地用少量数据跑一次 smoke 训练，确认代码能跑通，再上服务器。

## 全自动（可选）：`scripts/orchestrator.py`

配好环境变量和脚本顶部的 `TEACHER_PATH` / `TARGET_SHARDS` 等常量后，运行：

```bash
python scripts/orchestrator.py
```

它会：
1. 每 5 分钟检查服务器，直到教师权重完整、所有数据 shard 就绪
2. 就绪后执行 `start_train.sh` 启动训练
3. 30 秒后启动服务器端 `monitor_server.py`

orchestrator 运行在本地，需要本机保持开机直到训练启动。训练启动后独立于本机。

## Step 6: 每小时监控 + 微信推送

`scripts/monitor_server.py` 部署到服务器，nohup 常驻，本机关机也能继续推送。使用前改顶部配置：`REMOTE`、`OUTPUT_DIR`、`TRAIN_LOG`、`STAGE1_EPOCHS`、`STAGE2_EPOCHS`。

```bash
nohup /root/miniconda3/bin/python monitor_server.py > monitor_server.out 2>&1 &
```

推送内容（中文）：
- GPU 占用率、显存
- 当前阶段（Stage 1/2）和 epoch
- 最近损失、梯度范数、已用时间、checkpoint 数量
- 异常检测：OOM / NaN / Traceback / 梯度爆炸，异常时标 ⚠️

`scripts/wxpush.py` 封装 wxpusher API：

```bash
python scripts/wxpush.py check                # 发测试消息验证凭据
python scripts/wxpush.py "标题" "内容"        # 发送
```

凭据走 `WXPUSHER_TOKEN` / `WXPUSHER_UID` 环境变量。

## Step 7: 训练完成后的评估

训练产出最终模型后，对模型做系统评估（按项目领域选择指标），对比论文目标，并生成可视化与实验笔记。

> 评估协议**因项目而异**。以下以图像分割/检测类项目（如 SAM 家族）为例，其他领域按实际调整。

### 7.1 评估脚本

评估脚本通常位于项目的 `eval/` 目录。分割/检测类项目的常见形态：

- `eval_box_prompt.py` — box / box+1pt / box+2pt prompt 分割（COCO/LVIS）
- `eval_dense_seg.py` — dense 分割（`--points_per_side 10 14 17 20 22`）
- `eval_detection.py` — detection-assisted（需 `--precomputed_detections`）
- 一键串行跑全套件：`run_local_eval.py`

（非分割类项目：替换为对应领域的评估脚本，如分类用 accuracy/top-k，检测用 mAP 等。）

### 7.2 评估关键注意（实测）

- **cv2 中文路径 bug**：含中文的绝对路径（如 `E:\某项目`）会让 `cv2.imread` 失败。
  评估必须用**相对路径**（cwd 在项目根）+ 相对路径参数。
- **图片嵌套路径**：若图片嵌套一层（`val2017/val2017`），
  `--coco_root` 要指到内层（`DATA/val2017`），脚本内部会 `os.path.join(coco_root, "val2017")`。
- **全量评估很慢**：先用 `--max_samples` 少量样本冒烟，再跑全量。
- 全量评估耗时（约 5000 图 8 分钟等）按硬件/数据规模浮动。

### 7.3 可视化

训练曲线脚本 `scripts/plot_training_loss.py`（读 `steps.jsonl`，输出 `training_curve.png`）：
五面板训练曲线（全 loss / Stage1 / Stage2 / 梯度范数 / 每 epoch 均值）。

### 7.4 实验笔记（LaTeX → PDF）

- LaTeX 模板 `experiment_notes/training_notes.tex`
- 用 **xelatex** 编译（支持中文）：`xelatex -interaction=nonstopmode training_notes.tex`
- 中文需 `\usepackage[UTF8]{ctex}`
- MiKTeX 路径示例：`/d/miktex/miktex/bin/x64/xelatex`

### 7.5 结果对比与推送

- 实测 vs 论文目标，按"达到论文百分比"评估（蒸馏模型通常可达基线 90% 以上）
- 结果用 `wxpush.py` 推送到微信（含对比表、PDF 路径）

---

## 首次使用需要配置的项

每个脚本都要先填你的真实配置，无法跳过：

**必填**
- [ ] SSH 凭据：`SSH_HOST` / `SSH_PORT` / `SSH_USER` / `SSH_PASSWORD`
- [ ] wxpusher 凭据：`WXPUSHER_TOKEN` / `WXPUSHER_UID`
- [ ] 训练命令：`scripts/start_train.sh` 里的各项参数

**用到对应功能才配**
- [ ] 数据上传：`upload_data.py` 的 `LOCAL_DATA` / `REMOTE_BASE` / `SHARDS` / `EXPECTED_FILES`
- [ ] 全自动：`orchestrator.py` 的 `TEACHER_PATH` / `TEACHER_SIZE` / `TARGET_SHARDS` / `TARGET_IMAGES`
- [ ] 监控：`monitor_server.py` 的 `REMOTE` / `OUTPUT_DIR` / `TRAIN_LOG` / `STAGE1_EPOCHS` / `STAGE2_EPOCHS`

**依赖**：`pip install -r requirements.txt`（paramiko）

验证配置：`ssh_helper.py check` 能连上服务器说明 SSH 配好；`wxpush.py check` 微信能收到测试消息说明推送配好。

## 常见问题

1. 服务器 python 不在 PATH：用 `/root/miniconda3/bin/python` 完整路径
2. Windows 下 tar 打包失败：用 python `tarfile`
3. AutoDL 系统盘只有 30GB，大数据放 `/root/autodl-tmp` 数据盘
4. 控制面板的磁盘占用显示有延迟，以服务器 `df -h` 为准
5. AutoDL 按量计费，开机即扣费（传输、空闲也算），余额不足会停机
6. 长任务用 nohup 后台 + 日志文件，监控读日志而不是依赖实时 SSH
7. 本机运行 skill 脚本前，确认用的解释器装有 paramiko
8. 监控脚本按训练产物的约定命名匹配（`stage1_epoch*`、`steps.jsonl`、`epoch_summary.json` 等），训练脚本命名不同时改 `monitor_server.py` 的 `collect()`

## 脚本

`scripts/` 下的工具，使用前按"首次使用需要配置的项"填配置：
- `ssh_helper.py` — SSH/SFTP 连接、命令执行、文件传输
- `upload_data.py` — 分片数据上传（断点续传）
- `wxpush.py` — wxpusher 微信推送
- `monitor_server.py` — 服务器端每小时训练监控
- `orchestrator.py` — 全自动：等传输完成 → 启动训练 → 启动监控
- `start_train.sh` — 远程训练启动模板
