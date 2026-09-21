# PyTorch 运行环境与 CUDA 验证

## 已验证的解释器

2026-09-07，镜像 `633955`（官网名 PyTorch 2.1.2，Ubuntu 20.04）在 A2000 550 驱动资源池实测：

- 启动脚本直接用系统 `python3` 会报 `No module named 'torch'`。
- 正确解释器是 **`/root/miniconda3/envs/myconda/bin/python`**。
- PyTorch `2.1.2+cu121`，CUDA runtime `12.1`，设备 `NVIDIA RTX A2000 12GB`。

在同一镜像中执行任务时，显式使用解释器路径：

```bash
/root/miniconda3/envs/myconda/bin/python your_task.py
```

不要依赖非交互 shell 自动激活 Conda。换镜像先查实际解释器和环境；不能因为系统 Python 导入失败就重装 PyTorch 或断言镜像没有安装。镜像名也不能替代实际版本验证。

## 短启动脚本

官网租机 `cmd` 实测把 3903 字符的 ASCII 脚本截断为 1024 字符，导致 heredoc 不完整、实例退出。客户端现在保守限制为 1024 UTF-8 字节，在本地拒绝超长请求。

使用脚本生成经过真实运行验证的短命令：

```bash
python3 scripts/make_torch_startup.py --result-file torch-result.json > startup.sh
```

将文件内容作为 `/api/node` 的 `cmd`，并设置 `ports` 为字符串 `[{"srcPort":8895,"protocol":2}]`。生成器会查找常见 Conda 环境里的 Python，运行 CUDA 矩阵乘法并写结果 JSON；未找到可运行环境时查看 `/tmp/codex-smoke/errors.txt`。端口结果 URL 应按 web-api.md 保留认证 query、修改 path，不打印连接 Token。

测试创建 256×256 的全 1 CUDA 矩阵，计算 `a @ a`，同步 CUDA 并断言每个元素等于 256。它同时验证导入、GPU 分配、CUDA 运算和结果正确性；仅 `import torch` 或 `cuda.is_available()` 不足以替代此检查。

完整脚本 `scripts/torch_check.py` 可在具备可用 SSH 的 GPU 实例上执行，它会选择 PyTorch 解释器并比较 GPU/CPU 随机矩阵乘法。通过 SSH/SCP 传送完整文件，不塞进受限的启动字段。自定义启动命令后，先验证 SSH/Jupyter 服务实际可用，不能仅凭 API 存在端口映射就假设服务已经启动。

HTTP 服务超时退出不等于释放实例。结果取得后立即 DELETE /node，并 GET 确认终态 4。

## 实测结果

以下为已脱敏的历史 CUDA 验证结果（镜像 `633955`）：

```json
{
  "passed": true,
  "python": "/root/miniconda3/envs/myconda/bin/python",
  "torch_version": "2.1.2+cu121",
  "cuda_runtime": "12.1",
  "device": "NVIDIA RTX A2000 12GB",
  "result_device": "cuda:0",
  "shape": [256, 256],
  "checksum": 16777216.0
}
```

历史测试在结果取回后确认实例进入终态 4。每次新的运行仍需独立核实释放状态。
