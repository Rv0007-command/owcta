import os
import sys
import subprocess
import asyncio
import logging

# ========== PENGECEKAN DEPENDENSI AWAL ==========
def check_dependencies():
    missing = []
    try:
        import telegram
        import requests
    except ImportError:
        missing.append("python-telegram-bot requests")
    
    # Cek yt-dlp
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        missing.append("yt-dlp")
    
    # Cek ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        missing.append("ffmpeg")
    
    if missing:
        print("\n❌ DEPENDENSI BELUM TERINSTAL!")
        print("Silakan jalankan perintah berikut:\n")
        print("pip install python-telegram-bot requests yt-dlp")
        if "ffmpeg" in missing:
            print("sudo apt install ffmpeg -y   # untuk Ubuntu/Debian")
        print("\nSetelah itu, jalankan ulang bot.\n")
        sys.exit(1)

check_dependencies()

# ========== IMPOR SETELAH PENGECEKAN ==========
import requests
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.request import HTTPXRequest

# === CONFIG OXYX V109.1 ===
TOKEN = "8328979483:AAGVICrdqOy-vf_az7zg3tZRPBwHcCwfwTw"
WORK_DIR = os.path.join(os.getcwd(), "oxyx_engine")
if not os.path.exists(WORK_DIR):
    os.makedirs(WORK_DIR)

# --- CLEAN LOGGING SYSTEM ---
logging.basicConfig(format='[%(asctime)s] %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

USER_STATES = {}
ACTIVE_PROCESS = {}

# ================= TERMINAL PROGRESS BAR =================
class ProgressBar:
    def __init__(self, total_steps=100):
        self.total = total_steps
        self.current = 0
        self._stop = False
        self._task = None
        self._lock = asyncio.Lock()
        self._message = ""
        self._spinner = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
        self._spinner_idx = 0

    async def start(self, message="Processing..."):
        async with self._lock:
            self._stop = False
            self.current = 0
            self._message = message
            self._task = asyncio.create_task(self._animate())

    async def update(self, percent, message=None):
        async with self._lock:
            self.current = percent
            if message:
                self._message = message

    async def _animate(self):
        while not self._stop:
            filled = int(self.current / 100 * 10)
            bar = "▓" * filled + "░" * (10 - filled)
            spinner = self._spinner[self._spinner_idx % len(self._spinner)]
            sys.stdout.write(f"\r{spinner} {self._message} [{bar}] {self.current}%")
            sys.stdout.flush()
            self._spinner_idx += 1
            await asyncio.sleep(0.1)
        sys.stdout.write("\r" + " " * 50 + "\r")
        sys.stdout.flush()

    async def stop(self):
        async with self._lock:
            self._stop = True
            if self._task:
                await self._task
                self._task = None

progress = ProgressBar()

# ================= DOWNLOADER =================
def run_safe_download(url, output_path):
    cmd_hq = [
        "yt-dlp", "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4/best",
        url, "-o", output_path, "--no-playlist", "--max-filesize", "50M",
        "--merge-output-format", "mp4", "--no-check-certificate"
    ]
    cmd_fallback = ["yt-dlp", "-f", "best", url, "-o", output_path, "--no-playlist", "--max-filesize", "50M"]

    try:
        subprocess.run(cmd_hq, capture_output=True, text=True, timeout=120)
        if os.path.exists(output_path):
            return True, "HQ Success"
        subprocess.run(cmd_fallback, capture_output=True, timeout=120)
        if os.path.exists(output_path):
            return True, "Fallback Success"
        return False, "File tidak ditemukan"
    except subprocess.TimeoutExpired:
        return False, "Waktu download habis"
    except Exception as e:
        return False, str(e)

async def run_safe_download_async(url, output_path, progress_bar):
    async def update_progress():
        for p in range(0, 101, 10):
            await progress_bar.update(p, f"Mengunduh {p}%...")
            await asyncio.sleep(0.5)

    loop = asyncio.get_running_loop()
    download_future = loop.run_in_executor(None, run_safe_download, url, output_path)
    progress_task = asyncio.create_task(update_progress())
    try:
        result = await download_future
        progress_task.cancel()
        return result
    except Exception as e:
        progress_task.cancel()
        return False, str(e)

# ================= AI GAMBAR =================
async def generate_image(chat_id, prompt):
    img_path = os.path.join(WORK_DIR, f"ai_{chat_id}.jpg")
    encoded_prompt = prompt.replace(' ', '%20')
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?nologo=true&width=1024&height=1024"

    await progress.update(10, "Mengirim permintaan...")
    await asyncio.sleep(0.5)
    await progress.update(30, "Menunggu respon server...")

    for attempt in range(2):
        try:
            response = requests.get(url, timeout=60)
            if response.status_code == 200 and 'image' in response.headers.get('content-type', ''):
                if len(response.content) > 1000:
                    await progress.update(70, "Menyimpan gambar...")
                    with open(img_path, "wb") as f:
                        f.write(response.content)
                    await progress.update(100, "Selesai!")
                    return img_path
        except Exception as e:
            logging.error(f"Image attempt {attempt+1} error: {e}")
        if attempt == 0:
            await progress.update(50, "Coba ulang...")
        await asyncio.sleep(1)
    return None

# ================= MENU =================
async def ls_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_time = time.time()
    chat_id = update.effective_chat.id
    USER_STATES[chat_id] = None
    keyboard = [
        [InlineKeyboardButton("🎬 Video AI", callback_data='m_video'), InlineKeyboardButton("🎨 Gambar AI", callback_data='m_image')],
        [InlineKeyboardButton("📥 Video Downloader", callback_data='m_dl')],
        [InlineKeyboardButton("📊 Info & Penawaran", callback_data='m_info')],
        [InlineKeyboardButton("🛰️ Status", callback_data='m_check'), InlineKeyboardButton("👨‍💻 Admin", callback_data='m_admin')]
    ]
    text = "🚀 **OXYX V109.1 - CLEAN CONSOLE**\nSistem berjalan dalam mode senyap, Tuan."

    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    elapsed = time.time() - start_time
    logging.info(f"ls_menu finished in {elapsed:.2f}s")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    await query.answer()

    if query.data == 'm_video':
        USER_STATES[chat_id] = "mode_video"
        await query.edit_message_text("🎬 **MODE VIDEO AI**\nKetik topik konten Tuan!\n\n_Proses bisa memakan waktu 1-2 menit._")
    elif query.data == 'm_image':
        USER_STATES[chat_id] = "mode_image"
        await query.edit_message_text("🎨 **MODE GAMBAR AI**\nKetik deskripsi gambar Tuan!")
    elif query.data == 'm_dl':
        USER_STATES[chat_id] = "mode_dl"
        await query.edit_message_text("📥 **MODE DOWNLOADER**\nKirim link video!")
    elif query.data == 'm_info':
        await query.edit_message_text("📄 **OFERTA**\n[Baca Penawaran](https://telegra.ph/PUBLICHNAYA-OFERTA-12-25-6)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data='m_back')]]), parse_mode=ParseMode.MARKDOWN)
    elif query.data == 'm_admin':
        await query.edit_message_text("👨‍💻 **ADMIN**: @ConnectAdv_bot", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data='m_back')]]))
    elif query.data == 'm_check':
        await query.edit_message_text(f"🛰️ **STATUS:** `{ACTIVE_PROCESS.get(chat_id, 'Idle')}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data='m_back')]]))
    elif query.data == 'm_back':
        await ls_menu(update, context)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    chat_id = update.effective_chat.id
    state = USER_STATES.get(chat_id)

    if state == "mode_image":
        ACTIVE_PROCESS[chat_id] = "Generating Image..."
        status_msg = await update.message.reply_text("🎨 **Sedang melukis...**")
        await progress.start("Mempersiapkan...")
        try:
            img_path = await generate_image(chat_id, user_input)
            await progress.stop()
            if img_path and os.path.exists(img_path):
                await update.message.reply_photo(photo=open(img_path, 'rb'), caption=f"✅ **Gambar berhasil dibuat!**")
                os.remove(img_path)
            else:
                await update.message.reply_text("❌ **Gagal membuat gambar.**\nCoba deskripsi lain atau ulangi nanti.")
        except Exception as e:
            logging.error(f"Error in image generation: {e}")
            await update.message.reply_text("❌ **Terjadi kesalahan server.**")
        finally:
            await progress.stop()
            await status_msg.delete()
            ACTIVE_PROCESS[chat_id] = "Idle"
            USER_STATES[chat_id] = None

    elif state == "mode_video":
        ACTIVE_PROCESS[chat_id] = "Error"
        status_msg = await update.message.reply_text("🎬 **Memproses video AI...**")
        await progress.start("Memeriksa ketersediaan model...")
        await asyncio.sleep(1)
        await progress.stop()
        await status_msg.edit_text("❌ **Fitur Video AI sedang dalam pengembangan.**\nModel yang digunakan tidak menyediakan API gratis. Silakan gunakan **Gambar AI** atau **Downloader**.")
        await status_msg.delete()
        ACTIVE_PROCESS[chat_id] = "Idle"
        USER_STATES[chat_id] = None

    elif state == "mode_dl" or ("http" in user_input and len(user_input) > 10):
        ACTIVE_PROCESS[chat_id] = "Downloading..."
        status_msg = await update.message.reply_text("📥 **Mengeksekusi Download...**")
        await progress.start("Memulai download...")
        video_file = os.path.join(WORK_DIR, f"out_{chat_id}.mp4")
        success, info = await run_safe_download_async(user_input, video_file, progress)
        await progress.stop()
        if success:
            try:
                await update.message.reply_video(video=open(video_file, 'rb'), caption=f"✅ **Berhasil diunduh!**")
            except Exception as e:
                await update.message.reply_text(f"✅ **Berhasil diunduh, tapi gagal dikirim:** {e}")
            finally:
                if os.path.exists(video_file):
                    os.remove(video_file)
        else:
            await update.message.reply_text(f"❌ **Gagal mendownload.**\n{info}")
        await status_msg.delete()
        ACTIVE_PROCESS[chat_id] = "Idle"
        USER_STATES[chat_id] = None

    else:
        await ls_menu(update, context)

def main():
    request = HTTPXRequest(read_timeout=30, write_timeout=30, connect_timeout=30)
    app = Application.builder().token(TOKEN).request(request).build()
    app.add_handler(CommandHandler(["start", "ls"], ls_menu))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    os.system('clear')
    print("OXYX V109.1 ONLINE - CLEAN CONSOLE ACTIVE")
    print("✅ Gambar AI aktif | ❌ Video AI nonaktif (model tidak punya API)")
    print("🔄 Terminal progress bar akan muncul saat proses berjalan.")
    app.run_polling()

if __name__ == "__main__":
    main()
