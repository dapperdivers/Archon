"""
Built-in MCP Server Definitions

This module contains the definitions for popular and built-in MCP servers.
"""


from .models import MCPServerCapability, MCPServerTemplate


def create_builtin_servers() -> list[MCPServerTemplate]:
    """Create all built-in server templates."""

    servers = []

    # Archon Core Server
    archon_server = MCPServerTemplate(
        server_id="archon-core",
        name="Archon Core",
        description="Core Archon MCP server with RAG, projects, and knowledge management",
        server_type="archon",
        transport="sse",
        default_port=8051,
        capabilities=[
            MCPServerCapability(
                name="perform_rag_query",
                description="Perform RAG queries against the knowledge base",
                category="knowledge",
                parameters=[
                    {"name": "query", "type": "string", "required": True},
                    {"name": "match_count", "type": "integer", "default": 5}
                ]
            ),
            MCPServerCapability(
                name="search_code_examples",
                description="Search for code examples in the knowledge base",
                category="knowledge",
                parameters=[
                    {"name": "query", "type": "string", "required": True},
                    {"name": "match_count", "type": "integer", "default": 3}
                ]
            ),
            MCPServerCapability(
                name="manage_project",
                description="Create and manage projects",
                category="project",
                parameters=[
                    {"name": "action", "type": "string", "required": True},
                    {"name": "project_data", "type": "object", "required": False}
                ]
            ),
            MCPServerCapability(
                name="manage_task",
                description="Create and manage tasks within projects",
                category="project",
                parameters=[
                    {"name": "action", "type": "string", "required": True},
                    {"name": "task_data", "type": "object", "required": False}
                ]
            )
        ],
        tags=["archon", "rag", "knowledge", "projects", "core"],
        documentation_url="https://docs.anthropic.com/en/docs/claude-code",
        author="Anthropic",
        license="MIT"
    )
    servers.append(archon_server)

    # Popular NPX Servers
    brave_search = MCPServerTemplate(
        server_id="brave-search",
        name="Brave Search",
        description="Search the web using Brave Search API",
        server_type="npx",
        package="@modelcontextprotocol/server-brave-search",
        required_env=["BRAVE_API_KEY"],
        transport="stdio",
        capabilities=[
            MCPServerCapability(
                name="brave_web_search",
                description="Search the web using Brave Search",
                category="search",
                parameters=[
                    {"name": "query", "type": "string", "required": True},
                    {"name": "count", "type": "integer", "default": 10}
                ]
            )
        ],
        tags=["search", "web", "brave", "npx"],
        documentation_url="https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search",
        repository_url="https://github.com/modelcontextprotocol/servers",
        author="Model Context Protocol Team",
        license="MIT"
    )
    servers.append(brave_search)

    filesystem_server = MCPServerTemplate(
        server_id="filesystem",
        name="Filesystem",
        description="Read and write files on the local filesystem",
        server_type="npx",
        package="@modelcontextprotocol/server-filesystem",
        transport="stdio",
        capabilities=[
            MCPServerCapability(
                name="read_file",
                description="Read the contents of a file",
                category="filesystem",
                parameters=[
                    {"name": "path", "type": "string", "required": True}
                ]
            ),
            MCPServerCapability(
                name="write_file",
                description="Write content to a file",
                category="filesystem",
                parameters=[
                    {"name": "path", "type": "string", "required": True},
                    {"name": "content", "type": "string", "required": True}
                ]
            ),
            MCPServerCapability(
                name="list_directory",
                description="List files and directories",
                category="filesystem",
                parameters=[
                    {"name": "path", "type": "string", "required": True}
                ]
            )
        ],
        tags=["filesystem", "files", "npx"],
        documentation_url="https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
        repository_url="https://github.com/modelcontextprotocol/servers",
        author="Model Context Protocol Team",
        license="MIT"
    )
    servers.append(filesystem_server)

    github_server = MCPServerTemplate(
        server_id="github",
        name="GitHub",
        description="Interact with GitHub repositories and issues",
        server_type="npx",
        package="@modelcontextprotocol/server-github",
        required_env=["GITHUB_PERSONAL_ACCESS_TOKEN"],
        transport="stdio",
        capabilities=[
            MCPServerCapability(
                name="create_or_update_file",
                description="Create or update a file in a GitHub repository",
                category="github",
                parameters=[
                    {"name": "owner", "type": "string", "required": True},
                    {"name": "repo", "type": "string", "required": True},
                    {"name": "path", "type": "string", "required": True},
                    {"name": "content", "type": "string", "required": True}
                ]
            ),
            MCPServerCapability(
                name="search_repositories",
                description="Search for GitHub repositories",
                category="github",
                parameters=[
                    {"name": "query", "type": "string", "required": True}
                ]
            ),
            MCPServerCapability(
                name="create_issue",
                description="Create a new issue in a repository",
                category="github",
                parameters=[
                    {"name": "owner", "type": "string", "required": True},
                    {"name": "repo", "type": "string", "required": True},
                    {"name": "title", "type": "string", "required": True},
                    {"name": "body", "type": "string", "required": False}
                ]
            )
        ],
        tags=["github", "git", "repositories", "npx"],
        documentation_url="https://github.com/modelcontextprotocol/servers/tree/main/src/github",
        repository_url="https://github.com/modelcontextprotocol/servers",
        author="Model Context Protocol Team",
        license="MIT"
    )
    servers.append(github_server)

    postgres_server = MCPServerTemplate(
        server_id="postgres",
        name="PostgreSQL",
        description="Connect to and query PostgreSQL databases",
        server_type="npx",
        package="@modelcontextprotocol/server-postgres",
        required_env=["POSTGRES_CONNECTION_STRING"],
        transport="stdio",
        capabilities=[
            MCPServerCapability(
                name="query",
                description="Execute a SQL query",
                category="database",
                parameters=[
                    {"name": "sql", "type": "string", "required": True}
                ]
            ),
            MCPServerCapability(
                name="list_tables",
                description="List all tables in the database",
                category="database"
            ),
            MCPServerCapability(
                name="describe_table",
                description="Get the schema for a specific table",
                category="database",
                parameters=[
                    {"name": "table_name", "type": "string", "required": True}
                ]
            )
        ],
        tags=["database", "postgres", "sql", "npx"],
        documentation_url="https://github.com/modelcontextprotocol/servers/tree/main/src/postgres",
        repository_url="https://github.com/modelcontextprotocol/servers",
        author="Model Context Protocol Team",
        license="MIT"
    )
    servers.append(postgres_server)

    # Playwright Server
    playwright_server = MCPServerTemplate(
        server_id="playwright",
        name="Playwright",
        description="Browser automation and web testing with Playwright",
        server_type="npx",
        package="@modelcontextprotocol/server-playwright",
        transport="stdio",
        capabilities=[
            MCPServerCapability(
                name="navigate",
                description="Navigate to a URL",
                category="browser",
                parameters=[
                    {"name": "url", "type": "string", "required": True}
                ]
            ),
            MCPServerCapability(
                name="click",
                description="Click on an element",
                category="browser",
                parameters=[
                    {"name": "selector", "type": "string", "required": True}
                ]
            ),
            MCPServerCapability(
                name="fill",
                description="Fill a form field",
                category="browser",
                parameters=[
                    {"name": "selector", "type": "string", "required": True},
                    {"name": "text", "type": "string", "required": True}
                ]
            ),
            MCPServerCapability(
                name="screenshot",
                description="Take a screenshot of the page",
                category="browser",
                parameters=[
                    {"name": "path", "type": "string", "required": False}
                ]
            )
        ],
        tags=["browser", "automation", "testing", "playwright", "npx"],
        documentation_url="https://github.com/modelcontextprotocol/servers/tree/main/src/playwright",
        repository_url="https://github.com/modelcontextprotocol/servers",
        author="Model Context Protocol Team",
        license="MIT"
    )
    servers.append(playwright_server)

    # Popular UV Servers (Python-based)
    fetch_server = MCPServerTemplate(
        server_id="fetch",
        name="Web Fetch",
        description="Fetch web pages and extract content",
        server_type="uv",
        package="mcp-server-fetch",
        transport="stdio",
        capabilities=[
            MCPServerCapability(
                name="fetch",
                description="Fetch content from a URL",
                category="web",
                parameters=[
                    {"name": "url", "type": "string", "required": True},
                    {"name": "headers", "type": "object", "required": False}
                ]
            )
        ],
        tags=["web", "fetch", "http", "uv", "python"],
        author="MCP Community",
        license="MIT"
    )
    servers.append(fetch_server)

    # Git Server
    git_server = MCPServerTemplate(
        server_id="git",
        name="Git",
        description="Git repository operations and version control",
        server_type="npx",
        package="@modelcontextprotocol/server-git",
        transport="stdio",
        capabilities=[
            MCPServerCapability(
                name="git_status",
                description="Get git repository status",
                category="git"
            ),
            MCPServerCapability(
                name="git_diff",
                description="Show git diff",
                category="git",
                parameters=[
                    {"name": "path", "type": "string", "required": False}
                ]
            ),
            MCPServerCapability(
                name="git_commit",
                description="Create a git commit",
                category="git",
                parameters=[
                    {"name": "message", "type": "string", "required": True}
                ]
            )
        ],
        tags=["git", "version-control", "repositories", "npx"],
        documentation_url="https://github.com/modelcontextprotocol/servers/tree/main/src/git",
        repository_url="https://github.com/modelcontextprotocol/servers",
        author="Model Context Protocol Team",
        license="MIT"
    )
    servers.append(git_server)

    return servers


def get_server_by_category(category: str) -> list[MCPServerTemplate]:
    """Get all built-in servers that provide capabilities in a specific category."""
    servers = create_builtin_servers()
    matching_servers = []

    for server in servers:
        for capability in server.capabilities:
            if capability.category == category:
                matching_servers.append(server)
                break

    return matching_servers


def get_popular_servers() -> list[MCPServerTemplate]:
    """Get the most popular/recommended servers."""
    servers = create_builtin_servers()

    # Define popularity order
    popular_order = [
        "archon-core",
        "brave-search",
        "filesystem",
        "github",
        "postgres",
        "playwright",
        "git",
        "fetch"
    ]

    # Sort servers by popularity
    popularity_map = {sid: i for i, sid in enumerate(popular_order)}
    servers.sort(key=lambda s: popularity_map.get(s.server_id, 999))

    return servers
