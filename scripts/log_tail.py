import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
key=(root/'.env').read_text().strip().split('=',1)[1]
for f in sys.argv[1:]:
 p=root/f
 print('LOG:',f)
 if p.exists():print('\n'.join(p.read_text(errors='replace').replace(key,'[REDACTED]').splitlines()[-18:]))
