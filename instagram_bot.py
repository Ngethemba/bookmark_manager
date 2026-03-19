"""
Instagram Kaydedilen Gönderi Kaldırma Botu
Playwright kullanarak seçili gönderileri Instagram'dan kaldırır
"""

import asyncio
import random
import json
import sys
import re
import io
from pathlib import Path

# UTF-8 encoding'i güç içine sok - Windows console sorunlarını çöz
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("Playwright yüklü değil. Yükleniyor...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


class InstagramBot:
    def __init__(self, headless=False, profile_name='default'):
        self.headless = headless
        self.profile_name = profile_name or 'default'
        self.browser = None
        self.context = None
        self.page = None
        self.is_logged_in = False
        self.removed_count = 0
        self.failed_urls = []
        
    async def start(self):
        """Tarayıcıyı başlat - Gerçek Chrome profili kullan"""
        import os
        
        self.playwright = await async_playwright().start()
        
        # Persistent context kullan (oturum bilgilerini saklar)
        base_dir = os.path.dirname(__file__)
        legacy_profile_path = os.path.join(base_dir, 'browser_profile')
        profiles_root = os.path.join(base_dir, 'browser_profiles')
        os.makedirs(profiles_root, exist_ok=True)

        safe_profile_name = re.sub(r'[^A-Za-z0-9._-]', '_', self.profile_name).strip('._-') or 'default'
        if safe_profile_name == 'default' and os.path.exists(legacy_profile_path):
            profile_path = legacy_profile_path
        else:
            profile_path = os.path.join(profiles_root, safe_profile_name)
        
        print("="*50)
        print("TARAYICI BAŞLATILIYOR")
        print("="*50)
        print(f"Profil: {safe_profile_name}")

        launch_kwargs = dict(
            headless=self.headless,
            slow_mo=100,
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            locale='tr-TR',
            timezone_id='Europe/Istanbul',
            geolocation={'latitude': 41.0082, 'longitude': 28.9784},
            permissions=['geolocation'],
            color_scheme='light',
            # Bot algılamayı atlatma ayarları
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process'
            ],
            ignore_default_args=['--enable-automation'],
        )
        
        # Stealth ayarları ile başlat
        current_profile_path = profile_path
        try:
            self.context = await self.playwright.chromium.launch_persistent_context(
                profile_path,
                **launch_kwargs,
            )
        except Exception as e:
            fallback_profile_path = os.path.join(profiles_root, f'{safe_profile_name}_fallback')
            print(f"⚠ Ana profil açılamadı ({str(e)[:80]})")
            print(f"↪ Yedek profil ile yeniden deneniyor: {fallback_profile_path}")
            current_profile_path = fallback_profile_path
            self.context = await self.playwright.chromium.launch_persistent_context(
                fallback_profile_path,
                **launch_kwargs,
            )
        
        # JavaScript ile bot işaretlerini gizle
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        
        await self.page.add_init_script("""
            // webdriver flag'ini gizle
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Chrome runtime'ı ekle
            window.chrome = {
                runtime: {}
            };
            
            // Plugins'i gerçekçi yap
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['tr-TR', 'tr', 'en-US', 'en']
            });
        """)
        
        print("✓ Tarayıcı başlatıldı (Stealth mod)")
        print("✓ Profil kaydedilecek: " + current_profile_path)

    async def setup_account_session(self):
        """Yeni hesap/profil için login oturumu başlat ve kaydet."""
        await self.start()
        if not await self.login():
            print("✗ Hesap kurulumu başarısız.")
            return False

        print("✓ Hesap giriş bilgileri profile kaydedildi.")
        print("Tarayıcı 5 saniye sonra kapanacak...")
        await asyncio.sleep(5)
        return True
        
    async def close(self):
        """Tarayıcıyı kapat"""
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        print("✓ Tarayıcı kapatıldı")
    
    async def random_delay(self, min_sec=2, max_sec=5):
        """İnsan gibi rastgele bekleme"""
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)

    async def _wait_for_manual_login(self, max_wait_sec=300, check_interval=5):
        """Etkileşimsiz ortamlarda login tamamlanana kadar bekle."""
        waited = 0
        while waited < max_wait_sec:
            try:
                url = self.page.url.lower()
                if 'instagram.com' in url and 'login' not in url and 'challenge' not in url:
                    return True

                # Bazı durumlarda URL değişmeden navbar görünebilir.
                nav = await self.page.query_selector('nav, [role="navigation"]')
                if nav:
                    return True
            except Exception:
                pass

            await asyncio.sleep(check_interval)
            waited += check_interval

        return False
    
    async def login(self):
        """Instagram'a giriş yap (manuel)"""
        print("\n" + "="*50)
        print("INSTAGRAM GİRİŞİ")
        print("="*50)
        
        await self.page.goto('https://www.instagram.com/accounts/login/')
        await self.random_delay(3, 5)
        
        # Çerez popup'ını kapat (varsa)
        try:
            cookie_btn = await self.page.wait_for_selector(
                'button:has-text("Tümüne izin ver"), button:has-text("Allow all"), button:has-text("Kabul Et"), button:has-text("Allow essential")',
                timeout=5000
            )
            if cookie_btn:
                await cookie_btn.click()
                await self.random_delay(1, 2)
        except:
            pass
        
        print("\n⚠️  MANUEL GİRİŞ GEREKLİ!")
        print("="*50)
        print("1. Açılan tarayıcıda Instagram'a giriş yapın")
        print("2. İki faktörlü doğrulama (2FA) varsa kodu girin")
        print("3. 'Bilgileri Kaydet' çıkarsa 'Şimdi Değil' seçin")
        print("4. 'Bildirimleri Aç' çıkarsa 'Şimdi Değil' seçin")
        print("5. Ana sayfa veya profil sayfası görününce ENTER'a basın")
        print("="*50)
        print("\n💡 İPUCU: Beyaz ekranda takılırsanız:")
        print("   - Sayfayı yenileyin (F5)")
        print("   - Veya adres çubuğuna instagram.com yazıp gidin")
        print("-"*50)

        if sys.stdin and sys.stdin.isatty():
            input("\n[Giriş yaptıktan sonra ENTER'a basın...]")
        else:
            print("\n[ENTER yerine otomatik bekleme aktif: giriş için 300sn beklenecek]")
            if not await self._wait_for_manual_login(max_wait_sec=300, check_interval=5):
                print("✗ Giriş zaman aşımı.")
                return False
        
        # Sayfa boşsa yenile
        try:
            content = await self.page.content()
            if len(content) < 1000 or 'html' not in content.lower():
                print("Sayfa yüklenmemiş, yenileniyor...")
                await self.page.goto('https://www.instagram.com/')
                await self.random_delay(3, 5)
        except:
            pass
        
        # Ana sayfaya git
        await self.page.goto('https://www.instagram.com/')
        await self.random_delay(3, 5)
        
        # Tekrar popup'ları kapat
        await self.close_popups()
        
        # Giriş kontrolü - birden fazla yöntem dene
        login_success = False
        
        # Yöntem 1: Nav elementlerini kontrol et
        try:
            nav = await self.page.wait_for_selector('nav, [role="navigation"]', timeout=5000)
            if nav:
                login_success = True
        except:
            pass
        
        # Yöntem 2: URL kontrolü
        if not login_success:
            current_url = self.page.url
            if 'instagram.com' in current_url and 'login' not in current_url and 'challenge' not in current_url:
                login_success = True
        
        # Yöntem 3: Sayfa içeriği kontrolü
        if not login_success:
            try:
                content = await self.page.content()
                if 'Direct' in content or 'Keşfet' in content or 'Explore' in content or 'Home' in content:
                    login_success = True
            except:
                pass
        
        if login_success:
            self.is_logged_in = True
            print("✓ Giriş başarılı!")
            return True
        else:
            print("✗ Giriş yapılmamış görünüyor.")
            print("  Tarayıcıda giriş tamamlandıktan sonra tekrar denenecek...")
            retry_ok = await self._wait_for_manual_login(max_wait_sec=120, check_interval=5)
            if retry_ok:
                self.is_logged_in = True
                print("✓ Giriş başarılı (gecikmeli doğrulama)")
                return True
            return False
    
    async def close_popups(self):
        """Instagram popup'larını kapat"""
        popups = [
            'button:has-text("Şimdi Değil")',
            'button:has-text("Not Now")',
            'button:has-text("Hayır")',
            'button:has-text("No")',
            'button:has-text("Cancel")',
            'button:has-text("İptal")',
            '[aria-label="Close"], [aria-label="Kapat"]'
        ]
        
        for selector in popups:
            try:
                btn = await self.page.wait_for_selector(selector, timeout=2000)
                if btn:
                    await btn.click()
                    await self.random_delay(0.5, 1)
            except:
                pass

    def _is_valid_username(self, username):
        """Instagram kullanıcı adı formatını doğrula"""
        if not username:
            return False
        return bool(re.fullmatch(r'[A-Za-z0-9._]{1,30}', username))

    async def resolve_username_from_instagram_url(self, url):
        """Instagram URL'sinden kullanıcı adını çıkar. Post/Reels linklerinde sayfadan çöz."""
        if not url:
            return None

        match = re.search(r'https?://(?:www\.)?instagram\.com/([^/?#]+)/?', url)
        if not match:
            return None

        first_segment = match.group(1).strip().lower()
        media_segments = {'p', 'reel', 'reels', 'tv'}

        if first_segment in media_segments:
            return await self.resolve_username_from_media_url(url)

        if self._is_valid_username(first_segment):
            return first_segment

        return None

    async def resolve_username_from_media_url(self, media_url):
        """Post/Reels URL'sini açıp paylaşım sahibini bul."""
        try:
            await self.page.goto(media_url)
            await self.random_delay(2, 4)

            owner_link = await self.page.query_selector('header a[href^="/"]')
            if owner_link:
                href = await owner_link.get_attribute('href')
                if href:
                    candidate = href.strip('/').split('/')[0].lower()
                    if self._is_valid_username(candidate):
                        return candidate
        except Exception as e:
            print(f"  ⚠ Medya linkinden kullanıcı çözülemedi: {str(e)[:60]}")

        return None

    async def get_recent_thread_links(self, max_threads=10):
        """DM kutusundaki son konuşma linklerini topla."""
        print("[DM] Inbox aciliyor...")
        await self.page.goto('https://www.instagram.com/direct/inbox/')
        
        # KRITIK: Instagram dinamik JavaScript yümüklüyor - uzun bekle
        # User testi: İlk 6-9 saniyede linkler yoktu, 10+ sonra çıktı
        await self.random_delay(12, 15)
        await self.close_popups()
        await self.random_delay(2, 3)
        
        print("[DM] Thread linkler aranıyor...")
        
        try:
            # Tüm <a> tag'larında /direct/t/ olan linkler al
            # # sonrası normalizasyon: /direct/t/123# → /direct/t/123
            thread_links = await self.page.evaluate("""
                () => {
                    const links = [];
                    document.querySelectorAll('a').forEach(a => {
                        const href = a.getAttribute('href') || '';
                        if (href.includes('/direct/t/')) {
                            const clean = href.split('#')[0];
                            if (clean && !links.includes(clean)) {
                                links.push(clean);
                            }
                        }
                    });
                    return links;
                }
            """)
            
            if thread_links and len(thread_links) > 0:
                print(f"[DM] {len(thread_links)} thread bulundu!")
                return thread_links[:max_threads]
        
        except Exception as e:
            print(f"[DM] Hata: {str(e)[:60]}")
            pass
        
        print("[DM] Thread bulunamadı - Retry yapılıyor...")
        await self.page.reload()
        await self.random_delay(5, 8)
        
        try:
            threads_retry = await self.page.evaluate("""
                () => {
                    return [...new Set(
                        [...document.querySelectorAll('a')]
                            .map(a => a.href)
                            .filter(h => h && h.includes('/direct/t/'))
                            .map(h => h.split('#')[0])
                    )];
                }
            """)
            if threads_retry:
                print(f"[DM] Retry sonrası {len(threads_retry)} thread bulundu")
                return threads_retry[:max_threads]
        except:
            pass
        
        print("[DM] SORUN: Thread link bulunamadı!")
        print("[DM] Çözüm: DM inbox'ta en az 1 konuşmanın olması gerekiyor")
        return []

    async def get_latest_message_payload(self):
        """Açık konuşmadaki en son mesajın metin ve linklerini al."""
        try:
            await self.page.wait_for_selector('div[role="row"]', timeout=10000)
        except PlaywrightTimeout:
            return {'text': '', 'links': []}

        payload = await self.page.evaluate("""
            () => {
                const rows = [...document.querySelectorAll('div[role="row"]')];
                const candidates = rows
                    .map((row) => {
                        const text = (row.innerText || '').trim();
                        const links = [...row.querySelectorAll('a[href]')]
                            .map(a => a.href)
                            .filter(Boolean)
                            .filter(href => href.includes('instagram.com'));
                        return { text, links };
                    })
                    .filter(item => item.text.length > 0 || item.links.length > 0);

                if (!candidates.length) {
                    return { text: '', links: [] };
                }

                return candidates[candidates.length - 1];
            }
        """)

        return payload or {'text': '', 'links': []}

    async def extract_username_from_message(self, message_text, links):
        """Mesaj metni ve linklerden kullanıcı adını bul."""
        links = links or []

        for link in links:
            username = await self.resolve_username_from_instagram_url(link)
            if username:
                return username

        if message_text:
            mention_match = re.search(r'@([A-Za-z0-9._]{1,30})', message_text)
            if mention_match:
                candidate = mention_match.group(1).lower()
                if self._is_valid_username(candidate):
                    return candidate

            # Düz yazılmış kullanıcı adı olasılığı için basit desen
            plain_match = re.search(r'\b([A-Za-z0-9._]{3,30})\b', message_text)
            if plain_match:
                candidate = plain_match.group(1).lower()
                if self._is_valid_username(candidate):
                    return candidate

        return None

    async def ensure_following(self, username):
        """Hesap takip edilmiyorsa takip et."""
        profile_url = f'https://www.instagram.com/{username}/'
        print(f"  → Profil kontrolü: @{username}")

        try:
            await self.page.goto(profile_url)
            await self.random_delay(2, 4)
            await self.close_popups()

            already_following_selectors = [
                'button:has-text("Takiptesin")',
                'button:has-text("Following")',
                'button:has-text("Requested")',
                'button:has-text("İstek Gönderildi")'
            ]
            for selector in already_following_selectors:
                try:
                    btn = await self.page.wait_for_selector(selector, timeout=1500)
                    if btn:
                        print("  ✓ Hesap zaten takip ediliyor veya istek beklemede")
                        return 'already_following'
                except:
                    pass

            follow_selectors = [
                'button:has-text("Takip Et")',
                'button:has-text("Follow")'
            ]
            for selector in follow_selectors:
                try:
                    btn = await self.page.wait_for_selector(selector, timeout=2500)
                    if btn:
                        await btn.click()
                        await self.random_delay(1.5, 2.5)
                        print("  ✓ Hesap takip edildi")
                        return 'followed'
                except:
                    pass

            print("  ⚠ Takip durumu net tespit edilemedi")
            return 'unknown'
        except Exception as e:
            print(f"  ✗ Takip kontrol hatası: {str(e)[:70]}")
            return 'error'

    async def leave_heart_on_current_thread(self):
        """Açık DM konuşmasında son mesaja kalp bırak."""
        # Öncelik: son mesaja çift tık ile reaksiyon dene
        try:
            rows = await self.page.query_selector_all('div[role="row"]')
            for row in reversed(rows):
                text = (await row.inner_text()).strip()
                if text:
                    await row.dblclick(timeout=2000)
                    await self.random_delay(0.8, 1.2)
                    print("  ✓ Son mesaja kalp reaksiyonu bırakıldı")
                    return True
        except Exception:
            pass

        # Fallback: DM kutusuna kalp gönder
        input_selectors = [
            'textarea[placeholder*="Mesaj"]',
            'textarea[placeholder*="Message"]',
            'div[role="textbox"]'
        ]
        for selector in input_selectors:
            try:
                msg_box = await self.page.wait_for_selector(selector, timeout=2500)
                if msg_box:
                    await msg_box.click()
                    await msg_box.fill('❤️')
                    await msg_box.press('Enter')
                    await self.random_delay(0.8, 1.2)
                    print("  ✓ Mesaja kalp gönderildi")
                    return True
            except Exception:
                continue

        print("  ✗ Kalp bırakma başarısız")
        return False

    async def process_direct_messages_for_follow(self, max_threads=10):
        """DM konuşmalarını tarayıp hesapları takip et ve kalp bırak."""
        print(f"\n{'='*50}")
        print("DM TAKİP VE KALP İŞLEMİ BAŞLIYOR")
        print(f"Taranacak konuşma: {max_threads}")
        print(f"{'='*50}")

        thread_links = await self.get_recent_thread_links(max_threads=max_threads)
        if not thread_links:
            print("⚠ İşlenecek DM konuşması bulunamadı.")
            return {'processed': 0, 'followed': 0, 'already': 0, 'hearted': 0, 'skipped': 0, 'details': []}

        results = {
            'processed': 0,
            'followed': 0,
            'already': 0,
            'hearted': 0,
            'skipped': 0,
            'details': []
        }

        for i, thread_href in enumerate(thread_links, 1):
            thread_url = f'https://www.instagram.com{thread_href}' if thread_href.startswith('/') else thread_href
            print(f"\n[{i}/{len(thread_links)}] Konuşma işleniyor...")

            try:
                await self.page.goto(thread_url)
                await self.random_delay(2, 4)

                payload = await self.get_latest_message_payload()
                message_text = payload.get('text', '')
                message_links = payload.get('links', [])

                username = await self.extract_username_from_message(message_text, message_links)
                if not username:
                    print("  ⚠ Mesajdan hesap bilgisi çıkarılamadı")
                    results['skipped'] += 1
                    results['details'].append({
                        'thread': thread_url,
                        'status': 'skipped_no_username'
                    })
                    continue

                follow_status = await self.ensure_following(username)

                if follow_status == 'followed':
                    results['followed'] += 1
                elif follow_status == 'already_following':
                    results['already'] += 1

                # Profilden geri dönüp aynı konuşmada kalp bırak
                await self.page.goto(thread_url)
                await self.random_delay(1.5, 2.5)
                hearted = await self.leave_heart_on_current_thread()
                if hearted:
                    results['hearted'] += 1

                results['processed'] += 1
                results['details'].append({
                    'thread': thread_url,
                    'username': username,
                    'follow_status': follow_status,
                    'hearted': hearted
                })
            except Exception as e:
                print(f"  ✗ Konuşma işlenemedi: {str(e)[:70]}")
                results['skipped'] += 1
                results['details'].append({
                    'thread': thread_url,
                    'status': 'error',
                    'error': str(e)[:120]
                })

            await self.random_delay(1, 2)

        print(f"\n{'='*50}")
        print("DM İŞLEMİ TAMAMLANDI")
        print(f"İşlenen: {results['processed']}")
        print(f"Takip edildi: {results['followed']}")
        print(f"Zaten takipte: {results['already']}")
        print(f"Kalp bırakılan: {results['hearted']}")
        print(f"Atlanan: {results['skipped']}")
        print(f"{'='*50}")

        return results
    
    async def remove_saved_post(self, url):
        """Tek bir gönderiyi kaydedilenlerden kaldır"""
        try:
            print(f"\n→ Açılıyor: {url[:50]}...")
            
            # Gönderi sayfasına git
            await self.page.goto(url)
            await self.random_delay(2, 4)
            
            # Kaydet butonunu bul (dolu ikon = kaydedilmiş)
            # Instagram'da kaydet butonu SVG olarak render ediliyor
            save_button = None
            
            # Yöntem 1: aria-label ile
            try:
                save_button = await self.page.wait_for_selector(
                    'svg[aria-label="Kaldır"], svg[aria-label="Remove"], [aria-label="Kaydedilenden kaldır"]',
                    timeout=5000
                )
            except:
                pass
            
            # Yöntem 2: Kaydet butonu container'ı
            if not save_button:
                try:
                    # Tüm kaydet butonlarını bul
                    buttons = await self.page.query_selector_all('svg[aria-label*="Kaydet"], svg[aria-label*="Save"]')
                    for btn in buttons:
                        # Dolu mu kontrol et (kaydedilmiş = siyah/dolu)
                        parent = await btn.evaluate_handle('el => el.closest("button") || el.parentElement')
                        if parent:
                            save_button = parent
                            break
                except:
                    pass
            
            # Yöntem 3: Bookmark ikonu (genel arama)
            if not save_button:
                try:
                    # Sayfadaki tüm butonları tara
                    save_button = await self.page.wait_for_selector(
                        'button:has(svg[aria-label*="aydet"]), button:has(svg[aria-label*="ave"]), span[class*="save"] button',
                        timeout=5000
                    )
                except:
                    pass
            
            if save_button:
                # Butona tıkla
                await save_button.click()
                await self.random_delay(1, 2)
                
                print(f"  ✓ Kaydedilenlerden kaldırıldı")
                self.removed_count += 1
                return True
            else:
                print(f"  ⚠ Kaydet butonu bulunamadı veya zaten kaldırılmış")
                self.failed_urls.append({'url': url, 'reason': 'Buton bulunamadı'})
                return False
                
        except PlaywrightTimeout:
            print(f"  ✗ Sayfa yüklenemedi (timeout)")
            self.failed_urls.append({'url': url, 'reason': 'Timeout'})
            return False
        except Exception as e:
            print(f"  ✗ Hata: {str(e)[:50]}")
            self.failed_urls.append({'url': url, 'reason': str(e)[:100]})
            return False
    
    async def remove_multiple(self, urls, delay_between=3):
        """Birden fazla gönderiyi kaldır"""
        total = len(urls)
        print(f"\n{'='*50}")
        print(f"TOPLU KALDIRMA BAŞLIYOR")
        print(f"Toplam: {total} gönderi")
        print(f"Tahmini süre: ~{total * (delay_between + 3)} saniye")
        print(f"{'='*50}")
        
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{total}] İşleniyor...")
            
            success = await self.remove_saved_post(url)
            
            # İşlemler arası rastgele bekleme
            if i < total:
                wait_time = random.uniform(delay_between, delay_between + 3)
                print(f"  ⏳ Sonraki işlem için {wait_time:.1f}s bekleniyor...")
                await asyncio.sleep(wait_time)
            
            # Her 10 işlemde bir uzun mola (güvenlik için)
            if i % 10 == 0 and i < total:
                long_wait = random.uniform(15, 30)
                print(f"\n  🛑 Güvenlik molası: {long_wait:.0f}s bekleniyor...")
                await asyncio.sleep(long_wait)
        
        # Sonuç özeti
        print(f"\n{'='*50}")
        print("İŞLEM TAMAMLANDI")
        print(f"{'='*50}")
        print(f"✓ Başarılı: {self.removed_count}/{total}")
        print(f"✗ Başarısız: {len(self.failed_urls)}")
        
        if self.failed_urls:
            print("\nBaşarısız olanlar:")
            for item in self.failed_urls[:5]:
                print(f"  - {item['url'][:40]}... ({item['reason']})")
            if len(self.failed_urls) > 5:
                print(f"  ... ve {len(self.failed_urls) - 5} tane daha")
        
        return {
            'success': self.removed_count,
            'failed': len(self.failed_urls),
            'failed_urls': self.failed_urls
        }


async def main(urls_file=None, urls_list=None, auto_confirm=False, profile_name='default'):
    """Ana fonksiyon"""
    bot = InstagramBot(headless=False, profile_name=profile_name)  # headless=False: tarayıcıyı göster
    
    try:
        # URL'leri al
        urls = []
        if urls_file:
            with open(urls_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                urls = data if isinstance(data, list) else data.get('urls', [])
        elif urls_list:
            urls = urls_list
        else:
            print("URL listesi gerekli!")
            return
        
        if not urls:
            print("Kaldırılacak URL bulunamadı!")
            return
        
        print(f"\n📋 {len(urls)} gönderi kaldırılacak")
        print("\nÖrnek URL'ler:")
        for url in urls[:3]:
            print(f"  • {url[:60]}...")
        if len(urls) > 3:
            print(f"  ... ve {len(urls) - 3} tane daha")
        
        if not auto_confirm:
            confirm = input("\nDevam etmek istiyor musunuz? (e/h): ").lower()
            if confirm != 'e':
                print("İptal edildi.")
                return
        
        # Tarayıcıyı başlat
        await bot.start()
        
        # Giriş yap
        if not await bot.login():
            print("Giriş başarısız. Program sonlandırılıyor.")
            return
        
        # Gönderileri kaldır
        result = await bot.remove_multiple(urls)
        
        # Sonucu kaydet
        with open('removal_result.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print("\nSonuçlar 'removal_result.json' dosyasına kaydedildi.")
        
    finally:
        await bot.close()


# Flask API endpoint'i için wrapper
def run_removal(urls):
    """Senkron wrapper - Flask'tan çağrılacak"""
    return asyncio.run(main(urls_list=urls))


async def main_dm_follow(max_threads=10, profile_name='default'):
    """DM kutusunu tarayıp mesajdaki hesapları takip et, kalp bırak"""
    bot = InstagramBot(headless=False, profile_name=profile_name)

    try:
        await bot.start()

        if not await bot.login():
            print("Giriş başarısız. Program sonlandırılıyor.")
            return

        result = await bot.process_direct_messages_for_follow(max_threads=max_threads)

        with open('dm_follow_result.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print("\nSonuçlar 'dm_follow_result.json' dosyasına kaydedildi.")
    finally:
        await bot.close()


def run_dm_follower(max_threads=10, profile_name='default'):
    """Senkron wrapper - DM takip/kalp akışı"""
    return asyncio.run(main_dm_follow(max_threads=max_threads, profile_name=profile_name))


def parse_cli_args(args):
    """Komut satırı argümanlarını basit şekilde ayrıştır."""
    parsed = {
        'mode': 'help',
        'urls_file': None,
        'max_threads': 10,
        'profile_name': 'default',
        'auto_confirm': False,
    }

    if not args:
        return parsed

    if args[0] == '--scan-dm':
        parsed['mode'] = 'scan_dm'
        cursor = 1
        if cursor < len(args) and not args[cursor].startswith('--'):
            try:
                parsed['max_threads'] = int(args[cursor])
                cursor += 1
            except ValueError:
                print("Geçersiz konuşma limiti, varsayılan 10 kullanılacak.")
        while cursor < len(args):
            token = args[cursor]
            if token == '--profile' and cursor + 1 < len(args):
                parsed['profile_name'] = args[cursor + 1]
                cursor += 2
            else:
                cursor += 1
        return parsed

    if args[0] == '--setup-account':
        parsed['mode'] = 'setup_account'
        if len(args) < 2:
            raise ValueError("--setup-account için profil adı gerekli")
        parsed['profile_name'] = args[1]
        return parsed

    parsed['mode'] = 'remove_saved'
    parsed['urls_file'] = args[0]
    cursor = 1
    while cursor < len(args):
        token = args[cursor]
        if token == '--profile' and cursor + 1 < len(args):
            parsed['profile_name'] = args[cursor + 1]
            cursor += 2
        elif token == '--yes':
            parsed['auto_confirm'] = True
            cursor += 1
        else:
            cursor += 1

    return parsed


if __name__ == '__main__':
    try:
        parsed = parse_cli_args(sys.argv[1:])

        if parsed['mode'] == 'scan_dm':
            asyncio.run(main_dm_follow(
                max_threads=parsed['max_threads'],
                profile_name=parsed['profile_name']
            ))
        elif parsed['mode'] == 'setup_account':
            setup_bot = InstagramBot(headless=False, profile_name=parsed['profile_name'])
            try:
                success = asyncio.run(setup_bot.setup_account_session())
                if not success:
                    sys.exit(1)
            finally:
                try:
                    asyncio.run(setup_bot.close())
                except Exception:
                    pass
        elif parsed['mode'] == 'remove_saved':
            asyncio.run(main(
                urls_file=parsed['urls_file'],
                auto_confirm=parsed['auto_confirm'],
                profile_name=parsed['profile_name']
            ))
        else:
            print("Instagram Kaydedilen Gönderi Kaldırma Botu")
            print("-" * 40)
            print("\nKullanım:")
            print("  python instagram_bot.py urls.json --profile default")
            print("  python instagram_bot.py urls.json --profile deneme --yes")
            print("  python instagram_bot.py --scan-dm 10 --profile deneme")
            print("  python instagram_bot.py --setup-account deneme")
            print("\nveya Python'dan:")
            print("  from instagram_bot import run_removal")
            print("  run_removal(['https://instagram.com/p/xxx', ...])")
            print("\nDM takip/kalp akışı:")
            print("  from instagram_bot import run_dm_follower")
            print("  run_dm_follower(10)")
    except ValueError as e:
        print(f"Argüman hatası: {e}")
        sys.exit(1)
