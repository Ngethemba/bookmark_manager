import os
import subprocess
import sys
import re
import json
from pathlib import Path
import io

# Unbuffered output - critical for .exe double-click execution
if not os.environ.get('PYTHONUNBUFFERED'):
    os.environ['PYTHONUNBUFFERED'] = '1'
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)


def resolve_project_dir():
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "instagram_bot.py").exists():
            return exe_dir
        if (exe_dir.parent / "instagram_bot.py").exists():
            return exe_dir.parent
        return exe_dir
    return Path(__file__).resolve().parent


def resolve_python_exe(base_dir):
    venv_python = base_dir / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return venv_python

    if getattr(sys, "frozen", False):
        return Path("py")

    return Path(sys.executable)


def ensure_runtime(python_exe):
    # Ensure bot dependencies and browser binary are available.
    subprocess.run([str(python_exe), "-m", "pip", "install", "playwright"], check=False)
    subprocess.run([str(python_exe), "-m", "playwright", "install", "chromium"], check=False)


def accounts_file_path(base_dir):
    return base_dir / "instagram_accounts.json"


def default_accounts_data():
    return {
        "selected": "default",
        "accounts": [
            {
                "id": "default",
                "name": "Varsayilan Hesap",
                "profile": "default",
            }
        ],
    }


def load_accounts(base_dir):
    path = accounts_file_path(base_dir)
    if not path.exists():
        data = default_accounts_data()
        save_accounts(base_dir, data)
        return data

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "accounts" not in data or not data["accounts"]:
            return default_accounts_data()
        if not data.get("selected"):
            data["selected"] = data["accounts"][0]["id"]
        return data
    except Exception:
        return default_accounts_data()


def save_accounts(base_dir, data):
    path = accounts_file_path(base_dir)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def slugify(value):
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip().lower())
    return slug.strip("-._") or "hesap"


def get_selected_account(data):
    selected_id = data.get("selected")
    for account in data.get("accounts", []):
        if account.get("id") == selected_id:
            return account
    return data.get("accounts", [None])[0]


def print_accounts(data):
    selected_id = data.get("selected")
    print("\nMevcut hesaplar:")
    for idx, account in enumerate(data.get("accounts", []), start=1):
        marker = "*" if account.get("id") == selected_id else " "
        print(f"  {idx}. [{marker}] {account.get('name')} (profil: {account.get('profile')})")


def choose_or_add_account(base_dir, data):
    while True:
        print_accounts(data)
        print("\nSecenekler:")
        print("  [numara] Hesap sec")
        print("  a        Yeni hesap ekle")
        print("  q        Cikis")
        
        try:
            choice = input("Seciminiz: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            # Non-interactive terminal (orn: .exe double-click)
            # Secilen hesabi kullan
            selected = get_selected_account(data)
            if selected:
                print(f"\n[OTOMATIK] Secili hesap: {selected['name']}")
                return selected, data
            # Yoksa varsayilani kullan
            return data.get("accounts", [None])[0], data

        if choice == "q":
            return None, data

        if choice == "a":
            try:
                name = input("Yeni hesap adi: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("Hesap ekleme non-interactive ortamda desteklenmiyor.")
                return get_selected_account(data), data
            
            if not name:
                print("Hesap adi bos olamaz.")
                continue

            new_id = slugify(name)
            existing_ids = {a["id"] for a in data.get("accounts", [])}
            base_id = new_id
            suffix = 2
            while new_id in existing_ids:
                new_id = f"{base_id}-{suffix}"
                suffix += 1

            account = {"id": new_id, "name": name, "profile": new_id}
            data.setdefault("accounts", []).append(account)
            data["selected"] = new_id
            save_accounts(base_dir, data)
            print(f"Hesap eklendi ve secildi: {name}")
            return account, data

        if choice.isdigit():
            index = int(choice) - 1
            accounts = data.get("accounts", [])
            if 0 <= index < len(accounts):
                selected = accounts[index]
                data["selected"] = selected["id"]
                save_accounts(base_dir, data)
                return selected, data

        print("Gecersiz secim, tekrar deneyin.")


def run_setup_login(python_exe, profile):
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    subprocess.run(
        [str(python_exe), "instagram_bot.py", "--setup-account", profile],
        env=env,
        check=False,
    )


def run():
    base_dir = resolve_project_dir()
    os.chdir(base_dir)
    python_exe = resolve_python_exe(base_dir)
    
    # Log dosyası oluştur
    log_file = base_dir / "dm_launcher.log"
    log_handle = open(log_file, 'a', encoding='utf-8')
    
    def log_print(*args, **kwargs):
        """Hem ekrana hem de log dosyasına yazdır"""
        print(*args, **kwargs)
        print(*args, **kwargs, file=log_handle)
        log_handle.flush()
    
    log_print("\n" + "="*50)
    log_print("DM LAUNCHER BAŞLATILDI")
    log_print("="*50)

    if str(python_exe).lower() == "py":
        log_print("⚠ Uyari: .venv bulunamadi. Lutfen once uygulamayi normal baslatin.")

    log_print(f"Python: {python_exe}")
    log_print(f"Project: {base_dir}")

    ensure_runtime(python_exe)

    data = load_accounts(base_dir)
    account, data = choose_or_add_account(base_dir, data)
    if account is None:
        log_print("❌ İşlem iptal edildi.")
        log_handle.close()
        return

    log_print(f"\n✓ Secili hesap: {account['name']} (profil: {account['profile']})")

    try:
        setup_choice = input("Bu hesap icin giris ekranini simdi ac? (e/h): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        setup_choice = "h"  # Non-interactive: Dont open login screen

    try:
        threads = input("Kac DM konusmasi taransin? (varsayilan 10): ").strip() or "10"
    except (EOFError, KeyboardInterrupt):
        threads = "10"  # Non-interactive: Use default

    if setup_choice == "e":
        log_print("\n📱 Giris penceresi aciliyor...")
        run_setup_login(python_exe, account["profile"])

    log_print(f"\n🔍 DM konusmalarini taramaya basliyor... ({threads} konu)")
    log_print("=" * 50)
    
    # Bot'u çalıştır ve output'u direkt göster (capture etme, buffering sorunu)
    # UTF-8 encoding'i zorunlu kıl (Windows console encoding sorunu için)
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUNBUFFERED'] = '1'
    
    result = subprocess.run(
        [str(python_exe), "instagram_bot.py", "--scan-dm", threads, "--profile", account["profile"]],
        env=env
    )
    
    log_print("\n" + "=" * 50)
    if result.returncode == 0:
        log_print("✅ Bot işlemi başarılı tamamlandı!")
    else:
        log_print(f"⚠ Bot işlemi hata ile sonlandı (kod: {result.returncode})")
    
    log_print("=" * 50)
    log_print(f"\n📋 Loglar kaydedildi: {log_file}")
    log_print("\nExit için Enter tuşuna basın...")
    log_handle.close()
    
    try:
        input()
    except EOFError:
        pass


if __name__ == "__main__":
    run()
