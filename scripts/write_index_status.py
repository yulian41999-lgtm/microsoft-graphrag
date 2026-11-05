import json,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
root=Path(sys.argv[1]);phase=sys.argv[2];p=root/'index-status.json'
d=json.loads(p.read_text()) if p.exists() else {}
now=datetime.now(timezone(timedelta(hours=8))).isoformat()
if phase=='running':d={'state':phase,'started_at':now}
else:d.update(state='complete' if int(phase)==0 else 'failed',exit_code=int(phase),finished_at=now)
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
