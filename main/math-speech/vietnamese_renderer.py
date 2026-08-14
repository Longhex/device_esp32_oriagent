"""Deterministic Vietnamese narration for common Presentation MathML.

MathCAT remains the broad fallback in :mod:`app`.  This renderer owns the
structures where scope is important to Vietnamese TTS (fractions, roots,
scripts, brackets and large operators), so their wording does not depend on a
machine-translated upstream rule.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass


class UnsupportedMathML(ValueError):
    """Ask the caller to use its general-purpose MathML fallback."""


_GREEK = {
    "α": "an pha",
    "β": "bê ta",
    "γ": "gam ma",
    "Γ": "gam ma",
    "δ": "đen ta",
    "Δ": "đen ta",
    "ε": "ép xi lon",
    "ζ": "dét ta",
    "η": "ê ta",
    "θ": "thê ta",
    "Θ": "thê ta",
    "ι": "i ô ta",
    "κ": "ka pa",
    "λ": "lam đa",
    "Λ": "lam đa",
    "μ": "miu",
    "ν": "niu",
    "ξ": "xi",
    "Π": "pi",
    "π": "pi",
    "ρ": "rô",
    "σ": "xích ma",
    "Σ": "xích ma",
    "τ": "tô",
    "υ": "íp xi lon",
    "φ": "phi",
    "χ": "khi",
    "ψ": "pơ xi",
    "ω": "ô mê ga",
    "Ω": "ô mê ga",
}

_IDENTIFIERS = {
    **_GREEK,
    "∞": "vô cùng",
    "ℕ": "tập số tự nhiên",
    "ℤ": "tập số nguyên",
    "ℚ": "tập số hữu tỷ",
    "ℝ": "tập số thực",
    "ℂ": "tập số phức",
    "±": "cộng hoặc trừ",
    "∓": "trừ hoặc cộng",
    "sin": "sin",
    "cos": "cos",
    "tan": "tan",
    "cot": "cot",
    "sec": "séc",
    "csc": "cô séc",
    "ln": "lô ga rít tự nhiên",
    "log": "lô ga rít",
    "lim": "giới hạn",
}

_OPERATORS = {
    "+": "cộng",
    "−": "trừ",
    "-": "trừ",
    "±": "cộng hoặc trừ",
    "∓": "trừ hoặc cộng",
    "×": "nhân",
    "⋅": "nhân",
    "·": "nhân",
    "*": "nhân",
    "÷": "chia",
    "/": "trên",
    "=": "bằng",
    "≠": "khác",
    "<": "nhỏ hơn",
    ">": "lớn hơn",
    "≤": "nhỏ hơn hoặc bằng",
    "≥": "lớn hơn hoặc bằng",
    "≈": "xấp xỉ bằng",
    "≃": "xấp xỉ bằng",
    "≡": "đồng nhất với",
    "→": "tiến tới",
    "⇒": "suy ra",
    "⇔": "tương đương",
    "∈": "thuộc",
    "∉": "không thuộc",
    "⊂": "là tập con của",
    "⊆": "là tập con hoặc bằng",
    "∪": "hợp",
    "∩": "giao",
    "∖": "hiệu",
    "∥": "song song với",
    "⊥": "vuông góc với",
    "∝": "tỉ lệ với",
    "∣": "với điều kiện",
    "∞": "vô cùng",
    "∂": "đạo hàm riêng",
    "det": "định thức",
    "!": "giai thừa",
    "%": "phần trăm",
    ",": "phẩy",
    ":": "hai chấm",
    "…": "chấm chấm chấm",
    "⋯": "chấm chấm chấm",
    "∀": "với mọi",
    "∃": "tồn tại",
    "∄": "không tồn tại",
    "¬": "phủ định",
    "∧": "và",
    "∨": "hoặc",
}

_OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}", "⟨": "⟩"}
_CLOSE = set(_OPEN_TO_CLOSE.values())
_FUNCTIONS = {"sin", "cos", "tan", "cot", "sec", "csc", "ln", "log"}
_CALLABLE_IDENTIFIERS = _FUNCTIONS | {"f", "g", "h", "F", "G", "H", "P", "det"}
_RELATIONS = {"=", "≠", "<", ">", "≤", "≥", "≈", "≃", "≡"}
_BINARY = set(_OPERATORS) - {"!", "%", ",", ":", "…", "⋯"}


@dataclass(frozen=True)
class Phrase:
    text: str
    kind: str = "value"


def _tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _children(node: ET.Element) -> list[ET.Element]:
    return [child for child in node if _tag(child) != "annotation"]


def _text(node: ET.Element) -> str:
    return "".join(node.itertext()).strip()


def _unwrap(node: ET.Element) -> ET.Element:
    while _tag(node) in {"math", "mrow", "mstyle", "mpadded", "semantics"}:
        children = _children(node)
        if len(children) != 1:
            break
        node = children[0]
    return node


def _integer_under_1000(number: int, *, full: bool = False) -> str:
    digits = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
    parts: list[str] = []
    hundreds, remainder = divmod(number, 100)
    if hundreds or full:
        parts.extend([digits[hundreds], "trăm"])
    tens, ones = divmod(remainder, 10)
    if tens >= 2:
        parts.extend([digits[tens], "mươi"])
        if ones == 1:
            parts.append("mốt")
        elif ones == 4:
            parts.append("tư")
        elif ones == 5:
            parts.append("lăm")
        elif ones:
            parts.append(digits[ones])
    elif tens == 1:
        parts.append("mười")
        if ones == 5:
            parts.append("lăm")
        elif ones:
            parts.append(digits[ones])
    elif ones:
        if (hundreds or full) and remainder < 10:
            parts.append("linh")
        parts.append(digits[ones])
    return " ".join(parts) if parts else "không"


def integer_to_vietnamese(number: int) -> str:
    """Read a signed integer with Vietnamese short-scale group names."""

    if number == 0:
        return "không"
    if number < 0:
        return "âm " + integer_to_vietnamese(-number)

    groups: list[int] = []
    while number:
        number, group = divmod(number, 1000)
        groups.append(group)
    scales = ["", "nghìn", "triệu", "tỷ"]
    parts: list[str] = []
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        if not group:
            continue
        scale_index = index % 4
        billion_block = index // 4
        full = bool(parts and group < 100)
        parts.append(_integer_under_1000(group, full=full))
        if scale_index:
            parts.append(scales[scale_index])
        if billion_block:
            parts.extend(["tỷ"] * billion_block)
    return " ".join(parts)


def number_to_vietnamese(value: str) -> str:
    value = value.strip().replace("\u2212", "-")
    if re.fullmatch(r"[+-]?\d+", value):
        return integer_to_vietnamese(int(value))
    decimal = re.fullmatch(r"([+-]?\d+)([.,])(\d+)", value)
    if decimal:
        head, _, tail = decimal.groups()
        sign = "âm " if head.startswith("-") else ""
        head = head.lstrip("+-")
        digit_names = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
        return f"{sign}{integer_to_vietnamese(int(head))} phẩy " + " ".join(
            digit_names[int(digit)] for digit in tail
        )
    scientific = re.fullmatch(r"([+-]?\d+(?:[.,]\d+)?)[eE]([+-]?\d+)", value)
    if scientific:
        coefficient, exponent = scientific.groups()
        return (
            f"{number_to_vietnamese(coefficient)} nhân mười mũ "
            f"{number_to_vietnamese(exponent)}"
        )
    # MathML can contain grouped or non-decimal numerals. Reading each glyph is
    # safer than silently changing their value.
    digit_names = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
    if value and all(char.isdigit() or char.isspace() for char in value):
        return " ".join(digit_names[int(char)] for char in value if char.isdigit())
    raise UnsupportedMathML(f"Unsupported numeral: {value!r}")


class VietnameseMathMLRenderer:
    def render(self, mathml: str) -> str:
        root = ET.fromstring(mathml)
        spoken = self._render(root).text
        spoken = re.sub(r"\s+", " ", spoken)
        spoken = re.sub(r"\s+,", ",", spoken)
        spoken = re.sub(r",(?:\s*,)+", ",", spoken)
        return spoken.strip(" ,")

    def _render(self, node: ET.Element) -> Phrase:
        tag = _tag(node)
        if tag in {"math", "mrow", "mstyle", "mpadded", "mtd"}:
            return self._render_row(_children(node))
        if tag == "semantics":
            children = _children(node)
            return self._render(children[0]) if children else Phrase("")
        if tag == "mn":
            return Phrase(number_to_vietnamese(_text(node)), "number")
        if tag == "mi":
            value = _text(node)
            return Phrase(_IDENTIFIERS.get(value, value), "identifier")
        if tag == "mtext":
            return Phrase(_text(node), "text")
        if tag == "mo":
            return self._operator(_text(node))
        if tag == "mfrac":
            return self._fraction(node)
        if tag == "msqrt":
            body = self._render_row(_children(node)).text
            return Phrase(f"căn bậc hai của {body}", "root")
        if tag == "mroot":
            children = _children(node)
            if len(children) != 2:
                raise UnsupportedMathML("mroot must have a radicand and an index")
            body = self._render(children[0]).text
            index = self._render(children[1]).text
            return Phrase(f"căn bậc {index} của {body}", "root")
        if tag == "msup":
            return self._superscript(node)
        if tag == "msub":
            return self._subscript(node)
        if tag in {"msubsup", "munderover"}:
            return self._subsup(node)
        if tag == "mover":
            return self._over(node)
        if tag == "munder":
            children = _children(node)
            if len(children) != 2:
                raise UnsupportedMathML("munder must have two children")
            return Phrase(
                f"{self._render(children[0]).text}, phía dưới là {self._render(children[1]).text}",
                "scripted",
            )
        if tag == "mfenced":
            return self._fenced(node)
        if tag == "mtable":
            return self._table(node)
        if tag in {"mtr", "mlabeledtr"}:
            cells = [self._render(child).text for child in _children(node)]
            return Phrase(", ".join(cells), "row")
        if tag == "menclose":
            body = self._render_row(_children(node)).text
            notation = node.attrib.get("notation", "longdiv")
            if "radical" in notation:
                return Phrase(f"căn bậc hai của {body}", "root")
            return Phrase(body)
        if tag in {"mspace", "mphantom", "annotation", "annotation-xml"}:
            return Phrase("")
        if tag == "maction":
            children = _children(node)
            return self._render(children[0]) if children else Phrase("")
        raise UnsupportedMathML(f"Unsupported MathML element: {tag}")

    def _operator(self, value: str) -> Phrase:
        if value in _OPEN_TO_CLOSE or value in _CLOSE or value in {"|", "‖"}:
            return Phrase(value, "fence")
        large_operators = {
            "∑": "tổng",
            "∏": "tích",
            "∫": "tích phân",
            "∬": "tích phân kép",
            "∭": "tích phân ba lớp",
            "∮": "tích phân đường kín",
        }
        if value in large_operators:
            return Phrase(large_operators[value], "large_operator")
        if value in _OPERATORS:
            return Phrase(_OPERATORS[value], "operator")
        if not value:
            return Phrase("")
        raise UnsupportedMathML(f"Unsupported operator: {value!r}")

    def _is_simple(self, node: ET.Element) -> bool:
        return _tag(_unwrap(node)) in {"mi", "mn"}

    def _is_numeric(self, node: ET.Element) -> bool:
        return _tag(_unwrap(node)) == "mn"

    def _fraction(self, node: ET.Element) -> Phrase:
        children = _children(node)
        if len(children) != 2:
            raise UnsupportedMathML("mfrac must have a numerator and denominator")
        numerator, denominator = children

        if node.attrib.get("linethickness") in {"0", "0px", "0em"}:
            return Phrase(
                f"tổ hợp chập {self._render(denominator).text} của "
                f"{self._render(numerator).text}",
                "binomial",
            )

        # dy/dx is conventionally clearer by mathematical role than by layout.
        num_parts = _children(_unwrap_row(numerator))
        den_parts = _children(_unwrap_row(denominator))
        if len(num_parts) == len(den_parts) == 2 and (
            _text(num_parts[0]) == _text(den_parts[0]) == "d"
            or _text(num_parts[0]) == _text(den_parts[0]) == "∂"
        ):
            derivative = (
                "đạo hàm riêng" if _text(num_parts[0]) == "∂" else "đạo hàm"
            )
            return Phrase(
                f"{derivative} của {self._render(num_parts[1]).text} theo "
                f"{self._render(den_parts[1]).text}",
                "fraction",
            )

        # d^n y / dx^n and its partial-derivative counterpart.
        if len(num_parts) == len(den_parts) == 2:
            num_diff = _script_base_and_power(num_parts[0])
            den_var = _script_base_and_power(den_parts[1])
            if (
                num_diff
                and den_var
                and _text(den_parts[0]) == num_diff[0]
                and num_diff[0] in {"d", "∂"}
                and num_diff[1] == den_var[1]
            ):
                derivative = "đạo hàm riêng" if num_diff[0] == "∂" else "đạo hàm"
                return Phrase(
                    f"{derivative} bậc {number_to_vietnamese(num_diff[1])} của "
                    f"{self._render(num_parts[1]).text} theo {self._render(_children(den_parts[1])[0]).text}",
                    "fraction",
                )

        top = self._render(numerator).text
        bottom = self._render(denominator).text
        if self._is_numeric(numerator) and self._is_numeric(denominator):
            return Phrase(f"{top} phần {bottom}", "fraction")
        if self._is_simple(numerator) and self._is_simple(denominator):
            return Phrase(f"{top} trên {bottom}", "fraction")
        return Phrase(f"phân số, {top}, tất cả trên {bottom}", "fraction")

    def _superscript(self, node: ET.Element) -> Phrase:
        children = _children(node)
        if len(children) != 2:
            raise UnsupportedMathML("msup must have a base and exponent")
        base_node, exponent_node = children
        base = self._render(base_node).text
        exponent = self._render(exponent_node).text
        raw_exponent = _text(_unwrap(exponent_node))
        prime_names = {"′": "phẩy", "″": "hai phẩy", "‴": "ba phẩy"}
        if raw_exponent in prime_names:
            return Phrase(f"{base} {prime_names[raw_exponent]}", "identifier")
        if raw_exponent == "2":
            return Phrase(f"{base} bình phương", "scripted")
        if raw_exponent == "3":
            return Phrase(f"{base} lập phương", "scripted")
        separator = ", " if not self._is_simple(exponent_node) else " "
        return Phrase(f"{base} mũ{separator}{exponent}", "scripted")

    def _subscript(self, node: ET.Element) -> Phrase:
        children = _children(node)
        if len(children) != 2:
            raise UnsupportedMathML("msub must have a base and subscript")
        base_node, subscript_node = children
        raw_base = _text(_unwrap(base_node))
        subscript = self._render(subscript_node).text
        if raw_base == "log":
            return Phrase(f"lô ga rít cơ số {subscript}", "log_base")
        if raw_base == "lim":
            return Phrase(subscript, "limit")
        base = self._render(base_node).text
        # Conventional x_1/a_n is natural without saying "chỉ số".
        if self._is_simple(base_node) and self._is_simple(subscript_node):
            return Phrase(f"{base} {subscript}", "scripted")
        return Phrase(f"{base} chỉ số {subscript}", "scripted")

    def _subsup(self, node: ET.Element) -> Phrase:
        children = _children(node)
        if len(children) != 3:
            raise UnsupportedMathML("sub/sup node must have three children")
        base_node, lower_node, upper_node = children
        raw_base = _text(_unwrap(base_node))
        lower = self._render(lower_node).text
        upper = self._render(upper_node).text
        names = {
            "∑": "tổng",
            "∏": "tích",
            "∫": "tích phân",
            "∬": "tích phân kép",
            "∭": "tích phân ba lớp",
            "∮": "tích phân đường kín",
        }
        if raw_base in names:
            return Phrase(f"{names[raw_base]} từ {lower} đến {upper}", "large_operator")
        base = self._render(base_node).text
        return Phrase(f"{base} chỉ số {lower}, mũ {upper}", "scripted")

    def _over(self, node: ET.Element) -> Phrase:
        children = _children(node)
        if len(children) != 2:
            raise UnsupportedMathML("mover must have two children")
        base = self._render(children[0]).text
        accent = _text(children[1])
        if accent in {"¯", "‾", "―", "→", "⃗"}:
            word = "véc tơ" if accent in {"→", "⃗"} else "gạch ngang"
            return Phrase(f"{word} {base}", "scripted")
        if accent in {"^", "ˆ", "^"}:
            return Phrase(f"{base} mũ", "scripted")
        return Phrase(f"{base}, phía trên là {self._render(children[1]).text}", "scripted")

    def _fenced(self, node: ET.Element) -> Phrase:
        open_char = node.attrib.get("open", "(")
        close_char = node.attrib.get("close", ")")
        body = self._render_row(_children(node)).text
        if open_char == close_char == "|":
            return Phrase(f"giá trị tuyệt đối của {body}", "group")
        return Phrase(f"trong ngoặc {body}, hết ngoặc", "group")

    def _table(self, node: ET.Element) -> Phrase:
        rows = [child for child in _children(node) if _tag(child) in {"mtr", "mlabeledtr"}]
        spoken_rows = []
        for row_number, row in enumerate(rows, 1):
            cells = [self._render(cell).text for cell in _children(row)]
            spoken_rows.append(
                f"hàng {integer_to_vietnamese(row_number)} là " + ", ".join(cells)
            )
        return Phrase(
            f"ma trận có {integer_to_vietnamese(len(rows))} hàng, "
            + "; ".join(spoken_rows),
            "table",
        )

    def _cases(self, node: ET.Element) -> Phrase:
        rows = [child for child in _children(node) if _tag(child) in {"mtr", "mlabeledtr"}]
        cell_rows = [[self._render(cell).text for cell in _children(row)] for row in rows]
        if cell_rows and all(len(cells) >= 2 for cells in cell_rows):
            cases = [f"{cells[0]} khi {cells[1]}" for cells in cell_rows]
            return Phrase("hàm từng phần, " + "; ".join(cases), "cases")
        equations = [cells[0] for cells in cell_rows if cells]
        return Phrase("hệ phương trình gồm, " + "; ".join(equations), "cases")

    def _render_row(self, children: list[ET.Element]) -> Phrase:
        if not children:
            return Phrase("")
        output: list[str] = []
        kinds: list[str] = []
        index = 0
        while index < len(children):
            raw = _text(children[index])

            # A cases environment has one opening brace and no closing token.
            if (
                _tag(children[index]) == "mo"
                and raw == "{"
                and index + 1 < len(children)
                and _tag(children[index + 1]) == "mtable"
            ):
                self._append(output, kinds, self._cases(children[index + 1]))
                index += 2
                continue

            # latex2mathml emits floor and ceiling fences as identifier nodes.
            floor_or_ceiling = {
                "⌊": ("⌋", "phần nguyên dưới"),
                "⌈": ("⌉", "phần nguyên trên"),
            }
            if raw in floor_or_ceiling:
                closer, name = floor_or_ceiling[raw]
                close = next(
                    (
                        position
                        for position in range(index + 1, len(children))
                        if _text(children[position]) == closer
                    ),
                    None,
                )
                if close is not None:
                    body = self._render_row(children[index + 1 : close]).text
                    self._append(output, kinds, Phrase(f"{name} của {body}", "group"))
                    index = close + 1
                    continue

            # Turn explicit delimiter tokens into one scoped group.
            if _tag(children[index]) == "mo" and (
                raw in _OPEN_TO_CLOSE or raw in {"|", "‖"}
            ):
                close_index = self._matching_fence(children, index, raw)
                if close_index is not None:
                    body = self._render_row(children[index + 1 : close_index]).text
                    if raw == "|":
                        phrase = Phrase(f"giá trị tuyệt đối của {body}", "group")
                    elif raw == "‖":
                        phrase = Phrase(f"chuẩn của {body}", "group")
                    elif raw == "{":
                        phrase = Phrase(f"tập hợp gồm {body}", "group")
                    elif (
                        index + 2 == close_index
                        and _tag(children[index + 1]) == "mfrac"
                        and children[index + 1].attrib.get("linethickness")
                        in {"0", "0px", "0em"}
                    ):
                        phrase = self._render(children[index + 1])
                    elif (
                        index + 2 == close_index
                        and _tag(children[index + 1]) == "mtable"
                    ):
                        phrase = self._render(children[index + 1])
                    else:
                        phrase = Phrase(f"trong ngoặc {body}, hết ngoặc", "group")
                    self._append(output, kinds, phrase)
                    index = close_index + 1
                    continue
                raise UnsupportedMathML(f"Unclosed fence: {raw!r}")

            # f(x), sin(x), ...: consume the following explicit parentheses.
            function = self._function_call(children, index)
            if function is not None:
                phrase, consumed = function
                self._append(output, kinds, phrase)
                index += consumed
                continue

            # log x / ln x conventionally use "của" even without brackets.
            if (
                _tag(children[index]) == "mi"
                and raw in {"log", "ln"}
                and index + 1 < len(children)
            ):
                argument, consumed = self._right_operand(children, index + 1)
                self._append(
                    output,
                    kinds,
                    Phrase(f"{self._render(children[index]).text} của {argument.text}"),
                )
                index += consumed + 1
                continue

            # Prime marks directly following a function identifier.
            if _tag(children[index]) == "mi" and index + 1 < len(children):
                prime_count = 0
                while index + 1 + prime_count < len(children) and _text(
                    children[index + 1 + prime_count]
                ) == "′":
                    prime_count += 1
                if prime_count:
                    name = self._render(children[index]).text
                    suffix = "phẩy" if prime_count == 1 else f"{integer_to_vietnamese(prime_count)} phẩy"
                    next_index = index + prime_count + 1
                    if (
                        next_index < len(children)
                        and _tag(children[next_index]) == "mo"
                        and _text(children[next_index]) == "("
                    ):
                        close = self._matching_fence(children, next_index, "(")
                        if close is not None:
                            argument = self._render_row(children[next_index + 1 : close]).text
                            self._append(
                                output,
                                kinds,
                                Phrase(f"{name} {suffix} của {argument}", "identifier"),
                            )
                            index = close + 1
                            continue
                    self._append(output, kinds, Phrase(f"{name} {suffix}", "identifier"))
                    index = next_index
                    continue

            # latex2mathml keeps a written slash as <mo>/</mo>. Build a scoped
            # fraction from its adjacent operands instead of reading it as a
            # context-free operator.
            if (
                _tag(children[index]) == "mo"
                and raw == "/"
                and output
                and index + 1 < len(children)
            ):
                right, consumed = self._right_operand(children, index + 1)
                left = Phrase(output.pop(), kinds.pop())
                self._append(output, kinds, self._slash_fraction(left, right))
                index += consumed + 1
                continue

            phrase = self._render(children[index])

            # A root followed by more arithmetic needs an audible closing scope.
            if phrase.kind == "root" and self._has_following_expression(children, index):
                phrase = Phrase(phrase.text + ", hết căn,", "closed_scope")

            # Large operators own the following expression. This adds the natural
            # "của" in sum/product/integral/limit speech.
            if phrase.kind in {"large_operator", "limit"} and index + 1 < len(children):
                rest = children[index + 1 :]
                stop_at_sum = phrase.kind == "limit" or "tích phân" not in phrase.text
                boundary = self._expression_boundary(rest, stop_at_sum=stop_at_sum)
                body_nodes = rest[:boundary]
                if not body_nodes:
                    raise UnsupportedMathML("Large operator has no following expression")
                if phrase.kind == "limit":
                    body, differential = self._render_row(body_nodes).text, None
                    text = f"giới hạn của {body} khi {phrase.text}"
                else:
                    body, differential = self._integral_body(body_nodes) if "tích phân" in phrase.text else (self._render_row(body_nodes).text, None)
                    text = f"{phrase.text} của {body}"
                if differential:
                    text += f" theo {differential}"
                self._append(output, kinds, Phrase(text, "value"))
                index += len(body_nodes) + 1
                if index >= len(children):
                    break
                continue

            # log_a b must say "của b" rather than merely concatenate tokens.
            if phrase.kind == "log_base" and index + 1 < len(children):
                argument = self._render(children[index + 1]).text
                self._append(output, kinds, Phrase(f"{phrase.text} của {argument}"))
                index += 2
                continue

            # Minus is unary at row start or immediately after another operator.
            if _tag(children[index]) == "mo" and raw in {"-", "−"}:
                unary = not kinds or kinds[-1] == "operator"
                phrase = Phrase("âm" if unary else "trừ", "operator")
            elif _tag(children[index]) == "mo" and raw == "+":
                unary = not kinds or kinds[-1] == "operator"
                phrase = Phrase("dương" if unary else "cộng", "operator")

            self._append(output, kinds, phrase)
            index += 1

        return Phrase(" ".join(part for part in output if part))

    def _append(self, output: list[str], kinds: list[str], phrase: Phrase) -> None:
        if not phrase.text:
            return
        # Juxtaposed parentheses represent multiplication; juxtaposed symbols
        # such as 4ac deliberately remain "bốn a c".
        if kinds and phrase.kind in {"group", "table"} and kinds[-1] not in {"operator"}:
            output.append("nhân")
            kinds.append("operator")
        output.append(phrase.text)
        kinds.append(phrase.kind)

    def _matching_fence(
        self, children: list[ET.Element], start: int, opener: str
    ) -> int | None:
        expected = opener if opener in {"|", "‖"} else _OPEN_TO_CLOSE[opener]
        depth = 0
        for index in range(start + 1, len(children)):
            if _tag(children[index]) != "mo":
                continue
            value = _text(children[index])
            if opener not in {"|", "‖"} and value == opener:
                depth += 1
            elif value == expected:
                if depth == 0:
                    return index
                depth -= 1
        return None

    def _function_call(
        self, children: list[ET.Element], index: int
    ) -> tuple[Phrase, int] | None:
        if index + 2 >= len(children):
            return None
        node = children[index]
        raw_name = _text(_unwrap(node))
        node_tag = _tag(_unwrap(node))
        if node_tag not in {"mi", "mo", "msup", "msub"}:
            return None
        callable_name = raw_name
        if node_tag in {"msup", "msub"}:
            scripted_children = _children(_unwrap(node))
            if scripted_children:
                callable_name = _text(_unwrap(scripted_children[0]))
        if callable_name not in _CALLABLE_IDENTIFIERS:
            return None
        if _tag(children[index + 1]) != "mo" or _text(children[index + 1]) != "(":
            return None
        close = self._matching_fence(children, index + 1, "(")
        if close is None:
            return None
        argument = self._render_row(children[index + 2 : close]).text
        name = self._render(node).text
        connector = " " if callable_name in _FUNCTIONS - {"log", "ln"} else " của "
        return Phrase(f"{name}{connector}{argument}", "identifier"), close - index + 1

    def _has_following_expression(self, children: list[ET.Element], index: int) -> bool:
        return any(_text(child) not in {",", ";", "."} for child in children[index + 1 :])

    def _right_operand(
        self, children: list[ET.Element], start: int
    ) -> tuple[Phrase, int]:
        node = children[start]
        raw = _text(node)
        if _tag(node) == "mo" and raw in _OPEN_TO_CLOSE:
            close = self._matching_fence(children, start, raw)
            if close is None:
                raise UnsupportedMathML("Unclosed denominator group")
            body = self._render_row(children[start + 1 : close]).text
            return Phrase(body, "group"), close - start + 1
        return self._render(node), 1

    def _slash_fraction(self, left: Phrase, right: Phrase) -> Phrase:
        left_text = _without_group_words(left.text)
        right_text = _without_group_words(right.text)
        if left.kind == right.kind == "number":
            return Phrase(f"{left_text} phần {right_text}", "fraction")
        if left.kind in {"number", "identifier"} and right.kind in {"number", "identifier"}:
            return Phrase(f"{left_text} trên {right_text}", "fraction")
        return Phrase(
            f"phân số, {left_text}, tất cả trên {right_text}",
            "fraction",
        )

    def _integral_body(self, nodes: list[ET.Element]) -> tuple[str, str | None]:
        if len(nodes) >= 2 and _text(nodes[-2]) == "d" and _tag(nodes[-2]) == "mi":
            differential = self._render(nodes[-1]).text
            return self._render_row(nodes[:-2]).text, differential
        return self._render_row(nodes).text, None

    def _expression_boundary(
        self, nodes: list[ET.Element], *, stop_at_sum: bool
    ) -> int:
        depth = 0
        for index, node in enumerate(nodes):
            if _tag(node) != "mo":
                continue
            value = _text(node)
            if value in _OPEN_TO_CLOSE:
                depth += 1
                continue
            if value in _CLOSE:
                depth = max(0, depth - 1)
                continue
            if depth == 0 and (
                value in _RELATIONS or (stop_at_sum and value in {"+", "-", "−"})
            ):
                return index
        return len(nodes)


def _unwrap_row(node: ET.Element) -> ET.Element:
    while _tag(node) in {"math", "mrow", "mstyle", "mpadded"}:
        children = _children(node)
        if len(children) != 1 or _tag(children[0]) == "mrow":
            break
        node = children[0]
    return node


def _without_group_words(text: str) -> str:
    match = re.fullmatch(r"trong ngoặc (.*), hết ngoặc", text)
    return match.group(1) if match else text


def _script_base_and_power(node: ET.Element) -> tuple[str, str] | None:
    node = _unwrap(node)
    if _tag(node) != "msup":
        return None
    children = _children(node)
    if len(children) != 2:
        return None
    return _text(_unwrap(children[0])), _text(_unwrap(children[1]))


def render_mathml(mathml: str) -> str:
    """Return Vietnamese speech or raise :class:`UnsupportedMathML`."""

    return VietnameseMathMLRenderer().render(mathml)
