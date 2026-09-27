import type { DashboardArtifact } from './types'

const escapeHtml = (value: string) => value.replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[char]!)

const scriptJson = (value: unknown) => JSON.stringify(value)
  .replace(/&/g, '\\u0026')
  .replace(/</g, '\\u003c')
  .replace(/>/g, '\\u003e')
  .replace(/\u2028/g, '\\u2028')
  .replace(/\u2029/g, '\\u2029')

/** One frozen, self-contained dashboard. It never loads data or code from the network. */
export function buildDashboardHtml(artifact: DashboardArtifact): string {
  const snapshot = {
    id: artifact.id,
    version: artifact.version,
    created_at: artifact.created_at,
    spec: artifact.spec,
    results: artifact.results,
  }
  const title = escapeHtml(artifact.spec.title || 'Night Owl dashboard')
  const data = scriptJson(snapshot)
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>${title} · Night Owl</title>
<style>
:root{color-scheme:light;--ink:#171717;--muted:#6b6b6b;--faint:#8f8f8f;--bg:#f6f6f5;--card:#fff;--line:rgba(0,0,0,.08);--grid:rgba(0,0,0,.07);--hover:rgba(0,0,0,.04);--accent:#c8731e;--c0:#c8731e;--c1:#2f6fae;--c2:#2a9a70;--c3:#8a63c9;--c4:#c2477a;--c5:#4e8f9c}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--ink:#ededed;--muted:#a3a3a3;--faint:#737373;--bg:#0a0a0a;--card:#141414;--line:rgba(255,255,255,.1);--grid:rgba(255,255,255,.08);--hover:rgba(255,255,255,.05);--accent:#cf7f30;--c0:#cf7f30;--c1:#4585cc;--c2:#3fa060;--c3:#8f74d4;--c4:#d0608f;--c5:#5ea3b0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:clamp(18px,3vw,36px)}h1,h2,p{margin-top:0}h1{font-size:22px;line-height:1.25;font-weight:600;letter-spacing:-.01em;margin-bottom:4px}h2{font-size:13.5px;line-height:1.35;font-weight:600;margin:0}header{margin-bottom:18px}.summary{max-width:64ch;color:var(--muted);font-size:13.5px;margin-bottom:4px}.meta-line,.muted{color:var(--faint);font-size:12px;margin:0}.note{margin:24px 0 0;color:var(--faint);font-size:12px}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:12px}.card{grid-column:span 6;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px 10px;min-width:0;display:flex;flex-direction:column}.card.wide{grid-column:1/-1}.card.tile{grid-column:span 3;align-self:start}.cardhead{display:flex;justify-content:space-between;align-items:start;gap:12px}.desc{color:var(--muted);font-size:12.5px;margin:2px 0 0}
.controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:10px 0 0}.controls label{font-size:12px;color:var(--muted);display:inline-flex;align-items:center;gap:4px}select,input[type=search],button{font:inherit;font-size:12.5px;border:1px solid var(--line);background:var(--card);border-radius:6px;padding:4px 8px;color:var(--ink)}button{cursor:pointer}button:hover{border-color:var(--faint)}button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}.series{display:flex;gap:10px;flex-wrap:wrap}
.chart{width:100%;height:auto;min-height:220px;display:block;margin-top:10px}.chart text{font:11px -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;fill:var(--faint);font-variant-numeric:tabular-nums}.chart .axis{stroke:var(--line)}.chart .gridline{stroke:var(--grid)}.f0{fill:var(--c0)}.f1{fill:var(--c1)}.f2{fill:var(--c2)}.f3{fill:var(--c3)}.f4{fill:var(--c4)}.f5{fill:var(--c5)}.k0{stroke:var(--c0)}.k1{stroke:var(--c1)}.k2{stroke:var(--c2)}.k3{stroke:var(--c3)}.k4{stroke:var(--c4)}.k5{stroke:var(--c5)}.dot{stroke:var(--card);stroke-width:2}
.legend{display:flex;gap:4px 14px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:4px}.legend span{display:inline-flex;align-items:center;gap:6px}.legend span:before{content:"";display:inline-block;width:8px;height:8px;background:var(--swatch);border-radius:2px}.legend.lines span:before{width:10px;height:2px;border-radius:1px}.axisnote{display:flex;justify-content:space-between;gap:12px;color:var(--faint);font-size:11px;margin-top:4px}
.tablewrap{overflow:auto;max-height:560px;border:1px solid var(--line);border-radius:8px;margin-top:10px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top;white-space:nowrap}th{position:sticky;top:0;background:var(--card);z-index:1}th button{border:0;background:transparent;padding:0;text-align:left;font-weight:500;color:var(--muted);font-size:12px}th button:hover{color:var(--ink)}td{font-variant-numeric:tabular-nums}tr:hover td{background:var(--hover)}
.metrics{display:flex;flex-wrap:wrap;gap:14px 24px;margin:12px 0 10px}.metric{display:flex;flex-direction:column;gap:6px}.metric .label{color:var(--muted);font-size:12.5px;margin:0}.metric .value{font-size:30px;line-height:1;font-weight:600;letter-spacing:-.02em;margin:0}.metric .value small{font-size:13px;font-weight:500;color:var(--muted);letter-spacing:0}
.meta{margin-top:auto;padding-top:10px;font-size:11.5px;color:var(--faint)}.meta p{margin:2px 0}.empty{padding:32px 12px;text-align:center;color:var(--muted);background:var(--hover);border-radius:8px;font-size:13px;margin-top:10px}
@media(max-width:900px){.card{grid-column:span 12}.card.tile{grid-column:span 6}}@media(max-width:520px){main{padding:16px}.card{padding:12px 12px 8px}.card.tile{grid-column:span 12}.chart{min-height:200px}}
</style>
</head>
<body>
<main><header id="header"></header><div id="cards" class="grid"></div><p class="note">Frozen snapshot. Charts and tables work offline; chat and live data refresh remain in the Night Owl app.</p></main>
<script id="snapshot" type="application/json">${data}</script>
<script>
(() => {
  'use strict';
  const artifact = JSON.parse(document.getElementById('snapshot').textContent);
  const own = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
  const value = (row, key) => row && own(row, key) ? row[key] : null;
  const str = (v) => v == null ? '' : String(v);
  const number = (v) => typeof v === 'number' && Number.isFinite(v) ? v : null;
  const SLOTS = 6;
  const barPath = (x, y, w, h, up) => { const r = Math.min(4, w / 2, h); return up ? 'M' + x + ',' + (y + h) + 'v' + (r - h) + 'a' + r + ',' + r + ' 0 0 1 ' + r + ',' + (-r) + 'h' + (w - 2 * r) + 'a' + r + ',' + r + ' 0 0 1 ' + r + ',' + r + 'v' + (h - r) + 'z' : 'M' + x + ',' + y + 'v' + (h - r) + 'a' + r + ',' + r + ' 0 0 0 ' + r + ',' + r + 'h' + (w - 2 * r) + 'a' + r + ',' + r + ' 0 0 0 ' + r + ',' + (-r) + 'v' + (r - h) + 'z'; };
  const make = (tag, cls, text) => { const node = document.createElement(tag); if (cls) node.className = cls; if (text != null) node.textContent = str(text); return node; };
  const svgNode = (tag, attrs, text) => { const node = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const [key, val] of Object.entries(attrs || {})) node.setAttribute(key, str(val)); if (text != null) node.textContent = str(text); return node; };
  const numericFormat = new Intl.NumberFormat(undefined,{maximumFractionDigits:3});
  const isFraction = (unit) => unit === 'probability' || unit === 'fraction';
  const unitLabel = (unit) => isFraction(unit) ? '%' : unit === 'percentile 0–100' ? 'percentile' : unit === 'year' ? '' : unit;
  const tick = (v, unit) => unit === 'year' ? str(v) : isFraction(unit) ? numericFormat.format(v * 100) + '%' : numericFormat.format(v);
  const niceStep = (span) => { const raw = span / 4, mag = Math.pow(10, Math.floor(Math.log10(raw))), n = raw / mag; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag; };
  const format = (v, unit) => {
    if (typeof v !== 'number' || !Number.isFinite(v)) return str(v) || '—';
    if (unit === 'year') return str(v);
    if (isFraction(unit)) return numericFormat.format(v * 100) + '%';
    return numericFormat.format(v) + (unit ? ' ' + unit : '');
  };
  const column = (result, key) => result.columns.find((item) => item.key === key);
  const label = (result, key) => column(result, key)?.label || key;
  const unit = (result, key) => column(result, key)?.unit || '';
  const header = document.getElementById('header');
  header.append(make('h1','',artifact.spec.title), make('p','summary',artifact.spec.description));
  const stamp = new Date(artifact.created_at);
  header.append(make('p','meta-line','Night Owl · version ' + str(artifact.version) + ' · ' + (Number.isNaN(stamp.getTime()) ? str(artifact.created_at) : stamp.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }))));
  const cards = document.getElementById('cards');

  function drawChart(host, card, result, kind, selected) {
    const rows = result.rows;
    const series = selected.filter((key) => rows.some((row) => number(value(row,key)) !== null));
    if (!rows.length || !series.length) { host.append(make('p','empty','No numeric rows for this chart. Use the table view to inspect the data.')); return; }
    const width = Math.max(360, Math.round(host.clientWidth) || 800), height = 280, left = 52, right = 12, top = 12, bottom = 36;
    const plotW = width-left-right, plotH = height-top-bottom;
    const points = [];
    rows.forEach((row, i) => series.forEach((key, j) => { const y = number(value(row,key)); if (y !== null) points.push({i,j,key,y,x:number(value(row,card.x))}); }));
    if (!points.length) { host.append(make('p','empty','No numeric values.')); return; }
    let minY = Math.min(0,...points.map((p) => p.y)), maxY = Math.max(0,...points.map((p) => p.y));
    if (minY === maxY) maxY = minY + 1;
    const stepY = niceStep(maxY - minY); minY = Math.floor(minY / stepY) * stepY; maxY = Math.ceil(maxY / stepY) * stepY;
    const yPx = (v) => top + plotH * (maxY-v)/(maxY-minY);
    const svg = svgNode('svg',{class:'chart',viewBox:'0 0 '+width+' 280',role:'img','aria-label':kind + ' chart: ' + card.title});
    const yUnit=unit(result,series[0]);
    for (let i=0;i<=4;i++) {
      const y=top+plotH*i/4;
      svg.append(svgNode('line',{x1:left,y1:y,x2:width-right,y2:y,class:'gridline'}));
      svg.append(svgNode('text',{x:left-8,y:y+4,'text-anchor':'end'},tick(maxY-(maxY-minY)*i/4,yUnit)));
    }
    svg.append(svgNode('line',{x1:left,y1:yPx(0),x2:width-right,y2:yPx(0),class:'axis'}));
    if (kind === 'scatter') {
      const numericX = points.filter((p) => p.x !== null);
      if (!numericX.length) { host.append(make('p','empty','Scatter view needs a numeric x-axis. Use the table view.')); return; }
      let minX=Math.min(...numericX.map((p)=>p.x)),maxX=Math.max(...numericX.map((p)=>p.x));
      if(minX===maxX)maxX=minX+1;
      for(const p of numericX){
        const x=left+plotW*(p.x-minX)/(maxX-minX);
        const dot=svgNode('circle',{cx:x,cy:yPx(p.y),r:4.5,class:'dot f'+(p.j%SLOTS)});
        dot.append(svgNode('title',{},label(result,p.key)+': '+format(p.y,unit(result,p.key))+' · '+label(result,card.x)+': '+format(p.x,unit(result,card.x))));
        svg.append(dot);
      }
      svg.append(svgNode('text',{x:left,y:height-12},tick(minX,unit(result,card.x))));
      svg.append(svgNode('text',{x:width-right,y:height-12,'text-anchor':'end'},tick(maxX,unit(result,card.x))));
    } else {
      const count=Math.max(1,rows.length),step=plotW/count;
      if(kind==='bar'){
        const barW=Math.max(1,Math.min(24,(step*.7-2*(series.length-1))/series.length)),groupW=barW*series.length+2*(series.length-1);
        for(const p of points){
          const x=left+p.i*step+(step-groupW)/2+p.j*(barW+2);
          const y=Math.min(yPx(p.y),yPx(0)),h=Math.max(1,Math.abs(yPx(p.y)-yPx(0)));
          const bar=svgNode('path',{d:barPath(x,y,barW,h,p.y>=0),class:'f'+(p.j%SLOTS)});
          bar.append(svgNode('title',{},str(value(rows[p.i],card.x))+' · '+label(result,p.key)+': '+format(p.y,unit(result,p.key))));
          svg.append(bar);
        }
      }
      if(kind==='line')for(let j=0;j<series.length;j++){
        const key=series[j], slot=j%SLOTS;
        let run=[];
        const flush=()=>{if(run.length>1)svg.append(svgNode('polyline',{points:run.join(' '),fill:'none','stroke-width':2,'stroke-linejoin':'round','stroke-linecap':'round',class:'k'+slot}));run=[];};
        rows.forEach((row,i)=>{
          const y=number(value(row,key));
          if(y===null){flush();return;}
          const x=left+(i+.5)*step;
          run.push(x+','+yPx(y));
          const dot=svgNode('circle',{cx:x,cy:yPx(y),r:4,class:'dot f'+slot});
          dot.append(svgNode('title',{},str(value(row,card.x))+' · '+label(result,key)+': '+format(y,unit(result,key))));
          svg.append(dot);
        });
        flush();
      }
      const ticks=count<=8?rows.map((_,i)=>i):[0,Math.floor((count-1)/2),count-1].filter((v,i,a)=>a.indexOf(v)===i);
      for(const i of ticks)svg.append(svgNode('text',{x:left+(i+.5)*step,y:height-12,'text-anchor':'middle'},str(value(rows[i],card.x)).slice(0,count<=8?16:24)));
    }
    host.append(svg);
    const named=(key)=>{const suffix=unitLabel(unit(result,key));return label(result,key)+(suffix?' ('+suffix+')':'');};
    if(series.length>1){
      const legend=make('div','legend'+(kind==='line'?' lines':''));
      series.forEach((key,j)=>{const item=make('span','',named(key));item.style.setProperty('--swatch','var(--c'+(j%SLOTS)+')');legend.append(item);});
      host.append(legend);
    }
    const note=make('div','axisnote');note.append(make('span','',label(result,card.x)),make('span','',named(series[0])));
    if(series.length===1)host.append(note);
  }

  function csvCell(v) { let s=str(v); if(typeof v==='string' && /^[=+@\\-\\t\\r\\n]/.test(s))s="'"+s; return '"'+s.replace(/"/g,'""')+'"'; }
  function saveCsv(card, columns, rows) { const lines=[columns.map((c)=>csvCell(c.label)).join(',')]; for(const row of rows)lines.push(columns.map((c)=>csvCell(value(row,c.key))).join(',')); const blob=new Blob(['\\ufeff'+lines.join('\\r\\n')],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=make('a');a.href=url;a.download=(card.id.replace(/[^a-zA-Z0-9_-]+/g,'-')||'dashboard')+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }
  function drawTable(host, card, result, selected) {
    const columns=result.columns.filter((col)=>!card.y.includes(col.key)||selected.includes(col.key));
    const controls=make('div','controls'),search=make('input');search.type='search';search.placeholder='Search rows';search.setAttribute('aria-label','Search '+card.title+' table');const save=make('button','','Download CSV');save.type='button';controls.append(search,save);host.append(controls);
    const wrap=make('div','tablewrap'),table=make('table'),caption=make('caption','',card.title+' data');caption.style.cssText='position:absolute;clip:rect(0,0,0,0)';table.append(caption);const head=make('thead'),hr=make('tr'),body=make('tbody');head.append(hr);table.append(head,body);wrap.append(table);host.append(wrap);
    let sortKey='',ascending=true,displayed=[];
    function compareRows(a,b){
      const av=value(a,sortKey),bv=value(b,sortKey);
      if(av==null)return bv==null?0:1;
      if(bv==null)return -1;
      const an=number(av),bn=number(bv);
      const cmp=an!==null&&bn!==null?an-bn:str(av).localeCompare(str(bv),undefined,{numeric:true,sensitivity:'base'});
      return ascending?cmp:-cmp;
    }
    function render(){
      const term=search.value.toLocaleLowerCase();
      displayed=result.rows.filter((row)=>columns.some((col)=>str(value(row,col.key)).toLocaleLowerCase().includes(term)));
      if(sortKey)displayed.sort(compareRows);
      body.replaceChildren();
      for(const row of displayed){const tr=make('tr');for(const col of columns)tr.append(make('td','',format(value(row,col.key),col.unit)));body.append(tr);}
    }
    for(const col of columns){const th=make('th'),button=make('button','',col.label);button.type='button';button.setAttribute('aria-label','Sort by '+col.label);button.addEventListener('click',()=>{ascending=sortKey===col.key?!ascending:true;sortKey=col.key;render();});th.scope='col';th.append(button);hr.append(th);}search.addEventListener('input',render);save.addEventListener('click',()=>saveCsv(card,columns,displayed));render();
  }

  function renderCard(card) {
    const result=own(artifact.results,card.id)?artifact.results[card.id]:null;
    const section=make('section','card'+(card.kind==='table'?' wide':card.kind==='metric'?' tile':''));const head=make('div','cardhead');head.append(make('h2','',card.title));section.append(head);if(card.description)section.append(make('p','desc',card.description));cards.append(section);
    if(!result){section.append(make('p','empty','No saved result for this card.'));return;}
    const available=card.y.filter((key)=>result.columns.some((col)=>col.key===key));let selected=[...available];
    const sameUnits=available.every((key)=>unit(result,key)===unit(result,available[0]));
    const chartable=!!card.x&&available.length>0&&sameUnits&&result.rows.some((row)=>available.some((key)=>number(value(row,key))!==null));
    const scatterable=chartable&&result.rows.some((row)=>number(value(row,card.x))!==null);
    const kinds=card.kind==='metric'?['metric','table']:card.kind==='scatter'?scatterable?['scatter','table']:['table']:chartable?['bar','line','table']:['table'];
    let kind=kinds.includes(card.kind)?card.kind:kinds[0];
    const controls=make('div','controls'),typeLabel=make('label','','View'),type=make('select');type.setAttribute('aria-label',card.title+' chart type');for(const option of kinds){const node=make('option','',option[0].toUpperCase()+option.slice(1));node.value=option;type.append(node);}type.value=kind;typeLabel.append(type);controls.append(typeLabel);
    if(available.length>1){const toggles=make('div','series');for(const key of available){const labelNode=make('label');const check=make('input');check.type='checkbox';check.checked=true;check.addEventListener('change',()=>{selected=check.checked?[...selected,key]:selected.filter((item)=>item!==key);draw();});labelNode.append(check,document.createTextNode(label(result,key)));toggles.append(labelNode);}controls.append(toggles);}
    section.append(controls);const content=make('div');section.append(content);
    function draw(){content.replaceChildren();if(kind==='table')drawTable(content,card,result,selected);else if(kind==='metric'){const row=result.rows[0];if(!row){content.append(make('p','empty','No saved values.'));return;}const tiles=make('div','metrics');for(const key of selected){const tile=make('div','metric');const v=value(row,key),u=unit(result,key),big=make('p','value',typeof v==='number'&&Number.isFinite(v)?(isFraction(u)?numericFormat.format(v*100)+'%':numericFormat.format(v)):str(v)||'—');if(typeof v==='number'&&Number.isFinite(v)&&u&&!isFraction(u))big.append(make('small','',' '+u));tile.append(make('p','label',label(result,key)),big);tiles.append(tile);}content.append(tiles);if(result.rows.length>1)content.append(make('p','muted','Showing the first row. Switch to table for all rows.'));}else drawChart(content,card,result,kind,selected);}
    type.addEventListener('change',()=>{kind=type.value;draw();});draw();
    const meta=make('div','meta');
    const noun=result.query.aggregation==='raw'||!result.query.group_by?'result rows':'result groups';
    meta.append(make('p','',result.rows.length===result.total_rows?result.total_rows+' '+noun:result.rows.length+' of '+result.total_rows+' '+noun+' saved in this snapshot.'));
    if(result.total_rows>result.rows.length)meta.append(make('p','',
      'Query limit omitted '+(result.total_rows-result.rows.length)+' '+noun+'; charts, tables, and CSV use only saved data.'));
    meta.append(make('p','',(({fixture:'Sample data',events:'Event data',model:'Model data',history:'NYC Open Data'})[result.source.kind]||result.source.kind)+' · '+(result.source.as_of||'date unknown')));
    for(const note of result.source.notes)meta.append(make('p','',note));
    section.append(meta);
  }
  for(const card of artifact.spec.cards)renderCard(card);
})();
</script>
</body>
</html>`
}

export function downloadDashboard(artifact: DashboardArtifact): void {
  const html = buildDashboardHtml(artifact)
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${(artifact.spec.title || artifact.id).normalize('NFKD').replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-|-$/g, '').slice(0, 64) || 'night-owl-dashboard'}.html`
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
