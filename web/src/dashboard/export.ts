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
:root{color-scheme:light;--ink:#17212b;--muted:#5a6772;--paper:#f5f3ed;--card:#fff;--line:#d9ddd8;--accent:#a84432;--blue:#395f78;--green:#61775e;--gold:#a77b33}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1200px;margin:auto;padding:clamp(18px,4vw,48px)}h1,h2,h3,p{margin-top:0}h1{font-size:clamp(30px,4vw,48px);line-height:1.08;letter-spacing:-.035em}h2{font-size:21px;line-height:1.2}h3{font-size:16px}small,.muted{color:var(--muted)}header{border-bottom:1px solid var(--line);padding-bottom:22px;margin-bottom:28px}.eyebrow{text-transform:uppercase;letter-spacing:.13em;color:var(--accent);font-size:12px;font-weight:700}.summary{max-width:76ch}.notice{border-left:3px solid var(--accent);padding:10px 14px;background:#fff8f2;color:#443d38;margin:22px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr));gap:18px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;min-width:0;box-shadow:0 2px 10px #17212b08}.card.wide{grid-column:1/-1}.cardhead{display:flex;justify-content:space-between;align-items:start;gap:12px;flex-wrap:wrap}.controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:12px 0}.controls label{font-size:13px;color:var(--muted)}select,input[type=search],button{font:inherit;border:1px solid #b9c3c5;background:white;border-radius:6px;padding:5px 8px;color:var(--ink)}button{cursor:pointer}button:hover{border-color:var(--blue)}button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}.series{display:flex;gap:10px;flex-wrap:wrap}.series label{display:inline-flex;align-items:center;gap:4px}.chart{width:100%;height:auto;min-height:260px;display:block}.chart text{font:12px system-ui,sans-serif;fill:var(--muted)}.chart .axis{stroke:#aeb8b8}.chart .gridline{stroke:#e5e8e6}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted)}.legend span:before{content:"";display:inline-block;width:9px;height:9px;background:var(--swatch);margin-right:5px;border-radius:2px}.tablewrap{overflow:auto;max-height:620px;border:1px solid var(--line);border-radius:6px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:9px 11px;border-bottom:1px solid #e8ece8;vertical-align:top}th{position:sticky;top:0;background:#f3f5f2;z-index:1;white-space:nowrap}th button{border:0;background:transparent;padding:0;text-align:left;font-weight:700}td{overflow-wrap:anywhere}tr:hover td{background:#f8faf8}.metric{font-size:clamp(30px,5vw,48px);line-height:1.1;font-weight:700;color:var(--accent);margin:12px 0}.meta{border-top:1px solid var(--line);margin-top:14px;padding-top:10px;font-size:12px;color:var(--muted)}.meta p{margin:3px 0}.empty{padding:18px 0;color:var(--muted)}
@media(max-width:640px){main{padding:18px}.card{padding:15px}.chart{min-height:220px}}
</style>
</head>
<body>
<main><header id="header"></header><p class="notice">Frozen snapshot. Charts and tables work offline; chat and live data refresh remain in the Night Owl app.</p><div id="cards" class="grid"></div></main>
<script id="snapshot" type="application/json">${data}</script>
<script>
(() => {
  'use strict';
  const artifact = JSON.parse(document.getElementById('snapshot').textContent);
  const own = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
  const value = (row, key) => row && own(row, key) ? row[key] : null;
  const str = (v) => v == null ? '' : String(v);
  const number = (v) => typeof v === 'number' && Number.isFinite(v) ? v : null;
  const colours = ['#a84432','#395f78','#61775e','#a77b33','#7a5c85','#477b79'];
  const make = (tag, cls, text) => { const node = document.createElement(tag); if (cls) node.className = cls; if (text != null) node.textContent = str(text); return node; };
  const svgNode = (tag, attrs, text) => { const node = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const [key, val] of Object.entries(attrs || {})) node.setAttribute(key, str(val)); if (text != null) node.textContent = str(text); return node; };
  const numericFormat = new Intl.NumberFormat(undefined,{maximumFractionDigits:3});
  const isFraction = (unit) => unit === 'probability' || unit === 'fraction';
  const unitLabel = (unit) => isFraction(unit) ? '%' : unit;
  const format = (v, unit) => {
    if (typeof v !== 'number' || !Number.isFinite(v)) return str(v) || '—';
    if (isFraction(unit)) return numericFormat.format(v * 100) + '%';
    return numericFormat.format(v) + (unit ? ' ' + unit : '');
  };
  const column = (result, key) => result.columns.find((item) => item.key === key);
  const label = (result, key) => column(result, key)?.label || key;
  const unit = (result, key) => column(result, key)?.unit || '';
  const header = document.getElementById('header');
  header.append(make('p','eyebrow','Night Owl · exported dashboard'), make('h1','',artifact.spec.title), make('p','summary',artifact.spec.description));
  header.append(make('p','muted','Snapshot captured ' + str(artifact.created_at) + ' · Version ' + str(artifact.version)));
  const cards = document.getElementById('cards');

  function drawChart(host, card, result, kind, selected) {
    const rows = result.rows;
    const series = selected.filter((key) => rows.some((row) => number(value(row,key)) !== null));
    if (!rows.length || !series.length) { host.append(make('p','empty','No numeric rows for this chart. Use the table view to inspect the data.')); return; }
    const width = 800, height = 310, left = 64, right = 18, top = 18, bottom = 64;
    const plotW = width-left-right, plotH = height-top-bottom;
    const points = [];
    rows.forEach((row, i) => series.forEach((key, j) => { const y = number(value(row,key)); if (y !== null) points.push({i,j,key,y,x:number(value(row,card.x))}); }));
    if (!points.length) { host.append(make('p','empty','No numeric values.')); return; }
    let minY = Math.min(0,...points.map((p) => p.y)), maxY = Math.max(0,...points.map((p) => p.y));
    if (minY === maxY) maxY = minY + 1;
    const yPx = (v) => top + plotH * (maxY-v)/(maxY-minY);
    const svg = svgNode('svg',{class:'chart',viewBox:'0 0 800 310',role:'img','aria-label':kind + ' chart: ' + card.title});
    const yUnit=unit(result,series[0]);
    for (let i=0;i<=4;i++) {
      const y=top+plotH*i/4;
      svg.append(svgNode('line',{x1:left,y1:y,x2:width-right,y2:y,class:'gridline'}));
      svg.append(svgNode('text',{x:4,y:y+4},format(maxY-(maxY-minY)*i/4,yUnit)));
    }
    svg.append(svgNode('line',{x1:left,y1:top+plotH,x2:width-right,y2:top+plotH,class:'axis'}));
    if (kind === 'scatter') {
      const numericX = points.filter((p) => p.x !== null);
      if (!numericX.length) { host.append(make('p','empty','Scatter view needs a numeric x-axis. Use the table view.')); return; }
      let minX=Math.min(...numericX.map((p)=>p.x)),maxX=Math.max(...numericX.map((p)=>p.x));
      if(minX===maxX)maxX=minX+1;
      for(const p of numericX){
        const x=left+plotW*(p.x-minX)/(maxX-minX);
        const dot=svgNode('circle',{cx:x,cy:yPx(p.y),r:4,fill:colours[p.j%colours.length]});
        dot.append(svgNode('title',{},label(result,p.key)+': '+format(p.y,unit(result,p.key))+' · '+label(result,card.x)+': '+format(p.x,unit(result,card.x))));
        svg.append(dot);
      }
      svg.append(svgNode('text',{x:left,y:height-18},format(minX,unit(result,card.x))));
      svg.append(svgNode('text',{x:width-right,y:height-18,'text-anchor':'end'},format(maxX,unit(result,card.x))));
    } else {
      const count=Math.max(1,rows.length),step=plotW/count;
      if(kind==='bar')for(const p of points){
        const barW=Math.max(1,step*.8/series.length);
        const x=left+p.i*step+step*.1+p.j*barW;
        const y=Math.min(yPx(p.y),yPx(0)),h=Math.max(1,Math.abs(yPx(p.y)-yPx(0)));
        const bar=svgNode('rect',{x,y,width:barW,height:h,fill:colours[p.j%colours.length]});
        bar.append(svgNode('title',{},str(value(rows[p.i],card.x))+' · '+label(result,p.key)+': '+format(p.y,unit(result,p.key))));
        svg.append(bar);
      }
      if(kind==='line')for(let j=0;j<series.length;j++){
        const key=series[j], colour=colours[j%colours.length];
        let run=[];
        const flush=()=>{if(run.length>1)svg.append(svgNode('polyline',{points:run.join(' '),fill:'none',stroke:colour,'stroke-width':2.5,'stroke-linejoin':'round'}));run=[];};
        rows.forEach((row,i)=>{
          const y=number(value(row,key));
          if(y===null){flush();return;}
          const x=left+(i+.5)*step;
          run.push(x+','+yPx(y));
          const dot=svgNode('circle',{cx:x,cy:yPx(y),r:3,fill:colour});
          dot.append(svgNode('title',{},str(value(row,card.x))+' · '+label(result,key)+': '+format(y,unit(result,key))));
          svg.append(dot);
        });
        flush();
      }
      const ticks=[0,Math.floor((count-1)/2),count-1].filter((v,i,a)=>a.indexOf(v)===i);
      for(const i of ticks)svg.append(svgNode('text',{x:left+(i+.5)*step,y:height-18,'text-anchor':i===0?'start':i===count-1?'end':'middle'},str(value(rows[i],card.x)).slice(0,24)));
    }
    host.append(svg);
    const legend=make('div','legend');
    series.forEach((key,j)=>{
      const suffix=unitLabel(unit(result,key));
      const item=make('span','',label(result,key)+(suffix?' ('+suffix+')':''));
      item.style.setProperty('--swatch',colours[j%colours.length]);
      legend.append(item);
    });
    host.append(legend);
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
    const section=make('section','card'+(card.kind==='table'?' wide':''));const head=make('div','cardhead');head.append(make('h2','',card.title));section.append(head);if(card.description)section.append(make('p','muted',card.description));
    if(!result){section.append(make('p','empty','No saved result for this card.'));cards.append(section);return;}
    const available=card.y.filter((key)=>result.columns.some((col)=>col.key===key));let selected=[...available];
    const sameUnits=available.every((key)=>unit(result,key)===unit(result,available[0]));
    const chartable=!!card.x&&available.length>0&&sameUnits&&result.rows.some((row)=>available.some((key)=>number(value(row,key))!==null));
    const scatterable=chartable&&result.rows.some((row)=>number(value(row,card.x))!==null);
    const kinds=card.kind==='metric'?['metric','table']:card.kind==='scatter'?scatterable?['scatter','table']:['table']:chartable?['bar','line','table']:['table'];
    let kind=kinds.includes(card.kind)?card.kind:kinds[0];
    const controls=make('div','controls'),typeLabel=make('label','','View '),type=make('select');type.setAttribute('aria-label',card.title+' chart type');for(const option of kinds){const node=make('option','',option[0].toUpperCase()+option.slice(1));node.value=option;type.append(node);}type.value=kind;typeLabel.append(type);controls.append(typeLabel);
    if(available.length>1){const toggles=make('div','series');for(const key of available){const labelNode=make('label');const check=make('input');check.type='checkbox';check.checked=true;check.addEventListener('change',()=>{selected=check.checked?[...selected,key]:selected.filter((item)=>item!==key);draw();});labelNode.append(check,document.createTextNode(label(result,key)));toggles.append(labelNode);}controls.append(toggles);}
    section.append(controls);const content=make('div');section.append(content);
    function draw(){content.replaceChildren();if(kind==='table')drawTable(content,card,result,selected);else if(kind==='metric'){const row=result.rows[0];if(!row){content.append(make('p','empty','No saved values.'));return;}for(const key of selected){content.append(make('p','muted',label(result,key)),make('p','metric',format(value(row,key),unit(result,key))));}if(result.rows.length>1)content.append(make('p','muted','Showing the first row. Switch to table for all rows.'));}else drawChart(content,card,result,kind,selected);}
    type.addEventListener('change',()=>{kind=type.value;draw();});draw();
    const meta=make('div','meta');
    const noun=result.query.aggregation==='raw'||!result.query.group_by?'result rows':'result groups';
    meta.append(make('p','',result.rows.length+' of '+result.total_rows+' '+noun+' saved in this snapshot.'));
    if(result.total_rows>result.rows.length)meta.append(make('p','',
      'Query limit omitted '+(result.total_rows-result.rows.length)+' '+noun+'; charts, tables, and CSV use only saved data.'));
    meta.append(make('p','',result.source.label+' · '+result.source.kind+' · as of '+result.source.as_of));
    for(const note of result.source.notes)meta.append(make('p','',note));
    section.append(meta);cards.append(section);
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
