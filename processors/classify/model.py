from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import pandas as pd
from features import FeaturesExtractor
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder


class RFModel:
    def __init__(self) -> None:
        self._model = None
        self._features = None
        self._label_encoder = None

    @property
    def model(self):
        return self._model

    @property
    def encoder(self):
        return self._label_encoder

    @property
    def feature_names(self):
        return self._features

    def train(self, df, feature_cols, target_col="label"):
        X = df[feature_cols].fillna(0)
        y = df[target_col]

        self._label_encoder = LabelEncoder()
        y_encoded = self._label_encoder.fit_transform(y)

        self._model = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=5,
            random_state=42,
            n_jobs=-1,
        )
        self._model.fit(X, y_encoded)
        self._features = feature_cols

        # print(f"Модель обучена на {len(X)} примерах")
        # print(f"Классы: {self.label_encoder.classes_}")
        # print(f"Важность признаков (топ-5):")
        # importance = dict(zip(self.feature_names, self.model.feature_importances_))
        # for k, v in sorted(importance.items(), key=lambda x: x[1], reverse=True)[:5]:
        #     print(f"  {k}: {v:.3f}")

        return self

    def save(self, filepath="model.joblib") -> None:
        if self._model is None or self._features is None or self._label_encoder is None:
            raise ValueError("Model not loaded, run train() or load() first")

        model = {
            "model": self._model,
            "features": self._features,
            "encoder": self._label_encoder,
        }
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, filepath)

    def load(self, filepath="model.joblib") -> None:
        if Path(filepath).exists():
            model_data = joblib.load(filepath)
            self._model = model_data["model"]
            self._features = model_data["features"]
            self._label_encoder = model_data["encoder"]
        else:
            raise ValueError("Model weights not found")

    def predict(
        self, features: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[int], List[float]]:
        if self._model is None or self._features is None or self._label_encoder is None:
            raise ValueError("Model not loaded, run train() or load() first")

        X = pd.DataFrame(features).fillna(0)[self._features]
        y_pred_encoded = self._model.predict(X)
        y_pred = self._label_encoder.inverse_transform(y_pred_encoded)

        y_proba = self._model.predict_proba(X)
        class_indexes = self._label_encoder.transform(y_pred)
        y_proba = [float(proba[idx]) for proba, idx in zip(y_proba, class_indexes)]
        return y_pred, class_indexes, y_proba


def decide_by_thresholds(
    classes: List[str], indexes: List[int], proba: List[float], threshold: float = 0.75
) -> List[Tuple[str, Optional[int], str, float]]:
    res = []
    for cls, idx, prob in zip(classes, indexes, proba):
        if prob >= threshold:
            res.append((cls, idx, "classified", proba))
        else:
            res.append(("review", None, "review", proba))
    return res


def train() -> None:
    datapath = Path("~/Projects/OrdersAgent/private/mails/emails_parsed.parquet")
    df = pd.read_parquet(datapath)

    # df["label"] = df["label"].replace("unknown", "review")
    # df.to_parquet(datapath)

    features_data = []
    for row in df.iterrows():
        row = row[1]
        subject = row["subject"]
        body = row["body"]
        files = row["files"].split("|")
        text = subject + "\n\n" + "\n".join(files) + "\n\n" + body
        features = FeaturesExtractor.extract_text_features(text)
        files_features = FeaturesExtractor.extract_files_features(files)

        features.update(files_features)
        features["label"] = row["label"]
        features_data.append(features)

    features_df = pd.DataFrame(features_data)

    model = RFModel()
    model.train(features_df, features_df.drop(["label"], axis=1).columns)

    model.save()


def development() -> None:
    model = RFModel()
    model.load()

    datapath = Path("~/Projects/OrdersAgent/private/mails/emails_parsed.parquet")
    df = pd.read_parquet(datapath)

    features_data = []
    for row in df.iterrows():
        row = row[1]
        subject = row["subject"]
        body = row["body"]
        files = row["files"].split("|")
        text = subject + "\n\n" + "\n".join(files) + "\n\n" + body
        features = FeaturesExtractor.extract_text_features(text)
        files_features = FeaturesExtractor.extract_files_features(files)

        features.update(files_features)
        features["label"] = row["label"]
        features_data.append(features)

    predicted_class, _, predicted_proba = model.predict(features_data)
    print(predicted_class)
    print(predicted_proba)


if __name__ == "__main__":
    # train()
    development()
