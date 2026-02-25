import os, re, logging, threading, uuid
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_file
import yt_dlp

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
Path("downloads").mkdir(exist_ok=True)

HTML = '<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Media Downloader</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:sans-serif;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px}.container{background:#fff;border-radius:20px;padding:40px;max-width:500px;box-shadow:0 20px 60px rgba(0,0,0,.3)}h1{text-align:center;color:#333;margin-bottom:10px}.sub{text-align:center;color:#666;margin-bottom:30px;font-size:14px}input{width:100%;padding:15px;border:2px solid #e0e0e0;border-radius:10px;font-size:16px;margin-bottom:20px}.btn{width:100%;padding:15px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:10px;font-size:16px;cursor:pointer}.status{text-align:center;margin:20px 0;padding:15px;border-radius:10px;display:none}.status.load{background:#fff3cd;color:#856404;display:block}.status.err{background:#f8d7da;color:#721c24;display:block}.status.ok{background:#d4edda;color:#155724;display:block}.result{display:none;margin-top:20px}.result.show{display:block}.info{background:#f8f9fa;padding:15px;border-radius:10px;margin-bottom:15px}.title{font-weight:700;color:#333}.meta{color:#666;font-size:14px}.btns{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.qbtn{padding:12px;background:#f0f0f0;border:none;border-radius:8px;cursor:pointer}.dlink{display:block;text-align:center;padding:15px;background:#28a745;color:#fff;text-decoration:none;border-radius:10px;margin-top:15px}</style></head><body><div class="container"><h1>🎬 Media Downloader</h1><p class="sub">Download videos from any platform</p><input type="text" id="url" placeholder="Paste link here"><button class="btn" onclick="getInfo()">🔍 Get Info</button><div id="st" class="status"></div><div id="res" class="result"><div class="info"><div id="title" class="title"></div><div id="meta" class="meta"></div></div><div id="btns" class="btns"></div><a id="dl" class="dlink" style="display:none">📥 Download</a></div></div><script>const st=document.getElementById("st"),res=document.getElementById("res");function show(m,t){st.textContent=m,st.className="status "+t}async function getInfo(){const u=document.getElementById("url").value.trim();if(!u)return show("Please enter a URL","err");show("🔍 Fetching...","load"),res.classList.remove("show");try{const r=await fetch("/api/info",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:u})}),d=await r.json();d.success?(document.getElementById("title").textContent=d.title,document.getElementById("meta").textContent="👤 "+d.uploader+" • ⏱ "+d.duration,showBtns(d,u)):show("❌ "+d.error,"err")}catch(e){show("❌ "+e.message,"err")}}function showBtns(i,u){const b=document.getElementById("btns");b.innerHTML="",i.is_video&&i.resolutions&&i.resolutions.forEach(q=>{const n=document.createElement("button");n.className="qbtn",n.textContent="🎬 "+q,n.onclick=()=>download(u,q),b.appendChild(n)}),i.has_audio&&(n=document.createElement("button"),n.className="qbtn",n.textContent="🎵 Audio MP3",n.onclick=()=>download(u,"audio"),b.appendChild(n)),n=document.createElement("button"),n.className="qbtn",n.textContent="🖼 Thumbnail",n.onclick=()=>download(u,"thumbnail"),b.appendChild(n),res.classList.add("show"),st.className="status"}async function download(u,q){show("⬇️ Downloading...","load");try{const r=await fetch("/api/download",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:u,quality:q})}),d=await r.json();d.success?d.is_url?(window.open(d.file_path,"_blank"),show("✅ Opened!","ok")):(document.getElementById("dl").href="/api/file/"+d.file_name,document.getElementById("dl").style.display="block",show("✅ Ready!","ok")):show("❌ "+d.error,"err")}catch(e){show("❌ "+e.message,"err")}}</script></body></html>'

def get_info(url):
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True}) as ydl:
            i = ydl.extract_info(url, download=False)
            f = i.get('formats', [])
            r = set()
            for x in f:
                if x.get('vcodec') != 'none' and x.get('height'):
                    h = x.get('height')
                    if h >= 2160: r.add('4K')
                    elif h >= 1440: r.add('2K')
                    elif h >= 1080: r.add('1080p')
                    elif h >= 720: r.add('720p')
                    elif h >= 480: r.add('480p')
            d = i.get('duration', 0)
            return {'success': True, 'title': i.get('title', 'Unknown'), 'uploader': i.get('uploader') or i.get('channel') or 'Unknown', 'duration': f"{d//60}:{d%60:02d}" if d else "Unknown", 'resolutions': sorted(list(r), reverse=True), 'has_audio': any(x.get('acodec') != 'none' for x in f), 'is_video': any(x.get('vcodec') != 'none' for x in f)}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def dl_media(url, q, uid):
    base = f"downloads/{uid}"
    try:
        if q == 'thumbnail':
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                i = ydl.extract_info(url, download=False)
                t = i.get('thumbnails', [])
                if t: return {'success': True, 'is_url': True, 'file_path': t[-1]['url']}
            return {'success': False, 'error': 'No thumbnail'}
        o = {'audio': {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}]}, '4K': {'format': 'bestvideo[height<=2160]+bestaudio/best'}, '2K': {'format': 'bestvideo[height<=1440]+bestaudio/best'}, '1080p': {'format': 'bestvideo[height<=1080]+bestaudio/best'}, '720p': {'format': 'bestvideo[height<=720]+bestaudio/best'}, '480p': {'format': 'bestvideo[height<=480]+bestaudio/best'}}.get(q, {'format': 'best'})
        o.update({'outtmpl': f'{base}.%(ext)s', 'quiet': True, 'merge_output_format': 'mp4'})
        with yt_dlp.YoutubeDL(o) as ydl: ydl.download([url])
        for f in Path("downloads").glob(f"{uid}*"):
            if f.is_file(): return {'success': True, 'file_path': str(f), 'file_name': f.name, 'is_url': False}
        return {'success': False, 'error': 'File not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

app = Flask(__name__)
@app.route('/')
def home(): return HTML
@app.route('/api/info', methods=['POST'])
def api_info(): return jsonify(get_info(request.get_json().get('url', '')))
@app.route('/api/download', methods=['POST'])
def api_download():
    d = request.get_json()
    return jsonify(dl_media(d.get('url', ''), d.get('quality', '720p'), f"web_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"))
@app.route('/api/file/<n>')
def get_file(n):
    p = Path("downloads") / n
    return send_file(str(p), as_attachment=True) if p.exists() else ("Not found", 404)

def run_bot():
    if not BOT_TOKEN: return
    try:
        from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
        async def start(u, c): await u.message.reply_text("🤖 Media Downloader\n\nSend any video link!\n\nYouTube, TikTok, Instagram, Twitter, Facebook & more")
        async def msg(u, c):
            t = u.message.text
            if 'http' not in t: await u.message.reply_text("❌ Send a valid link"); return
            s = await u.message.reply_text("🔍 Getting info...")
            i = get_info(t)
            if not i['success']: await s.edit_text(f"❌ {i.get('error')}"); return
            c.user_data['url'] = t
            kb = []
            if i.get('is_video'): [kb.append([InlineKeyboardButton(f"🎬 {r}", callback_data=f"dl_{r}")]) for r in i.get('resolutions', [])]
            if i.get('has_audio'): kb.append([InlineKeyboardButton("🎵 Audio MP3", callback_data="dl_audio")])
            kb.append([InlineKeyboardButton("🖼 Thumbnail", callback_data="dl_thumb")])
            await s.delete()
            await u.message.reply_text(f"📺 {i['title']}\n👤 {i['uploader']}\n⏱ {i['duration']}", reply_markup=InlineKeyboardMarkup(kb))
        async def cb(u, c):
            q = u.callback_query; await q.answer()
            ql = q.data.replace("dl_", "").replace("thumb", "thumbnail")
            url = c.user_data.get('url')
            if not url: await q.edit_message_text("❌ Expired"); return
            await q.edit_message_text("⬇️ Downloading...")
            r = dl_media(url, ql, f"tg_{u.effective_user.id}")
            if not r['success']: await q.edit_message_text(f"❌ {r['error']}"); return
            await q.edit_message_text("📤 Uploading...")
            try:
                if r.get('is_url'): await c.bot.send_photo(u.effective_user.id, photo=r['file_path'])
                else:
                    with open(r['file_path'], 'rb') as f:
                        if 'mp3' in r['file_name']: await c.bot.send_audio(u.effective_user.id, audio=f)
                        else: await c.bot.send_video(u.effective_user.id, video=f)
                await q.edit_message_text("✅ Done!")
            except Exception as e: await q.edit_message_text(f"❌ {e}")
        a = Application.builder().token(BOT_TOKEN).build()
        a.add_handler(CommandHandler("start", start))
        a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg))
        a.add_handler(CallbackQueryHandler(cb))
        a.run_polling(close_loop=False)
    except: pass

if __name__ == "__main__":
    print("🚀 Media Downloader Running!")
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=8080)
