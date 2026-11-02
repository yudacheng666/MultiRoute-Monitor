# MultiRoute-Monitor｜项目状态

更新：2026-11-02

## GitHub 基线
- 仓库：yudacheng666/MultiRoute-Monitor（Public）
- 用户新建 main 初始 commit：df872495456eece3292f58db8cbc4758efa9d024
- 当前工作分支：feat/m1a-local-simulation-board
- 正式 main：只含初始 README；本阶段不得直接修改 main。

## 本阶段 M1-A
候选：本地模拟多路线看板、路线管理、自动刷新和测试。模拟与真实数据须严格分离；尚未运行高德 API。准确产品 SHA、PR、CI 及环境测试结果应在候选提交后更新。

## 未完成 / 阻塞
- 用户真实 Windows 电脑 NOT TESTED / NOT DEPLOYED。
- 用户高德 Web 服务 / JS Key NOT PROVIDED（不应提交）。
- 个人非商用还是公司业务用途 UNCONFIRMED；真实高德调用不准启用。
- 高德账户具体免费额度、按路况字段的接口等级、协议缓存限制未在本人账户实测。
- 真实道路地图和真实拥堵 ETA NOT IMPLEMENTED。

## 下一步
1. 本分支实现并测试 M1-A；通过 GitHub PR 的自动化验证。
2. 用户审阅真实浏览器视觉及 M1-A 功能，审核合并。
3. 个人非商用授权或相关服务许可确认后，单独 M1-B 分支探测高德实时接口与额度。
