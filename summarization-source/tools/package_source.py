"""Create a source-only handoff ZIP, never collecting business documents."""
from pathlib import Path
from datetime import datetime
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES=['.gitignore','README.md','THIRD_PARTY.md','app.py',
       'lawtool.py','config.json','requirements-web.txt','start_web.py',
       'windows_runtime.py','tools/build_converter.py','tools/package_source.py',
       'tools/converter/pom.xml','tools/converter/LICENSE-upstream.txt']
TREES={'webapp':{'.py'},'tests':{'.py'},'tools/converter/src':{'.java'},'assets':{'.md','.png','.svg','.css'}}

def build():
    paths=[ROOT/name for name in FILES]
    for folder,extensions in TREES.items():
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in extensions)
    paths=sorted(set(paths))
    secret=re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('Unsafe source path')
        if secret.search(path.read_bytes()):
            raise ValueError('Possible secret found: '+str(path.relative_to(ROOT)))
    destination=ROOT/'output'/('source_release_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    destination.mkdir(parents=True)
    archive=destination/'summarization-source.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for path in paths: z.write(path,path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(paths)
        assert all(not n.startswith(('input/','output/','models/','.venv/','.git/')) for n in z.namelist())
    print(archive)
    print(f'{len(paths)} source files; {archive.stat().st_size:,} bytes; integrity/secret-pattern checks passed')

if __name__=='__main__': build()
