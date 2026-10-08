"""
XGBoost trainer for risk scoring.
Uses heuristic scores as weak labels.
"""
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score
import xgboost as xgb
from loguru import logger

from src.ml.features import get_extractor, FeatureExtractor


MODEL_PATH = "models/risk_model.pkl"


async def train_model(sample_size: int = 50000) -> dict:
    """Full training pipeline: extract → split → train → evaluate → save."""
    logger.info("🧠 Starting XGBoost training pipeline")

    extractor = get_extractor()
    df = await extractor.extract_for_training(limit=sample_size)

    if len(df) < 100:
        raise ValueError(f"Not enough data to train: {len(df)} rows")

    df["label"] = (df["risk_score"] >= 20).astype(int)
    logger.info(f"Label distribution: {df['label'].value_counts().to_dict()}")

    X = df[FeatureExtractor.FEATURE_COLUMNS].values
    y = df["label"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    logger.info(f"Train: {len(X_train)}, Test: {len(X_test)}")

    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
    )

    logger.info("Training XGBoost...")
    model.fit(X_train, y_train)

    y_pred_proba = model.predict_proba(X_test)[:, 1]
    y_pred = (y_pred_proba >= 0.5).astype(int)

    auc = roc_auc_score(y_test, y_pred_proba)
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

    logger.success(f"✅ Training complete. AUC: {auc:.4f}")
    logger.info(f"Precision: {report['1']['precision']:.3f}")
    logger.info(f"Recall: {report['1']['recall']:.3f}")
    logger.info(f"F1: {report['1']['f1-score']:.3f}")

    os.makedirs("models", exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    logger.success(f"💾 Model saved to {MODEL_PATH}")

    importances = dict(zip(
        FeatureExtractor.FEATURE_COLUMNS,
        model.feature_importances_.tolist()
    ))
    top_features = sorted(importances.items(), key=lambda x: -x[1])[:5]
    logger.info("📊 Top 5 features:")
    for name, imp in top_features:
        logger.info(f"   {name}: {imp:.4f}")

    return {
        "auc": round(auc, 4),
        "precision": round(report['1']['precision'], 4),
        "recall": round(report['1']['recall'], 4),
        "f1": round(report['1']['f1-score'], 4),
        "train_size": len(X_train),
        "test_size": len(X_test),
        "model_path": MODEL_PATH,
        "top_features": top_features,
    }


def load_model():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}. Run training first.")
    return joblib.load(MODEL_PATH)


def predict_single(features: dict) -> dict:
    model = load_model()
    X = np.array([[features[col] for col in FeatureExtractor.FEATURE_COLUMNS]])
    proba = model.predict_proba(X)[0, 1]
    return {
        "label": int(proba >= 0.5),
        "probability": float(proba),
    }
