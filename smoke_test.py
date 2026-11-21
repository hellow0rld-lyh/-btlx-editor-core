"""Smoke test for a locally installed wheel, using only synthetic fixture bytes."""
import hashlib
import sys
from pathlib import Path

assert len(sys.argv) == 2
target = Path(sys.argv[1]).resolve(strict=True)
sys.path.insert(0, str(target))

import btlx_core as core

assert Path(core.__file__).resolve().is_relative_to(target)
assert core.list_profiles() == ()
spec = core.ProfileSpec("test-v1", "Synthetic", "v1", "", "")
descriptor = {"candidates": [{"messages": [
    {"name": "Root", "fullName": "Test.Root", "fields": [
        {"name": "Score", "number": 1, "type": "int32", "label": "optional"},
        {"name": "Child", "number": 2, "type": "message",
         "typeName": ".Test.Child", "label": "optional"},
    ]},
    {"name": "Child", "fullName": "Test.Child", "fields": [
        {"name": "Name", "number": 1, "type": "string", "label": "optional"},
    ]},
]}]}
profile = core.profile_from_reports(
    spec, descriptor, {"rootMessage": {"fullName": "Test.Root", "status": "Synthetic"}}
)
# Noncanonical field one, an unknown length field and a protobuf group.
original = bytes.fromhex("88 00 87 00 9a 03 02 08 01 1b 20 03 1c")
msg = core.parse_btlx(original, profile)
assert msg.serialize() == original
assert msg.get_value("Score") == 7
plan = {"schema": "EasyTechBTLXEditPlan/v1", "profile": "test-v1",
        "sourceSha256": hashlib.sha256(original).hexdigest(),
        "operations": [{"op": "set", "path": "Score", "value": 300}]}
new_bytes, receipt = core.apply_edit_plan(original, profile, plan)
assert receipt["postEditRoundTripExact"] and new_bytes.endswith(original[4:])
assert core.parse_btlx(new_bytes, profile).get_value("Score") == 300
assert core.parse_message(new_bytes).fields[1].raw == core.parse_message(original).fields[1].raw
bad = dict(plan, sourceSha256="0" * 64)
try:
    core.apply_edit_plan(original, profile, bad)
except core.CodecError:
    pass
else:
    raise AssertionError("source hash guard bypassed")
try:
    core.parse_btlx(original, profile).set_value("51", b"oops")
except core.CodecError:
    pass
else:
    raise AssertionError("Unknown-field typed-write guard bypassed")
try:
    core.apply_edit_plan(original, profile, dict(plan, operations=[{"op": "event-create"}]))
except core.CodecError:
    pass
else:
    raise AssertionError("unsupported game-specific operation accepted")
try:
    core.apply_edit_plan(original, profile, dict(plan, referencePolicy="report"))
except core.CodecError:
    pass
else:
    raise AssertionError("unsupported reference policy accepted")
print("Isolated wheel synthetic smoke: PASS")
