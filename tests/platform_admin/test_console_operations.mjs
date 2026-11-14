/** Zustandsgrenzen der bestehenden Betriebsaktionen im Frontend. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const html=readFileSync(new URL('../../src/crime/platform_admin/static/index.html',import.meta.url),'utf8');
new vm.Script(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
const source=html.slice(html.indexOf('function operationPayload('),html.indexOf('function operationFacts('));
const context=vm.createContext({});vm.runInContext(source,context);
const revision={resource:'settings',decision:'approve',actor:'Artan'},impact={status:'AWAITING_GIT'};
const action=(r=revision,i=impact,g=null,j=null,e=true,roles=['engineer','release_manager'],actor='Christian')=>context.publicationAction(r,i,g,j,e,roles,actor);
let passed=0;function check(name,fn){fn();passed++}
check('Syntax des gesamten ausgelieferten Scripts',()=>assert.ok(source));
check('Freigegebenen Antrag als PR anlegen',()=>assert.equal(action(),'git-open'));
check('Offenen PR durch zweite Person mergen',()=>assert.equal(action(revision,impact,{state:'PR_OPEN'}),'git-merge'));
check('Selbstmerge bleibt gesperrt',()=>assert.equal(action(revision,impact,{state:'PR_OPEN'},null,true,['release_manager'],' artan '),null));
check('Ohne Git keine Aktion',()=>assert.equal(action(revision,impact,null,null,false),null));
check('Ohne Rolle keine Aktion',()=>assert.equal(action(revision,impact,null,null,true,[]),null));
check('Ohne Freigabe keine Aktion',()=>assert.equal(action({...revision,decision:null}),null));
check('Fehlgeschlagener Impact erlaubt keinen PR',()=>assert.equal(action(revision,{status:'FAILED'}),null));
for(const status of ['QUEUED','RUNNING'])check(status+' sperrt erneute Einreichung',()=>assert.equal(action(revision,impact,null,{status}),null));
check('Bestätigter Merge wird nicht wiederholt',()=>assert.equal(action(revision,impact,{state:'MERGED'}),null));
check('Unbestätigten Merge erneut prüfen',()=>assert.equal(action(revision,impact,{state:'MERGED_UNVERIFIED'}),'git-merge'));
check('Bereitstellung nur für denselben aktiven Release grün',()=>assert.equal(context.analysisReadiness('r1',{status:'SUCCEEDED',release_id:'r1'}),true));
for(const a of [{},{status:'RUNNING',release_id:'r1'},{status:'PARTIAL',release_id:'r1'},{status:'SUCCEEDED',release_id:'r0'}])check('Unvollständiger oder veralteter Nachweis nicht grün',()=>assert.equal(context.analysisReadiness('r1',a),false));
check('Ohne aktiven Release kein Bereitschaftsnachweis',()=>assert.equal(context.analysisReadiness(null,{status:'SUCCEEDED'}),false));
check('Ungültiges Protokollpayload bricht Anzeige nicht ab',()=>assert.equal(Object.keys(context.operationPayload({payload:'{'})).length,0));
check('Protokoll gehört zum konkreten Antrag',()=>assert.equal(context.operationPayload({payload:'{"id":"revision-2"}'}).id,'revision-2'));
const current={active_release_id:'release-2',mapping:{id:'m'},settings:{id:'s'}};
const reviewed={status:'AWAITING_GIT',baseline_release_id:'release-1',spec:'{"base_heads":{"mapping":"m","settings":"s"}}'};
check('Gewechseltes Release blockiert den geprüften Git-Ablauf',()=>assert.ok(context.staleReview(reviewed,current)));
check('Unveränderte Prüfbasis lässt den Git-Ablauf zu',()=>assert.equal(context.staleReview({...reviewed,baseline_release_id:'release-2'},current),false));
check('Impact nur bei gescheiterter Berechnung erneut anbieten',()=>{
 const open={id:'r'};
 assert.ok(context.canRetryImpact(open,{status:'FAILED'},[],['engineer']));
 assert.equal(context.canRetryImpact(open,{status:'READY'},[],['engineer']),false);
 assert.equal(context.canRetryImpact(open,{status:'FAILED'},[{revision_id:'r',status:'QUEUED'}],['engineer']),false);
 assert.equal(context.canRetryImpact(revision,{status:'FAILED'},[],['engineer']),false);
});
// Ausgehende Verträge ohne Worker, GitHub oder Dateischreibzugriff prüfen.
const queueSource=html.slice(html.indexOf('async function queueOperation('),html.indexOf('function renderOperationViews('));
const calls=[];
Object.assign(context,{tr:x=>x,confirm:()=>true,api:async(kind,payload)=>calls.push({kind,payload}),normalizeProposalReason:x=>x.trim().replace(/\s+/g,' '),message:()=>{},refreshOperations:async()=>{},renderInbox:()=>{},state:{revisions:[]},selectedRevision:null});
vm.runInContext(queueSource,context);
await assert.rejects(context.queueOperation('git-open','r2','  ','PR'),/Begründung/);passed++;
await context.queueOperation('git-open','r2','Begründung\nmit Referenz','PR');
check('PR-Aktion verwendet exakt den geöffneten Antrag',()=>assert.equal(calls[0].payload.id,'r2'));
check('Mehrzeilige Begründung bleibt API-kompatibel',()=>assert.equal(calls[0].payload.reason,'Begründung mit Referenz'));
await context.queueOperation('serving',null,'Wiederholung','Serving');
check('Bereitstellung überlässt die Releaseauswahl dem Server',()=>assert.equal(calls[1].payload.id,null));
context.confirm=()=>false;await context.queueOperation('backup',null,'Test','Backup');
check('Abbruch sendet keinen Auftrag',()=>assert.equal(calls.length,2));

function node(textContent=''){
 return {textContent,children:[],dataset:{},attributes:{},append(...children){this.children.push(...children)},
  setAttribute(name,value){this.attributes[name]=value},
  replaceChildren(...children){this.children=children}};
}
const nodes=new Map();
const getNode=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)};
const labels=box=>box.children.flatMap(child=>[child.textContent,...labels(child)]);
const r={...revision,id:'r'};
let shownImpact=reviewed;
Object.assign(context,{
 $:getNode,document:{querySelector:()=>node()},element:(_tag,label)=>node(label),
 button:(box,label,onclick,disabled=false)=>{const b=node(label);Object.assign(b,{onclick,disabled});box.append(b);return b},
 requestImpact:()=>shownImpact,renderRequestGit:()=>{},gitChanges:new Map(),gitJobs:new Map(),
 operationsData:{operations:[]},revisionsById:new Map(),gitEnabled:true,impactLabels:{},
 operationFacts:()=>{},operationLog:()=>{},own:()=>context.state.operator===r.actor
});
context.state={...current,roles:['reviewer','engineer'],operator:'Christian',release_events:[]};
vm.runInContext(html.slice(html.indexOf('function renderRequestPublication('),html.indexOf('function renderImpactAttempts(')),context);
const feedback=getNode('request-git-feedback'),git=getNode('request-git-actions');
context.renderRequestPublication(r);
check('Reviewer kann den veralteten Workflow retournieren',()=>{
 assert.ok(labels(feedback).includes('Workflow an Antragsteller retournieren'));
 assert.ok(!labels(feedback).includes('Vorschlag auf aktuelle Basis übertragen'));
 assert.equal(git.children[0].disabled,true);
});
context.state.operator='Artan';
context.renderRequestPublication(r);
check('Antragsteller sieht Übertragung mit Hinweis zur automatischen Berechnung',()=>{
 assert.ok(labels(feedback).includes('Vorschlag auf aktuelle Basis übertragen'));
 assert.ok(labels(feedback).includes('Der Impact wird automatisch neu berechnet.'));
 assert.ok(!labels(feedback).includes('Workflow an Antragsteller retournieren'));
 const [transfer,hint]=feedback.children.at(-1).children;
 assert.equal(transfer.attributes['aria-describedby'],hint.id);
 assert.equal(hint.children[0].attributes['aria-hidden'],'true');
});
shownImpact={...reviewed,status:'WITHDRAWN'};
context.state.operator='Christian';
context.state.release_events=[{revision_id:'r',action:'PROPOSAL_REBASED',evidence:'{"new_revision_id":"r2"}'}];
context.revisionsById.set('r2',{id:'r2'});
context.renderRequestPublication(r);
check('Reviewer sieht den neuen Vorschlag ohne doppelte Rückgabe',()=>{
 assert.match(labels(feedback).join(' '),/Neuberechnung des Impacts.*bereits ausgelöst/);
 assert.ok(labels(feedback).includes('Neuen Vorschlag öffnen'));
 assert.ok(!labels(feedback).includes('Workflow an Antragsteller retournieren'));
});
const featuredSource=html.slice(html.indexOf('function featuredEtlJobs('),html.indexOf('function renderRunningJobs('));
vm.runInContext(featuredSource,context);
check('ETL-Übersicht zeigt laufende Jobs und danach den letzten beendeten Lauf',()=>{
 const older={id:'older',impact:{},status:'SUCCEEDED',finished_at:'2026-11-14T08:00:00Z'};
 const failed={id:'failed',impact:{},status:'FAILED',finished_at:'2026-11-14T09:00:00Z'};
 const running={id:'active',impact:{},status:'RUNNING'};
 const importJob={id:'import',status:'SUCCEEDED',finished_at:'2026-11-14T10:00:00Z'};
 assert.equal(context.featuredEtlJobs([older,importJob,running,failed])[0],running);
 assert.equal(context.featuredEtlJobs([older,importJob,failed])[0],failed);
});
console.log(`${passed} Betriebsansicht-Prüfungen bestanden`);
