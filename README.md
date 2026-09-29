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

## 安装：推荐交给 Agent

把下面这段话发给你使用的 AI 编程助手，让 Agent 完成安装并引导初始化：

```text
请安装 https://github.com/quziang/matpool-gpu 这个 skill。
先阅读 README.md 和 SKILL.md，按当前客户端支持的技能目录安装，
已有同名技能时先检查来源和本地修改，避免覆盖或重复安装。
安装后运行公开库存查询及 matpool_auth.py status，并按我的使用场景引导 Token 初始化。
Token 只在本机终端、私密文件或环境变量中配置，不要让我粘贴到聊天。
这次只安装和验证，不租用 GPU、不提交任务。
```

在 Codex 中，也可以直接说：

> 使用 $skill-installer 安装 https://github.com/quziang/matpool-gpu，技能位于仓库根目录，安装名为 matpool-gpu；然后按照 README 引导我初始化认证。

Agent 的具体步骤见 [安装与初始化指引](references/setup.md)。安装完成后可说：

> 使用 $matpool-gpu 查询 A2000 当前库存和小时价格。

### 手动安装（可选）

本地需要 **Python 3.9+** 和 Git。核心脚本只依赖 Python 标准库，无需 `pip install`。
仓库根目录就是技能目录；以下按 [Codex 官方技能文档](https://learn.chatgpt.com/docs/build-skills) 的用户级路径安装：

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/quziang/matpool-gpu.git ~/.agents/skills/matpool-gpu
cd ~/.agents/skills/matpool-gpu
```

其他 Agent 使用各自支持的技能目录。已有 `~/.codex/skills/matpool-gpu` 等安装时沿用当前客户端识别的路径，先保留本地修改，不要再装一份同名技能。Codex 会自动发现技能；若未显示，重启客户端。

## 快速验证：无需 Token

以下命令均在技能目录运行。它们不会创建付费资源；库存查询会访问公开接口，`status` 只检查本机配置。

```bash
# 无需登录，不会租机
python3 scripts/matpool_inventory.py --gpu A2000
python3 scripts/matpool_auth.py status
```

输出包含查询时间、完整 GPU 名称、`resource_pool_id`、可用份数、驱动与 `hourly_cny_per_unit`。库存是查询时的快照，不是资源预约，也不能保证 PaaS 立即调度。

## Token 初始化：按需配置一次

| 操作 | 服务 | 凭证来源 | 脚本读取方式 |
| --- | --- | --- | --- |
| 公共库存 | `matgo.cn` | 无 | 不发送认证信息 |
| 官网镜像和实例 | `matgo.cn/api` | 该站点的网页登录会话 | 初始化文件、`MATPOOL_WEB_TOKEN` 或 `--token-file` |
| PaaS 任务 | `paas.matpool.com` | 平台开通的 PaaS Token | 初始化文件、`MATPOOL_PAAS_TOKEN` 或 `--token-file` |

**只查库存可跳过认证；官网租机只需 web，PaaS 批任务才需 paas，两种 Token 不能互换。** SSH/Jupyter 使用实例自己的连接凭证，不在这里初始化。

### 1. 获取对应凭证

- **web**：登录 [矩池云官网](https://matgo.cn/)。可在本机浏览器开发者工具中查看该站点 `matpool_token` Cookie，使用 URL 解码后的值；初始化器接受 Token 本身或 `Bearer ` 前缀。也可选择下面的 Chrome 导入方式。
- **paas**：按 [矩池云官方说明](https://apidoc.matpool.com/) 联系平台开通并获取独立 PaaS Token。

在你自己的终端中运行所需的一项，按提示输入 Token（输入不回显）：

```bash
python3 scripts/matpool_auth.py init --service web
# 仅需要 PaaS 时再配置
python3 scripts/matpool_auth.py init --service paas
```

`init` 仅保存本地凭证，不联网，也不读取浏览器。Agent 无法代你输入时，应让你在自己的终端完成这一步，不把 Token 发到聊天或放进命令行参数。

### 2. 做一次只读认证检查

```bash
python3 scripts/matpool_auth.py check --service web
# 已配置 PaaS 时才运行
python3 scripts/matpool_auth.py check --service paas
```

`check` 分别查询官网实例列表或 PaaS 状态，只有 HTTP 成功且业务 `code=0` 才报告 `verified: true`；不租机、不提交任务，也不输出实例详情。`status` 的“已配置”不代表远端认证有效。网络失败、过期或权限不足时按具体服务处理，不换用另一种 Token。

### 3. 后续命令自动使用配置

默认文件是 `~/.config/matpool-gpu/matgo-web.token` 和 `~/.config/matpool-gpu/paas.token`；POSIX 目录权限 `0700`、文件 `0600`；Windows 使用仅当前用户的受保护 DACL。官网和 PaaS 客户端自动读取各自文件，无需每次传 Token。

```bash
python3 scripts/matpool_web.py nodes
python3 scripts/matpool_api.py stats
```

读取优先级：**显式 `--token-file` → 对应环境变量 → 初始化文件**。选中的来源无效会报错，不静默切换账户。`status` 和 `check` 会显示使用的来源，不显示 Token。可用 `MATPOOL_CONFIG_DIR` 改配置目录；初始化工具也支持全局 `--config-dir`（放在子命令前），后续客户端需使用同一环境变量或显式文件路径。

已有本机凭证时可由 Agent 导入；更新过期 Token 时加 `--replace`，只替换选中的服务：

```bash
# 前提：已在本机设置对应环境变量，命令中不包含 Token 值
python3 scripts/matpool_auth.py init --service web --from-env
python3 scripts/matpool_auth.py init --service paas --token-file /absolute/private/paas.token
# 在自己的终端中更新，随后重新 check
python3 scripts/matpool_auth.py init --service web --replace
```

环境变量会优先于新保存的文件；若要使用文件，先在本机取消对应环境变量。已有文件默认不覆盖；旧路径的凭证不会被自动扫描或搬迁，可用 `--token-file` 明确导入。

### 可选：复用本机 Chrome 登录态

用户已授权复用时，可在 macOS 上将限定站点凭证导入同一默认目录：

```bash
python3 scripts/import_chrome_session.py \
  --output-dir "$HOME/.config/matpool-gpu"
python3 scripts/matpool_auth.py check --service web
```

该脚本只读取当前 Chrome profile 中 `.matgo.cn` 和 `.matpool.com` 的 `matpool_token`，使用系统钥匙串解密，不打印值、不覆盖已有文件，且不会在安装或 `init` 中自动运行。官网客户端使用 `matgo-web.token`；另一个站点的文件不会冒充 PaaS Token。仅支持指定的 macOS Chrome Cookie 格式；缺少 matgo 登录态或格式不支持时，改用本机终端初始化。具体限制见 [官网 API 文档](references/web-api.md)。

## 官网实例工作流

以下命令在仓库根目录运行。`VERIFIED_POOL_ID`、`NODE_ID` 必须替换为查询获得的值。

```bash
# 查当前资源池可用镜像
python3 scripts/matpool_web.py images --pool VERIFIED_POOL_ID --keyword Pytorch

# 查自己的实例
python3 scripts/matpool_web.py nodes

# 本地预览：示例的 image_id=0 故意无效，请先替换为查询值
cp examples/rent.example.json rent.local.json
# 编辑 rent.local.json 中的资源池、镜像和配置
python3 scripts/matpool_web.py rent --file rent.local.json
```

确认配置、预算与授权后，才执行租机。建议用 `--output` 保存完整响应，文件必须尚不存在，其父目录必须已存在：

```bash
python3 scripts/matpool_web.py \
  --output "$HOME/.config/matpool-gpu/create-response.json" \
  rent --file rent.local.json --execute
```

保存返回的内部实例 ID，再用 `get NODE_ID` 查询运行状态。**结束训练、关闭终端和启动命令退出，都不等于释放官网实例。** 结果已取回且允许释放时：

```bash
# 不带 --execute 时仅预览
python3 scripts/matpool_web.py release NODE_ID

python3 scripts/matpool_web.py release NODE_ID --execute

python3 scripts/matpool_web.py get NODE_ID
```

按历史验证的官网状态语义，需确认终态 `4`；释放请求成功不等于已经停止计费。官网内部数字 ID、网页 `displayID` 和 PaaS 任务 ID 有不同用途，见 [官网 API 参考](references/web-api.md)。

## PaaS 批任务

PaaS 适合运行前台命令并跟踪任务状态。使用前需取得独立 PaaS 权限。

```bash
python3 scripts/matpool_api.py stats

cp examples/job.example.json job.local.json
# 替换镜像 ID、GPU 完整型号、区域、命令及本次运行备注
python3 scripts/matpool_api.py create --file job.local.json

# 已确认配置与费用后提交
python3 scripts/matpool_api.py create --file job.local.json --execute
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
- `--output` 新建私密完整响应文件（POSIX 0600；Windows 受保护 DACL）。它可能包含连接密码或带 Token 的 URL，请保存在仓库外，勿上传日志全文。
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
scripts/          认证初始化、库存、官网、PaaS 和 CUDA 辅助脚本
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

## Windows

支持 Windows Python 3.9+、PowerShell 和含中文/空格的路径；输入文件支持 UTF-8 BOM。凭据初始化及完整响应保存使用原生 Windows ACL，不依赖 POSIX chmod。Chrome 会话导入仍仅支持 macOS；任务允许网页操作时可复用已登录浏览器，无需导出 Token。具体命令、SSH 上传与浏览器定位排查见 [Windows 指南](references/windows.md)。离线 CI 同时覆盖 Ubuntu/Windows 和 Python 3.9/3.12；测试仅使用合成凭据，不租机。
