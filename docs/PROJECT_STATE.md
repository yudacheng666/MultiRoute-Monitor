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
- 已将时区改为标准库固定 UTC+8 时区偏移，无新依赖：修复源码 SHA a3a5f94598b05948dd2ddb3dc00605ea59605e64；后续 CI 结果需单独核实，**不能把旧 PASS 当作本 SHA 验证**。

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
