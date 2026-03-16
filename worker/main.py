import json
from pathlib import Path

# custom modules
from llm import LLM


class Table:
    def __init__(self, data) -> None:
        self.parse(data)

    def parse(self, data_dict):
        for key, val in data_dict.items():
            setattr(self, key, val)


def read_config(path: Path):
    with open(path, "r") as config_file:
        config_data = json.load(config_file)

    llm_config = Table(config_data["llm"])

    return (llm_config,)


def main():
    ...

if __name__ == "__main__":
    main()
