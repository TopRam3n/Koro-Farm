from typing import Annotated

from pydantic import BeforeValidator, StringConstraints

from src.backend.app.domain.common.value_objects import CROP_CODE_PATTERN


def _normalize_crop_code(value):
    return value.strip().upper().replace(" ", "_").replace("-", "_") if isinstance(value, str) else value


# API representation of a crop catalogue code. Membership in the catalogue is checked by the handler
# (supply/application/crops.py), because the catalogue is data, not a fixed list.
CropCodeField = Annotated[str, BeforeValidator(_normalize_crop_code), StringConstraints(pattern=CROP_CODE_PATTERN)]
