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
const version = process.env.DECK_VERSION || 'v19';
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

// 4. Verified live Pi-to-map prototype loop.
{
  const slide=base('A live Pi event reaches the map',4);
  const steps=[
    {y:158,n:'1',t:'Pick a site',d:'Rank risk and the data gap'},
    {y:250,n:'2',t:'Capture',d:'Pi 5 camera watches the room-lit prop'},
    {y:342,n:'3',t:'Detect',d:'V5 processed 1,346 live frames in 90 s'},
    {y:434,n:'4',t:'Update the map',d:'One genuine event reached the local API'},
  ];
  for(const q of steps){
    txt(slide,q.n,80,q.y,52,64,43,c.teal,true);
    txt(slide,q.t,147,q.y,470,37,28,c.navy,true);
    txt(slide,q.d,147,q.y+37,475,42,22,c.ink);
  }
  line(slide,645,175,2,c.pale,344);
  const liveMap=await fs.readFile(path.join(WORKSPACE,'assets/live-pi-map-20260927.png'));
  slide.images.add({blob:new Uint8Array(liveMap),contentType:'image/png',alt:'Live Barn Owl map after one accepted Pi plush event; two sightings and site ranked first',fit:'contain',position:{left:675,top:182,width:525,height:295}});
  txt(slide,'Live map · two sightings · site rank 1',675,483,525,48,18,c.muted);
  line(slide,80,561,1120,c.pale,2);
  txt(slide,'Live loop',80,579,190,49,25,c.teal,true);
  txt(slide,'1 event · score 13.0% → 16.2% · rank 2 → 1',270,577,910,70,27,c.ink);
  notes(slide,
    'The room-lit physical Pi 5 camera fed the locked V5 ONNX detector for 89.859 seconds. The observer inferred 1,346 frames at 14.98 processed frames per second, mean 59.15 milliseconds per frame. It saved six event crops; root and the API reviewer inspected all six and each showed the same visible plush. Exactly one genuine event from the live Pi observer was relayed to the local API on the Mac, which returned HTTP 200 and accepted it. The node was live-v5-observer in H3 cell 892a100d467ffff at 2026-09-27 04:52:03.340 UTC. The served score changed from .1297 to .1618, sightings from one to two, and candidate rank from two to one. The visible map screenshot shows the new sighting and rank-one site. The other five saved events were not posted. This verifies a supervised live Pi camera-to-detector-to-local-API-to-map loop on a room-lit plush prop. It does not establish field reliability, wild-rat or infrared performance, or the .90 detector target. PIR wakes capture; the detector decides. An accepted event updates a chosen Beta prior and reranks candidates; it does not retrain Model B.',
    'pitch/evidence/v5-live-run-stats.json; pitch/evidence/v5-live-integration-result.json; pitch/assets/live-pi-map-20260927.png; api/posterior.py; vision/V5_FORMAL_EVENT_RESULTS.md');
}

// 5. Honest demo state and proposed next test.
{
  const slide=base('What is real today',5);
  txt(slide,'Real',80,173,190,56,36,c.teal,true);
  txt(slide,'NYC data and sweep outcomes\nCell models and a 119-month backtest\nPi camera and PIR at the hackathon\nLive plush event reached the map',80,242,530,241,27,c.ink);
  line(slide,638,175,2,c.pale,352);
  txt(slide,'Demo and open work',696,173,480,56,36,c.coral,true);
  txt(slide,'Fresh V5 box target not established\nFormal replay: 17 false alerts / 190 s\nCap and shoe caused those alerts\nRoom-lit prop; no field deployment\nNo IR or wild-rat validation',696,242,485,240,24,c.ink);
  line(slide,80,531,1100,c.pale,2);
  txt(slide,'Next',80,558,173,50,28,c.teal,true);
  txt(slide,'Improve cap and shoe handling, then test on new footage.',251,553,935,69,29,c.navy);
  notes(slide,
    'The city data, cell models and 119-month swept-cell backtest exist. The live room-lit plush Pi-to-local-API-to-map loop is verified on one accepted event; see slide four. Detector readiness is separate. V4 scored rat AP50 .925806 on 59 adjacent same-session frames, then .882675 on 439 reviewed new-room frames. V5 used those new-room clips for tuning and scored .960806 rat AP50 on its weakest development clip and .975279 combined over 146 development frames. Its frozen fresh box test measured .615779 rat AP50 as run on 369 frames, with exact PyTorch/ONNX AP parity. Completed source-only annotation QC found shifted and oversized reference boxes; 31 correction proposals remain unadopted and no corrected AP exists. The .90 box target is not established. In a separate fixed recorded-video formal event test, 18 of 19 source-reviewed plush appearances eventually had verified alerts, or 94.7 percent observed on that source; the brief first appearance was missed. All 43 emitted positive crops showed plush, but include repeat firings. The negative clip produced 17 false events over 190.409 seconds, or 5.357 per minute, above the required fewer than .5 per minute. Sixteen false alerts targeted one cap and one targeted a partial shoe. The formal event test failed, and 19 appearances also fall short of the specified 20-push coverage. These event and box measurements do not establish general field performance. There is no IR or wild-rat validation, field deployment, or rat population estimate. Improve cap and shoe handling, then evaluate on new independent footage before any pilot.',
    'vision/V5_FORMAL_EVENT_RESULTS.md; vision/V5_FRESH_RESULTS.md; pitch/evidence/v5-live-integration-result.json; pitch/evidence/v5-live-run-stats.json; vision/artifacts/rat-litroom-v5-development-candidate-20260927.zip; model/out/backtest.json; api/posterior.py');
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
