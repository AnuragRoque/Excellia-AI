"""Live end-to-end: spawn the real MCP server over stdio, let it
auto-start the core API (detached), and call a tool. This is the Stage A
proof and it guards the Windows detached-spawn fix from regression.

Opt-in — it boots uvicorn + pandas + sklearn, so it's slow and needs a
free port. Enable with:  EXCELLIA_RUN_MCP_IT=1 pytest
"""

import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("EXCELLIA_RUN_MCP_IT") != "1",
    reason="set EXCELLIA_RUN_MCP_IT=1 to run the live MCP integration test",
)


def test_stdio_server_autostarts_api_and_profiles():
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # dedicated port so we never clobber a developer's warm API on 8000
    port = "8137"
    env = dict(os.environ, EXCELLIA_PORT=port, EXCELLIA_API=f"http://127.0.0.1:{port}")

    async def run() -> str:
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "excellia.mcp_server.server"],
            env=env,
            cwd=os.getcwd(),
        )
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                assert names >= {"profile_sheet", "validate", "detect_anomalies",
                                 "reconcile", "ask_data", "transform_preview",
                                 "transform_apply", "run_recipe", "save_ruleset",
                                 "export_report", "job_status"}
                result = await session.call_tool(
                    "profile_sheet", {"file_path": "examples/messy_vendors.xlsx"}
                )
                return "".join(b.text for b in result.content if getattr(b, "text", None))

    try:
        out = asyncio.run(asyncio.wait_for(run(), timeout=90))
    finally:
        # best-effort: reap the detached API we started on our test port
        if os.name == "nt":
            os.system(
                'powershell -NoProfile -Command "Get-CimInstance Win32_Process '
                "-Filter \\\"Name='python.exe'\\\" | Where-Object "
                f"{{$_.CommandLine -match 'EXCELLIA_PORT.*{port}' -or "
                "$_.CommandLine -match 'excellia.api.main'}} | ForEach-Object "
                '{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"'
            )

    assert '"row_count": 50' in out
    assert '"error"' not in out
