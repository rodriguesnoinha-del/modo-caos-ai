"""Private video clipping API. Requires ffmpeg and ffprobe on PATH.
Optional transcription: pip install faster-whisper (downloads model on first run).
"""
import json, os, re, shutil, subprocess, tempfile, uuid
from pathlib import Path
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

ROOT=Path(os.getenv('WORK_DIR',tempfile.gettempdir()))/'modo-caos-jobs'
ROOT.mkdir(parents=True,exist_ok=True)
TOKEN=os.getenv('MODO_CAOS_TOKEN','')
ORIGINS=[x.strip() for x in os.getenv('ALLOWED_ORIGINS','').split(',') if x.strip()]
app=FastAPI(title='Modo Caos API')
app.add_middleware(CORSMiddleware,allow_origins=ORIGINS,allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type'])

def authorize(auth):
    if not TOKEN or auth!=f'Bearer {TOKEN}':
        raise HTTPException(401,'Token inválido ou servidor não configurado')

def run(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=900)
    if p.returncode: raise RuntimeError(p.stderr[-800:])
    return p.stdout

def probe(path):
    data=json.loads(run(['ffprobe','-v','error','-show_format','-of','json',str(path)]))
    return float(data['format']['duration'])

def transcription(path):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    model=WhisperModel(os.getenv('WHISPER_MODEL','tiny'),device='cpu',compute_type='int8')
    segments,_=model.transcribe(str(path),vad_filter=True)
    return [{'start':s.start,'end':s.end,'text':s.text.strip()} for s in segments]

def srt(segments,start,end,out):
    def stamp(sec):
        ms=max(0,int(sec*1000));h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
        return f'{h:02}:{m:02}:{s:02},{ms:03}'
    rows=[]
    for seg in segments or []:
        a=max(start,seg['start']);b=min(end,seg['end'])
        if b>a: rows.append(f'{len(rows)+1}\n{stamp(a-start)} --> {stamp(b-start)}\n{seg["text"]}\n')
    out.write_text('\n'.join(rows),encoding='utf-8')
    return bool(rows)

@app.get('/health')
def health(): return {'ok':True,'ffmpeg':bool(shutil.which('ffmpeg')),'transcription_available':__import__('importlib').util.find_spec('faster_whisper') is not None}

@app.post('/process')
async def process(file:UploadFile=File(...),count:int=Form(3),seconds:int=Form(35),captions:bool=Form(True),authorization:str|None=Header(None)):
    authorize(authorization)
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'): raise HTTPException(503,'FFmpeg não instalado')
    if not 1<=count<=8 or not 10<=seconds<=90: raise HTTPException(400,'Parâmetros inválidos')
    job=uuid.uuid4().hex; folder=ROOT/job;folder.mkdir()
    src=folder/'source.mp4';size=0
    with src.open('wb') as dest:
        while chunk:=await file.read(1024*1024):
            size+=len(chunk)
            if size>500*1024*1024: raise HTTPException(413,'Limite de 500 MB')
            dest.write(chunk)
    try:
        duration=probe(src)
        if duration<10: raise HTTPException(400,'Vídeo muito curto')
        transcript=transcription(src) if captions else None
        # Transcript-aware candidates: prefer speech-dense windows; without Whisper, evenly spaced windows.
        length=min(seconds,duration)
        candidates=[min(i*max(1,(duration-length)/max(1,count*5)),duration-length) for i in range(count*5+1)]
        def score(t):
            if not transcript:return 0
            return sum(len(s['text']) for s in transcript if s['start']<t+length and s['end']>t)
        selected=[]
        for t in sorted(candidates,key=score,reverse=True):
            if all(abs(t-v)>=length*.8 for v in selected):selected.append(t)
            if len(selected)==count:break
        selected.sort(); results=[]
        for i,start in enumerate(selected,1):
            end=min(duration,start+length);out=folder/f'corte-{i}.mp4';sub=folder/f'corte-{i}.srt'
            has_sub=srt(transcript,start,end,sub) if transcript else False
            vf='scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1'
            # Subtitles exported separately for reliable cross-platform use.
            run(['ffmpeg','-y','-ss',str(start),'-i',str(src),'-t',str(end-start),'-vf',vf,'-c:v','libx264','-preset','veryfast','-crf','25','-c:a','aac','-movflags','+faststart',str(out)])
            results.append({'start':round(start,1),'end':round(end,1),'video':f'/download/{job}/{out.name}','subtitles':f'/download/{job}/{sub.name}' if has_sub else None})
        return {'job':job,'clips':results,'method':'speech-density' if transcript else 'even-spacing','note':'Os cortes são sugestões automáticas; revise antes de publicar.'}
    except HTTPException:raise
    except Exception as exc: raise HTTPException(500,str(exc)[:400])

@app.get('/download/{job}/{filename}')
def download(job:str,filename:str,authorization:str|None=Header(None)):
    authorize(authorization)
    if not re.fullmatch(r'[a-f0-9]{32}',job) or not re.fullmatch(r'corte-\d+\.(mp4|srt)',filename):raise HTTPException(400,'Arquivo inválido')
    path=ROOT/job/filename
    if not path.is_file():raise HTTPException(404,'Não encontrado')
    return FileResponse(path,filename=filename)
