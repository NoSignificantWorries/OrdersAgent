import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

from llm.llm import LLM


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    if isinstance(value, list):
        parts = [to_text(x).strip() for x in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def decide_by_thresholds(prob_1: float):
    if prob_1 <= 0.25:
        return "auto_0", 0
    if prob_1 >= 0.60:
        return "auto_1", 1
    return "review", None


def classify_email_text(llm_worker, subject, body, files_text) -> float:
    subject = to_text(subject).strip()
    body = to_text(body).strip()
    files_text = to_text(files_text).strip()

    parts = [subject, files_text, body]
    text = "\n\n".join(part for part in parts if part).strip()

    if not text:
        text = " "

    return llm_worker.predict_prob_1(text)


def main():
    payload = json.load(sys.stdin)

    subject = to_text(payload.get("subject"))
    body = to_text(payload.get("body"))
    files_text = to_text(payload.get("files_text"))

    log(f"subject type={type(payload.get('subject')).__name__}")
    log(f"body type={type(payload.get('body')).__name__}")
    log(f"files_text type={type(payload.get('files_text')).__name__}")

    model_path = Path("model_out/final_lora")

    log("LLM init start")

    captured = io.StringIO()
    with redirect_stdout(captured):
        llm_worker = LLM(model_path)

    init_logs = captured.getvalue().strip()
    if init_logs:
        print(init_logs, file=sys.stderr, flush=True)

    log("LLM init done")

    prob_1 = classify_email_text(llm_worker, subject, body, files_text)
    model_decision, predicted_class = decide_by_thresholds(prob_1)

    result = {
        "prob_1": prob_1,
        "predicted_class": predicted_class,
        "model_decision": model_decision,
    }

    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.flush()


if __name__ == "__main__":
    main()