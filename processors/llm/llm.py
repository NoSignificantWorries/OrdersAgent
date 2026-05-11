import unicodedata
from pathlib import Path

import torch
from peft import PeftConfig, PeftModel
from transformers import AutoModelForSequenceClassification, AutoTokenizer


class LLM:
    def __init__(self, model_path: str | Path) -> None:
        print("LLM init start")

        self.model_path = str(model_path)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print("device:", self.device)

        print("loading peft config...")
        peft_config = PeftConfig.from_pretrained(self.model_path)
        base_model_name = peft_config.base_model_name_or_path
        print("base model:", base_model_name)

        print("loading tokenizer...")
        self.tokenizer = AutoTokenizer.from_pretrained(base_model_name, use_fast=False)

        print("loading base model...")
        base_model = AutoModelForSequenceClassification.from_pretrained(
            base_model_name,
            num_labels=2,
        )

        print("loading lora adapter...")
        self.model = PeftModel.from_pretrained(base_model, self.model_path)

        print("moving model to device...")
        self.model.to(self.device)
        self.model.eval()
        print("LLM init done")

    def train(self) -> None: ...

    def _normalize_text(self, value) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            text = value
        elif isinstance(value, bytes):
            text = value.decode("utf-8", errors="ignore")
        elif isinstance(value, (list, tuple)):
            parts = [self._normalize_text(x).strip() for x in value]
            text = "\n".join(part for part in parts if part)
        elif isinstance(value, dict):
            text = " ".join(
                f"{self._normalize_text(k)}: {self._normalize_text(v)}"
                for k, v in value.items()
            )
        else:
            text = str(value)

        text = unicodedata.normalize("NFKC", text)

        cleaned = []
        for ch in text:
            cat = unicodedata.category(ch)
            if cat == "Cs":
                continue
            if ch in ("\n", "\r", "\t"):
                cleaned.append(ch)
                continue
            if cat.startswith("C"):
                continue
            cleaned.append(ch)

        text = "".join(cleaned)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return text.strip()

    def predict_prob_1(self, text: str) -> float:
        text = self._normalize_text(text)

        # ЛОГ: что идёт в классификацию
        print("=== LLM INPUT START ===")
        print(text)
        print("=== LLM INPUT END ===")

        if not text:
            text = " "

        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            padding=False,
            max_length=256,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits[0]
            probs = torch.softmax(logits, dim=-1)

        return float(probs[1].item())

    def inference(self, text):
        return self.predict_prob_1(text)


def decide_by_thresholds(prob_1: float):
    if prob_1 <= 0.25:
        return "auto_0", 0, "classified"
    if prob_1 >= 0.60:
        return "auto_1", 1, "classified"
    return "review", None, "review"


def development() -> None:
    model_path = Path("../model_out/final_lora")
    model = LLM(model_path)

    examples = [
        "Добрый день. Просим сделать расчет.",
        "Нужен счет, прошу выставить.",
        "Заявка в работу, без пересчета.",
    ]

    for text in examples:
        prob_1 = model.predict_prob_1(text)
        print(f"{text}: {prob_1}")


if __name__ == "__main__":
    development()
