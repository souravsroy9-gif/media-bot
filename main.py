import os
from flask import Flask, request, send_file
import yt_dlp
import uuid
from pathlib import Path
from datetime import datetime

app = Flask(__name__)
Path("downloads").mkdir(exist_ok=True)

HTML = '''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Media Downloader</title><style>body{font-family:Arial;background:#667eea;min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px}.box{background:#fff;border-radius:20px;padding:30px;max-width:400px;width:100%}h1{text-align:center}input{width:100%;padding:12px;border:2px solid #ddd;border-radius:8px;margin:15px 0;box-sizing:border-box}button{width:100%;padding:12px;background:#667eea;color:#fff;border:none;border-radius:8px;cursor:pointer}.btns button{background:#f0f0f0;color:#333;margin:5px 0}.btns button:hover{background:#667eea;color:#fff}a{display:block;padding:12px;background:#28a745;color:#fff;text-decoration:none;border-radius:8px;text-align:center;margin-top:10px}</style></head><body><div class="box"><h1>🎬 Downloader</h1><input type="text" id="url" placeholder="Paste link..."><button onclick="getInfo()">🔍 Get Info</button><div id="res"></div></div><script>async function getInfo(){const u=document.getElementById("url").value;if(!u)return alert("Enter URL");const r=await fetch("/api/info",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:u})});const d=await r.json();if(!d.success)return alert(d.error);let h="<p><b>"+d.title+"</b></p><div class=\"btns\">";if(d.is_video)d.resolutions.forEach(q=>h+="<button onclick=\"dl(\'"+q+"\')\">🎬 "+q+"</button>");if(d.has_audio)h+="<button onclick=\"dl(\'audio\')\">🎵 MP3</button>";h+="<button onclick=\"dl(\'thumbnail\')\">🖼 Thumb</button></div>";document.getElementById("res").innerHTML=h}async function dl(q){const u=document.getElementById("url").value;const r=await fetch("/api/download",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:u,quality:q})});const d=await r.json();if(!d.success)return alert(d.error);if(d.is_url)window.open(d.file_path);else document.getElementById("res").innerHTML+="<a href=\"/file/"+d.file_name+"\">📥 Download</a>"}</script></body></html>'''

def get_info(url):
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True}) as ydl:
            i = ydl.extract_info(url, download=False)
            f = i.get('formats', [])
            r = set()
            for x in f:
                if x.get('vcodec') != 'none' and x.get('height'):
                    h = x['height']
                    if h >= 2160: r.add('4K')
                    elif h >= 1440: r.add('2K')
                    elif h >= 1080: r.add('1080p')
                    elif h >= 720: r.add('720p')
                    elif h >= 480: r.add('480p')
            d = i.get('duration') or 0
            return {'success': True, 'title': i.get('title', 'Unknown'), 'uploader': i.get('uploader') or 'Unknown', 'duration': f"{d//60}:{d%60:02d}", 'resolutions': sorted(r, reverse=True), 'has_audio': any(x.get('acodec') != 'none' for x in f), 'is_video': any(x.get('vcodec') != 'none' for x in f)}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/')
def home():
    return HTML

@app.route('/api/info', methods=['POST'])
def api_info():
    return jsonify(get_info(request.get_json().get('url', '')))

from flask import jsonify

@app.route('/api/download', methods=['POST'])
def api_download():
    d = request.get_json()
    url = d.get('url', '')
    q = d.get('quality', '720p')
    fid = f"file_{uuid.uuid4().hex[:8]}"
    try:
        if q == 'thumbnail':
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                i = ydl.extract_info(url, download=False)
                t = i.get('thumbnails', [])
                if t: return jsonify({'success': True, 'is_url': True, 'file_path': t[-1]['url']})
            return jsonify({'success': False, 'error': 'No thumbnail'})
        opts = {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]} if q == 'audio' else {'format': f'best[height<={q[:-1]}]'} if q.endswith('p') or q in ['4K', '2K'] else {'format': 'best'}
        opts['outtmpl'] = f'downloads/{fid}.%(ext)s'
        opts['quiet'] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        for f in Path("downloads").glob(f"{fid}*"):
            if f.is_file():
                return jsonify({'success': True, 'file_name': f.name, 'is_url': False})
        return jsonify({'success': False, 'error': 'Failed'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/file/<name>')
def get_file(name):
    p = Path("downloads") / name
    if p.exists():
        return send_file(str(p), as_attachment=True)
    return "Not found", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
