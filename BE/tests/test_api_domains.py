"""Ensure the domain-organized API keeps existing URLs and OpenAPI groups."""

from app.main import app


def test_domain_api_groups_keep_existing_route_prefixes():
    paths = app.openapi()["paths"]

    assert "/api/formats" in paths
    assert "/api/formats/{format_id}/publish-without-approval" in paths
    assert "/api/formats/{format_id}/approval/history" in paths
    assert "/api/formats/teams" in paths
    assert "/api/records" in paths
    assert "/api/documents/repository" in paths
    assert "/api/documents/{document_id}" in paths
    assert "/api/workflow" in paths
    assert "/api/auth/users" in paths
    assert "/api/departments" in paths
    assert "/api/roles" in paths
    assert "/api/roles/permissions" in paths
    assert "/api/roles/users/{user_id}" in paths


def test_template_document_and_people_apis_have_domain_tags():
    paths = app.openapi()["paths"]

    assert "Template Management" in paths["/api/formats"]["get"]["tags"]
    assert "Document Management" in paths["/api/records"]["get"]["tags"]
    assert "Document Management" in paths[
        "/api/documents/{document_id}"
    ]["get"]["tags"]
    assert "People & Teams" in paths["/api/formats/teams"]["get"]["tags"]
    assert "People & Teams" in paths["/api/auth/users"]["get"]["tags"]
    assert paths["/api/departments"]["get"]["tags"] == ["People & Teams"]
    assert paths["/api/departments"]["post"]["tags"] == ["People & Teams"]


def test_create_user_does_not_document_a_csrf_header():
    operation = app.openapi()["paths"]["/api/auth/users"]["post"]
    assert all(
        parameter["name"] != "X-CSRF-Token"
        for parameter in operation.get("parameters", [])
    )


def test_each_operation_belongs_to_only_its_section():
    paths = app.openapi()["paths"]

    assert paths["/api/formats/teams"]["get"]["tags"] == ["People & Teams"]
    assert paths["/api/formats/teams"]["post"]["tags"] == ["People & Teams"]
    assert paths["/api/formats"]["get"]["tags"] == ["Template Management"]
    assert paths["/api/auth/users"]["get"]["tags"] == ["People & Teams"]
    assert paths["/api/roles"]["get"]["tags"] == ["Identity & Access"]
    assert paths["/api/roles/permissions"]["get"]["tags"] == ["Identity & Access"]
    assert paths["/api/auth/login"]["post"]["tags"] == ["Identity & Access"]
    assert all(
        len(operation.get("tags", [])) == 1
        for operations in paths.values()
        for operation in operations.values()
    )


def test_collection_slash_aliases_are_not_duplicated_in_openapi():
    paths = app.openapi()["paths"]
    canonical_operations = set()

    assert "/api/csrf-token" not in paths
    assert "/api/auth/csrf-token" not in paths

    for path, operations in paths.items():
        for method in operations:
            key = (path.rstrip("/") or "/", method)
            assert key not in canonical_operations, (
                f"Duplicate OpenAPI operation for {method.upper()} {key[0]}"
            )
            canonical_operations.add(key)


def test_csrf_token_endpoints_are_removed():
    from fastapi.testclient import TestClient

    client = TestClient(app)
    assert client.get("/api/csrf-token").status_code == 404
    assert client.get("/api/auth/csrf-token").status_code == 404


def test_api_counts_match_documented_api_operations():
    from fastapi.testclient import TestClient

    paths = app.openapi()["paths"]
    expected = {}
    total = 0
    http_methods = {
        "get", "post", "put", "patch", "delete", "options", "head", "trace",
    }
    for path, operations in paths.items():
        if not path.startswith("/api/"):
            continue
        for method, operation in operations.items():
            if method.lower() not in http_methods:
                continue
            total += 1
            section = operation["tags"][0]
            expected[section] = expected.get(section, 0) + 1

    response = TestClient(app).get("/api/health/api-counts")

    assert response.status_code == 200
    assert response.json() == {
        "total_apis": total,
        "by_section": dict(sorted(expected.items())),
    }
def test_template_approval_request_schema_is_clear_in_swagger():
    openapi = app.openapi()
    operation = openapi["paths"][
        "/api/formats/{format_id}/submit-approval"
    ]["post"]
    request_body = operation["requestBody"]["content"]["application/json"]

    assert "process_owner_then_cft" in request_body["examples"]
    payload_schema = openapi["components"]["schemas"]["FormatReviewPayload"]
    step_schema = openapi["components"]["schemas"]["FormatReviewStepPayload"]
    assert payload_schema["properties"]["steps"]["description"]
    assert payload_schema["properties"]["priority"]["enum"] == [
        "low", "normal", "high", "urgent",
    ]
    assert set(step_schema["properties"]) == {
        "name",
        "reviewer_ids",
        "role_id",
        "mode",
        "due_days",
    }
    assert step_schema["properties"]["mode"]["enum"] == ["any", "all"]


def test_format_create_schema_contains_form_details_not_approval_setup():
    openapi = app.openapi()
    assert "/api/formats/approvers" in openapi["paths"]
    assert "/api/formats/approvals/mine" in openapi["paths"]
    assert "/api/formats/builder" not in openapi["paths"]
    assert any(
        parameter["name"] == "tab"
        for parameter in openapi["paths"]["/api/formats"]["get"]["parameters"]
    )
    operation = openapi["paths"]["/api/formats"]["post"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    format_schema = openapi["components"]["schemas"]["FormatPayload"]
    properties = format_schema["properties"]

    assert set(properties) == {
        "code",
        "title",
        "frequency",
        "description",
        "fields",
        "layout",
        "work_instruction_ref",
        "work_instruction",
        "storage_path",
    }
    # the code is optional: a blank one is the team's next (QF-PQ-004), assigned by the server
    assert set(format_schema["required"]) == {"title", "frequency"}
    assert "examples" in format_schema
    assert format_schema["examples"][0]["storage_path"] == "Teams"
    assert request_schema["$ref"].endswith("/FormatPayload")
