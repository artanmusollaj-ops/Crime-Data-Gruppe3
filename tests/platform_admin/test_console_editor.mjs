/** Reine Frontend-Vertragstests: node tests/platform_admin/test_console_editor.mjs */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdtempSync,unlinkSync,rmdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

const html=readFileSync(new URL('../../src/crime/platform_admin/static/index.html',import.meta.url),'utf8');
// Derselbe Code, den Flask ausliefert; keine zweite Implementierung im Test.
const start=html.indexOf('let consoleLanguage=');
const end=html.indexOf('const proposalLabels=',start);
const temporary=mkdtempSync(join(tmpdir(),'crime-editor-test-'));
const modulePath=join(temporary,'core.mjs');
writeFileSync(modulePath,html.slice(start,end)+'\nexport {validateProposalSettings,parseConsoleCSV,settingsChanges,rebaseProposalSettings,proposalImportJobs,normalizeProposalReason}; export const language=v=>consoleLanguage=v;');
let core;
try{core=await import(pathToFileURL(modulePath).href)}finally{unlinkSync(modulePath);rmdirSync(temporary)}
const settings={scope_start:'2021-01-01',scope_end_exclusive:'2027-01-01',maximum_unmapped_ratio:0.05,jobs:[
 {name:'chicago_daily',task:'daily_chicago',enabled:false,at_utc:'07:15',year:2026,lookback_days:14},
 {name:'detroit_full',task:'full_detroit',enabled:false,at_utc:'06:15',years:[2024,2025,2026]}
]};
let passed=0;
function check(name,fn){fn();passed++;}
check('Aktuelle Konfiguration ist gültig',()=>core.validateProposalSettings(settings));
for(const [name,mutate] of [
 ['gleiche Zeitraumgrenzen',v=>v.scope_end_exclusive=v.scope_start],
 ['ungültiger Kalendertag',v=>v.scope_start='2026-02-30'],
 ['fehlender Zeitraum',v=>delete v.scope_start],
 ['negative Quote',v=>v.maximum_unmapped_ratio=-0.1],
 ['Quote über 100 Prozent',v=>v.maximum_unmapped_ratio=1.01],
 ['leere numerische Eingabe',v=>v.maximum_unmapped_ratio=NaN],
 ['Boolean statt Quote',v=>v.maximum_unmapped_ratio=true],
 ['unbekanntes Feld',v=>v.command='anything'],
 ['gleiche Jobnamen',v=>v.jobs.push({...v.jobs[0]})],
 ['unbekannter Auftrag',v=>v.jobs[0].task='shell'],
 ['ungültige Uhrzeit',v=>v.jobs[0].at_utc='24:00'],
 ['ungültige Automatik',v=>v.jobs[0].enabled='true'],
 ['leere Detroit-Jahre',v=>v.jobs[1].years=[]],
 ['doppelte Detroit-Jahre',v=>v.jobs[1].years=[2024,2024]],
 ['zu viele Detroit-Jahre',v=>v.jobs[1].years=Array.from({length:26},(_,i)=>2001+i)],
 ['Tatjahr bei Detroit',v=>v.jobs[1].year=2024],
 ['Kalenderjahre bei Chicago',v=>v.jobs[0].years=[2024]],
 ['Chicago-Lookback abweichend',v=>v.jobs[0].lookback_days=15],
 ['Lookback für Detroit Full',v=>v.jobs[1].lookback_days=14],
 ['fehlendes Chicago-Tatjahr',v=>delete v.jobs[0].year],
 ['unbekannte Joboption',v=>v.jobs[0].credentials='x'],
 ['ungültiger Jobname',v=>v.jobs[0].name='Name With Spaces']
])check(name,()=>{const v=structuredClone(settings);mutate(v);assert.throws(()=>core.validateProposalSettings(v))});
check('Prozentdarstellung bleibt API-Verhältnis',()=>{const v=structuredClone(settings);v.maximum_unmapped_ratio=4/100;core.validateProposalSettings(v);assert.equal(core.settingsChanges(settings,v)[0].after,0.04)});
check('Umordnung von Aufträgen ist keine fachliche Änderung',()=>{const v=structuredClone(settings);v.jobs.reverse();assert.deepEqual(core.settingsChanges(settings,v),[])});
check('Neuen Auftrag auch mit unbekanntem Namen nachvollziehbar erkennen',()=>{const v=structuredClone(settings);v.jobs.push({name:'quality_extra',task:'checks',enabled:false,at_utc:'08:00'});assert.ok(core.settingsChanges(settings,v).some(x=>x.key==='jobs/quality_extra'))});
check('CSV erhält führende Nullen und zitierte Kommas',()=>{assert.deepEqual(core.parseConsoleCSV('code,description\r\n0010,"Text, mit Komma"\r\n0020,"Ein ""Zitat"""'),[{code:'0010',description:'Text, mit Komma'},{code:'0020',description:'Ein "Zitat"'}])});
check('Basiswechsel erhält fremde Änderungen',()=>{
 const draft=structuredClone(settings),current=structuredClone(settings);draft.jobs[1].at_utc='06:30';current.maximum_unmapped_ratio=0.03;current.jobs[0].year=2025;
 const merged=core.rebaseProposalSettings(settings,draft,current);assert.equal(merged.jobs[1].at_utc,'06:30');assert.equal(merged.jobs[0].year,2025);assert.equal(merged.maximum_unmapped_ratio,0.03);assert.equal(settings.jobs[1].at_utc,'06:15');
});
check('Entfernte Aufträge bleiben nach Basiswechsel entfernt',()=>{const draft=structuredClone(settings);draft.jobs.pop();assert.equal(core.rebaseProposalSettings(settings,draft,settings).jobs.length,1)});
check('Englische Validierung ohne Änderung der API-Werte',()=>{core.language('en');const v=structuredClone(settings);v.jobs[0].lookback_days=20;assert.throws(()=>core.validateProposalSettings(v),/fixed 14-day/);assert.equal(v.jobs[0].task,'daily_chicago')});
const importJobs=['full_chicago','daily_chicago','full_detroit','delta_detroit','daily_detroit','rebuild','checks'].map(task=>({name:task,task,enabled:false}));
for(const [city,kind,task] of [['chicago','full','full_chicago'],['chicago','delta','daily_chicago'],['detroit','full','full_detroit'],['detroit','delta','delta_detroit']])check(city+' '+kind+' zeigt nur den passenden Import',()=>assert.deepEqual(core.proposalImportJobs(importJobs,city,kind).map(j=>j.task),[task]));
check('Unbekannte Stadt startet keinen Ersatzauftrag',()=>assert.deepEqual(core.proposalImportJobs(importJobs,'unknown','full'),[]));
check('Mehrere Aufträge derselben Ladeart bleiben auswählbar',()=>assert.equal(core.proposalImportJobs([...importJobs,{name:'full_extra',task:'full_detroit'}],'detroit','full').length,2));
check('Mehrzeilige Begründung erfüllt den API-Vertrag',()=>assert.equal(core.normalizeProposalReason('  Erste Zeile\r\nZweite Zeile\n  '),'Erste Zeile Zweite Zeile'));
export const result={passed};
console.log(`${passed} Frontend-Vertragstests bestanden`);
