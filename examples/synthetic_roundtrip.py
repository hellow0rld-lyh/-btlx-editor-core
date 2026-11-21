"""Only synthetic wire records and a hand-authored descriptor; no game assets."""
import hashlib
from btlx_core import ProfileSpec, profile_from_reports, parse_btlx, apply_edit_plan

spec = ProfileSpec("demo-v1", "Synthetic", "v1", "", "")
descriptor = {"candidates": [{"messages": [
    {"name": "Root", "fullName": "Demo.Root", "fields": [
        {"name": "Score", "number": 1, "type": "int32", "label": "optional"},
    ]},
]}]}
profile = profile_from_reports(
    spec, descriptor, {"rootMessage": {"fullName": "Demo.Root", "status": "Synthetic"}}
)
source = bytes.fromhex("08 07 9a 03 02 08 01")
assert parse_btlx(source, profile).serialize() == source
plan = {"schema": "EasyTechBTLXEditPlan/v1", "profile": "demo-v1",
        "sourceSha256": hashlib.sha256(source).hexdigest(),
        "operations": [{"op": "set", "path": "Score", "value": 9}]}
edited, receipt = apply_edit_plan(source, profile, plan)
assert edited == bytes.fromhex("08 09 9a 03 02 08 01")
assert receipt["postEditRoundTripExact"]
print("Synthetic byte-preserving BTLX core edit: PASS")
