"""Authority enum — tracks whether an identifier was issued by a registrar
or minted by this pipeline."""

from __future__ import annotations

from enum import Enum


class Authority(str, Enum):
    REGISTRAR = "registrar"
    DERIVED = "derived"
