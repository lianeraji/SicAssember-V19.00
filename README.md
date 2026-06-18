# SIC Assembler V19.00 — Pass 1 & Pass 2
Systems Programming Course
Liane Raji 221152

This project implements a **two-pass assembler** for the **SIC** machine as part of the *Systems Programming* course.

The assembler is written in **Python** and follows a fixed-format.

DISCLAIMER: Note that some AI was used to help learn how to implements concepts as starting points.

---

## Overview

The assembler works in two phases:

### Pass 1
- Reads the `.asm` source file
- Parses fixed-format lines
- Maintains `LOCCTR`
- Builds the **Symbol Table (SYMTAB)**
- Calculates program length
- Detects errors
- Generates an intermediate file (`.mdt`)

### Pass 2
- Reads the `.mdt` file
- Reconstructs `SYMTAB`
- Generates **object code**
- Produces:
  - Object file (`.obj`)
  - Listing file (`.lst`)

---

## Project Structure

- `pass1.py` → Pass 1 implementation 
- `pass2.py` → Pass 2 implementation
- `parser.py` → Fixed-format parser
- `optab.py` → SIC opcode table
- `models.py` → Data structures
- `samples/*.asm` → Input test files  
- `samples/*.mdt` → Intermediate files  
- `samples/*.obj` → Object files  
- `samples/*.lst` → Listing files  

---

## ⚙️ Supported Features

### Instructions
- All standard SIC instructions defined in `OPTAB`

### Directives
- `START`, `END`, `BYTE`, `WORD`, `RESB`, `RESW`

### Addressing Modes
- Simple: `LABEL`
- Indexed: `LABEL,X` (sets x-bit using `+0x8000`)

### Comments
- Any line starting with `.` is treated as a full comment

### Fixed Format (Strict)
| Columns | Field |
|--------|------|
| 1–10   | Label |
| 11     | Blank |
| 12–20  | Opcode |
| 21     | Blank |
| 22–39  | Operand |
| 40–70  | Comment |

---

## Not Supported (By Design)

- Literals (`=C'EOF'`, `=X'05'`)
- Immediate addressing (`#`)
- Indirect addressing (`@`)
- Advanced directives (`LTORG`)

---

## Pass 1 Details (Part 1)

### Output
- Program name, start address, LOCCTR, length
- SYMTAB
- Intermediate file (`.mdt`)

### Errors Detected
- Duplicate labels
- Invalid labels
- Invalid opcodes/directives
- Invalid operands
- Missing `END`
- Undefined symbols
- Incorrect addressing format
- Statements after `END`

---

## Pass 2 Details (Part 2)

### Object Code Generation

- Instructions → `OPCODE + address`
- Indexed addressing → sets x-bit (`+ 0x8000`)
- WORD → 3-byte integer 
- BYTE C'...' → ASCII hex
- BYTE X'...' → direct hex
- RESB / RESW → no object code 

---

## Object File Format (`.obj`)

### Header Record
```

H^PROGNAME^START^LENGTH

```

### Text Records
```

T^start^length^objectcodes...

```
- Max 30 bytes per record

### End Record
```

E^execution_start

```

---

## Listing File (`.lst`)

Each line contains:
```

address  label  opcode  operand  object_code

```

Also includes:
- Inline error messages
- Final error summary

---

## Intermediate File (`.mdt`)

Format:
```

line_no|address|label|opcode|operand|comment|is_comment|errors|raw

```

Used as input to Pass 2.

---

## How to Run

```bash
python3 pass1.py samples/test.asm samples/output.mdt
````

```bash
python3 pass2.py samples/output.mdt samples/output.obj samples/output.lst
```

---

## Example Outputs

* `output.mdt` → intermediate representation
* `output.obj` → SIC object code (H/T/E records)
* `output.lst` → full listing with object code and errors

---

## Notes

* The assembler strictly follows SIC fixed-format input
* Error handling is implemented in both passes
* Pass 2 depends entirely on the correctness of Pass 1 output

---

## Summary

This project successfully implements a functional SIC assembler with complete Pass 1 (analysis + symbol resolution) and complete Pass 2 (object code generation).

---

## Final Note

This project killed me. 

```

---
