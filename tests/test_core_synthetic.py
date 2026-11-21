# SPDX-License-Identifier: LGPL-3.0-or-later
"""Synthetic, dependency-free contract checks for the public neutral core."""

from __future__ import annotations

import hashlib
import unittest

from btlx_core import (
    CodecError,
    ProfileSpec,
    WireParseError,
    apply_edit_plan,
    encode_varint,
    list_profiles,
    parse_btlx,
    parse_message,
    profile_from_reports,
)


class SyntheticCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = ProfileSpec("synthetic-v1", "Synthetic", "v1", "", "")
        report = {
            "candidates": [
                {
                    "messages": [
                        {
                            "name": "Root",
                            "fullName": "Example.Root",
                            "fields": [
                                {
                                    "name": "Score", "number": 1,
                                    "type": "int32", "label": "optional",
                                }
                            ],
                        }
                    ]
                }
            ]
        }
        cls.profile = profile_from_reports(
            spec, report,
            {"rootMessage": {"fullName": "Example.Root", "status": "Synthetic"}},
        )
        cls.original = bytes.fromhex("88 00 87 00 9a 03 02 08 01 1b 20 03 1c")

    def make_plan(self, **overrides):
        plan = {
            "schema": "EasyTechBTLXEditPlan/v1",
            "profile": "synthetic-v1",
            "sourceSha256": hashlib.sha256(self.original).hexdigest(),
            "operations": [{"op": "set", "path": "Score", "value": 300}],
        }
        plan.update(overrides)
        return plan

    def test_no_private_game_profiles_bundled(self):
        self.assertEqual(list_profiles(), ())

    def test_unknown_fields_and_noncanonical_encoding_survive_read(self):
        parsed = parse_btlx(self.original, self.profile)
        self.assertEqual(parsed.get_value("Score"), 7)
        self.assertEqual(parsed.serialize(), self.original)

    def test_edit_is_surgical_and_preserves_unknown_fields(self):
        updated, receipt = apply_edit_plan(
            self.original, self.profile, self.make_plan(),
        )
        self.assertTrue(receipt["postEditRoundTripExact"])
        self.assertEqual(parse_btlx(updated, self.profile).get_value("Score"), 300)
        original_fields = parse_message(self.original).fields
        updated_fields = parse_message(updated).fields
        self.assertEqual(
            tuple(f.raw for f in original_fields[1:]),
            tuple(f.raw for f in updated_fields[1:]),
        )

    def test_stale_sha256_precondition_rejected(self):
        with self.assertRaises(CodecError):
            apply_edit_plan(
                self.original, self.profile,
                self.make_plan(sourceSha256="0" * 64),
            )

    def test_unsupported_game_specific_operation_rejected(self):
        with self.assertRaises(CodecError):
            apply_edit_plan(
                self.original, self.profile,
                self.make_plan(operations=[{"op": "event-create"}]),
            )

    def test_no_game_reference_rewrite_policy(self):
        with self.assertRaises(CodecError):
            apply_edit_plan(
                self.original, self.profile,
                self.make_plan(referencePolicy="report"),
            )

    def test_invalid_protobuf_key_rejected(self):
        with self.assertRaises(WireParseError):
            parse_message(b"\x00")

    def test_truncated_varint_rejected(self):
        with self.assertRaises(WireParseError):
            parse_message(b"\x08\x80")

    def test_varint_round_trip(self):
        self.assertEqual(encode_varint(300), b"\xac\x02")

    def test_negative_unsigned_varint_rejected(self):
        with self.assertRaises(ValueError):
            encode_varint(-1)


if __name__ == "__main__":
    unittest.main()
