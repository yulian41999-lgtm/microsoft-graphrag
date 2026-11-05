from pathlib import Path
import pandas as pd,json,re
p=Path('output/visualization')
s=(p/'index.html').read_text()
e=pd.read_parquet('output/entities.parquet').fillna({'description':'','type':'UNKNOWN'})
r=pd.read_parquet('output/relationships.parquet').fillna({'description':''})
nodes=[dict(id=str(x.title),label=str(x.title),group=str(x.type),value=int(x.degree),title=str(x.description)) for x in e.itertuples()]
edges=[dict(source=str(x.source),target=str(x.target),description=str(x.description)) for x in r.itertuples()]
payload=json.dumps(dict(nodes=nodes,edges=edges),ensure_ascii=False).replace('<','\\u003c')
start=s.index('const data=');end=s.index(';const svg=',start)
s=s[:start]+'const full='+payload+';let data={nodes:[],edges:[]};function subset(id){let ns;if(id){let ids=new Set([id]);for(const e of full.edges){if(e.source===id)ids.add(e.target);if(e.target===id)ids.add(e.source);if(ids.size>=80)break}ns=full.nodes.filter(n=>ids.has(n.id))}else ns=[...full.nodes].sort((a,b)=>b.value-a.value).slice(0,100);let ids=new Set(ns.map(n=>n.id));data={nodes:ns,edges:full.edges.filter(e=>ids.has(e.source)&&ids.has(e.target))}}subset()'+s[end:]
s=s.replace('const svg=','const svg=',1)
a=s.index('let map={};');b=s.index("document.querySelector('#search').oninput",a)
render=s[a:b]
render=render.replace('let map={};','g.replaceChildren();let map={};')
render=render.replace("n.c.onclick=()=>detail.textContent=", "n.c.ondblclick=()=>{subset(n.id);render()};n.c.onclick=()=>detail.textContent=")
render=render.replace("let t=el('text'", "n.c.onpointerdown=e=>{e.stopPropagation();moving=n;n.c.setPointerCapture(e.pointerId)};let t=el('text'")
render=render.replace("t.textContent=n.label", "n.t=t;t.textContent=n.label")
render=render.replace("l.onclick=", "e.line=l;l.onclick=")
s=s[:a]+'let moving=null;function render(){'+render+'}render();'+s[b:]
a=s.index("document.querySelector('#search').oninput");b=s.index('function update()',a)
s=s[:a]+'''const search=document.querySelector('#search'),matches=document.createElement('div');search.parentElement.append(matches);search.placeholder='搜索全部 33,184 个实体';search.oninput=()=>{matches.replaceChildren();const q=search.value.trim();if(!q)return;const hits=full.nodes.filter(n=>n.id.includes(q)).sort((a,b)=>b.value-a.value);const label=document.createElement('span');label.textContent='匹配 '+hits.length+' 项，前 15 项：';matches.append(label);hits.slice(0,15).forEach(n=>{const b=document.createElement('button');b.textContent=n.id;b.onclick=()=>{subset(n.id);render()};matches.append(b)})};let paused=matchMedia('(prefers-reduced-motion: reduce)').matches;const pause=document.createElement('button');function label(){pause.textContent=paused?'播放动画':'暂停动画'}label();pause.onclick=()=>{paused=!paused;label()};search.after(pause);const home=document.createElement('button');home.textContent='核心概览';home.onclick=()=>{subset();render()};pause.after(home);
''' +s[b:]
s=s.replace('svg.onpointermove=e=>{if(drag)',"svg.onpointermove=e=>{if(moving){const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(g.getScreenCTM().inverse());moving.x=p.x;moving.y=p.y;return}if(drag)")
s=s.replace('svg.onpointerup=()=>drag=null;', 'svg.onpointerup=()=>{drag=null;moving=null};svg.onpointercancel=()=>{drag=null;moving=null};')
s=s.replace('</script>', '''let tick=0;function animate(){if(!paused){const ns=data.nodes;for(let i=0;i<ns.length;i++){let a=ns[i];if(a===moving)continue;let fx=-a.x*.0006,fy=-a.y*.0006;for(let j=0;j<ns.length;j++){if(i===j)continue;let b=ns[j],dx=a.x-b.x,dy=a.y-b.y,d=Math.max(20,Math.hypot(dx,dy));fx+=dx/d*900/(d*d);fy+=dy/d*900/(d*d)}for(const e of data.edges){if(e.source!==a.id&&e.target!==a.id)continue;let b=ns.find(n=>n.id===(e.source===a.id?e.target:e.source));if(!b)continue;let dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy));fx+=dx/d*(d-110)*.001;fy+=dy/d*(d-110)*.001}a.x+=Math.max(-3,Math.min(3,fx));a.y+=Math.max(-3,Math.min(3,fy))}}const m=new Map(data.nodes.map(n=>[n.id,n]));data.nodes.forEach(n=>{n.c.setAttribute('cx',n.x);n.c.setAttribute('cy',n.y);n.t.setAttribute('x',n.x+8);n.t.setAttribute('y',n.y)});data.edges.forEach(e=>{const a=m.get(e.source),b=m.get(e.target);e.line.setAttribute('x1',a.x);e.line.setAttribute('y1',a.y);e.line.setAttribute('x2',b.x);e.line.setAttribute('y2',b.y)});requestAnimationFrame(animate)}animate();</script>''')
s=s.replace('当前显示度数最高的 150 个实体及其内部关系','动态布局 · 核心概览 100 实体 / 搜索后展开最多 80 个邻域实体')
s=s.replace('滚轮缩放，拖动平移，点击节点或关系查看详情。','滚轮缩放，拖动空白平移，拖拽节点，双击节点展开邻域；点击节点或关系查看完整详情。')
s=s.replace("const types=[...new Set(data.nodes.map(n=>n.group))]", "const types=[...new Set(full.nodes.map(n=>n.group))]")
s=s.replace('colors[types.indexOf(n.group)]','colors[types.indexOf(n.group)%colors.length]')
(p/'dynamic.html').write_text(s)
print('Generated:',len(nodes),'entities',len(edges),'relationships', (p/'dynamic.html').stat().st_size,'bytes')
