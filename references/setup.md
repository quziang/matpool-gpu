# Agent 安装与 Token 初始化

用于首次安装、本机配置和认证失效恢复。凭证不进入聊天、命令行字面参数、仓库或测试日志。

Windows/Powershell 命令与权限见 [windows.md](windows.md)；以下 `python3` 在 Windows 替换为已确认可用的 `python` 或 `py -3`。

## 安装

1. 检查当前客户端支持的技能路径、Python 3.9+ 和 Git。仓库为 <https://github.com/quziang/matpool-gpu>，根目录含 `SKILL.md`，安装目录名用 `matpool-gpu`。Codex 可使用已有的 skill-installer；手动路径参照 [官方文档](https://learn.chatgpt.com/docs/build-skills)，当前用户级路径为 `~/.agents/skills/`。其他客户端按自己的规则安装。
2. 已有同名安装时核对实际加载路径、来源和本地修改。已有 `~/.codex/skills/` 等可识别安装时沿用，不创建重复副本。Git 安装可在工作区干净、来源匹配时快进更新；非 Git 副本或有修改时先保留改动，不用强制重置覆盖。
3. 在技能目录运行 `python3 scripts/matpool_inventory.py --gpu A2000` 和 `python3 scripts/matpool_auth.py status`。库存可因网络失败，此时明确报告，不误称安装或认证成功。Codex 通常自动发现技能，未显示时让用户重启；安装结果报告实际路径和验证情况。

## 按需初始化

- 只查询库存：不要求 Token，完成公开查询即可。
- 官网实例：配置 `web`，来自 matgo.cn 登录会话。
- PaaS 批任务：配置 `paas`，需向矩池云官方单独申请。不要拿网页登录 Token 或模型 API Key 替代。

先检查 `status`。已有配置时运行对应 `check`，通过就直接复用，无需再次初始化。`check` 仅发送固定 HTTPS GET：官网 `/api/nodes` 或 PaaS `/v1/job/stats`；不会创建或取消资源。HTTP 成功且业务 code 为整数 0 才算通过。

缺少 API 配置但任务已允许使用登录后的浏览器时，可直接按 [console.md](console.md) 操作，无需先导出凭证。必须使用 API 时，使用以下一种方式：

- 用户在自己的终端运行 `python3 scripts/matpool_auth.py init --service web`（或 `paas`），隐藏输入 Token。非交互环境拒绝回退到明文输入；Agent 应提供实际技能目录和命令，等待用户在本机完成，不在聊天收集凭证。
- 已有对应环境变量：`python3 scripts/matpool_auth.py init --service web --from-env`。
- 用户指定私密文件：`python3 scripts/matpool_auth.py init --service paas --token-file /absolute/private/paas.token`。
- 用户选择且已授权 Chrome 复用：按 [web-api.md](web-api.md) 运行导入器，输出到 `~/.config/matpool-gpu`。不要在一般安装中默认读取浏览器；不支持时回到终端或文件方式，不扩展读取其他浏览器。

`init` 不联网、不自动导入浏览器，保存后 `verified` 为 false。随后执行 `python3 scripts/matpool_auth.py check --service web`（或 `paas`）；只向用户报告服务、凭证来源和是否通过，不展示原始响应或凭证。初始化不创建付费资源。

## 保存、优先级与更新

默认目录为 `~/.config/matpool-gpu`，文件为 `matgo-web.token` / `paas.token`。POSIX 目录 0700、文件 0600；Windows 创建时使用仅当前用户的受保护 DACL，见 windows.md。两种服务分别保存。目录可用 `MATPOOL_CONFIG_DIR` 指定；初始化工具支持 `--config-dir PATH`，位于子命令前。只给初始化传自定义目录时，后续客户端还需同一环境变量或显式 `--token-file`。

客户端读取顺序为显式文件、对应环境变量、初始化文件。空或非法的显式来源不触发回退；`status`/`check` 展示实际选中来源。旧目录不自动扫描，需用户指定文件后导入。

文件已存在时默认拒绝覆盖；用户更换或续期 Token 时，用相同 `init` 加 `--replace`，仅原子替换所选服务。更新后重新 `check`。若环境变量仍在生效，明确提示它会覆盖文件选择；要改用文件应取消该环境变量。网络故障不等同 Token 失效；业务拒绝也可能是凭证类型或权限问题，不自动改用另一服务或重复下单探测。
