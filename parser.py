"""
fixed columns:
1-10  label
11     blank
12-20  opcode / directive
21     blank
22-39  operand
40-70  comment
"""

from models import SourceLine


def parse_fixed_format_line(raw_line: str, line_no: int) -> SourceLine:
    """Parse one source line using the project's fixed-column layout."""
    raw = raw_line.rstrip("\n")


    if raw.startswith("."):
        return SourceLine(line_no=line_no, raw=raw, comment=raw, is_comment=True)


    padded = raw.ljust(70)
    label = padded[0:10].strip()
    opcode = padded[11:20].strip()
    operand = padded[21:39].strip()
    comment = padded[39:70].rstrip()

    return SourceLine(
        line_no=line_no,
        raw=raw,
        label=label,
        opcode=opcode,
        operand=operand,
        comment=comment,
        is_comment=False,
    )
