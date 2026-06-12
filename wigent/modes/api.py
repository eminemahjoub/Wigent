"""
Role: API and interface design mode with contract-first principles.
Author: Wigent AI
Version: 1.0.0

Enforces Hyrum's Law, One-Version Rule, explicit error semantics,
and backward compatibility. Every API change is a breaking change
unless proven otherwise.

Usage:
    from wigent.modes.api import APIMode, APIContract

    mode = APIMode(llm_client)

    contract = mode.design_contract(
        resource="User",
        operations=["create", "read", "update", "delete", "list"],
        constraints=["idempotent create", "soft delete"]
    )

    openapi_spec = mode.generate_openapi(contract)
    breaking = mode.detect_breaking_changes(old_contract, new_contract)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wigent.models.base_model import BaseModel


class HTTPMethod(Enum):
    """Standard HTTP methods with idempotency and safety properties."""
    GET = ("GET", True, True)
    POST = ("POST", False, False)
    PUT = ("PUT", False, True)
    PATCH = ("PATCH", False, False)
    DELETE = ("DELETE", False, True)
    HEAD = ("HEAD", True, True)
    OPTIONS = ("OPTIONS", True, True)


class ErrorCategory(Enum):
    """Standard error categories with HTTP status mappings."""
    VALIDATION = (400, "client", "Request syntax or semantics invalid")
    AUTHENTICATION = (401, "client", "Credentials missing or invalid")
    AUTHORIZATION = (403, "client", "Insufficient permissions")
    NOT_FOUND = (404, "client", "Resource does not exist")
    CONFLICT = (409, "client", "Resource state conflict")
    RATE_LIMIT = (429, "client", "Too many requests")
    SERVER_ERROR = (500, "server", "Unexpected server error")
    UNAVAILABLE = (503, "server", "Service temporarily unavailable")

    def __init__(self, status: int, blame: str, description: str):
        self.status = status
        self.blame = blame
        self.description = description


@dataclass
class APIField:
    """A single field in an API schema."""

    name: str
    type: str
    required: bool = True
    description: str = ""
    example: str | None = None
    deprecated: bool = False
    nullable: bool = False
    constraints: dict = field(default_factory=dict)


@dataclass
class APIOperation:
    """A single API operation with full contract definition."""

    name: str
    method: HTTPMethod
    path: str
    summary: str
    description: str = ""
    parameters: list[APIField] = field(default_factory=list)
    request_body: APIField | None = None
    responses: dict[int, APIField] = field(default_factory=dict)
    errors: dict[ErrorCategory, str] = field(default_factory=dict)
    rate_limit: str | None = None
    idempotency_key: bool = False
    deprecated: bool = False
    since_version: str = "1.0.0"


@dataclass
class APIContract:
    """Complete API contract for a resource."""

    name: str
    version: str
    base_path: str
    operations: list[APIOperation] = field(default_factory=list)
    schemas: dict[str, list[APIField]] = field(default_factory=dict)
    security: list[str] = field(default_factory=list)
    changelog: list[dict] = field(default_factory=list)

    def to_openapi(self) -> dict:
        """Convert to OpenAPI 3.1 specification."""
        return APIMode._contract_to_openapi(self)


class BreakingChange(Enum):
    """Types of breaking changes with severity."""
    FIELD_REMOVED = auto()
    FIELD_TYPE_CHANGED = auto()
    FIELD_REQUIRED_ADDED = auto()
    FIELD_NULLABLE_REMOVED = auto()
    ENDPOINT_REMOVED = auto()
    ENDPOINT_PATH_CHANGED = auto()
    METHOD_CHANGED = auto()
    RESPONSE_STATUS_REMOVED = auto()
    ERROR_FORMAT_CHANGED = auto()
    AUTH_CHANGED = auto()
    RATE_LIMIT_TIGHTENED = auto()


@dataclass
class ChangeReport:
    """Report of changes between two API versions."""

    breaking: list[tuple[BreakingChange, str, str]] = field(default_factory=list)
    additive: list[tuple[str, str]] = field(default_factory=list)
    deprecated: list[tuple[str, str]] = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        return len(self.breaking) == 0

    def to_markdown(self) -> str:
        """Render as markdown report."""
        lines = ["# API Change Report", ""]

        if self.breaking:
            lines.extend([
                f"## Breaking Changes ({len(self.breaking)})",
                "",
                "| Type | Location | Details |",
                "|------|----------|---------|",
            ])
            for change_type, location, details in self.breaking:
                lines.append(f"| {change_type.name} | {location} | {details} |")
            lines.append("")
        else:
            lines.extend(["## No Breaking Changes", ""])

        if self.additive:
            lines.extend([
                f"## Additive Changes ({len(self.additive)})",
                "",
                "| Location | Details |",
                "|----------|---------|",
            ])
            for location, details in self.additive:
                lines.append(f"| {location} | {details} |")
            lines.append("")

        if self.deprecated:
            lines.extend([
                f"## Deprecations ({len(self.deprecated)})",
                "",
                "| Location | Details |",
                "|----------|---------|",
            ])
            for location, details in self.deprecated:
                lines.append(f"| {location} | {details} |")
            lines.append("")

        return "\n".join(lines)


class APIMode:
    """
    API design mode with contract-first principles.

    Principles:
    1. Contract First -- OpenAPI before implementation
    2. Hyrum's Law -- Every observable behavior will be depended upon
    3. One-Version Rule -- Never maintain multiple API versions
    4. Explicit Errors -- Every error has a code, message, and remediation
    5. Backward Compatible -- Additive only; breaking changes require new resource
    """

    HYRUN_OBSERVABLES = [
        "Response field order",
        "Error message text",
        "Timestamp precision",
        "Pagination defaults",
        "Whitespace in JSON",
        "Header case sensitivity",
        "Status phrase text",
        "Redirect behavior",
        "Cache-Control defaults",
        "Rate limit reset timing",
    ]

    VERSION_EVOLUTION = {
        "additive": "Add fields, endpoints, optional parameters",
        "expandable": "Use extensible enums, discriminator patterns",
        "soft_deprecate": "Mark deprecated, keep functional, monitor usage",
        "hard_deprecate": "Only after 12+ months with active migration path",
        "sunset": "Never remove without successor; redirect if possible",
    }

    def __init__(
        self,
        llm_client: BaseModel,
        base_path: str = "/api/v1",
        strict_mode: bool = True,
    ) -> None:
        self.llm = llm_client
        self.base_path = base_path
        self.strict_mode = strict_mode
        self._contracts: dict[str, APIContract] = {}
        self._change_history: list[ChangeReport] = []

    def design_contract(
        self,
        resource: str,
        operations: list[str],
        constraints: list[str] | None = None,
        existing_schema: dict | None = None,
    ) -> APIContract:
        """
        Design a complete API contract from requirements.

        Args:
            resource: Resource name (e.g., "User", "Order")
            operations: CRUD operations + custom (e.g., ["create", "read", "list"])
            constraints: Special requirements (e.g., ["idempotent create", "soft delete"])
            existing_schema: Existing schema to extend (additive only)

        Returns:
            APIContract with full OpenAPI-compatible definition
        """
        prompt = self._build_design_prompt(
            resource=resource,
            operations=operations,
            constraints=constraints or [],
            existing_schema=existing_schema,
        )

        response = self.llm.generate(prompt, temperature=0.2, max_tokens=4000)

        contract = self._parse_contract_response(response, resource)

        self._validate_contract(contract)

        self._contracts[resource] = contract
        return contract

    def generate_openapi(self, contract: APIContract) -> dict:
        """
        Generate OpenAPI 3.1 specification from contract.

        Returns complete, validatable spec.
        """
        return contract.to_openapi()

    def detect_breaking_changes(
        self,
        old_contract: APIContract,
        new_contract: APIContract,
    ) -> ChangeReport:
        """
        Detect breaking changes between two contract versions.

        Hyrum's Law: Any observable change is potentially breaking.
        """
        report = ChangeReport()

        old_ops = {op.name: op for op in old_contract.operations}
        new_ops = {op.name: op for op in new_contract.operations}

        for name, old_op in old_ops.items():
            if name not in new_ops:
                report.breaking.append((
                    BreakingChange.ENDPOINT_REMOVED,
                    f"{old_op.method.value[0]} {old_op.path}",
                    f"Operation '{name}' was removed"
                ))
                continue

            new_op = new_ops[name]

            if old_op.method != new_op.method:
                report.breaking.append((
                    BreakingChange.METHOD_CHANGED,
                    name,
                    f"Method changed from {old_op.method.name} to {new_op.method.name}"
                ))

            if old_op.path != new_op.path:
                report.breaking.append((
                    BreakingChange.ENDPOINT_PATH_CHANGED,
                    name,
                    f"Path changed from {old_op.path} to {new_op.path}"
                ))

        for schema_name, old_fields in old_contract.schemas.items():
            if schema_name not in new_contract.schemas:
                continue

            new_fields = {f.name: f for f in new_contract.schemas[schema_name]}
            old_field_map = {f.name: f for f in old_fields}

            for field_name, old_field in old_field_map.items():
                if field_name not in new_fields:
                    report.breaking.append((
                        BreakingChange.FIELD_REMOVED,
                        f"{schema_name}.{field_name}",
                        "Field was removed"
                    ))
                    continue

                new_field = new_fields[field_name]

                if old_field.type != new_field.type:
                    report.breaking.append((
                        BreakingChange.FIELD_TYPE_CHANGED,
                        f"{schema_name}.{field_name}",
                        f"Type changed from {old_field.type} to {new_field.type}"
                    ))

                if not old_field.required and new_field.required:
                    report.breaking.append((
                        BreakingChange.FIELD_REQUIRED_ADDED,
                        f"{schema_name}.{field_name}",
                        "Field became required"
                    ))

                if old_field.nullable and not new_field.nullable:
                    report.breaking.append((
                        BreakingChange.FIELD_NULLABLE_REMOVED,
                        f"{schema_name}.{field_name}",
                        "Field no longer nullable"
                    ))

        for name in new_ops:
            if name not in old_ops:
                report.additive.append((name, "New operation added"))

        for schema_name, new_fields in new_contract.schemas.items():
            if schema_name not in old_contract.schemas:
                report.additive.append((schema_name, "New schema added"))
                continue
            old_field_names = {f.name for f in old_contract.schemas[schema_name]}
            for field in new_fields:
                if field.name not in old_field_names:
                    report.additive.append((
                        f"{schema_name}.{field.name}",
                        "New field added"
                    ))

        self._change_history.append(report)
        return report

    def validate_request(
        self,
        contract: APIContract,
        operation: str,
        request: dict,
    ) -> tuple[bool, list[dict]]:
        """
        Validate a request against contract.

        Returns (is_valid, list_of_errors).
        """
        op = next((o for o in contract.operations if o.name == operation), None)
        if not op:
            return False, [{"error": "Operation not found"}]

        errors = []

        for param in op.parameters:
            if param.required and param.name not in request.get("parameters", {}):
                errors.append({
                    "field": param.name,
                    "error": "required",
                    "message": f"Parameter '{param.name}' is required",
                })

        if op.request_body and op.request_body.required:
            body = request.get("body")
            if body is None:
                errors.append({
                    "field": "body",
                    "error": "required",
                    "message": "Request body is required",
                })
            else:
                for field in contract.schemas.get(op.request_body.type, []):
                    if field.required and field.name not in body:
                        errors.append({
                            "field": field.name,
                            "error": "required",
                            "message": f"Field '{field.name}' is required",
                        })

        return len(errors) == 0, errors

    def generate_error_response(
        self,
        category: ErrorCategory,
        message: str,
        remediation: str,
        request_id: str | None = None,
    ) -> dict:
        """
        Generate standardized error response.

        Every error includes:
        - Machine-readable code
        - Human-readable message
        - Remediation steps
        - Request ID for tracing
        """
        return {
            "error": {
                "code": f"{category.name}_{self._snake_to_camel(category.name)}",
                "status": category.status,
                "message": message,
                "remediation": remediation,
                "category": category.blame,
                "request_id": request_id or self._generate_request_id(),
                "documentation": f"/docs/errors/{category.name.lower()}",
            }
        }

    def get_hyrum_warnings(self, contract: APIContract) -> list[str]:
        """
        Generate warnings about observable behaviors that will become contracts.

        Per Hyrum's Law.
        """
        warnings = []

        for op in contract.operations:
            if op.responses:
                for status, schema in op.responses.items():
                    warnings.append(
                        f"{op.name}: Response fields for {status} will be depended on in order. "
                        f"Use JSON objects, not arrays, for stability."
                    )

            if op.errors:
                warnings.append(
                    f"{op.name}: Error messages will be parsed by clients. "
                    f"Keep stable or add machine-readable error codes."
                )

            if "list" in op.name.lower() or "search" in op.name.lower():
                warnings.append(
                    f"{op.name}: Pagination defaults (page size, max) will become expected. "
                    f"Document explicitly and never tighten without notice."
                )

        return warnings

    def get_versioning_strategy(self) -> dict:
        """
        Return One-Version Rule strategy document.

        How to evolve without maintaining multiple versions.
        """
        return {
            "principle": "One-Version Rule",
            "rule": "Never maintain multiple API versions simultaneously",
            "rationale": "Version explosion creates maintenance burden and confusion",
            "strategies": self.VERSION_EVOLUTION,
            "migration_path": {
                "notification": "6 months advance notice for breaking changes",
                "deprecation": "12 months with Sunset header",
                "removal": "Only after <1% traffic and active successor",
            },
            "headers": {
                "Sunset": "RFC 8594 -- deprecation timeline",
                "Deprecation": "RFC 9745 -- feature deprecation",
                "Link": "RFC 8288 -- relation to successor",
            },
        }

    # =================================================================
    # Internal Methods
    # =================================================================

    def _build_design_prompt(
        self,
        resource: str,
        operations: list[str],
        constraints: list[str],
        existing_schema: dict | None,
    ) -> str:
        """Build LLM prompt for API contract design."""
        op_templates = {
            "create": {
                "method": "POST",
                "path": f"/{resource.lower()}s",
                "summary": f"Create a new {resource}",
            },
            "read": {
                "method": "GET",
                "path": f"/{resource.lower()}s/{{id}}",
                "summary": f"Get a {resource} by ID",
            },
            "update": {
                "method": "PUT",
                "path": f"/{resource.lower()}s/{{id}}",
                "summary": f"Update a {resource}",
            },
            "patch": {
                "method": "PATCH",
                "path": f"/{resource.lower()}s/{{id}}",
                "summary": f"Partially update a {resource}",
            },
            "delete": {
                "method": "DELETE",
                "path": f"/{resource.lower()}s/{{id}}",
                "summary": f"Delete a {resource}",
            },
            "list": {
                "method": "GET",
                "path": f"/{resource.lower()}s",
                "summary": f"List {resource}s",
            },
        }

        return f"""Design a REST API contract for {resource}.

## Operations Required
{chr(10).join(f"- {op}: {op_templates.get(op, {}).get('summary', op)}" for op in operations)}

## Constraints
{chr(10).join(f"- {c}" for c in constraints) if constraints else "- Standard REST conventions"}

## Existing Schema (Extend Only)
{json.dumps(existing_schema, indent=2) if existing_schema else "None"}

## Rules
1. Contract-first: Design OpenAPI-compatible schema
2. Every operation has explicit error responses
3. Use standard HTTP methods correctly (GET safe/idempotent, POST neither, etc.)
4. Include rate limits for all mutating operations
5. Idempotency keys for POST/PUT/PATCH
6. Soft delete preferred over hard delete
7. Pagination for list operations (cursor-based)
8. Consistent error format across all endpoints
9. Hyrum's Law: Document all observable behaviors
10. One-Version Rule: Design for additive evolution

## Output Format
Return JSON:

```json
{{
  "name": "{resource}",
  "version": "1.0.0",
  "base_path": "/api/v1",
  "operations": [
    {{
      "name": "createUser",
      "method": "POST",
      "path": "/users",
      "summary": "...",
      "parameters": [...],
      "request_body": {{...}},
      "responses": {{"201": {{...}}, "400": {{...}}}},
      "errors": {{"VALIDATION": "...", "CONFLICT": "..."}},
      "rate_limit": "100/minute",
      "idempotency_key": true
    }}
  ],
  "schemas": {{
    "User": [
      {{"name": "id", "type": "uuid", "required": true, "description": "Unique identifier"}},
      ...
    ]
  }}
}}
```
"""

    def _parse_contract_response(self, response: str, resource: str) -> APIContract:
        """Parse LLM response into APIContract."""
        import re

        json_match = re.search(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in response")

        data = json.loads(json_match.group(1))

        operations = []
        for op_data in data.get("operations", []):
            method = HTTPMethod[op_data["method"].upper()]
            operations.append(APIOperation(
                name=op_data["name"],
                method=method,
                path=op_data["path"],
                summary=op_data["summary"],
                description=op_data.get("description", ""),
                parameters=[
                    APIField(**p) for p in op_data.get("parameters", [])
                ],
                request_body=APIField(**op_data["request_body"]) if op_data.get("request_body") else None,
                responses={
                    int(k): APIField(**v) for k, v in op_data.get("responses", {}).items()
                },
                errors={
                    ErrorCategory[k]: v for k, v in op_data.get("errors", {}).items()
                },
                rate_limit=op_data.get("rate_limit"),
                idempotency_key=op_data.get("idempotency_key", False),
            ))

        schemas = {
            name: [APIField(**f) for f in fields]
            for name, fields in data.get("schemas", {}).items()
        }

        return APIContract(
            name=data.get("name", resource),
            version=data.get("version", "1.0.0"),
            base_path=data.get("base_path", "/api/v1"),
            operations=operations,
            schemas=schemas,
        )

    def _validate_contract(self, contract: APIContract) -> None:
        """Validate contract against design principles."""
        if self.strict_mode:
            for op in contract.operations:
                if not op.errors:
                    raise ValueError(
                        f"Operation {op.name} missing error definitions. "
                        f"Every operation must document failure modes."
                    )

                if op.method in (HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.PATCH, HTTPMethod.DELETE):
                    if not op.rate_limit:
                        raise ValueError(
                            f"Mutating operation {op.name} missing rate limit"
                        )

    @staticmethod
    def _contract_to_openapi(contract: APIContract) -> dict:
        """Convert APIContract to OpenAPI 3.1 specification."""
        paths = {}

        for op in contract.operations:
            if op.path not in paths:
                paths[op.path] = {}

            responses = {}
            for status, schema in op.responses.items():
                responses[str(status)] = {
                    "description": schema.description or "Success",
                    "content": {
                        "application/json": {
                            "schema": APIMode._field_to_schema(schema)
                        }
                    }
                }

            for category, message in op.errors.items():
                status = str(category.status)
                if status not in responses:
                    responses[status] = {
                        "description": category.description,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "error": {
                                            "type": "object",
                                            "properties": {
                                                "code": {"type": "string"},
                                                "message": {"type": "string"},
                                                "remediation": {"type": "string"},
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

            path_item = {
                "summary": op.summary,
                "description": op.description,
                "operationId": op.name,
                "parameters": [
                    {
                        "name": p.name,
                        "in": "path" if f"{{{p.name}}}" in op.path else "query",
                        "required": p.required,
                        "schema": {"type": p.type},
                        "description": p.description,
                    }
                    for p in op.parameters
                ],
                "responses": responses,
            }

            if op.request_body:
                path_item["requestBody"] = {
                    "required": op.request_body.required,
                    "content": {
                        "application/json": {
                            "schema": APIMode._field_to_schema(op.request_body)
                        }
                    }
                }

            paths[op.path][op.method.value[0].lower()] = path_item

        schemas = {}
        for name, fields in contract.schemas.items():
            schemas[name] = {
                "type": "object",
                "properties": {
                    f.name: APIMode._field_to_schema(f)
                    for f in fields
                },
                "required": [f.name for f in fields if f.required],
            }

        return {
            "openapi": "3.1.0",
            "info": {
                "title": f"{contract.name} API",
                "version": contract.version,
                "description": f"Contract-first API for {contract.name}",
            },
            "paths": paths,
            "components": {
                "schemas": schemas,
            },
        }

    @staticmethod
    def _field_to_schema(field: APIField) -> dict:
        """Convert APIField to OpenAPI schema."""
        schema = {
            "type": field.type,
            "description": field.description,
        }

        if field.example:
            schema["example"] = field.example

        if field.nullable:
            schema["nullable"] = True

        if field.deprecated:
            schema["deprecated"] = True

        if field.constraints:
            for key, value in field.constraints.items():
                if key in ("minimum", "maximum", "minLength", "maxLength", "pattern", "enum"):
                    schema[key] = value

        return schema

    def _snake_to_camel(self, text: str) -> str:
        """Convert SNAKE_CASE to camelCase."""
        words = text.lower().split("_")
        return words[0] + "".join(w.capitalize() for w in words[1:])

    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        import uuid
        return str(uuid.uuid4())[:8]
