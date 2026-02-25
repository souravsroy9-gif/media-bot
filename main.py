import os
from flask import Flask, request, send_file
import yt_dlp
import uuid
from pathlib import Path

app = Flask(__name__)
Path("downloads").mkdir(exist_ok=True)

HTML = '''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Downloader</title><style>body{font-family:Arial;background:#6610f2;min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px;margin:0}.box{background:#fff;border-radius:16px;padding:25px;max-width:350px;width:100%}h1{text-align:center;margin:0 0 15px}input{width:100%;padding:10px;border:2px solid #ddd;border-radius:8px;margin-bottom:10px;box-sizing:border-box}button{width:100%;padding:10px;background:#6610f2;color:#fff;border:none;border-radius:8px}p{margin:10px 0}a{display:block;text-align:center;padding:10px;background:#28a745;color:#fff;text-decoration:none;border-radius:8px;margin-top:10px}</style></head><body><div class="box"><h1>🎬 Downloader</h1><input type="text" id="url" placeholder="Paste link..."><button onclick="dl()">⬇️ Download</button><p id="msg"></p></div><script>async function dl(){const u=document.getElementById("url").value;if(!u){alert("Enter URL");return}document.getElementById("msg").innerText="⏳ Downloading...";try{const r=await fetch("/dl",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:u})});const d=await r.json();if(d.e){document.getElementById("msg").innerText="❌ "+d.e;return}document.getElementById("msg").innerHTML='<a href="/f/'+d.f+'">📥 Download File</a>'}catch(e){document.getElementById("msg").innerText="❌ Error"}}</script></body></html>'''

@app.route('/')
def home():
    return HTML

@app.route('/dl', methods=['POST'])
def download():
    try:
        url = request.get_json().get('url', '')
        fid = uuid.uuid4().hex[:8]
        ydl = yt_dlp.YoutubeDL({
            'format': 'best',
            'outtmpl': f'downloads/{fid}.%(ext)s',
            'quiet': True,
            'no_warnings': True
        })
        ydl.download([url])
        for f in Path("downloads").glob(f"{fid}*"):
            if f.is_file():
                return {'f': f.name}
        return {'e': 'Failed'}
    except Exception as e:
        return {'e': str(e)[:50]}

@app.route('/f/<name>')
def file(name):
    p = Path("downloads") / name
    return send_file(str(p), as_attachment=True) if p.exists() else ("Not found", 404)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
