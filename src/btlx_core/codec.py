# SPDX-License-Identifier: LGPL-3.0-or-later
#!/usr/bin/env python3
"""Profile-aware lossless BTLX read/write/diff core.

Untouched fields are always serialized from their original encoded bytes.
Edits are surgical: only the selected leaf field and the length prefixes of its
ancestor message fields are re-encoded.
"""

from __future__ import annotations

import json
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schema import (
    PACKABLE_TYPES,
    FieldDescriptor,
    MessageDescriptor,
    SchemaProfile,
    WIRE_BY_TYPE,
    load_profile,
)
from .wire import (
    Field,
    Message,
    WireParseError,
    encode_varint,
    parse_message,
    read_varint,
)

_PATH_SEGMENT = re.compile(
    r"^(?P<token>#?\d+|[A-Za-z_][A-Za-z0-9_]*)(?:\[(?P<index>\d+)\])?$"
)


class CodecError(ValueError):
    """A profile-aware BTLX codec error."""


@dataclass(frozen=True)
class PathSegment:
    token: str
    occurrence: int = 0


def parse_field_path(path: str) -> tuple[PathSegment, ...]:
    text = path.strip()
    if not text:
        raise CodecError("field path is empty")
    segments: list[PathSegment] = []
    for raw in text.split("."):
        match = _PATH_SEGMENT.fullmatch(raw)
        if match is None:
            raise CodecError(
                f"invalid path segment {raw!r}; use Name, 13, #13, or Name[2]"
            )
        token = match.group("token")
        if token.startswith("#"):
            token = token[1:]
        occurrence = int(match.group("index") or "0")
        segments.append(PathSegment(token=token, occurrence=occurrence))
    return tuple(segments)


def _signed_from_unsigned(value: int, bits: int) -> int:
    mask = (1 << bits) - 1
    value &= mask
    sign = 1 << (bits - 1)
    return value - (1 << bits) if value & sign else value


def _zigzag_decode(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def _zigzag_encode(value: int, bits: int) -> int:
    minimum = -(1 << (bits - 1))
    maximum = (1 << (bits - 1)) - 1
    if value < minimum or value > maximum:
        raise CodecError(f"value {value} outside sint{bits} range")
    return (value << 1) ^ (value >> (bits - 1))


def _unsigned_checked(value: int, bits: int, label: str) -> int:
    if value < 0 or value > (1 << bits) - 1:
        raise CodecError(f"value {value} outside {label} range")
    return value


def _signed_varint(value: int, bits: int, label: str) -> int:
    minimum = -(1 << (bits - 1))
    maximum = (1 << (bits - 1)) - 1
    if value < minimum or value > maximum:
        raise CodecError(f"value {value} outside {label} range")
    if value < 0:
        return value & ((1 << 64) - 1)
    return value


def _decode_varint_value(value: int, field_type: str) -> Any:
    if field_type == "bool":
        return bool(value)
    if field_type in {"int32", "enum"}:
        return _signed_from_unsigned(value, 32)
    if field_type == "int64":
        return _signed_from_unsigned(value, 64)
    if field_type == "sint32":
        return _zigzag_decode(value)
    if field_type == "sint64":
        return _zigzag_decode(value)
    if field_type == "uint32":
        return value & 0xFFFFFFFF
    if field_type == "uint64":
        return value
    return value


def _encode_varint_value(value: Any, field_type: str) -> bytes:
    if field_type == "bool":
        if not isinstance(value, bool):
            raise CodecError("bool field requires true/false")
        return encode_varint(1 if value else 0)
    if not isinstance(value, int) or isinstance(value, bool):
        raise CodecError(f"{field_type} field requires an integer")
    if field_type in {"int32", "enum"}:
        return encode_varint(_signed_varint(value, 32, field_type))
    if field_type == "int64":
        return encode_varint(_signed_varint(value, 64, field_type))
    if field_type == "sint32":
        return encode_varint(_zigzag_encode(value, 32))
    if field_type == "sint64":
        return encode_varint(_zigzag_encode(value, 64))
    if field_type == "uint32":
        return encode_varint(_unsigned_checked(value, 32, field_type))
    if field_type == "uint64":
        return encode_varint(_unsigned_checked(value, 64, field_type))
    raise CodecError(f"unsupported varint protobuf type {field_type!r}")


def _decode_fixed(payload: bytes, field_type: str) -> Any:
    if field_type == "float":
        return struct.unpack("<f", payload)[0]
    if field_type == "double":
        return struct.unpack("<d", payload)[0]
    if field_type == "fixed32":
        return struct.unpack("<I", payload)[0]
    if field_type == "sfixed32":
        return struct.unpack("<i", payload)[0]
    if field_type == "fixed64":
        return struct.unpack("<Q", payload)[0]
    if field_type == "sfixed64":
        return struct.unpack("<q", payload)[0]
    return {"hex": payload.hex()}


def _encode_fixed(value: Any, field_type: str) -> bytes:
    if field_type in {"float", "double"}:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise CodecError(f"{field_type} field requires a number")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise CodecError("non-finite float edits are not accepted by the typed writer")
        return struct.pack("<f" if field_type == "float" else "<d", numeric)
    if not isinstance(value, int) or isinstance(value, bool):
        raise CodecError(f"{field_type} field requires an integer")
    if field_type == "fixed32":
        return struct.pack("<I", _unsigned_checked(value, 32, field_type))
    if field_type == "sfixed32":
        if value < -(1 << 31) or value > (1 << 31) - 1:
            raise CodecError(f"value {value} outside sfixed32 range")
        return struct.pack("<i", value)
    if field_type == "fixed64":
        return struct.pack("<Q", _unsigned_checked(value, 64, field_type))
    if field_type == "sfixed64":
        if value < -(1 << 63) or value > (1 << 63) - 1:
            raise CodecError(f"value {value} outside sfixed64 range")
        return struct.pack("<q", value)
    raise CodecError(f"unsupported fixed protobuf type {field_type!r}")


def _decode_packed(payload: bytes, descriptor: FieldDescriptor) -> list[Any]:
    field_type = descriptor.type
    values: list[Any] = []
    if field_type in {
        "int32",
        "int64",
        "uint32",
        "uint64",
        "sint32",
        "sint64",
        "bool",
        "enum",
    }:
        offset = 0
        while offset < len(payload):
            varint, offset = read_varint(payload, offset, len(payload))
            values.append(_decode_varint_value(varint.value, field_type))
        return values

    width = 4 if field_type in {"float", "fixed32", "sfixed32"} else 8
    if len(payload) % width:
        raise CodecError(
            f"packed {field_type} payload length {len(payload)} is not divisible by {width}"
        )
    for offset in range(0, len(payload), width):
        values.append(_decode_fixed(payload[offset : offset + width], field_type))
    return values


def _encode_packed(values: Any, descriptor: FieldDescriptor) -> bytes:
    if not isinstance(values, (list, tuple)):
        raise CodecError(
            f"packed repeated field {descriptor.name} requires a JSON/list value"
        )
    field_type = descriptor.type
    out = bytearray()
    for value in values:
        if field_type in {
            "int32",
            "int64",
            "uint32",
            "uint64",
            "sint32",
            "sint64",
            "bool",
            "enum",
        }:
            out.extend(_encode_varint_value(value, field_type))
        else:
            out.extend(_encode_fixed(value, field_type))
    return bytes(out)


def decode_field_value(field: Field, descriptor: FieldDescriptor | None) -> Any:
    if descriptor is None:
        if field.wire_type == 0 and field.value_varint is not None:
            return {"unknownVarint": field.value_varint.value, "raw": field.raw.hex()}
        if field.wire_type == 2:
            return {"unknownBytes": (field.payload or b"").hex(), "raw": field.raw.hex()}
        return {"unknownRaw": field.raw.hex()}

    field_type = descriptor.type
    if (
        descriptor.repeated
        and field_type in PACKABLE_TYPES
        and field.wire_type == 2
        and field.payload is not None
    ):
        return _decode_packed(field.payload, descriptor)

    if field.wire_type == 0 and field.value_varint is not None:
        return _decode_varint_value(field.value_varint.value, field_type)

    if field.wire_type in {1, 5} and field.payload is not None:
        return _decode_fixed(field.payload, field_type)

    if field.wire_type == 2 and field.payload is not None:
        if field_type == "string":
            try:
                return field.payload.decode("utf-8")
            except UnicodeDecodeError:
                return {"invalidUtf8": field.payload.hex()}
        if field_type == "bytes":
            return {"hex": field.payload.hex()}
        return {"hex": field.payload.hex()}

    return {"raw": field.raw.hex()}


def _length_prefix(field: Field, payload_length: int) -> bytes:
    if (
        field.length_varint is not None
        and field.length_varint.value == payload_length
    ):
        return field.length_varint.raw
    return encode_varint(payload_length)


def _encode_new_known_field(
    descriptor: FieldDescriptor,
    value: Any,
    *,
    wire_type: int | None = None,
) -> bytes:
    if descriptor.type == "group":
        raise CodecError("structural add does not support protobuf group fields")

    selected_wire = (
        WIRE_BY_TYPE.get(descriptor.type)
        if wire_type is None
        else wire_type
    )
    if selected_wire is None or selected_wire not in descriptor.expected_wire_types:
        raise CodecError(
            f"{descriptor.name} cannot be encoded with wire type {selected_wire}"
        )

    key_raw = encode_varint((descriptor.number << 3) | selected_wire)

    if descriptor.type == "message":
        if selected_wire != 2:
            raise CodecError("message fields require wire type 2")
        if not isinstance(value, bytes):
            raise CodecError("message add requires raw child-message payload bytes")
        try:
            parse_message(value)
        except WireParseError as exc:
            raise CodecError(f"message payload is not valid protobuf wire data: {exc}") from exc
        return key_raw + encode_varint(len(value)) + value

    if (
        descriptor.repeated
        and descriptor.type in PACKABLE_TYPES
        and selected_wire == 2
    ):
        values = value if isinstance(value, (list, tuple)) else [value]
        payload = _encode_packed(values, descriptor)
        return key_raw + encode_varint(len(payload)) + payload

    if selected_wire == 0:
        return key_raw + _encode_varint_value(value, descriptor.type)

    if selected_wire in {1, 5}:
        return key_raw + _encode_fixed(value, descriptor.type)

    if selected_wire == 2:
        if descriptor.type == "string":
            if not isinstance(value, str):
                raise CodecError("string field requires a string")
            payload = value.encode("utf-8")
        elif descriptor.type == "bytes":
            if isinstance(value, bytes):
                payload = value
            elif isinstance(value, str):
                try:
                    payload = bytes.fromhex(value.removeprefix("0x"))
                except ValueError as exc:
                    raise CodecError(
                        "bytes field requires bytes or hexadecimal text"
                    ) from exc
            else:
                raise CodecError("bytes field requires bytes or hexadecimal text")
        else:
            raise CodecError(
                f"wire type 2 add is unsupported for descriptor type {descriptor.type!r}"
            )
        return key_raw + encode_varint(len(payload)) + payload

    raise CodecError(f"structural add does not support wire type {selected_wire}")


def _single_field_from_raw(raw: bytes) -> Field:
    parsed = parse_message(raw)
    if len(parsed.fields) != 1:
        raise CodecError("structural field encoding must contain exactly one field")
    return parsed.fields[0]


def _encode_known_field(
    field: Field,
    descriptor: FieldDescriptor,
    value: Any,
) -> bytes:
    if field.wire_type not in descriptor.expected_wire_types:
        raise CodecError(
            f"{descriptor.name} observed wire type {field.wire_type} is not compatible "
            f"with descriptor type {descriptor.type}"
        )

    if descriptor.type == "message":
        raise CodecError("direct message replacement is not supported; edit a child path")

    if (
        descriptor.repeated
        and descriptor.type in PACKABLE_TYPES
        and field.wire_type == 2
    ):
        payload = _encode_packed(value, descriptor)
        return field.key.raw + _length_prefix(field, len(payload)) + payload

    if field.wire_type == 0:
        encoded = _encode_varint_value(value, descriptor.type)
        return field.key.raw + encoded

    if field.wire_type in {1, 5}:
        payload = _encode_fixed(value, descriptor.type)
        return field.key.raw + payload

    if field.wire_type == 2:
        if descriptor.type == "string":
            if not isinstance(value, str):
                raise CodecError("string field requires a string")
            payload = value.encode("utf-8")
        elif descriptor.type == "bytes":
            if isinstance(value, bytes):
                payload = value
            elif isinstance(value, str):
                try:
                    payload = bytes.fromhex(value.removeprefix("0x"))
                except ValueError as exc:
                    raise CodecError("bytes field requires bytes or hexadecimal text") from exc
            else:
                raise CodecError("bytes field requires bytes or hexadecimal text")
        else:
            raise CodecError(
                f"wire type 2 edit is unsupported for descriptor type {descriptor.type!r}"
            )
        return field.key.raw + _length_prefix(field, len(payload)) + payload

    raise CodecError(f"editing wire type {field.wire_type} is not supported")


@dataclass
class LosslessField:
    owner: "LosslessMessage"
    wire: Field
    descriptor: FieldDescriptor | None
    _replacement_raw: bytes | None = None
    _child: "LosslessMessage | None" = None
    _child_loaded: bool = False

    @property
    def number(self) -> int:
        return self.wire.number

    @property
    def name(self) -> str:
        return self.descriptor.name if self.descriptor is not None else f"#{self.number}"

    def child(self) -> "LosslessMessage":
        if self._child_loaded:
            if self._child is None:
                raise CodecError(f"{self.name} is not a descriptor-backed message field")
            return self._child
        self._child_loaded = True
        if (
            self.descriptor is None
            or self.descriptor.type != "message"
            or self.wire.wire_type != 2
            or self.wire.payload is None
            or not self.descriptor.type_name
        ):
            self._child = None
            raise CodecError(f"{self.name} is not a descriptor-backed message field")
        target = self.owner.profile.message(self.descriptor.type_name)
        if target is None:
            self._child = None
            raise CodecError(
                f"descriptor target {self.descriptor.type_name!r} is unavailable"
            )
        try:
            parsed = parse_message(self.effective_wire().payload or b"")
        except WireParseError as exc:
            self._child = None
            raise CodecError(
                f"cannot parse child {self.descriptor.type_name}: {exc}"
            ) from exc
        self._child = LosslessMessage(
            profile=self.owner.profile,
            descriptor=target,
            wire_message=parsed,
        )
        return self._child

    def effective_wire(self) -> Field:
        if self._replacement_raw is None:
            return self.wire
        parsed = parse_message(self._replacement_raw)
        if len(parsed.fields) != 1:
            raise CodecError("internal replacement must encode exactly one field")
        return parsed.fields[0]

    def value(self) -> Any:
        if self.descriptor is not None and self.descriptor.type == "message":
            child = self.child()
            return {
                "message": child.descriptor.full_name,
                "fieldCount": len(child.fields),
            }
        return decode_field_value(self.effective_wire(), self.descriptor)

    def replace_value(self, value: Any) -> None:
        if self.descriptor is None:
            raise CodecError(
                f"field #{self.number} is Unknown in profile {self.owner.profile.spec.slug}; "
                "typed editing is refused"
            )
        if self.descriptor.type != "message":
            if self.value() == value:
                # An idempotent edit retains any pending replacement.
                return
            if decode_field_value(self.wire, self.descriptor) == value:
                # Editing back to the original semantic value must restore the
                # original, potentially non-canonical wire encoding.
                self._replacement_raw = None
                return
        self._replacement_raw = _encode_known_field(self.wire, self.descriptor, value)

    def serialize(self) -> bytes:
        current = self.effective_wire() if self._replacement_raw is not None else self.wire
        if self._child_loaded and self._child is not None:
            payload = self._child.serialize()
            original = current.payload or b""
            if payload != original:
                return current.key.raw + _length_prefix(current, len(payload)) + payload
        return self._replacement_raw if self._replacement_raw is not None else self.wire.raw


class LosslessMessage:
    def __init__(
        self,
        *,
        profile: SchemaProfile,
        descriptor: MessageDescriptor,
        wire_message: Message,
    ) -> None:
        self.profile = profile
        self.descriptor = descriptor
        self.wire_message = wire_message
        by_number = descriptor.fields_by_number
        self.fields = [
            LosslessField(
                owner=self,
                wire=field,
                descriptor=by_number.get(field.number),
            )
            for field in wire_message.fields
        ]

    @property
    def raw(self) -> bytes:
        return self.wire_message.raw

    def serialize(self) -> bytes:
        return b"".join(field.serialize() for field in self.fields)

    def resolve_message(self, path: str | None = None) -> "LosslessMessage":
        if path is None or path.strip() in {"", "$"}:
            return self
        current = self
        for segment in parse_field_path(path):
            current = current._select(segment).child()
        return current

    def _descriptor_for_token(self, token: str | int) -> FieldDescriptor:
        descriptor = self.profile.field(self.descriptor, token)
        if descriptor is None:
            raise CodecError(
                f"{self.descriptor.name} has no descriptor-known field {token!r} "
                f"in profile {self.profile.spec.slug}"
            )
        return descriptor

    def _matching_indices(self, number: int) -> list[int]:
        return [
            index
            for index, field in enumerate(self.fields)
            if field.number == number
        ]

    def _insert_structural_field(
        self,
        descriptor: FieldDescriptor,
        raw: bytes,
    ) -> tuple[LosslessField, int, int]:
        matching = self._matching_indices(descriptor.number)
        if matching:
            insert_index = matching[-1] + 1
            occurrence = len(matching)
        else:
            insert_index = len(self.fields)
            occurrence = 0
        wire = _single_field_from_raw(raw)
        if wire.number != descriptor.number:
            raise CodecError("internal structural field-number mismatch")
        inserted = LosslessField(
            owner=self,
            wire=wire,
            descriptor=descriptor,
        )
        self.fields.insert(insert_index, inserted)
        return inserted, insert_index, occurrence

    def _resolve_with_parent(
        self,
        path: str,
    ) -> tuple["LosslessMessage", LosslessField, PathSegment]:
        segments = parse_field_path(path)
        parent = self
        for segment in segments[:-1]:
            parent = parent._select(segment).child()
        selected = parent._select(segments[-1])
        return parent, selected, segments[-1]

    def add_field(
        self,
        *,
        parent_path: str | None,
        field_token: str | int,
        value: Any,
        wire_type: int | None = None,
    ) -> dict[str, Any]:
        parent = self.resolve_message(parent_path)
        descriptor = parent._descriptor_for_token(field_token)
        matching = parent._matching_indices(descriptor.number)
        if matching and not descriptor.repeated:
            raise CodecError(
                f"{descriptor.name} is {descriptor.label}; structural add refuses "
                "to create a duplicate singular field"
            )

        selected_wire = wire_type
        if selected_wire is None and matching:
            observed = parent.fields[matching[-1]].effective_wire().wire_type
            if observed in descriptor.expected_wire_types:
                selected_wire = observed

        raw = _encode_new_known_field(
            descriptor,
            value,
            wire_type=selected_wire,
        )
        inserted, insert_index, occurrence = parent._insert_structural_field(
            descriptor,
            raw,
        )
        prefix = "" if not parent_path or parent_path == "$" else f"{parent_path}."
        return {
            "operation": "add",
            "parent": parent_path or "$",
            "field": descriptor.name,
            "fieldNumber": descriptor.number,
            "occurrence": occurrence,
            "path": f"{prefix}{descriptor.name}[{occurrence}]",
            "insertIndex": insert_index,
            "insertionPolicy": "same-number-cluster-append-else-message-end",
            "raw": inserted.serialize().hex(),
        }

    def remove_field(self, path: str) -> dict[str, Any]:
        parent, selected, segment = self._resolve_with_parent(path)
        descriptor = selected.descriptor
        if descriptor is None:
            raise CodecError("structural remove of Unknown fields is refused")
        if descriptor.label == "required":
            raise CodecError(f"cannot remove required field {descriptor.name}")
        index = next(
            (
                index
                for index, field in enumerate(parent.fields)
                if field is selected
            ),
            None,
        )
        if index is None:
            raise CodecError("internal structural remove target disappeared")
        raw = selected.serialize()
        del parent.fields[index]
        return {
            "operation": "remove",
            "path": path,
            "field": descriptor.name,
            "fieldNumber": descriptor.number,
            "occurrence": segment.occurrence,
            "removedIndex": index,
            "raw": raw.hex(),
        }

    def clone_field(self, path: str) -> dict[str, Any]:
        parent, selected, segment = self._resolve_with_parent(path)
        descriptor = selected.descriptor
        if descriptor is None:
            raise CodecError("structural clone of Unknown fields is refused")
        if not descriptor.repeated:
            raise CodecError(
                f"structural clone is limited to repeated fields; "
                f"{descriptor.name} is {descriptor.label}"
            )
        raw = selected.serialize()
        inserted, insert_index, occurrence = parent._insert_structural_field(
            descriptor,
            raw,
        )
        prefix_parts = parse_field_path(path)[:-1]
        prefix = ".".join(
            f"{part.token}[{part.occurrence}]"
            for part in prefix_parts
        )
        output_path = (
            f"{prefix}.{descriptor.name}[{occurrence}]"
            if prefix
            else f"{descriptor.name}[{occurrence}]"
        )
        return {
            "operation": "clone",
            "sourcePath": path,
            "sourceOccurrence": segment.occurrence,
            "field": descriptor.name,
            "fieldNumber": descriptor.number,
            "newOccurrence": occurrence,
            "newPath": output_path,
            "insertIndex": insert_index,
            "insertionPolicy": "same-number-cluster-append-else-message-end",
            "rawExactClone": inserted.serialize() == raw,
        }

    def move_repeated(self, path: str, to_occurrence: int) -> dict[str, Any]:
        if to_occurrence < 0:
            raise CodecError("to_occurrence must be >= 0")
        parent, selected, segment = self._resolve_with_parent(path)
        descriptor = selected.descriptor
        if descriptor is None:
            raise CodecError("structural move of Unknown fields is refused")
        if not descriptor.repeated:
            raise CodecError(
                f"structural move is limited to repeated fields; "
                f"{descriptor.name} is {descriptor.label}"
            )
        slots = parent._matching_indices(descriptor.number)
        if to_occurrence >= len(slots):
            raise CodecError(
                f"to_occurrence {to_occurrence} outside repeated field range "
                f"0..{len(slots) - 1}"
            )
        sequence = [parent.fields[index] for index in slots]
        source_occurrence = next(
            (
                index
                for index, field in enumerate(sequence)
                if field is selected
            ),
            None,
        )
        if source_occurrence is None:
            raise CodecError("internal structural move target disappeared")
        if source_occurrence != to_occurrence:
            item = sequence.pop(source_occurrence)
            sequence.insert(to_occurrence, item)
            for slot, field in zip(slots, sequence):
                parent.fields[slot] = field
        return {
            "operation": "move",
            "path": path,
            "field": descriptor.name,
            "fieldNumber": descriptor.number,
            "fromOccurrence": source_occurrence,
            "toOccurrence": to_occurrence,
            "slotPolicy": "permute-same-number-slots-only",
            "changed": source_occurrence != to_occurrence,
        }

    def _select(self, segment: PathSegment) -> LosslessField:
        descriptor = self.profile.field(self.descriptor, segment.token)
        if descriptor is not None:
            number = descriptor.number
        elif segment.token.isdigit():
            number = int(segment.token)
        else:
            raise CodecError(
                f"{self.descriptor.name} has no field named {segment.token!r} "
                f"in profile {self.profile.spec.slug}"
            )
        matches = [field for field in self.fields if field.number == number]
        if segment.occurrence >= len(matches):
            raise CodecError(
                f"field {segment.token!r} occurrence {segment.occurrence} is absent; "
                f"found {len(matches)} occurrence(s)"
            )
        return matches[segment.occurrence]

    def resolve(self, path: str | tuple[PathSegment, ...]) -> LosslessField:
        segments = parse_field_path(path) if isinstance(path, str) else path
        current = self
        for index, segment in enumerate(segments):
            selected = current._select(segment)
            if index == len(segments) - 1:
                return selected
            current = selected.child()
        raise AssertionError("non-empty path must resolve")

    def get_value(self, path: str) -> Any:
        field = self.resolve(path)
        if field.descriptor is not None and field.descriptor.type == "message":
            return field.child().to_view()
        return field.value()

    def set_value(self, path: str, value: Any) -> dict[str, Any]:
        field = self.resolve(path)
        before = field.value()
        field.replace_value(value)
        after_wire = parse_message(field.serialize()).fields[0]
        after = decode_field_value(after_wire, field.descriptor)
        return {"path": path, "before": before, "after": after}

    def to_view(self, *, max_depth: int = 8, _depth: int = 0) -> dict[str, Any]:
        occurrences: dict[int, int] = {}
        rows: list[dict[str, Any]] = []
        for field in self.fields:
            occurrence = occurrences.get(field.number, 0)
            occurrences[field.number] = occurrence + 1
            row: dict[str, Any] = {
                "number": field.number,
                "name": field.descriptor.name if field.descriptor else None,
                "occurrence": occurrence,
                "wireType": field.wire.wire_type,
                "known": field.descriptor is not None,
                "keyCanonical": field.wire.key.canonical,
            }
            if field.descriptor is not None:
                row.update(
                    {
                        "label": field.descriptor.label,
                        "type": field.descriptor.type,
                        "typeName": field.descriptor.type_name,
                    }
                )
            if (
                field.descriptor is not None
                and field.descriptor.type == "message"
                and _depth < max_depth
            ):
                try:
                    row["value"] = field.child().to_view(
                        max_depth=max_depth,
                        _depth=_depth + 1,
                    )
                except CodecError as exc:
                    row["value"] = {
                        "parseError": str(exc),
                        "rawPayload": (field.wire.payload or b"").hex(),
                    }
            elif field.descriptor is not None and field.descriptor.type == "message":
                row["value"] = {
                    "message": field.descriptor.type_name,
                    "depthLimit": True,
                    "rawLength": len(field.wire.payload or b""),
                }
            else:
                row["value"] = field.value()
            rows.append(row)
        return {
            "message": self.descriptor.full_name,
            "fieldCount": len(self.fields),
            "fields": rows,
        }

    def inspect(self) -> dict[str, Any]:
        field_counts: dict[int, int] = {}
        unknown_counts: dict[int, int] = {}
        noncanonical_keys = 0
        noncanonical_values = 0
        noncanonical_lengths = 0
        for field in self.fields:
            field_counts[field.number] = field_counts.get(field.number, 0) + 1
            if field.descriptor is None:
                unknown_counts[field.number] = unknown_counts.get(field.number, 0) + 1
            if not field.wire.key.canonical:
                noncanonical_keys += 1
            if field.wire.value_varint is not None and not field.wire.value_varint.canonical:
                noncanonical_values += 1
            if field.wire.length_varint is not None and not field.wire.length_varint.canonical:
                noncanonical_lengths += 1
        return {
            "profile": self.profile.spec.slug,
            "title": self.profile.spec.title,
            "version": self.profile.spec.version,
            "rootMessage": self.descriptor.full_name,
            "rootStatus": self.profile.root_status,
            "byteLength": len(self.raw),
            "fieldOccurrences": len(self.fields),
            "fieldCounts": {str(k): field_counts[k] for k in sorted(field_counts)},
            "unknownFieldCounts": {
                str(k): unknown_counts[k] for k in sorted(unknown_counts)
            },
            "fieldOrder": [field.number for field in self.fields],
            "noncanonical": {
                "keys": noncanonical_keys,
                "values": noncanonical_values,
                "lengths": noncanonical_lengths,
            },
            "roundTripExact": self.serialize() == self.raw,
        }

    def _flatten(
        self,
        *,
        prefix: str = "",
        max_depth: int = 64,
        _depth: int = 0,
    ) -> list[tuple[str, Any]]:
        occurrences: dict[int, int] = {}
        out: list[tuple[str, Any]] = []
        for field in self.fields:
            occurrence = occurrences.get(field.number, 0)
            occurrences[field.number] = occurrence + 1
            name = field.descriptor.name if field.descriptor else f"#{field.number}"
            segment = f"{name}[{occurrence}]"
            path = f"{prefix}.{segment}" if prefix else segment
            if (
                field.descriptor is not None
                and field.descriptor.type == "message"
                and _depth < max_depth
            ):
                try:
                    child = field.child()
                except CodecError as exc:
                    out.append(
                        (
                            path,
                            {
                                "messageParseError": str(exc),
                                "raw": field.wire.raw.hex(),
                            },
                        )
                    )
                else:
                    child_rows = child._flatten(
                        prefix=path,
                        max_depth=max_depth,
                        _depth=_depth + 1,
                    )
                    if child_rows:
                        out.extend(child_rows)
                    else:
                        out.append((path, {"emptyMessage": True}))
            else:
                out.append((path, field.value()))
        return out


def parse_btlx(data: bytes, profile: SchemaProfile | str) -> LosslessMessage:
    selected = load_profile(profile) if isinstance(profile, str) else profile
    try:
        message = parse_message(data)
    except WireParseError as exc:
        raise CodecError(f"BTLX wire parse failed: {exc}") from exc
    return LosslessMessage(
        profile=selected,
        descriptor=selected.root_message,
        wire_message=message,
    )


def parse_btlx_file(path: Path, profile: SchemaProfile | str) -> LosslessMessage:
    return parse_btlx(path.read_bytes(), profile)


def semantic_diff(
    left: LosslessMessage,
    right: LosslessMessage,
    *,
    max_changes: int | None = None,
) -> dict[str, Any]:
    if left.profile.spec.slug != right.profile.spec.slug:
        raise CodecError("semantic diff requires the same explicit profile")
    left_rows = left._flatten()
    right_rows = right._flatten()
    left_map = dict(left_rows)
    right_map = dict(right_rows)
    ordered_paths = list(dict.fromkeys(
        [path for path, _ in left_rows] + [path for path, _ in right_rows]
    ))
    all_changes: list[dict[str, Any]] = []
    for path in ordered_paths:
        left_present = path in left_map
        right_present = path in right_map
        if left_present and right_present and left_map[path] == right_map[path]:
            continue
        all_changes.append(
            {
                "path": path,
                "leftPresent": left_present,
                "rightPresent": right_present,
                "left": left_map.get(path),
                "right": right_map.get(path),
            }
        )
    changes = (
        all_changes
        if max_changes is None
        else all_changes[:max_changes]
    )
    return {
        "profile": left.profile.spec.slug,
        "byteEqual": left.serialize() == right.serialize(),
        "semanticEqual": not all_changes and len(left_rows) == len(right_rows),
        "fieldOrderEqual": [path for path, _ in left_rows]
        == [path for path, _ in right_rows],
        "leftLeafCount": len(left_rows),
        "rightLeafCount": len(right_rows),
        "changeCountTotal": len(all_changes),
        "changeCountReturned": len(changes),
        "truncated": len(changes) < len(all_changes),
        "changes": changes,
    }


def _coerce_scalar_text(descriptor: FieldDescriptor, text: str) -> Any:
    if descriptor.type == "string":
        return text
    if descriptor.type == "bytes":
        return text.removeprefix("hex:")
    if descriptor.type == "bool":
        lowered = text.strip().casefold()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        raise CodecError("bool value must be true/false")
    if descriptor.type in {"float", "double"}:
        try:
            return float(text)
        except ValueError as exc:
            raise CodecError(f"invalid floating-point value {text!r}") from exc
    if descriptor.type in {
        "int32",
        "int64",
        "uint32",
        "uint64",
        "sint32",
        "sint64",
        "fixed32",
        "fixed64",
        "sfixed32",
        "sfixed64",
        "enum",
    }:
        try:
            return int(text, 0)
        except ValueError as exc:
            raise CodecError(f"invalid integer value {text!r}") from exc
    if descriptor.type == "message":
        raise CodecError("message values require explicit raw child payload bytes")
    raise CodecError(f"typed CLI editing is unsupported for {descriptor.type!r}")


def coerce_descriptor_value(descriptor: FieldDescriptor, text: str) -> Any:
    if descriptor.repeated and descriptor.type in PACKABLE_TYPES:
        stripped = text.strip()
        if stripped.startswith("["):
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise CodecError("repeated scalar JSON value is invalid") from exc
            if not isinstance(value, list):
                raise CodecError("repeated scalar JSON value must be an array")
            return [
                _coerce_scalar_text(
                    descriptor,
                    json.dumps(item) if descriptor.type == "bool" else str(item),
                )
                for item in value
            ]
    return _coerce_scalar_text(descriptor, text)


def coerce_cli_value(field: LosslessField, text: str) -> Any:
    descriptor = field.descriptor
    if descriptor is None:
        raise CodecError("typed CLI editing of Unknown fields is refused")

    if (
        descriptor.repeated
        and descriptor.type in PACKABLE_TYPES
        and field.wire.wire_type == 2
    ):
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CodecError("packed repeated values must be JSON arrays") from exc
        if not isinstance(value, list):
            raise CodecError("packed repeated values must be JSON arrays")
        if descriptor.type == "bool":
            if not all(isinstance(item, bool) for item in value):
                raise CodecError("packed bool array requires JSON true/false values")
        return value

    return _coerce_scalar_text(descriptor, text)
