#!/usr/bin/env python
"""Extract user-visible text units from supported source formats."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


TEXT_EXTENSIONS = {
    ".html",
    ".json",
    ".jsonl",
    ".md",
    ".properties",
    ".txt",
    ".yaml",
    ".yml",
}

ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ANSI_OSC_RE = re.compile(r"\x1b\][^\x07]*(?:\x07|\x1b\\)")
UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9A-Fa-f]{4})")
MARKDOWN_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
MARKDOWN_INLINE_CODE_RE = re.compile(r"(?P<ticks>`+).*?(?P=ticks)")


def clean_terminal_text(text: str) -> str:
    return ANSI_CSI_RE.sub("", ANSI_OSC_RE.sub("", text))


def unit(
    text: str,
    logical_path: str,
    line_number: int | None,
    kind: str,
    collapse_whitespace: bool = True,
) -> dict[str, object] | None:
    normalized = (
        re.sub(r"\s+", " ", text).strip()
        if collapse_whitespace
        else text.rstrip()
    )
    if not normalized.strip():
        return None
    return {
        "logical_path": logical_path,
        "line_number": line_number,
        "kind": kind,
        "text": normalized,
    }


def extract_lines(text: str, kind: str = "text") -> list[dict[str, object]]:
    text = clean_terminal_text(text)
    units: list[dict[str, object]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        extracted = unit(
            line,
            f"/line/{line_number}",
            line_number,
            kind,
            collapse_whitespace=False,
        )
        if extracted:
            units.append(extracted)
    return units


def extract_markdown(text: str) -> list[dict[str, object]]:
    lines = text.splitlines()
    frontmatter_end = 0
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:100], start=1):
            if line.strip() == "---":
                frontmatter_end = index + 1
                break

    units: list[dict[str, object]] = []
    fence: str | None = None
    for line_number, line in enumerate(lines, start=1):
        if line_number <= frontmatter_end:
            continue
        fence_match = MARKDOWN_FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence is not None:
            continue
        masked = MARKDOWN_INLINE_CODE_RE.sub(
            lambda match: " " * len(match.group(0)), line
        )
        extracted = unit(
            masked,
            f"/line/{line_number}",
            line_number,
            "markdown",
            collapse_whitespace=False,
        )
        if extracted:
            units.append(extracted)
    return units


class VisibleHtmlParser(HTMLParser):
    BLOCK_TAGS = {
        "blockquote",
        "button",
        "caption",
        "div",
        "dd",
        "dt",
        "figcaption",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "label",
        "legend",
        "li",
        "main",
        "nav",
        "option",
        "p",
        "section",
        "td",
        "th",
        "title",
    }
    SKIP_TAGS = {
        "code",
        "pre",
        "script",
        "style",
        "noscript",
        "template",
        "svg",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tag_stack: list[str] = []
        self.skip_depth = 0
        self.contexts: list[dict[str, object]] = []
        self.units: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.casefold()
        self.tag_stack.append(tag)
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth == 0 and tag in self.BLOCK_TAGS:
            line_number, _ = self.getpos()
            self.contexts.append(
                {
                    "tag": tag,
                    "line_number": line_number,
                    "logical_path": "/" + "/".join(self.tag_stack),
                    "parts": [],
                }
            )

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del tag, attrs

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.contexts:
            self.contexts[-1]["parts"].append(data)  # type: ignore[union-attr]
            return
        extracted = unit(
            data,
            "/" + "/".join(self.tag_stack),
            self.getpos()[0],
            "html_text",
        )
        if extracted:
            self.units.append(extracted)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        if self.skip_depth == 0 and self.contexts and self.contexts[-1]["tag"] == tag:
            context = self.contexts.pop()
            extracted = unit(
                "".join(context["parts"]),  # type: ignore[arg-type]
                str(context["logical_path"]),
                int(context["line_number"]),
                "html_text",
            )
            if extracted:
                self.units.append(extracted)
        if tag in self.tag_stack:
            reverse_index = self.tag_stack[::-1].index(tag)
            del self.tag_stack[len(self.tag_stack) - reverse_index - 1 :]


def extract_html(text: str) -> list[dict[str, object]]:
    parser = VisibleHtmlParser()
    parser.feed(text)
    parser.close()
    return parser.units


def escape_json_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def extract_json_value(
    value: Any,
    logical_path: str = "",
    line_number: int | None = None,
) -> list[dict[str, object]]:
    units: list[dict[str, object]] = []
    if isinstance(value, str):
        extracted = unit(value, logical_path or "/", line_number, "json_value")
        if extracted:
            units.append(extracted)
    elif isinstance(value, dict):
        for key, child in value.items():
            units.extend(
                extract_json_value(
                    child,
                    f"{logical_path}/{escape_json_pointer(str(key))}",
                    line_number,
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            units.extend(
                extract_json_value(child, f"{logical_path}/{index}", line_number)
            )
    return units


def extract_json(text: str) -> list[dict[str, object]]:
    return extract_json_value(json.loads(text))


def extract_jsonl(text: str) -> list[dict[str, object]]:
    units: list[dict[str, object]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            extracted = unit(
                line, f"/line/{line_number}", line_number, "invalid_jsonl"
            )
            if extracted:
                units.append(extracted)
            continue
        for extracted in extract_json_value(value, f"/line/{line_number}", line_number):
            units.append(extracted)
    return units


def extract_yaml(text: str) -> list[dict[str, object]]:
    try:
        import yaml
        from yaml.nodes import MappingNode, ScalarNode, SequenceNode
    except ImportError as error:  # pragma: no cover - environment dependency guard
        raise RuntimeError("PyYAML is required for YAML extraction") from error

    units: list[dict[str, object]] = []

    def visit(node: object, logical_path: str) -> None:
        if isinstance(node, ScalarNode):
            if node.tag == "tag:yaml.org,2002:str":
                extracted = unit(
                    node.value,
                    logical_path or "/",
                    node.start_mark.line + 1,
                    "yaml_value",
                )
                if extracted:
                    units.append(extracted)
            return
        if isinstance(node, SequenceNode):
            for index, child in enumerate(node.value):
                visit(child, f"{logical_path}/{index}")
            return
        if isinstance(node, MappingNode):
            for key_node, value_node in node.value:
                if isinstance(key_node, ScalarNode):
                    key = escape_json_pointer(str(key_node.value))
                else:
                    key = "?"
                visit(value_node, f"{logical_path}/{key}")

    for document_index, document in enumerate(yaml.compose_all(text)):
        if document is not None:
            visit(document, f"/document/{document_index}")
    return units


def unescape_properties(value: str) -> str:
    value = UNICODE_ESCAPE_RE.sub(lambda match: chr(int(match.group(1), 16)), value)
    replacements = {
        r"\n": "\n",
        r"\r": "\r",
        r"\t": "\t",
        r"\f": "\f",
        r"\=": "=",
        r"\:": ":",
        r"\ ": " ",
        r"\\": "\\",
    }
    for escaped, plain in replacements.items():
        value = value.replace(escaped, plain)
    return value


def split_property(line: str) -> tuple[str, str]:
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character in "=:" or character.isspace():
            key = line[:index].strip()
            value_start = index
            while value_start < len(line) and (
                line[value_start].isspace() or line[value_start] in "=:"
            ):
                value_start += 1
            return key, line[value_start:]
    return line.strip(), ""


def extract_properties(text: str) -> list[dict[str, object]]:
    logical_lines: list[tuple[int, str]] = []
    buffer = ""
    start_line = 1
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not buffer:
            start_line = line_number
        buffer += line.lstrip() if buffer else line
        trailing_backslashes = len(buffer) - len(buffer.rstrip("\\"))
        if trailing_backslashes % 2 == 1:
            buffer = buffer[:-1]
            continue
        logical_lines.append((start_line, buffer))
        buffer = ""
    if buffer:
        logical_lines.append((start_line, buffer))

    units: list[dict[str, object]] = []
    for line_number, line in logical_lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith(("#", "!")):
            continue
        key, value = split_property(line)
        extracted = unit(
            unescape_properties(value),
            f"/{escape_json_pointer(key)}",
            line_number,
            "property_value",
        )
        if extracted:
            units.append(extracted)
    return units


def extract_source_text(path: Path) -> list[dict[str, object]]:
    extension = path.suffix.casefold()
    if extension not in TEXT_EXTENSIONS:
        raise ValueError(f"Unsupported source format: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if extension == ".md":
        units = extract_markdown(text)
    elif extension == ".html":
        units = extract_html(text)
    elif extension == ".json":
        units = extract_json(text)
    elif extension == ".jsonl":
        units = extract_jsonl(text)
    elif extension in {".yaml", ".yml"}:
        units = extract_yaml(text)
    elif extension == ".properties":
        units = extract_properties(text)
    else:
        units = extract_lines(text)
    for index, extracted in enumerate(units, start=1):
        extracted["unit_id"] = f"unit-{index:06d}"
        extracted["source_format"] = extension
    return units
