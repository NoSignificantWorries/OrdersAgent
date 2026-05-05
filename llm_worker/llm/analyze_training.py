import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


DEBUG_DIR = Path("debug")
DEBUG_DIR.mkdir(exist_ok=True)

plt.style.use("seaborn-v0_8-whitegrid")


def load_training_log(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_epoch_metrics(log_history):
    train_loss = []
    val_loss = []
    val_acc = []
    val_f1 = []

    # все записи с валидацией — по одной на эпоху
    eval_entries = [e for e in log_history if "eval_loss" in e]
    num_epochs = len(eval_entries)

    for epoch_idx in range(num_epochs):
        ep = epoch_idx + 1  # номер эпохи 1..N

        # берём последнее сообщение с train loss, у которого epoch <= ep
        train_entries = [
            e
            for e in log_history
            if "loss" in e
            and "eval_loss" not in e
            and e.get("epoch", 0) <= ep
        ]
        if train_entries:
            train_loss.append(train_entries[-1]["loss"])
        else:
            train_loss.append(math.nan)

        eval_entry = eval_entries[epoch_idx]
        val_loss.append(eval_entry["eval_loss"])
        val_acc.append(eval_entry["eval_accuracy"])
        val_f1.append(eval_entry["eval_f1"])

    epochs = np.arange(1, num_epochs + 1)

    return (
        epochs,
        np.array(train_loss),
        np.array(val_loss),
        np.array(val_acc),
        np.array(val_f1),
    )


def setup_axes(ax, title, xlabel, ylabel, ylim=None):
    ax.set_title(title, fontsize=16, pad=12, fontweight="semibold")
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    if ylim is not None:
        ax.set_ylim(*ylim)
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_losses(epochs, train_loss, val_loss):
    fig, ax = plt.subplots(figsize=(9, 5))

    ax.plot(
        epochs,
        train_loss,
        marker="o",
        linestyle="-",
        linewidth=2.2,
        markersize=5,
        color="#1f77b4",
        label="Train loss",
    )
    ax.plot(
        epochs,
        val_loss,
        marker="o",
        linestyle="-",
        linewidth=2.2,
        markersize=5,
        color="#ff7f0e",
        label="Val loss",
    )

    setup_axes(ax, "Train / Val loss per epoch", "Epoch", "Loss")
    ax.set_xticks(epochs)
    ax.legend(frameon=True, fontsize=11)

    plt.tight_layout()
    out = DEBUG_DIR / "loss_curves.png"
    plt.savefig(out, dpi=180, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_metrics(epochs, val_acc, val_f1):
    fig, ax = plt.subplots(figsize=(9, 5))

    ax.plot(
        epochs,
        val_acc,
        marker="o",
        linestyle="-",
        linewidth=3.0,
        markersize=4,
        markerfacecolor="white",
        markeredgewidth=1.5,
        alpha=0.9,
        color="#1f77b4",
        label="Val accuracy",
    )

    ax.plot(
        epochs,
        val_f1,
        marker="o",
        linestyle="-",
        linewidth=3.0,
        markersize=4,
        markerfacecolor="white",
        markeredgewidth=1.5,
        alpha=0.9,
        color="#ff7f0e",
        label="Val F1",
    )

    setup_axes(ax, "Validation accuracy / F1 per epoch", "Epoch", "Score", ylim=(0, 1))
    ax.set_xticks(epochs)
    ax.legend(frameon=True, fontsize=11)

    plt.tight_layout()
    out = DEBUG_DIR / "val_metrics.png"
    plt.savefig(out, dpi=180, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def load_val_predictions(path: Path):
    labels = []
    probs = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            labels.append(int(obj["true_label"]))
            probs.append(float(obj["prob_1"]))

    return np.array(labels), np.array(probs)


def precision_recall_f1_at_thresholds(y_true, p1, thresholds):
    results = []

    for t in thresholds:
        y_pred = (p1 >= t).astype(int)

        tp = np.sum((y_pred == 1) & (y_true == 1))
        fp = np.sum((y_pred == 1) & (y_true == 0))
        fn = np.sum((y_pred == 0) & (y_true == 1))

        precision = 0.0 if (tp + fp) == 0 else tp / (tp + fp)
        recall = 0.0 if (tp + fn) == 0 else tp / (tp + fn)
        f1 = 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)
        acc = np.mean(y_pred == y_true)

        results.append((t, precision, recall, f1, acc))

    return results


def metrics_with_counts_at_thresholds(y_true, p1, thresholds):
    results = []

    for t in thresholds:
        y_pred = (p1 >= t).astype(int)

        tp = np.sum((y_pred == 1) & (y_true == 1))
        fp = np.sum((y_pred == 1) & (y_true == 0))
        fn = np.sum((y_pred == 0) & (y_true == 1))
        tn = np.sum((y_pred == 0) & (y_true == 0))

        precision = 0.0 if (tp + fp) == 0 else tp / (tp + fp)
        recall    = 0.0 if (tp + fn) == 0 else tp / (tp + fn)
        f1 = 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)
        acc = (tp + tn) / (tp + fp + fn + tn)

        results.append((t, tp, fp, fn, tn, precision, recall, f1, acc))

    return results


def plot_threshold_histograms(y_true, p1, best_t, best_f1):
    p1_neg = p1[y_true == 0]
    p1_pos = p1[y_true == 1]

    fig, ax = plt.subplots(figsize=(9, 5))

    ax.hist(
        p1_neg,
        bins=30,
        alpha=0.5,
        density=True,
        label="Класс 0 (negative)",
        color="#1f77b4",
    )
    ax.hist(
        p1_pos,
        bins=30,
        alpha=0.5,
        density=True,
        label="Класс 1 (positive)",
        color="#ff7f0e",
    )

    ax.axvline(best_t, color="red", linestyle="--", linewidth=2,
               label=f"Threshold = {best_t:.2f}")

    setup_axes(
        ax,
        f"Распределение p(class=1) и оптимальный threshold\n(best F1={best_f1:.3f})",
        "p(class=1)",
        "Плотность",
    )
    ax.legend(frameon=True, fontsize=11)

    plt.tight_layout()
    out = DEBUG_DIR / "threshold_hist_probs.png"
    plt.savefig(out, dpi=180, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_threshold_curves(y_true, p1, thresholds, stats):
    t = np.array([s[0] for s in stats])
    prec = np.array([s[5] for s in stats])
    rec = np.array([s[6] for s in stats])
    f1 = np.array([s[7] for s in stats])
    acc = np.array([s[8] for s in stats])

    fig, ax = plt.subplots(figsize=(10, 5.5))

    ax.plot(
        t,
        f1,
        #marker="o",
        linestyle="-",
        linewidth=2.4,
        markersize=6,
        color="#1f77b4",
        label="F1",
    )
    ax.plot(
        t,
        acc,
        #marker="o",
        linestyle="-",
        linewidth=2.4,
        markersize=6,
        color="#ff7f0e",
        label="Accuracy",
    )
    ax.plot(
        t,
        prec,
        linestyle="--",
        linewidth=2.0,
        color="#2ca02c",
        alpha=0.9,
        label="Precision",
    )
    ax.plot(
        t,
        rec,
        linestyle="--",
        linewidth=2.0,
        color="#d62728",
        alpha=0.9,
        label="Recall",
    )

    best_idx = np.argmax(f1)
    best_t = t[best_idx]
    best_f1 = f1[best_idx]

    ax.scatter(best_t, best_f1, color="black", s=45, zorder=5)
    ax.annotate(
        f"best F1={best_f1:.3f}\nthreshold={best_t:.2f}",
        xy=(best_t, best_f1),
        xytext=(best_t + 0.03, min(best_f1 + 0.08, 0.97)),
        arrowprops=dict(arrowstyle="->", alpha=0.6),
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.8", alpha=0.95),
    )

    setup_axes(ax, "Metrics vs threshold (validation set)", "Threshold for class 1", "Score", ylim=(0, 1))
    ax.set_xticks(np.round(np.linspace(0.1, 0.9, 9), 2))
    ax.legend(frameon=True, fontsize=11, ncol=2)

    plt.tight_layout()
    out = DEBUG_DIR / "threshold_curves.png"
    plt.savefig(out, dpi=180, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")

    return best_t, best_f1

def plot_threshold_class_counts(y_true, p1, thresholds, stats):
    t = np.array([s[0] for s in stats])
    tp = np.array([s[1] for s in stats])
    fp = np.array([s[2] for s in stats])
    fn = np.array([s[3] for s in stats])
    tn = np.array([s[4] for s in stats])
    f1 = np.array([s[7] for s in stats])

    best_idx = np.argmax(f1)
    best_t = t[best_idx]
    best_f1 = f1[best_idx]

    fig, ax = plt.subplots(figsize=(10, 5.8))

    # Верные ответы по классам
    ax.plot(
        t, tp,
        color="#ff7f0e",
        linewidth=2.5,
        label="Верно для класса 1 (TP)"
    )
    ax.plot(
        t, tn,
        color="#1f77b4",
        linewidth=2.5,
        label="Верно для класса 0 (TN)"
    )

    # Неверные ответы по классам
    ax.plot(
        t, fn,
        color="#d62728",
        linewidth=2.0,
        linestyle="--",
        label="Неверно для класса 1 (FN)"
    )
    ax.plot(
        t, fp,
        color="#2ca02c",
        linewidth=2.0,
        linestyle="--",
        label="Неверно для класса 0 (FP)"
    )

    ax.axvline(
        best_t,
        color="black",
        linestyle=":",
        linewidth=2.2,
        label=f"Лучший threshold = {best_t:.2f}"
    )

    ax.scatter(best_t, tp[best_idx], color="#ff7f0e", s=45, zorder=5)
    ax.scatter(best_t, tn[best_idx], color="#1f77b4", s=45, zorder=5)

    ax.annotate(
        f"best F1={best_f1:.3f}\nthreshold={best_t:.2f}",
        xy=(best_t, max(tp[best_idx], tn[best_idx])),
        xytext=(best_t + 0.03, max(tp.max(), tn.max()) * 0.92),
        arrowprops=dict(arrowstyle="->", alpha=0.6),
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.8", alpha=0.95),
    )

    setup_axes(
        ax,
        "Количество верных и неверных ответов по классам vs threshold",
        "Threshold для класса 1",
        "Количество объектов"
    )
    ax.set_xlim(0, 1)
    ax.set_xticks(np.round(np.linspace(0.1, 0.9, 9), 2))
    ax.legend(frameon=True, fontsize=10, ncol=2)

    plt.tight_layout()
    out = DEBUG_DIR / "threshold_class_counts.png"
    plt.savefig(out, dpi=180, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def main():
    log_path = DEBUG_DIR / "training_log.json"
    val_pred_path = DEBUG_DIR / "val_predictions.jsonl"

    if not log_path.exists():
        print(f"No {log_path}, run train.py first")
        return

    if not val_pred_path.exists():
        print(f"No {val_pred_path}, run train.py first")
        return

    log_history = load_training_log(log_path)
    epochs, train_loss, val_loss, val_acc, val_f1 = extract_epoch_metrics(log_history)

    plot_losses(epochs, train_loss, val_loss)
    plot_metrics(epochs, val_acc, val_f1)

    y_true, p1 = load_val_predictions(val_pred_path)

    thresholds = np.linspace(0.0, 1.0, 300)
    stats = metrics_with_counts_at_thresholds(y_true, p1, thresholds)

    best_t, best_f1 = plot_threshold_curves(y_true, p1, thresholds, stats)

    plot_threshold_class_counts(y_true, p1, thresholds, stats)


if __name__ == "__main__":
    main()