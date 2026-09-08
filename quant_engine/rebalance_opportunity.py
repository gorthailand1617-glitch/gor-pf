import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

ASSET_NAMES: Dict[str, str] = {
    "fixed_income": "แผนตราสารหนี้",
    "money_market": "แผนเงินฝากและตราสารหนี้ระยะสั้น",
    "thai_equity": "แผนหุ้นไทย",
    "thai_property": "แผนกองทุนอสังหาริมทรัพย์ไทย",
    "global_equity": "แผนหุ้นต่างประเทศ",
    "global_debt": "แผนตราสารหนี้ต่างประเทศ",
    "gold": "แผนทองคำ"
}

MAX_ANNUAL_REBALANCES = 12
COOLDOWN_DAYS = 5
SCORE_IMPROVEMENT_THRESHOLD = 8.0
SIGNIFICANT_WEIGHT_SHIFT_THRESHOLD = 0.15


class OpportunityDetector:
    """
    Analyzes asset signals against the user's current custom portfolio weights.
    Determines if there is a compelling, high-conviction opportunity to capture profit
    or preserve capital, while strictly enforcing the 12-rebalances-per-calendar-year limit.
    """

    def __init__(self, max_rebalances: int = MAX_ANNUAL_REBALANCES):
        self.max_rebalances = max_rebalances

    def calculate_optimized_weights(
        self,
        current_weights: Dict[str, float],
        signals: Dict[str, Dict[str, Any]],
        equity_cap: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Calculates optimal asset weights based on current quantitative signals.
        - REDUCE: Allocate 0% to exit risky / plunging assets.
        - WATCH: Cut weight by 50% to mitigate risk while staying observant.
        - BUY_HOLD: Retain and receive redistributed capital proportional to composite score.
        - equity_cap: Optional maximum total weight for equities (Life Path model).
        """
        optimized: Dict[str, float] = {}
        freed_weight = 0.0
        buy_hold_assets: List[str] = []

        for asset, w in current_weights.items():
            sig_data = signals.get(asset, {"signal": "WATCH", "composite_score": 50.0})
            sig = sig_data.get("signal", "WATCH")

            if sig == "REDUCE":
                optimized[asset] = 0.0
                freed_weight += w
            elif sig == "WATCH":
                new_w = w * 0.5
                optimized[asset] = new_w
                freed_weight += (w - new_w)
            else:
                buy_hold_assets.append(asset)
                optimized[asset] = w

        if buy_hold_assets:
            total_buy_score = sum(
                signals.get(a, {}).get("composite_score", 50.0) for a in buy_hold_assets
            )
            if total_buy_score > 0:
                for a in buy_hold_assets:
                    score = signals.get(a, {}).get("composite_score", 50.0)
                    share = (score / total_buy_score) * freed_weight
                    optimized[a] += share
        else:
            # All assets in trouble -> Park safely in money market
            for asset in current_weights.keys():
                optimized[asset] = 0.0
            optimized["money_market"] = 1.0

        # Enforce Life Path Equity Ceiling (Risk Cap based on user age / risk profile)
        if equity_cap is not None and equity_cap > 0:
            equity_assets = [a for a in ["thai_equity", "global_equity"] if a in optimized]
            current_equity_sum = sum(optimized[a] for a in equity_assets)
            if current_equity_sum > equity_cap and current_equity_sum > 0:
                scale = equity_cap / current_equity_sum
                excess = current_equity_sum - equity_cap
                for a in equity_assets:
                    optimized[a] = optimized[a] * scale
                # Park excess safely in fixed income or money market
                safe_haven = "fixed_income" if "fixed_income" in optimized else "money_market"
                optimized[safe_haven] = optimized.get(safe_haven, 0.0) + excess

        total_w = sum(optimized.values())
        if total_w > 0:
            for a in optimized.keys():
                optimized[a] = round(optimized[a] / total_w, 3)

            residual = 1.0 - sum(optimized.values())
            if abs(residual) > 0.0001:
                max_asset = max(optimized, key=optimized.get)
                optimized[max_asset] = round(optimized[max_asset] + residual, 3)

        return optimized

    def calculate_weighted_score(
        self,
        weights: Dict[str, float],
        signals: Dict[str, Dict[str, Any]]
    ) -> float:
        """Calculates the overall weighted composite score for a given portfolio allocation."""
        total_score = 0.0
        total_weight = sum(weights.values())
        if total_weight <= 0:
            return 50.0

        for asset, w in weights.items():
            score = signals.get(asset, {}).get("composite_score", 50.0)
            total_score += w * score

        return total_score / total_weight

    def evaluate_opportunity(
        self,
        current_weights: Dict[str, float],
        signals: Dict[str, Dict[str, Any]],
        quota_used_this_year: int,
        last_rebalance_date: Optional[datetime] = None,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluates whether an opportunistic rebalance is justified.
        Returns a dict containing opportunity flags, score delta, and adjustments.
        """
        year_now = datetime.now().year
        quota_remaining = max(0, self.max_rebalances - quota_used_this_year)
        quota_status = {
            "year": year_now,
            "max_allowed": self.max_rebalances,
            "used": quota_used_this_year,
            "remaining": quota_remaining
        }

        # 1. Quota Check: If no quota left this calendar year, no opportunity can be acted on
        if quota_remaining <= 0:
            return {
                "is_opportunity": False,
                "reason": f"โควตาการเปลี่ยนแผนการลงทุนปี {year_now} ครบ 12 ครั้งแล้ว (ไม่สามารถปรับเพิ่มได้)",
                "opportunity_type": "QUOTA_EXHAUSTED",
                "current_score": 0.0,
                "optimized_score": 0.0,
                "score_delta": 0.0,
                "optimized_weights": current_weights,
                "adjustments": [],
                "quota_status": quota_status,
                "user_profile": user_profile
            }

        # 2. Compute current and optimized portfolio metrics with Life Path Equity Cap
        equity_cap = user_profile.get("equity_cap") if user_profile else None
        optimized_weights = self.calculate_optimized_weights(current_weights, signals, equity_cap=equity_cap)
        current_score = self.calculate_weighted_score(current_weights, signals)
        optimized_score = self.calculate_weighted_score(optimized_weights, signals)
        score_delta = optimized_score - current_score

        # Calculate adjustments
        adjustments = []
        total_weight_diff = 0.0
        for asset, curr_w in current_weights.items():
            opt_w = optimized_weights.get(asset, 0.0)
            diff = opt_w - curr_w
            if abs(diff) > 0.01:  # >= 1% change
                total_weight_diff += abs(diff)
                adjustments.append({
                    "asset": asset,
                    "asset_name": ASSET_NAMES.get(asset, asset),
                    "current_weight": curr_w,
                    "target_weight": opt_w,
                    "diff": diff,
                    "diff_pct": diff * 100
                })

        # Sort adjustments by largest change
        adjustments.sort(key=lambda x: abs(x["diff"]), reverse=True)

        # 3. Check for severe risk (Capital Preservation)
        critical_risk_assets = []
        for asset, curr_w in current_weights.items():
            if curr_w >= 0.08:  # Holds >= 8% in this asset
                sig_data = signals.get(asset, {})
                if sig_data.get("signal") == "REDUCE":
                    critical_risk_assets.append(ASSET_NAMES.get(asset, asset))

        # 4. Check for high momentum profit opportunity (Alpha Momentum)
        top_momentum_assets = []
        for asset, opt_w in optimized_weights.items():
            curr_w = current_weights.get(asset, 0.0)
            sig_data = signals.get(asset, {})
            if sig_data.get("signal") == "BUY_HOLD" and sig_data.get("composite_score", 0) >= 70.0:
                if (opt_w - curr_w) >= 0.05:  # AI recommends increasing by >= 5%
                    top_momentum_assets.append(
                        f"{ASSET_NAMES.get(asset, asset)} (คะแนน {sig_data.get('composite_score', 0):.1f})"
                    )

        # 5. Cooldown check (prevent repeated alerts within 5 days unless critical risk)
        is_in_cooldown = False
        days_since = None
        if last_rebalance_date:
            days_since = (datetime.now() - last_rebalance_date).days
            if days_since < COOLDOWN_DAYS and not critical_risk_assets:
                is_in_cooldown = True

        if is_in_cooldown:
            return {
                "is_opportunity": False,
                "reason": f"เพิ่งปรับพอร์ตไปเมื่อ {days_since} วันก่อน (อยู่ในช่วง Cooldown {COOLDOWN_DAYS} วันเพื่อถนอมโควตา 12 ครั้ง)",
                "opportunity_type": "COOLDOWN",
                "current_score": current_score,
                "optimized_score": optimized_score,
                "score_delta": score_delta,
                "optimized_weights": optimized_weights,
                "adjustments": adjustments,
                "quota_status": quota_status
            }

        # 6. Opportunity Decision Matrix
        # Condition A: Emergency Capital Preservation
        if critical_risk_assets:
            reason = f"ตรวจพบความเสี่ยงสูงใน {', '.join(critical_risk_assets)} (สัญญาณ REDUCE) แนะนำหมุนเงินเพื่อรักษาเงินต้นและกำไรสะสม"
            return {
                "is_opportunity": True,
                "opportunity_type": "CAPITAL_PRESERVATION",
                "reason": reason,
                "current_score": current_score,
                "optimized_score": optimized_score,
                "score_delta": score_delta,
                "optimized_weights": optimized_weights,
                "adjustments": adjustments,
                "quota_status": quota_status
            }

        # Condition B: Strong Momentum Profit Opportunity (Score delta >= 8.0 or weight shift >= 15% with top assets)
        if score_delta >= SCORE_IMPROVEMENT_THRESHOLD and top_momentum_assets:
            reason = f"ตรวจพบจังหวะเร่งสร้างกำไรใน {', '.join(top_momentum_assets)} การปรับพอร์ตจะยกระดับคะแนนพอร์ตขึ้นถึง +{score_delta:.1f} คะแนน"
            return {
                "is_opportunity": True,
                "opportunity_type": "PROFIT_MOMENTUM",
                "reason": reason,
                "current_score": current_score,
                "optimized_score": optimized_score,
                "score_delta": score_delta,
                "optimized_weights": optimized_weights,
                "adjustments": adjustments,
                "quota_status": quota_status
            }

        # Condition C: Significant structural rebalance opportunity
        if (total_weight_diff / 2.0) >= SIGNIFICANT_WEIGHT_SHIFT_THRESHOLD and score_delta >= 5.0:
            reason = f"สภาวะตลาดเปลี่ยนทิศทางอย่างมีนัยสำคัญ การปรับโครงสร้างพอร์ต (+{score_delta:.1f} คะแนน) จะช่วยเพิ่มประสิทธิภาพการลงทุนอย่างชัดเจน"
            return {
                "is_opportunity": True,
                "opportunity_type": "BALANCED_GROWTH",
                "reason": reason,
                "current_score": current_score,
                "optimized_score": optimized_score,
                "score_delta": score_delta,
                "optimized_weights": optimized_weights,
                "adjustments": adjustments,
                "quota_status": quota_status
            }

        # Not enough conviction to spend 1 of 12 annual quotas
        return {
            "is_opportunity": False,
            "reason": f"คะแนนพอร์ตปัจจุบันอยู่ในเกณฑ์ที่เหมาะสม (ผลต่าง +{score_delta:.1f} คะแนน ยังไม่คุ้มค่ากับการใช้โควตา 1 ใน 12 ครั้ง)",
            "opportunity_type": "NONE",
            "current_score": current_score,
            "optimized_score": optimized_score,
            "score_delta": score_delta,
            "optimized_weights": optimized_weights,
            "adjustments": adjustments,
            "quota_status": quota_status
        }

    def format_alert_message(self, opportunity: Dict[str, Any], dashboard_url: str = "http://localhost:3000") -> str:
        """Formats a rich notification message for Telegram and LINE."""
        quota = opportunity["quota_status"]
        score_delta = opportunity["score_delta"]
        curr_score = opportunity["current_score"]
        opt_score = opportunity["optimized_score"]
        opp_type = opportunity.get("opportunity_type", "PROFIT_MOMENTUM")

        badge = "🎯 *[ตรวจพบโอกาสปรับแผนการลงทุน กบข.]*"
        if opp_type == "CAPITAL_PRESERVATION":
            badge = "🛡️ *[แจ้งเตือนด่วน: ปรับพอร์ตเพื่อลดความเสี่ยงและรักษาเงินต้น]*"

        adj_lines = []
        for adj in opportunity["adjustments"]:
            pct = adj["diff_pct"]
            if pct > 0:
                adj_lines.append(f"📈 เพิ่ม {adj['asset_name']}: +{pct:.1f}%")
            else:
                adj_lines.append(f"📉 ลด {adj['asset_name']}: {pct:.1f}%")

        adj_text = "\n".join(adj_lines) if adj_lines else "• คงสัดส่วนเดิม"

        msg = (
            f"{badge}\n\n"
            f"💡 *สัญญาณ AI:* {opportunity['reason']}\n\n"
            f"📊 *สิทธิ์การเปลี่ยนแผนปี {quota['year']}:* "
            f"ใช้ไปแล้ว *{quota['used']}/{quota['max_allowed']}* ครั้ง "
            f"(คงเหลืออีก *{quota['remaining']}* ครั้ง)\n\n"
            f"📈 *ศักยภาพพอร์ตภาพรวม:* "
            f"{curr_score:.1f} ➔ *{opt_score:.1f}* "
            f"({'+' if score_delta >= 0 else ''}{score_delta:.1f} คะแนน)\n\n"
            f"🔄 *สัดส่วนที่แนะนำปรับเปลี่ยน:*\n"
            f"{adj_text}\n\n"
            f"⚡ *ขั้นตอนการดำเนินการ:*\n"
            f"1. เข้าแอป My GPF (กบข.) แล้วปรับสัดส่วนตามคำแนะนำข้างต้น\n"
            f"2. กดยืนยันใน Dashboard เพื่อบันทึกประวัติและนับโควตา:\n"
            f"🔗 [เปิด Dashboard กดยืนยันปรับแผน]({dashboard_url})\n\n"
            f"⚠️ _หมายเหตุ: เป็นการประมวลผลเชิงปริมาณเพื่อช่วยสนับสนุนการตัดสินใจของท่าน_"
        )
        return msg
