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
