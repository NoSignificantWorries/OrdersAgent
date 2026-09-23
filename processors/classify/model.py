from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False


class LightGBMModel:    
    def __init__(self) -> None:
        self._model = None
        self._label_encoder = None
    
    @property
    def model(self):
        return self._model
    
    @property
    def encoder(self):
        return self._label_encoder
    
    @property
    def feature_names(self):
        # Для совместимости с RF
        if self._model and hasattr(self._model, 'named_steps'):
            vectorizer = self._model.named_steps.get('tfidf')
            if vectorizer:
                return vectorizer.get_feature_names_out()
        return None
    
    def load(self, filepath: str = "model.joblib") -> None:
        path = Path(filepath)
        if not path.exists():
            raise ValueError(f"Model weights not found: {filepath}")
        
        self._model = joblib.load(path)
        
        from sklearn.preprocessing import LabelEncoder
        self._label_encoder = LabelEncoder()
        if hasattr(self._model, 'classes_'):
            self._label_encoder.classes_ = self._model.classes_
    
    def predict(
        self, features: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[int], List[float]]:
        if self._model is None:
            raise ValueError("Model not loaded, run load() first")
        
        if features and isinstance(features[0], dict):
            raise ValueError(
                "LightGBM model requires texts, not feature dictionaries. "
                "Please use predict_from_texts() method instead."
            )
        
        texts = features
        y_pred = self._model.predict(texts)
        y_proba = self._model.predict_proba(texts)
        max_proba = y_proba.max(axis=1)
        
        if hasattr(self._model, 'classes_'):
            class_indexes = [
                list(self._model.classes_).index(pred) 
                for pred in y_pred
            ]
        else:
            class_indexes = list(range(len(y_pred)))
        
        return list(y_pred), class_indexes, list(max_proba)
    
    def predict_from_texts(
        self, texts: List[str]
    ) -> Tuple[List[str], List[int], List[float]]:
        if self._model is None:
            raise ValueError("Model not loaded, run load() first")
        
        y_pred = self._model.predict(texts)
        y_proba = self._model.predict_proba(texts)
        max_proba = y_proba.max(axis=1)
        
        if hasattr(self._model, 'classes_'):
            class_indexes = [
                list(self._model.classes_).index(pred) 
                for pred in y_pred
            ]
        else:
            class_indexes = list(range(len(y_pred)))
        
        y_pred = [str(pred) for pred in y_pred]
        max_proba = [float(p) for p in max_proba]

        return list(y_pred), class_indexes, list(max_proba)
    
    def predict_proba(
        self, features: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[int], List[List[float]]]:
        if self._model is None:
            raise ValueError("Model not loaded, run load() first")
        
        texts = features
        y_pred = self._model.predict(texts)
        y_proba = self._model.predict_proba(texts)
        
        if hasattr(self._model, 'classes_'):
            class_indexes = [
                list(self._model.classes_).index(pred) 
                for pred in y_pred
            ]
        else:
            class_indexes = list(range(len(y_pred)))
        
        return list(y_pred), class_indexes, y_proba.tolist()
    
    def save(self, filepath: str = "model.joblib") -> None:
        if self._model is None:
            raise ValueError("Model not loaded")
        
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model, filepath)


class RFModel:
    # Старый класс для Random Forest (оставлен для совместимости)
    
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
    
    def load(self, filepath: str = "model.joblib") -> None:
        path = Path(filepath)
        if not path.exists():
            raise ValueError(f"Model weights not found: {filepath}")
        
        model_data = joblib.load(path)
        
        if isinstance(model_data, dict) and "model" in model_data:
            self._model = model_data["model"]
            self._features = model_data["features"]
            self._label_encoder = model_data["encoder"]
        else:
            raise ValueError(
                "This is a pipeline model. Use LightGBMModel instead of RFModel."
            )
    
    def predict(
        self, features: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[int], List[float]]:
        import pandas as pd
        
        if self._model is None or self._features is None or self._label_encoder is None:
            raise ValueError("Model not loaded")
        
        X = pd.DataFrame(features).fillna(0)[self._features]
        y_pred_encoded = self._model.predict(X)
        y_pred = self._label_encoder.inverse_transform(y_pred_encoded)
        
        y_proba = self._model.predict_proba(X)
        class_indexes = list(map(int, self._label_encoder.transform(y_pred)))
        y_proba = [float(proba[idx]) for proba, idx in zip(y_proba, class_indexes)]
        
        return list(y_pred), class_indexes, y_proba


def decide_by_thresholds(
    classes: List[str],
    indexes: List[int],
    proba: List[float],
    threshold: float = 0.65,
) -> List[Tuple[str, Optional[int], str, float]]:
    res = []
    for cls, idx, prob in zip(classes, indexes, proba):
        if prob >= threshold:
            res.append((cls, idx, "classified", prob))
        else:
            res.append(("review", None, "review", prob))
    return res


def train() -> None:
    import pandas as pd

    if not LIGHTGBM_AVAILABLE:
        print("LightGBM не установлен. Выполните: uv add lightgbm")
        return
    
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import Pipeline
    
    datapath = Path("~/Projects/OrdersAgent/private/mails/emails_parsed.parquet").expanduser()
    if not datapath.exists():
        print(f"Датасет не найден: {datapath}")
        return
    
    df = pd.read_parquet(datapath)
    
    texts = []
    labels = []
    for _, row in df.iterrows():
        subject = row["subject"]
        body = row["body"]
        files = row["files"].split("|") if isinstance(row["files"], str) else []
        text = subject + "\n\n" + "\n".join(files) + "\n\n" + body
        texts.append(text)
        labels.append(row["label"])
    
    model = Pipeline([
        ('tfidf', TfidfVectorizer(
            max_features=3000,
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.95,
            sublinear_tf=True,
        )),
        ('clf', lgb.LGBMClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.1,
            num_leaves=31,
            class_weight='balanced',
            verbose=-1,
            n_jobs=-1,
            random_state=42,
        ))
    ])
    
    print(f"Обучение на {len(texts)} примерах...")
    model.fit(texts, labels)
    
    output_path = Path("model.joblib")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_path)
    print(f"Модель сохранена: {output_path}")


def development() -> None:
    try:
        model = LightGBMModel()
        model.load()
        print("LightGBM модель загружена")
    except Exception as e:
        print(f"Ошибка загрузки LightGBM: {e}")
        return
    
    # Тест
    test_texts = [
        "Прошу рассчитать стоимость",
        "Подтверждаю заказ в работу",
        "Подскажите когда будет готов",
    ]
    
    predictions = model.predict_from_texts(test_texts)
    print("\nТестовые предсказания:")
    for text, pred, prob in zip(test_texts, predictions[0], predictions[2]):
        print(f"  {text[:40]:<40} → {pred} ({prob:.3f})")


if __name__ == "__main__":
    # train()
    development()