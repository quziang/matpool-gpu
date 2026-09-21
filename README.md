# Matpool GPU Skill · 矩池云 GPU

让 AI 编程助手完成矩池云 GPU 工作流：**查库存 → 选镜像 → 准备租机 → 运行任务 → 取回结果 → 核实释放**。

这是一个可安装的 Agent Skill，也是一组可单独使用的 Python 命令行脚本。适合需要临时 GPU 进行 PyTorch 验证、训练或推理的开发者。核心客户端仅依赖 Python 标准库。

**非矩池云官方项目。** 官网 API 来自网站客户端使用的接口，可能发生变化；PaaS 使用独立的官方任务 API。两种方式的凭证和参数不能混用。

## 能做什么

| 场景 | 提供的能力 | 需要认证 |
| --- | --- | --- |
| 选 GPU | 按型号、区域查询库存、驱动、配置与每份小时价 | 否 |
| 官网实例 | 查镜像、查实例、预览及执行租用/释放、查账单 | 官网登录 Token |
| PaaS 批任务 | 预览及提交任务、查状态、列表、取消 | 独立 PaaS Token |
| PyTorch 检查 | 查找可用解释器，实际执行 CUDA 矩阵乘法 | 在 GPU 实例上运行 |
| SSH 工作流 | 提供连接、持久化、产物取回与释放检查指引 | 实例连接信息 |

创建、取消和释放默认只生成预览；加 `--execute` 才会发出请求。查询命令会直接请求服务。客户端不会自动重试创建操作，避免网络超时后重复租机。

## 快速开始：先查库存

本地需要 **Python 3.9+** 和 Git。库存、官网和 PaaS 客户端无需 `pip install`，可在常见 macOS/Linux 环境运行。Chrome 登录导入工具仅支持指定的 macOS Chrome Cookie 格式；GPU 检查需要实例中已有 NVIDIA GPU、驱动和 PyTorch。

```bash
git clone https://github.com/quziang/matpool-gpu.git
cd matpool-gpu

# 无需登录，不会租机
python3 scripts/matpool_inventory.py --gpu A2000

# 可选：限定经过确认的区域 ID（1 区对应 0）
python3 scripts/matpool_inventory.py --gpu A2000 --domain 0
```

输出包含查询时间、完整 GPU 名称、`resource_pool_id`、可用份数、驱动与 `hourly_cny_per_unit`。库存是查询时的快照，不是资源预约，也不能保证 PaaS 立即调度。

## 作为 Skill 安装

仓库根目录就是技能目录，入口为 [SKILL.md](SKILL.md)。将完整目录放入助手使用的技能目录，并保持文件夹名为 `matpool-gpu`。例如，使用本项目原有的 Codex 技能路径：

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/quziang/matpool-gpu.git ~/.codex/skills/matpool-gpu
```

如果目标目录已存在，先保留你的本地修改，不要直接覆盖。让客户端重新加载技能后，可以这样提问：

> 使用 $matpool-gpu 查询 A2000 的当前库存和小时价格，先不要租机。

> 使用 $matpool-gpu 为我的 PyTorch 项目准备单卡 GPU 运行方案，列出镜像、预计费用和结果保存路径。

> 使用 $matpool-gpu 检查我指定的实例状态，并在确认结果已保存后释放它。

支持 `SKILL.md` 的其他助手也可按其技能加载方式使用本仓库；不同客户端的安装路径和调用方式可能不同。

## 认证：选对 Token

| 操作 | 服务 | 凭证来源 | 脚本读取方式 |
| --- | --- | --- | --- |
| 公共库存 | `matgo.cn` | 无 | 不发送认证信息 |
| 官网镜像和实例 | `matgo.cn/api` | 该站点的网页登录会话 | `--token-file` 或 `MATPOOL_WEB_TOKEN` |
| PaaS 任务 | `paas.matpool.com` | 平台开通的 PaaS Token | `--token-file` 或 `MATPOOL_PAAS_TOKEN` |

请将凭证配置在本机私密文件或环境中，无需发给 AI、写进仓库或粘贴到 Issue。`--token-file` 读取的是 Token 本身，不包含 `Bearer ` 前缀。文件权限建议设为 `0600`。

如果你明确选择复用本机 Chrome 登录态，可在 macOS 上手动运行以下可选工具：

```bash
python3 scripts/import_chrome_session.py \
  --output-dir "$HOME/.config/matpool-private"
```

该脚本读取当前 Chrome profile 中 `.matgo.cn` 和 `.matpool.com` 的 `matpool_token`，使用系统钥匙串解密，只保存这两个站点的凭证，不打印值、不覆盖已有文件。它不会在安装或其他命令中自动运行。格式不支持时不要把整个浏览器配置目录导出。具体限制见 [官网 API 文档](references/web-api.md)。

## 官网实例工作流

以下命令在仓库根目录运行。`VERIFIED_POOL_ID`、`NODE_ID` 必须替换为查询获得的值。

```bash
# 查当前资源池可用镜像
python3 scripts/matpool_web.py \
  --token-file "$HOME/.config/matpool-private/matgo-web.token" \
  images --pool VERIFIED_POOL_ID --keyword Pytorch

# 查自己的实例
python3 scripts/matpool_web.py \
  --token-file "$HOME/.config/matpool-private/matgo-web.token" nodes

# 本地预览：示例的 image_id=0 故意无效，请先替换为查询值
cp examples/rent.example.json rent.local.json
# 编辑 rent.local.json 中的资源池、镜像和配置
python3 scripts/matpool_web.py rent --file rent.local.json
```

确认配置、预算与授权后，才执行租机。建议用 `--output` 保存完整响应，文件必须尚不存在，其父目录必须已存在：

```bash
python3 scripts/matpool_web.py \
  --token-file "$HOME/.config/matpool-private/matgo-web.token" \
  --output "$HOME/.config/matpool-private/create-response.json" \
  rent --file rent.local.json --execute
```

保存返回的内部实例 ID，再用 `get NODE_ID` 查询运行状态。**结束训练、关闭终端和启动命令退出，都不等于释放官网实例。** 结果已取回且允许释放时：

```bash
# 不带 --execute 时仅预览
python3 scripts/matpool_web.py release NODE_ID

python3 scripts/matpool_web.py \
  --token-file "$HOME/.config/matpool-private/matgo-web.token" \
  release NODE_ID --execute

python3 scripts/matpool_web.py \
  --token-file "$HOME/.config/matpool-private/matgo-web.token" get NODE_ID
```

按历史验证的官网状态语义，需确认终态 `4`；释放请求成功不等于已经停止计费。官网内部数字 ID、网页 `displayID` 和 PaaS 任务 ID 有不同用途，见 [官网 API 参考](references/web-api.md)。

## PaaS 批任务

PaaS 适合运行前台命令并跟踪任务状态。使用前需取得独立 PaaS 权限。

```bash
python3 scripts/matpool_api.py \
  --token-file "$HOME/.config/matpool-private/paas.token" stats

cp examples/job.example.json job.local.json
# 替换镜像 ID、GPU 完整型号、区域、命令及本次运行备注
python3 scripts/matpool_api.py create --file job.local.json

# 已确认配置与费用后提交
python3 scripts/matpool_api.py \
  --token-file "$HOME/.config/matpool-private/paas.token" \
  create --file job.local.json --execute
```

任务查询使用 `get TASK_ID`，取消使用 `cancel TASK_ID --execute`。`TASK_ID` 是 API 内部数字 ID。获取队列 ID 不代表训练成功，状态历史也不等于训练 stdout。完整字段、状态差异和查重要求见 [PaaS 参考](references/paas-api.md)。

## PyTorch 与结果保存

```bash
# 在已连接的 GPU 实例上运行；实例需已有 PyTorch
python3 scripts/torch_check.py --output torch-result.json

# 在本地生成短启动命令，不会自动上传或租机
python3 scripts/make_torch_startup.py --result-file torch-result.json > startup.sh
```

`torch_check.py` 查找解释器，执行 GPU 矩阵乘法并与 CPU 结果比较。短启动命令适配官网客户端的 1024 字节限制，并临时通过 8895 端口提供结果文件；端口配置、访问认证和清理步骤见 [PyTorch 指南](references/pytorch.md)。临时 HTTP 服务退出后仍须核实平台释放状态。

网盘与实例必须同区；使用前检查实际挂载。将 checkpoint、日志和退出状态保存到确认过的持久目录，或在释放前取回。

## 隐私与使用边界

- 仓库只包含通用代码、操作说明和虚构占位示例，不包含登录 Token、Cookie、SSH 私钥、真实实例编号或账户原始响应。
- API 客户端使用 HTTPS，并拒绝自动跟随重定向。官网 stdout 为字段白名单摘要；PaaS stdout 会隐藏已知敏感字段，但不能保证识别未来所有服务端字段，分享前仍应检查。
- `--output` 新建权限为 `0600` 的完整响应文件。它可能包含连接密码或带 Token 的 URL，请保存在仓库外，勿上传日志全文。
- `.gitignore` 排除常见凭证、`.env`、本地请求、日志和缓存；它不能代替发布前审查。
- 本项目不会配置 MT Switch 模型代理，也不附带矩池云账户、余额或可用 GPU。

## 验证与已知限制

历史平台验证日期为 **2026-09-07**，不是持续可用性承诺。

| 范围 | 验证情况 |
| --- | --- |
| 公共库存 | 已查询并核对市场字段 |
| 官网流程 | 已验证镜像查询、创建、CUDA 运算、结果取回与释放终态 |
| PaaS | 已验证认证、创建、查询与取消；未验证完整训练成功及自动释放链路 |
| SSH / Jupyter | 有操作指引，尚未验证完整成功链路 |
| 当前版本 | 仓库提供离线测试；不在 CI 中租用 GPU 或访问账户 |

价格、库存、镜像和接口结构须以实际使用时为准。官网 API 不是稳定公开契约；遇到变化应重新核对，不猜字段或自动重复下单。

## 仓库结构与开发

```text
SKILL.md          AI 助手的技能入口
agents/           技能显示名称与默认提示
scripts/          库存、官网、PaaS 和 CUDA 辅助脚本
references/       API 字段、状态语义与运行指引
examples/         不含凭证、默认无法直接提交的请求示例
tests/            不连接外部服务的回归测试
```

```bash
python3 -m unittest discover -s tests -v
```

欢迎提交接口变化、兼容性修复和经过脱敏的复现步骤。提交 Issue 或 PR 前，请移除 Token、Cookie、带认证参数的 URL、账户/实例信息、私有数据路径和完整 API 响应。请勿为测试而自动创建付费资源。

官方入口：[GPU 市场](https://matgo.cn/host-market/gpu) · [平台教程](https://matgo.cn/supports/doc-quick-start/) · [PaaS API](https://apidoc.matpool.com/)

## License

[MIT](LICENSE)。第三方平台名称和商标归各自所有者，本项目与平台无官方关联。
