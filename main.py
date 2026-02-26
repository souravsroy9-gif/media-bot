import os
import logging
import asyncio
import tempfile
import re
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

# ── Flask Keep Alive ──────────────────────────────────────
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ Media Bot is Running!"

def run_flask():
    flask_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# ── Platform Detection ────────────────────────────────────
def detect_platform(url):
    u = url.lower()
    if 'youtube.com' in u or 'youtu.be' in u: return 'youtube'
    if 'instagram.com' in u: return 'instagram'
    if 'tiktok.com' in u: return 'tiktok'
    if 'twitter.com' in u or 'x.com' in u: return 'twitter'
    if 'facebook.com' in u or 'fb.watch' in u: return 'facebook'
    if 'reddit.com' in u: return 'reddit'
    if 'vimeo.com' in u: return 'vimeo'
    if 'pinterest.com' in u: return 'pinterest'
    return 'other'

# ── YT-DLP (for TikTok, Twitter, Reddit etc.) ────────────
def get_ydl_opts(mode="video", quality="best", tmpdir="."):
    common = {
        'quiet': True,
        'no_warnings': True,
        'outtmpl': os.path.join(tmpdir, '%(title).50s.%(ext)s'),
        'socket_timeout': 30,
        'retries': 5,
        'http_headers': {
            'User-Agent': (
                'Mozilla/5.0 (Linux; Android 13; Pixel 7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/116.0.0.0 Mobile Safari/537.36'
            ),
        },
    }
    if mode == "audio":
        common['format'] = 'bestaudio/best'
        common['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        q_map = {
            'best': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '720':  'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
            '480':  'bestvideo[height<=480]+bestaudio/best[height<=480]/best',
            '360':  'bestvideo[height<=360]+bestaudio/best[height<=360]/best',
        }
        common['format'] = q_map.get(quality, q_map['best'])
        common['merge_output_format'] = 'mp4'
    return common

def format_size(b):
    for u in ['B','KB','MB','GB']:
        if b < 1024: return f"{b:.1f}{u}"
        b /= 1024
    return f"{b:.1f}GB"

pending = {}

# ── Commands ──────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to Media Bot!*\n\n"
        "📲 Send me any social media link!\n\n"
        "✅ *Direct download:*\n"
        "🎵 TikTok (no watermark)\n"
        "🐦 Twitter / X\n"
        "🟠 Reddit\n"
        "📘 Facebook\n"
        "🎥 Vimeo\n\n"
        "🔗 *Smart link (opens in Safari):*\n"
        "🎬 YouTube → cobalt.tools\n"
        "📸 Instagram → snapinsta.app\n\n"
        "_Just paste any link to get started!_ 🚀",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 *How to use:*\n\n"
        "1️⃣ Copy any video link\n"
        "2️⃣ Paste it here\n"
        "3️⃣ For TikTok/Twitter/Reddit → choose quality, file sent directly!\n"
        "4️⃣ For YouTube/Instagram → tap the link to open in Safari\n\n"
        "⚠️ Max file size: 50MB",
        parse_mode="Markdown"
    )

# ── Link Handler ──────────────────────────────────────────
async def handle_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ Please send a valid URL starting with https://")
        return

    platform = detect_platform(url)

    # ── YouTube: send cobalt.tools link ──────────────────
    if platform == 'youtube':
        import urllib.parse
        cobalt_url = f"https://cobalt.tools/#{urllib.parse.quote(url)}"
        keyboard = [[
            InlineKeyboardButton("🎬 Open in cobalt.tools", url=cobalt_url)
        ]]
        await update.message.reply_text(
            "🎬 *YouTube Link Detected!*\n\n"
            "Tap the button below to download in Safari!\n"
            "cobalt.tools works perfectly for YouTube 🚀\n\n"
            "💡 *Tip:* Choose your quality on the cobalt page, then download!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    # ── Instagram: send snapinsta link ───────────────────
    if platform == 'instagram':
        keyboard = [[
            InlineKeyboardButton("📸 Open in SnapInsta", url="https://snapinsta.app")
        ]]
        await update.message.reply_text(
            "📸 *Instagram Link Detected!*\n\n"
            "Instagram blocks all bots on free servers.\n\n"
            "✅ *Use this instead:*\n"
            "1️⃣ Tap the button below\n"
            "2️⃣ Paste your link in snapinsta.app\n"
            "3️⃣ Download instantly! 🎉\n\n"
            "snapinsta.app works for ALL Instagram posts & reels!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    # ── Other platforms: download directly ───────────────
    platform_names = {
        'tiktok': 'TikTok', 'twitter': 'Twitter/X',
        'facebook': 'Facebook', 'reddit': 'Reddit',
        'vimeo': 'Vimeo', 'pinterest': 'Pinterest', 'other': 'Media'
    }
    pname = platform_names.get(platform, 'Media')

    msg = await update.message.reply_text(f"🔍 Processing {pname} link...")
    pending[user_id] = url

    keyboard = [
        [InlineKeyboardButton("🎬 Best Quality", callback_data="v|best"),
         InlineKeyboardButton("📹 720p",         callback_data="v|720")],
        [InlineKeyboardButton("📹 480p",         callback_data="v|480"),
         InlineKeyboardButton("📹 360p",         callback_data="v|360")],
        [InlineKeyboardButton("🎵 Audio MP3",    callback_data="a|best")],
        [InlineKeyboardButton("❌ Cancel",        callback_data="cancel")],
    ]

    await msg.edit_text(
        f"✅ *{pname} link ready!*\n\n"
        f"🔗 `{url[:50]}{'...' if len(url)>50 else ''}`\n\n"
        f"*Choose download option:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

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
    platform = detect_platform(url)
    pname = platform.title()

    await query.edit_message_text(f"⬇️ Downloading from {pname}... ⏳")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            opts = get_ydl_opts(
                mode="audio" if mode=="a" else "video",
                quality=quality,
                tmpdir=tmpdir
            )
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)

            files = list(Path(tmpdir).iterdir())
            if not files:
                raise Exception("No file was downloaded.")

            filepath = max(files, key=lambda f: f.stat().st_size)
            size = filepath.stat().st_size
            title = (info.get('title') or 'media')[:50]
            ext = filepath.suffix.lower()

            if size > 50 * 1024 * 1024:
                await query.edit_message_text(
                    f"❌ File too large ({format_size(size)})\n"
                    "Please try 480p or 360p quality!"
                )
                return

            await query.edit_message_text(
                f"📤 Uploading *{title}* ({format_size(size)})...",
                parse_mode="Markdown"
            )

            with open(filepath, 'rb') as f:
                if mode == "a" or ext in ['.mp3', '.m4a']:
                    await query.message.reply_audio(
                        audio=f, title=title,
                        performer=info.get('uploader', ''),
                        caption=f"🎵 {title}\n_via Media Bot_",
                        parse_mode="Markdown"
                    )
                elif ext in ['.jpg', '.jpeg', '.png', '.webp']:
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
                f"✅ *Done! {title} sent!* 🎉",
                parse_mode="Markdown"
            )

    except Exception as e:
        err = str(e)
        log.error(f"Download error: {err}")
        if 'Sign in' in err or 'bot' in err.lower():
            await query.edit_message_text(
                "⚠️ This platform blocked the download.\n"
                "Try again in 30 seconds! 🔄"
            )
        elif 'Requested format' in err:
            await query.edit_message_text("❌ Quality not available. Try lower quality!")
        elif 'too large' in err.lower() or '413' in err:
            await query.edit_message_text("❌ File too large. Try 360p or Audio MP3!")
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
    await asyncio.Event().wait()

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN not set!")
        return
    Thread(target=run_flask, daemon=True).start()
    print("✅ Flask started!")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()

if __name__ == "__main__":
    main()
