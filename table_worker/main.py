import json
from pathlib import Path


class ColumnsConfig:
    def __init__(self, config_path):
        self.path = config_path
        
        with open(self.path, "r") as file:
            data = json.load(file)

        self.col_asc = data["column-associations"]


def main():
    config_path = Path("config.json")

    conf = ColumnsConfig(config_path)


if __name__ == "__main__":
    main()
