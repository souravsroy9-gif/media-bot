import os
from flask import Flask, request, jsonify, send_file
import yt_dlp
import uuid
from pathlib import Path

app = Flask(__name__)
Path("downloads").mkdir(exist_ok=True)

@app.route('/')
def home():
    return '''
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Media Downloader</title>
<style>
body{font-family:Arial;background:#667eea;min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px;margin:0}
.box{background:#fff;border-radius:20px;padding:30px;max-width:400px;width:100%}
h1{text-align:center;margin-bottom:20px}
input{width:100%;padding:12px;border:2px solid #ddd;border-radius:8px;margin-bottom:15px;box-sizing:border-box}
button{width:100%;padding:12px;background:#667eea;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:16px}
.btns{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:15px}
.btns button{background:#f0f0f0;color:#333;font-size:14px}
.btns button:hover{background:#667eea;color:#fff}
.dl{display:block;text-align:center;padding:12px;background:#28a745;color:#fff;text-decoration:none;border-radius:8px;margin-top:15px}
.info{background:#f5f5f5;padding:12px;border-radius:8px;margin-bottom:10px}
</style>
</head>
<body>
<div class="box">
<h1>🎬 Media Downloader</h1>
<input type="text" id="url" placeholder="Paste YouTube/TikTok link...">
<button onclick="getInfo()">🔍 Get Info</button>
<div id="result"></div>
</div>
<script>
async function getInfo(){
const url=document.getElementById("url").value.trim();
if(!url){alert("Enter a URL");return}
document.getElementById("result").innerHTML="<p>Loading...</p>";
try{
const r=await fetch("/api/info",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url})});
const d=await r.json();
if(d.error){alert(d.error);return}
let h='<div class="info"><b>'+d.title+'</b><br>⏱ '+d.duration+'</div><div class="btns">';
if(d.resolutions)d.resolutions.forEach(q=>h+='<button onclick="download(\''+q+'\')">🎬 '+q+'</button>');
h+='<button onclick="download(\'audio\')">🎵 MP3</button>';
h+='<button onclick="download(\'thumbnail\')">🖼 Thumb</button></div>';
document.getElementById("result").innerHTML=h;
}catch(e){alert("Error: "+e.message)}
}
async function download(q){
const url=document.getElementById("url").value;
document.getElementById("result").innerHTML+="<p>Downloading...</p>";
try{
const r=await fetch("/api/download",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url,quality:q})});
const d=await r.json();
if(d.error){alert(d.error);return}
if(d.is_url)window.open(d.url,"_blank");
else document.getElementById("result").innerHTML+='<a class="dl" href="/file/'+d.file+'">📥 Download '+d.file+'</a>';
}catch(e){alert("Error: "+e.message)}
}
</script>
</body>
</html>
'''

@app.route('/api/info', methods=['POST'])
def api_info():
    try:
        url = request.get_json().get('url', '')
        ydl = yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True})
        info = ydl.extract_info(url, download=False)
        formats = info.get('formats', [])
        res = set()
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('height'):
                h = f['height']
                if h >= 1080: res.add('1080p')
                elif h >= 720: res.add('720p')
                elif h >= 480: res.add('480p')
        dur = info.get('duration') or 0
        return jsonify({
            'title': info.get('title', 'Video'),
            'duration': f"{dur//60}:{dur%60:02d}",
            'resolutions': sorted(res, reverse=True)
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/download', methods=['POST'])
def api_download():
    try:
        data = request.get_json()
        url = data.get('url', '')
        q = data.get('quality', '720p')
        fid = str(uuid.uuid4())[:8]
        
        if q == 'thumbnail':
            ydl = yt_dlp.YoutubeDL({'quiet': True})
            info = ydl.extract_info(url, download=False)
            thumbs = info.get('thumbnails', [])
            if thumbs:
                return jsonify({'is_url': True, 'url': thumbs[-1]['url']})
            return jsonify({'error': 'No thumbnail'})
        
        fmt = 'bestaudio/best' if q == 'audio' else f'best[height<={q[:-1]}]'
        opts = {
            'format': fmt,
            'outtmpl': f'downloads/{fid}.%(ext)s',
            'quiet': True
        }
        if q == 'audio':
            opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]
        
        yt_dlp.YoutubeDL(opts).download([url])
        
        for f in Path("downloads").glob(f"{fid}*"):
            if f.is_file():
                return jsonify({'file': f.name})
        return jsonify({'error': 'Download failed'})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/file/<name>')
def get_file(name):
    path = Path("downloads") / name
    if path.exists():
        return send_file(str(path), as_attachment=True)
    return "Not found", 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print("🚀 Running on port", port)
    app.run(host='0.0.0.0', port=port)
