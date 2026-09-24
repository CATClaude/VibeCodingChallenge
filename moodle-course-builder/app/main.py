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
    cfg = payload.get("model_api", {})
    base_prompt = (
        "KURSVORGABEN:\n"
        f"- Erzeuge EXAKT {slide_count} Inhalts-Slides. Nicht mehr und nicht weniger.\n"
        "- Keine Kapitel, Module oder Unterkapitel erzeugen. Nur einzelne Slides.\n"
        "- Die Abkürzungs-Slide wird später automatisch ergänzt und zählt NICHT zu dieser Zahl.\n"
        f"- Weitere Hinweise: {hints if hints else 'Keine zusätzlichen Hinweise.'}\n\n"
        "ANALYSE:\n" + json.dumps(payload.get("analysis"), ensure_ascii=False, indent=2) +
        "\n\nQUELLEN:\n" + payload.get("source_text", "")[:150000]
    )
    last = None
    for attempt in range(3):
        correction = "" if attempt == 0 else (
            f"\n\nKORREKTUR: Gib zwingend genau {slide_count} Objekte im Array slides zurück."
        )
        out = clean(llm_chat(cfg, read_skill("02_course_concept.md"), base_prompt + correction))
        try:
            data = json.loads(out)
            slides = data.get("slides", [])
            if isinstance(slides, list) and len(slides) == slide_count:
                for i, slide in enumerate(slides, 1):
                    slide["id"] = f"slide_{i}"
                    slide["number"] = i
                data["slides"] = slides
                return {"concept": data}
            last = data
        except Exception:
            last = {"raw": out}
    raise HTTPException(502, f"Das Modell hat nach 3 Versuchen nicht exakt {slide_count} Slides erzeugt.")

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
    prompt=f"SLIDE: {payload.get('title','')}\n\nLERNINHALT:\n{payload.get('html','')}\n\nErzeuge daraus einen natürlichen Sprechtext."
    out=clean(llm_chat(payload.get("model_api",{}),read_skill("05_speech_script.md"),prompt))
    return {"speech_text":out}

SCORM_API='''var scorm={api:null,find:function(w){var n=0;while(w&&!w.API&&w.parent&&w.parent!==w&&n<10){w=w.parent;n++;}return w&&w.API?w.API:null;},init:function(){this.api=this.find(window);if(this.api){try{this.api.LMSInitialize("");var s=this.api.LMSGetValue("cmi.core.lesson_status");if(!s||s==="not attempted")this.api.LMSSetValue("cmi.core.lesson_status","incomplete");}catch(e){}}},setLocation:function(i){if(this.api){try{this.api.LMSSetValue("cmi.core.lesson_location",String(i));this.api.LMSCommit("");}catch(e){}}},getLocation:function(){if(!this.api)return 0;try{return parseInt(this.api.LMSGetValue("cmi.core.lesson_location")||"0",10)||0;}catch(e){return 0;}},finish:function(score){if(!this.api)return;try{this.api.LMSSetValue("cmi.core.score.raw",String(score));this.api.LMSSetValue("cmi.core.score.min","0");this.api.LMSSetValue("cmi.core.score.max","100");this.api.LMSSetValue("cmi.core.lesson_status",score>=70?"passed":"completed");this.api.LMSCommit("");}catch(e){}},close:function(){if(this.api){try{this.api.LMSFinish("");}catch(e){}}}};window.addEventListener("load",function(){scorm.init();});window.addEventListener("beforeunload",function(){scorm.close();});'''
COURSE_JS='''var currentPage=0;
function pages(){return Array.from(document.querySelectorAll(".course-page"));}
function showPage(i){
 var all=pages(); if(!all.length)return;
 currentPage=Math.max(0,Math.min(i,all.length-1));
 all.forEach(function(p,n){p.classList.toggle("active",n===currentPage);});
 var c=document.getElementById("pageCounter"); if(c)c.textContent=(currentPage+1)+" / "+all.length;
 var bar=document.getElementById("progressBar"); if(bar)bar.style.width=(((currentPage+1)/all.length)*100)+"%";
 var prev=document.getElementById("prevPage"),next=document.getElementById("nextPage");
 if(prev)prev.disabled=currentPage===0;
 if(next)next.disabled=currentPage===all.length-1;
 scorm.setLocation(currentPage);
 window.scrollTo(0,0);
}
function nextPage(){showPage(currentPage+1);}
function prevPage(){showPage(currentPage-1);}
function gradeQuiz(){
 const qs=[...document.querySelectorAll(".scorm-question")];
 if(!qs.length){scorm.finish(100);return;}
 let correct=0;
 qs.forEach(q=>{const s=q.querySelector("input[type=radio]:checked"),fb=q.querySelector(".feedback");if(s){if(s.dataset.correct==="true"){correct++;fb.textContent="Richtig. "+(q.dataset.explanation||"");}else fb.textContent="Nicht richtig. "+(q.dataset.explanation||"");}else fb.textContent="Bitte eine Antwort auswählen.";});
 const score=Math.round(correct/qs.length*100);document.getElementById("scoreOut").textContent="Ergebnis: "+correct+"/"+qs.length+" ("+score+" %)";scorm.finish(score);
}
window.addEventListener("load",function(){setTimeout(function(){showPage(scorm.getLocation());},0);});
'''
COURSE_CSS=''':root{--bg:#eef2f7;--text:#1f2937;--accent:#2457d6;--border:#dbe2ea}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif;line-height:1.6}header{background:linear-gradient(135deg,#172f66,#3275e8);color:#fff;padding:22px}header>div,.course-shell{width:min(1000px,calc(100% - 28px));margin:auto}.course-shell{margin-top:20px;margin-bottom:30px}.progress{height:7px;background:#dfe5ed;border-radius:999px;overflow:hidden}.progress>div{height:100%;background:var(--accent);width:0}.course-page{display:none;min-height:560px;background:#fff;border:1px solid var(--border);border-radius:16px;padding:32px;margin-top:12px}.course-page.active{display:block}.slide-kicker{color:#64748b;font-size:.9rem;font-weight:700}.chapter-audio{width:100%;margin:12px 0 18px}.abbr-table{width:100%;border-collapse:collapse}.abbr-table th,.abbr-table td{border:1px solid var(--border);padding:9px;text-align:left}.scorm-question{margin:18px 0;padding:14px;border:1px solid var(--border);border-radius:10px}.scorm-question label{display:block;padding:6px}.feedback{font-weight:650;margin-top:8px}.course-nav{display:flex;align-items:center;justify-content:space-between;margin-top:12px}.course-nav button,.scorm-question button{background:var(--accent);color:#fff;border:0;border-radius:9px;padding:10px 15px;font-weight:700;cursor:pointer}.course-nav button:disabled{opacity:.4}.counter{font-weight:700}@media(max-width:700px){.course-page{padding:18px;min-height:480px}}'''

def course_plaintext(sections):
    parts = []
    for section in sections:
        title = str(section.get("title", ""))
        content = re.sub(r"<[^>]+>", " ", str(section.get("html", "")))
        speech = str(section.get("speech_text", ""))
        parts.extend([title, content, speech])
    return re.sub(r"\s+", " ", " ".join(parts)).strip()

def extract_abbreviation_candidates(sections):
    text = course_plaintext(sections)
    candidates = re.findall(r"\b[A-ZÄÖÜ][A-ZÄÖÜ0-9.-]{1,9}\b", text)
    seen = []
    for abbr in candidates:
        clean_abbr = abbr.strip(".-")
        if len(clean_abbr) >= 2 and clean_abbr not in seen:
            seen.append(clean_abbr)
    return sorted(seen)

def build_abbreviation_directory(sections, model_api):
    candidates = extract_abbreviation_candidates(sections)
    if not candidates:
        return []
    plain = course_plaintext(sections)[:100000]
    prompt = (
        "KURSINHALT:\n" + plain +
        "\n\nERKANNTE ABKÜRZUNGEN:\n" + ", ".join(candidates) +
        "\n\nErstelle daraus das Abkürzungsverzeichnis. Nimm nur Abkürzungen auf, "
        "die im Kurs tatsächlich als Abkürzungen verwendet werden. Die Langform darf nur "
        "aus dem Kursinhalt sicher ableitbar sein. Wenn sie nicht sicher ableitbar ist, "
        "setze meaning auf 'Im Kursmaterial nicht eindeutig ausgeschrieben'."
    )
    try:
        out = clean(llm_chat(model_api, read_skill("06_abbreviation_directory.md"), prompt))
        data = json.loads(out)
        items = data.get("abbreviations", [])
        result = []
        for item in items:
            abbr = str(item.get("abbr", "")).strip()
            meaning = str(item.get("meaning", "")).strip()
            if abbr and abbr in candidates:
                result.append({"abbr": abbr, "meaning": meaning or "Im Kursmaterial nicht eindeutig ausgeschrieben"})
        return sorted(result, key=lambda x: x["abbr"].casefold())
    except Exception:
        return [{"abbr": a, "meaning": "Im Kursmaterial nicht eindeutig ausgeschrieben"} for a in candidates]

@app.post("/api/abbreviations")
async def abbreviations(payload:dict):
    items = build_abbreviation_directory(payload.get("sections", []), payload.get("model_api", {}))
    return {"abbreviations": items}

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
    title = payload.get("title", "Moodle Lernkurs")
    sections = payload.get("sections", [])
    quiz = payload.get("quiz", [])
    tts_enabled = bool(payload.get("tts_enabled"))
    tts_cfg = payload.get("tts_api", {})
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", title).strip("_") or "kurs"
    outdir = WORK / (safe + "_scorm")
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)

    pages_html = []
    extra = []
    for i, s in enumerate(sections, 1):
        st = str(s.get("title", f"Slide {i}"))
        speech = (s.get("speech_text") or "").strip()
        audio_html = ""
        if tts_enabled and speech:
            audio_bytes, fmt = tts_call(tts_cfg, speech)
            ext = "mp3" if fmt == "mp3" else re.sub(r"[^a-z0-9]", "", fmt) or "mp3"
            fn = f"audio_{i}.{ext}"
            (outdir / fn).write_bytes(audio_bytes)
            extra.append(fn)
            audio_html = f'<audio class="chapter-audio" controls preload="metadata" src="{fn}"></audio>'
        pages_html.append(
            f'<section class="course-page"><div class="slide-kicker">Slide {i}</div>'
            f'<h2>{html.escape(st)}</h2>{audio_html}{s.get("html","")}</section>'
        )

    abbreviations = payload.get("abbreviations")
    if not isinstance(abbreviations, list):
        abbreviations = build_abbreviation_directory(sections, payload.get("model_api", {}))
    rows = ''.join(
        f'<tr><td><strong>{html.escape(str(x.get("abbr","")))}</strong></td>'
        f'<td>{html.escape(str(x.get("meaning","")))}</td></tr>' for x in abbreviations
    )
    abbr_body = (
        '<table class="abbr-table"><thead><tr><th>Abkürzung</th><th>Bedeutung</th></tr></thead><tbody>'
        + rows + '</tbody></table>'
        if abbreviations else '<p>In diesem Kurs wurden keine Abkürzungen erkannt.</p>'
    )
    pages_html.append(
        '<section class="course-page"><div class="slide-kicker">Zusatz-Slide</div>'
        '<h2>Abkürzungsverzeichnis</h2>' + abbr_body + '</section>'
    )

    if quiz:
        quiz_html = render_quiz(quiz)
        pages_html.append(
            '<section class="course-page"><div class="slide-kicker">Abschlusstest</div>'
            + quiz_html + '</section>'
        )

    full = (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{html.escape(title)}</title><link rel="stylesheet" href="style.css"></head><body>'
        f'<header><div><h1>{html.escape(title)}</h1></div></header>'
        '<div class="course-shell"><div class="progress"><div id="progressBar"></div></div>'
        + ''.join(pages_html) +
        '<div class="course-nav"><button id="prevPage" onclick="prevPage()">← Zurück</button>'
        '<span id="pageCounter" class="counter"></span>'
        '<button id="nextPage" onclick="nextPage()">Weiter →</button></div></div>'
        '<script src="scorm.js"></script><script src="course.js"></script></body></html>'
    )
    file_nodes = ''.join(f'<file href="{html.escape(f)}"/>' for f in extra)
    manifest = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<manifest identifier="MANIFEST-{safe}" version="1.0" '
        'xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2" '
        'xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2">'
        '<metadata><schema>ADL SCORM</schema><schemaversion>1.2</schemaversion></metadata>'
        '<organizations default="ORG"><organization identifier="ORG">'
        f'<title>{html.escape(title)}</title><item identifier="ITEM" identifierref="RES">'
        f'<title>{html.escape(title)}</title></item></organization></organizations>'
        '<resources><resource identifier="RES" type="webcontent" adlcp:scormtype="sco" href="index.html">'
        '<file href="index.html"/><file href="style.css"/><file href="scorm.js"/><file href="course.js"/>'
        f'{file_nodes}</resource></resources></manifest>'
    )
    (outdir/"index.html").write_text(full,encoding="utf-8")
    (outdir/"style.css").write_text(COURSE_CSS,encoding="utf-8")
    (outdir/"scorm.js").write_text(SCORM_API,encoding="utf-8")
    (outdir/"course.js").write_text(COURSE_JS,encoding="utf-8")
    (outdir/"imsmanifest.xml").write_text(manifest,encoding="utf-8")
    zp = WORK / (safe + "_SCORM12.zip")
    with zipfile.ZipFile(zp,"w",zipfile.ZIP_DEFLATED) as z:
        for p in outdir.iterdir():
            z.write(p,p.name)
    return FileResponse(zp,media_type="application/zip",filename=zp.name)
