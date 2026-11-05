"""Read-only progress/ETA estimate from the current run's timestamped log."""
import json,re
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TZ=timezone(timedelta(hours=8))
now=datetime.now(TZ)
state=json.loads((ROOT/'index-status.json').read_text())
print('当前时间:',now.strftime('%Y-%m-%d %H:%M:%S UTC+8'))
print('任务状态:',state.get('state','unknown'))
start=datetime.fromisoformat(state['started_at']) if state.get('started_at') else None
if start:print('已运行:',str(now-start).split('.')[0])
if state.get('state')!='running':raise SystemExit(0)
phase=None;phase_start=None;points=[];label=None
log=ROOT/'logs/indexing-engine.log'
if not log.exists():print('尚未生成带时间戳日志');raise SystemExit(0)
with log.open(errors='replace') as handle:
 for line in handle:
  match=re.match(r'(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)',line)
  if not match:continue
  stamp=datetime.fromisoformat(match[1]).replace(tzinfo=TZ)
  if start and stamp<start:continue
  stage=re.search(r'Workflow started: (\w+)',line)
  if stage:
   phase=stage[1];phase_start=stamp;points=[];label=None
  item=re.search(r' - ([^-\n]*?progress):\s*(\d+)\s*/\s*(\d+)',line)
  if item:
   name,current,total=item[1],int(item[2]),int(item[3])
   if label!=name or (points and (total!=points[-1][2] or current<points[-1][1])):
    points=[];label=name
   points.append((stamp,current,total))
print('当前阶段:',phase or '初始化')
if not points:
 print('当前阶段暂无可用于估算的进度计数。');raise SystemExit(0)
last,done,total=points[-1]
print(f'当前计数: {done}/{total} ({done/total:.2%})；{label}')
stale=max(0,(now-last).total_seconds())
print(f'距最新进度: {int(stale)}秒')
window=[p for p in points if p[0]>=last-timedelta(minutes=15)]
if len(window)>=10 and (window[-1][0]-window[0][0]).total_seconds()>=120:
 elapsed=(window[-1][0]-window[0][0]).total_seconds();count=window[-1][1]-window[0][1];basis='最近15分钟以内的进度'
else:
 elapsed=(last-phase_start).total_seconds() if phase_start else 0;count=done;basis='当前阶段起始以来的进度'
if elapsed<=0 or count<=0:print('样本不足，暂无法估算');raise SystemExit(0)
rate=count/elapsed;remaining=(total-done)/rate
print(f'估算速度: {rate*60:.2f}项/分钟（{basis}）')
print('当前计数预计剩余:',str(timedelta(seconds=int(remaining))).split('.')[0])
print('按最新进度推算完成时间:',(last+timedelta(seconds=remaining)).strftime('%Y-%m-%d %H:%M UTC+8'))
if done<100:print('注意：完成不足100项，属于早期粗估，波动可能较大。')
if stale>180:print('注意：进度已有超过3分钟未更新，ETA可能失真，请检查任务日志。')
print('此ETA仅针对当前计数，不含后续描述合并、社区摘要和向量索引等阶段，不能视为全任务完成时间。')
