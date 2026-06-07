# 自选股行情仪表板 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 Flask 本地 Web 仪表板，以卡片式布局展示自选股实时行情、走势图和基本面数据。

**Architecture:** Flask 后端从新浪/东方财富 API 抓取行情 → 统一格式后注入 Jinja2 模板 → 前端 ECharts 渲染交互图表 + 30 秒自动轮询。配置驱动（config.yaml），API 优先 + 本地缓存兜底。

**Tech Stack:** Python 3.14, Flask, PyYAML, Requests, ECharts 5.x (CDN)

---

### Task 1: 项目骨架

**Files:**
- Create: `stock-dashboard/requirements.txt`
- Create: `stock-dashboard/config.yaml`

- [ ] **Step 1: 创建 requirements.txt**

```bash
mkdir -p /Users/rosermf2021/git2026/stock-dashboard/templates
mkdir -p /Users/rosermf2021/git2026/stock-dashboard/data
```

Write `stock-dashboard/requirements.txt`:

```
flask>=3.0
pyyaml>=6.0
requests>=2.31
```

- [ ] **Step 2: 安装依赖**

```bash
pip install -r /Users/rosermf2021/git2026/stock-dashboard/requirements.txt
```

- [ ] **Step 3: 创建 config.yaml**

Write `stock-dashboard/config.yaml`:

```yaml
stocks:
  - code: "002594"
    name: "比亚迪"
    market: "sz"
  - code: "600519"
    name: "贵州茅台"
    market: "sh"

sources:
  - "eastmoney"
  - "sina"
  - "cache"

chart:
  days: 5
```

- [ ] **Step 4: 将 .superpowers 加入 .gitignore**

Append to `gitignore` (or create `.gitignore`):

```
.superpowers/
```

- [ ] **Step 5: Commit**

```bash
cd /Users/rosermf2021/git2026
git add stock-dashboard/requirements.txt stock-dashboard/config.yaml .gitignore
git commit -m "feat: 初始化 stock-dashboard 项目骨架"
```

---

### Task 2: 初始缓存数据

**Files:**
- Create: `stock-dashboard/data/cache.json`

- [ ] **Step 1: 写入初始缓存文件**

Write `stock-dashboard/data/cache.json`（用已有的比亚迪和茅台行情数据）：

```json
{
  "002594": {
    "code": "002594",
    "name": "比亚迪",
    "market": "sz",
    "price": 93.01,
    "change": -0.43,
    "change_pct": -0.46,
    "open": 93.52,
    "close_yest": 93.44,
    "high": 94.00,
    "low": 92.30,
    "volume": "34.00万手",
    "amount": "31.59亿",
    "pe": 30.78,
    "pb": 3.66,
    "market_cap": "约8,480亿",
    "turnover_rate": 0.98,
    "history": [
      {"date": "6/1", "close": 93.65},
      {"date": "6/2", "close": 96.76},
      {"date": "6/3", "close": 94.82},
      {"date": "6/4", "close": 93.11},
      {"date": "6/5", "close": 93.01}
    ],
    "source": "cache",
    "updated_at": "2026-06-05 15:00:00"
  },
  "600519": {
    "code": "600519",
    "name": "贵州茅台",
    "market": "sh",
    "price": 1272.86,
    "change": 4.86,
    "change_pct": 0.38,
    "open": 1278.00,
    "close_yest": 1268.00,
    "high": 1283.00,
    "low": 1267.74,
    "volume": "313.04万手",
    "amount": "39.84亿",
    "pe": 14.60,
    "pb": 5.87,
    "market_cap": "约1.59万亿",
    "turnover_rate": 0.25,
    "history": [
      {"date": "6/1", "close": 1309.60},
      {"date": "6/2", "close": 1307.22},
      {"date": "6/3", "close": 1281.91},
      {"date": "6/4", "close": 1268.00},
      {"date": "6/5", "close": 1272.86}
    ],
    "source": "cache",
    "updated_at": "2026-06-05 15:00:00"
  }
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/rosermf2021/git2026
git add stock-dashboard/data/cache.json
git commit -m "feat: 添加初始行情缓存数据"
```

---

### Task 3: 数据抓取模块

**Files:**
- Create: `stock-dashboard/fetcher.py`

- [ ] **Step 1: 实现 fetcher.py**

Write `stock-dashboard/fetcher.py`:

```python
"""行情数据抓取与缓存模块。按 config.yaml 中的 sources 顺序尝试，兜底读本地缓存。"""
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests

DATA_DIR = Path(__file__).parent / "data"
CACHE_FILE = DATA_DIR / "cache.json"

# A 股交易时段：周一至周五 9:30-11:30, 13:00-15:00
def is_trading_time():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (9 * 60 + 30 <= t <= 11 * 60 + 30) or (13 * 60 <= t <= 15 * 60)


def _parse_volume(vol_shares):
    """将股数转成 xx.xx万手"""
    if vol_shares:
        wan = float(vol_shares) / 10000 / 100
        return f"{wan:.2f}万手"
    return "——"


def _parse_amount(amount_yuan):
    """将元转成 xx.xx亿"""
    if amount_yuan:
        yi = float(amount_yuan) / 1e8
        return f"{yi:.2f}亿"
    return "——"


# ── 东方财富 API ─────────────────────────────────────

def _fetch_eastmoney(code, market, name):
    secid = f"0.{code}" if market == "sz" else f"1.{code}"
    fields = "f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f58,f116,f167,f168"
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/get"
        f"?secid={secid}&fields={fields}"
    )
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    d = resp.json().get("data", {})
    if not d:
        raise ValueError("东方财富返回空数据")

    price = d.get("f43", 0) / 100
    change = d.get("f50", 0) / 100
    change_pct = round(d.get("f51", 0) / 100, 2)
    volume_shares = d.get("f47")
    amount_yuan = d.get("f48")

    return {
        "code": code,
        "name": name,
        "market": market,
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "open": d.get("f46", 0) / 100 if d.get("f46") else "——",
        "close_yest": d.get("f52", 0) / 100 if d.get("f52") else "——",
        "high": d.get("f44", 0) / 100 if d.get("f44") else "——",
        "low": d.get("f45", 0) / 100 if d.get("f45") else "——",
        "volume": _parse_volume(volume_shares),
        "amount": _parse_amount(amount_yuan),
        "pe": round(d.get("f58", 0) / 100, 2) if d.get("f58") else "——",
        "pb": round(d.get("f167", 0) / 100, 2) if d.get("f167") else "——",
        "market_cap": f"{d.get('f116', 0) / 1e8:.0f}亿" if d.get("f116") else "——",
        "turnover_rate": round(d.get("f55", 0) / 100, 2) if d.get("f55") else "——",
        "history": [],  # 单个快照不含历史，由上层合并缓存历史
        "source": "eastmoney",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── 新浪财经 API ─────────────────────────────────────

def _fetch_sina(code, market, name):
    symbol = f"{market}{code}"
    url = f"https://hq.sinajs.cn/list={symbol}"
    headers = {"Referer": "https://finance.sina.com.cn"}
    resp = requests.get(url, timeout=5, headers=headers)
    resp.raise_for_status()
    resp.encoding = "gbk"
    text = resp.text

    # 新浪返回格式: var hq_str_sz002594="名称,今开,昨收,现价,最高,最低,..."
    match = re.search(r'"([^"]*)"', text)
    if not match:
        raise ValueError(f"新浪返回格式异常: {text[:80]}")
    fields = match.group(1).split(",")
    if len(fields) < 32:
        raise ValueError(f"新浪返回字段不足: {len(fields)} 个")

    price = float(fields[3])
    close_yest = float(fields[2])
    change = round(price - close_yest, 2)
    change_pct = round(change / close_yest * 100, 2) if close_yest else 0
    volume_shares = int(fields[8])
    amount_yuan = float(fields[9]) * 10000  # 新浪单位是万元

    return {
        "code": code,
        "name": fields[0],
        "market": market,
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "open": float(fields[1]),
        "close_yest": close_yest,
        "high": float(fields[4]),
        "low": float(fields[5]),
        "volume": _parse_volume(volume_shares),
        "amount": _parse_amount(amount_yuan),
        "pe": "——",       # 新浪基础接口不含 PE/PB
        "pb": "——",
        "market_cap": "——",
        "turnover_rate": "——",
        "history": [],
        "source": "sina",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── 缓存回退 ────────────────────────────────────────

def _load_cache():
    if not CACHE_FILE.exists():
        return {}
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _fetch_cache(code, market, name):
    cache = _load_cache()
    item = cache.get(code, {})
    if not item:
        return {
            "code": code, "name": name, "market": market,
            "price": "——", "change": "——", "change_pct": "——",
            "open": "——", "close_yest": "——", "high": "——", "low": "——",
            "volume": "——", "amount": "——",
            "pe": "——", "pb": "——", "market_cap": "——", "turnover_rate": "——",
            "history": [], "source": "cache", "updated_at": "——",
        }
    item["source"] = "cache"
    return item


# ── 保存缓存 ────────────────────────────────────────

def save_cache(all_data):
    """all_data: list[dict]，按 code 写入 cache.json，合并已有 history"""
    existing = _load_cache()
    for item in all_data:
        code = item["code"]
        prev = existing.get(code, {})
        prev_history = prev.get("history", [])
        new_history = item.get("history", [])
        # 合并历史：新数据优先，去重
        dates = {h["date"] for h in new_history}
        merged = list(new_history)
        for h in prev_history:
            if h["date"] not in dates:
                merged.append(h)
                dates.add(h["date"])
        merged.sort(key=lambda x: x["date"])
        item["history"] = merged[-30:]  # 最多保留 30 天
        existing[code] = item
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


# ── 主入口 ──────────────────────────────────────────

FETCHERS = {
    "eastmoney": _fetch_eastmoney,
    "sina": _fetch_sina,
    "cache": _fetch_cache,
}


def fetch_stock(code, market, name, sources):
    """按 sources 依次尝试抓取，返回统一格式 dict。"""
    result = None
    for src in sources:
        fetcher = FETCHERS.get(src)
        if not fetcher:
            continue
        try:
            result = fetcher(code, market, name)
            if result and result.get("price") != "——":
                break
        except Exception:
            continue

    if result is None:
        result = _fetch_cache(code, market, name)

    # 合并缓存中的 history（API 通常不带 history）
    if not result.get("history"):
        cache = _load_cache()
        cached_item = cache.get(code, {})
        result["history"] = cached_item.get("history", [])

    return result
```

- [ ] **Step 2: Commit**

```bash
cd /Users/rosermf2021/git2026
git add stock-dashboard/fetcher.py
git commit -m "feat: 实现行情数据抓取与缓存模块"
```

---

### Task 4: Flask 主入口

**Files:**
- Create: `stock-dashboard/app.py`

- [ ] **Step 1: 实现 app.py**

Write `stock-dashboard/app.py`:

```python
"""自选股行情仪表板 — Flask 主入口"""
import json
from datetime import datetime
from pathlib import Path

import yaml
from flask import Flask, jsonify, render_template, request

from fetcher import fetch_stock, save_cache, is_trading_time

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.yaml"

app = Flask(__name__)


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def gather_data():
    """遍历自选股，抓取行情，返回 (data_list, meta_dict)。"""
    config = load_config()
    stocks = config.get("stocks", [])
    sources = config.get("sources", ["eastmoney", "sina", "cache"])

    results = []
    for s in stocks:
        item = fetch_stock(s["code"], s["market"], s["name"], sources)
        results.append(item)

    # 非缓存数据写入缓存（API 成功时）
    fresh = [r for r in results if r.get("source") != "cache"]
    if fresh:
        save_cache(results)

    first_source = next(
        (r["source"] for r in results if r["source"] != "cache"), "cache"
    )

    meta = {
        "count": len(results),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": first_source,
        "is_trading": is_trading_time(),
    }
    return results, meta


@app.route("/")
def index():
    data, meta = gather_data()
    return render_template(
        "dashboard.html",
        stocks_data=data,
        meta=meta,
    )


@app.route("/api/data")
def api_data():
    data, meta = gather_data()
    return jsonify({"stocks": data, "meta": meta})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/rosermf2021/git2026
git add stock-dashboard/app.py
git commit -m "feat: 实现 Flask 主入口与 API 路由"
```

---

### Task 5: 仪表板页面模板

**Files:**
- Create: `stock-dashboard/templates/dashboard.html`

- [ ] **Step 1: 实现 dashboard.html**

Write `stock-dashboard/templates/dashboard.html`:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>自选股行情仪表板</title>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      min-height: 100vh;
      font-family: "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif;
      background: linear-gradient(135deg, #fff5e6 0%, #ffe0c2 50%, #ffd1b3 100%);
      padding: 24px;
      color: #5c3a21;
    }

    .container {
      max-width: 900px;
      margin: 0 auto;
    }

    /* ── 顶部栏 ── */
    .header {
      text-align: center;
      margin-bottom: 24px;
    }
    .header h1 {
      font-size: 1.8rem;
      color: #d2691e;
      margin-bottom: 6px;
    }
    .header .info {
      font-size: 0.85rem;
      color: #a0673a;
    }
    .header .info span {
      margin: 0 8px;
    }
    .status-dot {
      display: inline-block;
      width: 8px; height: 8px;
      border-radius: 50%;
      margin-right: 4px;
    }
    .status-dot.live { background: #4ec9b0; }
    .status-dot.offline { background: #e94545; }
    .status-dot.closed { background: #f0ad4e; }

    .toolbar {
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 12px;
      margin-bottom: 20px;
    }
    .btn-refresh {
      padding: 8px 20px;
      border: none;
      border-radius: 20px;
      background: #ffa770;
      color: #fff;
      font-size: 0.9rem;
      cursor: pointer;
      transition: background 0.3s;
    }
    .btn-refresh:hover { background: #ff8c52; }
    .btn-refresh:disabled { opacity: 0.6; cursor: not-allowed; }

    /* ── 股票卡片 ── */
    .stock-card {
      background: rgba(255, 255, 255, 0.75);
      backdrop-filter: blur(12px);
      border-radius: 20px;
      padding: 24px;
      margin-bottom: 20px;
      box-shadow:
        0 8px 24px rgba(255, 153, 102, 0.12),
        0 2px 6px rgba(0, 0, 0, 0.04);
      animation: fadeIn 0.5s ease-out;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(12px); }
      to   { opacity: 1; transform: translateY(0); }
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 16px;
    }
    .stock-name {
      font-size: 1.3rem;
      font-weight: 600;
      color: #5c3a21;
    }
    .stock-code {
      font-size: 0.8rem;
      color: #a0673a;
      margin-left: 8px;
    }
    .stock-price {
      text-align: right;
    }
    .stock-price .price {
      font-size: 2rem;
      font-weight: 700;
    }
    .stock-price .change {
      font-size: 0.95rem;
    }
    .up { color: #e94545; }
    .down { color: #4ec946; }
    .flat { color: #a0673a; }

    /* ── 图表容器 ── */
    .chart-box {
      width: 100%;
      height: 260px;
      margin-bottom: 16px;
      background: rgba(255, 245, 230, 0.35);
      border-radius: 12px;
    }

    /* ── 指标网格 ── */
    .indicators {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
      margin-bottom: 12px;
    }
    .indicator {
      background: rgba(255, 245, 230, 0.5);
      border-radius: 8px;
      padding: 10px 8px;
      text-align: center;
    }
    .indicator .label {
      font-size: 0.7rem;
      color: #a0673a;
      margin-bottom: 2px;
    }
    .indicator .value {
      font-size: 0.95rem;
      font-weight: 600;
    }

    /* ── 基本面折叠区 ── */
    .fundamentals {
      border-top: 1px solid rgba(255, 167, 112, 0.25);
      padding-top: 10px;
    }
    .fundamentals summary {
      font-size: 0.9rem;
      color: #d2691e;
      cursor: pointer;
      font-weight: 500;
    }
    .fundamentals .fund-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin-top: 10px;
      font-size: 0.85rem;
      color: #6b4423;
    }

    /* ── 空状态 ── */
    .empty-state {
      text-align: center;
      padding: 80px 20px;
      color: #a0673a;
    }
    .empty-state h2 {
      font-size: 1.4rem;
      margin-bottom: 8px;
    }

    /* ── 响应式 ── */
    @media (max-width: 640px) {
      body { padding: 12px; }
      .indicators { grid-template-columns: repeat(3, 1fr); }
      .stock-price .price { font-size: 1.4rem; }
      .chart-box { height: 200px; }
    }
  </style>
</head>
<body>
  <div class="container">
    <!-- 顶部 -->
    <div class="header">
      <h1>📈 自选股行情仪表板</h1>
      <div class="info">
        {% if meta.count == 0 %}
        <span>请在 config.yaml 中添加自选股</span>
        {% else %}
        <span>
          {% if meta.is_trading %}
          <span class="status-dot live"></span>交易中
          {% else %}
          <span class="status-dot closed"></span>已收盘
          {% endif %}
        </span>
        <span>更新时间：<strong id="update-time">{{ meta.updated_at }}</strong></span>
        <span>数据来源：<strong id="data-source">{{ meta.source }}</strong></span>
        <span>共 {{ meta.count }} 只自选股</span>
        {% endif %}
      </div>
    </div>

    {% if stocks_data %}
    <div class="toolbar">
      <button class="btn-refresh" id="btn-refresh" onclick="refreshData()">🔄 刷新数据</button>
    </div>
    {% endif %}

    <!-- 股票卡片 -->
    <div id="cards-container">
      {% if stocks_data %}
        {% for stock in stocks_data %}
        <div class="stock-card" id="card-{{ stock.code }}" data-code="{{ stock.code }}">
          <div class="card-header">
            <div>
              <span class="stock-name">{{ stock.name }}</span>
              <span class="stock-code">{{ stock.code }}.{{ 'SZ' if stock.market == 'sz' else 'SH' }}</span>
            </div>
            <div class="stock-price">
              {% if stock.price == '——' %}
              <div class="price flat">——</div>
              <div class="change">暂无数据</div>
              {% elif stock.change >= 0 %}
              <div class="price up">{{ "%.2f"|format(stock.price) }}</div>
              <div class="change up">+{{ "%.2f"|format(stock.change) }} (+{{ stock.change_pct }}%)</div>
              {% else %}
              <div class="price down">{{ "%.2f"|format(stock.price) }}</div>
              <div class="change down">{{ "%.2f"|format(stock.change) }} ({{ stock.change_pct }}%)</div>
              {% endif %}
            </div>
          </div>

          <!-- 走势图 -->
          <div class="chart-box" id="chart-{{ stock.code }}"></div>

          <!-- 指标网格 -->
          <div class="indicators">
            <div class="indicator"><div class="label">今开</div><div class="value">{{ stock.open }}</div></div>
            <div class="indicator"><div class="label">昨收</div><div class="value">{{ stock.close_yest }}</div></div>
            <div class="indicator"><div class="label">最高</div><div class="value">{{ stock.high }}</div></div>
            <div class="indicator"><div class="label">最低</div><div class="value">{{ stock.low }}</div></div>
            <div class="indicator"><div class="label">成交量</div><div class="value">{{ stock.volume }}</div></div>
            <div class="indicator"><div class="label">成交额</div><div class="value">{{ stock.amount }}</div></div>
            <div class="indicator"><div class="label">市盈率</div><div class="value">{{ stock.pe }}</div></div>
            <div class="indicator"><div class="label">市净率</div><div class="value">{{ stock.pb }}</div></div>
          </div>

          <!-- 基本面折叠 -->
          <details class="fundamentals">
            <summary>📋 基本面 & 资金面</summary>
            <div class="fund-grid">
              <div><strong>总市值：</strong>{{ stock.market_cap }}</div>
              <div><strong>换手率：</strong>{{ stock.turnover_rate }}</div>
            </div>
          </details>
        </div>
        {% endfor %}
      {% else %}
      <div class="empty-state">
        <h2>暂无自选股</h2>
        <p>请在 config.yaml 中配置 stocks 列表，然后重启服务。</p>
      </div>
      {% endif %}
    </div>
  </div>

  <script>
    // ── 初始数据 ──
    const initialData = {{ stocks_data | tojson }};
    // ── ECharts 图表初始化 ──
    const charts = {};

    function initChart(code, history) {
      const dom = document.getElementById('chart-' + code);
      if (!dom) return;
      if (charts[code]) charts[code].dispose();

      const chart = echarts.init(dom);
      charts[code] = chart;

      const dates = (history || []).map(h => h.date);
      const closes = (history || []).map(h => h.close);
      const hasData = dates.length > 0 && closes.length > 0;

      chart.setOption({
        grid: { left: 50, right: 20, top: 20, bottom: 30 },
        xAxis: {
          type: 'category',
          data: hasData ? dates : ['暂无数据'],
          axisLine: { lineStyle: { color: '#d9a679' } },
          axisLabel: { color: '#a0673a', fontSize: 11 },
        },
        yAxis: {
          type: 'value',
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { lineStyle: { color: 'rgba(255,167,112,0.2)' } },
          axisLabel: { color: '#a0673a', fontSize: 11 },
        },
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(255,255,255,0.9)',
          borderColor: '#ffa770',
          textStyle: { color: '#5c3a21' },
        },
        series: [{
          type: 'line',
          data: hasData ? closes : [],
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { color: '#ffa770', width: 2 },
          itemStyle: { color: '#d2691e' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(255,167,112,0.35)' },
              { offset: 1, color: 'rgba(255,167,112,0.02)' },
            ]),
          },
        }],
      });
    }

    // ── 初始化所有图表 ──
    initialData.forEach(stock => {
      initChart(stock.code, stock.history);
    });

    // ── 自动刷新 ──
    let refreshTimer = null;

    function startAutoRefresh() {
      refreshTimer = setInterval(refreshData, 30000);
    }

    async function refreshData() {
      const btn = document.getElementById('btn-refresh');
      if (btn) btn.disabled = true;
      try {
        const resp = await fetch('/api/data');
        const json = await resp.json();
        document.getElementById('update-time').textContent = json.meta.updated_at;

        const sourceEl = document.getElementById('data-source');
        if (sourceEl) sourceEl.textContent = json.meta.source;

        json.stocks.forEach(stock => {
          const card = document.getElementById('card-' + stock.code);
          if (!card) return;
          // 更新价格
          const priceEl = card.querySelector('.price');
          const changeEl = card.querySelector('.change');
          if (stock.price === '——') {
            priceEl.textContent = '——';
            priceEl.className = 'price flat';
            changeEl.textContent = '暂无数据';
          } else {
            priceEl.textContent = stock.price.toFixed(2);
            if (stock.change >= 0) {
              priceEl.className = 'price up';
              changeEl.className = 'change up';
              changeEl.textContent = '+' + stock.change.toFixed(2) + ' (+' + stock.change_pct + '%)';
            } else {
              priceEl.className = 'price down';
              changeEl.className = 'change down';
              changeEl.textContent = stock.change.toFixed(2) + ' (' + stock.change_pct + '%)';
            }
          }
          // 更新指标
          const indicators = card.querySelectorAll('.indicator .value');
          const vals = [
            stock.open, stock.close_yest, stock.high, stock.low,
            stock.volume, stock.amount, stock.pe, stock.pb,
          ];
          indicators.forEach((el, i) => { if (i < vals.length) el.textContent = vals[i]; });
          // 更新图表
          if (stock.history && stock.history.length > 0) {
            charts[stock.code].setOption({
              xAxis: { data: stock.history.map(h => h.date) },
              series: [{ data: stock.history.map(h => h.close) }],
            });
          }
        });
      } catch (err) {
        console.error('刷新失败:', err);
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    startAutoRefresh();

    // ── 窗口尺寸变化时重绘图表 ──
    window.addEventListener('resize', () => {
      Object.values(charts).forEach(c => c.resize());
    });
  </script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
cd /Users/rosermf2021/git2026
git add stock-dashboard/templates/dashboard.html
git commit -m "feat: 实现仪表板页面模板（卡片布局 + ECharts 走势图）"
```

---

### Task 6: 集成验证

- [ ] **Step 1: 启动服务并验证**

```bash
cd /Users/rosermf2021/git2026/stock-dashboard
python app.py
```

打开浏览器访问 `http://localhost:5000`，检查：
- 能否看到比亚迪和贵州茅台的卡片
- 走势图是否正常渲染
- 价格、指标数值是否正确显示
- 30 秒后是否自动刷新

- [ ] **Step 2: 验证边界场景**

在浏览器中：
- 刷新按钮是否可用
- 基本面折叠区能否展开/收起
- 缩小窗口看响应式是否正常

断开网络后重启服务，检查：
- 是否回退到缓存数据
- 是否标注"数据来源：cache"

- [ ] **Step 3: 验证配置驱动**

编辑 `config.yaml`，删除贵州茅台条目，重启服务，验证页面只显示比亚迪。

- [ ] **Step 4: Commit（如有微调）**

```bash
cd /Users/rosermf2021/git2026
git add -A
git commit -m "chore: 集成验证完成"
```
