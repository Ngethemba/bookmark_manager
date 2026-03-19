# Instagram Bookmark Manager & DM Bot

Playwright tabanlı Instagram otomasyon aracı. Kaydedilen gönderileri toplu olarak silme ve DM konuşmalarını takip etme/tepki verme işlevleri.

## Özellikler

- **Kaydedilen Gönderi Kaldırma**: Instagram'da kaydedilen gönderileri seçilerek toplu silme
- **DM Otomasyonu**: DM konuşmalarından hesap bulma, otomatik takip etme, kalp gönderme
- **Multi-Account**: Farklı hesaplar için ayrı browser profilleri ve oturum yönetimi
- **Web UI**: Flask-based kontrol paneli hesap yönetimi ve bot kontrolü için
- **Standalone Executables**: Python yüklü olmayan bilgisayarlarda çalışabilir (.exe launcher'lar)

## Kurulum

### Gereksinimler
- Python 3.10+
- Pip (paket yöneticisi)

### Başlama

1. Virtual environment oluştur:
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac
```

2. Bağımlılıkları yükle:
```bash
pip install -r requirements.txt
```

3. Playwright browser'ı kur:
```bash
python -m playwright install chromium
```

## Kullanım

### Web Arayüzü

Kontrol panelini başlat:
```bash
python app.py  # Tarayıcıda http://localhost:5000 açılır
```

**İşlevler:**
- Hesap seçimi ve ekleme
- Kaydedilen gönderi kaldırma
- DM konuşmaları tarama (beklemede)
- Browser giriş ayarları

### Komut Satırı

**DM Otomasyonu:**
```bash
python instagram_bot.py --scan-dm 10 --profile default
```

**Hesap Giriş Ayarları:**
```bash
python instagram_bot.py --setup-account default
```

**Kaydedilen Gönderileri Silme:**
```bash
python instagram_bot.py urls.txt --profile default --yes
```

### Standalone Launcher (.exe)

Windows'ta `.exe` dosyalarını çift-tıkla:
- `DMFollowLauncher.exe` - DM otomasyon menüsü
- `BookmarkManager.exe` - Web arayüzü

## Proje Yapısı

```
.
├── instagram_bot.py       # Ana bot engine (Playwright)
├── app.py                 # Flask web uygulaması
├── launcher_*.py          # Standalone executable launcher'ları
├── templates/
│   └── index.html        # Web UI
├── browser_profiles/     # Multi-profile browser state (Git'e dahil değil)
├── dist/                 # Derlenmiş .exe dosyaları
├── requirements.txt      # Python bağımlılıkları
└── README.md             # Bu dosya
```

## Teknik Detaylar

- **Framework**: Playwright (Chromium automation)
- **Web Backend**: Flask + SQLAlchemy
- **Database**: SQLite
- **Browser Profile**: Ayrı oturum/çerez yönetimi
- **Executable Packaging**: PyInstaller

## DM Otomasyon Akışı

1. DM inbox'una gir
2. Son N konuşmayı bul
3. Her konuşmada:
   - Son mesajdan hesap adını çıkar (@mention, URL, vb.)
   - Hesabı takip et (eğer takip edilmiyorsa)
   - Mesaja kalp reaksiyonu bırak

## Sorun Giderme

### DM konuşmaları bulunamıyor
- Instagram'ın dinamik UI'ı nedeniyle selector'lar değişebilir
- Çözüm: Tarayıcı Console'da şunu çalıştır ve sonucu ilet:
```javascript
[...document.querySelectorAll('a')].filter(a=>a.href.includes('/direct/t/')).map(a=>a.href)
```

### Giriş zaman aşımı
- Tarayıcı açılıp manuel 2FA girişi gerekebilir
- 300 saniyelik timeout süresi vardır
- Alternatif: `--setup-account` ile profile'a oturum kaydet

## Lisans

Kişisel kullanım için

## Not

Bu proje eğitim amaçlıdır. Instagram'ın Hizmet Şartlarını (ToS) kontrol edin; otomatik botlar izin verilmeyebilir.
