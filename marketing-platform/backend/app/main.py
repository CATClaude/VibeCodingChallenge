from pathlib import Path
import json, os, re, shutil, uuid
import httpx
from docx import Document
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from pypdf import PdfReader

ROOT=Path("/app/data/projects"); ROOT.mkdir(parents=True,exist_ok=True)
BASE=os.getenv("OLLAMA_BASE_URL","http://host.docker.internal:11434").rstrip("/")
MODEL=os.getenv("OLLAMA_MODEL","qwen3:latest")
MAX_MB=int(os.getenv("MAX_UPLOAD_MB","25"))
ALLOWED={".pdf",".docx",".txt",".md",".markdown"}

app=FastAPI(title="Marketing Platform API")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])

class ProjectIn(BaseModel):
    name:str
    audience:str=""
    goal:str="Leads und Verkäufe"
    tone:str="professionell, klar, vertrauenswürdig"

class Ollama(BaseModel):
    base_url:str=BASE
    model:str=MODEL

class Generate(BaseModel):
    ollama:Ollama=Ollama()
    additional_context:str=""

def pdir(pid:str):
    p=ROOT/pid
    if not p.exists(): raise HTTPException(404,"Projekt nicht gefunden")
    return p

def meta(pid:str):
    return json.loads((pdir(pid)/"project.json").read_text("utf-8"))

def save_meta(pid:str,m:dict):
    (pdir(pid)/"project.json").write_text(json.dumps(m,ensure_ascii=False,indent=2),"utf-8")

def extract(path:Path):
    ext=path.suffix.lower()
    if ext in {".txt",".md",".markdown"}: return path.read_text("utf-8",errors="ignore")
    if ext==".pdf": return "\n\n".join((x.extract_text() or "") for x in PdfReader(str(path)).pages)
    if ext==".docx": return "\n".join(x.text for x in Document(str(path)).paragraphs)
    return ""

def sources(pid:str):
    u=pdir(pid)/"uploads"; parts=[]
    for f in sorted(u.glob("*")):
        if f.is_file() and f.suffix.lower() in ALLOWED:
            t=extract(f).strip()
            if t: parts.append(f"--- QUELLE: {f.name} ---\n{t}")
    return "\n\n".join(parts)[:120000]

async def chat(cfg:Ollama,system:str,user:str,temp=.35):
    url=cfg.base_url.rstrip("/")+"/api/chat"
    async with httpx.AsyncClient(timeout=300) as c:
        try:
            r=await c.post(url,json={"model":cfg.model,"stream":False,"messages":[{"role":"system","content":system},{"role":"user","content":user}],"options":{"temperature":temp}})
            r.raise_for_status()
        except Exception as e:
            raise HTTPException(502,f"Ollama nicht erreichbar oder Fehler: {e}")
    out=(r.json().get("message") or {}).get("content","").strip()
    if not out: raise HTTPException(502,"Ollama lieferte keine Antwort")
    return out

@app.get("/api/health")
def health(): return {"ok":True,"default_model":MODEL,"default_base_url":BASE}

@app.post("/api/ollama/test")
async def test_ollama(cfg:Ollama):
    async with httpx.AsyncClient(timeout=10) as c:
        try:
            r=await c.get(cfg.base_url.rstrip("/")+"/api/tags"); r.raise_for_status()
            return {"ok":True,"models":[m.get("name") for m in r.json().get("models",[])]}
        except Exception as e: raise HTTPException(502,str(e))

@app.get("/api/projects")
def list_projects():
    out=[]
    for d in ROOT.iterdir():
        f=d/"project.json"
        if f.exists():
            try: out.append(json.loads(f.read_text("utf-8")))
            except: pass
    return sorted(out,key=lambda x:x.get("name","").lower())

@app.post("/api/projects")
def create_project(req:ProjectIn):
    pid=uuid.uuid4().hex[:12]; d=ROOT/pid; (d/"uploads").mkdir(parents=True)
    m={"id":pid,**req.model_dump(),"files":[],"has_brief":False,"has_site":False}
    (d/"project.json").write_text(json.dumps(m,ensure_ascii=False,indent=2),"utf-8")
    return m

@app.post("/api/projects/{pid}/upload")
async def upload(pid:str,files:list[UploadFile]=File(...)):
    d=pdir(pid)/"uploads"; m=meta(pid); added=[]
    for f in files:
        name=re.sub(r"[^A-Za-z0-9._-]+","_",Path(f.filename or "upload").name)[:180]
        if Path(name).suffix.lower() not in ALLOWED: raise HTTPException(415,f"Nicht unterstützt: {name}")
        data=await f.read()
        if len(data)>MAX_MB*1024*1024: raise HTTPException(413,f"{name} ist größer als {MAX_MB} MB")
        (d/name).write_bytes(data); added.append(name)
    m["files"]=sorted(set(m.get("files",[])+added)); save_meta(pid,m)
    return {"saved":added,"project":m}

@app.post("/api/projects/{pid}/generate-brief")
async def generate_brief(pid:str,req:Generate):
    m=meta(pid); src=sources(pid)
    if not src and not req.additional_context.strip(): raise HTTPException(400,"Bitte Dateien oder Kontext bereitstellen")
    system="Du bist Senior Marketing Strategist und Conversion Copywriter. Nutze nur belegbare Angaben aus den Quellen. Erfinde keine Kennzahlen, Testimonials, Kunden oder Zertifikate. Antworte auf Deutsch."
    user=f"""Erstelle einen präzisen Marketing-Brief.
Projekt: {m['name']}
Zielgruppe: {m.get('audience') or 'aus Quellen ableiten'}
Ziel: {m.get('goal')}
Ton: {m.get('tone')}
Zusatzkontext: {req.additional_context}

QUELLEN:
{src}

Behandle: Kernangebot, Zielgruppen/Jobs-to-be-done, Pain Points, Nutzenargumente, Differenzierung, Belege, Einwände, Message Hierarchy, CTA, SEO (Intent/Keywords/Meta), Landingpage-Struktur und offene Punkte."""
    b=await chat(req.ollama,system,user,.4)
    (pdir(pid)/"brief.md").write_text(b,"utf-8"); m["has_brief"]=True; save_meta(pid,m)
    return {"brief":b}

@app.get("/api/projects/{pid}/brief")
def get_brief(pid:str):
    f=pdir(pid)/"brief.md"
    if not f.exists(): raise HTTPException(404,"Kein Brief vorhanden")
    return {"brief":f.read_text("utf-8")}

@app.post("/api/projects/{pid}/generate-site")
async def generate_site(pid:str,req:Generate):
    m=meta(pid); bf=pdir(pid)/"brief.md"
    if not bf.exists(): raise HTTPException(400,"Zuerst Marketing-Brief erstellen")
    brief=bf.read_text("utf-8")
    system="Du bist Senior Webdesigner, UX Designer und Conversion Copywriter. Erzeuge ausschließlich ein vollständiges valides HTML5-Dokument mit eingebettetem CSS und minimalem Vanilla-JS. Kein Markdown. Keine erfundenen Fakten, Kunden, Logos, Kennzahlen oder Testimonials. Responsive, zugänglich, SEO-freundlich und visuell hochwertig."
    user=f"""Erstelle eine vollständige Marketing-Landingpage.
Projekt: {m['name']}
Ton: {m.get('tone')}
Ziel: {m.get('goal')}
Zielgruppe: {m.get('audience') or 'siehe Brief'}

MARKETING-BRIEF:
{brief}

Anforderungen: Hero, Nutzen, Problem/Lösung, Leistungsblöcke, belegbare Vertrauenselemente falls vorhanden, CTA, FAQ, Footer, Meta-Title und Meta-Description. Keine externen Bilder. Nutze CSS-Flächen/Shapes statt Fake-Produktfotos."""
    html=await chat(req.ollama,system,user,.3)
    html=re.sub(r"^\s*```(?:html)?\s*","",html,flags=re.I); html=re.sub(r"\s*```\s*$","",html)
    if "<html" not in html.lower(): raise HTTPException(502,"Modell erzeugte kein vollständiges HTML")
    (pdir(pid)/"site.html").write_text(html,"utf-8"); m["has_site"]=True; save_meta(pid,m)
    return {"ok":True}

@app.get("/api/projects/{pid}/preview",response_class=HTMLResponse)
def preview(pid:str):
    f=pdir(pid)/"site.html"
    if not f.exists(): raise HTTPException(404,"Keine Website vorhanden")
    return HTMLResponse(f.read_text("utf-8"))

@app.get("/api/projects/{pid}/download")
def download(pid:str):
    f=pdir(pid)/"site.html"
    if not f.exists(): raise HTTPException(404,"Keine Website vorhanden")
    return FileResponse(f,filename="landingpage.html",media_type="text/html")

@app.delete("/api/projects/{pid}")
def delete(pid:str):
    shutil.rmtree(pdir(pid)); return {"ok":True}
