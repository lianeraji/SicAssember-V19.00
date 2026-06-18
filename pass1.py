import sys
from pathlib import Path

from models import IntermediateLine
from optab import DIRECTIVES, OPTAB
from parser import parse_fixed_format_line


class Pass1Assembler:
    def __init__(self) -> None:
        self.symtab = {}
        self.errors = []
        self.intermediate_lines = []
        self.program_name = ""
        self.start_address = 0
        self.program_length = 0
        self.locctr = 0
        self.execution_start_symbol = ""

    def run(self, source_path, intermediate_path) -> bool:
        source_path = Path(source_path)
        intermediate_path = Path(intermediate_path)

        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        lines = source_path.read_text(encoding="utf-8").splitlines()

        if not lines:
            self.errors.append("Source file is empty.")
            self.write_intermediate_file(intermediate_path)
            return False

        parsed_lines = [
            parse_fixed_format_line(raw_line, i)
            for i, raw_line in enumerate(lines, start=1)
        ]

        self._process_lines(parsed_lines)
        self._check_undefined_instruction_symbols()
        self.write_intermediate_file(intermediate_path)

        return len(self.errors) == 0

    def _process_lines(self, parsed_lines) -> None:
        first_real_line_index = self._find_first_real_line(parsed_lines)
        if first_real_line_index is None:
            self.errors.append("No assembly statements found. File contains only comments.")
            return

        end_found = False
        first_line = parsed_lines[first_real_line_index]

        if first_line.opcode == "START":
            if first_line.label:
                self.program_name = first_line.label

            start_value, start_errors = self._parse_start_operand(first_line.operand)
            if start_errors:
                self.start_address = 0
                self.locctr = 0
                self._register_line(first_line, None, start_errors)
            else:
                self.start_address = start_value
                self.locctr = start_value
                self._register_line(first_line, self.locctr, [])
        else:
            self.program_name = first_line.label or "NONAME"
            self.start_address = 0
            self.locctr = 0

        current_index = 0

        while current_index < len(parsed_lines):
            line = parsed_lines[current_index]
            current_index += 1

            if line.is_comment:
                self._register_line(line, None, [])
                continue

            if current_index - 1 == first_real_line_index and line.opcode == "START":
                continue

            if not line.label and not line.opcode and not line.operand:
                self._register_line(line, None, [])
                continue

            line_address = self.locctr
            line_errors = []
            opcode = line.opcode

            if line.label:
                self._validate_label(line.label, line_errors)

            if opcode in OPTAB:
                line_errors.extend(self._validate_instruction_operand(opcode, line.operand))
                self.locctr += 3

            elif opcode == "WORD":
                if not self._is_valid_word_operand(line.operand):
                    line_errors.append(f"Invalid WORD operand '{line.operand}'.")
                self.locctr += 3

            elif opcode == "RESW":
                if not self._is_decimal_number(line.operand):
                    line_errors.append(f"Invalid RESW operand '{line.operand}'.")
                else:
                    self.locctr += 3 * int(line.operand)

            elif opcode == "RESB":
                if not self._is_decimal_number(line.operand):
                    line_errors.append(f"Invalid RESB operand '{line.operand}'.")
                else:
                    self.locctr += int(line.operand)

            elif opcode == "BYTE":
                byte_len, byte_error = self._byte_length(line.operand)
                if byte_error:
                    line_errors.append(byte_error)
                else:
                    self.locctr += byte_len

            elif opcode == "END":
                line_errors.extend(self._validate_end_operand(line.operand))
                end_found = True
                self._register_line(line, line_address, line_errors)
                break

            elif opcode == "START":
                line_errors.append("START directive is only allowed on the first real line.")

            elif opcode in DIRECTIVES:
                line_errors.append(f"Directive '{opcode}' is not handled in this project version.")

            else:
                line_errors.append(f"Invalid mnemonic/directive '{opcode}'.")

            self._register_line(line, line_address, line_errors)

        if not end_found:
            self.errors.append("Missing END directive.")
        else:
            for trailing_line in parsed_lines[current_index:]:
                if trailing_line.is_comment:
                    self._register_line(trailing_line, None, [])
                    continue

                if trailing_line.label or trailing_line.opcode or trailing_line.operand:
                    self._register_line(
                        trailing_line,
                        None,
                        ["Statement found after END directive."],
                    )
                else:
                    self._register_line(trailing_line, None, [])

        self.program_length = self.locctr - self.start_address

    def _check_undefined_instruction_symbols(self) -> None:
        for line in self.intermediate_lines:
            if line.is_comment:
                continue

            if line.opcode not in OPTAB:
                continue

            if line.opcode == "RSUB":
                continue

            if line.errors:
                continue

            symbol = self._extract_symbol_from_operand(line.operand)
            if not symbol:
                continue

            if symbol not in self.symtab:
                message = f"Undefined symbol '{symbol}' in operand '{line.operand}'."
                line.errors.append(message)
                self.errors.append(f"Line {line.line_no}: {message}")

    def _extract_symbol_from_operand(self, operand):
        if not operand:
            return None

        if "," in operand:
            base, index = operand.split(",", 1)
            if index == "X":
                return base
            return None

        return operand

    def _find_first_real_line(self, parsed_lines):
        for index, line in enumerate(parsed_lines):
            if line.is_comment:
                continue
            if line.label or line.opcode or line.operand:
                return index
        return None

    def _parse_start_operand(self, operand):
        if not operand:
            return 0, ["START is missing its starting address."]
        try:
            return int(operand, 16), []
        except ValueError:
            return 0, [f"Invalid START address '{operand}'. Expected hexadecimal."]

    def _validate_label(self, label, line_errors):
        if not self._is_valid_symbol(label):
            line_errors.append(f"Invalid label '{label}'.")
            return

        if label in self.symtab:
            line_errors.append(f"Duplicate label '{label}'.")
            return

        if label in OPTAB or label in DIRECTIVES:
            line_errors.append(f"Invalid label '{label}'. Label cannot be a mnemonic/directive.")
            return

        self.symtab[label] = self.locctr

    def _validate_instruction_operand(self, opcode, operand):
        errors = []

        if opcode == "RSUB":
            if operand:
                errors.append("RSUB must not have an operand.")
            return errors

        if not operand:
            errors.append(f"{opcode} is missing its operand.")
            return errors

        if operand.startswith("="):
            errors.append(f"Invalid operand '{operand}'. Literals are not supported.")
            return errors

        if operand.startswith("#") or operand.startswith("@"):
            errors.append(
                f"Invalid operand '{operand}'. Only simple and indexed addressing are supported."
            )
            return errors

        if " " in operand:
            errors.append(f"Invalid operand '{operand}'. Operand must not contain spaces.")
            return errors

        if operand.count(",") > 1:
            errors.append(f"Invalid operand '{operand}'. Too many commas.")
            return errors

        if "," in operand:
            base, index = operand.split(",", 1)

            if not base or not index:
                errors.append(f"Invalid operand '{operand}'. Indexed format must be SYMBOL,X.")
                return errors

            if index != "X":
                errors.append(f"Invalid operand '{operand}'. Indexed addressing must use ,X only.")
                return errors

            if not self._is_valid_symbol(base):
                errors.append(f"Invalid operand '{operand}'. Indexed base must be a valid symbol.")
                return errors

            return errors

        if not self._is_valid_symbol(operand):
            errors.append(f"Invalid operand '{operand}'. Operand must be a valid symbol or SYMBOL,X.")

        return errors

#am i overdoing the project? maybe. is anyone else checking all errors? i have no idea. :,) -Apr/1/2026

    def _validate_end_operand(self, operand):
        errors = []

        if not operand:
            errors.append("END is missing its operand (execution start symbol).")
            return errors

        if not self._is_valid_symbol(operand):
            errors.append(f"Invalid END operand '{operand}'.")
            return errors

        self.execution_start_symbol = operand

        if operand not in self.symtab:
            errors.append(f"END operand '{operand}' is undefined.")

        return errors

    def _byte_length(self, operand):
        if len(operand) < 3 or operand[1] != "'" or not operand.endswith("'"):
            return 0, f"Invalid BYTE operand '{operand}'. Use C'EOF' or X'F1'."

        kind = operand[0]
        value = operand[2:-1]

        if kind == "C":
            return len(value), None

        if kind == "X":
            if len(value) == 0:
                return 0, f"Invalid BYTE operand '{operand}'. Hex string is empty."

            if len(value) % 2 != 0:
                return 0, f"Invalid BYTE operand '{operand}'. Hex string must have even length."

            valid_hex = set("0123456789ABCDEF")
            for ch in value:
                if ch not in valid_hex:
                    return 0, f"Invalid BYTE operand '{operand}'. Non-hex digit found."

            return len(value) // 2, None

        return 0, f"Invalid BYTE operand '{operand}'. Only C and X are allowed."

    def _is_valid_symbol(self, symbol):
        if not symbol:
            return False

        if len(symbol) > 10:
            return False

        if not symbol[0].isalpha():
            return False

        for ch in symbol:
            if not ch.isalnum():
                return False

        return True

    def _is_decimal_number(self, text):
        return text.isdigit()

    def _is_valid_word_operand(self, operand):
        if operand.startswith("+") or operand.startswith("-"):
            return operand[1:].isdigit()
        return operand.isdigit()

    def _register_line(self, source_line, address, line_errors):
        intermediate = IntermediateLine(
            line_no=source_line.line_no,
            address=address,
            label=source_line.label,
            opcode=source_line.opcode,
            operand=source_line.operand,
            comment=source_line.comment,
            is_comment=source_line.is_comment,
            raw=source_line.raw,
            errors=line_errors.copy(),
        )

        self.intermediate_lines.append(intermediate)

        for error in line_errors:
            self.errors.append(f"Line {source_line.line_no}: {error}")

    def write_intermediate_file(self, output_path) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as f:
            f.write("# SIC Assembler Pass 1 Intermediate File\n")
            f.write(f"# PRGNAME={self.program_name}\n")
            f.write(f"# START={self.start_address:04X}\n")
            f.write(f"# LENGTH={self.program_length:04X}\n")
            f.write("# line_no|address|label|opcode|operand|comment|is_comment|errors|raw\n")

            for line in self.intermediate_lines:
                address_text = "" if line.address is None else f"{line.address:04X}"
                errors_text = " ; ".join(line.errors)
                raw_text = line.raw.replace("|", "/")
                comment_text = line.comment.replace("|", "/")

                f.write(
                    f"{line.line_no}|{address_text}|{line.label}|{line.opcode}|{line.operand}|"
                    f"{comment_text}|{int(line.is_comment)}|{errors_text}|{raw_text}\n"
                )

    def _print_block_title(self, title):
        print("·༻𐫱༺·" * 8)
        print(f"      {title}")
        print("·༻𐫱༺·" * 8)

    def _print_section_title(self, title):
        print()
        print(f"·༻𐫱༺·  {title}  ·༻𐫱༺·")

    def _print_summary_info(self):
        print(f"Program name   : {self.program_name}")
        print(f"Start address  : {self.start_address:04X}")
        print(f"Final LOCCTR   : {self.locctr:04X}")
        print(f"Program length : {self.program_length:04X}")

    def _print_symtab(self):
        self._print_section_title("SYMTAB")
        if not self.symtab:
            print("<empty>")
            return

        for symbol in sorted(self.symtab):
            print(f"{symbol:<12} {self.symtab[symbol]:04X}")

    def _print_intermediate_table(self):
        self._print_section_title("INTERMEDIATE TABLE")
        print(f"{'ADDR':<6} {'LABEL':<10} {'OPCODE':<10} {'OPERAND':<18} {'COMMENT'}")
        print("·༻𐫱༺·" * 8)

        for line in self.intermediate_lines:
            if line.is_comment:
                print(f"{'':<6} {'.COMMENT':<10} {'':<10} {'':<18} {line.comment}")
                continue

            address_text = "" if line.address is None else f"{line.address:04X}"
            print(
                f"{address_text:<6} "
                f"{line.label:<10} "
                f"{line.opcode:<10} "
                f"{line.operand:<18} "
                f"{line.comment or ''}"
            )

    def _print_errors(self):
        self._print_section_title("ERRORS")
        if not self.errors:
            print("No errors found in Pass 1.")
            return

        for error in self.errors:
            print(error)

    def print_summary(self) -> None:
        self._print_block_title("SIC ASSEMBLER - PASS 1 SUMMARY")
        self._print_summary_info()
        self._print_symtab()
        self._print_intermediate_table()
        self._print_errors()
        print()
        print("·༻𐫱༺·" * 8)


def main() -> int:
    if len(sys.argv) != 3:
        print("Use: python pass1.py source_file.asm intermediate_file.mdt")
        return 1

    source_file = Path(sys.argv[1])
    intermediate_file = Path(sys.argv[2])

    assembler = Pass1Assembler()

    try:
        ok = assembler.run(source_file, intermediate_file)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        return 1

    assembler.print_summary()

    if ok:
        print("·༻𐫱༺·  Pass 1 completed successfully.  ·༻𐫱༺·")
        print(f"Intermediate file written to: {intermediate_file}")
        print("·༻𐫱༺·" * 8)
        return 0

    print("·༻𐫱༺·  Pass 1 terminated because errors were found.  ·༻𐫱༺·")
    print(f"Intermediate file still written to: {intermediate_file}")
    print("·༻𐫱༺·" * 8)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())