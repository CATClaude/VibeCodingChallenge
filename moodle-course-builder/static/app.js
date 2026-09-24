const $=id=>document.getElementById(id);
const state={analysis:null,sourceText:"",documents:[],concept:null,slides:[],active:0,quiz:[],abbreviations:[],versions:[],undo:[],redo:[]};

function modelCfg(){return {provider:$('provider').value,url:$('modelUrl').value.trim(),model:$('model').value.trim(),api_key:$('modelKey').value.trim()}}
function ttsCfg(){return {url:$('ttsUrl').value.trim(),model:$('ttsModel').value.trim(),voice:$('ttsVoice').value.trim(),api_key:$('ttsKey').value.trim(),format:$('ttsFormat').value}}
function settings(){return {slide_count:Math.max(1,Math.min(100,Number($('slideCount').value)||10)),hints:$('courseHints').value.trim()}}
function msg(t){$('status').textContent=t;$('status').classList.add('show')}
function pipe(name,status,text){const el=document.querySelector('[data-pipe="'+name+'"]');if(!el)return;el.className=status;el.querySelector('span').textContent=text}
function current(){return state.slides[state.active]}
function snapshot(){syncCurrent();return JSON.stringify({slides:state.slides,quiz:state.quiz,abbreviations:state.abbreviations,title:$('courseTitle').value,settings:settings()})}
function pushUndo(){state.undo.push(snapshot());if(state.undo.length>40)state.undo.shift();state.redo=[]}
function restore(raw){const d=JSON.parse(raw);state.slides=d.slides||[];state.quiz=d.quiz||[];state.abbreviations=d.abbreviations||[];$('courseTitle').value=d.title||'';if(d.settings){$('slideCount').value=d.settings.slide_count||10;$('courseHints').value=d.settings.hints||''}state.active=Math.min(state.active,Math.max(0,state.slides.length-1));renderAll()}

function showTab(name){
 document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));
 document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
 const map={setup:'setupView',slides:'slidesView',audio:'audioView',quiz:'quizView',abbr:'abbrView',preview:'previewView'};
 $(map[name]).classList.add('active');
 if(name==='preview')renderPreview();
 if(name==='audio')renderAudio();
}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>showTab(b.dataset.tab));

$('files').onchange=()=>{$('fileSummary').textContent=$('files').files.length?`${$('files').files.length} Datei(en) ausgewählt`:'Noch keine Dateien ausgewählt.'};
$('speechEnabled').onchange=()=>{$('ttsSetup').classList.toggle('disabled',!$('speechEnabled').checked)};

$('testModel').onclick=async()=>{const st=$('modelStatus');st.textContent='Teste …';try{const r=await fetch('/api/test-model',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(modelCfg())});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Fehler');st.className='apiStatus ok';st.textContent='✓ Verbindung erfolgreich'}catch(e){st.className='apiStatus bad';st.textContent='✗ '+e.message}};
$('testTts').onclick=async()=>{const st=$('ttsStatus');st.textContent='Teste …';try{const r=await fetch('/api/test-tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(ttsCfg())});if(!r.ok){const d=await r.json();throw new Error(d.detail||'Fehler')}const blob=await r.blob();st.className='apiStatus ok';st.textContent='✓ Verbindung erfolgreich';const a=$('ttsTestAudio');a.src=URL.createObjectURL(blob);a.style.display='block'}catch(e){st.className='apiStatus bad';st.textContent='✗ '+e.message}};

async function analyzeDocuments(){
 pipe('analysis','running','läuft');
 const fd=new FormData();[...$('files').files].forEach(f=>fd.append('files',f));const c=modelCfg();fd.append('provider',c.provider);fd.append('model_url',c.url);fd.append('model',c.model);fd.append('api_key',c.api_key);
 const r=await fetch('/api/analyze',{method:'POST',body:fd});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Dokumentanalyse fehlgeschlagen');
 state.analysis=d.analysis;state.sourceText=d.source_text;state.documents=d.documents;pipe('analysis','done','fertig');
}
async function generatePlan(){
 pipe('concept','running','läuft');
 const r=await fetch('/api/concept',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({analysis:state.analysis,source_text:state.sourceText,model_api:modelCfg(),course_settings:settings()})});
 const d=await r.json();if(!r.ok)throw new Error(d.detail||'Slide-Plan fehlgeschlagen');
 state.concept=d.concept;state.slides=(d.concept.slides||[]).map((s,i)=>({id:s.id||`slide_${i+1}`,number:i+1,title:s.title||`Slide ${i+1}`,html:`<p>${s.content_plan||''}</p>`,sources:s.sources||[],speech_text:''}));
 if(state.slides.length!==settings().slide_count)throw new Error(`Erwartet: ${settings().slide_count} Slides, erhalten: ${state.slides.length}`);
 $('courseTitle').value=d.concept.course_title||$('courseTitle').value;pipe('concept','done',`${state.slides.length} Slides`);
}
async function expandAll(){
 pipe('content','running','0/'+state.slides.length);
 for(let i=0;i<state.slides.length;i++){
  const s=state.slides[i];
  const r=await fetch('/api/expand-section',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({section:{id:s.id,number:i+1,title:s.title,sources:s.sources},source_text:state.sourceText,instruction:'Erstelle genau den vollständigen Inhalt dieser einzelnen Slide. Keine weitere Slide und kein Kapitel erzeugen.',model_api:modelCfg()})});
  const d=await r.json();if(!r.ok)throw new Error(d.detail||`Slide ${i+1} konnte nicht erzeugt werden`);s.html=d.html;pipe('content','running',`${i+1}/${state.slides.length}`);
 }
 pipe('content','done',`${state.slides.length}/${state.slides.length}`);
}
async function speechFor(s){
 const r=await fetch('/api/generate-speech',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:s.title,html:s.html,model_api:modelCfg()})});
 const d=await r.json();if(!r.ok)throw new Error(d.detail||'Sprechtext fehlgeschlagen');s.speech_text=d.speech_text||'';
}
async function generateSpeechAll(){
 if(!$('speechEnabled').checked){pipe('audio','done','deaktiviert');return}
 pipe('audio','running','0/'+state.slides.length);
 for(let i=0;i<state.slides.length;i++){await speechFor(state.slides[i]);pipe('audio','running',`${i+1}/${state.slides.length}`)}
 pipe('audio','done','fertig');
}
async function generateQuiz(){
 pipe('quiz','running','läuft');
 const all=state.slides.map(s=>`<h2>${s.title}</h2>${s.html}`).join('\n');
 const r=await fetch('/api/quiz',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({html:all,count:Number($('quizCount').value)||3,model_api:modelCfg()})});
 const d=await r.json();if(!r.ok)throw new Error(d.detail||'Quiz fehlgeschlagen');state.quiz=d.questions||[];pipe('quiz','done',`${state.quiz.length} Fragen`);
}
async function generateAbbreviations(){
 pipe('abbr','running','läuft');
 const r=await fetch('/api/abbreviations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sections:state.slides,model_api:modelCfg()})});
 const d=await r.json();if(!r.ok)throw new Error(d.detail||'Abkürzungsverzeichnis fehlgeschlagen');state.abbreviations=d.abbreviations||[];pipe('abbr','done',`${state.abbreviations.length} Einträge`);
}
$('generateCourse').onclick=async()=>{
 if(!$('files').files.length){alert('Bitte zuerst Quelldokumente auswählen.');return}
 if($('speechEnabled').checked&&!$('ttsUrl').value.trim()){alert('Audio ist aktiviert. Bitte eine TTS API URL eintragen.');return}
 $('pipeline').style.display='grid';['analysis','concept','content','audio','quiz','abbr'].forEach(n=>pipe(n,'','wartet'));
 try{
  msg('Kurs wird vollständig erzeugt …');await analyzeDocuments();await generatePlan();await expandAll();await generateSpeechAll();await generateQuiz();await generateAbbreviations();state.active=0;renderAll();msg(`Fertig: ${state.slides.length} Inhalts-Slides + 1 Abkürzungs-Slide.`);showTab('slides');
 }catch(e){msg('Fehler: '+e.message);document.querySelectorAll('.pipeline .running').forEach(x=>x.className='error')}
};

function syncCurrent(){const s=current();if(!s)return;s.title=$('slideTitle').value;s.html=$('editor').innerHTML}
function renderSlides(){
 const list=$('slideList');list.innerHTML='';
 state.slides.forEach((s,i)=>{const d=document.createElement('div');d.className='slideItem'+(i===state.active?' active':'');d.draggable=true;d.innerHTML=`<strong>${i+1}. ${s.title}</strong><div class="muted">${(s.sources||[]).join(', ')}</div>`;d.onclick=()=>selectSlide(i);d.ondragstart=e=>{d.classList.add('dragging');e.dataTransfer.setData('text/plain',String(i))};d.ondragend=()=>d.classList.remove('dragging');d.ondragover=e=>e.preventDefault();d.ondrop=e=>{e.preventDefault();pushUndo();const from=Number(e.dataTransfer.getData('text/plain'));const[x]=state.slides.splice(from,1);state.slides.splice(i,0,x);state.slides.forEach((s,j)=>{s.number=j+1;s.id=`slide_${j+1}`});state.active=i;renderAll()};list.appendChild(d)});
}
function selectSlide(i){syncCurrent();state.active=i;const s=current();$('slideHeading').textContent=`Slide ${i+1}`;$('slideTitle').value=s?.title||'';$('editor').innerHTML=s?.html||'<p>Kein Inhalt</p>';renderSources();renderSlides()}
function renderSources(){const box=$('sourceTags');box.innerHTML='';const s=current();if(!s)return;s.sources=s.sources||[];state.documents.forEach(name=>{const l=document.createElement('label');l.className='tag';l.innerHTML=`<input type="checkbox" ${s.sources.includes(name)?'checked':''}> ${name}`;l.querySelector('input').onchange=e=>{if(e.target.checked&&!s.sources.includes(name))s.sources.push(name);if(!e.target.checked)s.sources=s.sources.filter(x=>x!==name)};box.appendChild(l)})}
function renderQuiz(){const b=$('quizList');b.innerHTML='';state.quiz.forEach((q,i)=>{const d=document.createElement('div');d.className='quizCard';d.innerHTML=`<strong>${i+1}. ${q.question}</strong><div class="muted">${(q.answers||[]).map(a=>(a.correct?'✓ ':'')+a.text).join('<br>')}</div>`;b.appendChild(d)})}
function renderAudio(){const b=$('audioList');b.innerHTML='';state.slides.forEach((s,i)=>{const d=document.createElement('div');d.className='audioCard';d.innerHTML=`<strong>Slide ${i+1}: ${s.title}</strong><textarea class="speechText">${s.speech_text||''}</textarea>`;d.querySelector('textarea').oninput=e=>s.speech_text=e.target.value;b.appendChild(d)})}
function renderAbbr(){const b=$('abbrList');if(!state.abbreviations.length){b.innerHTML='<p>Keine Abkürzungen erkannt.</p>';return}b.innerHTML='<table class="abbrTable"><thead><tr><th>Abkürzung</th><th>Bedeutung</th></tr></thead><tbody>'+state.abbreviations.map(x=>`<tr><td><strong>${x.abbr}</strong></td><td>${x.meaning}</td></tr>`).join('')+'</tbody></table>'}
let previewIndex=0;
function renderPreview(){
 const slides=[...state.slides.map((s,i)=>({title:s.title,html:s.html,label:`Slide ${i+1}`})),{title:'Abkürzungsverzeichnis',html:state.abbreviations.length?'<table class="abbrTable"><tbody>'+state.abbreviations.map(a=>`<tr><td><strong>${a.abbr}</strong></td><td>${a.meaning}</td></tr>`).join('')+'</tbody></table>':'<p>Keine Abkürzungen erkannt.</p>',label:'Abkürzungen'}];
 previewIndex=Math.min(previewIndex,slides.length-1);
 $('preview').innerHTML='<div class="previewShell"><div class="previewProgress"><div style="width:'+(((previewIndex+1)/slides.length)*100)+'%"></div></div>'+slides.map((s,i)=>`<article class="previewSlide ${i===previewIndex?'active':''}"><div class="muted">${s.label}</div><h2>${s.title}</h2>${s.html}</article>`).join('')+`<div class="previewNav"><button id="prevPreview" class="secondary" ${previewIndex===0?'disabled':''}>← Zurück</button><span class="previewCounter">${previewIndex+1} / ${slides.length}</span><button id="nextPreview" ${previewIndex===slides.length-1?'disabled':''}>Weiter →</button></div></div>`;
 $('prevPreview').onclick=()=>{previewIndex--;renderPreview()};$('nextPreview').onclick=()=>{previewIndex++;renderPreview()};
}
function renderAll(){renderSlides();renderQuiz();renderAbbr();if(state.slides.length)selectSlide(Math.min(state.active,state.slides.length-1));renderAudio()}

$('slideTitle').onchange=()=>{pushUndo();syncCurrent();renderSlides()};$('editor').oninput=syncCurrent;
document.querySelectorAll('[data-cmd]').forEach(b=>b.onclick=()=>document.execCommand(b.dataset.cmd,false,null));
document.querySelectorAll('[data-block]').forEach(b=>b.onclick=()=>document.execCommand('formatBlock',false,b.dataset.block));
$('linkBtn').onclick=()=>{const u=prompt('URL:');if(u)document.execCommand('createLink',false,u)};
$('aiEdit').onclick=async()=>{if(!current())return;pushUndo();const r=await fetch('/api/edit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({html:$('editor').innerHTML,instruction:$('instruction').value,source_text:state.sourceText,model_api:modelCfg()})});const d=await r.json();if(!r.ok){msg('Fehler: '+(d.detail||'Unbekannt'));return}$('editor').innerHTML=d.html;syncCurrent()};
$('expandBtn').onclick=async()=>{if(!current())return;pushUndo();const s=current();const r=await fetch('/api/expand-section',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({section:{id:s.id,number:s.number,title:s.title,sources:s.sources},source_text:state.sourceText,instruction:'Erzeuge den vollständigen Inhalt nur für diese einzelne Slide.',model_api:modelCfg()})});const d=await r.json();if(!r.ok){msg('Fehler: '+(d.detail||'Unbekannt'));return}$('editor').innerHTML=d.html;syncCurrent()};
$('addSlide').onclick=()=>{pushUndo();state.slides.push({id:`slide_${state.slides.length+1}`,number:state.slides.length+1,title:'Neue Slide',html:'<p>Neuer Inhalt</p>',sources:[],speech_text:''});state.active=state.slides.length-1;renderAll()};
$('deleteSlide').onclick=()=>{if(!state.slides.length)return;pushUndo();state.slides.splice(state.active,1);state.slides.forEach((s,i)=>{s.id=`slide_${i+1}`;s.number=i+1});state.active=Math.max(0,Math.min(state.active,state.slides.length-1));renderAll()};
$('quizBtn').onclick=async()=>{try{await generateQuiz();renderQuiz()}catch(e){msg('Fehler: '+e.message)}};
$('abbrBtn').onclick=async()=>{try{await generateAbbreviations();renderAbbr()}catch(e){msg('Fehler: '+e.message)}};
$('generateAllSpeech').onclick=async()=>{try{await generateSpeechAll();renderAudio()}catch(e){msg('Fehler: '+e.message)}};
$('undoBtn').onclick=()=>{if(!state.undo.length)return;state.redo.push(snapshot());restore(state.undo.pop())};$('redoBtn').onclick=()=>{if(!state.redo.length)return;state.undo.push(snapshot());restore(state.redo.pop())};
$('saveVersion').onclick=()=>{const name='Version '+new Date().toLocaleString();state.versions.push({name,data:snapshot()});const o=document.createElement('option');o.value=state.versions.length-1;o.textContent=name;$('versions').appendChild(o)};
$('loadVersion').onclick=()=>{if($('versions').value==='')return;restore(state.versions[Number($('versions').value)].data)};
$('saveLocal').onclick=()=>{localStorage.setItem('moodleCourseBuilderProject',snapshot());msg('Projekt gespeichert.')};
$('loadLocal').onclick=()=>{const x=localStorage.getItem('moodleCourseBuilderProject');if(x){restore(x);msg('Projekt geladen.');showTab('slides')}};

$('exportBtn').onclick=async()=>{
 syncCurrent();msg('SCORM wird erstellt …');
 const r=await fetch('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('courseTitle').value,sections:state.slides,quiz:state.quiz,abbreviations:state.abbreviations,tts_enabled:$('speechEnabled').checked,tts_api:ttsCfg(),model_api:modelCfg(),course_settings:settings()})});
 if(!r.ok){let d={};try{d=await r.json()}catch(e){}msg('Exportfehler: '+(d.detail||r.statusText));return}
 const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='moodle_SCORM12.zip';document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);msg('SCORM erstellt.');
};

$('ttsSetup').classList.add('disabled');renderAll();
