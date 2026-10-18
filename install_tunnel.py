#!/usr/bin/env python3
"""Install the current official full tunnel-client, verifying release SHA256."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import tempfile
import urllib.request
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('--destination', type=Path, default=Path.home()/'.local/bin')
parser.add_argument('--check-only', action='store_true')
args = parser.parse_args()
arch = {'aarch64':'arm64','arm64':'arm64','x86_64':'amd64'}.get(platform.machine())
if platform.system() != 'Linux' or arch is None:
    raise SystemExit('This installer supports Linux ARM64 and AMD64.')

def fetch(url, limit=256*1024*1024):
    req = urllib.request.Request(url,headers={'User-Agent':'hatchery-bridge-setup','Accept':'application/vnd.github+json' if url.startswith('https://api.github.com/') else '*/*'})
    with urllib.request.urlopen(req,timeout=90) as response:
        data = response.read(limit+1)
    if len(data)>limit:
        raise RuntimeError('Download exceeds size limit')
    return data

release=json.loads(fetch('https://api.github.com/repos/openai/tunnel-client/releases/latest',2*1024*1024))
pattern=r'^tunnel-client-v[^/]+-linux-'+arch+r'\.zip$'
archives=[a for a in release['assets'] if re.fullmatch(pattern,a['name'])]
sums=[a for a in release['assets'] if a['name']=='SHA256SUMS.txt']
if len(archives)!=1 or len(sums)!=1:
    raise SystemExit('Release layout changed; use the official release download instructions.')
asset=archives[0]
print('Official release:',release['tag_name'],asset['name'])
if args.check_only:
    raise SystemExit(0)
checksums=fetch(sums[0]['browser_download_url'],1024*1024).decode()
expected=None
for line in checksums.splitlines():
    parts=line.split(maxsplit=1)
    if len(parts)==2 and parts[1].lstrip('*')==asset['name']:
        expected=parts[0]
if expected is None or not re.fullmatch('[0-9a-fA-F]{64}',expected):
    raise SystemExit('No checksum for the selected archive')
archive=fetch(asset['browser_download_url'])
if hashlib.sha256(archive).hexdigest()!=expected.lower():
    raise SystemExit('Checksum mismatch; nothing installed')
args.destination.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(io.BytesIO(archive)) as z:
    # Never extract arbitrary archive paths. Copy only the known executables.
    for binary in ('tunnel-client','cloudflared'):
        matches=[x for x in z.infolist() if Path(x.filename).name==binary and not x.is_dir()]
        if len(matches)!=1:
            raise SystemExit('Missing or ambiguous executable: '+binary)
        entry=matches[0]
        if entry.file_size>256*1024*1024:
            raise SystemExit('Executable exceeds size limit')
        payload=z.read(entry)
        fd,tmp=tempfile.mkstemp(dir=args.destination,prefix='.hatchery-download-')
        try:
            with os.fdopen(fd,'wb') as f:
                f.write(payload)
            os.chmod(tmp,0o755)
            os.replace(tmp,args.destination/binary)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        print('Installed',args.destination/binary)
print('SHA256 verified against the official release. Run tunnel-client help quickstart.')
