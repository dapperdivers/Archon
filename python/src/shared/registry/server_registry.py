"""
MCP Server Registry

This module provides a registry of available MCP servers, including built-in Archon servers
and external servers from the MCP ecosystem. It handles server discovery, capability management,
and configuration templates.
"""

import json
from typing import Any

import logging
mcp_logger = logging.getLogger(__name__)
from .builtin_servers import create_builtin_servers
from .models import MCPServerCapability, MCPServerTemplate


class MCPServerRegistry:
    """Registry for managing MCP server templates and discovery."""

    def __init__(self):
        self.templates: dict[str, MCPServerTemplate] = {}
        self.categories: dict[str, list[str]] = {}
        self._load_builtin_servers()

    def _load_builtin_servers(self):
        """Load built-in server templates."""
        builtin_servers = create_builtin_servers()
        for server in builtin_servers:
            self.register_template(server)

        # Build categories
        self._build_categories()

    def _build_categories(self):
        """Build category index from registered templates."""
        self.categories.clear()

        for template in self.templates.values():
            for capability in template.capabilities:
                category = capability.category
                if category not in self.categories:
                    self.categories[category] = []
                if template.server_id not in self.categories[category]:
                    self.categories[category].append(template.server_id)

    def register_template(self, template: MCPServerTemplate):
        """Register a new server template."""
        self.templates[template.server_id] = template
        mcp_logger.debug(f"Registered MCP server template: {template.server_id}")

    def get_template(self, server_id: str) -> MCPServerTemplate | None:
        """Get a server template by ID."""
        return self.templates.get(server_id)

    def list_templates(self,
                      category: str | None = None,
                      server_type: str | None = None,
                      tags: list[str] | None = None) -> list[MCPServerTemplate]:
        """List server templates with optional filtering."""
        templates = list(self.templates.values())

        if category:
            templates = [
                t for t in templates
                if any(cap.category == category for cap in t.capabilities)
            ]

        if server_type:
            templates = [t for t in templates if t.server_type == server_type]

        if tags:
            templates = [
                t for t in templates
                if any(tag in t.tags for tag in tags)
            ]

        return templates

    def get_categories(self) -> dict[str, list[str]]:
        """Get all capability categories and their associated servers."""
        return self.categories.copy()

    def search_templates(self, query: str) -> list[MCPServerTemplate]:
        """Search templates by name, description, or capabilities."""
        query_lower = query.lower()
        results = []

        for template in self.templates.values():
            # Search in name and description
            if (query_lower in template.name.lower() or
                query_lower in template.description.lower()):
                results.append(template)
                continue

            # Search in capabilities
            for capability in template.capabilities:
                if (query_lower in capability.name.lower() or
                    query_lower in capability.description.lower()):
                    results.append(template)
                    break

            # Search in tags
            if any(query_lower in tag.lower() for tag in template.tags):
                results.append(template)

        return results

    def get_popular_servers(self, limit: int = 10) -> list[MCPServerTemplate]:
        """Get popular/recommended servers."""
        # For now, return servers with specific tags, sorted by type
        popular_tags = ["core", "search", "filesystem", "github", "database"]
        popular_servers = []

        for tag in popular_tags:
            servers = self.list_templates(tags=[tag])
            popular_servers.extend(servers)

        # Remove duplicates while preserving order
        seen = set()
        unique_servers = []
        for server in popular_servers:
            if server.server_id not in seen:
                seen.add(server.server_id)
                unique_servers.append(server)

        return unique_servers[:limit]

    def validate_template(self, template: MCPServerTemplate) -> list[str]:
        """Validate a server template and return any errors."""
        errors = []

        if not template.server_id:
            errors.append("server_id is required")

        if not template.name:
            errors.append("name is required")

        if not template.server_type:
            errors.append("server_type is required")

        if template.server_type in ["npx", "uv"] and not template.package:
            errors.append(f"package is required for {template.server_type} servers")

        if template.server_type == "docker" and not template.command:
            errors.append("command is required for docker servers")

        if template.transport not in ["stdio", "sse", "http"]:
            errors.append("transport must be one of: stdio, sse, http")

        return errors

    def export_registry(self) -> str:
        """Export the registry as JSON."""
        data = {
            "version": "1.0",
            "templates": [
                {
                    "server_id": t.server_id,
                    "name": t.name,
                    "description": t.description,
                    "server_type": t.server_type,
                    "package": t.package,
                    "command": t.command,
                    "default_args": t.default_args,
                    "required_env": t.required_env,
                    "optional_env": t.optional_env,
                    "transport": t.transport,
                    "default_port": t.default_port,
                    "capabilities": [
                        {
                            "name": cap.name,
                            "description": cap.description,
                            "category": cap.category,
                            "parameters": cap.parameters,
                            "examples": cap.examples
                        }
                        for cap in t.capabilities
                    ],
                    "tags": t.tags,
                    "documentation_url": t.documentation_url,
                    "repository_url": t.repository_url,
                    "version": t.version,
                    "author": t.author,
                    "license": t.license
                }
                for t in self.templates.values()
            ]
        }
        return json.dumps(data, indent=2)

    def import_registry(self, json_data: str) -> int:
        """Import templates from JSON data. Returns number of templates imported."""
        try:
            data = json.loads(json_data)
            imported_count = 0

            for template_data in data.get("templates", []):
                # Convert capability data back to objects
                capabilities = []
                for cap_data in template_data.get("capabilities", []):
                    capabilities.append(MCPServerCapability(
                        name=cap_data["name"],
                        description=cap_data["description"],
                        category=cap_data.get("category", "general"),
                        parameters=cap_data.get("parameters", []),
                        examples=cap_data.get("examples", [])
                    ))

                template = MCPServerTemplate(
                    server_id=template_data["server_id"],
                    name=template_data["name"],
                    description=template_data["description"],
                    server_type=template_data["server_type"],
                    package=template_data.get("package"),
                    command=template_data.get("command"),
                    default_args=template_data.get("default_args", []),
                    required_env=template_data.get("required_env", []),
                    optional_env=template_data.get("optional_env", {}),
                    transport=template_data.get("transport", "stdio"),
                    default_port=template_data.get("default_port"),
                    capabilities=capabilities,
                    tags=template_data.get("tags", []),
                    documentation_url=template_data.get("documentation_url"),
                    repository_url=template_data.get("repository_url"),
                    version=template_data.get("version"),
                    author=template_data.get("author"),
                    license=template_data.get("license")
                )

                errors = self.validate_template(template)
                if not errors:
                    self.register_template(template)
                    imported_count += 1
                else:
                    mcp_logger.warning(f"Skipping invalid template {template.server_id}: {errors}")

            self._build_categories()
            return imported_count

        except json.JSONDecodeError as e:
            mcp_logger.error(f"Invalid JSON in registry import: {e}")
            return 0
        except Exception as e:
            mcp_logger.error(f"Error importing registry: {e}")
            return 0

    def get_server_by_package(self, package_name: str) -> MCPServerTemplate | None:
        """Find a server template by package name."""
        for template in self.templates.values():
            if template.package == package_name:
                return template
        return None

    def get_servers_by_capability(self, capability_name: str) -> list[MCPServerTemplate]:
        """Find server templates that provide a specific capability."""
        results = []
        for template in self.templates.values():
            for capability in template.capabilities:
                if capability.name == capability_name:
                    results.append(template)
                    break
        return results

    def get_registry_stats(self) -> dict[str, Any]:
        """Get statistics about the registry."""
        server_types = {}
        transport_types = {}
        total_capabilities = 0

        for template in self.templates.values():
            # Count server types
            server_type = template.server_type
            server_types[server_type] = server_types.get(server_type, 0) + 1

            # Count transport types
            transport = template.transport
            transport_types[transport] = transport_types.get(transport, 0) + 1

            # Count capabilities
            total_capabilities += len(template.capabilities)

        return {
            "total_servers": len(self.templates),
            "server_types": server_types,
            "transport_types": transport_types,
            "total_capabilities": total_capabilities,
            "categories": len(self.categories),
            "category_breakdown": {cat: len(servers) for cat, servers in self.categories.items()}
        }


# Global registry instance
_registry: MCPServerRegistry | None = None


def get_mcp_registry() -> MCPServerRegistry:
    """Get the global MCP server registry instance."""
    global _registry
    if _registry is None:
        _registry = MCPServerRegistry()
    return _registry
