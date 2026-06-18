from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SourceLine:
    line_no: int
    raw: str
    label: str = ""
    opcode: str = ""
    operand: str = ""
    comment: str = ""
    is_comment: bool = False


@dataclass
class IntermediateLine:
    line_no: int
    address: Optional[int]
    label: str
    opcode: str
    operand: str
    comment: str
    is_comment: bool
    raw: str
    errors: List[str] = field(default_factory=list)
