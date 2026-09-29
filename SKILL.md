---
name: matpool-gpu
description: 操作矩池云（Matpool / matgo.cn，用户有时称锯齿云）的 GPU 租赁、镜像与网盘、SSH 运行及 PaaS 任务 API。用于在该平台选卡、准备租机、运行训练或推理、查询或取消任务；不用于 MT Switch 模型代理配置。
---

# 矩池云 GPU

将用户的计算任务落到矩池云，按现有授权完成选型、配置、执行和结果取回。主机市场：<https://matgo.cn/host-market/gpu>。

## 首次安装与认证

用户要安装、初始化 Token 或处理认证失败时，读 [references/setup.md](references/setup.md)。优先由 Agent 检查安装位置与已有配置，再引导本机初始化。
公开库存无需认证；官网和 PaaS 凭证分别配置。`scripts/matpool_auth.py status` 只显示本地状态；`init --service web|paas` 保存凭证，`check --service web|paas` 做只读认证检查。不要要求用户把 Token 粘贴到聊天；终端隐藏输入由用户在自己的终端完成，Agent 可从已授权的环境变量或明确指定的私密文件导入。安装与认证不授权租机。
客户端按 `--token-file`、对应环境变量、`~/.config/matpool-gpu/` 初始化文件的顺序读取，可用 `MATPOOL_CONFIG_DIR` 改目录。先复用已有有效配置；Chrome 导入仅在用户选择并已授权时执行。

Windows 主机先读 [references/windows.md](references/windows.md)，按实际 Python、PowerShell、ACL 与浏览器能力执行。

## 选择操作方式

- **查 GPU、价格、库存**：优先运行 `python3 scripts/matpool_inventory.py --gpu A2000`，它读取无需 Token 的官方市场资源池接口；具体语义见 [references/inventory.md](references/inventory.md)。
- **直接 API 租机、镜像、实例及释放**：优先使用 `scripts/matpool_web.py`，见 [references/web-api.md](references/web-api.md)。官网接口需要网页登录 Token；PaaS Token 不能替代。在支持的 macOS 环境且用户授权复用 Chrome 登录态时可用限定站点导入脚本。Windows 使用已配置凭据或授权浏览器。
- **交互式租机**：用户已要求或允许网页操作时使用浏览器，见 [references/console.md](references/console.md)。用户明确限定 API 时，不自动切换网页下单；仅要求用技能辅助而没有限定方式时，已有网页授权可继续沿用，不强制用户先导出 Token。
- **已有实例跑代码**：从用户提供的信息或租用列表取得 SSH 连接信息，采用 SSH/SCP/rsync；保存路径和退出检查见 console.md。
- **PyTorch / CUDA 任务**：先核对 Python 解释器，见 [references/pytorch.md](references/pytorch.md)。镜像 633955 的 PyTorch 位于 `myconda` 环境；系统 `python3` 导入失败不代表镜像未安装。官网启动字段限制 1024 字节，短测试用 `scripts/make_torch_startup.py`。
- **自动提交、查询、取消批任务**：已有 PaaS Token 时使用 `scripts/matpool_api.py`；接口、认证及示例见 [references/paas-api.md](references/paas-api.md)。没有 Token 可以完成请求准备，需要真实 API 操作时再请用户配置。不要把网页登录凭证或模型 API Token 当成 PaaS Token。
- **MT Switch / 模型转发**：那是另一种产品能力。不要为了租 GPU 安装 `@mtswitch/switch`、运行 `matpool setup`，或修改 Codex/Claude/Gemini 配置。

## 执行要点

1. 从任务和上下文提取显存、卡数、运行环境、数据所在区域、时长或预算、结果位置。先做可独立完成的只读查询和配置准备，只问真正影响执行的缺项。
2. 创建前先查询精确型号和区域的资源池空余，保留查询时间、完整型号、驱动及可用份数。无空余不提交排队任务，除非用户要求排队。价格、库存、驱动和镜像实时核对，不把历史文档或营销横幅当作最终报价。区分单卡价与多卡合计价；预计计算费为页面实例小时合计价乘运行小时，存储等另计。
3. 网盘与实例必须同区。`/mnt` 是文档默认挂载路径，实际运行前核实。实例本地盘不能当成持久网盘。
4. 将订单或 API 请求准备到可审阅状态。创建技能或研究平台不授权付费租机；已有平台、任务和预算授权时直接在范围内执行，不重复询问。新增付费资源、超预算、非原定续费须补足授权。
5. 创建请求不自动重试：超时可能已创建，先按备注和时间查任务列表排除重复。取消之前确认内部任务 ID 与目标匹配，处理结果保存；不因取消接口返回成功就宣称已释放。
6. 最终报告实例/任务 ID、实际状态、结果位置及是否仍在计费。取得队列 ID 不代表任务成功；训练成功需要日志、退出码或实际产物证据。

## 验证边界

本技能于 2026-09-07 按公开市场页面和官方文档创建。已验证公共库存、PaaS 鉴权/创建/取消，以及官网 HTTPS 镜像/实例接口。通过官网 API 创建 A2000 后，已使用正确 Conda 解释器完成 PyTorch CUDA 矩阵乘法、取回结果、释放并确认终态；详见 pytorch.md。SSH 和 Jupyter 执行尚未验证成功。遇到文档与现行行为冲突，记录事实并收窄结论，不猜接口、区域 ID 或成功状态。
