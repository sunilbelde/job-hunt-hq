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
]
HEALTH = [("get", "/health"), ("get", "/healthz")]
RESPONSES = {
    ("get", "/health"): {"200"},
    ("get", "/healthz"): {"200"},
    ("post", "/application"): {"200", "201", "401", "422", "503"},
    ("patch", "/application/{application_id}"): {"200", "401", "404", "422", "503"},
    ("delete", "/application/{application_id}"): {"200", "401", "404", "503"},
    ("post", "/resume"): {"201", "401", "404", "422", "500", "502", "503"},
}
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

def test_documents_exactly_the_six_operations(schema):
    assert set(operations(schema)) == set(RESPONSES)


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
    for key in HEALTH:
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


def test_resume_response_documents_cover_letter_path(schema):
    response = operations(schema)[("post", "/resume")]["responses"]["201"]
    ref = response["content"]["application/json"]["schema"]["$ref"]
    created = schema["components"]["schemas"][ref.rsplit("/", 1)[1]]
    assert set(created["properties"]) == {"ok", "application_id", "saved_path", "cover_letter_path", "match"}
    assert "not generated yet" in created["properties"]["cover_letter_path"]["description"]


def test_resume_response_documents_match(schema):
    response = operations(schema)[("post", "/resume")]["responses"]["201"]
    ref = response["content"]["application/json"]["schema"]["$ref"]
    created = schema["components"]["schemas"][ref.rsplit("/", 1)[1]]
    match = schema["components"]["schemas"][created["properties"]["match"]["$ref"].rsplit("/", 1)[1]]
    assert set(match["properties"]) == set(match["required"]) == {"status", "threshold", "base_score", "tailored_score",
                                                                  "added_terms"}
    assert match["properties"]["added_terms"]["type"] == "array"
    assert match["properties"]["added_terms"]["items"] == {"type": "string"}
    assert set(match["properties"]["status"]["enum"]) == {"no_job_description", "base_meets_threshold", "tailored"}
    for score in ("base_score", "tailored_score"):
        assert {t["type"] for t in match["properties"][score]["anyOf"]} == {"integer", "null"}
    assert all(match["properties"][name].get("description") for name in match["properties"])


def test_resume_description_states_duration_and_failures(schema):
    op = operations(schema)[("post", "/resume")]
    assert "at least 10 minutes" in op["description"]
    assert all(status in op["description"] for status in ("no_job_description", "base_meets_threshold", "tailored"))
    assert "tailoring" in op["responses"]["500"]["description"]


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
    assert r.status_code == 201, r.json()


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
