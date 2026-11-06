"""Behavior tests. They build their sample answers from the questionnaire in
formspec.py, so adding, removing or rewording a question needs no edits here."""




import json

from django.conf import settings
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings

from .formspec import FIELD_BY_ID, FIELDS, IMPERIAL, METRIC, POSTAL_LETTERS, PROVINCE_ZONES, STOREY_OPTIONS, ZONES, ZONE_OPTIONS, zones_for_postal_letter


# Production settings refuse to load without a PostgreSQL configuration. Loading
# the settings opens no connection, so these values need not point anywhere real.
PRODUCTION_DB = {"DJANGO_DB_NAME": "retrofit", "DJANGO_DB_USER": "app", "DJANGO_DB_HOST": "db.invalid",
                 "DJANGO_ALLOWED_HOSTS": "d1234abcd.cloudfront.net"}
# A key that passes the strength check (50+ characters, many distinct ones). Test use only.
STRONG_KEY = "test-only-9f2c7a1e4b8d0c3f6a5e2d1b7c9e0f4a8b3d6c2e1f5a7b9d"


def sample_value(field):
    kind = field["type"]
    if kind in ("select", "radio"):
        return field["options"][0]
    if kind in ("checklist", "multiselect"):
        return [field["options"][0]]
    if kind in ("number", "currency"):
        low = field.get("min", 1)
        return low if low >= 1 else 1
    if kind == "records":
        kind_of_work = field["type_options"][0] if field.get("type_options") else "Window replacement"
        return [{"type": kind_of_work, "year": field["year_range"][1]}]
    if kind == "incentives":
        return []
    return "N9A 1A1" if field.get("format") == "postal_code" else "text"


def valid_answers():
    answers = {field["id"]: sample_value(field) for field in FIELDS}
    answers["zone"] = ZONE_OPTIONS[1]  # Zone 5 occurs in Ontario, where the sample postal code N9A is
    return answers


def required_ids(answers):
    """Required questions that are visible for these answers."""
    ids = []
    for field in FIELDS:
        cond = field.get("show_if")
        visible = not cond or answers.get(cond["field"]) == cond["equals"]
        if field["required"] and visible:
            ids.append(field["id"])
    return ids


@override_settings(RATELIMIT_ENABLE=False)
class ApiTests(TestCase):
    def setUp(self):
        cache.clear()  # rate-limit counts live in the cache

    def post(self, answers):
        return self.client.post(
            "/api/recommend", data={"answers": answers}, content_type="application/json"
        )

    def error_fields(self, response):
        return [e["field"] for e in response.json()["errors"]]

    # ---- the server and the questionnaire ----
    def test_server_is_up(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)

    def test_api_sends_a_deny_all_content_security_policy(self):
        policy = self.client.get("/api/health")["Content-Security-Policy"]
        self.assertIn("default-src 'none'", policy)
        self.assertIn("frame-ancestors 'none'", policy)

    @override_settings(RATELIMIT_ENABLE=True)
    def test_recommend_is_rate_limited_per_ip(self):
        limit = int(settings.RECOMMEND_RATE_LIMIT.split("/")[0])
        answers = valid_answers()
        for _ in range(limit):
            self.assertEqual(self.post(answers).status_code, 200)
        response = self.post(answers)
        self.assertEqual(response.status_code, 429)
        self.assertIn("errors", response.json())

    def test_form_spec_describes_every_question(self):
        spec = self.client.get("/api/form-spec").json()
        ids = [f["id"] for section in spec["sections"] for f in section["fields"]]
        self.assertEqual(ids, [f["id"] for f in FIELDS])
        self.assertEqual(len(ids), len(set(ids)), "question ids must be unique")
        for section in spec["sections"]:
            for field in section["fields"]:
                self.assertTrue(field["label"])
                self.assertIn("required", field)
                if field["type"] in ("select", "radio", "checklist", "multiselect"):
                    self.assertGreaterEqual(len(field["options"]), 2, field["id"])

    def test_unit_systems_match_the_units_question(self):
        spec = self.client.get("/api/form-spec").json()
        units = next(f for f in FIELDS if f["id"] == spec["unit_field"])
        self.assertEqual(sorted(units["options"]), sorted(spec["unit_systems"]))

    def test_placed_questions_are_ones_the_page_knows_how_to_place(self):
        spec = self.client.get("/api/form-spec").json()
        fields = [f for section in spec["sections"] for f in section["fields"]]
        for field in fields:
            self.assertIn(field.get("placement"), (None, "top", "map"), field["id"])
            # a question shown outside the sections is always visible, never behind another answer
            if field.get("placement"):
                self.assertNotIn("show_if", field, field["id"])
        # the climate zone sits under the map
        self.assertEqual([f["id"] for f in fields if f.get("placement") == "map"], ["zone"])

    # ---- valid submissions ----
    def test_valid_answers_return_a_package(self):
        response = self.post(valid_answers())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["package"])

    def test_only_required_questions_are_enough(self):
        answers = {k: v for k, v in valid_answers().items() if k in required_ids(valid_answers())}
        self.assertEqual(self.post(answers).status_code, 200)

    # ---- required and unknown input ----
    def test_every_required_question_is_required(self):
        for field_id in required_ids(valid_answers()):
            with self.subTest(missing=field_id):
                answers = valid_answers()
                del answers[field_id]
                response = self.post(answers)
                self.assertEqual(response.status_code, 422)
                self.assertIn(field_id, self.error_fields(response))

    def test_unknown_options_are_rejected(self):
        for field in FIELDS:
            if field["type"] in ("select", "radio"):
                bad = "not a real option"
            elif field["type"] in ("checklist", "multiselect"):
                bad = ["not a real option"]
            else:
                continue
            with self.subTest(question=field["id"]):
                response = self.post({**valid_answers(), field["id"]: bad})
                self.assertEqual(response.status_code, 422)
                self.assertIn(field["id"], self.error_fields(response))

    def test_unknown_field_is_rejected(self):
        response = self.post({**valid_answers(), "not_a_question": "x"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("not_a_question", self.error_fields(response))

    def test_errors_do_not_reflect_odd_input(self):
        odd_key = "<img src=x onerror=alert(1)>"
        response = self.post({**valid_answers(), odd_key: "x", "wall_materials": ["<script>"]})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("<", response.content.decode())
        self.assertIn("answers", self.error_fields(response))

    def test_wrong_json_shapes_are_rejected(self):
        for body in ("{bad", "[1, 2]", '{"answers": []}', '{"answers": null}', b"\xff\xfe{}"):
            with self.subTest(body=body):
                response = self.client.post("/api/recommend", data=body, content_type="application/json")
                self.assertEqual(response.status_code, 422)

    def test_numbers_too_big_for_a_float_are_rejected_not_crashed_on(self):
        year = next(f for f in FIELDS if f["id"] == "renovation_history")["year_range"][1]
        for answers in (
            {"year_built": 10**400},
            {"energy_bill_winter": -(10**400)},
            {"renovation_history": [{"type": "Walls", "year": 10**400}]},
        ):
            with self.subTest(field=next(iter(answers))):
                response = self.post({**valid_answers(), **answers})
                self.assertEqual(response.status_code, 422)
                self.assertIn(next(iter(answers)), self.error_fields(response))
        self.assertEqual(self.post({**valid_answers(), "renovation_history": [{"type": "Walls", "year": year}]}).status_code, 200)

    def test_a_zone_of_the_wrong_type_is_rejected_not_crashed_on(self):
        for zone in (["x"], {"a": 1}, 4):
            with self.subTest(zone=zone):
                response = self.post({**valid_answers(), "zone": zone, "target_subsidies": "Yes", "subsidies": ["A"]})
                self.assertEqual(response.status_code, 422)
                self.assertIn("zone", self.error_fields(response))

    def test_postal_codes_must_use_latin_digits(self):
        for bad in ("N٩A ١A١", "N9A 1A１", "N9A1A1\n"):
            with self.subTest(postal_code=bad):
                response = self.post({**valid_answers(), "postal_code": bad})
                if bad.endswith("\n"):  # whitespace is tidied away, so this one is fine
                    self.assertEqual(response.status_code, 200)
                else:
                    self.assertIn("postal_code", self.error_fields(response))

    def test_other_text_is_stored_without_control_or_invisible_characters(self):
        from .formspec import validate
        answers = {**valid_answers(), "wall_materials": ["Other"]}
        clean, errors = validate({**answers, "wall_materials_other": " Cob\x00 wall‮​\t" + "x" * 500})
        self.assertEqual(errors, [])
        stored = clean["wall_materials_other"]
        self.assertTrue(stored.startswith("Cob wall"))
        self.assertLessEqual(len(stored), 200)
        self.assertFalse(any(ch in stored for ch in "\x00‮​\t"))
        clean, _ = validate({**answers, "wall_materials_other": "\x00​"})
        self.assertNotIn("wall_materials_other", clean)  # nothing visible left

    def test_hidden_answers_are_dropped_not_passed_on(self):
        from .formspec import validate
        clean, errors = validate({**valid_answers(), "solar_existing": "No", "solar_capacity_kw": 5})
        self.assertEqual(errors, [])
        self.assertNotIn("solar_capacity_kw", clean)

    def test_unknown_field_with_a_trailing_newline_is_not_echoed(self):
        response = self.post({**valid_answers(), "not_a_question\n": "x"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.error_fields(response), ["answers"])

    def test_empty_request_is_rejected(self):
        response = self.client.post("/api/recommend", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 422)

    # ---- numbers and units ----
    def test_typed_numbers_must_be_in_range_and_numeric(self):
        for bad in (-5, 99999999, "100", True):  # 0 is allowed: a bill can be nothing
            with self.subTest(energy_bill_winter=bad):
                response = self.post({**valid_answers(), "energy_bill_winter": bad})
                self.assertEqual(response.status_code, 422)
                self.assertIn("energy_bill_winter", self.error_fields(response))

    def test_whole_number_questions_reject_decimals(self):
        response = self.post({**valid_answers(), "year_built": 1985.5})
        self.assertIn("year_built", self.error_fields(response))

    def test_imperial_values_are_converted_before_the_range_check(self):
        # the sample temperature (10) is a metric value, so give a normal one in °F
        base = {**valid_answers(), "preferred_units": IMPERIAL, "indoor_temperature": 70}
        self.assertEqual(self.post(base).status_code, 200)
        # 70 is a normal room temperature in °F but far too hot in °C
        metric = {**valid_answers(), "preferred_units": METRIC, "indoor_temperature": 70}
        self.assertEqual(self.post(metric).status_code, 422)

    def test_thickness_is_millimetres_or_inches_by_the_chosen_units(self):
        from .formspec import validate
        imperial = {**valid_answers(), "preferred_units": IMPERIAL, "indoor_temperature": 70}  # a normal 70 °F
        clean, errors = validate({**imperial, "wall_thickness": 8})
        self.assertEqual(errors, [])
        self.assertEqual(clean["wall_thickness"], 203.2)  # stored in mm
        self.assertIn("wall_thickness", self.error_fields(self.post({**imperial, "wall_thickness": 0.5})))  # 12.7 mm: too thin
        self.assertIn("roof_thickness", self.error_fields(self.post({**imperial, "roof_thickness": 70})))   # 1778 mm: too thick
        metric = {**valid_answers(), "preferred_units": METRIC, "indoor_temperature": 20}
        self.assertEqual(self.post({**metric, "wall_thickness": 8}).status_code, 422)  # 8 mm: too thin
        self.assertEqual(self.post({**metric, "wall_thickness": 200}).status_code, 200)

    # ---- questions answered from a dropdown that stand for a number ----
    def test_floor_area_storeys_and_occupants_are_dropdowns(self):
        by_id = {f["id"]: f for f in FIELDS}
        for question in ("floor_area", "storeys", "storeys_above_ground", "occupants"):
            self.assertEqual(by_id[question]["type"], "select", question)

    def test_only_listed_options_are_accepted_for_them(self):
        for question, bad in (("floor_area", "120"), ("floor_area", 120), ("storeys", 2), ("storeys", "11"),
                              ("storeys", "1.5"), ("occupants", "9"), ("occupants", 3)):
            with self.subTest(question=question, value=bad):
                response = self.post({**valid_answers(), question: bad})
                self.assertEqual(response.status_code, 422)
                self.assertIn(question, self.error_fields(response))

    def test_a_chosen_option_becomes_the_number_the_rest_of_the_app_uses(self):
        from .formspec import FLOOR_AREA_OPTIONS, validate
        clean, errors = validate({**valid_answers(), "floor_area": FLOOR_AREA_OPTIONS[2], "storeys": "3",
                                  "storeys_above_ground": "2", "occupants": "3 or above"})
        self.assertEqual(errors, [])
        self.assertEqual(clean["floor_area"], 125)  # the "100–150 m²" band is stood for by 125 m²
        self.assertEqual((clean["storeys"], clean["storeys_above_ground"], clean["occupants"]), (3, 2, 3))

    def test_floor_area_options_are_shown_in_the_units_the_user_chose(self):
        spec = self.client.get("/api/form-spec").json()
        area = next(f for section in spec["sections"] for f in section["fields"] if f["id"] == "floor_area")
        imperial = area["labels_by_unit"][IMPERIAL]
        self.assertEqual(len(imperial), len(area["options"]))
        self.assertTrue(all("ft²" in label for label in imperial))
        self.assertTrue(all("m²" in label for label in area["options"]))
        self.assertEqual(sorted(area["numeric"]), sorted(area["options"]))

    def test_rules_that_link_two_questions_point_at_real_numeric_questions(self):
        spec = self.client.get("/api/form-spec").json()
        by_id = {f["id"]: f for section in spec["sections"] for f in section["fields"]}
        linked = [f for f in by_id.values() if "not_more_than" in f]
        self.assertTrue(linked)
        for field in linked:
            other = by_id[field["not_more_than"]["field"]]
            for question in (field, other):
                numeric = question["type"] in ("number", "currency") or (question["type"] == "select" and "numeric" in question)
                self.assertTrue(numeric, question["id"])
            self.assertTrue(field["not_more_than"]["message"])

    def test_storeys_above_ground_cannot_exceed_total_storeys(self):
        response = self.post({**valid_answers(), "storeys": "2", "storeys_above_ground": "3"})
        self.assertIn("storeys_above_ground", self.error_fields(response))
        self.assertIn("cannot be more than", response.json()["errors"][0]["message"])
        self.assertEqual(self.post({**valid_answers(), "storeys": "3", "storeys_above_ground": "3"}).status_code, 200)

    def test_every_building_element_can_be_chosen_for_a_renovation(self):
        from .formspec import RENOVATION_ELEMENTS
        self.assertEqual(RENOVATION_ELEMENTS, ["Walls", "Roof", "HVAC system", "Windows", "Doors"])
        for element in RENOVATION_ELEMENTS:
            with self.subTest(element=element):
                records = [{"type": element, "year": 2015}]
                self.assertEqual(self.post({**valid_answers(), "renovation_history": records}).status_code, 200)

    def test_wall_materials_can_be_unknown(self):
        spec = self.client.get("/api/form-spec").json()
        walls = next(f for section in spec["sections"] for f in section["fields"] if f["id"] == "wall_materials")
        self.assertIn("Unknown", walls["options"])
        self.assertEqual(self.post({**valid_answers(), "wall_materials": ["Unknown"]}).status_code, 200)

    # ---- year built ----
    def test_the_generation_is_worked_out_from_the_year_that_was_typed(self):
        from .formspec import YEAR_OPTIONS, validate
        expected = {
            1800: 0, 1940: 0, 1941: 1, 1996: 1, 1997: 2, 2010: 2,
            2011: 3, 2016: 3, 2017: 4, 2019: 4, 2020: 5,
        }
        for year, index in expected.items():
            with self.subTest(year=year):
                clean, errors = validate({**valid_answers(), "year_built": year})
                self.assertEqual(errors, [])
                self.assertEqual(clean["year_of_construction"], YEAR_OPTIONS[index])

    def test_the_year_built_must_be_a_realistic_whole_number(self):
        from datetime import date
        for bad in (1799, 0, -5, date.today().year + 1, 1985.5, "1985", True):
            with self.subTest(year=bad):
                response = self.post({**valid_answers(), "year_built": bad})
                self.assertEqual(response.status_code, 422)
                self.assertIn("year_built", self.error_fields(response))

    def test_the_old_generation_dropdown_is_no_longer_a_question(self):
        response = self.post({**valid_answers(), "year_of_construction": "Pre 1941"})
        self.assertIn("year_of_construction", self.error_fields(response))

    # ---- postal code and province ----
    def test_valid_postal_codes_are_accepted_in_any_format(self):
        for good in ["N9A 1A1", "n9a1a1", " N9A  1A1 "]:
            with self.subTest(postal_code=good):
                self.assertEqual(
                    self.post({**valid_answers(), "postal_code": good}).status_code, 200
                )

    def test_invalid_postal_codes_are_rejected(self):
        for bad in ["60601", "D1A 1A1", "N9U 1A1", "W1A 1A1", "Z1A 1A1"]:
            with self.subTest(postal_code=bad):
                response = self.post({**valid_answers(), "postal_code": bad})
                self.assertEqual(response.status_code, 422)
                self.assertIn("postal_code", self.error_fields(response))

    # ---- questions that appear only after another answer ----
    def test_hidden_questions_are_ignored(self):
        answers = {**valid_answers(), "solar_existing": "No", "solar_capacity_kw": -50}
        self.assertEqual(self.post(answers).status_code, 200)

    def test_visible_conditional_questions_are_checked(self):
        answers = {**valid_answers(), "solar_existing": "Yes", "solar_capacity_kw": -50}
        response = self.post(answers)
        self.assertEqual(response.status_code, 422)
        self.assertIn("solar_capacity_kw", self.error_fields(response))

    # ---- renovation records ----
    def test_renovation_records_are_checked(self):
        year = next(f for f in FIELDS if f["id"] == "renovation_history")["year_range"][1]
        good = [{"type": "Roof", "year": 2015}, {"type": "Windows", "year": year}]
        self.assertEqual(self.post({**valid_answers(), "renovation_history": good}).status_code, 200)
        for bad in (
            [{"type": "", "year": 2015}],
            [{"type": "New roof", "year": 2015}],   
            [{"type": "Chimney", "year": 2015}],
            [{"type": "Roof", "year": 1850}],
            [{"type": "Roof", "year": year + 5}],
            [{"type": "Roof"}],
            [{"type": "Roof", "year": 2015, "extra": 1}],
            [{"type": "Roof", "year": 2015}] * 21,
        ):
            with self.subTest(records=str(bad)[:40]):
                response = self.post({**valid_answers(), "renovation_history": bad})
                self.assertEqual(response.status_code, 422)
                self.assertIn("renovation_history", self.error_fields(response))

    # ---- government incentives ----
    def test_incentives_are_filtered_by_zone(self):
        from unittest.mock import patch
        from . import incentives

        sample = [
            {"id": "a", "name": "A", "zones": "all"},
            {"id": "b", "name": "B", "zones": ["zone4"]},
        ]
        with patch.object(incentives, "INCENTIVES", sample):
            self.assertEqual([p["id"] for p in incentives.incentives_for("zone4")], ["a", "b"])
            self.assertEqual([p["id"] for p in incentives.incentives_for("zone8")], ["a"])
            self.assertEqual([p["id"] for p in incentives.incentives_for(None)], ["a"])

    def test_incentives_endpoint_answers_for_a_zone(self):
        response = self.client.get("/api/incentives", {"zone": ZONE_OPTIONS[0]})
        self.assertEqual(response.status_code, 200)
        self.assertIn("programs", response.json())
        self.assertEqual(self.client.get("/api/incentives", {"zone": "Zone 99"}).json(), {"programs": []})

    def test_a_program_that_does_not_exist_is_rejected(self):
        answers = {**valid_answers(), "target_subsidies": "Yes", "subsidies": ["Some program that does not exist"]}
        self.assertEqual(self.post(answers).status_code, 422)
        answers["subsidies"] = []
        self.assertEqual(self.post(answers).status_code, 200)

    # ---- request hardening ----
    def test_recommend_requires_json_content_type(self):
        response = self.client.post("/api/recommend", data="{}", content_type="text/plain")
        self.assertEqual(response.status_code, 415)

    def test_oversized_requests_are_rejected(self):
        response = self.client.post(
            "/api/recommend", data="x" * (300 * 1024), content_type="application/json"
        )
        self.assertEqual(response.status_code, 413)

    def test_too_many_fields_are_rejected(self):
        answers = {f"field_{i}": "x" for i in range(150)}
        response = self.post(answers)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["errors"][0]["field"], "answers")

    def test_recommend_needs_no_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post("/api/recommend", data=json.dumps({"answers": {}}), content_type="application/json")
        self.assertEqual(response.status_code, 422)  # reached the view: refused for the answers, not CSRF

    def test_json_content_type_in_any_case_and_with_a_charset(self):
        body = json.dumps({"answers": valid_answers()})
        for content_type in ("Application/JSON", "application/json; charset=utf-8"):
            with self.subTest(content_type=content_type):
                response = self.client.post("/api/recommend", data=body, content_type=content_type)
                self.assertEqual(response.status_code, 200)

    def test_body_size_limit_is_exact(self):
        limit = settings.DATA_UPLOAD_MAX_MEMORY_SIZE
        empty_pad = json.dumps({"answers": valid_answers(), "pad": ""})
        at_limit = json.dumps({"answers": valid_answers(), "pad": "x" * (limit - len(empty_pad))})
        self.assertEqual(len(at_limit), limit)
        post = lambda body: self.client.post("/api/recommend", data=body, content_type="application/json")
        self.assertEqual(post(at_limit).status_code, 200)
        self.assertEqual(post(at_limit.replace('"pad": "', '"pad": "x', 1)).status_code, 413)

    def test_field_count_limit_is_exact(self):
        from .formspec import MAX_ANSWERS
        answers = valid_answers()
        at_limit = {**answers, **{f"extra_{i}": 1 for i in range(MAX_ANSWERS - len(answers))}}
        self.assertEqual(len(at_limit), MAX_ANSWERS)
        errors = self.post(at_limit).json()["errors"]
        self.assertTrue(all(e["message"] == "Unknown field." for e in errors))  # judged, not refused outright
        errors = self.post({**at_limit, "one_more": 1}).json()["errors"]
        self.assertEqual(errors, [{"field": "answers", "message": "Too many fields in the request."}])

    def test_error_list_is_capped(self):
        from .formspec import MAX_ERRORS
        response = self.post({f"unknown_{i}": 1 for i in range(MAX_ERRORS * 3)})
        self.assertEqual(len(response.json()["errors"]), MAX_ERRORS)

    @override_settings(RATELIMIT_ENABLE=True)
    def test_rate_limit_is_kept_per_ip_and_ignores_forwarded_for(self):
        limit = int(settings.RECOMMEND_RATE_LIMIT.split("/")[0])
        body = json.dumps({"answers": valid_answers()})

        def post_from(ip, **headers):
            return self.client.post(
                "/api/recommend", data=body, content_type="application/json", REMOTE_ADDR=ip, **headers
            ).status_code

        for _ in range(limit):
            self.assertEqual(post_from("10.0.0.1"), 200)
        self.assertEqual(post_from("10.0.0.1"), 429)
        # a different address has its own allowance
        self.assertEqual(post_from("10.0.0.2"), 200)
        # a client cannot claim to be someone else with X-Forwarded-For
        self.assertEqual(post_from("10.0.0.1", HTTP_X_FORWARDED_FOR="203.0.113.9"), 429)

    @override_settings(RATELIMIT_ENABLE=True, TRUSTED_PROXY_COUNT=1)
    def test_rate_limit_behind_one_proxy_uses_the_address_it_appended(self):
        limit = int(settings.RECOMMEND_RATE_LIMIT.split("/")[0])
        body = json.dumps({"answers": valid_answers()})
        alb = "10.0.0.1"  # every request arrives from the load balancer

        def post_from(forwarded):
            return self.client.post(
                "/api/recommend", data=body, content_type="application/json",
                REMOTE_ADDR=alb, HTTP_X_FORWARDED_FOR=forwarded,
            ).status_code

        for _ in range(limit):
            self.assertEqual(post_from("198.51.100.7"), 200)
        self.assertEqual(post_from("198.51.100.7"), 429)
        # another visitor behind the same load balancer has their own allowance
        self.assertEqual(post_from("198.51.100.8"), 200)
        # a client cannot escape by prepending a fake address; the proxy's entry is last
        self.assertEqual(post_from("203.0.113.9, 198.51.100.7"), 429)

    def test_client_ip_picks_the_entry_from_the_outermost_trusted_proxy(self):
        from django.test import RequestFactory
        from .views import client_ip

        def ip(xff, hops):
            request = RequestFactory().post("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR=xff)
            with self.settings(TRUSTED_PROXY_COUNT=hops):
                return client_ip(None, request)

        self.assertEqual(ip("1.1.1.1, 2.2.2.2", 0), "10.0.0.1")  # no proxy: header ignored
        self.assertEqual(ip("1.1.1.1, 2.2.2.2", 1), "2.2.2.2")
        self.assertEqual(ip("fake, 1.1.1.1, 2.2.2.2", 2), "1.1.1.1")  # CloudFront + ALB
        self.assertEqual(ip("", 1), "10.0.0.1")  # header missing: fall back
        self.assertEqual(ip("2.2.2.2", 2), "10.0.0.1")  # fewer entries than proxies: fall back

    # ---- exact limits ----
    def test_every_number_accepts_its_limits_and_rejects_just_past_them(self):
        for field in FIELDS:
            if field["type"] not in ("number", "currency"):
                continue
            step = 1 if field.get("integer") else 0.01
            base = valid_answers()
            if field.get("show_if"):
                base[field["show_if"]["field"]] = field["show_if"]["equals"]
            for value in (field.get("min"), field.get("max")):
                if value is None:
                    continue
                with self.subTest(field=field["id"], value=value):
                    self.assertEqual(self.post({**base, field["id"]: value}).status_code, 200)
            for value in ((field["min"] - step) if field.get("min") is not None else None,
                          (field["max"] + step) if field.get("max") is not None else None):
                if value is None:
                    continue
                with self.subTest(field=field["id"], value=value):
                    self.assertIn(field["id"], self.error_fields(self.post({**base, field["id"]: value})))

    def test_imperial_values_that_convert_exactly_onto_a_limit(self):
        imperial = {**valid_answers(), "preferred_units": IMPERIAL, "indoor_temperature": 70}
        for question, value, ok in (
            ("indoor_temperature", 50, True),      # exactly 10 °C, the minimum
            ("indoor_temperature", 86, True),      # exactly 30 °C, the maximum
            ("indoor_temperature", 49.9, False),
            ("indoor_temperature", 86.1, False),
            ("wall_thickness", 20 / 25.4, True),   # exactly 20 mm
            ("wall_thickness", 0.7874, False),     # 19.99996 mm: rounding down by the user goes under
        ):
            with self.subTest(question=question, value=value):
                response = self.post({**imperial, question: value})
                if ok:
                    self.assertEqual(response.status_code, 200)
                else:
                    self.assertIn(question, self.error_fields(response))

    def test_every_listed_option_is_accepted(self):
        # unit-dependent numbers are left out so switching units cannot put them out of range
        base = {k: v for k, v in valid_answers().items()
                if not FIELD_BY_ID[k].get("unit_kind")}
        base["storeys"] = STOREY_OPTIONS[-1]  # so any "storeys above ground" fits under it
        for field in FIELDS:
            if field["type"] not in ("select", "radio", "checklist", "multiselect"):
                continue
            if field["id"] == "zone":
                continue  # which zones fit depends on the postal code; see PostalCodeZoneTests
            answers = [[o] for o in field["options"]] if field["type"] in ("checklist", "multiselect") \
                else field["options"]
            if field["type"] in ("checklist", "multiselect"):
                answers.append(list(field["options"]))  # everything ticked at once
            for answer in answers:
                with self.subTest(field=field["id"], answer=answer):
                    self.assertEqual(self.post({**base, field["id"]: answer}).status_code, 200)

    def test_renovation_records_at_their_limits(self):
        field = FIELD_BY_ID["renovation_history"]
        lo, hi = field["year_range"]
        full = [{"type": "Roof", "year": lo}] * (field["max_records"] - 1) + [{"type": "Walls", "year": hi}]
        self.assertEqual(self.post({**valid_answers(), "renovation_history": full}).status_code, 200)
        for bad_year in (lo - 1, hi + 1):
            with self.subTest(year=bad_year):
                response = self.post({**valid_answers(), "renovation_history": [{"type": "Roof", "year": bad_year}]})
                self.assertIn("renovation_history", self.error_fields(response))

    # ---- how accepted answers are stored ----
    def test_whole_number_answers_are_stored_as_whole_numbers(self):
        from .formspec import validate
        for field in FIELDS:
            if not field.get("integer"):
                continue
            with self.subTest(field=field["id"]):
                clean, errors = validate({**valid_answers(), field["id"]: field["min"] + 1})
                self.assertEqual(errors, [])
                self.assertIs(type(clean[field["id"]]), int)

    def test_duplicate_ticks_are_stored_once(self):
        from .formspec import validate
        clean, errors = validate({**valid_answers(), "objectives": ["Reduce energy bills"] * 3})
        self.assertEqual(errors, [])
        self.assertEqual(clean["objectives"], ["Reduce energy bills"])

    def test_other_text_is_dropped_when_other_is_not_ticked(self):
        from .formspec import validate
        clean, errors = validate({**valid_answers(), "wall_materials": ["Brick"], "wall_materials_other": "Cob"})
        self.assertEqual(errors, [])
        self.assertNotIn("wall_materials_other", clean)

    def test_zones_have_no_gaps_and_no_upper_limit_on_the_last(self):
        from .formspec import ZONES, zone_for_hdd
        for a, b in zip(ZONES, ZONES[1:]):
            self.assertEqual(a["hdd_max"], b["hdd_min"])
        self.assertIsNone(ZONES[-1]["hdd_max"])
        self.assertEqual(zone_for_hdd(2999.9)["id"], "zone4")
        self.assertEqual(zone_for_hdd(3000)["id"], "zone5")
        self.assertEqual(zone_for_hdd(9000)["id"], "zone8")


# A postal code that starts with this letter, and a zone option, for each zone id.
OPTION_FOR_ZONE = {z["id"]: option for z, option in zip(ZONES, ZONE_OPTIONS)}


@override_settings(RATELIMIT_ENABLE=False)
class PostalCodeZoneTests(TestCase):
    """The climate zone has to be one that occurs where the postal code is."""

    def post(self, **changes):
        return self.client.post(
            "/api/recommend", data={"answers": {**valid_answers(), **changes}}, content_type="application/json"
        )

    def test_every_province_zone_is_a_real_zone_and_every_province_has_zones(self):
        zone_ids = {z["id"] for z in ZONES}
        provinces = {p for provs in POSTAL_LETTERS.values() for p in provs}
        self.assertEqual(set(PROVINCE_ZONES), provinces)
        for province, zones in PROVINCE_ZONES.items():
            self.assertTrue(zones, province)
            self.assertTrue(set(zones) <= zone_ids, province)

    def test_every_zone_is_reachable_from_some_postal_code(self):
        reachable = {z for letter in POSTAL_LETTERS for z in zones_for_postal_letter(letter)}
        self.assertEqual(reachable, {z["id"] for z in ZONES})

    def test_each_postal_letter_accepts_exactly_its_zones(self):
        for letter in POSTAL_LETTERS:
            postal = f"{letter}1A 1A1"
            allowed = zones_for_postal_letter(letter)
            for zone in ZONES:
                with self.subTest(letter=letter, zone=zone["id"]):
                    response = self.post(postal_code=postal, zone=OPTION_FOR_ZONE[zone["id"]])
                    if zone["id"] in allowed:
                        self.assertEqual(response.status_code, 200)
                    else:
                        self.assertEqual(response.status_code, 422)
                        self.assertEqual([e["field"] for e in response.json()["errors"]], ["zone"])

    def test_a_pei_postal_code_cannot_have_the_far_north_zone(self):
        response = self.post(postal_code="C1A 1A1", zone=OPTION_FOR_ZONE["zone8"])
        self.assertEqual(response.status_code, 422)
        self.assertIn("C1A 1A1", response.json()["errors"][0]["message"])

    def test_bc_and_alberta_codes_can_have_the_far_north_zone(self):
        for postal in ("V0C 1A0", "T0H 1A0"):
            with self.subTest(postal=postal):
                self.assertEqual(self.post(postal_code=postal, zone=OPTION_FOR_ZONE["zone8"]).status_code, 200)

    def test_a_nunavut_postal_code_cannot_have_a_mild_zone(self):
        self.assertEqual(self.post(postal_code="X0A 0H0", zone=OPTION_FOR_ZONE["zone4"]).status_code, 422)
        self.assertEqual(self.post(postal_code="X0A 0H0", zone=OPTION_FOR_ZONE["zone8"]).status_code, 200)

    def test_a_letter_shared_by_two_territories_allows_both_their_zones(self):
        self.assertEqual(set(zones_for_postal_letter("X")), set(PROVINCE_ZONES["NT"]) | set(PROVINCE_ZONES["NU"]))

    def test_postal_code_formatting_does_not_change_the_check(self):
        for postal in ("c1a1a1", " C1A  1A1 ", "C1A 1A1\n"):
            with self.subTest(postal=postal):
                self.assertEqual(self.post(postal_code=postal, zone=OPTION_FOR_ZONE["zone8"]).status_code, 422)
                self.assertEqual(self.post(postal_code=postal, zone=OPTION_FOR_ZONE["zone6"]).status_code, 200)

    def test_an_invalid_postal_code_or_zone_reports_only_its_own_error(self):
        errors = self.post(postal_code="not a code", zone=OPTION_FOR_ZONE["zone8"]).json()["errors"]
        self.assertEqual([e["field"] for e in errors], ["postal_code"])
        errors = self.post(postal_code="V6B 1A1", zone="Zone 99").json()["errors"]
        self.assertEqual([e["field"] for e in errors], ["zone"])

    def test_a_missing_zone_is_reported_as_required_not_as_a_mismatch(self):
        answers = valid_answers()
        del answers["zone"]
        response = self.client.post("/api/recommend", data={"answers": answers}, content_type="application/json")
        self.assertEqual(response.json()["errors"], [{"field": "zone", "message": "Climate Zone is required."}])

    def test_the_form_spec_publishes_the_rule_for_the_page(self):
        spec = self.client.get("/api/form-spec").json()
        zone = next(f for s in spec["sections"] for f in s["fields"] if f["id"] == "zone")
        rule = zone["must_match_postal"]
        self.assertEqual(rule["field"], "postal_code")
        self.assertEqual(set(rule["zones_by_letter"]), set(POSTAL_LETTERS))
        for letter, zones in rule["zones_by_letter"].items():
            self.assertEqual(zones, zones_for_postal_letter(letter))


class SettingsTests(SimpleTestCase):
    """Settings are read when Python starts, so each case runs a fresh interpreter."""

    def settings_for(self, **env):
        import os
        import subprocess
        import sys
        from pathlib import Path
        clean = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
        code = "import json, config.settings as s; print(json.dumps({k: getattr(s, k, None) for k in " \
               "['DEBUG','ALLOWED_HOSTS','SESSION_COOKIE_SECURE','CSRF_COOKIE_SECURE','SECURE_SSL_REDIRECT'," \
               "'SECURE_HSTS_SECONDS','SECURE_PROXY_SSL_HEADER','SECURE_HSTS_INCLUDE_SUBDOMAINS'," \
               "'SECURE_HSTS_PRELOAD','CSRF_TRUSTED_ORIGINS','TRUSTED_PROXY_COUNT',]}))"
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=Path(settings.BASE_DIR), capture_output=True, text=True,
            env={**clean, "DJANGO_SETTINGS_MODULE": "config.settings", **PRODUCTION_DB, **env},
        )
        return result

    def loaded(self, **env):
        result = self.settings_for(**env)
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        return json.loads(result.stdout)

    def test_production_refuses_to_start_without_postgres(self):
        result = self.settings_for(DJANGO_SECRET_KEY=STRONG_KEY, DJANGO_DB_NAME="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_DB_NAME must be set", result.stderr)

    def test_debug_is_off_unless_asked_for(self):
        self.assertFalse(self.loaded(DJANGO_SECRET_KEY=STRONG_KEY)["DEBUG"])
        self.assertTrue(self.loaded(DJANGO_DEBUG="1")["DEBUG"])
        for value in ("0", "false", "no", "", "nonsense"):
            with self.subTest(value=value):
                self.assertFalse(self.loaded(DJANGO_DEBUG=value, DJANGO_SECRET_KEY=STRONG_KEY)["DEBUG"])

    def test_production_refuses_to_start_without_a_real_secret_key(self):
        for key in (None, "", "replace-with-something", "changeme", "Change-Me-now"):
            with self.subTest(key=key):
                env = {} if key is None else {"DJANGO_SECRET_KEY": key}
                result = self.settings_for(**env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_production_refuses_a_short_or_repetitive_secret_key(self):
        # The same rule as Django's security.W009, made fatal: a weak key lets attackers forge
        # signed cookies and CSRF tokens.
        for key in ("abc", STRONG_KEY[:49], "k" * 50, "abcd" * 20,
                    "django-insecure-" + STRONG_KEY):
            with self.subTest(key=key):
                result = self.settings_for(DJANGO_SECRET_KEY=key)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_a_weak_secret_key_is_still_fine_for_local_work(self):
        self.assertTrue(self.loaded(DJANGO_DEBUG="1", DJANGO_SECRET_KEY="abc")["DEBUG"])

    def test_a_strong_secret_key_passes_the_deploy_check(self):
        import os
        import subprocess
        import sys
        from pathlib import Path
        clean = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
        result = subprocess.run(
            [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
            cwd=Path(settings.BASE_DIR), capture_output=True, text=True,
            env={**clean, **PRODUCTION_DB, "DJANGO_SECRET_KEY": STRONG_KEY,
                 "DJANGO_REDIS_URL": "rediss://cache.example.internal:6379/0"},
        )
        self.assertEqual(result.returncode, 0, result.stdout[-800:] + result.stderr[-800:])

    def test_number_settings_with_a_typo_stop_startup_with_a_clear_message(self):
        for name in ("DJANGO_TRUSTED_PROXY_COUNT", "DJANGO_SECURE_HSTS_SECONDS"):
            for value in ("abc", "-1", "1.5", "²"):
                with self.subTest(name=name, value=value):
                    result = self.settings_for(DJANGO_SECRET_KEY=STRONG_KEY, **{name: value})
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("ImproperlyConfigured", result.stderr)
                    self.assertIn(name, result.stderr)

    def test_hsts_can_be_turned_off_and_then_sends_no_subdomain_or_preload_flags(self):
        s = self.loaded(DJANGO_SECRET_KEY=STRONG_KEY, DJANGO_SECURE_HSTS_SECONDS="0")
        self.assertEqual(s["SECURE_HSTS_SECONDS"], 0)
        self.assertFalse(s["SECURE_HSTS_INCLUDE_SUBDOMAINS"])
        self.assertFalse(s["SECURE_HSTS_PRELOAD"])

    def test_the_ssl_redirect_can_be_turned_off_behind_a_proxy_that_does_it(self):
        self.assertFalse(self.loaded(DJANGO_SECRET_KEY=STRONG_KEY, DJANGO_SECURE_SSL_REDIRECT="0")["SECURE_SSL_REDIRECT"])

    def test_csrf_trusted_origins_are_split_and_trimmed(self):
        s = self.loaded(DJANGO_SECRET_KEY=STRONG_KEY,
                        DJANGO_CSRF_TRUSTED_ORIGINS=" https://a.example ,, https://b.example ")
        self.assertEqual(s["CSRF_TRUSTED_ORIGINS"], ["https://a.example", "https://b.example"])

    def test_production_turns_on_secure_cookies_https_and_hsts(self):
        s = self.loaded(DJANGO_SECRET_KEY=STRONG_KEY)
        self.assertTrue(s["SESSION_COOKIE_SECURE"] and s["CSRF_COOKIE_SECURE"] and s["SECURE_SSL_REDIRECT"])
        self.assertEqual(s["SECURE_HSTS_SECONDS"], 31536000)
        self.assertIsNone(s["SECURE_PROXY_SSL_HEADER"])  # forwarded headers are not trusted by default

    def test_forwarded_headers_are_trusted_only_when_asked(self):
        s = self.loaded(DJANGO_SECRET_KEY=STRONG_KEY, DJANGO_TRUST_PROXY_HEADERS="1")
        self.assertEqual(s["SECURE_PROXY_SSL_HEADER"], ["HTTP_X_FORWARDED_PROTO", "https"])

    def test_allowed_hosts_are_split_and_trimmed(self):
        s = self.loaded(DJANGO_DEBUG="1", DJANGO_ALLOWED_HOSTS=" a.example , b.example,, ")
        self.assertEqual(s["ALLOWED_HOSTS"], ["a.example", "b.example"])
        self.assertEqual(self.loaded(DJANGO_DEBUG="1", DJANGO_ALLOWED_HOSTS="")["ALLOWED_HOSTS"],
                         ["localhost", "127.0.0.1", "[::1]"])

    def test_production_refuses_to_start_without_its_hostnames(self):
        for value in ("", "  ", " , "):
            with self.subTest(value=value):
                result = self.settings_for(DJANGO_SECRET_KEY=STRONG_KEY, DJANGO_ALLOWED_HOSTS=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("DJANGO_ALLOWED_HOSTS", result.stderr)

    def test_the_cloudfront_address_works_until_there_is_a_domain_and_both_can_be_listed(self):
        s = self.loaded(DJANGO_SECRET_KEY=STRONG_KEY, DJANGO_ALLOWED_HOSTS="d1234abcd.cloudfront.net")
        self.assertEqual(s["ALLOWED_HOSTS"], ["d1234abcd.cloudfront.net"])
        s = self.loaded(DJANGO_SECRET_KEY=STRONG_KEY,
                        DJANGO_ALLOWED_HOSTS="retrofit.example.com, d1234abcd.cloudfront.net, .example.org")
        self.assertEqual(s["ALLOWED_HOSTS"], ["retrofit.example.com", "d1234abcd.cloudfront.net", ".example.org"])

    def test_hostnames_that_are_not_hostnames_are_refused(self):
        # "*" would accept any Host header; a URL or path would never match one.
        for value in ("*", "retrofit.example.com,*", "https://retrofit.example.com", "retrofit.example.com/api"):
            for debug in ("0", "1"):
                with self.subTest(value=value, debug=debug):
                    result = self.settings_for(DJANGO_SECRET_KEY=STRONG_KEY, DJANGO_DEBUG=debug,
                                               DJANGO_ALLOWED_HOSTS=value)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("is not a hostname", result.stderr)

    def test_the_https_header_can_be_cloudfronts_until_there_is_a_domain(self):
        trust = {"DJANGO_SECRET_KEY": STRONG_KEY, "DJANGO_TRUST_PROXY_HEADERS": "1"}
        for value, expected in (("", "HTTP_X_FORWARDED_PROTO"), ("X-Forwarded-Proto", "HTTP_X_FORWARDED_PROTO"),
                                ("CloudFront-Forwarded-Proto", "HTTP_CLOUDFRONT_FORWARDED_PROTO"),
                                ("cloudfront-forwarded-proto", "HTTP_CLOUDFRONT_FORWARDED_PROTO")):
            with self.subTest(value=value):
                s = self.loaded(DJANGO_PROXY_SSL_HEADER=value, **trust)
                self.assertEqual(s["SECURE_PROXY_SSL_HEADER"], [expected, "https"])

    def test_only_the_two_known_https_headers_can_be_chosen(self):
        for value in ("X-Forwarded-Ssl", "Host", "HTTP_X_FORWARDED_PROTO"):
            with self.subTest(value=value):
                result = self.settings_for(DJANGO_SECRET_KEY=STRONG_KEY, DJANGO_TRUST_PROXY_HEADERS="1",
                                           DJANGO_PROXY_SSL_HEADER=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("DJANGO_PROXY_SSL_HEADER", result.stderr)

    def test_the_https_header_is_ignored_unless_proxy_headers_are_trusted(self):
        s = self.loaded(DJANGO_SECRET_KEY=STRONG_KEY, DJANGO_PROXY_SSL_HEADER="CloudFront-Forwarded-Proto")
        self.assertIsNone(s["SECURE_PROXY_SSL_HEADER"])


@override_settings(RATELIMIT_ENABLE=False)
class EndpointMethodTests(TestCase):
    def test_only_the_expected_methods_are_allowed(self):
        for url, allowed in (("/api/recommend", "POST"), ("/api/health", "GET"),
                             ("/api/form-spec", "GET"), ("/api/incentives", "GET")):
            for method in ("get", "post", "put", "patch", "delete"):
                if method.upper() == allowed:
                    continue
                with self.subTest(url=url, method=method):
                    self.assertEqual(getattr(self.client, method)(url).status_code, 405)

    def test_unknown_paths_and_the_admin_do_not_exist(self):
        for url in ("/admin/", "/api/", "/api/recommend/", "/api/unknown"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_no_endpoint_sets_a_csrf_cookie(self):
        for url in ("/api/form-spec", "/api/health"):
            with self.subTest(url=url):
                self.assertNotIn("csrftoken", Client().get(url).cookies)

    def test_security_headers_are_on_every_response(self):
        for url in ("/api/health", "/api/form-spec", "/nowhere"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                self.assertEqual(response["X-Frame-Options"], "DENY")
                self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_a_host_that_is_not_allowed_is_refused(self):
        # GET /api/health is the one exception, for load balancer checks (config/health.py).
        for method, url in (("get", "/api/form-spec"), ("get", "/api/incentives"),
                            ("post", "/api/recommend"), ("post", "/api/health")):
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url, HTTP_HOST="evil.example").status_code, 400)
        self.assertEqual(self.client.get("/api/health", HTTP_HOST="evil.example").status_code, 200)

    def test_deeply_nested_json_is_refused_not_crashed_on(self):
        body = '{"answers":' + "[" * 100000 + "]" * 100000 + "}"
        self.assertEqual(self.client.post("/api/recommend", data=body, content_type="application/json").status_code, 422)

    def test_negative_zero_is_stored_as_plain_zero(self):
        from .formspec import validate
        clean, errors = validate({**valid_answers(), "energy_bill_winter": -0.0})
        self.assertEqual(errors, [])
        self.assertEqual(str(clean["energy_bill_winter"]), "0.0")


@override_settings(RATELIMIT_ENABLE=False)
class WholeNumberTests(TestCase):
    """Years and other whole-number answers must arrive as integers, never as decimals."""

    def post_json(self, year_text=None, **changes):
        answers = {**valid_answers(), **changes}
        body = json.dumps({"answers": answers})
        if year_text is not None:  # spell the year exactly as given, e.g. 1985.0 or 1.985e3
            body = body.replace('"year_built": %d' % answers["year_built"], '"year_built": ' + year_text)
        return self.client.post("/api/recommend", data=body, content_type="application/json")

    def fields_in_error(self, response):
        return [e["field"] for e in response.json()["errors"]]

    def test_year_built_rejects_every_decimal_spelling(self):
        for text in ("1985.0", "1985.5", "1.985e3", "1985e0", "19850E-1", "1985.000000001"):
            with self.subTest(year=text):
                response = self.post_json(year_text=text)
                self.assertEqual(response.status_code, 422)
                self.assertIn("year_built", self.fields_in_error(response))

    def test_every_whole_number_question_rejects_a_float_even_when_it_looks_whole(self):
        for field in FIELDS:
            if not field.get("integer"):
                continue
            for value in (float(field["min"] + 1), field["min"] + 1.5):
                with self.subTest(field=field["id"], value=value):
                    response = self.post_json(**{field["id"]: value})
                    self.assertEqual(response.status_code, 422)
                    self.assertIn(field["id"], self.fields_in_error(response))

    def test_renovation_years_reject_floats(self):
        for year in (2015.0, 2015.5, 1e3, 2e3):
            with self.subTest(year=year):
                response = self.post_json(renovation_history=[{"type": "Roof", "year": year}])
                self.assertEqual(response.status_code, 422)
                self.assertIn("renovation_history", self.fields_in_error(response))

    def test_integers_are_still_accepted_and_kept_as_integers(self):
        from .formspec import validate
        clean, errors = validate({**valid_answers(), "year_built": 1985, "exterior_doors": 3,
                                  "renovation_history": [{"type": "Roof", "year": 2015}]})
        self.assertEqual(errors, [])
        self.assertIs(type(clean["year_built"]), int)
        self.assertIs(type(clean["exterior_doors"]), int)
        self.assertIs(type(clean["renovation_history"][0]["year"]), int)


@override_settings(RATELIMIT_ENABLE=False)
class CrossCheckTests(TestCase):
    def post(self, **changes):
        return self.client.post(
            "/api/recommend", data={"answers": {**valid_answers(), **changes}}, content_type="application/json"
        )

    def errors(self, response):
        return response.json().get("errors", [])

    def test_a_renovation_cannot_be_older_than_the_building(self):
        response = self.post(year_built=2000, renovation_history=[{"type": "Roof", "year": 2010},
                                                                   {"type": "Walls", "year": 1999}])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.errors(response),
                         [{"field": "renovation_history", "message": "Renovation 2 is dated before the building was built (2000)."}])

    def test_a_renovation_in_the_year_it_was_built_is_fine(self):
        self.assertEqual(self.post(year_built=2000, renovation_history=[{"type": "Roof", "year": 2000}]).status_code, 200)

    def test_rejected_renovations_are_not_passed_on(self):
        from .formspec import validate
        clean, errors = validate({**valid_answers(), "year_built": 2000,
                                  "renovation_history": [{"type": "Roof", "year": 1990}]})
        self.assertTrue(errors)
        self.assertNotIn("renovation_history", clean)

    def test_range_errors_are_written_in_the_units_the_user_chose(self):
        imperial = {**valid_answers(), "preferred_units": IMPERIAL, "indoor_temperature": 70}
        message = self.errors(self.post(**{**imperial, "indoor_temperature": 100}))[0]["message"]
        self.assertIn("(50 to 86 °F)", message)
        message = self.errors(self.post(**{**imperial, "wall_thickness": 0.1}))[0]["message"]
        self.assertIn("(0.79 to 59.06 in)", message)
        metric = {**valid_answers(), "preferred_units": METRIC, "indoor_temperature": 20}
        self.assertIn("(10 to 30 °C)", self.errors(self.post(**{**metric, "indoor_temperature": 40}))[0]["message"])
        self.assertIn("(0 to 20000)", self.errors(self.post(**{**metric, "energy_bill_winter": -1}))[0]["message"])

    def test_other_text_that_is_not_text_is_reported(self):
        for bad in (["Cob"], 5, {"a": 1}, True):
            with self.subTest(other=bad):
                response = self.post(wall_materials=["Other"], wall_materials_other=bad)
                self.assertEqual(response.status_code, 422)
                self.assertEqual([e["field"] for e in self.errors(response)], ["wall_materials_other"])
        self.assertEqual(self.post(wall_materials=["Other"], wall_materials_other=None).status_code, 200)


class CurrentYearTests(SimpleTestCase):
    """The "this year" limits follow the calendar while the server keeps running."""

    def test_limits_move_forward_on_new_year(self):
        from datetime import date
        from unittest import mock
        from . import formspec

        class NextYear(date):
            @classmethod
            def today(cls):
                return date(date.today().year + 1, 1, 1)

        this_year = date.today().year
        try:
            with mock.patch.object(formspec, "date", NextYear):
                answers = {**valid_answers(), "year_built": this_year + 1,
                           "renovation_history": [{"type": "Roof", "year": this_year + 1}]}
                clean, errors = formspec.validate(answers)
                self.assertEqual(errors, [])
                spec = formspec.public_spec()
                year_built = next(f for s in spec["sections"] for f in s["fields"] if f["id"] == "year_built")
                self.assertEqual(year_built["max"], this_year + 1)
        finally:
            formspec._sync_current_year()  # back to the real year for the other tests
        self.assertEqual(FIELD_BY_ID["year_built"]["max"], this_year)
        clean, errors = formspec.validate({**valid_answers(), "year_built": this_year + 1})
        self.assertIn("year_built", [e["field"] for e in errors])
