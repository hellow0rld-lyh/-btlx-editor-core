# SPDX-License-Identifier: LGPL-3.0-or-later
#!/usr/bin/env python3
"""Offline, fail-closed, multi-operation BTLX authoring transactions.

This is descriptor-qualified authoring, NOT evidence of game runtime semantics.
An edit plan is executed on a fresh in-memory parse; callers only receive bytes
after every step and the post-write serialization invariant succeed.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .codec import CodecError, LosslessMessage, parse_btlx
from .schema import FieldDescriptor, MessageDescriptor, SchemaProfile
from .wire import parse_message

PLAN_SCHEMA = "EasyTechBTLXEditPlan/v1"
MAX_OPERATIONS = 1000
MAX_MESSAGE_DEPTH = 16
MAX_MESSAGE_FIELDS = 10000


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CodecError(f"{label} must be a JSON object")
    return value


def _keys(obj: dict[str, Any], *, allowed: set[str], required: set[str], label: str) -> None:
    extra = set(obj) - allowed
    missing = required - set(obj)
    if extra or missing:
        raise CodecError(f"{label}: unexpected keys {sorted(extra)}; missing keys {sorted(missing)}")


def _text(obj: dict[str, Any], key: str, label: str) -> str:
    result = obj.get(key)
    if not isinstance(result, str) or not result.strip():
        raise CodecError(f"{label}.{key} must be a non-empty string")
    return result


def _wire_type(value: Any) -> int | None:
    if value is not None and (type(value) is not int or value not in (0, 1, 2, 5)):
        raise CodecError("wireType must be one of 0, 1, 2, 5")
    return value


def _child_fields(
    profile: SchemaProfile,
    descriptor: MessageDescriptor,
    rows: Any,
    *,
    depth: int = 0,
) -> bytes:
    if depth > MAX_MESSAGE_DEPTH:
        raise CodecError(f"message nesting exceeds {MAX_MESSAGE_DEPTH}")
    if not isinstance(rows, list) or len(rows) > MAX_MESSAGE_FIELDS:
        raise CodecError("fields must be an array within the message field limit")
    empty = parse_message(b"")
    child = LosslessMessage(profile=profile, descriptor=descriptor, wire_message=empty)
    for index, raw_row in enumerate(rows):
        row = _object(raw_row, f"fields[{index}]")
        _keys(
            row, allowed={"field", "value", "fields", "wireType"},
            required={"field"}, label=f"fields[{index}]",
        )
        token = row["field"]
        if not isinstance(token, (str, int)) or isinstance(token, bool):
            raise CodecError(f"fields[{index}].field must be a name or field number")
        field = profile.field(descriptor, token)
        if field is None:
            raise CodecError(f"{descriptor.name}: descriptor-unknown field {token!r} is refused")
        if field.type == "message":
            if "value" in row or "fields" not in row:
                raise CodecError(f"{field.name}: message requires fields, not value")
            nested = profile.message(field.type_name or "")
            if nested is None:
                raise CodecError(f"{field.name}: child message descriptor is unavailable")
            value = _child_fields(profile, nested, row["fields"], depth=depth + 1)
        else:
            if "fields" in row or "value" not in row:
                raise CodecError(f"{field.name}: scalar requires value, not fields")
            value = row["value"]
        child.add_field(
            parent_path="$", field_token=field.number, value=value,
            wire_type=_wire_type(row.get("wireType")),
        )
    missing_required = [
        field.name for field in descriptor.fields
        if field.label == "required" and not child._matching_indices(field.number)
    ]
    if missing_required:
        raise CodecError(f"{descriptor.name}: required fields missing: {missing_required}")
    return child.serialize()


def _contains_unknown(message: LosslessMessage, *, depth: int = 0) -> bool:
    if depth > MAX_MESSAGE_DEPTH:
        raise CodecError("cannot safely replace message deeper than inspected depth")
    for field in message.fields:
        if field.descriptor is None:
            return True
        if field.descriptor.type == "message" and _contains_unknown(field.child(), depth=depth + 1):
            return True
    return False


def _new_message_value(
    message: LosslessMessage, descriptor: FieldDescriptor, rows: Any
) -> bytes:
    target = message.profile.message(descriptor.type_name or "")
    if target is None:
        raise CodecError(f"{descriptor.name}: child message descriptor is unavailable")
    return _child_fields(message.profile, target, rows)


def _apply(message: LosslessMessage, op: dict[str, Any], *, terrain_catalog=None) -> dict[str, Any]:
    kind = _text(op, "op", "operation")
    if kind == "assert":
        _keys(op, allowed={"op", "path", "equals"}, required={"op", "path", "equals"}, label=kind)
        path = _text(op, "path", kind)
        selected = message.resolve(path)
        if selected.descriptor is None or selected.descriptor.type == "message":
            raise CodecError("assert only supports descriptor-known scalar fields")
        actual = selected.value()
        if actual != op["equals"]:
            raise CodecError(f"assert {path} failed: expected {op['equals']!r}, got {actual!r}")
        return {"operation": "assert", "path": path, "matched": True}

    if kind == "set":
        _keys(op, allowed={"op", "path", "value"}, required={"op", "path", "value"}, label=kind)
        return {"operation": "set", **message.set_value(_text(op, "path", kind), op["value"])}

    if kind == "add":
        _keys(op, allowed={"op", "parent", "field", "value", "fields", "wireType"},
              required={"op", "field"}, label=kind)
        parent_path = op.get("parent", "$")
        if not isinstance(parent_path, str):
            raise CodecError("add.parent must be a message path")
        parent = message.resolve_message(parent_path)
        token = op["field"]
        if not isinstance(token, (str, int)) or isinstance(token, bool):
            raise CodecError("add.field must be a name or field number")
        descriptor = parent.profile.field(parent.descriptor, token)
        if descriptor is None:
            raise CodecError(f"add: descriptor-unknown field {token!r} is refused")
        if descriptor.type == "message":
            if "value" in op or "fields" not in op:
                raise CodecError("add: message field requires fields")
            value = _new_message_value(parent, descriptor, op["fields"])
        else:
            if "fields" in op or "value" not in op:
                raise CodecError("add: scalar field requires value")
            value = op["value"]
        return message.add_field(
            parent_path=parent_path, field_token=descriptor.number,
            value=value, wire_type=_wire_type(op.get("wireType")),
        )

    if kind in ("remove", "clone", "move"):
        allowed = {"op", "path", "toOccurrence"} if kind == "move" else {"op", "path"}
        _keys(op, allowed=allowed, required=allowed, label=kind)
        path = _text(op, "path", kind)
        if kind == "remove":
            return message.remove_field(path)
        if kind == "clone":
            return message.clone_field(path)
        target = op["toOccurrence"]
        if type(target) is not int or target < 0:
            raise CodecError("move.toOccurrence must be a non-negative integer")
        return message.move_repeated(path, target)

    if kind == "replace-message":
        _keys(op, allowed={"op", "path", "fields"}, required={"op", "path", "fields"}, label=kind)
        path = _text(op, "path", kind)
        field = message.resolve(path)
        if field.descriptor is None or field.descriptor.type != "message":
            raise CodecError("replace-message requires a descriptor-known message field")
        if _contains_unknown(field.child()):
            raise CodecError("replace-message would discard Unknown fields; edit child paths instead")
        payload = _new_message_value(message, field.descriptor, op["fields"])
        original = field.serialize()
        wire = field.effective_wire()
        if wire.wire_type != 2:
            raise CodecError("replace-message requires wire type 2")
        from .codec import _length_prefix  # Preserve existing compatible prefix.
        field._replacement_raw = wire.key.raw + _length_prefix(wire, len(payload)) + payload
        field._child = None
        field._child_loaded = False
        return {"operation": "replace-message", "path": path,
                "beforeBytes": len(original), "afterBytes": len(field.serialize())}

    raise CodecError(f"unsupported edit operation {kind!r}")


def apply_edit_plan(
    source: bytes,
    profile: SchemaProfile | str,
    plan: Any,
    *,
    terrain_catalog=None,
    terrain_resource_identity=None,
) -> tuple[bytes, dict[str, Any]]:
    """Return (edited bytes, receipt); never mutates source or writes files."""
    root = _object(plan, "plan")
    _keys(root, allowed={"schema", "profile", "sourceSha256", "operations", "referencePolicy"},
          required={"schema", "profile", "operations"}, label="plan")
    if root["schema"] != PLAN_SCHEMA:
        raise CodecError(f"plan.schema must be {PLAN_SCHEMA}")
    profile_slug = profile.spec.slug if isinstance(profile, SchemaProfile) else profile
    if root["profile"] != profile_slug:
        raise CodecError(f"plan.profile {root['profile']!r} does not match selected {profile_slug!r}")
    before = hashlib.sha256(source).hexdigest()
    expected = root.get("sourceSha256")
    if expected is not None and expected != before:
        raise CodecError("sourceSha256 mismatch; refusing a plan for another source file")
    operations = root["operations"]
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise CodecError(f"operations must contain 1..{MAX_OPERATIONS} entries")
    message = parse_btlx(source, profile)
    changes: list[dict[str, Any]] = []
    for index, raw_op in enumerate(operations):
        try:
            changes.append(_apply(message, _object(raw_op, f"operations[{index}]"), terrain_catalog=terrain_catalog))
        except (CodecError, ValueError, TypeError, OverflowError) as exc:
            raise CodecError(f"operations[{index}] rejected; no output: {exc}") from exc
    result = message.serialize()
    reference_policy = root.get("referencePolicy", "none")
    if reference_policy not in ("none", "report", "reject-candidate-dangling"):
        raise CodecError("referencePolicy must be none, report or reject-candidate-dangling")
    reference_preflight = None
    if reference_policy != "none":
        raise CodecError("public core has no game-specific reference policies")
    reparsed = parse_btlx(result, profile)
    if reparsed.serialize() != result:
        raise CodecError("post-edit reparsing/serialization is not byte-exact")
    receipt = {
        "schema": "EasyTechBTLXEditReceipt/v1",
        "profile": profile_slug,
        "sourceSha256": before,
        "outputSha256": hashlib.sha256(result).hexdigest(),
        "sourceBytes": len(source),
        "outputBytes": len(result),
        "operationCount": len(changes),
        "changes": changes,
        "postEditRoundTripExact": True,
        "runtimeAcceptance": "NotRun",
    }
    if terrain_resource_identity is not None:
        receipt["terrainResourceIdentity"] = terrain_resource_identity
    if reference_preflight is not None:
        receipt["referencePolicy"] = reference_policy
        receipt["referencePreflight"] = reference_preflight
        receipt["referenceProof"] = "DescriptorNamedCandidateOnly"
    return result, receipt
