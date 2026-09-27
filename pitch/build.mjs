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
const version = process.env.DECK_VERSION || 'v18';
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

// 4. Physical prototype and recorded-footage software loop.
{
  const slide=base('Recorded footage reaches the map',4);
  const steps=[
    {y:158,n:'1',t:'Pick a site',d:'Rank risk and the data gap; select a tree pit'},
    {y:250,n:'2',t:'Capture',d:'Physical owl rig: Pi 5 camera and PIR sensor'},
    {y:342,n:'3',t:'Detect',d:'Room-lit plush model; live positive test pending'},
    {y:434,n:'4',t:'Update the map',d:'Accepted events update a chosen prior'},
  ];
  for(const q of steps){
    txt(slide,q.n,80,q.y,52,64,43,c.teal,true);
    txt(slide,q.t,147,q.y,640,37,28,c.navy,true);
    txt(slide,q.d,147,q.y+37,660,42,22,c.ink);
  }
  const rigPhoto=await fs.readFile(path.join(WORKSPACE,'assets/physical-prototype.jpeg'));
  slide.images.add({blob:new Uint8Array(rigPhoto),contentType:'image/jpeg',alt:'Physical owl camera rig and laptop at the hackathon',fit:'contain',position:{left:905,top:150,width:285,height:365}});
  txt(slide,'Physical prototype at the hackathon',915,516,275,43,17,c.muted);
  line(slide,80,561,1120,c.pale,2);
  txt(slide,'Earlier replay',80,579,200,49,25,c.teal,true);
  txt(slide,'1 event · score 9.2% → 13.0% · rank 11 → 2',280,577,900,70,27,c.ink);
  notes(slide,
    'The planner has 20 candidate tree sites in its current export. The table prop is room-lit. In an earlier local Mac replay using the V2 detector, original camera footage from zoom15_b at 59–63 seconds passed through the exported ONNX model, the Pi Detector class and its three-hit rules, crop generation, and the local API. Exactly one event at confidence 0.860 was accepted. The served cell score moved from 0.0923 to 0.1297; the plan candidate moved from rank 11 to 2. The frontend screenshot showed the crop, one sighting, and rank 2. V5 has separate detector development results but has not been verified through the same API path. The earlier software loop used saved video on a Mac. V5 also ran on a saved frame on the physical Pi; positive live-camera detection remains unverified. PIR only wakes capture; the detector decides. Team-reported IR capture does not validate the model under IR. An accepted event updates a chosen Beta prior and can rerank candidates; it does not retrain Model B. If demonstrating from recorded footage on stage, name it as recorded. A physical Pi trigger can be shown only if it works in a fresh test.',
    'vision/replay_video.py; vision/RUNBOOK.md; vision/TRAINING_RESULTS.md; model/out/plan.json; api/posterior.py; team local replay and frontend screenshot 2026-09-26; team physical-rig photo IMG_1788.jpeg 2026-09-26');
}

// 5. Honest demo state and proposed next test.
{
  const slide=base('What is real today',5);
  txt(slide,'Real',80,173,190,56,36,c.teal,true);
  txt(slide,'NYC data and sweep outcomes\nCell models and a 119-month backtest\nPi camera and PIR at the hackathon\nSaved-frame ONNX inference on Pi',80,242,530,241,27,c.ink);
  line(slide,638,175,2,c.pale,352);
  txt(slide,'Demo and open work',696,173,480,56,36,c.coral,true);
  txt(slide,'Fresh V5 test did not establish .90 AP50\nLabels and edge misses need work\nTuned development: .961 weakest clip\nEarlier footage → API → map verified\nRoom-lit prop demo; no field deployment',696,242,485,240,24,c.ink);
  line(slide,80,531,1100,c.pale,2);
  txt(slide,'Next',80,558,173,50,28,c.teal,true);
  txt(slide,'Improve the detector and repeat a frozen test before a pilot.',251,553,935,69,29,c.navy);
  notes(slide,
    'Here is the honest state. The data exports, model scores, and sweep backtest exist. Teammates report working Pi 5 camera, PIR, and infrared capture; the prop footage is room-lit. V4 scored rat AP50 .925806 on 59 adjacent frames from the same camera session, then .882675 on 439 reviewed new-room frames, below the .90 box target. Its recorded replay missed a parked plush and fired once on a dark case. V5 used those prior new-room clips as development data. The locked V5 checkpoint reached .960806 rat AP50 on its weakest selected development clip and .975279 combined over 146 development frames. A frozen fresh test of 369 reviewed frames measured .615779 rat AP50 and .492688 person AP50 as run, with .703102 rat AP50 on the positive clip; PyTorch and ONNX AP matched exactly. Completed source-only review of all 193 positive sampled frames found shifted and oversized rat reference boxes. Thirty-one source-estimated correction proposals are drafts and were not adopted or rescored; the frozen labels, model settings, and original report remain unchanged. The .615779 figure is the as-run score with known annotation defects, not a corrected performance estimate. The as-run test did not establish the .90 rat-box target. The fresh replay emitted 34 events in the positive clip; independent review of every saved event crop beside its source frame confirmed all 34 target the visible plush. The negative clip emitted zero events over 175.937 seconds. These are repeated firings across only two complete coarse positive presences, not 34 independent encounters or a 20-push recall test. The negative clip is shorter than three minutes, so the formal event gate is incomplete. The second presence first alerted 58.890 seconds after its start, largely while the plush was near the image edge. Source-only annotation QC is complete; the 31 proposed corrections remain unadopted. The V5 ONNX ran on a saved plush frame on the physical Pi at 60.23 milliseconds median, confidence .931. A separate earlier Mac replay using V2 footage carried one accepted event through detector rules and local API to the visible map. A later Pi live-camera trial had no plush target; positive live-camera integration is pending. AP50 is a box detection measure, not accuracy or rat population prevalence. No IR or wild-rat detector test and no field deployment have been done. An accepted event updates a chosen prior and can change candidate order; it does not retrain Model B. Improve the detector and repeat a frozen test before a field pilot.',
    'vision/V5_FRESH_RESULTS.md (completed crop and source-only annotation reviews; 31 correction proposals unadopted); pitch/evidence/v5-fresh-test-provisional.json (frozen as-run box scores); vision/artifacts/rat-litroom-v5-development-candidate-20260927.zip: reports/metrics.json, reports/candidate_lock.json, reports/dev_replay, reports/pi_saved_frame_smoke.json; vision/artifacts/rat-litroom-v4-new-room-evaluation-20260927.zip; model/out/backtest.json; api/posterior.py');
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
