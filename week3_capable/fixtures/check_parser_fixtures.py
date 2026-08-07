"""Standalone parity check, no pytest dependency -- consistent with this
repo's existing convention (every step's examples/example.py is a runnable
smoke test, not a pytest suite; see plan §6b/§11 decision #4).

Run: python3 week3_capable/fixtures/check_parser_fixtures.py
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from boukensha.world import parser

FIXTURES_PATH = Path(__file__).resolve().parent / "parser_cases.yaml"

_DATACLASS_FUNCTIONS = {"parse_room", "parse_pickup", "parse_combat_result"}


def _actual_for(case):
    fn = getattr(parser, case["function"])
    if case["function"] == "parse_pickup":
        return fn(case["raw_text"], item_arg=(case.get("args") or {}).get("item"))
    if case["function"] == "detect_seed_zone":
        name, description = case["name_desc"]
        return fn(name, description)
    return fn(case["raw_text"])


def _as_plain(value):
    if hasattr(value, "__dataclass_fields__"):
        return {f: getattr(value, f) for f in value.__dataclass_fields__}
    return value


def check_mob_line_case(case):
    # world.py owns this logic, not parser.py -- import lazily to avoid a
    # hard module-level dependency on world/__init__.py's private names.
    from boukensha import world as world_mod

    failures = []
    for sub in case["cases"]:
        m = world_mod._MOB_LINE_NAME_RE.match(sub["line"])
        is_real = bool(m) and m.group(1).strip().split()[0].lower() not in world_mod._MOB_LINE_STOPWORDS
        if is_real != sub["is_real_mob"]:
            failures.append(f"    line={sub['line']!r} expected is_real_mob={sub['is_real_mob']} got {is_real}")
    return failures


def check_classify_consumable_case(case):
    failures = []
    for sub in case["cases"]:
        actual = parser.classify_consumable(sub["name"])
        if actual != sub["expected"]:
            failures.append(f"    name={sub['name']!r} expected {sub['expected']!r} got {actual!r}")
    return failures


def main():
    cases = yaml.safe_load(FIXTURES_PATH.read_text())
    failures = 0
    for case in cases:
        if case["function"] == "mob_line_is_real_mob":
            errs = check_mob_line_case(case)
            if errs:
                failures += 1
                print(f"FAIL {case['name']}:")
                print("\n".join(errs))
            else:
                print(f"ok   {case['name']}")
            continue

        if case["function"] == "classify_consumable_cases":
            errs = check_classify_consumable_case(case)
            if errs:
                failures += 1
                print(f"FAIL {case['name']}:")
                print("\n".join(errs))
            else:
                print(f"ok   {case['name']}")
            continue

        actual = _as_plain(_actual_for(case))
        expected = case["expected"]
        if case["function"] in _DATACLASS_FUNCTIONS:
            expected = dict(expected)
            # dataclasses may carry extra fields the fixture doesn't assert
            # on (e.g. ParsedPickup.item_type when unset) -- only compare
            # keys the fixture actually specifies.
            actual = {k: actual.get(k) for k in expected}
        if actual != expected:
            failures += 1
            print(f"FAIL {case['name']}: expected {expected!r}, got {actual!r}")
        else:
            print(f"ok   {case['name']}")

    print()
    if failures:
        print(f"{failures} case(s) failed")
        sys.exit(1)
    print(f"All {len(cases)} case(s) passed")


if __name__ == "__main__":
    main()
