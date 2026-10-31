import json
import logging
import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import API_KEY

HEADERS = {"X-API-Key": API_KEY}
DOCS_PATHS = ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]
PROTECTED = [
    ("post", "/application"),
    ("patch", "/application/{application_id}"),
    ("delete", "/application/{application_id}"),
    ("post", "/resume"),
    ("get", "/resume/{application_id}/status"),
    ("post", "/cover-letter"),
    ("get", "/cover-letter/{application_id}/status"),
]
VIEWER_READS = [
    ("get", "/applications"),
    ("get", "/application/{application_id}"),
    ("get", "/application/{application_id}/resume.pdf"),
    ("get", "/application/{application_id}/cover-letter.pdf"),
    ("get", "/resume/base.pdf"),
    ("get", "/cover-letter/base.pdf"),
]
HEALTH = [("get", "/health"), ("get", "/healthz")]
RESPONSES = {
    ("get", "/health"): {"200"},
    ("get", "/healthz"): {"200"},
    ("post", "/application"): {"200", "201", "401", "422", "503"},
    ("patch", "/application/{application_id}"): {"200", "401", "404", "422", "503"},
    ("delete", "/application/{application_id}"): {"200", "401", "404", "503"},
    ("post", "/resume"): {"202", "401", "404", "422", "503"},
    ("get", "/resume/{application_id}/status"): {"200", "401", "404", "503"},
    ("post", "/cover-letter"): {"202", "401", "404", "422", "503"},
    ("get", "/cover-letter/{application_id}/status"): {"200", "401", "404", "503"},
    ("get", "/applications"): {"200", "503"},
    ("get", "/application/{application_id}"): {"200", "404", "503"},
    ("get", "/application/{application_id}/resume.pdf"): {"200", "404", "503"},
    ("get", "/application/{application_id}/cover-letter.pdf"): {"200", "404", "503"},
    ("get", "/resume/base.pdf"): {"200", "500"},
    ("get", "/cover-letter/base.pdf"): {"200", "404"},
}
PDF_OPERATIONS = [("get", "/application/{application_id}/resume.pdf"), ("get", "/application/{application_id}/cover-letter.pdf"),
                  ("get", "/resume/base.pdf"), ("get", "/cover-letter/base.pdf")]
IMMUTABLE = {"job_link", "posting_source_type", "verification_method", "official_apply_url"}


@pytest.fixture
def schema(docs_client):
    r = docs_client.get("/openapi.json")
    assert r.status_code == 200
    return r.json()


def operations(schema):
    return {(method, path): op for path, ops in schema["paths"].items() for method, op in ops.items()}


def component(schema, operation):
    ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    return schema["components"]["schemas"][ref.rsplit("/", 1)[1]]


# --- served only when enabled ---

@pytest.mark.parametrize("path", DOCS_PATHS)
def test_docs_not_served_by_default(settings, storage, path):
    client = TestClient(create_app(settings, storage))
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_docs_pages_served_when_enabled(docs_client, path):
    r = docs_client.get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")


def test_schema_served_without_api_key(schema):
    assert schema["openapi"].startswith("3.")


def test_swagger_does_not_persist_authorization(docs_client):
    html = docs_client.get("/docs").text
    assert '"persistAuthorization": false' in html
    assert '"persistAuthorization": true' not in html


# --- coverage and metadata ---

def test_documents_exactly_the_fifteen_operations(schema):
    assert set(operations(schema)) == set(RESPONSES) and len(RESPONSES) == 15


def test_viewer_page_is_not_an_operation(schema):
    assert "/viewer" not in schema["paths"]


def test_pdf_responses(schema):
    ops = operations(schema)
    for key in PDF_OPERATIONS:
        assert set(ops[key]["responses"]["200"]["content"]) == {"application/pdf"}, key


def test_viewer_reads_document_the_report(schema):
    ops = operations(schema)
    detail = ops[("get", "/application/{application_id}")]["responses"]["200"]["content"]["application/json"]
    assert detail["schema"]["$ref"] == "#/components/schemas/ApplicationDetail"
    schemas = schema["components"]["schemas"]
    assert {"base", "tailored", "added_terms", "rejected_terms", "saved_path"} <= set(schemas["ResumeReport"]["properties"])
    assert {"text", "status", "counted", "evidence"} <= set(schemas["RequirementRow"]["properties"])
    listed = ops[("get", "/applications")]["responses"]["200"]["content"]["application/json"]
    assert listed["schema"]["$ref"] == "#/components/schemas/ApplicationList"
    assert "full_job_description" not in schemas["ApplicationListItem"]["properties"]


def test_cover_letter_reads_described(schema):
    ops = operations(schema)
    saved = ops[("get", "/application/{application_id}/cover-letter.pdf")]
    assert "current company" in saved["description"] and "beside the resume" in saved["description"]
    base = ops[("get", "/cover-letter/base.pdf")]
    assert "data/COVER_LETTER.pdf" in base["description"] and "never generates" in base["description"]
    assert saved["tags"] == base["tags"] == ["viewer"]


def test_every_operation_has_tag_summary_description(schema):
    for key, op in operations(schema).items():
        assert op.get("tags") and op.get("summary") and op.get("description"), key


def test_health_routes_describe_each_other(schema):
    ops = operations(schema)
    assert "/healthz" in ops[("get", "/health")]["description"]
    assert "/health`" in ops[("get", "/healthz")]["description"]


# --- security ---

def test_api_key_security_scheme(schema):
    assert schema["components"]["securitySchemes"]["ApiKey"] == {
        **schema["components"]["securitySchemes"]["ApiKey"], "type": "apiKey", "in": "header", "name": "X-API-Key",
    }
    ops = operations(schema)
    for key in PROTECTED:
        assert ops[key]["security"] == [{"ApiKey": []}], key
    for key in HEALTH + VIEWER_READS:
        assert "security" not in ops[key], key


def test_api_key_is_not_a_header_parameter(schema):
    for key, op in operations(schema).items():
        assert all(p["name"].lower() != "x-api-key" for p in op.get("parameters", [])), key


# --- request bodies ---

def test_application_body_schema(schema):
    body = component(schema, operations(schema)[("post", "/application")])
    assert set(body["required"]) == {
        "company", "role", "job_link", "posting_source_type", "verification_method", "official_apply_url",
    }
    assert body["properties"]["posting_source_type"]["enum"] == ["recruiting_platform", "employer_site"]
    assert body["properties"]["verification_method"]["enum"] == ["official_apply_match", "employer_site"]


def test_update_body_schema(schema):
    body = component(schema, operations(schema)[("patch", "/application/{application_id}")])
    assert not IMMUTABLE & set(body["properties"])
    assert body["properties"]["status"]["enum"] == [
        "verified", "applied", "interviewing", "offer", "rejected", "withdrawn",
    ]
    assert "required" not in body


def test_resume_body_schema(schema):
    body = component(schema, operations(schema)[("post", "/resume")])
    assert body["required"] == ["application_id"]


def test_cover_letter_body_schema(schema):
    body = component(schema, operations(schema)[("post", "/cover-letter")])
    assert body["required"] == ["application_id"] and body["properties"]["application_id"]["type"] == "string"


def response_schema(schema, op, status):
    ref = op["responses"][status]["content"]["application/json"]["schema"]["$ref"]
    return schema["components"]["schemas"][ref.rsplit("/", 1)[1]]


STATUS_FIELDS = {"ok", "application_id", "status", "started_at", "finished_at", "saved_path", "error"}


@pytest.mark.parametrize("path", ["/resume", "/cover-letter"])
def test_generation_accepted_response(schema, path):
    op = operations(schema)[("post", path)]
    accepted = response_schema(schema, op, "202")
    assert set(accepted["properties"]) == {"ok", "application_id", "status", "started_at"}
    assert accepted["properties"]["status"]["const"] == "running"
    assert "201" not in op["responses"] and "500" not in op["responses"] and "502" not in op["responses"]


@pytest.mark.parametrize("path, status_path", [("/resume", "/resume/{application_id}/status"),
                                               ("/cover-letter", "/cover-letter/{application_id}/status")])
def test_background_generation_described(schema, path, status_path):
    description = " ".join(operations(schema)[("post", path)]["description"].split())
    for phrase in ("returns 202", "in the background", "whether or not the client stays connected",
                   f"`GET {status_path}`", "starts no second run", "`started_at`"):
        assert phrase in description, phrase
    assert "timeout" not in description


@pytest.mark.parametrize("path, result, tag", [("/resume/{application_id}/status", "match", "resumes"),
                                               ("/cover-letter/{application_id}/status", "text", "cover letters")])
def test_status_endpoints_described(schema, path, result, tag):
    op = operations(schema)[("get", path)]
    job = response_schema(schema, op, "200")
    assert set(job["properties"]) == STATUS_FIELDS | {result}
    assert job["properties"]["status"]["enum"] == ["running", "done", "failed"]
    for name in ("finished_at", "saved_path", "error", result):
        assert {t.get("type") for t in job["properties"][name]["anyOf"]} >= {"null"}, name
    description = " ".join(op["description"].split())
    for phrase in ("`running`, `done` or `failed`", "Interrupted by a service restart", "no posting text"):
        assert phrase in description, phrase
    assert op["tags"] == [tag] and op["security"] == [{"ApiKey": []}]
    assert "No job for this application" in op["responses"]["404"]["description"]


@pytest.mark.parametrize("model", ["ResumeJobStatus", "CoverLetterJobStatus", "ResumeReport"])
def test_saved_path_documented_as_a_file_name(schema, model):
    description = schema["components"]["schemas"][model]["properties"]["saved_path"]["description"]
    assert "file name" in description.lower()
    assert "/" not in description and "absolute" not in description.lower()


def test_no_operation_says_saved_path_is_a_path(schema):
    for key, op in operations(schema).items():
        description = " ".join(op.get("description", "").split())
        assert "absolute path" not in description and "at the job's `saved_path`" not in description, key


def test_cover_letter_description(schema):
    op = operations(schema)[("post", "/cover-letter")]
    text = response_schema(schema, operations(schema)[("get", "/cover-letter/{application_id}/status")], "200")
    assert text["properties"]["text"]["description"] and text["properties"]["saved_path"]["description"]
    description = " ".join(op["description"].split())
    for phrase in ("always tailored", "posting text", "beside the application's resume", "`text`",
                   "`POST /resume` never writes one"):
        assert phrase in description, phrase
    assert "posting text" in op["responses"]["422"]["description"]
    assert op["tags"] == ["cover letters"]


def test_resume_status_documents_match(schema):
    job = response_schema(schema, operations(schema)[("get", "/resume/{application_id}/status")], "200")
    ref = next(t["$ref"] for t in job["properties"]["match"]["anyOf"] if "$ref" in t)
    match = schema["components"]["schemas"][ref.rsplit("/", 1)[1]]
    assert set(match["properties"]) == set(match["required"]) == {"status", "threshold", "base_score", "tailored_score",
                                                                  "added_terms"}
    assert match["properties"]["added_terms"]["type"] == "array"
    assert match["properties"]["added_terms"]["items"] == {"type": "string"}
    assert set(match["properties"]["status"]["enum"]) == {"no_job_description", "base_meets_threshold", "tailored"}
    for score in ("base_score", "tailored_score"):
        assert {t["type"] for t in match["properties"][score]["anyOf"]} == {"integer", "null"}
    assert all(match["properties"][name].get("description") for name in match["properties"])
    assert "cover_letter_path" not in job["properties"]


def test_resume_description_states_duration_and_choices(schema):
    op = operations(schema)[("post", "/resume")]
    assert "capped at about 10" in op["description"]
    assert all(status in op["description"] for status in ("no_job_description", "base_meets_threshold", "tailored"))


def test_path_ids_stay_plain_strings(schema):
    # A typed UUID would let FastAPI answer a malformed ID with its own 422 instead of 404.
    for key in [("patch", "/application/{application_id}"), ("delete", "/application/{application_id}")]:
        (param,) = operations(schema)[key]["parameters"]
        assert param["schema"]["type"] == "string" and "format" not in param["schema"]


def test_documented_examples_are_accepted(schema, docs_client):
    ops = operations(schema)

    def example(key):
        return ops[key]["requestBody"]["content"]["application/json"]["example"]

    r = docs_client.post("/application", json=example(("post", "/application")), headers=HEADERS)
    assert r.status_code == 201, r.json()
    application_id = r.json()["application_id"]
    r = docs_client.patch(
        f"/application/{application_id}", json=example(("patch", "/application/{application_id}")), headers=HEADERS,
    )
    assert r.status_code == 200, r.json()
    # The documented resume example holds a placeholder ID; only its shape is checked here.
    resume = {**example(("post", "/resume")), "application_id": application_id}
    assert set(resume) == set(example(("post", "/resume")))
    r = docs_client.post("/resume", json=resume, headers=HEADERS)
    assert r.status_code == 202, r.json()
    # The example application's posting is too short for a letter, so a 422 is fine, but only for that reason.
    letter = {**example(("post", "/cover-letter")), "application_id": application_id}
    assert set(letter) == set(example(("post", "/cover-letter")))
    r = docs_client.post("/cover-letter", json=letter, headers=HEADERS)
    assert r.status_code == 202 or "posting text" in r.json()["message"], r.json()


# --- responses ---

def test_documented_statuses(schema):
    for key, op in operations(schema).items():
        assert set(op["responses"]) == RESPONSES[key], key


def test_errors_use_ok_message_shape(schema):
    assert set(schema["components"]["schemas"]["ErrorResponse"]["properties"]) == {"ok", "message"}
    for key, op in operations(schema).items():
        for status, response in op["responses"].items():
            if status[0] in "45":
                ref = response["content"]["application/json"]["schema"]["$ref"]
                assert ref == "#/components/schemas/ErrorResponse", (key, status)


def test_no_fastapi_validation_error_shape(schema):
    assert "HTTPValidationError" not in json.dumps(schema)
    assert "ValidationError" not in schema["components"]["schemas"]


# --- logging ---

def request_lines(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "app.requests"]


def test_docs_requests_emit_no_request_log_line(docs_client, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    for path in DOCS_PATHS:
        docs_client.get(path)
    assert request_lines(caplog) == []


def test_tried_request_logged_once(schema, docs_client, caplog):
    example = operations(schema)[("post", "/application")]["requestBody"]["content"]["application/json"]["example"]
    application_id = docs_client.post("/application", json=example, headers=HEADERS).json()["application_id"]
    caplog.set_level(logging.INFO, logger="app.requests")
    caplog.clear()
    docs_client.delete(f"/application/{application_id}", headers=HEADERS)
    lines = request_lines(caplog)
    assert len(lines) == 1 and lines[0]["event"] == "application_request" and lines[0]["method"] == "DELETE"
    assert API_KEY not in caplog.text


def test_healthz_listed_before_its_alias(schema):
    paths = list(schema["paths"])
    assert paths.index("/healthz") < paths.index("/health")


# --- pinned page assets ---

ASSET = re.compile(r'(?:src|href)="(https://cdn\.jsdelivr\.net/npm/[^"]+)"([^>]*)>')


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_page_assets_pinned_with_integrity(docs_client, path):
    assets = ASSET.findall(docs_client.get(path).text)
    assert assets
    for url, attributes in assets:
        assert re.search(r"@\d+\.\d+\.\d+/", url), url
        assert 'integrity="sha384-' in attributes and 'crossorigin="anonymous"' in attributes, url


def test_swagger_page_loads_scripts_and_styles(docs_client):
    urls = [url for url, _ in ASSET.findall(docs_client.get("/docs").text)]
    assert any(u.endswith("swagger-ui-bundle.js") for u in urls)
    assert any(u.endswith("swagger-ui.css") for u in urls)


def test_oauth2_redirect_served_when_enabled(docs_client):
    assert docs_client.get("/docs/oauth2-redirect").status_code == 200
