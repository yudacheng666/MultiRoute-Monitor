# M1-B｜高德真实接入的合法性与零预算门禁

文档核查日期：2026-11-02。

官方原始资料：
- https://lbs.amap.com/api/webservice/guide/api/newroute （驾车路径规划 2.0，字段 cost / tmcs / polyline）
- https://lbs.amap.com/faq/account/certification/39670 （个人认证开发者基础日配额参考）
- https://lbs.amap.com/api/javascript-api-v2/guide/abc/jscode （高德 JS API 安全码与代理）
- https://lbs.amap.com/pages/terms （使用范围、展示与 API 封装等限制）

## 以下条件缺一不可
1. **用户已于2026-11-02确认：完全个人使用、不用于公司业务**。但高德协议第3.1条针对自然人的免费条款限定“个人研究学习目的”；仅非商业个人使用不自动等于该条款下的所有用途均获授权。若用于长期个人日常通勤而非研究学习，应先向官方确认适用范围，再启用真实请求。
2. 在高德控制台核查本人：Web 服务 API Key 的驾车路径规划 2.0 权限、TMC 字段免费可用性、实际月剩余额度/QPS、地图 JS API 初始化配额及超限计费风险。2026官方基础服务计费表显示个人认证账户参考额度：**驾车规划150,000次/月、JS地图初始化1,500,000次/月**，另一FAQ列驾车5,000次/日；不能把月配额、日配额和地图初始化当成同一额度池，也不能将参考数当作当前账户保证。依据：https://lbs.amap.com/pages/base_service_price 和 https://lbs.amap.com/faq/account/certification/39670 。
3. 严格0元原则：不能确保不会计费就绝不启用真实调用；应用程序的100次/日默认上限不含共享 Key 的其他调用。
4. 高德协议对独立使用/再包装地图服务数据、复制或存储相关内容有特别限制。当前 SVG 道路线形仅为技术候选，未经明确许可不能声称已经满足地图展示合规要求。
5. 高德 JS API 2.0 正式底图及安全密钥服务端代理的**候选代码已实现**，但仍未用真实 Key 在Windows实测或核实全部地图资源可用性；地图自带的版权标识不得遮盖，按需加载需符合协议。
6. 用户本人在本地设置 Web Key，不发送给聊天机器人、GitHub 仓库或测试报告。CI 不使用真实 Key，不访问高德。

## 用户仅需完成的安全密钥本地配置
- 在高德“Web端（JS API）” Key 对应记录中找到 securityJsCode 安全密钥（与 JS Key 配对，不是第三个 Key）。
- 下载候选 ZIP 后在项目目录运行 `python setup_amap.py`，按提示输入两枚已有 Key 和该安全密钥。无需安装 Nginx，程序自身包含后端代理。不把 Key 发到聊天。
- 脚本保存文件不会开启实时调用；须经许可、免费额度与收费风险确认后，才由本人对真实模式作独立授权。

## 当前候选安全控制
- 默认全部关闭；同时具备四项条件才会启用：MRM_AMAP_WEB_KEY、MRM_USAGE_AUTHORIZED=YES、MRM_FREE_QUOTA_VERIFIED=YES、MRM_EXPLICIT_LIVE_OPT_IN=YES。
- 只监听127.0.0.1，默认端口8876；POST 本机同源 Origin + JSON + 自定义请求头，阻止普通跨站发请求。
- 固定 Web 服务 HTTPS 主机 restapi.amap.com，不跟随重定向，最多1MB响应、8秒超时。
- 同线路5分钟冷却、全局2秒、每日默认100次应用硬配额且最高1000次；先持久化尝试次数再发网络请求，失败也计数。
- 仅浏览器本地保存用户填写的地点/经纬度。服务端只存当天请求次数，不存交通数据、路线几何、响应体或历史。
- 高德真实请求永远只在用户点击相应路线手动查询后才可能发生；模拟自动刷新不访问高德。
- 额外启用官方地图需本机配置 MRM_AMAP_JS_KEY（Web端JS API公开Key）、MRM_AMAP_JS_SECURITY（安全码，仅后端保存）、MRM_AMAP_MAP_OPT_IN=YES，且真实Web服务查询先已获授权。`/_AMapService` 为同源限制代理，固定转发至高德服务端，仅允许预设路径，拒绝自定义jscode和任意外部URL；另设置本应用每日最多500次地图代理请求。JS地图脚本及底图只在用户取得路线响应后再次主动点击“查看高德地图”才加载。该代理调用限额不等同于高德地图图面初始化的供应商配额。
- 本地模拟 CI 使用虚构样例坐标与响应，不代表已取得高德数据授权。

## 正式 M1-B 验收前仍缺
- [x] 用户确认仅个人使用、无公司业务；[ ] 核实高德协议“个人研究学习”条款是否覆盖实际用途。
- [ ] 账户配额及超额计费风险实测与控制台证据（隐藏密钥）。
- [x] 官方 JS API 2.0 按需加载器及安全码代理的候选实现；[ ] 用真实合法账号验证地图资源、白名单请求和版权展示。
- [ ] 小额度真实接口，确认 response 结构、路线形状、TMC 颜色及路径规划语义。
- [ ] 用户 Windows 本机功能与费用验收。
- [ ] PR #3 通过准确 SHA CI、用户审批后才能合并 main。


## 2026-11-08｜代理路由与集成验收
- 按高德官方 JS API 2.0 安全密钥文档，地图样式 /v4/map/styles 单独固定转发 webapi.amap.com，其他允许的 /v3/*、/v4/* Web Service 路径固定转发 restapi.amap.com。不接受客户端指定上游。
- /_AMapService/ 请求仅 GET；本机 host 校验、Sec-Fetch-Site 跨站阻断、代理调用日上限、服务端注入 jscode、不跟随重定向、8秒超时、响应 1MB 上限和 MIME 白名单。
- 代理的完整 HTTP 路由测试使用假网关和 mock 上游，不会触发真实请求。真实地图资源/版权/Key域名白名单尚未验收。
- CI SHA 5a192a4dba94e4e92a1e4b7ca40dd93e1d0b7e19：Windows/Ubuntu Python 45/45 + Node 10/10，Chromium E2E 通过；Actions #42450312426 3/3 SUCCESS。
