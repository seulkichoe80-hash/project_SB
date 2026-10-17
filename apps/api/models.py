from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True)
class Principal:
    subject: str
    institution_id: str
    role: Literal['reader', 'manager', 'worker']


class Transition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    target: Literal['queued', 'processing', 'completed', 'failed']
    revision: int
    claim_token: str | None = None

