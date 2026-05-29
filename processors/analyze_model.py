from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from classify import FeaturesExtractor, RFModel


def development() -> None:
    model = RFModel()
    model.load("classify/model.joblib")

    datapath = Path("~/Projects/OrdersAgent/private/mails/emails_parsed.parquet")
    df = pd.read_parquet(datapath)

    origin_labels = df["label"].to_list()
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

    per_label_data = {}
    origin_classes = df["label"].to_list()
    predicted_class, _, predicted_proba = model.predict(features_data)

    for origin, label, proba in zip(origin_classes, predicted_class, predicted_proba):
        if origin not in per_label_data:
            per_label_data[origin] = {"true": [], "false": []}
        if origin == label:
            per_label_data[origin]["true"].append(proba)
        else:
            per_label_data[origin]["false"].append(proba)

    for label, probas in per_label_data.items():
        print(">>>", label)
        true = probas["true"]
        false = probas["false"]
        print("max false:", max(false))
        print("min true:", min(true))
        print("decision edge:", (max(false) + min(true)) / 2)


if __name__ == "__main__":
    development()
