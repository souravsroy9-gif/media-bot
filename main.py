import os
from flask import Flask, request, jsonify, send_file
import yt_dlp
import uuid
from pathlib import Path
from datetime import datetime

app = Flask(__name__)
Path("downloads").mkdir(exist_ok=True)

HTML = '''
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Media Downloader</title>
<style>
body{font-family:sans-serif;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px}
.box{background:#fff;border-radius:20px;padding:40px;max-width:500px;box-shadow:0 20px 60px rgba(0,0,0,.3)}
h1{text-align:center;color:#333}
input{width:100%;padding:15px;border:2px solid #ddd;border-radius:10px;font-size:16px;margin:20px 0}
button{width:100%;padding:15px;background:#667eea;color:#fff;border:none;border-radius:10px;font-size:16px;cursor:pointer}
.info{background:#f5f5f5;padding:15px;border-radius:10px;margin:15px 0}
.btns{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:15px}
.btns button{background:#f0f0f0;color:#333;padding:10px;border-radius:8px}
.btns button:hover{background:#667eea;color:#fff}
a{display:block;text-align:center;padding:15px;background:#28a745;color:#fff;text-decoration:none;border-radius:10px;margin-top:15px}
</style>
</head>
<body>
<div class="box">
<h1>🎬 Media Downloader</h1>
<input type="text" id="url" placeholder="Paste YouTube, TikTok, Instagram link...">
<button onclick="getInfo()">🔍 Get Info</button>
<div id="result"></div>
</div>
<script>
async function getInfo(){
const url=document.getElementById("url").value;
if(!url)return alert("Enter a URL");
const r=await fetch("/api/info",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url})});
const d=await r.json();
if(!d.success)return alert(d.error);
let html='<div class="info"><b>'+d.title+'</b><br>👤 '+d.uploader+' | ⏱ '+d.duration+'</div><div class="btns">';
if(d.is_video)d.resolutions.forEach(q=>html+='<button onclick="download(\''+q+'\')">🎬 '+q+'</button>');
if(d.has_audio)html+='<button onclick="download(\'audio\')">🎵 MP3</button>';
html+='<button onclick="download(\'thumbnail\')">🖼 Thumbnail</button></div>';
document.getElementById("result").innerHTML=html;
}
async function download(q){
const url=document.getElementById("url").value;
const r=await fetch("/api/download",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url,quality:q})});
const d=await r.json();
if(!d.success)return alert(d.error);
if(d.is_url)window.open(d.file_path,"_blank");
else document.getElementById("result").innerHTML+='<a href="/api/file/'+d.file_name+'">📥 Download '+d.file_name+'</a>';
}
</script>
</body>
</html>
'''

def get_info(url):
    try:
        ydl = yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True})
        info = ydl.extract_info(url, download=False)
        formats = info.get('formats', [])
        resolutions = set()
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('height'):
                h = f['height']
                if h >= 2160: resolutions.add('4K')
                elif h >= 1440: resolutions.add('2K')
                elif h >= 1080: resolutions.add('1080p')
                elif h >= 720: resolutions.add('720p')
                elif h >= 480: resolutions.add('480p')
        d = info.get('duration', 0) or 0
        return {
            'success': True,
            'title': info.get('title', 'Unknown'),
            'uploader': info.get('uploader') or info.get('channel') or 'Unknown',
            'duration': f"{d//60}:{d%60:02d}",
            'resolutions': sorted(list(resolutions), reverse=True),
            'has_audio': any(f.get('acodec') != 'none' for f in formats),
            'is_video': any(f.get('vcodec') != 'none' for f in formats)
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def download_media(url, quality, fid):
    try:
        if quality == 'thumbnail':
            ydl = yt_dlp.YoutubeDL({'quiet': True})
            info = ydl.extract_info(url, download=False)
            thumbs = info.get('thumbnails', [])
            if thumbs:
                return {'success': True, 'is_url': True, 'file_path': thumbs[-1]['url']}
            return {'success': False, 'error': 'No thumbnail'}
        
        opts = {
            'audio': {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}]},
            '4K': {'format': 'best[height<=2160]'},
            '2K': {'format': 'best[height<=1440]'},
            '1080p': {'format': 'best[height<=1080]'},
            '720p': {'format': 'best[height<=720]'},
            '480p': {'format': 'best[height<=480]'}
        }.get(quality, {'format': 'best'})
        
        opts['outtmpl'] = f'downloads/{fid}.%(ext)s'
        opts['quiet'] = True
        
        ydl = yt_dlp.YoutubeDL(opts)
        ydl.download([url])
        
        for f in Path("downloads").glob(f"{fid}*"):
            if f.is_file():
                return {'success': True, 'file_path': str(f), 'file_name': f.name, 'is_url': False}
        return {'success': False, 'error': 'Download failed'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/')
def home():
    return HTML

@app.route('/api/info', methods=['POST'])
def api_info():
    data = request.get_json()
    return jsonify(get_info(data.get('url', '')))

@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.get_json()
    fid = f"file_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    return jsonify(download_media(data.get('url', ''), data.get('quality', '720p'), fid))

@app.route('/api/file/<name>')
def get_file(name):
    path = Path("downloads") / name
    if path.exists():
        return send_file(str(path), as_attachment=True)
    return "Not found", 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"🚀 Running on port {port}")
    app.run(host='0.0.0.0', port=port)
