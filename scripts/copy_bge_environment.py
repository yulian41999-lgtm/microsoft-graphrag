"""Copy installed BGE dependency closure into a fresh same-ABI venv; source is read-only."""
import importlib.metadata as md,json,shutil,sys
from pathlib import Path
from packaging.requirements import Requirement
root=Path(__file__).resolve().parents[1]
source=Path(sys.prefix)/'lib/python3.10/site-packages'
target=root/'.venv-bge/lib/python3.10/site-packages'
assert target.resolve().is_relative_to(root)
queue=['torch','sentence-transformers','transformers'];seen={};tops=set()
while queue:
 name=queue.pop();dist=md.distribution(name);name=dist.metadata['Name']
 if name.lower() in seen:continue
 seen[name.lower()]=dist.version
 for req in dist.requires or []:
  r=Requirement(req)
  if r.marker is None or r.marker.evaluate({'extra':''}):queue.append(r.name)
 for file in dist.files or []:
  first=Path(str(file)).parts[0]
  if first not in {'.','..'} and (source/first).exists():tops.add(first)
for i,name in enumerate(sorted(tops),1):
 src=source/name;dst=target/name
 if dst.exists():continue
 if src.is_dir():shutil.copytree(src,dst,symlinks=False)
 else:shutil.copy2(src,dst)
 print(f'Copied {i}/{len(tops)}: {name}',flush=True)
(root/'bge-environment-provenance.json').write_text(json.dumps({'source_python':sys.executable,'method':'read-only copy of installed dependency closure into fresh Python3.10 venv','packages':seen},indent=2)+'\n')
print('BGE_ENV_COPY_COMPLETE',flush=True)
