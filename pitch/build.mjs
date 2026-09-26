import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Presentation, PresentationFile } from '@oai/artifact-tool';

const ROOT = path.resolve(import.meta.dirname, '..');
const WORKSPACE = path.resolve(import.meta.dirname);
const SKILL_DIR = '/Users/utsavsharma/.codex/plugins/cache/openai-primary-runtime/presentations/26.923.10815/skills/presentations';
const PYTHON = '/Users/utsavsharma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const TMP = path.join(WORKSPACE, '.build');
const OUT = path.join(WORKSPACE, 'out');
const version = process.env.DECK_VERSION || 'v7';
const FINAL = path.join(OUT, `barn-owl-three-minute-pitch-${version}.pptx`);
const { applyPresentationChartFont, finalizePresentation } = await import(
  pathToFileURL(path.join(SKILL_DIR, 'container_tools/artifact_tool_utils.mjs')).href
);
await fs.mkdir(TMP, { recursive: true });
await fs.mkdir(OUT, { recursive: true });
const backtest = JSON.parse(await fs.readFile(path.join(ROOT, 'model/out/backtest.json'), 'utf8'));
const cells = JSON.parse(await fs.readFile(path.join(ROOT, 'model/out/cells.json'), 'utf8')).cells;
const east = cells.find(x => x.h3 === '892a1008d97ffff');
const west = cells.find(x => x.h3 === '892a10721a7ffff');
if (!east || !west) throw new Error('Pitch comparison cells missing from model export');
const s = backtest.summary;
const font = 'Helvetica Neue';
const c = {
  navy: '#102635', ink: '#18313D', teal: '#087E83', mint: '#AEE5D2',
  coral: '#D96C50', paper: '#F8F8F2', pale: '#E6ECE8', muted: '#52656B',
  white: '#FFFFFF', sand: '#F2E8D8',
};
const p = Presentation.create({slideSize:{width:1280,height:720}});

function txt(slide, value, x,y,w,h, size=28, color=c.ink, bold=false, align='left') {
  const sh = slide.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  sh.text = value;
  sh.text.style = {typeface:font,fontSize:size,color,bold,alignment:align,verticalAlignment:'middle',autoFit:'none'};
  return sh;
}
function line(slide,x,y,w,color=c.pale,h=2){slide.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill:color,line:{fill:'none',width:0}})}
function base(title,num){
  const slide=p.slides.add(); slide.background.fill=c.paper;
  txt(slide,title,80,42,1120,74,40,c.navy,true);
  line(slide,80,123,1120,c.pale,2);
  txt(slide,String(num).padStart(2,'0'),1150,660,45,28,14,c.muted,false,'right');
  return slide;
}
function notes(slide,text,source='') {
  slide.speakerNotes.textFrame.setText(`${text}\n\nSource: ${source}`);
}

// 1. The reporting gap.
{
  const slide=p.slides.add(); slide.background.fill=c.navy;
  txt(slide,'BARN OWL',80,88,1100,95,80,c.white,true);
  txt(slide,'Find rat risk where 311 is quiet',80,205,1080,73,43,c.mint,false);
  line(slide,80,329,1080,c.teal,4);
  txt(slide,'A 311 complaint is a report.\nIt is not a rat count.',80,370,1040,150,45,c.white,true);
  txt(slide,'NYC inspections give us another signal: active rat signs found on swept blocks.',80,574,1080,66,27,c.mint);
  notes(slide,
    'New York records rat complaints, but a call depends on someone choosing to report. Barn Owl asks where active rat signs might be found even when 311 is quiet. We use the city\'s inspections of swept blocks as an independent outcome for training and backtesting. That inspection sample still has limits, which I will show on the evidence slide.',
    'model/README.md, model/05_backtest.py; plan/master-plan.md §10');
}

// 2. The two signals and the map.
{
  const slide=base('Two signals, one map',2);
  txt(slide,'A',80,175,80,74,61,c.coral,true);
  txt(slide,'Complaint model',168,170,395,50,33,c.navy,true);
  txt(slide,'Ranks expected 311 reports',168,222,390,45,25,c.muted);
  txt(slide,'B',80,331,80,74,61,c.teal,true);
  txt(slide,'Active-sign model',168,327,460,50,33,c.navy,true);
  txt(slide,'Uses physical and environmental features; no complaint counts',168,381,470,90,25,c.muted);
  line(slide,667,175,2,c.pale,370);
  txt(slide,'Silence Score',720,174,480,55,35,c.navy,true);
  txt(slide,'risk percentile − report percentile',720,232,470,53,27,c.teal);
  txt(slide,`East Harlem North   +${east.silence.toFixed(0)}`,720,333,480,48,31,c.teal,true);
  txt(slide,`${east.n_complaints_12m} complaints · ${(100*east.score_b).toFixed(1)}% modeled risk`,720,385,480,43,24,c.ink);
  txt(slide,`West Village   ${west.silence.toFixed(0)}`,720,467,480,48,31,c.muted,true);
  txt(slide,`${west.n_complaints_12m} complaints · ${(100*west.score_b).toFixed(1)}% modeled risk`,720,519,480,43,24,c.ink);
  txt(slide,'Prior 12 months · September 2026 export',720,603,480,37,19,c.muted);
  notes(slide,
    `Barn Owl scores each H3 cell and month two ways. Model A estimates complaints. Model B estimates the share of swept lots where an inspector would find active signs. Model B uses building and environmental features and omits complaint counts. A positive Silence Score means modeled risk ranks above reporting. In the September 2026 export, East Harlem North has zero complaints in the prior 12 months, ${(100*east.score_b).toFixed(1)}% modeled risk, and a +${east.silence.toFixed(0)} gap, rank ${east.rank_silent} of ${cells.length}. The West Village cell has ${west.n_complaints_12m} complaints, ${(100*west.score_b).toFixed(1)}% modeled risk, and a ${west.silence.toFixed(0)} gap. These are two examples of model output, not measured prevalence or a causal income result. On the live map, switch from complaints to risk, then silence.`,
    'model/out/cells.json; model/README.md §Key decisions; web/src');
}

// 3. Real exported backtest, with the evaluation population in view.
{
  const slide=base('The ranking finds more active signs',3);
  txt(slide,`${(100*s.mean_precision_silent).toFixed(1)}%`,80,156,369,114,88,c.teal,true);
  txt(slide,`vs ${(100*s.mean_precision_311).toFixed(1)}%`,444,178,425,75,52,c.coral,true);
  txt(slide,'Model B risk   /   prior 12-month 311 complaints',80,268,1100,55,27,c.ink);
  const chart=slide.charts.add('bar',{
    position:{left:80,top:336,width:1100,height:251},
    categories:['Model B risk','Prior rat findings','311 complaints','All swept cells'],
    series:[{name:'Active-sign share',values:[s.mean_precision_silent,s.mean_precision_positives,s.mean_precision_311,s.mean_precision_random],
      fill:c.teal,points:[{idx:1,fill:'#76979B'},{idx:2,fill:c.coral},{idx:3,fill:'#B9C8C5'}],valuesFormatCode:'0.0%'}],
    barOptions:{direction:'bar',grouping:'clustered',gapWidth:80},hasLegend:false,
    xAxis:{min:0,max:0.25,majorUnit:0.05,numberFormatCode:'0%',textStyle:{typeface:font,fontSize:15,fill:c.muted},majorGridlines:{style:'solid',fill:c.pale,width:1}},
    yAxis:{textStyle:{typeface:font,fontSize:20,fill:c.ink},line:{fill:'none',width:0}},
    dataLabels:{showValue:true,position:'outEnd',textStyle:{typeface:font,fontSize:17,fill:c.ink,bold:true}},
    chartFill:'none',plotAreaFill:'none',chartLine:{fill:'none',width:0},plotAreaLine:{fill:'none',width:0},
  });
  applyPresentationChartFont(chart,{fontFamily:font});
  txt(slide,`Mean monthly share of swept lots with active signs. Top ${backtest.k} swept cells each month, ${s.n_months} months (2016–2026).`,80,596,1100,46,21,c.muted);
  notes(slide,
    `This is the exported rolling backtest, not a simulation. Each month the model trains only on earlier months, then each method picks its top ${backtest.k} among cells that inspectors actually swept that month. We count the share of swept lots in those picked cells with active rat signs and average the monthly shares. Model B risk averages ${(100*s.mean_precision_silent).toFixed(1)}%, compared with ${(100*s.mean_precision_311).toFixed(1)}% for a ranking by prior 311 calls, a 4.3 point gap. The result is conditional on the swept sample; it does not tell us how many rats live citywide or prove a causal gain from deploying sensors. The quiet-block comparison is separate and is not the bar labeled Model B.`,
    'model/out/backtest.json and model/05_backtest.py');
}

// 4. Live loop, with the current backend behavior stated precisely.
{
  const slide=base('A node checks the next candidate',4);
  const steps=[
    {x:80,n:'1',t:'Pick a site',d:'Rank risk × data gap;\nsnap to a tree pit'},
    {x:363,n:'2',t:'See the prop',d:'Pi 5 + NoIR camera;\nPIR wakes capture'},
    {x:646,n:'3',t:'Send an event',d:'Detector test pending;\nrat crop and metadata'},
    {x:929,n:'4',t:'Update map',d:'Chosen Beta prior\nupdates the cell'},
  ];
  for(const q of steps){
    txt(slide,q.n,q.x,200,70,70,57,c.teal,true);
    txt(slide,q.t,q.x,294,235,57,27,c.navy,true);
    txt(slide,q.d,q.x,357,235,122,23,c.ink);
  }
  for(const x of [319,602,885]) txt(slide,'→',x,288,43,75,38,c.coral,true);
  line(slide,80,514,1120,c.pale,2);
  txt(slide,'Live demo',80,541,170,49,25,c.teal,true);
  txt(slide,'Toy rat → event feed → updated cell score',250,540,930,70,30,c.ink);
  notes(slide,
    'The planner has 20 candidate tree sites in its current export. At the table, the Pi 5 camera points down at a room-lit toy rat. The team reports camera, PIR, and IR capture working; that does not validate detector performance under IR. PIR only wakes capture; the detector must confirm the object. Its first version failed the event test and a second is being prepared. If an accepted rat event arrives, it posts a crop and metadata to the API. The API updates a chosen Beta prior for that cell, so the map score and candidate ranking can move. This is an event-driven re-rank, not live retraining of Model B. If the detector or network fails, say so and use the documented canned event only as a labeled fallback. Hold for the actual feed and map response before speaking the result.',
    'model/out/plan.json; node/DEBRIEF-utsav.md; api/posterior.py; plan/master-plan.md §9');
}

// 5. Honest demo state and proposed next test.
{
  const slide=base('What is real today',5);
  txt(slide,'Real',80,173,190,56,36,c.teal,true);
  txt(slide,'NYC data and sweep outcomes\nCell models and a 119-month backtest\nPi 5 camera, PIR and IR capture\nverified by onsite team',80,242,530,241,27,c.ink);
  line(slide,638,175,2,c.pale,352);
  txt(slide,'Demo and open work',696,173,480,56,36,c.coral,true);
  txt(slide,'Room-lit toy rat demo; detector validation pending\nChosen event prior; candidate re-rank\nNo field deployment or rat population count',696,242,485,240,27,c.ink);
  line(slide,80,531,1100,c.pale,2);
  txt(slide,'Next test',80,558,173,50,28,c.teal,true);
  txt(slide,'A supervised 50-node pilot, checked against later sweeps.',251,553,935,69,31,c.navy);
  notes(slide,
    'Here is the honest state. The data exports, model scores, and sweep backtest exist. Teammates report working Pi 5 camera, PIR, and infrared capture, and new IR rig footage exists. The table demo uses a room-lit toy rat. The first detector failed its event test; a second version is being prepared, and held-out clip and event tests remain pending. It is a prop demo, not a real-rat detector or a proven IR detector. The event posterior uses a chosen prior; an accepted event updates the served score and can change candidate order, but it does not retrain the city model. We have no field deployment and no rat population estimate. The next useful test would be a supervised 50-node pilot, evaluated against later proactive sweeps and false events.',
    'model/out/backtest.json; model/out/metrics.json; node/DEBRIEF-utsav.md; api/posterior.py; plan/master-plan.md §12');
}

const staging=path.join(WORKSPACE,'.codex-finalizer');
await fs.mkdir(staging,{recursive:true});
const candidate=path.join(staging,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidate);
const result=await finalizePresentation({
  workspaceDir:WORKSPACE,candidatePath:candidate,finalPath:FINAL,
  pythonExecutable:PYTHON,
  integrityValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],
  requiredNativeChartOwnerSlides:[3],
  materializeLiteralChartWorkbooks:true,
  fontPolicy:{basis:'design',families:[font]},
  verifyArtifactToolImport:true,
  receiptPath:path.join(staging,`barn-owl-${version}.validation.json`),
});
for(let i=0;i<5;i++){
  const slide=p.slides.getItem(i);
  const png=await p.export({slide,format:'png',scale:1});
  await fs.writeFile(path.join(TMP,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
console.log(JSON.stringify({final:FINAL,slides:5,summary:s,result},null,2));
