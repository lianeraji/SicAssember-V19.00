import sys
from pathlib import Path
from optab import OPTAB


MAX_TEXT_RECORD_BYTES = 30


class MDTLine:
    def __init__(self, parts):
        self.line_no = int(parts[0])
        self.address = int(parts[1], 16) if parts[1] else None
        self.label = parts[2]
        self.opcode = parts[3]
        self.operand = parts[4]
        self.comment = parts[5]
        self.is_comment = parts[6] == "1"
        self.errors = parts[7]
        self.raw = parts[8] if len(parts) > 8 else ""


class Pass2Assembler:
    def __init__(self):
        self.program_name = "NONAME"
        self.start_address = 0
        self.program_length = 0
        self.execution_start = 0
        self.lines = []
        self.symtab = {}
        self.errors = []
        self.listing_rows = []

    def run(self, mdt_path, obj_path, lst_path=None):
        mdt_path = Path(mdt_path)
        obj_path = Path(obj_path)

        if lst_path is None:
            lst_path = obj_path.with_suffix(".lst")
        else:
            lst_path = Path(lst_path)

        self.read_mdt(mdt_path)
        self.build_symtab()

        object_records = self.generate_object_records()

        self.write_obj(obj_path, object_records)
        self.write_lst(lst_path)

        return len(self.errors) == 0

    def read_mdt(self, mdt_path):
        if not mdt_path.exists():
            raise FileNotFoundError(f"Intermediate file not found: {mdt_path}")

        for raw_line in mdt_path.read_text(encoding="utf-8").splitlines():
            if raw_line.startswith("# PRGNAME="):
                self.program_name = raw_line.split("=", 1)[1].strip() or "NONAME"

            elif raw_line.startswith("# START="):
                self.start_address = int(raw_line.split("=", 1)[1].strip(), 16)

            elif raw_line.startswith("# LENGTH="):
                self.program_length = int(raw_line.split("=", 1)[1].strip(), 16)

            elif raw_line.startswith("#"):
                continue

            else:
                parts = raw_line.split("|")
                if len(parts) >= 8:
                    self.lines.append(MDTLine(parts))

    def build_symtab(self):
        for line in self.lines:
            if line.is_comment:
                continue

            if line.label and line.address is not None:
                if line.label not in self.symtab:
                    self.symtab[line.label] = line.address

    def generate_object_records(self):
        text_records = []
        current_start = None
        current_codes = []
        current_length = 0

        for line in self.lines:
            object_code = ""

            if line.is_comment:
                self.add_listing_row(line, "")
                continue

            if line.errors:
                self.errors.append(f"Line {line.line_no}: Pass 1 error: {line.errors}")
                self.add_listing_row(line, "")
                continue

            if line.opcode == "END":
                if line.operand in self.symtab:
                    self.execution_start = self.symtab[line.operand]
                else:
                    self.execution_start = self.start_address

                self.flush_text_record(text_records, current_start, current_codes, current_length)
                self.add_listing_row(line, "")
                return text_records

            object_code = self.make_object_code(line)

            if object_code is None:
                self.add_listing_row(line, "")
                self.flush_text_record(text_records, current_start, current_codes, current_length)
                current_start = None
                current_codes = []
                current_length = 0
                continue

            code_bytes = len(object_code) // 2

            if current_start is None:
                current_start = line.address

            if current_length + code_bytes > MAX_TEXT_RECORD_BYTES:
                self.flush_text_record(text_records, current_start, current_codes, current_length)
                current_start = line.address
                current_codes = []
                current_length = 0

            current_codes.append(object_code)
            current_length += code_bytes
            self.add_listing_row(line, object_code)

        self.flush_text_record(text_records, current_start, current_codes, current_length)
        return text_records

    def make_object_code(self, line):
        opcode = line.opcode
        operand = line.operand

        if opcode in OPTAB:
            op_hex = OPTAB[opcode]

            if opcode == "RSUB":
                return f"{op_hex}0000"

            address = self.resolve_operand_address(line)

            if address is None:
                return "000000"

            return f"{op_hex}{address:04X}"

        if opcode == "WORD":
            try:
                value = int(operand)
                return f"{value & 0xFFFFFF:06X}"
            except ValueError:
                self.errors.append(f"Line {line.line_no}: Invalid WORD operand '{operand}'.")
                return "000000"

        if opcode == "BYTE":
            return self.make_byte_object_code(line)

        if opcode in {"RESW", "RESB", "START"}:
            return None

        return None

    def resolve_operand_address(self, line):
        operand = line.operand

        if not operand:
            self.errors.append(f"Line {line.line_no}: Missing operand.")
            return None

        indexed = False

        if "," in operand:
            base, index = operand.split(",", 1)
            if index != "X":
                self.errors.append(f"Line {line.line_no}: Invalid indexed operand '{operand}'.")
                return None
            operand = base
            indexed = True

        if operand not in self.symtab:
            self.errors.append(f"Line {line.line_no}: Undefined symbol '{operand}'.")
            return None

        address = self.symtab[operand]

        if indexed:
            address += 0x8000

        return address

    def make_byte_object_code(self, line):
        operand = line.operand

        if len(operand) < 3 or operand[1] != "'" or not operand.endswith("'"):
            self.errors.append(f"Line {line.line_no}: Invalid BYTE operand '{operand}'.")
            return ""

        kind = operand[0]
        value = operand[2:-1]

        if kind == "C":
            return "".join(f"{ord(ch):02X}" for ch in value)

        if kind == "X":
            return value.upper()

        self.errors.append(f"Line {line.line_no}: Invalid BYTE type '{kind}'.")
        return ""

    def flush_text_record(self, text_records, start, codes, length):
        if start is None or not codes or length == 0:
            return

        record = f"T^{start:06X}^{length:02X}^" + "^".join(codes)
        text_records.append(record)

    def write_obj(self, obj_path, text_records):
        obj_path.parent.mkdir(parents=True, exist_ok=True)

        with obj_path.open("w", encoding="utf-8") as f:
            f.write(f"H^{self.program_name[:6]:<6}^{self.start_address:06X}^{self.program_length:06X}\n")

            for record in text_records:
                f.write(record + "\n")

            f.write(f"E^{self.execution_start:06X}\n")

    def add_listing_row(self, line, object_code):
        address_text = "" if line.address is None else f"{line.address:04X}"

        self.listing_rows.append(
            {
                "line_no": line.line_no,
                "address": address_text,
                "label": line.label,
                "opcode": line.opcode,
                "operand": line.operand,
                "object_code": object_code,
                "errors": line.errors,
                "raw": line.raw,
            }
        )

    def write_lst(self, lst_path):
        lst_path.parent.mkdir(parents=True, exist_ok=True)

        with lst_path.open("w", encoding="utf-8") as f:
            f.write("SIC ASSEMBLER LISTING FILE\n")
            f.write("=" * 80 + "\n")
            f.write(f"Program name   : {self.program_name}\n")
            f.write(f"Start address  : {self.start_address:04X}\n")
            f.write(f"Program length : {self.program_length:04X}\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"{'LINE':<6}{'ADDR':<8}{'LABEL':<12}{'OPCODE':<10}{'OPERAND':<18}{'OBJECT CODE'}\n")
            f.write("-" * 80 + "\n")

            for row in self.listing_rows:
                f.write(
                    f"{row['line_no']:<6}"
                    f"{row['address']:<8}"
                    f"{row['label']:<12}"
                    f"{row['opcode']:<10}"
                    f"{row['operand']:<18}"
                    f"{row['object_code']}\n"
                )

                if row["errors"]:
                    f.write(f"      ERROR: {row['errors']}\n")

            f.write("\n")
            f.write("=" * 80 + "\n")
            f.write("ERROR SUMMARY\n")
            f.write("=" * 80 + "\n")

            if not self.errors:
                f.write("No Pass 2 errors.\n")
            else:
                for error in self.errors:
                    f.write(error + "\n")

    def print_summary(self):
        print(" ")
        print("·༻𐫱༺·" * 8)
        print("      SIC ASSEMBLER - PASS 2 SUMMARY")
        print("·༻𐫱༺·" * 8)
        print(f"Program name   : {self.program_name}")
        print(f"Start address  : {self.start_address:04X}")
        print(f"Program length : {self.program_length:04X}")
        print()

        if not self.errors:
            print("No Pass 2 errors.")
        else:
            print("Errors:")
            for error in self.errors:
                print(error)

        print("·༻𐫱༺·" * 8)

#:)

def main():
    if len(sys.argv) not in {3, 4}:
        print("Use:")
        print("python pass2.py intermediate_file.mdt output_file.obj")
        print("or")
        print("python pass2.py intermediate_file.mdt output_file.obj output_file.lst")
        return 1

    mdt_file = sys.argv[1]
    obj_file = sys.argv[2]
    lst_file = sys.argv[3] if len(sys.argv) == 4 else None

    assembler = Pass2Assembler()

    try:
        ok = assembler.run(mdt_file, obj_file, lst_file)
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        return 1

    assembler.print_summary()

    if ok:
        print("·༻𐫱༺·  Pass 2 completed successfully.  ·༻𐫱༺·")
        print("·༻𐫱༺·" * 8)
        return 0

    print("·༻𐫱༺·  Pass 2 completed with errors.  ·༻𐫱༺·")
    print("·༻𐫱༺·" * 8)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())