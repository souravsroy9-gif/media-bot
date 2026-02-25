import os, threading, requests, uuid
from flask import Flask, request, send_file
from pathlib import Path

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
app = Flask(__name__)
Path("downloads").mkdir(exist_ok=True)

HTML = '''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Media Downloader</title><style>*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px;margin:0}.box{background:#fff;border-radius:20px;padding:30px;max-width:420px;width:100%;box-shadow:0 20px 60px rgba(0,0,0,.3)}h1{text-align:center;color:#333;margin:0 0 5px}.sub{text-align:center;color:#666;margin-bottom:20px;font-size:14px}input{width:100%;padding:14px;border:2px solid #ddd;border-radius:10px;margin-bottom:15px;font-size:16px}button{width:100%;padding:14px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:10px;font-size:16px;cursor:pointer;font-weight:bold}p{margin:10px 0;text-align:center}a{display:block;text-align:center;padding:14px;background:#28a745;color:#fff;text-decoration:none;border-radius:10px;margin-top:10px;font-weight:bold}.err{color:#dc3545}.load{color:#667eea}</style></head><body><div class="box"><h1>🎬 Media Downloader</h1><p class="sub">YouTube • TikTok • Instagram • Twitter • Facebook</p><input type="text" id="url" placeholder="Paste any link..."><button onclick="dl()">⬇️ Download</button><p id="msg"></p></div><script>async function dl(){const u=document.getElementById("url").value.trim();if(!u){document.getElementById("msg").innerHTML='<span class="err">Please paste a link</span>';return}document.getElementById("msg").innerHTML='<span class="load">⏳ Downloading...</span>';try{const r=await fetch("/api/dl",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:u})});const d=await r.json();if(d.error){document.getElementById("msg").innerHTML='<span class="err">❌ '+d.error+'</span>';return}if(d.direct){window.open(d.direct,"_blank");document.getElementById("msg").innerHTML='<span style="color:#28a745">✅ Download started!</span>'}else if(d.file){document.getElementById("msg").innerHTML='<a href="/f/'+d.file+'">📥 Download '+d.file+'</a>'}}catch(e){document.getElementById("msg").innerHTML='<span class="err">❌ Error: '+e.message+'</span>'}}</script></body></html>'''

def get_video(url):
    """Use cobalt API to bypass blocks"""
    try:
        # Try cobalt.tools API (free, works!)
        api_url = "https://api.cobalt.tools/api/json"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        data = {
            "url": url,
            "vCodec": "h264",
            "vQuality": "720",
            "aFormat": "mp3"
        }
        
        r = requests.post(api_url, json=data, headers=headers, timeout=30)
        
        if r.status_code == 200:
            result = r.json()
            
            if result.get("status") == "redirect" or result.get("status") == "stream":
                # Direct link available
                return {"direct": result.get("url")}
            
            elif result.get("status") == "picker":
                # Multiple options (like photos)
                if result.get("audio"):
                    return {"direct": result["audio"]}
                pics = result.get("picker", [])
                if pics:
                    return {"direct": pics[0].get("url")}
        
        # Fallback: try direct download
        return download_direct(url)
        
    except Exception as e:
        # Fallback method
        return download_direct(url)

def download_direct(url):
    """Fallback direct download using yt-dlp"""
    try:
        import yt_dlp
        fid = uuid.uuid4().hex[:8]
        opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': f'downloads/{fid}.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
        }
        yt_dlp.YoutubeDL(opts).download([url])
        for f in Path("downloads").glob(f"{fid}*"):
            if f.is_file():
                return {"file": f.name}
        return {"error": "Could not download"}
    except:
        return {"error": "Video unavailable or blocked"}

@app.route('/')
def home(): return HTML

@app.route('/api/dl', methods=['POST'])
def api_dl():
    url = request.get_json().get('url', '')
    if not url:
        return {"error": "No URL provided"}
    return get_video(url)

@app.route('/f/<name>')
def get_file(name):
    p = Path("downloads") / name
    return send_file(str(p), as_attachment=True) if p.exists() else ("Not found", 404)

def run_bot():
    if not BOT_TOKEN: 
        print("⚠️ No BOT_TOKEN - Telegram bot disabled")
        return
    try:
        from telegram import Update
        from telegram.ext import Application, CommandHandler, MessageHandler, filters
        
        async def start(u, c):
            await u.message.reply_text(
                "🎬 *Media Downloader Bot*\n\n"
                "Send me any link!\n\n"
                "✅ YouTube\n"
                "✅ TikTok\n"
                "✅ Instagram\n"
                "✅ Twitter/X\n"
                "✅ Facebook\n"
                "✅ Pinterest\n"
                "✅ Vimeo",
                parse_mode='Markdown'
            )
        
        async def msg(u, c):
            t = u.message.text
            if 'http' not in t:
                await u.message.reply_text("❌ Please send a valid link")
                return
            
            s = await u.message.reply_text("⬇️ Downloading...")
            
            try:
                result = get_video(t)
                
                if result.get("error"):
                    await s.edit_text(f"❌ {result['error']}")
                    return
                
                if result.get("direct"):
                    await s.edit_text("✅ Download ready!")
                    await u.message.reply_text(f"📥 Download link:\n{result['direct']}")
                
                elif result.get("file"):
                    await s.edit_text("📤 Uploading...")
                    filepath = f"downloads/{result['file']}"
                    with open(filepath, 'rb') as f:
                        if result['file'].endswith('.mp3'):
                            await u.message.reply_audio(audio=f, caption="✅ Done!")
                        else:
                            await u.message.reply_video(video=f, caption="✅ Done!")
                    await s.delete()
                    
            except Exception as e:
                await s.edit_text(f"❌ Error: {str(e)[:50]}")
        
        a = Application.builder().token(BOT_TOKEN).build()
        a.add_handler(CommandHandler("start", start))
        a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg))
        print("🤖 Telegram Bot started!")
        a.run_polling(close_loop=False)
        
    except Exception as e:
        print(f"Bot error: {e}")

if __name__ == '__main__':
    print("=" * 40)
    print("🎬 Media Downloader - BYPASS VERSION")
    print("=" * 40)
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
