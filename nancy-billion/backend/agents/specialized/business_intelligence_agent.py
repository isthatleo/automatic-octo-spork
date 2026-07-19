"""
Business Intelligence Agent for Nancy Billion Backend
Handles KPI tracking, dashboards, and business analytics
"""
from .base_specialized_agent import SpecializedAgent
from .. import real_compute as rc
from typing import Dict, Any, List
import numpy as np


class BusinessIntelligenceAgent(SpecializedAgent):
    """Specialized agent for business intelligence and analytics"""

    def __init__(self, settings):
        super().__init__(settings, "Business Intelligence Agent", "business-intelligence")
        self.capabilities.update({
            "description": "Advanced business intelligence agent for KPI tracking, dashboard creation, and business analytics",
            "confidence": 0.89,
            "specializations": [
                "kpi-tracking",
                "dashboard-creation",
                "data-visualization",
                "trend-analysis",
                "forecasting",
                "drill-down-analysis",
                "benchmarking"
            ],
            "tools": [
                "tableau-powerbi",
                "looker-metabase",
                "qlik-sense",
                "superset-redash",
                "python-pandas",
                "r-shiny"
            ]
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process business intelligence tasks"""
        task_type = task_data.get("type", "kpi-report")

        if task_type == "kpi-dashboard":
            return await self._create_kpi_dashboard(task_data)
        elif task_type == "trend-analysis":
            return await self._analyze_business_trends(task_data)
        elif task_type == "forecasting":
            return await self._create_business_forecast(task_data)
        elif task_type == "profitability-analysis":
            return await self._analyze_profitability(task_data)
        else:
            return await self._general_bi_consultation(task_data)

    async def _create_kpi_dashboard(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create KPI dashboard with real computed metrics"""
        department = params.get("department", "sales")
        timeframe = params.get("timeframe", "monthly")

        revenue_data = params.get("revenue_data", None)
        customer_data = params.get("customer_data", None)
        cost_data = params.get("cost_data", None)

        kpis = []

        if revenue_data and isinstance(revenue_data, list) and len(revenue_data) > 1:
            rev_arr = np.array(revenue_data)
            current_rev = float(rev_arr[-1])
            prev_rev = float(rev_arr[0])
            growth = ((current_rev - prev_rev) / (abs(prev_rev) + 1e-12)) * 100
            rev_stats = rc.compute_statistics(revenue_data)
            kpis.append({
                "name": "Revenue",
                "current": round(current_rev, 2),
                "previous": round(prev_rev, 2),
                "growth_pct": round(growth, 2),
                "mean": rev_stats["mean"],
                "std": rev_stats["std"],
                "trend": "upward" if growth > 0 else "downward",
                "unit": "$",
            })

        if customer_data and isinstance(customer_data, list) and len(customer_data) > 1:
            cust_arr = np.array(customer_data)
            current_cust = float(cust_arr[-1])
            prev_cust = float(cust_arr[0])
            cust_growth = ((current_cust - prev_cust) / (abs(prev_cust) + 1e-12)) * 100
            cust_stats = rc.compute_statistics(customer_data)
            kpis.append({
                "name": "Customer Count",
                "current": int(current_cust),
                "previous": int(prev_cust),
                "growth_pct": round(cust_growth, 2),
                "mean": round(cust_stats["mean"], 1),
                "std": round(cust_stats["std"], 1),
                "trend": "upward" if cust_growth > 0 else ("downward" if cust_growth < 0 else "stable"),
                "unit": "customers",
            })

        if cost_data and isinstance(cost_data, list) and len(cost_data) > 1:
            cost_arr = np.array(cost_data)
            current_cost = float(cost_arr[-1])
            prev_cost = float(cost_arr[0])
            cost_change = ((current_cost - prev_cost) / (abs(prev_cost) + 1e-12)) * 100
            if revenue_data and len(revenue_data) > 1:
                margin = ((float(rev_arr[-1]) - current_cost) / (float(rev_arr[-1]) + 1e-12)) * 100
            else:
                margin = 0.0
            kpis.append({
                "name": "Operating Cost",
                "current": round(current_cost, 2),
                "change_pct": round(cost_change, 2),
                "profit_margin_pct": round(margin, 2),
                "trend": "increasing" if cost_change > 0 else ("decreasing" if cost_change < 0 else "stable"),
                "unit": "$",
            })

        outliers = []
        if revenue_data and isinstance(revenue_data, list):
            outlier_indices = rc.detect_outliers_iqr(revenue_data)
            if outlier_indices:
                outliers = [{"index": int(i), "value": float(revenue_data[i])} for i in outlier_indices]

        seasonality = None
        if revenue_data and isinstance(revenue_data, list) and len(revenue_data) >= 4:
            seasonality = rc.detect_seasonality(revenue_data)

        return {
            "success": True,
            "task_type": "kpi-dashboard",
            "department": department,
            "timeframe": timeframe,
            "kpis": kpis,
            "anomalies": outliers,
            "seasonality": seasonality,
            "recommendations": [
                "Focus on improving customer retention to reduce acquisition costs",
                "Invest in high-performing marketing channels",
                "Implement customer feedback loops for product improvement",
                "Consider pricing optimization strategies"
            ]
        }

    async def _analyze_business_trends(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze business trends using real regression and seasonality detection"""
        metric = params.get("metric", "sales")
        period = params.get("period", "12_months")
        values = params.get("values", None)

        if not values or not isinstance(values, list) or len(values) < 2:
            return {
                "success": True,
                "task_type": "trend-analysis",
                "metric": metric,
                "period": period,
                "error": "insufficient data provided",
                "recommendations": ["Provide at least 2 data points for trend analysis"]
            }

        n = len(values)
        x = list(range(n))
        regression = rc.linear_regression(x, values)
        stats = rc.compute_statistics(values)
        seasonality = rc.detect_seasonality(values) if n >= 4 else {"has_seasonality": False, "period": 1, "strength": 0.0}

        outlier_indices = rc.detect_outliers_iqr(values)
        anomalies = []
        for idx in outlier_indices:
            predicted = regression["slope"] * idx + regression["intercept"]
            deviation = ((values[idx] - predicted) / (abs(predicted) + 1e-12)) * 100
            anomalies.append({
                "period": f"period_{idx}",
                "value": values[idx],
                "predicted": round(predicted, 4),
                "deviation_pct": round(deviation, 2),
            })

        sma = rc.compute_moving_average(values, min(3, n))

        return {
            "success": True,
            "task_type": "trend-analysis",
            "metric": metric,
            "period": period,
            "statistics": stats,
            "regression": regression,
            "trend_analysis": {
                "direction": "upward" if regression["slope"] > 0.01 else ("downward" if regression["slope"] < -0.01 else "stable"),
                "strength": "strong" if abs(regression["r_squared"]) > 0.7 else ("moderate" if abs(regression["r_squared"]) > 0.4 else "weak"),
                "seasonality": seasonality,
                "volatility": {
                    "level": "low" if stats["std"] / (abs(stats["mean"]) + 1e-12) < 0.1 else ("medium" if stats["std"] / (abs(stats["mean"]) + 1e-12) < 0.3 else "high"),
                    "cv": round(stats["std"] / (abs(stats["mean"]) + 1e-12), 4),
                }
            },
            "sma": [round(v, 4) for v in sma],
            "anomalies": anomalies,
            "recommendations": [
                "Monitor leading indicators for early trend detection",
                "Consider external factors that may influence future performance",
                "Invest in customer retention to stabilize revenue base",
                "Review pricing strategy to maximize lifetime value"
            ]
        }

    async def _create_business_forecast(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create business forecasts using real time series methods"""
        forecast_horizon = params.get("horizon", 3)
        confidence_level = params.get("confidence", 0.95)
        values = params.get("values", None)

        if not values or not isinstance(values, list) or len(values) < 2:
            return {
                "success": True,
                "task_type": "forecasting",
                "error": "insufficient data provided",
                "recommendations": ["Provide at least 2 data points for forecasting"]
            }

        try:
            forecast_horizon = int(forecast_horizon)
        except (ValueError, TypeError):
            forecast_horizon = 3
        forecast_horizon = max(1, min(forecast_horizon, 24))

        n = len(values)
        x = list(range(n))
        regression = rc.linear_regression(x, values)
        stats = rc.compute_statistics(values)
        sma = rc.compute_moving_average(values, min(3, n))
        ema = rc.compute_ema(values, min(5, n))

        last_sma = float(np.mean(sma[-3:])) if len(sma) >= 3 else float(sma[-1]) if len(sma) > 0 else float(values[-1])
        last_ema = ema[-1] if len(ema) > 0 else float(values[-1])

        forecasts = []
        for i in range(1, forecast_horizon + 1):
            idx = n + i - 1
            linear_pred = regression["slope"] * idx + regression["intercept"]
            sma_factor = last_sma / (abs(last_sma) + 1e-12)
            ema_adjustment = (values[-1] - last_ema) * 0.3
            combined = linear_pred + ema_adjustment

            residual_std = stats["std"] * 0.5
            z = 1.96 if confidence_level >= 0.95 else 1.645
            ci_lower = combined - z * residual_std * math.sqrt(1 + 1.0 / n + (idx - n / 2.0) ** 2 / sum((j - n / 2.0) ** 2 for j in range(n)))
            ci_upper = combined + z * residual_std * math.sqrt(1 + 1.0 / n + (idx - n / 2.0) ** 2 / sum((j - n / 2.0) ** 2 for j in range(n)))

            forecasts.append({
                "period": f"forecast_{i}",
                "predicted_value": round(combined, 4),
                "confidence_interval": {
                    "lower": round(ci_lower, 4),
                    "upper": round(ci_upper, 4),
                }
            })

        return {
            "success": True,
            "task_type": "forecasting",
            "horizon": f"{forecast_horizon}_periods",
            "confidence_level": confidence_level,
            "methodology": "ensemble_linear_trend_with_smoothing",
            "statistics": stats,
            "regression": regression,
            "forecasts": forecasts,
            "recommendations": [
                "Regularly update forecasts with actual performance data",
                "Monitor key leading indicators for early warning signs",
                "Develop contingency plans for high-risk scenarios",
                "Communicate forecast assumptions and limitations clearly"
            ]
        }

    async def _analyze_profitability(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze profitability using real revenue and cost data"""
        analysis_type = params.get("type", "product")
        segments_revenue = params.get("segments_revenue", None)
        segments_cost = params.get("segments_cost", None)
        segment_names = params.get("segment_names", None)

        profitability = []
        if segments_revenue and segments_cost and isinstance(segments_revenue, list) and isinstance(segments_cost, list):
            n_seg = min(len(segments_revenue), len(segments_cost))
            revenues = np.array(segments_revenue[:n_seg])
            costs = np.array(segments_cost[:n_seg])
            profits = revenues - costs
            margins = np.where(revenues > 0, (profits / revenues) * 100, 0.0)
            rank_order = np.argsort(-profits)

            for rank, idx in enumerate(rank_order):
                name = segment_names[idx] if segment_names and idx < len(segment_names) else f"Segment_{idx}"
                profitability.append({
                    "segment": name,
                    "revenue": round(float(revenues[idx]), 2),
                    "cost": round(float(costs[idx]), 2),
                    "profit": round(float(profits[idx]), 2),
                    "margin_pct": round(float(margins[idx]), 2),
                    "rank": rank + 1,
                })

            total_rev = float(np.sum(revenues))
            total_cost = float(np.sum(costs))
            total_profit = total_rev - total_cost
            overall_margin = ((total_profit) / (total_rev + 1e-12)) * 100
        else:
            total_rev = 0.0
            total_cost = 0.0
            total_profit = 0.0
            overall_margin = 0.0

        return {
            "success": True,
            "task_type": "profitability-analysis",
            "analysis_type": analysis_type,
            "profitability_analysis": profitability,
            "totals": {
                "total_revenue": round(total_rev, 2),
                "total_cost": round(total_cost, 2),
                "total_profit": round(total_profit, 2),
                "overall_margin_pct": round(overall_margin, 2),
            },
            "recommendations": [
                "Focus resources on high-margin, high-volume products",
                "Consider discontinuing or reworking low-margin products",
                "Investigate cost drivers for underperforming segments",
                "Test price elasticity for sensitive products"
            ]
        }

    async def _general_bi_consultation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Provide general business intelligence consultation"""
        query = params.get("query", "general BI question")
        answer = await self._llm_answer(query)
        return {
            "success": True,
            "task_type": "general-bi-consultation",
            "query": query,
            **({"response": answer} if answer else {}),
            "bi_lifecycle": [
                "data_collection",
                "data_integration",
                "data_storage",
                "data_analysis",
                "data_visualization",
                "insight_generation",
                "action_planning"
            ],
            "visualization_types": [
                {"type": "time_series", "use_cases": ["trend_analysis", "forecasting", "anomaly_detection"]},
                {"type": "bar_chart", "use_cases": ["comparison", "ranking", "distribution"]},
                {"type": "scatter_plot", "use_cases": ["correlation", "regression", "outlier_detection"]},
                {"type": "heatmap", "use_cases": ["correlation_matrix", "geographic_data", "usage_patterns"]},
                {"type": "funnel_chart", "use_cases": ["conversion_analysis", "sales_pipeline", "customer_journey"]}
            ],
            "recommendations": [
                "Start with clear business questions and objectives",
                "Ensure data quality and governance",
                "Choose appropriate visualization for message",
                "Tell a story with your data - context matters"
            ]
        }


import math
