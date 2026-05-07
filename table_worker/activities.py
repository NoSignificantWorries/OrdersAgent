import asyncio
import io
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from temporalio import activity

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


class ExcelProcessingActivities:
    def __init__(self, config_path: Path = Path("config.json")) -> None:
        self.config_path = config_path
        self.conf = ColumnsConfig(self.config_path)
        self.pipeline = ParserV2(DELIMETERS)
        self.processor = MaterialProcessor(self.pipeline)

        self.table = None

    @activity.defn
    async def download_excel(self, bucket: str, filepath: str) -> bytes:
        cloud_client = MinIOClient.get_client()

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: cloud_client.get_object(bucket, filepath)
        )

        try:
            data = response.read()
            return data
        finally:
            response.close()
            response.release_conn()

    @activity.defn
    async def process_excel(self, excel_data: bytes, filepath: str) -> Optional[bytes]:
        def _sync_part():
            excel_file = io.BytesIO(excel_data)
            table = TableWorker(excel_file, Path(filepath), self.conf)
            table.open_and_clean()
            table.match_class_to_data()

            data = table.apply_extruder(StandartExtruder())
            return table, data

        loop = asyncio.get_event_loop()
        table, data = await loop.run_in_executor(None, _sync_part)

        if data is None:
            return None

        request = await table.parse_materials(self.processor)

        def _make_xlsx():
            wb = table._make_xlsx()
            if wb is None:
                return None
            output = io.BytesIO()
            wb.save(output)
            return output.getvalue()

        result = await loop.run_in_executor(None, _make_xlsx)
        return result

    @activity.defn
    async def notify_user(self, filepath: str, query: Dict[str, bool]): ...

    @activity.defn
    async def process_excel_materials(
        self, excel_data: bytes, filepath: str
    ) -> Optional[Dict[str, bool]]:
        def _sync_part():
            excel_file = io.BytesIO(excel_data)
            table = TableWorker(excel_file, Path(filepath), self.conf)
            table.open_and_clean()
            table.match_class_to_data()

            data = table.apply_extruder(StandartExtruder())
            return table, data

        loop = asyncio.get_event_loop()
        table, data = await loop.run_in_executor(None, _sync_part)

        if data is None:
            raise ValueError("Failed parsing table")

        self.table = table

        request = await table.parse_materials(self.processor)
        return request

    @activity.defn
    async def process_excel_match(
        self, materials_matching: Dict[str, Tuple[str, bool]]
    ):
        if self.table is None:
            return None

        await self.table.set_material_matches(materials_matching)

    @activity.defn
    async def process_excel_finally(self):
        if self.table is None:
            return None

        def _make_xlsx():
            if self.table is None:
                return None
            wb = self.table._make_xlsx()
            if wb is None:
                return None
            output = io.BytesIO()
            wb.save(output)
            return output.getvalue()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _make_xlsx)
        return result

    @activity.defn
    async def upload_excel(self, results: bytes, bucket: str, filepath: str) -> str:
        client = MinIOClient.get_client()
        output = io.BytesIO(results)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: client.put_object(
                bucket_name=bucket,
                object_name=filepath,
                data=output,
                length=output.getbuffer().nbytes,
            ),
        )

        return f"s3://{bucket}/{filepath}"
