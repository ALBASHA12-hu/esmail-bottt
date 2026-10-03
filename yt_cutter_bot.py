import os
import sys
import json
import asyncio
import glob
import time
import re
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# المسارات والبيئة
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] = BASE_DIR + os.pathsep + os.environ.get("PATH", "")

# مجلد حفظ الفيديوهات المحملة
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# إعدادات البوت والآدمن
BOT_TOKEN = "8905161884:AAErupkMRhm-cLdvGpjQwXBEqT_H27ivU24"
ADMIN_CHAT_ID = 7719030172

QUOTA_FILE = os.path.join(BASE_DIR, "user_quota.json")
MAX_DAILY_VIDEOS = 2
COOLDOWN_SECONDS = 24 * 3600

DOWNLOAD_LOCK = asyncio.Lock()
waiting_count = 0
USER_DATA = {}

# تحويل الرسائل لحسابك كآدمن
async def log_to_admin(context: ContextTypes.DEFAULT_TYPE, text: str):
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=text
            )
        except Exception as e:
            print(f"[-] خطأ إرسال للأدمن: {e}")

# ================= إدارة الحد الزمني =================
def get_user_quota_info(user_id: int):
    now = time.time()
    if os.path.exists(QUOTA_FILE):
        try:
            with open(QUOTA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            user_info = data.get(str(user_id))
            if user_info:
                count = user_info.get("count", 0)
                reset_time = user_info.get("reset_time", 0)

                if reset_time > 0 and now >= reset_time:
                    user_info = {"count": 0, "reset_time": 0}
                    data[str(user_id)] = user_info
                    with open(QUOTA_FILE, "w", encoding="utf-8") as wf:
                        json.dump(data, wf, ensure_ascii=False, indent=2)
                    return True, 0, 0

                if count >= MAX_DAILY_VIDEOS:
                    rem = int(reset_time - now)
                    if rem > 0:
                        return False, rem, count
                    else:
                        user_info = {"count": 0, "reset_time": 0}
                        data[str(user_id)] = user_info
                        with open(QUOTA_FILE, "w", encoding="utf-8") as wf:
                            json.dump(data, wf, ensure_ascii=False, indent=2)
                        return True, 0, 0

                return True, 0, count
        except Exception:
            pass
    return True, 0, 0

def deduct_quota(user_id: int):
    now = time.time()
    data = {}
    if os.path.exists(QUOTA_FILE):
        try:
            with open(QUOTA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    user_info = data.get(str(user_id), {"count": 0, "reset_time": 0})
    if user_info.get("reset_time", 0) > 0 and now >= user_info["reset_time"]:
        user_info = {"count": 0, "reset_time": 0}

    user_info["count"] = user_info.get("count", 0) + 1

    if user_info["count"] >= MAX_DAILY_VIDEOS:
        user_info["reset_time"] = now + COOLDOWN_SECONDS

    data[str(user_id)] = user_info

    with open(QUOTA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def format_remaining_time(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0 and minutes > 0:
        return f"{hours} ساعة و {minutes} دقيقة"
    elif hours > 0:
        return f"{hours} ساعة"
    elif minutes > 0:
        return f"{minutes} دقيقة"
    else:
        return f"{seconds} ثانية"

def extract_youtube_url(text: str):
    match = re.search(r'(https?://(?:www\.)?(?:youtube\.com/[^\s]+|youtu\.be/[^\s]+))', text)
    if match:
        return match.group(1).strip()
    return None

def parse_time_to_seconds(time_str: str):
    time_str = time_str.strip()
    parts = time_str.split(":")
    try:
        if len(parts) == 1:
            return int(parts[0])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return None
    return None

def format_seconds_to_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

# ================= أوامر البوت =================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    USER_DATA.pop(user_id, None)
    
    await log_to_admin(
        context,
        f"👤 مستخدم فتح البوت:\n"
        f"• الاسم: {user.full_name}\n"
        f"• المعرف: @{user.username or 'بدون'}\n"
        f"• الآيدي: {user_id}\n"
        f"• الأمر: /start"
    )

    welcome_text = (
        "🍃🤍 **أهلاً بك في بوت تحميل الآسر**\n\n"
        "🌱 يمكنك قص وتحميل أي مقطع تريده بأعلى جودة ممكنة.\n"
        f"📌 الحد الأقصى المتاح لك: **{MAX_DAILY_VIDEOS} فيديوهات كل 24 ساعة** 🌿\n\n"
        "⏳ **تنبيه:** إذا تأخر البوت في الرد، فيكون ذلك بسبب ضغط الطلبات؛ فضلاً انتظر دقائق وسيتم الرد عليك تلقائياً فور انتهاء الضغط 🤍\n\n"
        "🔗 **أرسل الآن رابط فيديو اليوتيوب للبدء:**"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    USER_DATA.pop(user_id, None)
    
    await log_to_admin(context, f"🚫 المستخدم {user_id} (@{user.username or 'بدون'}) ألغى العملية.")
    await update.message.reply_text("❌ تم إلغاء العملية بنجاح 🌿 أرسل رابط الفيديو للبدء مجدداً في أي وقت.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()
    
    await log_to_admin(
        context,
        f"📩 رسالة واردة:\n"
        f"• من: {user.full_name} ({user_id}) | @{user.username or 'بدون'}\n"
        f"• النص: {text}"
    )

    yt_url = extract_youtube_url(text)
    if yt_url:
        can_dl, rem_sec, _ = get_user_quota_info(user_id)
        if not can_dl:
            time_text = format_remaining_time(rem_sec)
            rep = (
                f"🤍 **عذراً، لقد وصلت إلى الحد الأقصى المسموح به ({MAX_DAILY_VIDEOS} فيديوهات).**\n\n"
                f"⏳ **الوقت المتبقي لإتاحة التحميل مجدداً:** `{time_text}` 🌿🤍"
            )
            USER_DATA.pop(user_id, None)
            await update.message.reply_text(rep, parse_mode="Markdown")
            await log_to_admin(context, f"⚠️ المستخدم {user_id} أرسل رابطاً وتوقف بسبب الحد الزمني (متبقي: {time_text}).")
            return

        USER_DATA[user_id] = {"state": "AWAIT_START", "url": yt_url}
        rep = "⏱️ **أرسل وقت بداية المقطع:**\n(مثال: `00:30` أو `01:15` أو `01:05:20`) 🌿"
        await update.message.reply_text(rep, parse_mode="Markdown")
        await log_to_admin(context, f"🤖 رد البوت على {user_id}: طلب وقت البداية.")
        return

    user_session = USER_DATA.get(user_id)
    if not user_session:
        rep = "🍃🤍 أهلاً بك في **بوت تحميل الآسر**\nأرسل رابط فيديو اليوتيوب للبدء 🌿"
        await update.message.reply_text(rep, parse_mode="Markdown")
        return

    state = user_session.get("state")

    if state == "AWAIT_START":
        t_sec = parse_time_to_seconds(text)
        if t_sec is None or t_sec < 0:
            rep = "⚠️ صيغة الوقت غير صحيحة، يرجى كتابة وقت البداية بشكل صحيح (مثال: `01:20`):"
            await update.message.reply_text(rep, parse_mode="Markdown")
            return
        user_session["start_sec"] = t_sec
        user_session["state"] = "AWAIT_END"
        rep = "⏱ **أرسل وقت نهاية المقطع:**\n(مثال: `01:50` أو `02:30`) 🌿"
        await update.message.reply_text(rep, parse_mode="Markdown")
        await log_to_admin(context, f"🤖 رد البوت على {user_id}: طلب وقت النهاية.")

    elif state == "AWAIT_END":
        t_sec = parse_time_to_seconds(text)
        start_sec = user_session.get("start_sec", 0)
        if t_sec is None or t_sec <= start_sec:
            rep = "⚠️ وقت النهاية يجب أن يكون أكبر من وقت البداية! يرجى إرساله مجدداً:"
            await update.message.reply_text(rep)
            return
        user_session["end_sec"] = t_sec
        user_session["state"] = "SELECT_QUALITY"

        keyboard = [
            [
                InlineKeyboardButton("🌿 4K MP4", callback_data="q_4k_mp4")
            ],
            [
                InlineKeyboardButton("📁 4K FILE (ملف)", callback_data="q_4k_doc")
            ],
            [
                InlineKeyboardButton("🌱 1080p MP4", callback_data="q_1080_mp4")
            ],
            [InlineKeyboardButton("❌ إلغاء العملية", callback_data="q_cancel")]
        ]
        rep = (
            f"✅ **تم تحديد المدة بنجاح:**\nمن `{format_seconds_to_time(start_sec)}` إلى `{format_seconds_to_time(t_sec)}` ⏱️\n\n"
            "اختر الصيغة والجودة المطلوبة للبدء 👇"
        )
        await update.message.reply_text(
            rep,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        await log_to_admin(context, f"🤖 تم إرسال خيارات الجودة للمستخدم {user_id}.")

async def run_ytdlp_cmd(url, start_sec, end_sec, quality_mode, output_base):
    start_fmt = format_seconds_to_time(start_sec)
    end_fmt = format_seconds_to_time(end_sec)
    section_val = f"*{start_fmt}-{end_fmt}"

    ytdlp_bin = os.path.join(BASE_DIR, "yt-dlp.exe")
    if not os.path.exists(ytdlp_bin):
        ytdlp_bin = "yt-dlp"

    out_tmpl = f"{output_base}.%(ext)s"

    if quality_mode == "4k_mp4":
        cmd = [
            ytdlp_bin,
            "--download-sections", section_val,
            "-f", "bestvideo[height<=2160]+bestaudio/best",
            "--merge-output-format", "mp4",
            "--postprocessor-args", "ffmpeg:-movflags +faststart",
            "-o", out_tmpl,
            url
        ]
    elif quality_mode == "4k_doc":
        cmd = [
            ytdlp_bin,
            "--download-sections", section_val,
            "-f", "bestvideo[height<=2160]+bestaudio/best",
            "-o", out_tmpl,
            url
        ]
    else:  # 1080_mp4
        cmd = [
            ytdlp_bin,
            "--download-sections", section_val,
            "-f", "bestvideo[height<=1080]+bestaudio/best",
            "--merge-output-format", "mp4",
            "--postprocessor-args", "ffmpeg:-movflags +faststart",
            "-o", out_tmpl,
            url
        ]

    print(f"\n[EXEC CMD]: {' '.join(cmd)}\n")
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.wait()

    matched = glob.glob(f"{output_base}.*")
    return matched[0] if matched else None

async def quality_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global waiting_count
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    user_id = user.id

    await log_to_admin(context, f"🔘 المستخدم {user_id} اختار: {data}")

    if data == "q_cancel":
        USER_DATA.pop(user_id, None)
        await query.edit_message_text("❌ تم إلغاء العملية بنجاح 🌿")
        return

    can_dl, rem_sec, _ = get_user_quota_info(user_id)
    if not can_dl:
        time_text = format_remaining_time(rem_sec)
        rep = (
            f"🤍 **عذراً، لقد وصلت إلى الحد الأقصى المسموح به ({MAX_DAILY_VIDEOS} فيديوهات).**\n\n"
            f"⏳ **الوقت المتبقي لإتاحة التحميل مجدداً:** `{time_text}` 🌿🤍"
        )
        await query.edit_message_text(rep, parse_mode="Markdown")
        USER_DATA.pop(user_id, None)
        return

    session = USER_DATA.get(user_id)
    if not session or "url" not in session:
        await query.edit_message_text("⚠️ انتهت صلاحية الجلسة، يرجى إرسال رابط الفيديو مجدداً 🌿")
        return

    url = session["url"]
    start_sec = session["start_sec"]
    end_sec = session["end_sec"]
    quality_mode = data.replace("q_", "")
    USER_DATA.pop(user_id, None)

    is_busy = DOWNLOAD_LOCK.locked()
    if is_busy:
        waiting_count += 1
        pos = waiting_count
        status_msg = await query.edit_message_text(
            f"🚦 **طلبك قيد الانتظار (ترتيبك: {pos})**\n\n"
            "جاري معالجة مقطع لمستخدم آخر حالياً بأقصى جودة.\n"
            "سيبدأ طلبك تلقائياً وبشكل فوري بعد قليل ⌛🤍",
            parse_mode="Markdown"
        )
        await log_to_admin(context, f"🚦 المستخدم {user_id} دخل الطابور برقم: {pos}")
    else:
        status_msg = await query.edit_message_text("⚡ **جاري بدء عملية التحميل والقص المباشر...** ⏳", parse_mode="Markdown")

    async with DOWNLOAD_LOCK:
        if is_busy:
            waiting_count = max(0, waiting_count - 1)
            await status_msg.edit_text("⚡ **حان دورك الآن! بدأ التحميل والقص فوراً...** 🎬", parse_mode="Markdown")

        # حفظ الملف في مجلد downloads
        time_stamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_prefix = f"vid_{user_id}_{time_stamp_str}"
        target_base = os.path.join(DOWNLOADS_DIR, file_prefix)
        final_50mb_file = os.path.join(DOWNLOADS_DIR, f"{file_prefix}_telegram.mp4")
        downloaded_file = None

        try:
            downloaded_file = await run_ytdlp_cmd(url, start_sec, end_sec, quality_mode, target_base)
            if not downloaded_file or not os.path.exists(downloaded_file):
                await context.bot.send_message(chat_id=user_id, text="❌ تعذر تحميل المقطع، يرجى التأكد من الرابط والمحاولة مجدداً 🌿")
                return

            file_size_mb = os.path.getsize(downloaded_file) / (1024 * 1024)
            print(f"[+] اكتمل التحميل وحُفظ في المجلد! الملف: {downloaded_file} | الحجم: {file_size_mb:.2f} MB")

            trimmed = False
            if file_size_mb <= 49.0:
                upload_file = downloaded_file
            else:
                trimmed = True
                ffmpeg_bin = os.path.join(BASE_DIR, "ffmpeg.exe")
                if not os.path.exists(ffmpeg_bin):
                    ffmpeg_bin = "ffmpeg"
                trim_cmd = [
                    ffmpeg_bin, "-y",
                    "-i", downloaded_file,
                    "-fs", "48M",
                    "-c", "copy",
                    final_50mb_file
                ]
                p_trim = await asyncio.create_subprocess_exec(*trim_cmd)
                await p_trim.wait()
                upload_file = final_50mb_file if os.path.exists(final_50mb_file) else downloaded_file

            await status_msg.edit_text("📤 **تم التجهيز بنجاح! جاري رفع المقطع إليك الآن...** 🌿", parse_mode="Markdown")

            start_fmt = format_seconds_to_time(start_sec)
            end_fmt = format_seconds_to_time(end_sec)
            actual_size = os.path.getsize(upload_file) / (1024 * 1024)
            
            caption = f"🎬 **تم القص والتحميل بنجاح!**\n⏱ المدة: من `{start_fmt}` إلى `{end_fmt}`\n📦 الحجم: `{actual_size:.1f} MB` 🌿"
            if trimmed:
                caption += "\n\n⚠️ **تنبيه:** تجاوز الحجم 50MB وتم إرسال أول جزء ليتوافق مع سقف تليجرام."

            try:
                with open(upload_file, "rb") as media_file:
                    if quality_mode == "4k_doc":
                        await context.bot.send_document(
                            chat_id=user_id,
                            document=media_file,
                            caption=caption,
                            parse_mode="Markdown",
                            read_timeout=1200,
                            write_timeout=1200
                        )
                    else:
                        await context.bot.send_video(
                            chat_id=user_id,
                            video=media_file,
                            caption=caption,
                            parse_mode="Markdown",
                            supports_streaming=True,
                            read_timeout=1200,
                            write_timeout=1200
                        )
            except Exception as send_err:
                if "Timed out" in str(send_err):
                    print("[!] تم رفع الفيديو وتأخر الرد.")
                else:
                    raise send_err

            # رسالة الدعاء
            dua_msg = "نسألكم الدعاء فضلاً 🤲 جزانا وإياكم خير الجزاء 🤍"
            await context.bot.send_message(
                chat_id=user_id,
                text=dua_msg
            )

            # تسجيل الخصم وتفعيل الـ 24 ساعة
            deduct_quota(user_id)

            try:
                await status_msg.delete()
            except Exception:
                pass
            print(f"[+] تم الإرسال للمستخدم، والملف الأصلي محفوظ في {DOWNLOADS_DIR}\n")
            await log_to_admin(context, f"✅ تم إرسال المقطع ورسالة الدعاء بنجاح للمستخدم {user_id} (الحجم: {actual_size:.1f} MB)")

        except Exception as e:
            print(f"[-] خطأ: {e}")
            await context.bot.send_message(chat_id=user_id, text=f"❌ حدث خطأ أثناء المعالجة: {e}")

        finally:
            # حذف الملف المؤقت فقط إذا تم إنشاؤه لتجاوز حد الـ 50MB لتيليجرام
            # أما downloaded_file (الفيديو الأصلي المحمل) يظل محفوظاً في مجلد downloads
            if os.path.exists(final_50mb_file):
                try:
                    os.remove(final_50mb_file)
                except Exception:
                    pass

def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .connection_pool_size(100)
        .read_timeout(1200)
        .write_timeout(1200)
        .connect_timeout(1200)
        .pool_timeout(1200)
        .build()
    )

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CallbackQueryHandler(quality_callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))

    print(f"🚀 البوت يعمل الآن - جميع الفيديوهات تُحفظ في المجلد: {DOWNLOADS_DIR}")
    app.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()