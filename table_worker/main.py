import asyncio
import io
from pathlib import Path

from table import (
    DELIMETERS,
    ColumnsConfig,
    DatabaseManager,
    MaterialProcessor,
    MinIOClient,
    ParserV2,
    StandartExtruder,
    TableWorker,
    initialize_app,
)


async def runner() -> None:
    await initialize_app()

    config_path = Path("config.json")

    conf = ColumnsConfig(config_path)

    cloud_client = MinIOClient.get_client()
    bucket_name = "orders-attachments"

    pipeline = ParserV2(DELIMETERS)
    processor = MaterialProcessor(pipeline)

    filepath = "033/1108A.xls"
    with cloud_client.get_object(bucket_name, filepath) as response:
        excel_file = io.BytesIO(response.read())

    table = TableWorker(excel_file, Path(filepath), conf)
    table.open_and_clean()
    table.match_class_to_data()

    data = table.apply_extruder(StandartExtruder())

    if data is not None:
        await table.parse_materials(processor)

        wb = table._make_xlsx()
        if wb is None:
            raise ValueError("Wrong table format")
        else:
            output = io.BytesIO()
            wb.save(output)
            output.seek(0)

            cloud_client.put_object(
                bucket_name="results",
                object_name=filepath,
                data=output,
                length=output.getbuffer().nbytes,
            )
    else:
        print("ERROR: No data")

    await DatabaseManager.close()


def main():
    asyncio.run(runner())


if __name__ == "__main__":
    main()
