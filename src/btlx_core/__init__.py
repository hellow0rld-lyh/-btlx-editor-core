# SPDX-License-Identifier: LGPL-3.0-or-later
"""BTLX neutral editor core: descriptor-injected lossless library."""
from .wire import Field, Message, WireParseError, encode_varint, parse_message, serialize_preserving
from .schema import ProfileSpec, SchemaProfile, profile_from_reports, list_profiles
from .codec import CodecError, LosslessMessage, parse_btlx, semantic_diff
from .edit import apply_edit_plan, PLAN_SCHEMA

__version__ = "0.1.0a1"
__all__ = [
    "Field", "Message", "WireParseError", "encode_varint", "parse_message",
    "serialize_preserving", "ProfileSpec", "SchemaProfile", "profile_from_reports",
    "list_profiles", "CodecError", "LosslessMessage", "parse_btlx",
    "semantic_diff", "apply_edit_plan", "PLAN_SCHEMA",
]
