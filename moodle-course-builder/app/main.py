from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from typing import List
import json, re, zipfile, shutil, html, requests, base64
from pypdf import PdfReader
from docx import Document

BASE = Path(__file__).resolve().parent.parent
STATIC = BASE / "static"
SKILLS = BASE / "skills"
WORK = BASE / "work"
WORK.mkdir(exist_ok=True)
app = FastAPI(title="Moodle Course Builder V3")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

def read_skill(name):
    p = SKILLS / name
    if not p.exists():
        raise HTTPException(500, f"Skill fehlt: {name}")
    return p.read_text(encoding="utf-8")

def extract_text(path: Path):
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "\n\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    if ext == ".docx":
        d = Document(str(path))
        return "\n".join(p.text for p in d.paragraphs)
    if ext in {".txt", ".md", ".html", ".htm"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    raise HTTPException(400, f"Nicht unterstützter Dateityp: {ext}")

def clean(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json|html|text)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()

def llm_chat(cfg, system, user):
    provider = (cfg.get("provider") or "ollama").lower()
    url = (cfg.get("url") or "").rstrip("/")
    model = cfg.get("model") or ""
    api_key = cfg.get("api_key") or ""
    if not url: raise HTTPException(400, "Model-API-URL fehlt.")
    if not model: raise HTTPException(400, "Modellname fehlt.")
    headers = {"Content-Type": "application/json"}
    if api_key: headers["Authorization"] = f"Bearer {api_key}"
    try:
        if provider == "ollama":
            endpoint = url if url.endswith("/api/chat") else url + "/api/chat"
            payload = {"model": model, "stream": False, "messages": [
                {"role":"system","content":system},{"role":"user","content":user}],
                "options":{"temperature":0.2}}
            r = requests.post(endpoint, json=payload, headers=headers, timeout=600)
            r.raise_for_status()
            return r.json()["message"]["content"]
        endpoint = url if url.endswith("/chat/completions") else url + "/chat/completions"
        payload = {"model":model,"temperature":0.2,"messages":[
            {"role":"system","content":system},{"role":"user","content":user}]}
        r = requests.post(endpoint, json=payload, headers=headers, timeout=600)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except requests.RequestException as exc:
        detail = exc.response.text[:1000] if getattr(exc,"response",None) is not None else ""
        raise HTTPException(502, f"Model-API nicht erreichbar: {exc}. {detail}")
    except Exception as exc:
        raise HTTPException(502, f"Ungültige Model-API-Antwort: {exc}")

def tts_call(cfg, text):
    url = (cfg.get("url") or "").rstrip("/")
    if not url: raise HTTPException(400, "TTS-API-URL fehlt.")
    model = cfg.get("model") or "tts-1"
    voice = cfg.get("voice") or "alloy"
    api_key = cfg.get("api_key") or ""
    fmt = (cfg.get("format") or "mp3").lower()
    headers = {"Content-Type":"application/json"}
    if api_key: headers["Authorization"] = f"Bearer {api_key}"
    endpoint = url if url.endswith("/audio/speech") else url + "/audio/speech"
    payload = {"model":model,"voice":voice,"input":text,"response_format":fmt}
    try:
        r = requests.post(endpoint, json=payload, headers=headers, timeout=600)
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower()
        if "application/json" in ctype:
            data = r.json()
            for key in ("audio","audio_base64","data"):
                if isinstance(data.get(key), str):
                    try: return base64.b64decode(data[key]), fmt
                    except Exception: pass
            raise HTTPException(502, "TTS-API lieferte JSON, aber keine unterstützte Audiodatei.")
        return r.content, fmt
    except requests.RequestException as exc:
        detail = exc.response.text[:1000] if getattr(exc,"response",None) is not None else ""
        raise HTTPException(502, f"TTS-API nicht erreichbar: {exc}. {detail}")

@app.get("/", response_class=HTMLResponse)
def index(): return (STATIC/"index.html").read_text(encoding="utf-8")

@app.post("/api/test-model")
async def test_model(payload: dict):
    out = llm_chat(payload, "Antworte exakt mit OK", "Verbindungstest. Antworte ausschließlich mit OK.")
    return {"ok":True,"response":clean(out)[:200]}

@app.post("/api/test-tts")
async def test_tts(payload: dict):
    audio, fmt = tts_call(payload, "Dies ist ein Test der Text-zu-Sprache-Verbindung.")
    media = "audio/mpeg" if fmt == "mp3" else f"audio/{fmt}"
    return Response(content=audio, media_type=media, headers={"X-Audio-Format":fmt})

@app.post("/api/analyze")
async def analyze(files:List[UploadFile]=File(...), provider:str=Form("ollama"), model_url:str=Form(...), model:str=Form(...), api_key:str=Form("")):
    chunks,names=[],[]
    for f in files:
        target=WORK/Path(f.filename).name; target.write_bytes(await f.read()); txt=extract_text(target)
        names.append(f.filename); chunks.append(f"### QUELLE: {f.filename}\n{txt}")
    source_text="\n\n".join(chunks)
    if len(source_text)>220000: source_text=source_text[:220000]+"\n[Quelltext gekürzt]"
    cfg={"provider":provider,"url":model_url,"model":model,"api_key":api_key}
    result=clean(llm_chat(cfg,read_skill("01_document_analysis.md"),source_text))
    try: parsed=json.loads(result)
    except Exception: parsed={"raw":result}
    return {"analysis":parsed,"source_text":source_text,"documents":names}

@app.post("/api/concept")
async def concept(payload:dict):
    settings = payload.get("course_settings") or {}
    try:
        slide_count = max(1, min(int(settings.get("slide_count", 10)), 100))
    except (TypeError, ValueError):
        slide_count = 10
    hints = str(settings.get("hints") or "").strip()[:8000]
    prompt=(
        "KURSVORGABEN:\n"
        f"- Gewünschte Länge: ungefähr {slide_count} Slides/Lerneinheiten. "
        "Erzeuge insgesamt möglichst genau diese Anzahl an sections über alle Module hinweg.\n"
        f"- Weitere Hinweise: {hints if hints else 'Keine zusätzlichen Hinweise.'}\n\n"
        "ANALYSE:\n"+json.dumps(payload.get("analysis"),ensure_ascii=False,indent=2)+
        "\n\nQUELLEN:\n"+payload.get("source_text","")[:150000]
    )
    out=clean(llm_chat(payload.get("model_api",{}),read_skill("02_course_concept.md"),prompt))
    try:return {"concept":json.loads(out)}
    except Exception:return {"concept":{"raw":out}}

@app.post("/api/expand-section")
async def expand_section(payload:dict):
    s=payload.get("section",{})
    prompt="ABSCHNITT:\n"+json.dumps(s,ensure_ascii=False,indent=2)+"\n\nQUELLEN:\n"+payload.get("source_text","")[:100000]+"\n\nANWEISUNG:\n"+(payload.get("instruction") or "Erstelle einen vollständigen Lernabschnitt.")
    out=clean(llm_chat(payload.get("model_api",{}),read_skill("03_content_editor.md"),prompt))
    return {"html":out}

@app.post("/api/edit")
async def edit(payload:dict):
    prompt="QUELLEN:\n"+payload.get("source_text","")[:100000]+"\n\nAKTUELLER INHALT:\n"+payload.get("html","")+"\n\nANWEISUNG:\n"+payload.get("instruction","")
    out=clean(llm_chat(payload.get("model_api",{}),read_skill("03_content_editor.md"),prompt))
    return {"html":out}

@app.post("/api/quiz")
async def quiz(payload:dict):
    count=max(1,min(int(payload.get("count",3)),10)); prompt=f"LERNTEXT:\n{payload.get('html','')}\n\nErzeuge {count} Fragen."
    out=clean(llm_chat(payload.get("model_api",{}),read_skill("04_quiz_generator.md"),prompt))
    try:return json.loads(out)
    except Exception:return {"questions":[],"raw":out}

@app.post("/api/generate-speech")
async def generate_speech(payload:dict):
    prompt=f"KAPITEL: {payload.get('title','')}\n\nLERNINHALT:\n{payload.get('html','')}\n\nErzeuge daraus einen natürlichen Sprechtext."
    out=clean(llm_chat(payload.get("model_api",{}),read_skill("05_speech_script.md"),prompt))
    return {"speech_text":out}

SCORM_API='''var scorm={api:null,find:function(w){var n=0;while(w&&!w.API&&w.parent&&w.parent!==w&&n<10){w=w.parent;n++;}return w&&w.API?w.API:null;},init:function(){this.api=this.find(window);if(this.api){try{this.api.LMSInitialize("");var s=this.api.LMSGetValue("cmi.core.lesson_status");if(!s||s==="not attempted")this.api.LMSSetValue("cmi.core.lesson_status","incomplete");}catch(e){}}},finish:function(score){if(!this.api)return;try{this.api.LMSSetValue("cmi.core.score.raw",String(score));this.api.LMSSetValue("cmi.core.score.min","0");this.api.LMSSetValue("cmi.core.score.max","100");this.api.LMSSetValue("cmi.core.lesson_status",score>=70?"passed":"completed");this.api.LMSCommit("");}catch(e){}},close:function(){if(this.api){try{this.api.LMSFinish("");}catch(e){}}}};window.addEventListener("load",function(){scorm.init();});window.addEventListener("beforeunload",function(){scorm.close();});'''
COURSE_JS='''function gradeQuiz(){const qs=[...document.querySelectorAll(".scorm-question")];if(!qs.length){scorm.finish(100);alert("Kurs abgeschlossen.");return;}let correct=0;qs.forEach(q=>{const s=q.querySelector("input[type=radio]:checked"),fb=q.querySelector(".feedback");if(s){if(s.dataset.correct==="true"){correct++;fb.textContent="Richtig. "+(q.dataset.explanation||"");}else fb.textContent="Nicht richtig. "+(q.dataset.explanation||"");}else fb.textContent="Bitte eine Antwort auswählen.";});const score=Math.round(correct/qs.length*100);document.getElementById("scoreOut").textContent=`Ergebnis: ${correct}/${qs.length} (${score} %)`;scorm.finish(score);}'''
COURSE_CSS=''':root{--bg:#f4f6fa;--text:#1f2937;--accent:#2457d6;--border:#dbe2ea}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif;line-height:1.65}header{background:linear-gradient(135deg,#172f66,#3275e8);color:#fff;padding:38px 20px}header>div,main{width:min(980px,calc(100% - 30px));margin:auto}main{background:#fff;margin-top:24px;margin-bottom:50px;border:1px solid var(--border);border-radius:18px;padding:30px}nav{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--border);padding:10px 16px;z-index:5;overflow:auto;white-space:nowrap}nav a{display:inline-block;margin-right:14px;color:var(--accent);text-decoration:none}section{scroll-margin-top:65px;padding-top:6px}.sourcebox,.note,.example{padding:12px 14px;border-radius:10px;margin:14px 0}.sourcebox{background:#f8fafc;border:1px solid var(--border);font-size:.9rem;color:#64748b}.note{background:#eef3ff;border-left:5px solid var(--accent)}.example{background:#ecf9f1;border-left:5px solid #16804c}.chapter-audio{width:100%;margin:12px 0 18px}.abbr-table{width:100%;border-collapse:collapse;margin:14px 0}.abbr-table th,.abbr-table td{border:1px solid var(--border);padding:8px;text-align:left}.quiz{margin-top:30px;border-top:1px solid var(--border);padding-top:20px}.scorm-question{margin:20px 0;padding:16px;border:1px solid var(--border);border-radius:12px}.scorm-question label{display:block;padding:6px}.feedback{margin-top:8px;font-weight:600}button{background:var(--accent);color:#fff;border:0;border-radius:9px;padding:11px 16px;font-weight:700;cursor:pointer}@media(max-width:700px){main{padding:18px}}'''

def extract_abbreviations(sections):
    text_parts = []
    for section in sections:
        title = str(section.get("title", ""))
        content = re.sub(r"<[^>]+>", " ", str(section.get("html", "")))
        speech = str(section.get("speech_text", ""))
        text_parts.extend([title, content, speech])
    text = " ".join(text_parts)
    candidates = re.findall(r"\b[A-ZÄÖÜ][A-ZÄÖÜ0-9.-]{1,9}\b", text)
    stop = {"HTML","CSS","HTTP","HTTPS","SCORM","API","TTS","KI","AI","PDF","DOCX","TXT","JSON","URL","UTF"}
    seen = []
    for abbr in candidates:
        clean_abbr = abbr.strip(".-")
        if len(clean_abbr) < 2:
            continue
        if clean_abbr not in seen:
            seen.append(clean_abbr)
    return sorted(seen)

def render_quiz(questions):
    blocks=[]
    for i,q in enumerate(questions,1):
        ex=html.escape(str(q.get("explanation","")),quote=True); b=[f'<div class="scorm-question" data-explanation="{ex}"><strong>{i}. {html.escape(str(q.get("question","")))}</strong>']
        for a in q.get("answers",[]):
            b.append(f'<label><input type="radio" name="q{i}" data-correct="{"true" if a.get("correct") else "false"}"> {html.escape(str(a.get("text","")))}</label>')
        b.append('<div class="feedback"></div></div>');blocks.append("\n".join(b))
    if blocks:return '<section class="quiz"><h2>Abschlusstest</h2>'+"\n".join(blocks)+'<button onclick="gradeQuiz()">Auswerten</button><p id="scoreOut"></p></section>'
    return '<section class="quiz"><button onclick="gradeQuiz()">Kurs abschließen</button><p id="scoreOut"></p></section>'

@app.post("/api/export")
async def export_package(payload:dict):
    title=payload.get("title","Moodle Lernkurs"); sections=payload.get("sections",[]); quiz=payload.get("quiz",[]); tts_enabled=bool(payload.get("tts_enabled")); tts_cfg=payload.get("tts_api",{})
    course_settings = payload.get("course_settings") or {}
    safe=re.sub(r"[^a-zA-Z0-9_-]+","_",title).strip("_") or "kurs"; outdir=WORK/(safe+"_scorm")
    if outdir.exists():shutil.rmtree(outdir)
    outdir.mkdir(parents=True); nav=[];body=[];extra=[]
    for i,s in enumerate(sections,1):
        sid=f"sec{i}"; st=str(s.get("title",f"Kapitel {i}")); nav.append(f'<a href="#{sid}">{html.escape(st)}</a>'); audio_html=""; speech=(s.get("speech_text") or "").strip()
        if tts_enabled and speech:
            audio_bytes,fmt=tts_call(tts_cfg,speech); ext="mp3" if fmt=="mp3" else re.sub(r"[^a-z0-9]","",fmt) or "mp3"; fn=f"audio_{i}.{ext}"; (outdir/fn).write_bytes(audio_bytes);extra.append(fn);audio_html=f'<audio class="chapter-audio" controls preload="metadata" src="{fn}"></audio>'
        body.append(f'<section id="{sid}"><h2>{html.escape(st)}</h2>{audio_html}{s.get("html","")}</section>')
    abbreviations = extract_abbreviations(sections)
    abbr_rows = ''.join(f'<tr><td><strong>{html.escape(a)}</strong></td><td></td></tr>' for a in abbreviations)
    abbr_html = '<section id="abkuerzungen"><h2>Abkürzungsverzeichnis</h2>'
    if abbreviations:
        abbr_html += '<table class="abbr-table"><thead><tr><th>Abkürzung</th><th>Bedeutung</th></tr></thead><tbody>' + abbr_rows + '</tbody></table>'
    else:
        abbr_html += '<p>In diesem Kurs wurden keine Abkürzungen erkannt.</p>'
    abbr_html += '</section>'
    nav.append('<a href="#abkuerzungen">Abkürzungen</a>')
    full='<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+f'<title>{html.escape(title)}</title><link rel="stylesheet" href="style.css"></head><body><header><div><h1>{html.escape(title)}</h1></div></header><nav>{"".join(nav)}</nav><main>{"".join(body)}{abbr_html}{render_quiz(quiz)}</main><script src="scorm.js"></script><script src="course.js"></script></body></html>'
    file_nodes=''.join(f'<file href="{html.escape(f)}"/>' for f in extra)
    manifest='<?xml version="1.0" encoding="UTF-8"?>\n'+f'<manifest identifier="MANIFEST-{safe}" version="1.0" xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2" xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"><metadata><schema>ADL SCORM</schema><schemaversion>1.2</schemaversion></metadata><organizations default="ORG"><organization identifier="ORG"><title>{html.escape(title)}</title><item identifier="ITEM" identifierref="RES"><title>{html.escape(title)}</title></item></organization></organizations><resources><resource identifier="RES" type="webcontent" adlcp:scormtype="sco" href="index.html"><file href="index.html"/><file href="style.css"/><file href="scorm.js"/><file href="course.js"/>{file_nodes}</resource></resources></manifest>'
    (outdir/"index.html").write_text(full,encoding="utf-8");(outdir/"style.css").write_text(COURSE_CSS,encoding="utf-8");(outdir/"scorm.js").write_text(SCORM_API,encoding="utf-8");(outdir/"course.js").write_text(COURSE_JS,encoding="utf-8");(outdir/"imsmanifest.xml").write_text(manifest,encoding="utf-8")
    zp=WORK/(safe+"_SCORM12.zip")
    with zipfile.ZipFile(zp,"w",zipfile.ZIP_DEFLATED) as z:
        for p in outdir.iterdir():z.write(p,p.name)
    return FileResponse(zp,media_type="application/zip",filename=zp.name)
