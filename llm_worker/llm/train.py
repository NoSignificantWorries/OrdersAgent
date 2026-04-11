import json
from pathlib import Path

import numpy as np
import torch
from datasets import load_dataset
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

MODEL_NAME = "DeepPavlov/distilrubert-tiny-cased-conversational-5k"
DATA_PATH = "table/emails.jsonl"
NUM_LABELS = 2


def main():
    raw_ds = load_dataset(
        "json",
        data_files=DATA_PATH,
        split="train",
    )

    train_idx, val_idx = train_test_split(
        list(range(len(raw_ds))),
        test_size=0.2,
        stratify=raw_ds["label"],
        random_state=42,
    )

    train_ds = raw_ds.select(train_idx)
    val_ds = raw_ds.select(val_idx)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    def tokenize_fn(batch):
        return tokenizer(
            batch["text"],
            padding="max_length",
            truncation=True,
            max_length=256,
        )

    train_ds = train_ds.map(tokenize_fn, batched=True)
    val_ds = val_ds.map(tokenize_fn, batched=True)

    train_ds = train_ds.rename_column("label", "labels")
    val_ds = val_ds.rename_column("label", "labels")

    train_ds.set_format(
        type="torch",
        columns=["input_ids", "attention_mask", "labels"],
    )
    val_ds.set_format(
        type="torch",
        columns=["input_ids", "attention_mask", "labels"],
    )

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=NUM_LABELS,
    )

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        acc = accuracy_score(labels, preds)
        f1 = f1_score(labels, preds, average="binary")
        return {
            "accuracy": acc,
            "f1": f1,
        }

    training_args = TrainingArguments(
        output_dir="model_out",
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=3e-5,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        num_train_epochs=10,
        weight_decay=0.01,
        load_best_model_at_end=True,
        metric_for_best_model="eval_f1",
        greater_is_better=True,
        logging_strategy="steps",
        logging_steps=5,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        compute_metrics=compute_metrics,
    )

    trainer.train()

    debug_dir = Path("debug")
    debug_dir.mkdir(exist_ok=True)

    with open(debug_dir / "training_log.json", "w", encoding="utf-8") as f:
        json.dump(trainer.state.log_history, f, ensure_ascii=False, indent=2)

    pred = trainer.predict(val_ds)
    logits = pred.predictions
    labels = pred.label_ids

    probs = torch.softmax(torch.tensor(logits), dim=-1).numpy()
    probs_1 = probs[:, 1]
    y_pred = np.argmax(logits, axis=-1)

    val_records = []
    for i, (true_label, prob_1, pred_label) in enumerate(zip(labels, probs_1, y_pred)):
        val_records.append({
            "text": raw_ds[val_idx[i]]["text"],
            "true_label": int(true_label),
            "pred_label": int(pred_label),
            "prob_1": float(prob_1),
            "logits": logits[i].tolist(),
        })

    with open(debug_dir / "val_predictions.jsonl", "w", encoding="utf-8") as f:
        for record in val_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    errors = [record for record in val_records if record["true_label"] != record["pred_label"]]

    with open(debug_dir / "misclassified_val.jsonl", "w", encoding="utf-8") as f:
        for error in errors:
            f.write(json.dumps(error, ensure_ascii=False) + "\n")

    trainer.save_model("model_out/final")
    tokenizer.save_pretrained("model_out/final")


if __name__ == "__main__":
    main()