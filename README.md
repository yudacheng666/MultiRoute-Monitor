# MultiRoute-Monitor

**中国大陆多路线通行时间看板 · M1-A 模拟原型**。在电脑浏览器同一页面查看最多 6 条独立的路线卡片，可编辑起终点、手动和定时刷新。**当前没有接入真实地图、实时路况或高德接口；所有 ETA、交通颜色、道路曲线都是明确标识的模拟数据。**

## 0 元本地启动
需要 Python 3（Windows 10/11、macOS、Linux），无需 pip/npm、API Key 或云服务。

```sh
python app.py
```

浏览器访问 `http://127.0.0.1:8765/`。默认只监听本机回环地址；停止运行按 Ctrl+C。首次提供 4 条虚构示例，可增删改路线、刷新单条/全部、暂停或调整自动刷新间隔。配置只保存在当前浏览器 localStorage；清理浏览器网站数据会丢失配置。路线图为**非地理参考的示意曲线**。

## 安全与费用
- **0 元模拟模式**：运行时不请求高德或其他外部服务，前后端不含外部 CDN、密钥。
- 请勿提交真实 API Key、实际家庭/办公地址、路线配置和任何私人资料；GitHub 只存虚构示例。
- 浏览器界面“模拟”标识不可取消。实际路况功能需在确认高德服务条款、用户用途和个人账户免费配额后另行实现。
- 除路线配置与偏好外，不写入真实交通或路况历史。
- 当前仅本地服务，不对局域网或公网开放。

## 测试
```sh
python -m unittest discover -s tests -p "test_*.py" -v
node --test tests/test_core.cjs
```

真浏览器 E2E：`npm ci` 后 `npx playwright install chromium`，运行 `node tests/test_browser.cjs`。GitHub Actions 将在 PR 的准确 SHA 上运行跨平台单元测试及 Chromium 测试。

## 开发治理
- `AGENTS.md`：跨对话 AI 开发规则。
- `docs/REQUIREMENTS.md`：阶段范围和验收。
- `docs/DECISIONS.md`：架构和合规决定。
- `docs/PROJECT_STATE.md`：准确状态和下一步。
- M1-A → M1-B 只在用户确认后推进；通过 Draft PR 审阅，不擅自合并到 main。
