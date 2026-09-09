"""Recursive-descent parser for Purdue prerequisite strings.

Supported patterns:
  - Single course:  CS 18000
  - AND-list:       CS 18000 and CS 18200
  - OR-list:        CS 18000 or CS 18200
  - With grade:     CS 18000 (C or better)
  - Nested:         (CS 18000 or CS 18200) and CS 25100

Everything else → machine_checkable=False, verbatim retained.
English prose conditions ("permission of instructor", "junior standing", etc.)
always produce not_machine_checkable.
"""

from __future__ import annotations

import re
from typing import Optional

from granular.schema import AndList, OrList, PredicateNode, PrerequisiteRule, SingleCourse

# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

_COURSE_RE = re.compile(r"\b([A-Z]{2,5})\s+(\d{5}[A-Z]?)\b")
_GRADE_RE = re.compile(r"\(([A-D][+-]?)\s+or\s+better\)", re.IGNORECASE)


def _normalise_course_id(subject: str, number: str) -> str:
    return f"{subject}-{number}"


class _Token:
    COURSE = "COURSE"
    AND = "AND"
    OR = "OR"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    EOF = "EOF"

    def __init__(self, kind: str, value: str = "") -> None:
        self.kind = kind
        self.value = value

    def __repr__(self) -> str:
        return f"Token({self.kind}, {self.value!r})"


def _tokenise(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    text = text.strip()
    while i < len(text):
        # Skip whitespace
        if text[i].isspace():
            i += 1
            continue
        # Parentheses
        if text[i] == "(":
            # Check for grade clause: (C or better)
            grade_m = _GRADE_RE.match(text, i)
            if grade_m:
                tokens.append(_Token(_Token.COURSE, f"__grade__{grade_m.group(1)}"))
                i = grade_m.end()
                continue
            tokens.append(_Token(_Token.LPAREN))
            i += 1
            continue
        if text[i] == ")":
            tokens.append(_Token(_Token.RPAREN))
            i += 1
            continue
        # Course: SUBJ NNNNN
        course_m = _COURSE_RE.match(text, i)
        if course_m:
            cid = _normalise_course_id(course_m.group(1), course_m.group(2))
            tokens.append(_Token(_Token.COURSE, cid))
            i = course_m.end()
            continue
        # AND / OR keywords
        if re.match(r"\band\b", text[i:], re.IGNORECASE):
            tokens.append(_Token(_Token.AND))
            i += 3
            continue
        if re.match(r"\bor\b", text[i:], re.IGNORECASE):
            tokens.append(_Token(_Token.OR))
            i += 2
            continue
        # Unrecognised character — advance
        i += 1
    tokens.append(_Token(_Token.EOF))
    return tokens


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class _Parser:
    """Recursive descent parser over the token stream."""

    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _consume(self) -> _Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def parse(self) -> Optional[PredicateNode]:
        result = self._expr()
        if self._peek().kind != _Token.EOF:
            return None  # trailing tokens → unparseable
        return result

    def _expr(self) -> Optional[PredicateNode]:
        """expr := term (AND term)* | term (OR term)*"""
        left = self._term()
        if left is None:
            return None

        children = [left]
        op = None

        while self._peek().kind in (_Token.AND, _Token.OR):
            current_op = self._consume().kind
            if op is not None and current_op != op:
                # Mixed AND/OR without parens — too ambiguous
                return None
            op = current_op
            right = self._term()
            if right is None:
                return None
            children.append(right)

        if len(children) == 1:
            return children[0]
        if op == _Token.AND:
            return AndList(children=children)
        return OrList(children=children)

    def _term(self) -> Optional[PredicateNode]:
        """term := COURSE [grade_clause] | LPAREN expr RPAREN"""
        tok = self._peek()
        if tok.kind == _Token.LPAREN:
            self._consume()  # consume (
            inner = self._expr()
            if self._peek().kind != _Token.RPAREN:
                return None
            self._consume()  # consume )
            return inner
        if tok.kind == _Token.COURSE and not tok.value.startswith("__grade__"):
            self._consume()
            course_id = tok.value
            # Optional grade clause immediately following
            min_grade: Optional[str] = None
            if (
                self._peek().kind == _Token.COURSE
                and self._tokens[self._pos].value.startswith("__grade__")
            ):
                grade_tok = self._consume()
                min_grade = grade_tok.value.replace("__grade__", "")
            return SingleCourse(course_id=course_id, min_grade=min_grade)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_prerequisite(rule_id: str, verbatim: str) -> PrerequisiteRule:
    """Parse a verbatim prerequisite string into a PrerequisiteRule.

    Returns a machine_checkable=True rule on success,
    machine_checkable=False with verbatim text retained on failure.
    """
    if not verbatim or not verbatim.strip():
        return PrerequisiteRule(
            rule_id=rule_id,
            verbatim_text=verbatim or "(empty)",
            machine_checkable=False,
        )

    # Quick rejection: if the text contains no course-like patterns, skip parsing
    if not _COURSE_RE.search(verbatim):
        return PrerequisiteRule(
            rule_id=rule_id,
            verbatim_text=verbatim,
            machine_checkable=False,
        )

    tokens = _tokenise(verbatim)
    parser = _Parser(tokens)
    result = parser.parse()

    if result is None:
        return PrerequisiteRule(
            rule_id=rule_id,
            verbatim_text=verbatim,
            machine_checkable=False,
        )

    return PrerequisiteRule(
        rule_id=rule_id,
        verbatim_text=verbatim,
        machine_checkable=True,
        structured=result,
    )
