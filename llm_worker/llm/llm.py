from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification


class LLM:
    def __init__(self, model_path: str) -> None:
        print("LLM init start")

        self.model_path = str(model_path)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print("device:", self.device)

        print("loading tokenizer...")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)

        print("loading model...")
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)

        print("moving model to device...")
        self.model.to(self.device)
        self.model.eval()
        print("LLM init done")

    def train(self) -> None:
        ...

    def predict_prob_1(self, text: str) -> float:
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            padding=True,
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


def development() -> None:
    model_path = Path("model_out/final")
    model = LLM(model_path)

    prob_1 = model.predict_prob_1("Добрый день. Просим сделать расчет.")
    print(prob_1)


if __name__ == "__main__":
    development()


