from typing import Literal
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from datetime import datetime, timezone


class GenerateSQLRequest(BaseModel):
    model_config=ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",

    )
    question: str=Field(min_length=3,max_length=1000)

class GeneratedSQL(BaseModel):
    model_config=ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        )
    sql: str=Field(min_length=1, max_length=10000)
    _schema_version: str | None = PrivateAttr(default=None)

    @property
    def schema_version(self) -> str | None:
        return self._schema_version

class GenerateSQLResponse(BaseModel):
    question: str
    sql: str
    model: str
    validated: bool = False
    executed: Literal[False] = False

class QueryResponse(BaseModel):
    question: str
    sql: str
    model: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    estimated_cost: float
    database_duration_ms: float
    validated: Literal[True] = True
    executed: bool = True
    cache_hit: bool = False
    result_generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    repair_count: int = Field(ge=0, le=3)
    schema_version: str = Field(min_length=64, max_length=64)
    total_duration_ms: float = Field(ge=0)
    explanation: str = ""