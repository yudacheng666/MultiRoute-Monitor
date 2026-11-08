# MultiRoute-Monitor｜项目状态

更新：2026-11-02

## M1-A：已发布至 main
- 用户认可四窗口布局，批准合并 PR #1。
- 已合并：https://github.com/yudacheng666/MultiRoute-Monitor/pull/1
- main 合并 SHA：bb8287f040ae6e5e83709275e5daf28e4ff4bae9（squash）。
- 原 PR 的 Windows/Ubuntu/Chromium CI PASS；用户已能在 Windows 本地 8876 打开模拟页面。
- 合并 GitHub 不等于用户机器已自动安装更新。

## M1-B：新建独立候选
- 分支：feat/m1b-amap-safe-integration；Draft PR #3。
- 已新增高德 Web Service v5 驾车数据解析、权限/配额关闭门禁、持久计数与节流、Origin/Host 检验、可选坐标输入、手动真实查询卡片和单次道路坐标 SVG。
- 默认未授权时不访问高德 API、不使用 Key；自动定时器仍只刷新模拟值。
- 尚无高德 JS API 底图，SVG 当前仅技术候选。
- 2026-11-02 首轮 CI SHA 9f8aa3394885012ec84f78d56c6eda3064138edc：Ubuntu Python/Node PASS、Ubuntu Chromium PASS；Windows Python FAIL（系统无 tzdata，ZoneInfo 不可用），定位为跨平台时区依赖。
- 已将时区改为标准库固定 UTC+8 时区偏移，无新依赖：修复产品/测试 SHA a3a5f94598b05948dd2ddb3dc00605ea59605e64；[GitHub Actions #41452266900](https://github.com/yudacheng666/MultiRoute-Monitor/actions/runs/41452266900) 3/3 SUCCESS：Windows Python19/19+Node7/7，Ubuntu Python19/19+Node7/7，Chromium E2E PASS（伪造本地高德响应）。后续仅文档提交，不改变该测试证据对应的产品 SHA。

## 阻塞 / NOT TESTED
- 本人高德账号权限/实际免费调用剩余额度/用途合法性/计费风险 NOT VERIFIED。
- 真正 API 请求/返回实测 NOT TESTED。
- 高德 JS API 2.0 地图底图、安全密钥代理 NOT IMPLEMENTED。
- 用户 Windows 本机 M1-B NOT DEPLOYED/NOT TESTED。
- 用户没有批准 M1-B 合并；main 仍为已合并的 M1-A。

## 下一步
1. 先查修复后精确 SHA 的 Windows/Linux/Chromium CI，修复失败，只做有证据缺口的增量测试。
2. 核实高德个人/商业使用授权与账号免费配额；不确认时继续模拟。
3. 加入官方高德地图底图及安全密钥服务端代理，按高德协议处理交通数据并实际对比路线。
4. 整体 M1-B 需另行用户验收合并，不自动部署至 Windows。

## 用途与高德官方地图进展（2026-11-02）
- 用户明确：**完全个人使用，不涉及公司业务**。但官方《服务协议》3.1条强调“个人研究学习”，是否适用于长期通勤实用看板仍需确认；未因此直接将许可标记 PASS。
- 高德官方计费表公开参考：个人认证驾车规划150,000次/月，JS地图初始化1,500,000次/月；另有5,000次/日旧FAQ。二者独立配额，账户实际额度/付费设置尚未核实。来源：https://lbs.amap.com/pages/base_service_price 。
- 本分支新增官方高德 JS API 地图按需加载器、同源 `/_AMapService` 服务端安全码代理、地图资源请求限额与离线测试；**仍默认完全关闭，不发送真实高德请求，不在用户本机安装**。
- 两次人工操作：先在合法授权下手动查询路线，再主动点击“查看高德地图”才尝试初始化底图；防止页面打开即初始化多个地图。
- 当前测试仅离线模拟及代理白名单，不代表高德实际地图可以在该环境中加载；地图资源兼容性/版权合规/真实配额仍 NOT TESTED。
- 后续代码需核对准确 SHA 的 Windows、Ubuntu 与 Chromium CI，保留 Draft PR #3，M1-A main 不变。

## 当前候选完整离线验收结果（2026-11-02）
- 新增官方地图按需加载器、服务器端固定域名安全码代理、单独地图代理请求日上限、伪造地图对象测试；不存在未经用户允许的自动地图初始化。
- 初次新增代理测试揭示绝对URL可绕过参数验证但上游仍固定；已修复为拒绝 `scheme/netloc/fragment` 并复测（无需真实请求）。
- **受测产品/测试准确 SHA**：`f000cb84da741fab9d9d5dc9767633771065bbab`。
- [GitHub Actions #41454859270](https://github.com/yudacheng666/MultiRoute-Monitor/actions/runs/41454859270) **3/3 SUCCESS**：Windows Python27/27与Node10/10；Ubuntu Python27/27与Node10/10；Chromium E2E PASS。
- 此证据证明离线模拟、地图绘制的伪实现断言及安全代理路径规则通过；**不代表 JS API 地图在真实账户已能成功加载，不代表使用协议和费用验收通过**。
- 用户个人非商业用途已确认；高德官方许可中“个人研究学习目的”的适用性、实际账户及免费余额仍未确认。
- PR #3 继续 Draft，main 保持 M1-A。用户 Windows 新版未部署。

## 2026-11-03 当前小步修正：地图安全代理上游
- 依据官方文档将地图样式请求固定到 `webapi.amap.com`，已允许的 Web 服务代理请求固定到 `restapi.amap.com`；保留服务端 jscode 注入、路径白名单和对绝对 URL 的拒绝。
- 新增零外网单元测试，通过 fake HTTPS 检查实际选取的上游域名、HTTPS 参数和无效 URL 提前拒绝。
- 最新提交和 CI 准确 SHA 需以 GitHub Actions 运行记录为准；仍未使用真实高德 Key 或验证实际高德地图。
- PR #3 仍为 Draft；main 不变，不部署到用户 Windows。

## 2026-11-03 用户反馈后操作简化
- 用户明确已经创建两个 Key，要求服务器代理由项目开发者实现，用户无需理解/维护 Nginx。
- 已开发 `python setup_amap.py` 本地交互向导：只输入 Web服务 Key、JS API Key 和 JS安全密钥（不是第三个 Key），隐藏终端输入，存放 `local/amap_keys.json`（仓库忽略）。
- Python 网关现在可在正常启动时读取本地私有文件；单元测试注入独立环境不会读取真实密钥。配置文件不会写任何许可或真实调用开启标志，**输入 Key 后仍完全模拟，不产生网络请求**。
- 地图安全码代理前次已开发，当前官网示例要求样式走 webapi.amap.com、其他服务走 restapi.amap.com，代码采用固定双域名且不接受用户指定任意上游。
- 该新一轮 PR 产品 SHA 和 CI 结果待按 GitHub 实际执行核验。PR #3 保持 Draft，main 仍 M1-A；用户本人需要的下一操作仅在发布 ZIP 后运行 Key 配置向导。


## 2026-11-08｜代理 HTTP 集成与跨平台回归（离线）
- 按高德 JS API 2.0 官方安全密钥文档复核代理路径：/_AMapService/v4/map/styles 固定转发 webapi.amap.com/v4/map/styles；/_AMapService/ 其余 Web Service 资源固定转发 restapi.amap.com/。官方说明：https://lbs.amap.com/api/javascript-api-v2/guide/abc/jscode 。
- 代理路径允许安全的版本化 /v3/*、/v4/* Web Service 资源，样式路径优先匹配独立上游；仍禁止 scheme/netloc/fragment、反斜线、路径穿越、编码分隔符、调用者覆盖 jscode/callback、非白名单内容类型、超限响应及重定向跟随。
- 新增实际本地 HTTP server 集成测试：启用态样式/服务请求、服务端注入 jscode、跨站拒绝、非法路径拒绝、预算拒绝、上游失败不泄密、HEAD 拒绝；测试传输全部 mock，不访问高德。
- 新增代理响应大小/Content-Length/Content-Type/redirect 测试，以及 JS API loader 在追加官方脚本前配置 same-origin serviceHost、浏览器配置不含 securityJsCode 的 Node 测试。
- 受测产品 SHA：5a192a4dba94e4e92a1e4b7ca40dd93e1d0b7e19。Actions #42450312426 3/3 SUCCESS：Windows 45 Python tests + 10 Node tests；Ubuntu 45 Python tests + 10 Node tests；Ubuntu 24.04 Chromium E2E PASS。
- 该轮前两个迭代 CI 捕获并修复了测试夹具 Content-Length 行为和旧路径白名单断言，最终 SHA 全绿。CI 全程使用虚构响应和 mock HTTPS，不触发真实高德请求。
- main 仍为 bb8287f040ae6e5e83709275e5daf28e4ff4bae9（M1-A），PR #3 仍 Draft / unmerged。真实高德账号、许可、地图底图及真实 ETA/TMC 仍未实测；不得把离线 CI PASS 说成真实地图上线。


## 最新状态覆盖（2026-11-08，优先于上述历史记录）
- M1-B 已包含官方高德 JS API 2.0 按需加载器、固定上游安全密钥代理、本地 Key 向导及实际 HTTP server 集成测试；并非“未实现”。
- 最终受测产品/测试 SHA：27622cd87e425f312992b7e7b70ba28e978f7389。
- [GitHub Actions #42450447909](https://github.com/yudacheng666/MultiRoute-Monitor/actions/runs/42450447909)：3/3 SUCCESS。Windows 45/45 Python + 11/11 Node；Ubuntu 45/45 Python + 11/11 Node；Ubuntu 24.04 Chromium E2E PASS。
- 本轮覆盖安全代理通过真实本地 HTTP handler 的路由、两类上游路径选择、后端 jscode 注入、跨站拒绝、非法路径、请求预算、上游失败、响应大小/MIME/重定向，以及浏览器加载 JS API 前设置 same-origin serviceHost。所有上游均 mock，未访问高德。
- 最终包可从 M1-B 分支 ZIP 下载。用户已在旧文件夹配置 local/amap_keys.json；ZIP 不包含此私密文件，更新时应保留原 local 文件夹/配置。
- 当前唯一尚未完成的是真实高德在线验证：个人“研究学习”许可是否适用、账户实际免费配额与超额停止机制、真实地图底图和真实路线/TMC 返回。不能在 CI 使用用户密钥，也不能在授权/零费用机制未确认时自动启用。
- PR #3 仍 Draft / 未合并；main 仍为 M1-A SHA bb8287f040ae6e5e83709275e5daf28e4ff4bae9。用户尚未批准 M1-B 合并。


## 2026-11-08｜增加月度预算与地图初始化独立硬限制
- 路线规划请求计数升级为日/月双计数，旧版 {day,count} 文件自动迁移；损坏/日期回拨/未来日期均 fail-closed。
- 默认路线 API 应用预算：1000 次/日、30,000 次/月，绝对上限同为 1000/日与30,000/月；低于高德公开个人认证驾车规划参考配额 150,000/月。实际账号剩余额度/其他应用用量仍需用户核实。
- 地图图面初始化独立计数：30 次/日、900 次/月；地图代理资源请求：500 次/日、15,000 次/月。地图每次新建实例前必须通过本机 /api/amap/map-init 预占；失败或超额时不加载地图。该应用级限制不能替代高德账号级额度。
- 新增 HTTP 集成测试覆盖地图初始化 endpoint 和默认关闭态；新增月度计数迁移、重启、损坏文件 fail-closed 测试。所有测试均离线。


## 2026-11-08｜本地授权门禁与真实路况刷新能力
- 新增网页内「高德授权设置」表单，不再要求用户手工设置环境变量。只有用户填写高德工单号、控制台驾车规划/月地图初始化剩余额度，并勾选书面许可、配额核对、账号独占使用和费用风险确认后，才在本机 `local/amap_authorization.json` 写入授权标记。
- 授权数据不含 Key/安全密钥；配置损坏、符号链接、日期计数损坏均 fail-closed。新增「停用真实接口」按钮，可写入关闭标记并即时重建网关。
- 授权表单不是对高德工单的自动验证；用户必须先收到高德书面确认。未确认时不应勾选或启用。
- 授权门禁按用户报告的剩余额度预留50%，并应用本机上限：路线规划最多1000次/日、30000次/月；地图初始化最多30次/日、900次/月；地图代理最多500次/日、15000次/月。该门禁不能限制同一开发者账号的其他应用，也不是高德账号级计费硬停止。
- 新增「高德查询全部」顺序批处理及可选真实路况自动刷新。自动真实刷新默认关闭；开启后使用所选5/10/15/30分钟间隔，在一批全部完成后再开始下一轮，避免与同路线5分钟冷却冲突。模拟刷新按钮明确命名为「刷新模拟数据」。
- 新增授权文件、HTTP 授权/停用 endpoint 和 Chromium 授权对话框测试。全部测试均为离线/mock；真实高德接口仍未被调用。


## 2026-11-08 当前交付状态（优先于前面的历史记录）
- M1-B 最新工作分支继续独立于 main；main 仍是用户已验收的 M1-A。
- 已加入网页内高德书面许可/额度确认门禁、停用按钮、应用日/月预算、地图初始化独立预算、真实路况顺序批量查询/可选自动刷新、坐标拾取器链接、Windows 一键启动脚本。
- 自动真实刷新默认关闭；用户需要明确启用，5/10/15/30分钟逐条刷新。
- 仅有 Key 不足以启用真实服务。授权门禁要求工单编号、官方书面批准确认、控制台剩余配额、账号独占使用确认；不向高德自动验证。
- 高德服务协议第3.1条仅明确自然人以“个人研究学习目的”使用基础服务可享免费配额。本项目日常路线监控是否符合该条件尚无高德书面答复；未取得许可前不得启用真实服务。
- 应用级预算：驾车规划最高1,000/日、30,000/月；地图初始化最高30/日、900/月；代理资源500/日、15,000/月；按用户报告的剩余额度再留50%缓冲。无法限制同一高德账号其他应用用量，也不是高德计费硬停止。
- 新增 .github/workflows/release.yml：只在最终 release/v* 分支推送时，重新跑 Python/Node/Chromium 全套测试，构建唯一版本 ZIP 和 SHA256，并发布 GitHub Release。当前尚未创建 release 分支，因此没有提前发布半成品。
- 最新自动化验收证据：产品 SHA 0e964a0c36fe185996552e157b60f7cd1ce5cc9f 的 Actions #42453104687 3/3 PASS；之后新增授权 UI、测试、启动器和 release workflow，需以最新 SHA 的 CI 为准。
- 不把离线 CI 通过表述为真实高德联调通过。真实地图底图、真实 ETA/TMC、实际 Key 域名白名单和账户权限仍待书面许可后进行一次本机在线验收。
