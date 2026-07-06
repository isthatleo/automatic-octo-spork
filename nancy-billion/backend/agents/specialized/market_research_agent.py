"""
Market Research Agent for Nancy Billion Backend
Real statistical analysis for consumer insights and competitive analysis
"""
from .base_specialized_agent import SpecializedAgent
from .. import real_compute as rc
from typing import Dict, Any, List
import numpy as np
import math


_SENTIMENT_LEXICON: Dict[str, float] = {
    "excellent": 0.9, "great": 0.8, "good": 0.6, "positive": 0.7,
    "amazing": 0.9, "love": 0.8, "wonderful": 0.8, "best": 0.9,
    "satisfied": 0.6, "happy": 0.7, "impressed": 0.7, "recommend": 0.6,
    "poor": -0.6, "bad": -0.7, "terrible": -0.9, "awful": -0.9,
    "hate": -0.8, "worst": -0.9, "horrible": -0.9, "disappointed": -0.6,
    "frustrating": -0.6, "useless": -0.7, "broken": -0.6, "slow": -0.4,
    "expensive": -0.3, "cheap": 0.2, "affordable": 0.5, "quality": 0.5,
    "reliable": 0.6, "innovative": 0.7, "convenient": 0.5, "efficient": 0.6,
    "friendly": 0.5, "helpful": 0.5, "fast": 0.4, "easy": 0.4,
    "complicated": -0.3, "difficult": -0.4, "confusing": -0.5,
}


class MarketResearchAgent(SpecializedAgent):
    """Specialized agent for market research"""

    def __init__(self, settings):
        super().__init__(settings, "Market Research Agent", "market-research")
        self.capabilities.update({
            "description": "Advanced market research agent for consumer insights and competitive analysis",
            "confidence": 0.87,
            "specializations": [
                "consumer-behavior",
                "competitive-analysis",
                "market-trends"
            ],
            "tools": [
                "survey-tools",
                "analytics-platforms",
                "social-media-listening"
            ]
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process market research tasks"""
        task_type = task_data.get("type", "market-overview")

        if task_type == "consumer-insights":
            return await self._get_consumer_insights(task_data)
        elif task_type == "competitive-analysis":
            return await self._analyze_competitors(task_data)
        else:
            return await self._general_research_overview(task_data)

    async def _get_consumer_insights(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get consumer behavior insights with real cluster analysis and sentiment"""
        target_audience = params.get("audience", "general_consumers")
        survey_data = params.get("survey_data", None)
        survey_features = params.get("survey_features", None)
        review_texts = params.get("review_texts", None)

        segmentation = None
        if survey_data and isinstance(survey_data, list) and len(survey_data) > 0:
            if isinstance(survey_data[0], list) and len(survey_data[0]) >= 2:
                labels, centroids = rc.kmeans_cluster(survey_data, k=min(3, len(survey_data)))
                if labels:
                    cluster_counts: Dict[int, int] = {}
                    for lbl in labels:
                        cluster_counts[lbl] = cluster_counts.get(lbl, 0) + 1
                    segmentation = {
                        "k": len(centroids),
                        "cluster_centroids": centroids,
                        "cluster_sizes": {int(k): int(v) for k, v in cluster_counts.items()},
                        "labels": [int(l) for l in labels],
                    }
            elif isinstance(survey_data[0], (int, float)):
                stats = rc.compute_statistics(survey_data)
                segmentation = {"statistics": stats}

        sentiment_results = None
        if review_texts and isinstance(review_texts, list):
            sentiments = []
            for text in review_texts:
                score = _compute_sentiment(text)
                sentiments.append(score)
            if sentiments:
                sent_stats = rc.compute_statistics(sentiments)
                sentiment_results = {
                    "mean_sentiment": sent_stats["mean"],
                    "std_sentiment": sent_stats["std"],
                    "positive_ratio": round(len([s for s in sentiments if s > 0.1]) / len(sentiments), 4) if sentiments else 0,
                    "negative_ratio": round(len([s for s in sentiments if s < -0.1]) / len(sentiments), 4) if sentiments else 0,
                    "neutral_ratio": round(len([s for s in sentiments if -0.1 <= s <= 0.1]) / len(sentiments), 4) if sentiments else 0,
                }

        return {
            "success": True,
            "task_type": "consumer-insights",
            "target_audience": target_audience,
            "segmentation": segmentation,
            "sentiment_analysis": sentiment_results,
            "purchase_journey": {
                "awareness": "social_media_search_reviews",
                "consideration": "price_features_comparison",
                "purchase": "promotions_availability",
                "post_purchase": "product_use_feedback_sharing"
            },
            "recommendations": [
                "Focus on value proposition rather than just features",
                "Build trust through transparency and consistency",
                "Optimize mobile experience for on-the-go consumers",
                "Leverage social proof and user-generated content"
            ]
        }

    async def _analyze_competitors(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze competitive landscape with real scoring"""
        industry = params.get("industry", "technology")
        competitor_scores = params.get("competitor_scores", None)
        competitor_names = params.get("competitor_names", None)
        weights = params.get("weights", {"market_share": 0.3, "innovation": 0.25, "pricing": 0.2, "quality": 0.15, "distribution": 0.1})

        competitors = []
        if competitor_scores and isinstance(competitor_scores, list) and len(competitor_scores) > 0:
            scores_arr = np.array(competitor_scores, dtype=np.float64)
            if scores_arr.ndim == 1:
                scores_arr = scores_arr.reshape(-1, 1)

            w = np.array([weights.get(k, 0.2) for k in ["market_share", "innovation", "pricing", "quality", "distribution"]])
            w = w / (np.sum(w) + 1e-12)

            for i in range(min(scores_arr.shape[0], len(competitor_names) if competitor_names else scores_arr.shape[0])):
                row = scores_arr[i]
                if len(row) < len(w):
                    row_padded = np.pad(row, (0, len(w) - len(row)), constant_values=0.5)
                else:
                    row_padded = row[:len(w)]
                composite = float(np.dot(row_padded, w))

                n = len(competitor_names) if competitor_names else 0
                name = competitor_names[i] if competitor_names and i < n else f"Competitor_{i}"
                strengths = []
                weaknesses = []
                for j, dim in enumerate(["market_share", "innovation", "pricing", "quality", "distribution"]):
                    val = float(row_padded[j]) if j < len(row_padded) else 0.5
                    if val > 0.7:
                        strengths.append(dim)
                    elif val < 0.3:
                        weaknesses.append(dim)
                competitors.append({
                    "name": name,
                    "composite_score": round(composite, 4),
                    "dimension_scores": {
                        k: round(float(row_padded[j]), 4) for j, k in enumerate(["market_share", "innovation", "pricing", "quality", "distribution"]) if j < len(row_padded)
                    },
                    "strengths": strengths,
                    "weaknesses": weaknesses,
                })

            if competitors:
                ranked = sorted(competitors, key=lambda c: c["composite_score"], reverse=True)
                for rank, comp in enumerate(ranked, 1):
                    comp["rank"] = rank
                competitors = ranked

        return {
            "success": True,
            "task_type": "competitive-analysis",
            "industry": industry,
            "competitors": competitors,
            "market_dynamics": {
                "num_competitors": len(competitors),
                "top_score": competitors[0]["composite_score"] if competitors else 0.0,
                "spread": round(max(c["composite_score"] for c in competitors) - min(c["composite_score"] for c in competitors), 4) if len(competitors) > 1 else 0.0,
            },
            "recommendations": [
                "Differentiate through unique value proposition",
                "Monitor competitor pricing strategies",
                "Identify and exploit competitor weaknesses",
                "Consider strategic partnerships or acquisitions"
            ]
        }

    async def _general_research_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Provide general market research overview"""
        return {
            "success": True,
            "task_type": "general-market-research",
            "query": params.get("query", "general market research"),
            "key_indicators": [
                "market_size_growth",
                "consumer_confidence",
                "employment_trends",
                "interest_rates"
            ],
            "methodologies": [
                "surveys_and_questionnaires",
                "focus_groups_and_interviews",
                "observational_studies",
                "secondary_data_analysis"
            ],
            "recommendations": [
                "Define clear research objectives",
                "Use multiple data sources for triangulation",
                "Consider temporal and seasonal factors",
                "Validate findings with multiple approaches"
            ]
        }


def _compute_sentiment(text: str) -> float:
    """Compute real sentiment score from text using a lexicon approach."""
    words = text.lower().split()
    scores = []
    for word in words:
        word_clean = word.strip(".,!?;:'\"()[]")
        if word_clean in _SENTIMENT_LEXICON:
            scores.append(_SENTIMENT_LEXICON[word_clean])
    if not scores:
        return 0.0
    negators = {"not", "no", "never", "neither", "nor", "none", "n't", "hardly", "barely"}
    adjusted = []
    for i, w in enumerate(words):
        if i > 0 and words[i - 1] in negators:
            multiplier = -1.0
        elif i > 1 and words[i - 2] in negators:
            multiplier = -0.7
        else:
            multiplier = 1.0
        clean = w.strip(".,!?;:'\"()[]")
        if clean in _SENTIMENT_LEXICON:
            adjusted.append(_SENTIMENT_LEXICON[clean] * multiplier)
    if not adjusted:
        return 0.0
    return round(float(np.mean(adjusted)), 4)
