import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ['HATCHERY_WORKSPACE'] = tempfile.mkdtemp(prefix='hatchery-work-')
os.environ['HATCHERY_STATE'] = tempfile.mkdtemp(prefix='hatchery-state-')
import server

class BridgeTests(unittest.TestCase):
    def wait_job(self, jid):
        import time
        for _ in range(100):
            j = server.get_job(jid)
            if j['status'] not in ('running', 'queued'):
                return j
            time.sleep(.1)
        self.fail('Job did not finish')

    def test_file_roundtrip_conflict_and_escape(self):
        r = server.write_file('test.txt','hello','missing')
        self.assertEqual(server.read_file('test.txt')['content'],'hello')
        with self.assertRaises(server.ToolError):
            server.write_file('test.txt','clobber','missing')
        server.write_file('test.txt','next',r['sha256'])
        with self.assertRaises(server.ToolError):
            server.read_file('../outside')
        (server.ROOT/'link').symlink_to('/etc/passwd')
        with self.assertRaises(server.ToolError):
            server.read_file('link')

    def test_command_and_dedup(self):
        r = server.run_command("printf 'hello'; printf 'error' >&2",'same')
        j = self.wait_job(r['job_id'])
        self.assertEqual(j['output'],'helloerror')
        self.assertEqual(j['exit_code'],0)
        self.assertEqual(server.run_command("printf 'hello'; printf 'error' >&2",'same')['job_id'],r['job_id'])
        fast = server.run_command("printf fast", 'fast-inline')
        if fast['status'] == 'succeeded':
            self.assertEqual(fast['output'], 'fast')
        with self.assertRaises(server.ToolError):
            server.run_command('echo different','same')

    def test_coding_assistant_uses_configured_cli(self):
        fake = server.ROOT/'fake-codex'
        fake.write_text("#!/bin/sh\nprintf 'CODEX_HOME:%s\\n' \"${CODEX_HOME-unset}\"\nfor arg in \"$@\"; do printf 'ARG:%s\\n' \"$arg\"; done\nprintf 'PROMPT:'\ncat\n")
        fake.chmod(0o755)
        old_bin = os.environ.get('HATCHERY_CODEX_BIN')
        old_model = os.environ.get('HATCHERY_CODEX_MODEL')
        old_home = os.environ.get('CODEX_HOME')
        try:
            os.environ['HATCHERY_CODEX_BIN'] = str(fake)
            os.environ['HATCHERY_CODEX_MODEL'] = 'configured-model'
            os.environ['CODEX_HOME'] = str(server.ROOT/'unsupported-custom-codex-home')
            prompt = "--help\nreview 'quotes' ; $(not-shell)"
            r = server.coding_assistant(prompt, 'coding-route',
                model='default', read_only=True, timeout_seconds=30)
            j = self.wait_job(r['job_id'])
            self.assertEqual(j['exit_code'], 0)
            self.assertIn('CODEX_HOME:unset\n', j['output'])
            self.assertIn('ARG:--ask-for-approval\nARG:never\n', j['output'])
            self.assertIn('ARG:read-only\n', j['output'])
            self.assertIn('ARG:configured-model\n', j['output'])
            self.assertIn('ARG:exec\nARG:--color\nARG:never\nARG:-\n', j['output'])
            self.assertTrue(j['output'].endswith('PROMPT:'+prompt))

            # Exact retries recover from the durable request before mutable CLI
            # discovery/defaults are consulted again.
            os.environ['HATCHERY_CODEX_BIN'] = str(server.ROOT/'gone-codex')
            retry = server.coding_assistant(prompt, 'coding-route',
                model='default', read_only=True, timeout_seconds=30)
            self.assertEqual(retry['job_id'], r['job_id'])
            self.assertTrue(retry['deduplicated'])
            with self.assertRaises(server.ToolError):
                server.coding_assistant('different', 'coding-route',
                    model='default', read_only=True, timeout_seconds=30)
            with self.assertRaises(server.ToolError):
                server.coding_assistant('x', 'bad-assistant', assistant='bogus')
        finally:
            if old_bin is None:
                os.environ.pop('HATCHERY_CODEX_BIN', None)
            else:
                os.environ['HATCHERY_CODEX_BIN'] = old_bin
            if old_model is None:
                os.environ.pop('HATCHERY_CODEX_MODEL', None)
            else:
                os.environ['HATCHERY_CODEX_MODEL'] = old_model
            if old_home is None:
                os.environ.pop('CODEX_HOME', None)
            else:
                os.environ['CODEX_HOME'] = old_home

    def test_coding_assistant_defaults_and_claude_stdin(self):
        fake_codex = server.ROOT/'default-codex'
        fake_codex.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\ncat\n")
        fake_codex.chmod(0o755)
        fake_claude = server.ROOT/'fake-claude'
        fake_claude.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\ncat\n")
        fake_claude.chmod(0o755)
        saved = {name: os.environ.get(name) for name in (
            'HATCHERY_CODEX_BIN','HATCHERY_CODEX_MODEL','HATCHERY_CLAUDE_BIN')}
        try:
            os.environ['HATCHERY_CODEX_BIN'] = str(fake_codex)
            os.environ.pop('HATCHERY_CODEX_MODEL', None)
            r = server.coding_assistant('default model', 'coding-default', timeout_seconds=30)
            out = self.wait_job(r['job_id'])['output'].splitlines()
            self.assertIn('gpt-5.6-sol', out)
            self.assertEqual(out[-2:], ['-', 'default model'])

            os.environ['HATCHERY_CLAUDE_BIN'] = str(fake_claude)
            r = server.coding_assistant('--help is prompt text', 'coding-claude',
                assistant='claude', model='sonnet', read_only=True, timeout_seconds=30)
            out = self.wait_job(r['job_id'])['output'].splitlines()
            self.assertEqual(out[:3], ['--print', '--permission-mode', 'plan'])
            self.assertIn('sonnet', out)
            self.assertEqual(out[-1], '--help is prompt text')
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_failure_timeout_cancel(self):
        r = server.run_command('exit 7','failure')
        self.assertEqual(self.wait_job(r['job_id'])['exit_code'],7)
        r = server.run_command('sleep 30','timeout',timeout_seconds=1)
        self.assertEqual(self.wait_job(r['job_id'])['status'],'timed_out')
        r = server.run_command('sleep 30','cancel')
        server.cancel_job(r['job_id'])
        self.assertEqual(self.wait_job(r['job_id'])['status'],'cancelled')

    def test_output_cap(self):
        r = server.run_command('head -c 5000000 /dev/zero','cap')
        j = self.wait_job(r['job_id'])
        self.assertTrue(j['truncated'])
        self.assertEqual((server.STATE/(r['job_id']+'.log')).stat().st_size,server.MAX_LOG)

    def test_wait_tail_and_inspect(self):
        r = server.run_command("printf 'first\\n'; sleep .2; printf 'last\\n'", 'wait-tail')
        j = server.wait_job(r['job_id'], wait_seconds=3, tail_bytes=5)
        self.assertEqual(j['status'], 'succeeded')
        self.assertEqual(j['output'], 'last\n')
        self.assertGreater(j['output_offset'], 0)
        snap = server.inspect_workspace('.')
        self.assertIn('git', snap)
        self.assertIn('containers', snap)
        self.assertIn('active_jobs', snap)

    def test_modern_discovery_and_tools(self):
        from mcp import Client, StdioServerParameters
        import json
        async def check():
            params = StdioServerParameters(command=sys.executable,
                args=[str(Path(server.__file__))], env=dict(os.environ))
            # Stdio parameters force a real subprocess protocol exchange.
            async with Client(params, mode='auto', read_timeout_seconds=15) as client:
                self.assertIsNotNone(client.session.discover_result)
                self.assertGreaterEqual(client.protocol_version, '2026-07-28')
                listed = await client.list_tools()
                self.assertEqual({t.name for t in listed.tools},
                    {'status', 'run_command', 'coding_assistant', 'get_job', 'wait_job', 'inspect_workspace', 'cancel_job', 'read_file', 'write_file'})
                async def call(name, args):
                    result = await client.call_tool(name, args)
                    self.assertFalse(result.is_error, result)
                    return json.loads(result.content[0].text)
                await call('status', {})
                f = await call('write_file', {'path':'modern.txt','content':'modern','expected_sha256':'missing'})
                self.assertEqual((await call('read_file', {'path':'modern.txt'}))['sha256'], f['sha256'])
                for name, args in [
                    ('read_file', {'path':'../outside'}),
                    ('read_file', {'path':'absent.txt'}),
                    ('write_file', {'path':'modern.txt','content':'stale','expected_sha256':'missing'})]:
                    self.assertTrue((await client.call_tool(name, args)).is_error)
                job = await call('run_command', {'command':'sleep 30','request_id':'modern-cancel'})
                await call('cancel_job', {'job_id':job['job_id']})
                for _ in range(100):
                    state = await call('get_job', {'job_id':job['job_id']})
                    if state['status'] not in ('running','queued'):
                        break
                    await asyncio.sleep(.1)
                self.assertEqual(state['status'], 'cancelled')
                print('modern discovery negotiated', client.protocol_version, file=sys.stderr)
        asyncio.run(check())

    def test_protocol_and_detachment(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        async def check():
            params = StdioServerParameters(command=sys.executable,args=[str(Path(server.__file__))],env=dict(os.environ))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    self.assertEqual(len(listed.tools),9)
                    r = await session.call_tool('status',{})
                    self.assertFalse(r.is_error)
                    bad = await session.call_tool('read_file',{'path':'../x'})
                    self.assertTrue(bad.is_error)
                    r = await session.call_tool('run_command',{'command':'sleep 1; echo survived','request_id':'detached'})
                    import json
                    jid = json.loads(r.content[0].text)['job_id']
            return jid
        jid = asyncio.run(check())
        self.assertEqual(self.wait_job(jid)['output'],'survived\n')

if __name__ == '__main__':
    unittest.main(verbosity=2)
