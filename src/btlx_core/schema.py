# SPDX-License-Identifier: LGPL-3.0-or-later
#!/usr/bin/env python3
"""Profile-aware schema access for the EasyTech BTLX lossless codec.

The schema layer is deliberately version-qualified.  Field numbers are never
treated as globally meaningful across titles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

WIRE_BY_TYPE = {
    "double": 1,
    "float": 5,
    "int64": 0,
    "uint64": 0,
    "int32": 0,
    "fixed64": 1,
    "fixed32": 5,
    "bool": 0,
    "string": 2,
    "group": 3,
    "message": 2,
    "bytes": 2,
    "uint32": 0,
    "enum": 0,
    "sfixed32": 5,
    "sfixed64": 1,
    "sint32": 0,
    "sint64": 0,
}
PACKABLE_TYPES = {
    "double",
    "float",
    "int64",
    "uint64",
    "int32",
    "fixed64",
    "fixed32",
    "bool",
    "uint32",
    "enum",
    "sfixed32",
    "sfixed64",
    "sint32",
    "sint64",
}


@dataclass(frozen=True)
class ProfileSpec:
    slug: str
    title: str
    version: str
    descriptor_file: str
    profile_file: str


PROFILE_SPECS: dict[str, ProfileSpec] = {}


@dataclass(frozen=True)
class FieldDescriptor:
    name: str
    number: int
    label: str
    type: str
    type_name: str | None
    default_value: str | None

    @property
    def repeated(self) -> bool:
        return self.label == "repeated"

    @property
    def expected_wire_types(self) -> frozenset[int]:
        base = WIRE_BY_TYPE.get(self.type)
        if base is None:
            return frozenset()
        wires = {base}
        if self.repeated and self.type in PACKABLE_TYPES:
            wires.add(2)
        return frozenset(wires)


@dataclass(frozen=True)
class MessageDescriptor:
    name: str
    full_name: str
    fields: tuple[FieldDescriptor, ...]

    @property
    def fields_by_number(self) -> dict[int, FieldDescriptor]:
        return {field.number: field for field in self.fields}

    @property
    def fields_by_name(self) -> dict[str, FieldDescriptor]:
        return {field.name: field for field in self.fields}


@dataclass(frozen=True)
class SchemaProfile:
    spec: ProfileSpec
    root_message: MessageDescriptor
    root_status: str
    messages: dict[str, MessageDescriptor]
    source_identity: dict[str, Any]

    def message(self, full_name: str) -> MessageDescriptor | None:
        return self.messages.get(normalize_type_name(full_name))

    def field(
        self,
        message: MessageDescriptor,
        token: str | int,
    ) -> FieldDescriptor | None:
        if isinstance(token, int):
            return message.fields_by_number.get(token)
        text = str(token)
        if text.isdigit():
            return message.fields_by_number.get(int(text))
        exact = message.fields_by_name.get(text)
        if exact is not None:
            return exact
        lowered = text.casefold()
        matches = [field for field in message.fields if field.name.casefold() == lowered]
        if len(matches) == 1:
            return matches[0]
        return None


def normalize_type_name(value: str | None) -> str:
    if not value:
        return ""
    return value[1:] if value.startswith(".") else value


def _flatten_messages(messages: Iterable[dict[str, Any]]) -> dict[str, MessageDescriptor]:
    out: dict[str, MessageDescriptor] = {}

    def visit(raw: dict[str, Any]) -> None:
        full_name = normalize_type_name(raw.get("fullName") or raw.get("name"))
        fields = tuple(
            FieldDescriptor(
                name=str(field["name"]),
                number=int(field["number"]),
                label=str(field.get("label") or "optional"),
                type=str(field.get("type") or ""),
                type_name=(
                    normalize_type_name(field.get("typeName"))
                    if field.get("typeName")
                    else None
                ),
                default_value=field.get("defaultValue"),
            )
            for field in raw.get("fields", [])
        )
        out[full_name] = MessageDescriptor(
            name=str(raw.get("name") or full_name.rsplit(".", 1)[-1]),
            full_name=full_name,
            fields=fields,
        )
        for nested in raw.get("nestedTypes", []):
            visit(nested)

    for message in messages:
        visit(message)
    return out


def list_profiles() -> tuple[str, ...]:
    return tuple(PROFILE_SPECS)


def profile_from_reports(
    spec: ProfileSpec,
    descriptor_report: dict[str, Any],
    profile_report: dict[str, Any],
) -> SchemaProfile:
    """Build a version-qualified profile from caller-owned descriptor data.

    No EasyTech corpus directory or game-specific schema is required.  The
    caller is responsible for obtaining legitimately redistributable reports.
    """
    if not isinstance(spec, ProfileSpec) or not isinstance(descriptor_report, dict) or not isinstance(profile_report, dict):
        raise TypeError("profile requires a ProfileSpec and two report dictionaries")
    candidates = descriptor_report.get("candidates", [])
    if len(candidates) != 1:
        raise ValueError(
            f"{spec.descriptor_file}: expected exactly one descriptor candidate, "
            f"got {len(candidates)}"
        )
    messages = _flatten_messages(candidates[0].get("messages", []))

    root_info = profile_report.get("rootMessage") or {}
    root_name = normalize_type_name(root_info.get("fullName"))
    root = messages.get(root_name)
    if root is None:
        raise ValueError(
            f"{spec.profile_file}: root message {root_name!r} missing from descriptor"
        )

    return SchemaProfile(
        spec=spec,
        root_message=root,
        root_status=str(root_info.get("status") or "Unknown"),
        messages=messages,
        source_identity=dict(profile_report.get("sourceIdentity") or {}),
    )


def load_profile(slug: str) -> SchemaProfile:
    raise ValueError("no bundled game profiles; provide an explicit SchemaProfile")
