from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .base import DatabaseManager
from .models import Mapping


class MaterialRepository:
    def find_target(self, source: str) -> Optional[Tuple[str, bool]]:
        with DatabaseManager.session_scope() as session:
            mapping = session.get(Mapping, source)
            if mapping:
                return mapping.target, mapping.black_list
            return None

    def add_source(self, source: str, target: str, black_list: bool) -> None:
        with DatabaseManager.session_scope() as session:
            mapping = Mapping(source=source, target=target, black_list=black_list)
            session.add(mapping)

    def batch_find(self, sources: List[str]) -> Dict[str, Optional[Tuple[str, bool]]]:
        if not sources:
            return {}

        with DatabaseManager.session_scope() as session:
            query = select(Mapping).where(Mapping.source.in_(sources))
            result = session.execute(query)
            mappings = result.scalars().all()

            result_dict = {m.source: (m.target, m.black_list) for m in mappings}
            for source in sources:
                if source not in result_dict:
                    result_dict[source] = None

        return result_dict

    def batch_add(self, mappings: List[Tuple[str, str, bool]]) -> None:
        with DatabaseManager.session_scope() as session:
            for source, target, black_list in mappings:
                mapping = Mapping(source=source, target=target, black_list=black_list)
                session.add(mapping)
