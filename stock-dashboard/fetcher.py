"""行情数据抓取与缓存模块。按 config.yaml 中的 sources 顺序尝试，兜底读本地缓存。"""
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 绕过系统代理，避免因本地代理不可用导致 API 请求挂起
session = requests.Session()
session.trust_env = False
# 东财等接口偶发瞬时断连(RemoteDisconnected)，对幂等 GET 自动重试 2 次(退避 0.5/1.0s)，
# 避免一次抖动就回退到新浪、白白丢掉基本面/资金面字段；成功路径零开销
_retry = Retry(total=2, backoff_factor=0.5, allowed_methods=frozenset(["GET"]))
session.mount("https://", HTTPAdapter(max_retries=_retry))
session.mount("http://", HTTPAdapter(max_retries=_retry))

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

def _em_val(v, scale=100, ndigits=2, empty="——", zero_ok=False):
    """东方财富原始字段 → 展示值。
    - 非数值（如 f58 名称是字符串）或 None → 返回 empty，从根上杜绝 str/None ÷ int 崩溃
    - 默认把 0 也当「无数据」返回 empty；涨跌额/涨跌幅这类平盘合法为 0 的字段传 zero_ok=True
    """
    if isinstance(v, (int, float)) and (zero_ok or v != 0):
        return round(v / scale, ndigits)
    return empty


def _fetch_eastmoney(code, market, name):
    secid = f"0.{code}" if market == "sz" else f"1.{code}"
    # 字段语义已对照接口真实返回校准（曾把 f58 名称误当市盈率，str÷int 让整个源每次崩溃）：
    #   f43现价 f44最高 f45最低 f46今开 f47成交量(手) f48成交额(元)
    #   f60昨收 f116总市值 f162市盈率(动) f167市净率 f168换手率 f169涨跌额 f170涨跌幅
    fields = "f43,f44,f45,f46,f47,f48,f60,f116,f162,f167,f168,f169,f170"
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/get"
        f"?secid={secid}&fields={fields}"
    )
    resp = session.get(url, timeout=5)
    resp.raise_for_status()
    d = resp.json().get("data", {})
    if not d:
        raise ValueError("东方财富返回空数据")

    price = _em_val(d.get("f43"))
    if price == "——":
        raise ValueError("东方财富现价为空，疑似停牌")

    # 东财 f47 单位是「手」，而 _parse_volume 期望「股」(内部 ÷100 折算手)，先 ×100 对齐口径
    volume_shares = (d.get("f47") or 0) * 100
    f116 = d.get("f116")

    return {
        "code": code,
        "name": name,
        "market": market,
        "price": price,
        "change": _em_val(d.get("f169"), empty=0, zero_ok=True),
        "change_pct": _em_val(d.get("f170"), empty=0, zero_ok=True),
        "open": _em_val(d.get("f46")),
        "close_yest": _em_val(d.get("f60")),
        "high": _em_val(d.get("f44")),
        "low": _em_val(d.get("f45")),
        "volume": _parse_volume(volume_shares),
        "amount": _parse_amount(d.get("f48")),
        "pe": _em_val(d.get("f162")),
        "pb": _em_val(d.get("f167")),
        "market_cap": f"{f116 / 1e8:.0f}亿" if isinstance(f116, (int, float)) and f116 else "——",
        "turnover_rate": _em_val(d.get("f168")),
        "history": [],
        "source": "eastmoney",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── 新浪财经 API ─────────────────────────────────────

def _fetch_sina(code, market, name):
    symbol = f"{market}{code}"
    url = f"https://hq.sinajs.cn/list={symbol}"
    headers = {"Referer": "https://finance.sina.com.cn"}
    resp = session.get(url, timeout=5, headers=headers)
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

    # 停牌股票返回空字符串，提前检测避免 float("") 引发 ValueError
    if not fields[3] or not fields[2]:
        raise ValueError("股票可能已停牌，价格字段为空")

    price = float(fields[3])
    close_yest = float(fields[2])
    change = round(price - close_yest, 2)
    change_pct = round(change / close_yest * 100, 2) if close_yest else 0
    volume_shares = int(fields[8])
    amount_yuan = float(fields[9])  # 新浪返回成交额单位已是元

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
        "pe": "——",
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
        dates = {h["date"] for h in new_history}
        merged = list(new_history)
        for h in prev_history:
            if h["date"] not in dates:
                merged.append(h)
                dates.add(h["date"])
        merged.sort(key=lambda x: x["date"])
        item["history"] = merged[-30:]
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
    if market not in ("sz", "sh"):
        raise ValueError(f"market 必须是 'sz' 或 'sh'，收到: {market}")
    result = None
    for src in sources:
        fetcher = FETCHERS.get(src)
        if not fetcher:
            continue
        try:
            result = fetcher(code, market, name)
            if result and result.get("price") not in (None, 0, "——", 0.0):
                break
        except Exception as e:
            # 不再静默吞异常：曾因东财字段编号写错导致每次崩溃却无人察觉
            print(f"[fetch] 数据源 {src} 抓取 {name}({code}) 失败: {type(e).__name__}: {e}")
            continue

    if result is None:
        result = _fetch_cache(code, market, name)

    # 合并缓存中的 history（API 通常不带 history）
    if not result.get("history"):
        cache = _load_cache()
        cached_item = cache.get(code, {})
        result["history"] = cached_item.get("history", [])

    return result
