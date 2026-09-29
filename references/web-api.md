# 官网 HTTPS API

官网客户端使用的接口，不是公开 PaaS 文档的稳定契约。2026-09-07 从官网 `app.123d6e64.js`、`6674.900a5831.js`、`3163.935e28c0.js`、`8691.6e5f1581.js`、`6888.914d75a0.js` 核对方法与字段，来源前缀 `https://matgo.cn/fe-next/js/`。

## 认证分流

首次配置见 [setup.md](setup.md)：`python3 scripts/matpool_auth.py init --service web`，再运行 `check --service web`。客户端读取优先级为 `--token-file` → `MATPOOL_WEB_TOKEN` → `~/.config/matpool-gpu/matgo-web.token`；默认目录可用 `MATPOOL_CONFIG_DIR` 更改。

- 市场库存 `/api/machine_pools`：无需登录，不发 Token。
- 官网镜像、租机与实例 `https://matgo.cn/api`：用该站网页登录凭证，即 `matpool_token` Cookie 解码后去掉 `Bearer ` 前缀，作为 `Authorization: Bearer ...` 发送。
- PaaS `https://paas.matpool.com/v1/job...`：使用独立 PaaS Token，见 paas-api.md。

实测同一个 HTTPS 镜像 URL：PaaS Token 返回 HTTP 200、业务 `code=176`（check jwt token failed）；Chrome 站点 Token 返回 HTTP 200、`code=0` 和镜像列表。因此这次失败是凭证类型/适用接口不匹配，不是 HTTP/HTTPS 协议问题。HTTP 200 仅表示请求得到响应，不能代替业务成功码。不要为了排查把凭证降级发送到 HTTP。

用户授权复用本机 Chrome 登录时，在 macOS 可运行：

```bash
python3 scripts/import_chrome_session.py --output-dir /absolute/private/credentials
```

导入脚本只读取当前 Chrome profile 的 `.matgo.cn`、`.matpool.com` 的 `matpool_token`，不扫描其他站点。输出目录 0700、Token 0600，不覆盖已有文件，不打印值。依赖 macOS Chrome v10 Cookie 格式和系统钥匙串；不支持时说明具体限制，不自动改读其他浏览器或账号。凭证与原始响应放入不提交 Git 的私密目录，不能写进技能、示例、日志或聊天。

## 命令

```bash
python3 scripts/matpool_web.py --token-file /private/credentials/matgo-web.token images --pool VERIFIED_POOL_ID --keyword Pytorch
python3 scripts/matpool_web.py --token-file /private/credentials/matgo-web.token nodes
python3 scripts/matpool_web.py --token-file /private/credentials/matgo-web.token get NODE_ID
python3 scripts/matpool_web.py rent --file rent.json
python3 scripts/matpool_web.py --token-file /private/credentials/matgo-web.token --output /private/credentials/create.json rent --file rent.json --execute
python3 scripts/matpool_web.py --token-file /private/credentials/matgo-web.token release NODE_ID --execute
```

默认 stdout 只输出白名单摘要；使用 `--output` 将完整响应保存至新建私密文件（POSIX 0600；Windows 受保护 DACL）。完整响应包含连接信息，应私密保存。`rent`、`release` 没有 `--execute` 只预览；是否执行由用户现有授权决定，不强制再问确认。

已确认路由：

| 操作 | 方法和路径 | 参数位置 |
|---|---|---|
| 镜像 | GET /images | 查询 machine_category=0、resource_pool_id、page、per_page；keywords 是 JSON 字符串数组 |
| 实例列表 | GET /nodes | 查询 page、per_page、order=false（新实例优先） |
| 实例详情 | GET /node | 查询 id |
| 租用 | POST /node | JSON 对象 |
| 释放 | DELETE /node | **JSON 对象 `{"id":内部数字ID}`** |
| 账单 | GET /node/bill | 查询 request_id=displayID（与详情接口不同） |

租用最小参考对象（替换为实时查询值）：

```json
{
  "resource_pool_id": "FROM_CURRENT_INVENTORY",
  "image_id": 633955,
  "machine_category": 0,
  "hardware_qty": 1,
  "vnc_switcher": true,
  "auto_password": true,
  "c": ""
}
```

`image_id` 与 PaaS 的 `from_image_id` 不同，不能混用。示例 ID 不是长期可用性保证；需在当前池的 `/images` 列表中再次确认。镜像显示名为 `alias`，`name` 可能为空。可选 `cmd` 是启动 shell 脚本；`ports` 是 JSON 字符串，元素为 `{"srcPort":8895,"protocol":2}`。省略网盘挂载、快照、包时购买等额外功能，除非任务需要且已获授权。

`cmd` 有截断风险：3903 字符的 ASCII 脚本实测只保留了前 1024 字符。客户端限制为 1024 UTF-8 字节，超出时在请求前报错。PyTorch 环境与短测试命令见 [pytorch.md](pytorch.md)。

列表是 `userNodes`，详情是 `userNode`；数字 ID 在 `.node.id`，状态在 `.status`，不是 `.node.status`。`displayID` 是显示标识，不能作为 DELETE 的内部 ID。状态 1 启动、2 运行、3 退出、4 完成、6 释放中。不要用 `releaseTime` 是否为空判断终态，历史已完成实例该字段也可为空。

创建不自动重试：先保存响应，再查询新实例，排除重复。启动脚本退出或 HTTP 服务停止不等于实例释放；无论测试成功失败都需执行 DELETE，继续 GET 到终态 4。只释放本次明确识别的实例。无法验证终态时立即报告，不宣称停止计费。

创建成功返回 `node.id`；立即私密保存，清理流程必须绑定这个 ID。端口 URL 可能带 `?token=...`，属于连接凭证，不能打印或放进公开结果。读取子路径时用 `urllib.parse.urlsplit/urlunsplit` 修改 path 并保留 query，不能直接在整个 URL 后拼文件名。

## 历史验证范围（2026-09-07）

已验证 Chrome 登录导入、镜像和实例查询、官网 API 创建实例、CUDA 运算、结果取回及释放至终态 4。该记录不保证当前库存、价格、镜像和接口保持不变；不公开账号、实例标识、连接地址或原始响应。PyTorch 环境结论见 [pytorch.md](pytorch.md)。
