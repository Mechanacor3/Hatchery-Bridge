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
                    {'status', 'run_command', 'get_job', 'wait_job', 'inspect_workspace', 'cancel_job', 'read_file', 'write_file'})
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
                    self.assertEqual(len(listed.tools),8)
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
