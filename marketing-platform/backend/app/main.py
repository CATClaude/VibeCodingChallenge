from pathlib import Path
import asyncio, base64, json, os, re, shutil, uuid, zipfile, mimetypes
import httpx
from docx import Document
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, Response
from pydantic import BaseModel
from pypdf import PdfReader
import fitz

ROOT=Path("/app/data/projects"); ROOT.mkdir(parents=True,exist_ok=True)
BASE=os.getenv("OLLAMA_BASE_URL","http://host.docker.internal:11434").rstrip("/")
MODEL=os.getenv("OLLAMA_MODEL","qwen3:latest")
MAX_MB=int(os.getenv("MAX_UPLOAD_MB","25"))
ALLOWED={".pdf",".docx",".txt",".md",".markdown"}
OLLAMA_LOCK=asyncio.Lock()
OLLAMA_RETRIES=int(os.getenv("OLLAMA_RETRIES","2"))
OLLAMA_NUM_CTX=int(os.getenv("OLLAMA_NUM_CTX","32768"))

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

def extract_images(pid:str,path:Path):
    assets=pdir(pid)/"assets"; assets.mkdir(exist_ok=True)
    out=[]; ext=path.suffix.lower()
    try:
        if ext==".docx":
            with zipfile.ZipFile(path) as z:
                for n in z.namelist():
                    if n.startswith("word/media/") and not n.endswith("/"):
                        raw=z.read(n); suffix=Path(n).suffix.lower() or ".bin"
                        name=f"{path.stem}-{uuid.uuid4().hex[:8]}{suffix}"
                        (assets/name).write_bytes(raw); out.append(name)
        elif ext==".pdf":
            doc=fitz.open(str(path)); seen=set()
            for page in doc:
                for img in page.get_images(full=True):
                    xref=img[0]
                    if xref in seen: continue
                    seen.add(xref); info=doc.extract_image(xref)
                    if not info or not info.get("image"): continue
                    suffix="."+info.get("ext","png")
                    name=f"{path.stem}-{uuid.uuid4().hex[:8]}{suffix}"
                    (assets/name).write_bytes(info["image"]); out.append(name)
            doc.close()
    except Exception:
        pass
    return out

def asset_names(pid:str):
    d=pdir(pid)/"assets"
    return sorted([f.name for f in d.iterdir() if f.is_file()]) if d.exists() else []

def embed_assets(pid:str,html:str):
    assets=pdir(pid)/"assets"
    if not assets.exists(): return html
    for f in assets.iterdir():
        if not f.is_file(): continue
        mime=mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        data=base64.b64encode(f.read_bytes()).decode("ascii")
        uri=f"data:{mime};base64,{data}"
        html=html.replace(f'src="assets/{f.name}"',f'src="{uri}"')
        html=html.replace(f"src='assets/{f.name}'",f"src='{uri}'")
    return html

def sources(pid:str):
    u=pdir(pid)/"uploads"; parts=[]
    for f in sorted(u.glob("*")):
        if f.is_file() and f.suffix.lower() in ALLOWED:
            t=extract(f).strip()
            if t: parts.append(f"--- QUELLE: {f.name} ---\n{t}")
    return "\n\n".join(parts)[:120000]

def normalize_base_url(url:str):
    url=(url or BASE).strip().rstrip("/")
    url=re.sub(r"^http://localhost(?=[:/]|$)","http://host.docker.internal",url,flags=re.I)
    url=re.sub(r"^http://127\.0\.0\.1(?=[:/]|$)","http://host.docker.internal",url,flags=re.I)
    return url

async def chat(cfg:Ollama,system:str,user:str,temp=.35):
    url=normalize_base_url(cfg.base_url)+"/api/chat"
    payload={"model":cfg.model,"stream":False,"keep_alive":-1,"messages":[{"role":"system","content":system},{"role":"user","content":user}],"options":{"temperature":temp,"num_ctx":OLLAMA_NUM_CTX}}
    last=None
    async with OLLAMA_LOCK:
        for attempt in range(OLLAMA_RETRIES+1):
            try:
                timeout=httpx.Timeout(600.0,connect=20.0,read=600.0,write=60.0)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    r=await client.post(url,json=payload)
                    if r.status_code>=500:
                        raise httpx.HTTPStatusError(f"Ollama HTTP {r.status_code}",request=r.request,response=r)
                    r.raise_for_status()
                    out=(r.json().get("message") or {}).get("content","").strip()
                    if not out: raise RuntimeError("Ollama lieferte keine Antwort")
                    return out
            except (httpx.ConnectError,httpx.ReadTimeout,httpx.RemoteProtocolError,httpx.HTTPStatusError,RuntimeError) as e:
                last=e
                if attempt<OLLAMA_RETRIES:
                    await asyncio.sleep(2*(attempt+1))
                    continue
                break
    raise HTTPException(502,f"Ollama-Anfrage nach {OLLAMA_RETRIES+1} Versuchen fehlgeschlagen: {last}")

@app.get("/api/health")
def health(): return {"ok":True,"default_model":MODEL,"default_base_url":BASE}

@app.post("/api/ollama/test")
async def test_ollama(cfg:Ollama):
    async with httpx.AsyncClient(timeout=10) as c:
        try:
            resolved=normalize_base_url(cfg.base_url)
            r=await c.get(resolved+"/api/tags"); r.raise_for_status()
            return {"ok":True,"resolved_url":resolved,"models":[m.get("name") for m in r.json().get("models",[])]}
        except Exception as e:
            raise HTTPException(502,f"Ollama unter {normalize_base_url(cfg.base_url)} nicht erreichbar: {e}. Falls Ollama auf diesem Host läuft, starte es mit OLLAMA_HOST=0.0.0.0:11434.")

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
    pid=uuid.uuid4().hex[:12]; d=ROOT/pid; (d/"uploads").mkdir(parents=True); (d/"assets").mkdir(exist_ok=True)
    m={"id":pid,**req.model_dump(),"files":[],"images":[],"has_brief":False,"has_site":False}
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
        extracted=extract_images(pid,d/name)
        m["images"]=sorted(set(m.get("images",[])+extracted))
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

Behandle: Kernangebot, Zielgruppen/Jobs-to-be-done, Pain Points, Nutzenargumente, Differenzierung, Belege, Einwände, Message Hierarchy, CTA, SEO (Intent/Keywords/Meta), Landingpage-Struktur und offene Punkte. Berücksichtige, dass Bildmaterial aus den Quelldokumenten für die Website verfügbar sein kann."""
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
    images=asset_names(pid)
    image_paths=[f"assets/{x}" for x in images]
    system="Du bist Senior Webdesigner, UX Designer und Conversion Copywriter. Erzeuge ausschließlich ein vollständiges valides HTML5-Dokument mit eingebettetem CSS und minimalem Vanilla-JS. Kein Markdown. Keine erfundenen Fakten, Kunden, Logos, Kennzahlen oder Testimonials. Responsive, zugänglich, SEO-freundlich und visuell hochwertig."
    user=f"""Erstelle eine vollständige Marketing-Landingpage.
Projekt: {m['name']}
Ton: {m.get('tone')}
Ziel: {m.get('goal')}
Zielgruppe: {m.get('audience') or 'siehe Brief'}

MARKETING-BRIEF:
{brief}

Anforderungen: Hero, Nutzen, Problem/Lösung, Leistungsblöcke, belegbare Vertrauenselemente falls vorhanden, CTA, FAQ, Footer, Meta-Title und Meta-Description. Keine externen Bilder. Falls unter VERFÜGBARE BILDER Pfade stehen, verwende passende davon mit <img src="assets/DATEINAME"> und erfinde keine anderen Bildpfade. Wenn keine Bilder vorhanden sind, nutze CSS-Flächen/Shapes statt Fake-Produktfotos.\n\nVERFÜGBARE BILDER:\n{chr(10).join(image_paths) if image_paths else "keine"}"""
    html=await chat(req.ollama,system,user,.3)
    html=re.sub(r"^\s*```(?:html)?\s*","",html,flags=re.I); html=re.sub(r"\s*```\s*$","",html)
    if "<html" not in html.lower(): raise HTTPException(502,"Modell erzeugte kein vollständiges HTML")
    html=embed_assets(pid,html)
    (pdir(pid)/"site.html").write_text(html,"utf-8"); m["has_site"]=True; save_meta(pid,m)
    return {"ok":True}

@app.get("/api/projects/{pid}/assets/{name}")
def get_asset(pid:str,name:str):
    safe=Path(name).name
    f=pdir(pid)/"assets"/safe
    if not f.exists() or not f.is_file(): raise HTTPException(404,"Bild nicht gefunden")
    mime=mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    return FileResponse(f,media_type=mime)

@app.get("/api/projects/{pid}/preview",response_class=HTMLResponse)
def preview(pid:str):
    f=pdir(pid)/"site.html"
    if not f.exists(): raise HTTPException(404,"Keine Website vorhanden")
    html=f.read_text("utf-8")
    html=re.sub(r'(?i)(src=["\\\'])assets/',rf'\\1/api/projects/{pid}/assets/',html)
    return HTMLResponse(html)

@app.get("/api/projects/{pid}/download")
def download(pid:str):
    f=pdir(pid)/"site.html"
    if not f.exists(): raise HTTPException(404,"Keine Website vorhanden")
    return FileResponse(f,filename="landingpage.html",media_type="text/html")

@app.delete("/api/projects/{pid}")
def delete(pid:str):
    shutil.rmtree(pdir(pid)); return {"ok":True}
