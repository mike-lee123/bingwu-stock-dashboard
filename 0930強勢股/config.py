"""選股門檻。數字都是起始值，請用回測或小部位實測後調整。"""
from dataclasses import dataclass, field


@dataclass
class PremarketConfig:
    lookback_days: int = 20            # 「前高」看幾個交易日
    avg_days: int = 5                  # 均量天數
    min_avg_value: float = 1e8         # 5 日均成交值下限（元），濾掉冷門股
    close_near_high: float = 0.8       # (收-低)/(高-低) 門檻
    volume_surge: float = 1.5          # 前一日量 / 5 日均量
    min_score: int = 3                 # 盤前分數達標才進候選
    max_candidates: int = 200


@dataclass
class IntradayConfig:
    poll_seconds: int = 20
    hold_tolerance: float = 0.005      # 回測開盤價容許跌破 0.5%
    volume_ratio: float = 2.0          # 預估量 / 5 日均量
    min_outer_ratio: float = 0.55      # 外盤比（逐次快照近似）
    min_turnover_0930: float = 5e7     # 9:30 前累計成交值下限（元）
    trial_fade: float = 0.01           # 試撮價從高點下修超過 1% 視為追價不足
    # 開盤後 N 分鐘累計量約占全日量的比例，用來推估全日量。
    # 這是粗估值，建議用自己的歷史分K資料校正。
    volume_curve: dict = field(default_factory=lambda: {
        1: 0.025, 5: 0.07, 10: 0.11, 15: 0.145, 20: 0.175, 25: 0.20, 30: 0.225,
    })
