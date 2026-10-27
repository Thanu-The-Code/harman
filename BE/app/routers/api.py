"""Register the version of the API that is exposed by this FastAPI app.

The domain groups organize route modules and the generated API documentation.
They are modular boundaries within one deployment, not independently deployed
microservices.
"""
from fastapi import FastAPI
from fastapi.routing import APIRoute, APIRouter

from . import (
    actions,
    admin,
    approve,
    audit,
    auth,
    backup,
    change_requests,
    documents,
    departments,
    formats,
    health,
    my_approvals,
    ocr,
    records,
    record_change_requests,
    repository,
    roles,
    security,
    settings,
    signatures,
    workflow,
)

API_TAGS = [
    {
        "name": "Identity & Access",
        "description": "Sign-in, sessions, and account access.",
    },
    {
        "name": "People & Teams",
        "description": "Manage departments, quality teams, and the people assigned to them.",
    },
    {
        "name": "Template Management",
        "description": "Create, review, publish, and maintain reusable templates.",
    },
    {
        "name": "Document Management",
        "description": "Fill records, manage document files, and track their lifecycle.",
    },
    {
        "name": "Document Repository",
        "description": "Browse approved, filed records by folder, and rename or pin folders.",
    },
    {
        "name": "Approval Workflows",
        "description": "Route documents through review, signatures, and decisions.",
    },
    {
        "name": "Corrective Actions",
        "description": "Track and close follow-up actions.",
    },
    {
        "name": "Audit Trail",
        "description": "Review recorded system and document activity.",
    },
    {
        "name": "Platform Administration",
        "description": "Configure and administer Paperless Factory.",
    },
    {
        "name": "Backup & Recovery",
        "description": "Create, inspect, and restore application backups.",
    },
    {
        "name": "Platform Health",
        "description": "Check service health and operational readiness.",
    },
    {
        "name": "Security",
        "description": "Review and manage security controls.",
    },
]

API_ROUTERS: tuple[tuple[APIRouter, str, str], ...] = (
    (auth.router, "/api/auth", "Identity & Access"),
    (roles.router, "/api/roles", "Identity & Access"),
    (departments.router, "/api/departments", "People & Teams"),
    (settings.router, "/api/settings", "Platform Administration"),
    (health.router, "/api/health", "Platform Health"),
    (backup.router, "/api/backup", "Backup & Recovery"),
    # Must stay ahead of documents.router: that router has a catch-all
    # "/{document_id}" route which would otherwise capture
    # GET /api/documents/repository. The prefix keeps the existing URLs.
    (repository.router, "/api/documents/repository", "Document Repository"),
    (documents.router, "/api/documents", "Document Management"),
    (security.router, "/api/security", "Security"),
    (admin.router, "/api/admin", "Platform Administration"),
    (workflow.router, "/api/workflow", "Approval Workflows"),
    (audit.router, "/api/audit", "Audit Trail"),
    (signatures.router, "/api/signatures", "Approval Workflows"),
    (approve.router, "/api/approve", "Approval Workflows"),
    (formats.router, "/api/formats", "Template Management"),
    (ocr.router, "/api/ocr", "Template Management"),
    (record_change_requests.router, "/api/record-change-requests", "Document Management"),
    (records.router, "/api/records", "Document Management"),
    (my_approvals.router, "/api/my-approvals", "Approval Workflows"),
    (change_requests.router, "/api/change-requests", "Template Management"),
    (actions.router, "/api/actions", "Corrective Actions"),
)


def register_api_routers(app: FastAPI) -> None:
    """Mount routes under exactly one documentation domain.

    An operation-level tag identifies cross-domain endpoints such as team
    management; otherwise it inherits the router's domain. Passing router tags
    to ``include_router`` would append a second tag to those operations.
    """
    for router, prefix, tag in API_ROUTERS:
        for route in router.routes:
            if isinstance(route, APIRoute) and not route.tags:
                route.tags = [tag]
        app.include_router(router, prefix=prefix)