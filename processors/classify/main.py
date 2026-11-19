from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .features import FeaturesExtractor
from .model import RFModel, decide_by_thresholds


class TaskClass(str, Enum):
    REQUEST = "request"
    CALCULATION = "calculation"
    QUESTION = "question"
    CLAIM = "claim"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClassifyResult:
    decision: TaskClass
    class_index: int | None
    status: str
    proba: float


class ClassifyEmail:
    def __init__(self, path: Path | str) -> None:
        self.model = RFModel()
        self.model.load(path)

    def extract_features(self, text: str, files: list[str]) -> dict[str, Any]:
        text_feach = FeaturesExtractor.extract_text_features(text)
        files_feach = FeaturesExtractor.extract_files_features(files)
        text_feach.update(files_feach)
        return text_feach

    def detect_claim_class(self, text: str) -> bool:
        return "претензия" in text.lower()

    def run(self, text: str, files: list[str]) -> ClassifyResult:
        if self.detect_claim_class(text):
            return ClassifyResult(TaskClass.CLAIM, 4, "classified", 1.0)

        features = self.extract_features(text, files)
        pred_labels, pred_indexes, pred_proba = self.model.predict([features])
        model_decision, predicted_class, new_status, proba = decide_by_thresholds(pred_labels, pred_indexes, pred_proba)[0]

        match model_decision:
            case "request":
                cls = TaskClass.REQUEST
            case "calculation":
                cls = TaskClass.CALCULATION
            case "question":
                cls = TaskClass.QUESTION
            case "claim":
                cls = TaskClass.CLAIM
            case _:
                cls = TaskClass.UNKNOWN

        return ClassifyResult(cls, predicted_class, new_status, proba)
