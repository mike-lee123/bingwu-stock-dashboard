"""下載日線股價、計算技術指標、畫技術面圖。

用法：
    python scripts/fetch_prices.py NVDA            # 完整：prices.csv + indicators.json + chart_technical.png
    python scripts/fetch_prices.py NVDA --quote    # 只印出最新報價與近 3 個月漲跌
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
SUPPORT, RESIST = "#17a2b8", "#e67e22"  # 支撐／超賣、壓力／超買：不隨漲跌配色變動


def download(ticker, period="2y"):
    df = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False)
    if df.empty:
        sys.exit(f"抓不到 {ticker} 的股價資料")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def add_indicators(df):
    c = df["Close"]
    for n in (20, 50, 200):
        df[f"SMA{n}"] = c.rolling(n).mean()

    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["RSI14"] = 100 - 100 / (1 + gain / loss)

    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_hist"] = df["MACD"] - df["MACD_signal"]

    std20 = c.rolling(20).std()
    df["BB_upper"] = df["SMA20"] + 2 * std20
    df["BB_lower"] = df["SMA20"] - 2 * std20

    prev_close = c.shift(1)
    tr = pd.concat([df["High"] - df["Low"],
                    (df["High"] - prev_close).abs(),
                    (df["Low"] - prev_close).abs()], axis=1).max(axis=1)
    df["ATR14"] = tr.ewm(alpha=1 / 14, adjust=False).mean()

    df["VOL20"] = df["Volume"].rolling(20).mean()
    df["VOL60"] = df["Volume"].rolling(60).mean()
    return df


def swing_levels(df, lookback=120, window=5, k=3):
    """近 lookback 日內的波段高低點，取離現價最近的 k 個支撐與壓力。"""
    d = df.tail(lookback)
    highs = d["High"][(d["High"] == d["High"].rolling(2 * window + 1, center=True).max())]
    lows = d["Low"][(d["Low"] == d["Low"].rolling(2 * window + 1, center=True).min())]
    price = df["Close"].iloc[-1]
    resistance = merge_close(sorted(float(v) for v in highs if v > price))[:k]
    support = merge_close(sorted((float(v) for v in lows if v < price), reverse=True))[:k]
    return support, resistance


def merge_close(levels, tol=0.01):
    """相距不到 1% 的價位視為同一關卡，只留離現價最近的那個。"""
    kept = []
    for lv in levels:
        if not kept or abs(lv / kept[-1] - 1) > tol:
            kept.append(lv)
    return [round(v, 2) for v in kept]


def is_taiwan(ticker):
    return ticker.endswith((".TW", ".TWO")) or ticker == "^TWII"


def pct(a, b):
    return round((a / b - 1) * 100, 2)


def summarize(df, ticker):
    last = df.iloc[-1]
    c = df["Close"]
    support, resistance = swing_levels(df)
    year = df.tail(252)

    def r(x):
        return None if pd.isna(x) else round(float(x), 2)

    return {
        "ticker": ticker,
        "last_date": df.index[-1].strftime("%Y-%m-%d"),
        "close": r(last["Close"]),
        "change_1d_pct": pct(c.iloc[-1], c.iloc[-2]),
        "change_1m_pct": pct(c.iloc[-1], c.iloc[-22]),
        "change_3m_pct": pct(c.iloc[-1], c.iloc[-64]),
        "change_1y_pct": pct(c.iloc[-1], c.iloc[-253]) if len(c) > 253 else None,
        "high_52w": r(year["High"].max()),
        "low_52w": r(year["Low"].min()),
        "from_52w_high_pct": pct(c.iloc[-1], year["High"].max()),
        "sma20": r(last["SMA20"]),
        "sma50": r(last["SMA50"]),
        "sma200": r(last["SMA200"]),
        "above_sma20": bool(last["Close"] > last["SMA20"]),
        "above_sma50": bool(last["Close"] > last["SMA50"]),
        "above_sma200": bool(last["Close"] > last["SMA200"]),
        "rsi14": r(last["RSI14"]),
        "macd": r(last["MACD"]),
        "macd_signal": r(last["MACD_signal"]),
        "macd_hist": r(last["MACD_hist"]),
        "macd_hist_rising": bool(df["MACD_hist"].iloc[-1] > df["MACD_hist"].iloc[-2]),
        "bb_upper": r(last["BB_upper"]),
        "bb_lower": r(last["BB_lower"]),
        "atr14": r(last["ATR14"]),
        "atr14_pct": round(float(last["ATR14"] / last["Close"] * 100), 2),
        "vol20_vs_vol60": round(float(last["VOL20"] / last["VOL60"]), 2),
        "support": support,
        "resistance": resistance,
        "source": "Yahoo Finance 日線（還原權值），經 scripts/fetch_prices.py 計算",
    }


def plot(df, ticker, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["Microsoft JhengHei", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    d = df.tail(180)
    x = np.arange(len(d))
    up = d["Close"] >= d["Open"]
    green, red = "#1a9850", "#d73027"  # 美股慣例：漲綠跌紅
    if is_taiwan(ticker):  # 台股慣例：漲紅跌綠
        green, red = red, green

    fig, axes = plt.subplots(4, 1, figsize=(11, 8.5), sharex=True,
                             gridspec_kw={"height_ratios": [4, 1, 1.2, 1.2]})
    ax = axes[0]
    ax.vlines(x, d["Low"], d["High"], color=np.where(up, green, red), linewidth=0.8)
    ax.bar(x, (d["Close"] - d["Open"]).abs(), bottom=d[["Open", "Close"]].min(axis=1),
           color=np.where(up, green, red), width=0.7)
    for col, color in (("SMA20", "#f39c12"), ("SMA50", "#2c7fb8"), ("SMA200", "#6a3d9a")):
        ax.plot(x, d[col], color=color, linewidth=1.2, label=col)
    ax.fill_between(x, d["BB_lower"], d["BB_upper"], color="#888", alpha=0.08, label="布林通道")
    support, resistance = swing_levels(df)
    for lv in support:
        ax.axhline(lv, color=SUPPORT, linestyle="--", linewidth=0.7, alpha=0.7)
    for lv in resistance:
        ax.axhline(lv, color=RESIST, linestyle="--", linewidth=0.7, alpha=0.7)
    ax.set_title(f"{ticker} 日線（近 180 個交易日）", fontsize=13, loc="left")
    ax.legend(loc="upper left", fontsize=8, ncol=4, frameon=False)
    ax.grid(alpha=0.2)

    axes[1].bar(x, d["Volume"] / 1e6, color=np.where(up, green, red), width=0.7)
    axes[1].plot(x, d["VOL20"] / 1e6, color="#333", linewidth=0.9)
    axes[1].set_ylabel("量(百萬)", fontsize=8)

    axes[2].plot(x, d["RSI14"], color="#2c7fb8", linewidth=1)
    axes[2].axhline(70, color=RESIST, linewidth=0.6, linestyle="--")
    axes[2].axhline(30, color=SUPPORT, linewidth=0.6, linestyle="--")
    axes[2].set_ylim(0, 100)
    axes[2].set_ylabel("RSI14", fontsize=8)

    axes[3].bar(x, d["MACD_hist"], color=np.where(d["MACD_hist"] >= 0, green, red), width=0.7)
    axes[3].plot(x, d["MACD"], color="#2c7fb8", linewidth=0.9, label="MACD")
    axes[3].plot(x, d["MACD_signal"], color="#f39c12", linewidth=0.9, label="Signal")
    axes[3].set_ylabel("MACD", fontsize=8)
    axes[3].legend(loc="upper left", fontsize=7, frameon=False)

    ticks = x[::20]
    axes[3].set_xticks(ticks)
    axes[3].set_xticklabels([d.index[i].strftime("%Y-%m") for i in ticks], fontsize=8)
    for a in axes[1:]:
        a.grid(alpha=0.2)
        a.tick_params(labelsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--quote", action="store_true", help="只印最新報價")
    args = ap.parse_args()
    ticker = args.ticker.upper()

    df = add_indicators(download(ticker))
    summary = summarize(df, ticker)

    if args.quote:
        keys = ["ticker", "last_date", "close", "change_1d_pct", "change_1m_pct",
                "change_3m_pct", "change_1y_pct", "high_52w", "low_52w"]
        print(json.dumps({k: summary[k] for k in keys}, ensure_ascii=False, indent=2))
        return

    out_dir = ROOT / "work" / ticker
    out_dir.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(out_dir / "prices.csv")
    (out_dir / "indicators.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    plot(df, ticker, out_dir / "chart_technical.png")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n已寫入 {out_dir}")


if __name__ == "__main__":
    main()
