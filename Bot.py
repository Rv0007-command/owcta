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
