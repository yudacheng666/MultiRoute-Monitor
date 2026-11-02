# MultiRoute-Monitor｜项目状态

更新：2026-11-02

## GitHub 基线与候选
- Public 仓库：yudacheng666/MultiRoute-Monitor
- main 初始 SHA：df872495456eece3292f58db8cbc4758efa9d024（尚未合并任何产品代码）
- 开发分支：feat/m1a-local-simulation-board
- Draft PR：[M1-A #1](https://github.com/yudacheng666/MultiRoute-Monitor/pull/1)，**未合并**
- 后续真实高德计划：[M1-B Issue #2](https://github.com/yudacheng666/MultiRoute-Monitor/issues/2)
- **当前经过 CI 验证的产品/测试准确 SHA**：b2a68c794f0057dfa2779f897242670b314b525a（删除四项无用统计）
- 早期基线 CI SHA：424775dd7a4952f920c4a6d6cd2fa3216f4d3405，详见下方历史证据
- 本状态文件为测试完成后的 Markdown-only 记录；如分支新增文档提交，不得把其 SHA 冒称上面的受测产品 SHA。

## M1-A 代码已实现（模拟模式）
- Python 标准库 HTTP 服务，仅 127.0.0.1，静态文件白名单、Host 检查、CSP、无写入 API。
- 四个虚构示例小窗，模拟 ETA、延误、拥堵分段和**非地理**路线示意线。
- 独立路线增/改/删、刷新单条/全部、10 分钟默认自动刷新、5/10/15/30 分钟选择、暂停与恢复。
- 路线名称/端点和刷新偏好保存在当前浏览器 localStorage；无交通历史。
- 始终可见模拟模式/非真实路况，既不访问外部 API，也没有 Key、CDN 或网络地图底图。

## 测试证据（精确产品 SHA 424775dd...）
[GitHub Actions #41429604483](https://github.com/yudacheng666/MultiRoute-Monitor/actions/runs/41429604483)：**3/3 jobs SUCCESS**。
- Ubuntu GitHub-hosted：Python 6/6 PASS；Node 6/6 PASS。
- Windows GitHub-hosted：Python 6/6 PASS；Node 6/6 PASS。
- Ubuntu 真 Chromium：单条浏览器 E2E 流程 PASS（四卡、多次刷新、XSS 文本安全、本地路由增/改/删、刷新持久性、调整间隔、暂停恢复、390px 窄屏无横向溢出、无外网请求）。
- 2026-11-02 通过 GitHub 作业日志复核，以上结果不外推至真实高德接口。

## 未测试 / 未交付 / 阻塞
- **真实高德地图、道路路线、实时交通 ETA/TMC：NOT IMPLEMENTED / NOT TESTED**。
- **用户自己的 Windows 电脑安装/实测：NOT TESTED / NOT DEPLOYED**（CI Windows Runner 不等于公司/个人电脑）。
- 浏览器 5/10 分钟真实定时器长周期计时精度：NOT TESTED；小窗上限 6 的整条 UI E2E 路径尚未专项覆盖（核心边界逻辑有代码与部分单元验证）。
- 高德账户 Key、免费配额、QPS、用途授权以及数据服务合规尚未从用户账号验证。
- 未联系真实个人地理位置；没有公开或保存真实路线。

## 端口冲突修正（2026-11-02）
- 用户报告 8765 是 SRM 端口，不能给 MultiRoute-Monitor 默认使用。
- 修正默认端口为 8876，文档与回归测试同步更新；`python app.py --port 8876` 对先前下载版本同样有效。
- 修正产品 SHA：`70a12033f36d652bde9e8fbd68eaaafde1a12fc6`。
- [GitHub Actions #41448185794](https://github.com/yudacheng666/MultiRoute-Monitor/actions/runs/41448185794)：**3/3 SUCCESS**。Windows Python 7 PASS + Node 6 PASS；Ubuntu Python 7 PASS + Node 6 PASS；Ubuntu 真 Chromium E2E PASS。
- 此修正的测试已在精确产品 SHA `70a12033...` 完成，不能把不同 SHA 的旧 PASS 当作新提交证据。
- 用户 Windows 本机 8876 是否空闲及启动结果：NOT TESTED。

## 下一步
1. 用户在本机从当前分支的 README 启动模拟页面，体验 4 条小窗并反馈 UI；必要时只补 UI 差异定向测试，不重复相同 SHA 的全量 CI。
2. 用户明确批准后，才能将 Draft PR 改为可合并并完成 main 正式合并；代码合并不等于本机升级。
3. M1-B 严格根据 Issue #2 的授权/零费用/Key 安全门槛启动单独分支，不在 M1-A 中偷偷启用任何真实调用。

## M1-A UI 用户反馈与修正（2026-11-02）
- 用户已在 Windows 8876 打开页面，并指出顶部四项统计标签没有使用意义。
- 取消四项统计汇总卡片及对应运算，保留路线数量（标题角标）、模拟标识、刷新操作及每路线独立时间/路况。
- 新增浏览器定向 E2E：统计卡片不存在、路线数量角标仍正确、路线卡片首屏可见。
- [GitHub Actions #41449541037](https://github.com/yudacheng666/MultiRoute-Monitor/actions/runs/41449541037) 在产品/测试 SHA `b2a68c794f0057dfa2779f897242670b314b525a` **3/3 SUCCESS**：Windows Python 7 PASS + Node 6 PASS；Ubuntu Python 7 PASS + Node 6 PASS；Ubuntu 真 Chromium E2E PASS（新增无统计卡片与卡片首屏可见断言）。
- 本次仅 UI 小改，不影响 SRM 8765、不改变模拟/真实接口隔离；用户新版 UI 在 Windows 8876 实机复核：NOT TESTED（先前仅确认能够打开旧版页面）。
