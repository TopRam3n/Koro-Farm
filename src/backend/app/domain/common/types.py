from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from src.backend.app.domain.common.value_objects import CropCode

CROP_CODE_LENGTH = 64


class CropCodeType(TypeDecorator):
    """Stores a crop catalogue code as VARCHAR(64) and loads it as a CropCode."""

    impl = String(CROP_CODE_LENGTH)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else str(value)

    def process_result_value(self, value, dialect):
        return None if value is None else CropCode(value)
