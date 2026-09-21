# PaaS API 调用

## 来源与已核实差异

官方索引：<https://apidoc.matpool.com/llms.txt>；总览：<https://apidoc.matpool.com/>。

总览称仅支持 HTTP，但接口 OpenAPI 的 server 为 `https://paas.matpool.com`（标注为测试环境）。2026-09-07 对该 HTTPS 地址 `GET /v1/job/stats` 无 Token 探测得到 HTTP 200、`{"code":176,"msg":"check jwt token failed"}`。这仅确认 TLS 与路由可达，不能声称账户 API 已可用。保持 HTTPS；供应商若给另一个地址，核实来源后修改客户端，勿将凭证降级发到 HTTP。

总览写 PaaS Token 需联系官方开通，默认有效期一个月；使用前核实现行权限。仅通过 `Authorization: Bearer ...` 请求头传递。脚本从 `MATPOOL_PAAS_TOKEN` 环境变量或 `--token-file` 读取，不把 Token 写入技能、URL、命令参数或输出。用户在本机配置凭证即可，无需粘贴到对话。脚本不读取浏览器 Cookie。

## 接口表

| 操作 | 方法与路径 | 参数 | 官方文档 |
|---|---|---|---|
| 创建 | POST `/v1/job` | multipart/form-data | [创建](https://apidoc.matpool.com/api-281356330.md) |
| 单个详情 | GET `/v1/job` | `id`，API 内部 ID | [详情](https://apidoc.matpool.com/api-281356331.md) |
| 状态统计 | GET `/v1/job/stats` | 无 | [统计](https://apidoc.matpool.com/api-281356333.md) |
| 列表详情 | GET `/v1/job/jobs` | `page`, `per_page`, `order` | [列表](https://apidoc.matpool.com/api-281356334.md) |
| 取消 | DELETE `/v1/job` | `id` | [取消](https://apidoc.matpool.com/api-281356335.md) |

`order=false` 创建时间倒序，`true` 正序；列表在 `job` 数组，分页在 `pagination`。脚本一次返回一页，需要全部任务时根据 `pagination.numPages` 翻页。

所有操作同时检查 HTTP 状态和 JSON `code`，仅 `code=0` 成功。错误码包括 1、6、7 和示例中的 176，不能只识别一种鉴权错误。

## 创建字段

- `spec`：JSON 字符串，如 `{"gpuName":"NVIDIA A16"}`。完整 GPU 名需与平台匹配，文档未明确多卡请求字段，不推测。
- `agent_domain`：必需整数区域 ID。**1 区为 0**，2 区为 2，3 区为 3；其它区域尤其亚太区须确认，不能机械转换页面区号。
- `from_image_id` / `from_snapshot_id`：二选一正整数。镜像 ID 由平台提供，环境 ID 来自同账户环境列表，不借用教程示例 ID。
- `cmd`：由 `bash -c` 执行并覆盖镜像入口，命令结束实例自动释放。明确工作目录、前台运行、日志和退出码保存；不为常驻套上 `tail -f /dev/null`。
- `envs`：可选，`KEY=value;KEY2=value2`，不是 JSON。
- `remark`：实例和任务备注。用项目名和本次运行标记便于查重。
- `domain`：`all` 不过滤，`offical` 有网盘，`others` 无网盘。**`offical` 是官方拼写**。依赖网盘时使用它并核对区域。
- `ports`：JSON 数组字符串，每项如 `{"port":22,"protocol":1}`。协议 1=SSH、2=HTTP、3=VNC、4=RDP。不需远程服务就省略或 `[]`，只按授权需求开放端口。

## 辅助脚本

路径以技能目录为基准。Python 3 标准库，无需安装官方 CLI。准备 `job.json`，内容为上述字段的 JSON 对象；`spec` 也可写对象、`ports` 也可写数组，自动转表单字符串。

```bash
python3 scripts/matpool_api.py --help
python3 scripts/matpool_api.py probe
python3 scripts/matpool_api.py stats
python3 scripts/matpool_api.py list --page 1 --per-page 20
python3 scripts/matpool_api.py get 123456
python3 scripts/matpool_api.py create --file job.json
python3 scripts/matpool_api.py create --file job.json --execute
python3 scripts/matpool_api.py cancel 123456
python3 scripts/matpool_api.py cancel 123456 --execute
```

`probe` 不带凭证，鉴权失败是预期，并以非零退出码表示未认证。创建和取消默认预览；`--execute` 防误操作，不代替用户授权。创建要求明确 cmd、remark、区域和一个镜像/环境 ID，这是客户端约束，并非全是官方必填项。

脚本输出默认隐藏凭证字段、命令、环境变量和访问 URL；需要完整响应时使用全局参数 `--output PRIVATE_PATH`，新建权限 0600 文件，拒绝覆盖。该文件可能有密码，按需局部读取，不粘贴整份。

## 状态和结束条件

详情文档：1 排队、2 已调度、3 运行中（计费）、4 已完成、5 取消中、6 初始化中。创建文档把 6 写成排队，与详情不一致；保留原始值，以详情/平台信息复核。排队可能因资源、余额、镜像不存在或权限不足，不能单凭排队认定缺卡。

`job.id` 是 API 内部数字 ID，`displayID` 是网页展示 ID，`ctx.nodeDisplayID` 是实例展示 ID，不可混用。创建后记录这些 ID；超时或响应异常先列表查重，不自动重发 POST。

按任务耗时合理间隔查询。`state.log` 是状态历史，不是训练 stdout；用持久化任务日志和产物验收。取消 `code=0` 只表示请求成功，继续查详情及平台计费状态，不推测取消终态。命令结束自动释放仍需在真实任务上验证。

## 真实调用补充（2026-09-07）

- PaaS Token 实测可查询和创建任务；同一个 Token 调用网站 `/api/images` 被拒绝，不能当成网页登录授权。
- 553 字节入口命令返回 `code=6, param illegal`，仅将入口缩短为已接受的 218 字节后成功。较早 2996 字节命令同样失败。推测有长度或内容约束，但未证实准确上限；不为验证上限批量创建任务。优先用短启动命令运行预先上传的脚本。
- 创建返回状态 6 后进入 1；取消排队任务返回成功后先为 5，约几十秒后变为 4。状态历史可确认有无进入 3，但实际账单仍应从平台核对。
