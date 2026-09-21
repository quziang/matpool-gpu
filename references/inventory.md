# 实时 GPU 库存

2026-09-07 从官网公开客户端代码确认并实测：

`GET https://matgo.cn/api/machine_pools?machine_category=0&page=1&per_page=100`

这是官网市场接口，不是公开 PaaS 文档列出的稳定契约，结构变化时重新核对。查询无需 Token，避免额外发送凭证。GPU 类型编码是整数 `0`，字符串 `gpu` 会报类型转换错误。

```bash
python3 scripts/matpool_inventory.py
python3 scripts/matpool_inventory.py --gpu A2000 --domain 0
```

响应有 `pools` 和 `pagination`，可能没有 `code`；不能因此误判失败。分页键为 `num_pages`，不是 PaaS 列表的 `numPages`。

- `gpu_model`：完整名称，用于 PaaS `spec.gpuName`，例如 `NVIDIA RTX A2000`。
- `domain`：区域 ID；1 区对应 0。
- `driver_version`：资源池驱动版本。
- `max_available_units`：该资源池的当前可租份数，**不是预约或资源锁定**。不要用总卡数 `total` 当作空余量。
- `resource_pool_id`：资源池标识。保留原值，不自行构造。公开 PaaS 创建文档未列出该字段，不擅自塞入请求。
- `machine`：代表机器与配置。`hardware.discountPriceMillicent / 100000` 为折扣后的元/小时/份；缺少折扣字段时看 `priceMillicent`。历史测试曾与网页报价交叉核实；当前价格以实时查询与订单为准。

租机前过滤完整型号、区域和所需配置，确认可用份数大于等于请求数量。数量会变化，创建返回资源不足时刷新库存后再决定；纯 API 流程不需要操作网页才能查询。

**库存空余不保证 PaaS 能启动**：历史测试中市场有空余，但 PaaS 仍停留在排队状态、没有实例 ID。余额、镜像权限、驱动兼容性或队列调度等可能影响启动，接口未返回原因时不能断定是哪一个。不要继续靠换卡或重复建任务来试错；先通过官网 API 查镜像/账号条件，见 web-api.md。队列任务也要取消并查到终态，避免未来意外启动。
