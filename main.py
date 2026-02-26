import os
import logging
import asyncio
import requests
import tempfile
from pathlib import Path
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ── Cobalt API instances (free, no bot detection!) ────────
COBALT_INSTANCES = [
    "https://api.cobalt.tools",
    "https://cobalt.api.timelessnesses.me",
    "https://cobalt.tools/api",
]

# ── Keep Alive Flask ──────────────────────────────────────
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ Media Bot is Running! Powered by Cobalt API"

def run_flask():
    flask_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# ── Cobalt API call ───────────────────────────────────────
def cobalt_get_url(url, quality="1080", audio_only=False):
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)"
    }
    payload = {
        "url": url,
        "videoQuality": quality,
        "audioFormat": "mp3",
        "audioBitrate": "320",
        "downloadMode": "audio" if audio_only else "auto",
        "filenameStyle": "pretty",
    }

    for instance in COBALT_INSTANCES:
        try:
            r = requests.post(
                instance,
                json=payload,
                headers=headers,
                timeout=15
            )
            if r.status_code == 200:
                data = r.json()
                status = data.get("status", "")

                if status == "stream" or status == "redirect" or status == "tunnel":
                    return {"success": True, "url": data.get("url"), "type": "video"}
                elif status == "picker":
                    # Multiple items (e.g. Instagram carousel)
                    items = data.get("picker", [])
                    if items:
                        return {"success": True, "url": items[0].get("url"), "type": "picker", "items": items}
                elif status == "error":
                    log.warning(f"Cobalt error from {instance}: {data.get('error', {})}")
                    continue
        except Exception as e:
            log.warning(f"Cobalt instance {instance} failed: {e}")
            continue

    return {"success": False, "error": "All Cobalt instances failed"}

def detect_platform(url):
    url = url.lower()
    if 'youtube.com' in url or 'youtu.be' in url: return 'YouTube'
    if 'instagram.com' in url: return 'Instagram'
    if 'tiktok.com' in url: return 'TikTok'
    if 'twitter.com' in url or 'x.com' in url: return 'Twitter/X'
    if 'facebook.com' in url or 'fb.watch' in url: return 'Facebook'
    if 'reddit.com' in url: return 'Reddit'
    if 'vimeo.com' in url: return 'Vimeo'
    if 'pinterest.com' in url: return 'Pinterest'
    if 'twitch.tv' in url: return 'Twitch'
    if 'soundcloud.com' in url: return 'SoundCloud'
    return 'Media'

def format_size(b):
    if not b: return "?"
    for u in ['B','KB','MB','GB']:
        if b < 1024: return f"{b:.1f}{u}"
        b /= 1024
    return f"{b:.1f}GB"

pending = {}

# ── Commands ──────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to Media Bot!*\n\n"
        "🚀 *Powered by Cobalt API*\n\n"
        "✅ *Supported platforms:*\n"
        "🎬 YouTube\n"
        "📸 Instagram (public & reels)\n"
        "🎵 TikTok (no watermark)\n"
        "🐦 Twitter / X\n"
        "📘 Facebook\n"
        "🟠 Reddit\n"
        "🎥 Vimeo\n"
        "📌 Pinterest\n"
        "💜 Twitch clips\n"
        "🎶 SoundCloud\n\n"
        "📲 *Just paste any link!* 🔗",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 *How to use:*\n\n"
        "1️⃣ Copy any video/photo link\n"
        "2️⃣ Paste it here\n"
        "3️⃣ Choose quality\n"
        "4️⃣ Get your file! 🎉\n\n"
        "⚠️ *Limits:*\n"
        "• Max file size: 50MB (Telegram limit)\n"
        "• For large files try lower quality\n\n"
        "💡 *Tip:* Works best with public content!",
        parse_mode="Markdown"
    )

# ── Link Handler ──────────────────────────────────────────
async def handle_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ Please send a valid link starting with http:// or https://")
        return

    platform = detect_platform(url)
    msg = await update.message.reply_text(f"🔍 Processing {platform} link...")

    pending[user_id] = url

    # Build quality buttons
    keyboard = []

    if platform == 'YouTube':
        keyboard = [
            [InlineKeyboardButton("🎬 4K", callback_data="v|2160"),
             InlineKeyboardButton("🎬 2K", callback_data="v|1440")],
            [InlineKeyboardButton("📹 1080p", callback_data="v|1080"),
             InlineKeyboardButton("📹 720p",  callback_data="v|720")],
            [InlineKeyboardButton("📹 480p", callback_data="v|480"),
             InlineKeyboardButton("📹 360p", callback_data="v|360")],
            [InlineKeyboardButton("🎵 Audio MP3", callback_data="a|best")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        ]
    elif platform in ['Instagram', 'TikTok', 'Twitter/X', 'Facebook']:
        keyboard = [
            [InlineKeyboardButton("🎬 Best Quality", callback_data="v|1080")],
            [InlineKeyboardButton("🎵 Audio Only",   callback_data="a|best")],
            [InlineKeyboardButton("❌ Cancel",        callback_data="cancel")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🎬 Best Quality", callback_data="v|1080"),
             InlineKeyboardButton("📹 720p",         callback_data="v|720")],
            [InlineKeyboardButton("🎵 Audio Only",   callback_data="a|best")],
            [InlineKeyboardButton("❌ Cancel",        callback_data="cancel")],
        ]

    await msg.edit_text(
        f"✅ *{platform} link detected!*\n\n"
        f"🔗 `{url[:60]}{'...' if len(url)>60 else ''}`\n\n"
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

    await query.edit_message_text(f"⬇️ Downloading from {platform}... please wait ⏳")

    try:
        # Call Cobalt API
        audio_only = (mode == "a")
        result = cobalt_get_url(url, quality=quality, audio_only=audio_only)

        if not result["success"]:
            await query.edit_message_text(
                f"❌ Download failed!\n\n"
                f"*Reason:* {result.get('error', 'Unknown error')}\n\n"
                f"Try:\n"
                f"• A different quality\n"
                f"• Make sure the post is public\n"
                f"• Try again in 1 minute",
                parse_mode="Markdown"
            )
            return

        download_url = result["url"]
        await query.edit_message_text(f"📥 Fetching file from {platform}...")

        # Download the file
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = "mp3" if audio_only else "mp4"
            filepath = os.path.join(tmpdir, f"media.{ext}")

            r = requests.get(
                download_url,
                stream=True,
                timeout=60,
                headers={
                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15"
                }
            )
            r.raise_for_status()

            # Check content type
            content_type = r.headers.get("content-type", "")
            if "image" in content_type:
                ext = "jpg"
                filepath = os.path.join(tmpdir, f"media.jpg")
            elif "audio" in content_type or audio_only:
                ext = "mp3"
                filepath = os.path.join(tmpdir, f"media.mp3")

            with open(filepath, 'wb') as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

            size = os.path.getsize(filepath)

            if size > 50 * 1024 * 1024:
                await query.edit_message_text(
                    f"❌ File too large ({format_size(size)})\n\n"
                    f"Telegram limit is 50MB.\n"
                    f"Please try:\n"
                    f"• Lower quality (480p or 360p)\n"
                    f"• Audio MP3 only"
                )
                return

            await query.edit_message_text(
                f"📤 Uploading ({format_size(size)})...",
            )

            with open(filepath, 'rb') as f:
                if ext == "mp3" or audio_only:
                    await query.message.reply_audio(
                        audio=f,
                        caption=f"🎵 Downloaded via Media Bot\n_Powered by Cobalt_",
                        parse_mode="Markdown"
                    )
                elif ext == "jpg" or "image" in content_type:
                    await query.message.reply_photo(
                        photo=f,
                        caption=f"🖼 Downloaded via Media Bot\n_Powered by Cobalt_",
                        parse_mode="Markdown"
                    )
                else:
                    await query.message.reply_video(
                        video=f,
                        supports_streaming=True,
                        caption=f"🎬 Downloaded via Media Bot\n_Powered by Cobalt_",
                        parse_mode="Markdown"
                    )

        await query.edit_message_text("✅ *Done! File sent successfully!* 🎉", parse_mode="Markdown")

    except requests.exceptions.Timeout:
        await query.edit_message_text(
            "⏱ Download timed out.\n"
            "The file may be too large. Try lower quality!"
        )
    except Exception as e:
        log.error(f"Download error: {e}")
        await query.edit_message_text(
            f"❌ Something went wrong!\n\n"
            f"`{str(e)[:200]}`\n\n"
            f"Please try again!",
            parse_mode="Markdown"
        )

# ── Main ──────────────────────────────────────────────────
async def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help",  cmd_help))
    application.add_handler(CallbackQueryHandler(handle_button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    print("🚀 Bot is LIVE! Powered by Cobalt API")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    await asyncio.Event().wait()

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN not set!")
        return
    t = Thread(target=run_flask, daemon=True)
    t.start()
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
