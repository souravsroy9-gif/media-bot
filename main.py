import os
import logging
import tempfile
import asyncio
from pathlib import Path
from flask import Flask
from threading import Thread
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ── Keep Alive Flask ──────────────────────────────────────
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ Media Bot is Running!"

def run_flask():
    flask_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# ── YT-DLP Options ────────────────────────────────────────
def get_ydl_opts(mode="video", quality="best", tmpdir="."):
    common = {
        'quiet': True,
        'no_warnings': True,
        'outtmpl': os.path.join(tmpdir, '%(title).60s.%(ext)s'),
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web'],
                'player_skip': ['webpage', 'config'],
            }
        },
        'http_headers': {
            'User-Agent': (
                'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) '
                'AppleWebKit/605.1.15 (KHTML, like Gecko) '
                'Version/16.6 Mobile/15E148 Safari/604.1'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
        },
        'socket_timeout': 30,
        'retries': 5,
    }
    if mode == "audio":
        common['format'] = 'bestaudio/best'
        common['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    elif mode == "photo":
        common['writethumbnail'] = True
        common['skip_download'] = True
    else:
        q_map = {
            'best': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '1080': 'bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080]/best',
            '720':  'bestvideo[height<=720][ext=mp4]+bestaudio/best[height<=720]/best',
            '480':  'bestvideo[height<=480][ext=mp4]+bestaudio/best[height<=480]/best',
            '360':  'bestvideo[height<=360][ext=mp4]+bestaudio/best[height<=360]/best',
        }
        common['format'] = q_map.get(quality, q_map['best'])
        common['merge_output_format'] = 'mp4'
    return common

pending = {}

def format_duration(sec):
    if not sec: return "?"
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def format_size(b):
    for u in ['B','KB','MB','GB']:
        if b < 1024: return f"{b:.1f}{u}"
        b /= 1024
    return f"{b:.1f}GB"

# ── Commands ──────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to Media Downloader Bot!*\n\n"
        "📲 Just send me any social media link!\n\n"
        "✅ *Supported:*\n"
        "YouTube • Instagram • TikTok • Twitter/X\n"
        "Facebook • Reddit • Pinterest • Vimeo • 1000+ more!\n\n"
        "🎬 Up to *4K quality*\n\n"
        "_Paste a link to get started!_ 🔗",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 *How to use:*\n\n"
        "1️⃣ Copy any video/photo link\n"
        "2️⃣ Paste it here\n"
        "3️⃣ Choose quality\n"
        "4️⃣ Get your file! 🎉\n\n"
        "⚠️ Max file size: 50MB",
        parse_mode="Markdown"
    )

# ── Link Handler ──────────────────────────────────────────
async def handle_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ Please send a valid URL!")
        return
    msg = await update.message.reply_text("🔍 Fetching info...")
    try:
        opts = get_ydl_opts()
        opts['skip_download'] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        title = (info.get('title') or 'Unknown')[:60]
        duration = format_duration(info.get('duration'))
        uploader = info.get('uploader') or info.get('channel') or 'Unknown'
        extractor = info.get('extractor_key', '')
        formats = info.get('formats', [])
        heights = [f.get('height') for f in formats if f.get('height')]
        max_h = max(heights) if heights else 0
        pending[user_id] = url
        row1 = [InlineKeyboardButton("🎬 Best/4K", callback_data="v|best")]
        if max_h >= 1080: row1.append(InlineKeyboardButton("📹 1080p", callback_data="v|1080"))
        if max_h >= 720:  row1.append(InlineKeyboardButton("📹 720p",  callback_data="v|720"))
        keyboard = [
            row1,
            [InlineKeyboardButton("📹 480p", callback_data="v|480"),
             InlineKeyboardButton("📹 360p", callback_data="v|360")],
            [InlineKeyboardButton("🎵 Audio MP3", callback_data="a|best"),
             InlineKeyboardButton("🖼 Photo",     callback_data="p|best")],
            [InlineKeyboardButton("❌ Cancel",    callback_data="cancel")],
        ]
        res_text = f"Up to {max_h}p" if max_h else "Auto"
        await msg.edit_text(
            f"✅ *Found!*\n\n📌 *{title}*\n"
            f"👤 {uploader}  |  ⏱ {duration}  |  🎬 {res_text}\n"
            f"🌐 {extractor}\n\n*Choose download option:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        err = str(e)
        if "Sign in" in err or "bot" in err.lower():
            await msg.edit_text("⚠️ YouTube blocked this. Try again in 30 seconds! 🔄")
        elif "Unsupported URL" in err:
            await msg.edit_text("❌ URL not supported. Try a direct post link.")
        elif "Private" in err or "login" in err.lower():
            await msg.edit_text("🔒 This content is private.")
        else:
            await msg.edit_text(f"❌ Error: {err[:200]}")

# ── Button Handler ────────────────────────────────────────
async def handle_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == "cancel":
        pending.pop(user_id, None)
        await query.edit_message_text("❌ Cancelled.")
        return
    url = pending.get(user_id)
    if not url:
        await query.edit_message_text("⚠️ Session expired. Send the link again.")
        return
    mode, quality = query.data.split("|")
    pending.pop(user_id, None)
    await query.edit_message_text("⬇️ Downloading... please wait ⏳")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            opts = get_ydl_opts(
                mode="audio" if mode=="a" else ("photo" if mode=="p" else "video"),
                quality=quality, tmpdir=tmpdir
            )
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            files = list(Path(tmpdir).iterdir())
            if not files: raise Exception("No file downloaded.")
            filepath = max(files, key=lambda f: f.stat().st_size)
            size = filepath.stat().st_size
            title = (info.get('title') or 'media')[:50]
            ext = filepath.suffix.lower()
            await query.edit_message_text(
                f"📤 Uploading *{title}* ({format_size(size)})...",
                parse_mode="Markdown"
            )
            if size > 50 * 1024 * 1024:
                await query.edit_message_text("❌ File too large (>50MB). Try 480p or 360p.")
                return
            with open(filepath, 'rb') as f:
                if mode == "a" or ext in ['.mp3','.m4a']:
                    await query.message.reply_audio(
                        audio=f, title=title,
                        performer=info.get('uploader',''),
                        caption=f"🎵 {title}\n_via Media Bot_",
                        parse_mode="Markdown"
                    )
                elif mode == "p" or ext in ['.jpg','.jpeg','.png','.webp']:
                    await query.message.reply_photo(
                        photo=f,
                        caption=f"🖼 {title}\n_via Media Bot_",
                        parse_mode="Markdown"
                    )
                else:
                    await query.message.reply_video(
                        video=f, supports_streaming=True,
                        caption=f"🎬 {title}\n_via Media Bot_",
                        parse_mode="Markdown"
                    )
            await query.edit_message_text(
                f"✅ Done! *{title}* sent! 🎉",
                parse_mode="Markdown"
            )
    except Exception as e:
        err = str(e)
        if "Sign in" in err or "bot" in err.lower():
            await query.edit_message_text("⚠️ YouTube blocked. Try again in 30 seconds! 🔄")
        elif "Requested format" in err:
            await query.edit_message_text("❌ Quality not available. Try lower quality.")
        else:
            await query.edit_message_text(f"❌ Failed: {err[:200]}")

# ── Main ──────────────────────────────────────────────────
async def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help",  cmd_help))
    application.add_handler(CallbackQueryHandler(handle_button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    print("🚀 Bot is LIVE!")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    # Keep running forever
    await asyncio.Event().wait()

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN not set!")
        return

    # Start Flask in background thread
    t = Thread(target=run_flask, daemon=True)
    t.start()
    print("✅ Flask keep-alive started!")

    # Run bot with asyncio
    asyncio.run(run_bot())

if __name__ == "__main__":
    main()
