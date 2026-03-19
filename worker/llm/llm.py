import torch
from transformers import AutoTokenizer, AutoModel


class LLM:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModel.from_pretrained(self.model_name)

    def train(self) -> None:
        ...

    def inference(self, text):
        inputs = self.tokenizer(text, return_tensors="pt")
        with torch.no_grad():
            outputs = self.model(**inputs)
        return outputs


def development() -> None:
    model_name = "DeepPavlov/distilrubert-tiny-cased-conversational-5k"
    model = LLM(model_name)

    print(model.inference("Привет, мир!"))


if __name__ == "__main__":
    development()


