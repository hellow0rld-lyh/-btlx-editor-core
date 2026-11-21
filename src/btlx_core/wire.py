# SPDX-License-Identifier: LGPL-3.0-or-later
#!/usr/bin/env python3
"""Strict protobuf-wire primitives for BTLX recovery.

This module intentionally knows nothing about EW7/WS field semantics.  It parses
wire records losslessly and preserves each field's original bytes so unknown
fields, field order, duplicate fields, and non-canonical varints can be
re-emitted byte-for-byte.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

MAX_FIELD_NUMBER = (1 << 29) - 1
WIRE_VARINT = 0
WIRE_FIXED64 = 1
WIRE_LENGTH_DELIMITED = 2
WIRE_START_GROUP = 3
WIRE_END_GROUP = 4
WIRE_FIXED32 = 5
VALID_WIRE_TYPES = {
    WIRE_VARINT,
    WIRE_FIXED64,
    WIRE_LENGTH_DELIMITED,
    WIRE_START_GROUP,
    WIRE_END_GROUP,
    WIRE_FIXED32,
}


class WireParseError(ValueError):
    """A strict protobuf-wire parse error with a byte offset."""

    def __init__(self, offset: int, message: str) -> None:
        super().__init__(f"offset {offset}: {message}")
        self.offset = offset
        self.message = message


@dataclass(frozen=True)
class Varint:
    value: int
    raw: bytes
    canonical: bool


@dataclass(frozen=True)
class Field:
    number: int
    wire_type: int
    start: int
    end: int
    raw: bytes
    key: Varint
    value_varint: Varint | None = None
    length_varint: Varint | None = None
    payload: bytes | None = None
    children: tuple["Field", ...] = ()


@dataclass(frozen=True)
class Message:
    fields: tuple[Field, ...]
    raw: bytes


def encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("protobuf wire varints are unsigned at the raw layer")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def read_varint(data: bytes, offset: int, end: int | None = None) -> tuple[Varint, int]:
    limit = len(data) if end is None else end
    start = offset
    value = 0
    shift = 0
    for _ in range(10):
        if offset >= limit:
            raise WireParseError(start, "truncated varint")
        byte = data[offset]
        offset += 1
        if shift == 63 and byte > 1:
            raise WireParseError(start, "varint exceeds uint64")
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            raw = data[start:offset]
            return Varint(value=value, raw=raw, canonical=(raw == encode_varint(value))), offset
        shift += 7
    raise WireParseError(start, "varint exceeds 10 bytes")


def _parse_sequence(
    data: bytes,
    offset: int,
    end: int,
    stop_group: int | None,
) -> tuple[list[Field], int, bytes | None]:
    fields: list[Field] = []
    while offset < end:
        start = offset
        key, offset = read_varint(data, offset, end)
        if key.value == 0:
            raise WireParseError(start, "field key 0 is invalid")
        number = key.value >> 3
        wire_type = key.value & 0x7
        if number < 1 or number > MAX_FIELD_NUMBER:
            raise WireParseError(start, f"invalid field number {number}")
        if wire_type not in VALID_WIRE_TYPES:
            raise WireParseError(start, f"invalid wire type {wire_type}")

        if wire_type == WIRE_END_GROUP:
            if stop_group is None:
                raise WireParseError(start, f"unexpected end-group for field {number}")
            if number != stop_group:
                raise WireParseError(
                    start,
                    f"end-group field {number} does not match start-group field {stop_group}",
                )
            return fields, offset, data[start:offset]

        if wire_type == WIRE_VARINT:
            value, offset = read_varint(data, offset, end)
            fields.append(
                Field(
                    number=number,
                    wire_type=wire_type,
                    start=start,
                    end=offset,
                    raw=data[start:offset],
                    key=key,
                    value_varint=value,
                )
            )
            continue

        if wire_type == WIRE_FIXED64:
            value_end = offset + 8
            if value_end > end:
                raise WireParseError(offset, "truncated fixed64")
            offset = value_end
            fields.append(
                Field(
                    number=number,
                    wire_type=wire_type,
                    start=start,
                    end=offset,
                    raw=data[start:offset],
                    key=key,
                    payload=data[offset - 8 : offset],
                )
            )
            continue

        if wire_type == WIRE_LENGTH_DELIMITED:
            length, payload_start = read_varint(data, offset, end)
            payload_end = payload_start + length.value
            if payload_end > end:
                raise WireParseError(offset, f"length-delimited payload exceeds message by {payload_end - end} bytes")
            offset = payload_end
            fields.append(
                Field(
                    number=number,
                    wire_type=wire_type,
                    start=start,
                    end=offset,
                    raw=data[start:offset],
                    key=key,
                    length_varint=length,
                    payload=data[payload_start:payload_end],
                )
            )
            continue

        if wire_type == WIRE_START_GROUP:
            children, group_end, end_group_raw = _parse_sequence(data, offset, end, number)
            if end_group_raw is None:
                raise WireParseError(start, f"unterminated group field {number}")
            offset = group_end
            fields.append(
                Field(
                    number=number,
                    wire_type=wire_type,
                    start=start,
                    end=offset,
                    raw=data[start:offset],
                    key=key,
                    children=tuple(children),
                )
            )
            continue

        if wire_type == WIRE_FIXED32:
            value_end = offset + 4
            if value_end > end:
                raise WireParseError(offset, "truncated fixed32")
            offset = value_end
            fields.append(
                Field(
                    number=number,
                    wire_type=wire_type,
                    start=start,
                    end=offset,
                    raw=data[start:offset],
                    key=key,
                    payload=data[offset - 4 : offset],
                )
            )
            continue

        raise AssertionError("unreachable wire type")

    if stop_group is not None:
        raise WireParseError(end, f"unterminated group field {stop_group}")
    return fields, offset, None


def parse_message(data: bytes) -> Message:
    fields, offset, _ = _parse_sequence(data, 0, len(data), None)
    if offset != len(data):
        raise WireParseError(offset, "parser did not consume the full message")
    return Message(fields=tuple(fields), raw=data)


def serialize_preserving(message: Message | Iterable[Field]) -> bytes:
    """Re-emit fields in original order using their original encoded bytes."""

    fields = message.fields if isinstance(message, Message) else tuple(message)
    return b"".join(field.raw for field in fields)


def try_parse_message(data: bytes) -> Message | None:
    try:
        return parse_message(data)
    except WireParseError:
        return None


def try_parse_packed_varints(data: bytes) -> tuple[Varint, ...] | None:
    if not data:
        return None
    values: list[Varint] = []
    offset = 0
    try:
        while offset < len(data):
            value, offset = read_varint(data, offset, len(data))
            values.append(value)
    except WireParseError:
        return None
    return tuple(values)


def utf8_text_score(data: bytes) -> tuple[bool, float, str | None]:
    if not data:
        return False, 0.0, ""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False, 0.0, None
    if not text:
        return False, 0.0, text
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\r\n\t")
    score = printable / len(text)
    return score >= 0.85 and "\x00" not in text, score, text


def classify_length_delimited(data: bytes) -> dict[str, object]:
    """Return structural candidates without promoting any semantic interpretation."""

    utf8_candidate, utf8_score, _ = utf8_text_score(data)
    packed_varints = try_parse_packed_varints(data)
    nested = try_parse_message(data)

    nested_nonempty = nested is not None and bool(nested.fields)
    nested_field_count = len(nested.fields) if nested is not None else 0
    nested_distinct_fields = len({field.number for field in nested.fields}) if nested_nonempty else 0
    nested_all_keys_canonical = (
        all(field.key.canonical for field in nested.fields) if nested_nonempty else False
    )

    score = 0
    reasons: list[str] = []
    if nested_nonempty:
        score += 1
        reasons.append("full-payload-wire-parse")
        if nested_field_count >= 2:
            score += 1
            reasons.append("multiple-wire-fields")
        if nested_distinct_fields >= 2:
            score += 1
            reasons.append("multiple-field-numbers")
        if nested_all_keys_canonical:
            score += 1
            reasons.append("canonical-field-keys")
        if utf8_candidate:
            score -= 2
            reasons.append("also-plausible-utf8")
        if packed_varints is not None and len(packed_varints) >= 2:
            score -= 1
            reasons.append("also-plausible-packed-varints")

    if not nested_nonempty:
        confidence = "none"
    elif score >= 3:
        confidence = "strong-candidate"
    elif score >= 2:
        confidence = "possible-candidate"
    else:
        confidence = "weak-candidate"

    return {
        "length": len(data),
        "embeddedMessageParseable": nested is not None,
        "embeddedMessageNonEmpty": nested_nonempty,
        "embeddedMessageFieldCount": nested_field_count,
        "embeddedMessageDistinctFieldCount": nested_distinct_fields,
        "embeddedMessageCandidateConfidence": confidence,
        "embeddedMessageCandidateReasons": reasons,
        "utf8Candidate": utf8_candidate,
        "utf8PrintableRatio": round(utf8_score, 6),
        "packedVarintCandidate": packed_varints is not None and len(packed_varints) >= 2,
        "packedVarintCount": len(packed_varints) if packed_varints is not None else 0,
        "packedVarintAllCanonical": (
            all(value.canonical for value in packed_varints) if packed_varints else False
        ),
        "packedFixed32Candidate": bool(data) and len(data) % 4 == 0,
        "packedFixed64Candidate": bool(data) and len(data) % 8 == 0,
        "rawBytesCandidate": True,
    }
