# Windows 操作

## Python、路径与认证

使用已安装的 Python 3.9+。先用 `Get-Command python, py -ErrorAction SilentlyContinue` 确认入口；选择可用的 `python` 或 `py -3`，不要假定存在 `python3`、Bash 或 rsync。在实际技能目录运行：

```powershell
$env:PYTHONUTF8 = '1'
python scripts/matpool_inventory.py --gpu A100
python scripts/matpool_auth.py status
```

公开库存不需要 Token。若任务允许浏览器、用户已登录且仅缺 API 凭证，可直接复用授权浏览器完成租机，不必先让用户导出 Token。只有任务必须使用 API 时才按 [setup.md](setup.md) 配置对应服务。用户在自己的交互终端执行 `python scripts/matpool_auth.py init --service web` 隐藏输入；已有明确授权的文件或环境变量可直接导入。不要把 Token 写进聊天、命令行字面参数或仓库。

`import_chrome_session.py` 仅支持 macOS；Windows 会在创建目录或访问浏览器前退出。本技能不实现 Windows Chrome/Edge Cookie 解密，不尝试绕过 App-Bound Encryption。登录态可用于授权浏览器 UI，不等于 API 客户端已配置。

默认路径仍为 `$HOME/.config/matpool-gpu`。Windows 新建凭据目录、凭据文件及完整响应文件时使用受保护 DACL，仅当前用户拥有完整访问权，禁止继承父目录的宽泛权限；不依赖 `chmod(0600)`。使用支持持久 ACL 的磁盘（例如 NTFS）；不支持时直接失败，不退回明文无权限保护。现有目录不更改 ACL，文件仍在创建时设定自己的保护。管理员/备份特权不属于该保护的隔离边界。POSIX 保留目录 0700、文件 0600。

输入 Token/JSON 支持 UTF-8（有或无 BOM），输出为 UTF-8 无 BOM。Windows PowerShell 5.1 的 `Out-File` 默认 UTF-16，不能用于这些输入；使用 `Set-Content -Encoding UTF8`，或显式编码写入。路径有中文和空格时应加引号。执行带空格的解释器路径需调用运算符：`& 'C:\Path With Spaces\python.exe' scripts/matpool_auth.py status`。

## 已登录网页操作

继续使用用户指定的浏览器/标签页。选择区域、GPU、卡数、驱动、计费和镜像后，读取实际选中值及订单汇总；以当前报价为准。账户余额、算力豆、优惠券是否抵扣需在结算说明中核实，不能只凭余额为零推断必须充值。

若元素点击落到了其他区域或横幅：先读取新页面状态，确认绑定的标签仍存在；使用当前截图和浏览器工具支持的坐标或键盘操作，并逐步验证选中值。不要重复相同错位点击，不要用下单按钮测试定位。只有能可靠识别最终订单后才提交。临时修改过视口时，在结束前恢复。此排查用于实际错位，不假定所有 Windows 浏览器都有该问题。

## 上传与远端执行

先完成部署包和依赖清单，再开始付费租赁。原生 OpenSSH 可通过 `Get-Command ssh, scp -ErrorAction SilentlyContinue` 检查；从实例页面读取真实主机/端口/用户，不硬编码旧连接信息。使用本机 SSH/SCP 或授权浏览器上传，保留主机密钥验证。SCP 上传本机文件时可先切换至文件所在目录，使用带引号的相对路径，避免盘符冒号被解释为远端。

发送到 Linux 的 `.sh` 使用 UTF-8 无 BOM、LF 换行；不要直接把 PowerShell here-string 当成远端 shell 命令。先上传脚本，再用实际远端解释器运行。写入经 `findmnt`/平台配置确认的持久目录，网盘与实例保持同区。关闭 PowerShell、SSH 断开或训练进程退出都不会释放实例；取回或持久保存结果后，检查平台释放终态。
