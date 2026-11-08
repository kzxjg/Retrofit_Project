import json
import math
import re

from django.test import SimpleTestCase, override_settings
from hypothesis import HealthCheck, given, settings, strategies as st

from .formspec import CRITERIA_IDS, FIELD_BY_ID, FIELDS, MAX_ERRORS, SAFE_KEY_RE, _visible, validate
from .tests import valid_answers

settings.register_profile(
    "retrofit", max_examples=300, deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("retrofit")

KNOWN_IDS = list(FIELD_BY_ID)
DERIVED_IDS = {"year_of_construction", "zone_id"}  # added by validate(), never sent
POSTAL_STORED = re.compile(r"[A-Z][0-9][A-Z] [0-9][A-Z][0-9]")

# Integers too big to turn into a float (over about 309 digits). JSON allows
# them and Python reads them, but st.integers() alone almost never makes one.
huge_ints = st.integers(min_value=2**1024, max_value=10**400) | st.integers(min_value=-(10**400), max_value=-(2**1024))

# Any value JSON can carry: null, true/false, integers of any size, floats
# (including huge and tiny ones), text with any characters, and lists and
# objects nested inside each other.
scalars = (
    st.none() | st.booleans() | st.integers() | huge_ints
    | st.floats(allow_nan=False, allow_infinity=False) | st.text()
)
json_values = st.recursive(
    scalars,
    lambda inner: st.lists(inner, max_size=5) | st.dictionaries(st.text(max_size=10), inner, max_size=5),
    max_leaves=15,
)

# Values that look a little like real answers, so more of them get past the
# first checks and reach the deeper rules: real option text, numbers near the
# limits, and weight objects with random parts.
option_text = st.sampled_from(sorted({o for f in FIELDS for o in f.get("options", [])}))
weights = st.fixed_dictionaries({c: st.integers(-5, 105) | json_values for c in CRITERIA_IDS}) | st.dictionaries(
    st.sampled_from(CRITERIA_IDS) | st.text(max_size=8), st.integers(-5, 105) | json_values, max_size=8,
)
plausible = (
    option_text | st.integers(-10, 10**6) | huge_ints
    | st.floats(-1e6, 1e6, allow_nan=False) | weights | json_values
)

# 1. Pure nonsense: real or made-up question names with any values at all.
random_answers = st.dictionaries(st.sampled_from(KNOWN_IDS) | st.text(max_size=20), json_values, max_size=15)

# 2. A valid submission with a few answers swapped for random ones.
almost_valid_answers = st.dictionaries(
    st.sampled_from(KNOWN_IDS), plausible, max_size=6,
).map(lambda changes: {**valid_answers(), **changes})

# 3. Combinations that random values almost never hit on their own: a postal code of the right
# shape but with non-Latin digits, a zone of the wrong type, and advanced mode with odd weights.
postal_letter = st.sampled_from("ABCEGHJKLMNPRSTVWXYZ")
any_digit = st.characters(categories=["Nd"])  # 0-9, and also non-Latin digits
odd_postal_answers = st.tuples(postal_letter, any_digit, postal_letter, any_digit, postal_letter, any_digit).map(
    lambda p: {"postal_code": "{}{}{} {}{}{}".format(*p)}
)
wrong_zone_answers = st.fixed_dictionaries({"zone": json_values.filter(lambda z: not isinstance(z, str))})
advanced_answers = st.fixed_dictionaries({
    "preference_mode": st.just(FIELD_BY_ID["weights"]["show_if"]["equals"]),
    "weights": weights,
})
targeted_answers = (odd_postal_answers | wrong_zone_answers | advanced_answers).map(
    lambda changes: {**valid_answers(), **changes}
)

any_answers = random_answers | almost_valid_answers | targeted_answers


def assert_clean_value_is_safe(test, fid, value):
    """Rule 2: whatever validate() accepts has the shape the rest of the app expects."""
    if fid in DERIVED_IDS:
        test.assertIsInstance(value, str)
        return
    field = FIELD_BY_ID[fid]
    kind = field["type"]
    if kind == "text":
        test.assertEqual(field.get("format"), "postal_code", fid)
        test.assertRegex(value, POSTAL_STORED)
        test.assertTrue(value.isascii(), value)
    elif kind == "select":
        test.assertIn(value, field["options"], fid)
    elif kind in ("number", "currency"):
        test.assertNotIsInstance(value, bool, fid)
        test.assertIsInstance(value, (int, float), fid)
        test.assertTrue(math.isfinite(value), (fid, value))
        if field.get("integer"):
            test.assertIs(type(value), int, fid)
        if field.get("min") is not None:
            test.assertGreaterEqual(value, field["min"], fid)
        if field.get("max") is not None:
            test.assertLessEqual(value, field["max"], fid)
    elif kind == "weights":
        test.assertEqual(list(value), CRITERIA_IDS)
        test.assertTrue(all(type(v) is int and field["min"] <= v <= field["max"] for v in value.values()), value)
        test.assertGreater(sum(value.values()), 0)
    else:
        test.fail(f"no rule for question type {kind!r}")


class ValidateFuzzTests(SimpleTestCase):
    @given(any_answers)
    def test_validate_never_crashes(self, answers):
        clean, errors = validate(answers)
        self.assertIsInstance(clean, dict)
        self.assertIsInstance(errors, list)
        self.assertLessEqual(len(errors), MAX_ERRORS)
        for error in errors:
            self.assertEqual(set(error), {"field", "message"})
            self.assertIsInstance(error["message"], str)
            # an error names a real question, the whole request, or a safe-looking key
            self.assertTrue(
                error["field"] in KNOWN_IDS or error["field"] == "answers"
                or SAFE_KEY_RE.fullmatch(error["field"]),
                error["field"],
            )

    @given(st.one_of(json_values, st.lists(json_values)))
    def test_validate_handles_answers_that_are_not_an_object(self, answers):
        clean, errors = validate(answers)
        if not isinstance(answers, dict):
            self.assertEqual(clean, {})
            self.assertTrue(errors)

    @given(any_answers)
    def test_accepted_answers_are_always_safe(self, answers):
        clean, errors = validate(answers)
        self.assertTrue(set(clean) <= set(KNOWN_IDS) | DERIVED_IDS, set(clean) - set(KNOWN_IDS))
        for fid, value in clean.items():
            assert_clean_value_is_safe(self, fid, value)
        if not errors:
            # a submission with no errors has every required question that is shown
            for field in FIELDS:
                if field["required"] and _visible(field, answers):
                    self.assertIn(field["id"], clean)

    @given(any_answers)
    def test_hidden_questions_never_get_through(self, answers):
        clean, _ = validate(answers)
        for field in FIELDS:
            if not _visible(field, answers):
                self.assertNotIn(field["id"], clean)

    @given(st.dictionaries(st.sampled_from(KNOWN_IDS) | st.text(min_size=1, max_size=8), st.integers(), min_size=90, max_size=120))
    def test_large_submissions_are_judged_or_refused_whole(self, answers):
        from .formspec import MAX_ANSWERS
        clean, errors = validate(answers)
        if len(answers) > MAX_ANSWERS:
            self.assertEqual(clean, {})
            self.assertEqual(errors, [{"field": "answers", "message": "Too many fields in the request."}])


@override_settings(RATELIMIT_ENABLE=False)
class EndpointFuzzTests(SimpleTestCase):
    """Rule 4: whatever arrives, /api/recommend answers with one of its planned codes."""

    PLANNED = {200, 413, 415, 422, 429}

    @given(any_answers)
    def test_recommend_never_errors_on_any_answers(self, answers):
        response = self.client.post(
            "/api/recommend", data=json.dumps({"answers": answers}), content_type="application/json"
        )
        self.assertIn(response.status_code, self.PLANNED)
        self.assertIn("application/json", response["Content-Type"])
        if response.status_code == 200:
            self.assertEqual(len(response.json()["packages"]), 4)

    @given(st.binary(max_size=2000))
    def test_recommend_never_errors_on_any_bytes(self, body):
        response = self.client.post("/api/recommend", data=body, content_type="application/json")
        self.assertIn(response.status_code, self.PLANNED)

    @given(json_values)
    def test_recommend_never_errors_on_any_json(self, payload):
        response = self.client.post(
            "/api/recommend", data=json.dumps(payload), content_type="application/json"
        )
        self.assertIn(response.status_code, self.PLANNED)

    @given(st.dictionaries(st.text(min_size=1, max_size=10), st.text(max_size=50), max_size=4))
    def test_form_spec_ignores_any_query_string(self, query):
        response = self.client.get("/api/form-spec", query)
        self.assertEqual(response.status_code, 200)
        self.assertIn("sections", response.json())
