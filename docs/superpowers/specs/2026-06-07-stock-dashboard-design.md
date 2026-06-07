# 自选股行情仪表板 — 设计规格

**日期**：2026-06-07 | **状态**：已确认

## 概述

一个基于 Flask 的本地 Web 仪表板，展示自选股实时行情。通过浏览器访问 `localhost:5000`，以卡片式布局呈现每只股票的行情数据、走势图和基本面信息。

## 方案

Flask + Jinja2 + ECharts（CDN），API 优先抓取，本地缓存兜底，`config.yaml` 管理自选股列表。

## 项目结构

```
git2026/stock-dashboard/
├── app.py                  # Flask 主入口（路由 + 模板渲染）
├── config.yaml             # 自选股配置
├── requirements.txt        # flask, pyyaml, requests
├── fetcher.py              # 行情抓取 + 缓存逻辑
├── data/
│   └── cache.json          # 本地行情缓存
└── templates/
    └── dashboard.html      # Jinja2 模板 + ECharts
```

启动：`cd stock-dashboard && python app.py` → `http://localhost:5000`

## 配置文件 `config.yaml`

```yaml
stocks:
  - code: "002594"
    name: "比亚迪"
    market: "sz"
  - code: "600519"
    name: "贵州茅台"
    market: "sh"

sources:
  - "sina"
  - "eastmoney"
  - "cache"

chart:
  days: 5
```

增减自选股只需编辑 `stocks` 列表。

## 数据层 `fetcher.py`

- API 源按 `sources` 顺序尝试，失败则切换到下一个
- `cache` 作为最终兜底，确保始终有数据展示
- 每个 API 源返回统一 dict 结构：`code`, `name`, `price`, `change`, `change_pct`, `open`, `high`, `low`, `volume`, `amount`, `pe`, `pb`, `market_cap`, `turnover_rate`, `history[]`, `source`
- 抓取成功后自动写入 `cache.json`
- 非交易时段返回缓存数据并标注状态

## 页面布局（卡片式 + 暖橙色调）

- **顶部栏**：标题"自选股行情仪表板"，更新时间，刷新按钮，数据来源指示
- **股票卡片**（每只一张）：
  - 卡片头部：股票名 + 代码 + 最新价 + 涨跌幅（颜色区分红涨绿跌）
  - 走势图区：ECharts 折线图，近 5 日收盘价，支持 hover tooltip
  - 指标网格（2x4）：今开、昨收、最高、最低、成交量、成交额、市盈率、市净率
  - 基本面折叠区（details/summary）：总市值、换手率、主力资金、融资余额等
- **视觉风格**：暖橙渐变背景 + 白色毛玻璃卡片，和 `index.html` 统一

## ECharts 图表

- CDN 引入：`echarts@5.x`
- 深色背景适配折线图
- 支持 hover 查看具体数值
- 30 秒轮询时图表平滑过渡更新

## 刷新机制

- 前端每 30 秒 `setInterval` 轮询后端 API 获取最新数据
- 提供手动刷新按钮
- 非交易时段自动降低刷新频率（可选优化）

## 边界场景

| 场景 | 处理 |
|------|------|
| 非交易时段 | 显示缓存数据，标注"已收盘" |
| API 全部不可用 | 回退 cache.json，标注"离线" |
| 某只股票数据不完整 | 缺失字段显示"——" |
| 缓存文件不存在 | 显示"暂无数据，请检查网络后刷新" |
| 自选股为空 | 显示"请在 config.yaml 中添加自选股" |

## 依赖

- `flask` — Web 框架
- `pyyaml` — 配置文件解析
- `requests` — HTTP 请求（可选，也可用 `urllib`）

## 不包含

- 用户登录/权限
- 数据库持久化（仅用 JSON 文件做缓存）
- Docker 部署
- 移动端适配
- 交易功能
