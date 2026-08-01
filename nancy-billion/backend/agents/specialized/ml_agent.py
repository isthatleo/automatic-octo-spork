"""
Machine Learning Agent for Nancy/Billion.

Real, CPU-bounded machine learning: trains and maintains a scikit-learn
text-classification pipeline (TF-IDF + a linear classifier) that predicts
which specialist domain a message belongs to, learned from Nancy's own real
conversation history rather than a synthetic/fabricated dataset.

Honest about where the labels come from: there is no existing human-labeled
dataset, so training examples are built by pairing each real historical user
message (conversation_log.recent_turns) with the domain agent_service's own
deterministic keyword router (_auto_route) would have picked for it. This is
a legitimate technique (imitation learning from a rule-based system) -- the
model starts by reproducing the keyword router's decisions, but a learned
classifier generalizes to phrasings the fixed keyword list doesn't cover,
and ModelTrainingAgent periodically retrains it as more real usage
accumulates. This agent owns the model artifact and its train/predict/status
logic; ModelTrainingAgent owns the training *lifecycle* (when to retrain,
dataset export, local-model personalization).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ml_models"
CLASSIFIER_PATH = MODEL_DIR / "domain_classifier.joblib"
MIN_TRAINING_EXAMPLES = 25


class MLAgent(SpecializedAgent):
    """Real scikit-learn model training/serving, not just an LLM wrapper."""

    def __init__(self, settings):
        super().__init__(settings, "ML Agent", "machine-learning")
        self.capabilities.update({
            "description": (
                "Trains and serves a real scikit-learn text classifier from Nancy's own "
                "conversation history to predict which specialist domain a message needs"
            ),
            "confidence": 0.85,
            "specializations": ["text-classification", "intent-routing", "model-training", "tfidf"],
            "tools": ["scikit-learn", "joblib"],
        })
        self._pipeline = None  # lazily loaded from disk
        self._metrics: Dict[str, Any] = {}

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "train":
            return self._train()
        if task_type == "predict":
            return self._predict(task_data.get("text", ""))
        if task_type == "status":
            return self._status()
        if task_type == "query":
            return await self._general_ml(task_data)
        return await self._general_ml(task_data)

    # -- model I/O -----------------------------------------------------------

    def _load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        try:
            import joblib
            if CLASSIFIER_PATH.exists():
                self._pipeline = joblib.load(CLASSIFIER_PATH)
                logger.info("MLAgent: loaded existing classifier from %s", CLASSIFIER_PATH)
        except Exception as e:
            logger.warning("MLAgent: could not load existing classifier: %s", e)
        return self._pipeline

    def _build_training_set(self) -> Tuple[List[str], List[str]]:
        """Real historical user messages, pseudo-labeled by the existing
        deterministic keyword router. Messages the router can't classify
        (no keyword match) are excluded -- they'd just be noise for a
        supervised classifier, not a real signal either way."""
        import conversation_log
        from agents.agent_service import _auto_route

        texts, labels = [], []
        for text in conversation_log.recent_turns(role="user", limit=2000):
            label = _auto_route(text)
            if label:
                texts.append(text)
                labels.append(label)
        return texts, labels

    def _train(self) -> Dict[str, Any]:
        texts, labels = self._build_training_set()
        if len(texts) < MIN_TRAINING_EXAMPLES:
            return {
                "success": False,
                "error": f"Not enough labeled real conversation data yet ({len(texts)}/{MIN_TRAINING_EXAMPLES} minimum)",
                "examples_available": len(texts),
            }
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.model_selection import train_test_split
            from sklearn.pipeline import Pipeline
            from sklearn.metrics import accuracy_score
            import joblib

            unique_labels = set(labels)
            stratify = labels if len(texts) >= 10 and all(labels.count(l) >= 2 for l in unique_labels) else None
            X_train, X_test, y_train, y_test = train_test_split(
                texts, labels, test_size=0.2, random_state=42, stratify=stratify,
            )
            pipeline = Pipeline([
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=5000)),
                ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
            ])
            pipeline.fit(X_train, y_train)
            accuracy = accuracy_score(y_test, pipeline.predict(X_test)) if X_test else None

            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            joblib.dump(pipeline, CLASSIFIER_PATH)
            self._pipeline = pipeline
            self._metrics = {
                "trained_at": time.time(),
                "training_examples": len(texts),
                "unique_domains": len(unique_labels),
                "holdout_accuracy": round(float(accuracy), 4) if accuracy is not None else None,
            }
            logger.info(
                "MLAgent: trained domain classifier on %d real examples across %d domains, holdout accuracy=%s",
                len(texts), len(unique_labels), self._metrics["holdout_accuracy"],
            )
            return {"success": True, **self._metrics}
        except Exception as e:
            logger.exception("MLAgent: training failed")
            return {"success": False, "error": str(e)}

    def _predict(self, text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"success": False, "error": "text is required"}
        pipeline = self._load_pipeline()
        if pipeline is None:
            return {"success": False, "error": "No trained model yet -- run a 'train' task first"}
        try:
            predicted = pipeline.predict([text])[0]
            proba = None
            if hasattr(pipeline, "predict_proba"):
                probs = pipeline.predict_proba([text])[0]
                proba = round(float(max(probs)), 4)
            return {"success": True, "predicted_domain": predicted, "confidence": proba}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _status(self) -> Dict[str, Any]:
        pipeline = self._load_pipeline()
        texts, _ = self._build_training_set()
        return {
            "success": True,
            "model_trained": pipeline is not None,
            "model_path": str(CLASSIFIER_PATH) if pipeline is not None else None,
            "real_examples_available_now": len(texts),
            "last_training_metrics": self._metrics or None,
        }

    async def _general_ml(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        query = task_data.get("query") or task_data.get("text", "")
        answer = await self._llm_answer(query)
        if answer:
            return {"success": True, "response": answer}
        return {
            "success": True,
            "response": (
                "I'm the ML agent -- I train and serve a real scikit-learn classifier "
                "from your actual conversation history. Ask me to 'train', 'predict' a domain "
                "for some text, or check 'status' for the current model's metrics."
            ),
        }
