"""Lets the frontend tests talk to the real questionnaire without a running server.

    python tools/spec_contract.py spec              # prints the real GET /api/form-spec body
    python tools/spec_contract.py check < in.json   # in.json: a list of answer objects

`check` runs each answer object through the real POST /api/recommend validation and
prints, for each, {"errors": [...], "package": "..." or null}. Used by
frontend/src/contract.test.ts. Run from the Retrofit folder.
"""

import json
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ["DJANGO_DEBUG"] = "1"  # local settings: no secret key or database needed
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from recommendations.formspec import public_spec, validate  # noqa: E402
from recommendations.logic import recommend_package  # noqa: E402


def check(answers):
    clean, errors = validate(answers)
    return {"errors": errors, "package": None if errors else recommend_package(clean)}


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "spec":
        json.dump(public_spec(), sys.stdout, ensure_ascii=False)
    elif command == "check":
        json.dump([check(answers) for answers in json.load(sys.stdin)], sys.stdout, ensure_ascii=False)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
