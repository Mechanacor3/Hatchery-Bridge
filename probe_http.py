"""Read-only protocol probe for the deployed loopback MCP server."""
import asyncio

from mcp import Client


async def main():
    expected = {'status', 'run_command', 'get_job', 'cancel_job', 'read_file', 'write_file'}
    # Alternate eras against one process to catch connection lifecycle leakage.
    for mode in ('legacy', '2026-07-28', 'legacy', '2026-07-28'):
        async with Client('http://127.0.0.1:8765/mcp', mode=mode,
                          read_timeout_seconds=15) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == expected
            result = await client.call_tool('status', {})
            assert not result.is_error, result
            print(f'{client.protocol_version}: discovery, six tools, status OK')


if __name__ == '__main__':
    asyncio.run(main())
