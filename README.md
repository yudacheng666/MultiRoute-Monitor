# MultiRoute-Monitor

**中国大陆多路线通行时间看板 · M1-A 已发布 / M1-B 安全接入候选**。在电脑浏览器同一页面查看最多 6 条独立的路线卡片，可编辑起终点、手动和定时刷新。**当前没有接入真实地图、实时路况或高德接口；所有 ETA、交通颜色、道路曲线都是明确标识的模拟数据。**

## 0 元本地启动
需要 Python 3（Windows 10/11、macOS、Linux），无需 pip/npm、API Key 或云服务。

```sh
python app.py
```

浏览器访问 `http://127.0.0.1:8876/`。**默认端口 8876 与 SRM 的 8765 端口隔离**。如果本机 8876 已被占用，可通过 `python app.py --port 18876` 改用其他空闲端口。默认只监听本机回环地址；停止运行按 Ctrl+C。首次提供 4 条虚构示例，可增删改路线、刷新单条/全部、暂停或调整自动刷新间隔。配置只保存在当前浏览器 localStorage；清理浏览器网站数据会丢失配置。路线图为**非地理参考的示意曲线**。

## 安全与费用
- **0 元模拟模式**：运行时不请求高德或其他外部服务，前后端不含外部 CDN、密钥。
- 请勿提交真实 API Key、实际家庭/办公地址、路线配置和任何私人资料；GitHub 只存虚构示例。
- 浏览器界面“模拟”标识不可取消。实际路况功能需在确认高德服务条款、用户用途和个人账户免费配额后另行实现。
- 除路线配置与偏好外，不写入真实交通或路况历史。
- 当前仅本地服务，不对局域网或公网开放。

## M1-B 高德路径规划接入候选（尚未正式上线）
M1-B 独立分支提供可选经纬度输入、驾车2.0响应解析、路况分段线形、手动查询 UI 与本地预算门禁；模拟模式仍为默认，未经授权不发送高德请求。实际账号许可/免费余额、真实 API 行为及高德地图底图都未核验。
用户确认高德许可及账户费用后，须在本机设置 MRM_AMAP_WEB_KEY、MRM_USAGE_AUTHORIZED=YES、MRM_FREE_QUOTA_VERIFIED=YES、MRM_EXPLICIT_LIVE_OPT_IN=YES 才允许请求；密钥不得上传 GitHub 或发给 ChatGPT。即便启用，本程序仅按需手动查询，默认每天最多100次、应用硬上限1000次，同路线5分钟内不重复查询。
程序配额不统计同一个 Key 的其他使用方，不能保证高德账号不会收费；未确认实际免费授权则继续模拟。
当前分支新增官方高德 JS API 2.0 按需地图加载器和同源安全代理（**仅技术候选，未经真实账号验收**）：需要额外本机配置 MRM_AMAP_JS_KEY、MRM_AMAP_JS_SECURITY、MRM_AMAP_MAP_OPT_IN=YES；先合法手动查询路线，再点击“查看高德地图”才会加载图面。安全码不返回浏览器，Web端 JS Key 会在浏览器使用。地图代理每日最多500次，不等同于地图初始化配额。

用户已明确完全个人使用，但高德免费许可在协议中要求自然人“个人研究学习目的”；须核实与实际看板用途的匹配程度。官方当前月配额参考为驾车规划150,000次、地图初始化1,500,000次，**不能替代本人账号实际配额与计费核实**。详见 docs/M1B_GATES.md。
本机端口仍为8876，SRM 的8765不受影响。

## 你只需要配置 Key，代理由程序自动处理

当高德授权和免费额度条件满足后，从本分支下载 ZIP，解压并在项目文件夹运行：

```powershell
python setup_amap.py
```

脚本会要求输入已有的 **Web服务 Key、Web端(JS API) Key**，以及 Web端 Key 页面中的 **安全密钥 securityJsCode**。第三项不是第三个 Key。输入不回显；密钥仅保存在该电脑的 local/amap_keys.json（已被 Git 忽略），不用发送给 ChatGPT，也不用安装 Nginx 或自行配置代理。更换下载目录时，请注意迁移此私有文件并确保它没有上传到公开仓库。

**保存 Key ≠ 开启真实查询**：脚本只保存三个密钥，不设置授权开关、也不会发起任何高德 API 调用。个人用途是否符合授权、账号免费余额及超额计费停止条件仍需核实。

## 测试
```sh
python -m unittest discover -s tests -p "test_*.py" -v
node --test tests/test_core.cjs
```

真浏览器 E2E：`npm install --no-save --no-package-lock playwright@1.56.1` 后 `npx playwright install chromium`，运行 `node tests/test_browser.cjs`。GitHub Actions 将在 PR 的准确 SHA 上运行跨平台单元测试及 Chromium 测试。

## 开发治理
- `AGENTS.md`：跨对话 AI 开发规则。
- `docs/REQUIREMENTS.md`：阶段范围和验收。
- `docs/DECISIONS.md`：架构和合规决定。
- `docs/PROJECT_STATE.md`：准确状态和下一步。
- M1-A → M1-B 只在用户确认后推进；通过 Draft PR 审阅，不擅自合并到 main。
