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
import time
from urllib.parse import urlparse, parse_qs, unquote
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

    async def _has_active_instagram_session(self):
        """Aktif Instagram oturumu var mı hızlıca kontrol et."""
        try:
            await self.page.goto('https://www.instagram.com/', wait_until='domcontentloaded')
            await self.random_delay(0.8, 1.4)

            current_url = (self.page.url or '').lower()
            if 'accounts/login' in current_url or '/challenge/' in current_url:
                return False

            nav = await self.page.query_selector('nav, [role="navigation"]')
            if nav:
                return True

            # URL login/challenge değilse ve page boş değilse çoğu durumda oturum vardır.
            content = await self.page.content()
            return bool(content and len(content) > 1200 and 'login' not in current_url)
        except Exception:
            return False
    
    async def login(self):
        """Instagram'a giriş yap (manuel)"""
        print("\n" + "="*50)
        print("INSTAGRAM GİRİŞİ")
        print("="*50)

        if await self._has_active_instagram_session():
            self.is_logged_in = True
            print("✓ Oturum zaten açık, manuel giriş adımı atlandı")
            await self.close_popups()
            return True
        
        await self.page.goto('https://www.instagram.com/accounts/login/')
        await self.random_delay(3, 5)

        # Login URL'sine gitsek bile Instagram bazen aktif oturumu direkt anasayfaya taşır.
        if await self._has_active_instagram_session():
            self.is_logged_in = True
            print("✓ Oturum aktif algılandı, ENTER beklenmeden devam ediliyor")
            await self.close_popups()
            return True
        
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

    def _is_reserved_instagram_segment(self, segment):
        """Kullanıcı adı olmayan bilinen Instagram path segmentleri."""
        reserved = {
            'direct', 'accounts', 'explore', 'reels', 'reel', 'p', 'tv',
            'stories', 'notifications', 'about', 'legal', 'challenge',
            'login', 'api', 'graphql', 'developer', 'web'
        }
        return (segment or '').lower() in reserved

    def _normalize_thread_href(self, href):
        """DM thread href'ini normalize et."""
        if not href:
            return None

        cleaned = href.strip().split('#')[0].split('?')[0]
        if not cleaned:
            return None

        if cleaned.startswith('http://') or cleaned.startswith('https://'):
            match = re.search(r'https?://(?:www\.)?instagram\.com(/direct/t/[^/?#]+/?)', cleaned)
            if not match:
                return None
            cleaned = match.group(1)

        if not cleaned.startswith('/direct/t/'):
            return None

        parts = cleaned.strip('/').split('/')
        if len(parts) < 3 or not parts[2]:
            return None

        return f"/direct/t/{parts[2]}/"

    async def _collect_thread_links_from_dom(self):
        """Sayfadaki DM konuşma linklerini topla ve normalize et."""
        raw_links = await self.page.evaluate("""
            () => {
                const links = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    if (href.includes('/direct/t/')) {
                        links.push(href);
                    }
                });
                return links;
            }
        """)

        unique = []
        for href in raw_links or []:
            normalized = self._normalize_thread_href(href)
            if normalized and normalized not in unique:
                unique.append(normalized)

        return unique

    async def _collect_thread_links_from_api(self):
        """Instagram inbox API'den thread id çekip link üret (DOM fallback)."""
        data = await self.page.evaluate("""
            async () => {
                try {
                    const cookie = document.cookie || '';
                    const csrfMatch = cookie.match(/(?:^|;\\s*)csrftoken=([^;]+)/i);
                    const csrf = csrfMatch ? decodeURIComponent(csrfMatch[1]) : '';

                    const response = await fetch('/api/v1/direct_v2/inbox/?persistentBadging=true&limit=30', {
                        credentials: 'include',
                        headers: {
                            'x-requested-with': 'XMLHttpRequest',
                            'x-csrftoken': csrf,
                            'x-ig-app-id': '936619743392459'
                        }
                    });

                    if (!response.ok) {
                        let body = '';
                        try {
                            body = (await response.text() || '').slice(0, 200);
                        } catch (e) {
                            body = String(e || '');
                        }
                        return { ok: false, status: response.status, body, links: [] };
                    }

                    const json = await response.json();
                    const threads = (json && json.inbox && Array.isArray(json.inbox.threads)) ? json.inbox.threads : [];
                    const links = [];

                    for (const t of threads) {
                        const id = (t && t.thread_id) ? String(t.thread_id).trim() : '';
                        if (id) {
                            links.push(`/direct/t/${id}/`);
                        }
                    }

                    return { ok: true, status: 200, links };
                } catch (err) {
                    return { ok: false, status: -1, error: String(err || ''), links: [] };
                }
            }
        """)

        links = []
        for href in (data or {}).get('links', []):
            normalized = self._normalize_thread_href(href)
            if normalized and normalized not in links:
                links.append(normalized)

        return {
            'ok': bool((data or {}).get('ok')),
            'status': (data or {}).get('status'),
            'links': links,
            'error': (data or {}).get('error', ''),
            'body': (data or {}).get('body', '')
        }

    def _extract_thread_links_from_html(self, html):
        """HTML içeriğinde gömülü kalan /direct/t/ linklerini regex ile yakala."""
        if not html:
            return []

        matches = re.findall(r'/direct/t/\d+/?', html)
        links = []
        for href in matches:
            normalized = self._normalize_thread_href(href)
            if normalized and normalized not in links:
                links.append(normalized)
        return links

    def _extract_thread_id_from_url(self, thread_url):
        """Thread URL'sinden thread_id çıkar."""
        if not thread_url:
            return None
        match = re.search(r'/direct/t/(\d+)/?', thread_url)
        return match.group(1) if match else None

    async def find_target_from_thread_api(self, thread_url, excluded_usernames=None):
        """Thread API'den karşı tarafın paylaştığı içerik sahibini bul.

        Tüm paylaşımları kontrol et ve geçerli hedeflerin tamamını liste olarak döndür.
        Yalnızca partner tarafından gönderilen item'lar dikkate alınır.
        """
        excluded_usernames = {u.lower() for u in (excluded_usernames or set()) if u}
        thread_id = self._extract_thread_id_from_url(thread_url)
        if not thread_id:
            return []

        data = await self.page.evaluate(
            """
            async (threadId) => {
                const out = {
                    ok: false,
                    status: -1,
                    candidates: [],
                    reason: '',
                    item_types: [],
                    partner_item_count: 0
                };

                try {
                    const cookie = document.cookie || '';
                    const csrfMatch = cookie.match(/(?:^|;\\s*)csrftoken=([^;]+)/i);
                    const csrf = csrfMatch ? decodeURIComponent(csrfMatch[1]) : '';

                    const response = await fetch(`/api/v1/direct_v2/threads/${threadId}/?limit=100`, {
                        credentials: 'include',
                        headers: {
                            'x-requested-with': 'XMLHttpRequest',
                            'x-csrftoken': csrf,
                            'x-ig-app-id': '936619743392459'
                        }
                    });

                    out.status = response.status;
                    if (!response.ok) {
                        out.reason = (await response.text()).slice(0, 200);
                        return out;
                    }

                    const json = await response.json();
                    out.ok = true;

                    const thread = (json && json.thread) ? json.thread : null;
                    if (!thread) {
                        out.reason = 'thread_missing';
                        return out;
                    }
                    const graphqlThreadId = String(thread.thread_id || thread.pk || '').trim();

                    const partnerIds = new Set((thread.users || []).map(u => String(u.pk)));
                    const items = Array.isArray(thread.items) ? thread.items : [];

                    const getByPath = (obj, path) => {
                        let cur = obj;
                        for (const p of path) {
                            if (!cur || typeof cur !== 'object' || !(p in cur)) return null;
                            cur = cur[p];
                        }
                        return cur;
                    };

                    const findNestedUsername = (obj, depth = 0) => {
                        if (!obj || typeof obj !== 'object' || depth > 4) return null;

                        if (typeof obj.username === 'string' && obj.username.trim()) {
                            return obj.username.trim();
                        }

                        for (const key of Object.keys(obj)) {
                            const val = obj[key];
                            if (val && typeof val === 'object') {
                                const found = findNestedUsername(val, depth + 1);
                                if (found) return found;
                            }
                        }
                        return null;
                    };

                    for (const item of items) {
                        const senderId = String(item && item.user_id ? item.user_id : '');
                        if (!partnerIds.has(senderId)) {
                            continue;
                        }

                        out.partner_item_count += 1;
                        if (item && item.item_type && !out.item_types.includes(String(item.item_type))) {
                            out.item_types.push(String(item.item_type));
                        }

                        const text = (item && item.text) ? String(item.text) : '';
                        const links = [];

                        let candidate = null;
                        if (item && item.media_share && item.media_share.user && item.media_share.user.username) {
                            candidate = item.media_share.user.username;
                        } else if (item && item.clip && item.clip.user && item.clip.user.username) {
                            candidate = item.clip.user.username;
                        } else if (item && item.reel_share && item.reel_share.media && item.reel_share.media.user && item.reel_share.media.user.username) {
                            candidate = item.reel_share.media.user.username;
                        } else if (item && item.profile && item.profile.username) {
                            candidate = item.profile.username;
                        } else if (item && item.media && item.media.user && item.media.user.username) {
                            candidate = item.media.user.username;
                        } else if (item && item.story_share && item.story_share.media && item.story_share.media.user && item.story_share.media.user.username) {
                            candidate = item.story_share.media.user.username;
                        } else if (item && item.felix_share && item.felix_share.media && item.felix_share.media.user && item.felix_share.media.user.username) {
                            candidate = item.felix_share.media.user.username;
                        } else if (item && item.xma_media_share && item.xma_media_share.target && item.xma_media_share.target.user && item.xma_media_share.target.user.username) {
                            candidate = item.xma_media_share.target.user.username;
                        }

                        if (item && item.link && item.link.link_context && item.link.link_context.link_url) {
                            links.push(String(item.link.link_context.link_url));
                        }
                        const altLinkPaths = [
                            ['media_share', 'permalink'],
                            ['reel_share', 'media', 'permalink'],
                            ['clip', 'permalink'],
                            ['story_share', 'media', 'permalink'],
                            ['xma_media_share', 'target_url'],
                        ];
                        for (const p of altLinkPaths) {
                            const v = getByPath(item, p);
                            if (typeof v === 'string' && v.trim()) {
                                links.push(v.trim());
                            }
                        }

                        if (!candidate) {
                            candidate = findNestedUsername(item);
                        }

                        const reactionObj = (item && item.reactions && typeof item.reactions === 'object') ? item.reactions : null;
                        const reactionCount = reactionObj
                            ? ((Array.isArray(reactionObj.emojis) ? reactionObj.emojis.length : 0)
                                + (Array.isArray(reactionObj.likes) ? reactionObj.likes.length : 0)
                                + Number(reactionObj.count || 0)
                                + Number(reactionObj.like_count || 0))
                            : 0;
                        const hasViewerReaction = !!(item && (item.has_viewer_reaction || item.viewer_reaction));
                        const alreadyReacted = hasViewerReaction || reactionCount > 0;

                        // Username bulunduysa veya link bulunduysa, aday listesine ekle
                        if (candidate || links.length) {
                            const messageId = String(
                                (item && (item.message_id || item.client_context)) || ''
                            ).trim();
                            out.candidates.push({
                                item_id: (item && (item.item_id || item.client_context)) ? String(item.item_id || item.client_context) : '',
                                message_id: messageId,
                                graphql_thread_id: graphqlThreadId,
                                username: candidate ? String(candidate) : null,
                                source_text: text,
                                source_links: [...new Set(links)],
                                already_reacted: alreadyReacted
                            });
                        }
                    }

                    if (out.candidates.length === 0) {
                        out.reason = 'no_partner_share_item';
                    }
                    out.candidates_count = out.candidates.length;
                    return out;
                } catch (err) {
                    out.reason = String(err || '');
                    return out;
                }
            }
            """,
            thread_id
        )

        if not data:
            return []

        # Tüm candidate'ları kontrol et
        candidates = data.get('candidates', [])
        if len(candidates) > 0:
            print(f"  [DEBUG] {len(candidates)} paylaşılan içerik kontrol ediliyor...")
        valid_targets = []
        
        for i, candidate_data in enumerate(candidates, 1):
            username = (candidate_data.get('username') or '').strip().lower()
            links = candidate_data.get('source_links') or []
            text = candidate_data.get('source_text') or ''
            item_id = (candidate_data.get('item_id') or '').strip()
            message_id = (candidate_data.get('message_id') or '').strip()
            graphql_thread_id = (candidate_data.get('graphql_thread_id') or '').strip()
            already_reacted = bool(candidate_data.get('already_reacted'))

            # Username bulunduysa kontrol et
            if username:
                # Debug çıktı
                reason = ""
                if self._is_reserved_instagram_segment(username):
                    reason = "[reserved]"
                elif username in excluded_usernames:
                    reason = "[partner]"
                elif not self._is_valid_username(username):
                    reason = "[invalid_format]"
                
                if reason:
                    print(f"    {i}. @{username} - atlandı {reason}")
                    continue
                
                if self._is_valid_username(username):
                    print(f"    {i}. @{username} ✓")
                    valid_targets.append({
                        'item_id': item_id,
                        'message_id': message_id,
                        'graphql_thread_id': graphql_thread_id,
                        'username': username,
                        'source_text': text,
                        'source_links': links,
                        'matched_link': (links[0] if links else None),
                        'source': 'thread_api',
                        'already_reacted': already_reacted
                    })
                    continue

            # Eğer username bulunamadıysa linklerden çöz
            for link in links:
                normalized = self._normalize_shared_instagram_link(link)
                resolved = await self.resolve_username_from_instagram_url(normalized or link)
                if resolved and resolved.lower() not in excluded_usernames:
                    valid_targets.append({
                        'item_id': item_id,
                        'message_id': message_id,
                        'graphql_thread_id': graphql_thread_id,
                        'username': resolved.lower(),
                        'source_text': text,
                        'source_links': links,
                        'matched_link': link,
                        'source': 'thread_api_link',
                        'already_reacted': already_reacted
                    })
                    break

        return valid_targets

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

        if self._is_reserved_instagram_segment(first_segment):
            return None

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
        async def scan_current_page(label):
            print(f"[DM] {label} taranıyor...")
            attempts = 3
            for attempt in range(1, attempts + 1):
                if attempt == 1:
                    await self.random_delay(12, 15)
                else:
                    print(f"[DM] Deneme {attempt}/{attempts}: sayfa yenileniyor...")
                    await self.page.reload(wait_until='domcontentloaded')
                    await self.random_delay(8, 10)

                await self.close_popups()

                # Sol konuşma listesinin yüklenmesine küçük bir pencere tanı.
                try:
                    await self.page.wait_for_function(
                        """() => !!document.querySelector('a[href*="/direct/t/"]')""",
                        timeout=7000
                    )
                except Exception:
                    pass

                # Listeyi kaydırarak lazy-loaded thread'leri görünür kıl.
                try:
                    await self.page.evaluate("""
                        () => {
                            const candidates = [
                                document.querySelector('div[role="main"]'),
                                ...document.querySelectorAll('div')
                            ];
                            for (const el of candidates) {
                                if (!el) continue;
                                if (el.scrollHeight > el.clientHeight + 120) {
                                    el.scrollTop = 0;
                                    el.scrollTop = Math.min(el.scrollHeight, 1200);
                                    break;
                                }
                            }
                        }
                    """)
                    await self.random_delay(1.5, 2.5)
                except Exception:
                    pass

                try:
                    thread_links = await self._collect_thread_links_from_dom()
                    if thread_links:
                        print(f"[DM] DOM ile {len(thread_links)} thread bulundu!")
                        return thread_links[:max_threads]
                except Exception as e:
                    print(f"[DM] DOM link toplama hatası: {str(e)[:70]}")

                # HTML fallback (script içinde gömülü URL yakalama)
                try:
                    html = await self.page.content()
                    html_links = self._extract_thread_links_from_html(html)
                    if html_links:
                        print(f"[DM] HTML fallback ile {len(html_links)} thread bulundu!")
                        return html_links[:max_threads]
                except Exception as e:
                    print(f"[DM] HTML fallback hatası: {str(e)[:70]}")

                # Inbox API fallback
                try:
                    api_result = await self._collect_thread_links_from_api()
                    api_links = api_result.get('links', [])
                    if api_links:
                        print(f"[DM] API fallback ile {len(api_links)} thread bulundu!")
                        return api_links[:max_threads]

                    if attempt == attempts:
                        body = (api_result.get('body') or '').strip()
                        body_note = f", body={body!r}" if body else ''
                        print(
                            f"[DM] API fallback boş döndü (ok={api_result.get('ok')}, status={api_result.get('status')}{body_note})"
                        )
                except Exception as e:
                    if attempt == attempts:
                        print(f"[DM] API fallback hatası: {str(e)[:70]}")

            return []

        print("[DM] Inbox aciliyor...")
        await self.page.goto('https://www.instagram.com/direct/inbox/', wait_until='domcontentloaded')
        await self.close_popups()
        print(f"[DM] Aktif URL: {self.page.url}")
        inbox_links = await scan_current_page('Inbox')
        if inbox_links:
            return inbox_links[:max_threads]

        # Primary inbox boşsa requests klasörünü de tara.
        print("[DM] Requests kutusu deneniyor...")
        await self.page.goto('https://www.instagram.com/direct/requests/', wait_until='domcontentloaded')
        await self.close_popups()
        requests_links = await scan_current_page('Requests')
        if requests_links:
            return requests_links[:max_threads]

        print("[DM] SORUN: Thread link bulunamadı!")
        print("[DM] Çözüm: DM inbox'ta en az 1 konuşmanın olması gerekiyor")
        return []

    async def get_latest_message_payload(self):
        """Açık konuşmadaki en son mesajın metin ve linklerini al."""
        try:
            await self.page.wait_for_selector('main', timeout=10000)
        except PlaywrightTimeout:
            return {'text': '', 'links': []}

        payload = await self.page.evaluate("""
            () => {
                const main = document.querySelector('main') || document.body;

                // 1) Row tabanlı yaklaşım
                const rows = [...main.querySelectorAll('div[role="row"]')];
                const rowCandidates = rows
                    .map((row) => {
                        const text = (row.innerText || '').trim();
                        const links = [...row.querySelectorAll('a[href]')]
                            .map(a => a.href)
                            .filter(Boolean)
                            .filter(href => href.includes('instagram.com'));
                        return { text, links };
                    })
                    .filter(item => item.text.length > 0 || item.links.length > 0);

                if (rowCandidates.length) {
                    return rowCandidates[rowCandidates.length - 1];
                }

                // 2) span[dir=auto] fallback
                const textParts = [...main.querySelectorAll('span[dir="auto"], div[dir="auto"]')]
                    .map(el => (el.innerText || '').trim())
                    .filter(Boolean);

                const links = [...main.querySelectorAll('a[href]')]
                    .map(a => a.href)
                    .filter(Boolean)
                    .filter(href => href.includes('instagram.com'));

                const text = textParts.length ? textParts[textParts.length - 1] : '';
                return { text, links };
            }
        """)

        return payload or {'text': '', 'links': []}

    async def get_recent_message_candidates(self, limit=60):
        """Konuşmadan son mesaj adaylarını (metin + linkler) topla."""
        try:
            await self.page.wait_for_selector('main', timeout=10000)
        except PlaywrightTimeout:
            return []

        items = await self.page.evaluate("""
            (limit) => {
                const main = document.querySelector('main') || document.body;
                const rows = [...main.querySelectorAll('div[role="row"]')];
                const results = [];

                for (const row of rows) {
                    const text = (row.innerText || '').trim();
                    const hrefLinks = [...row.querySelectorAll('a[href]')]
                        .map(a => a.href)
                        .filter(Boolean);

                    const urlRegex = new RegExp('https?:\\/\\/[^\\s)]+', 'gi');
                    const textUrls = (text.match(urlRegex) || []);
                    const links = [...new Set([...hrefLinks, ...textUrls])];

                    if (!text && !links.length) continue;

                    results.push({ text, links });
                }

                return results.slice(Math.max(0, results.length - limit));
            }
        """, limit)

        return items or []

    def _normalize_shared_instagram_link(self, link):
        """Paylaşılan linki Instagram hedef URL'sine normalize et."""
        if not link:
            return None

        raw = link.strip()
        if not raw.startswith('http://') and not raw.startswith('https://'):
            return None

        try:
            parsed = urlparse(raw)
            host = (parsed.netloc or '').lower()

            # l.instagram.com redirect linklerinden asıl URL'yi çıkar.
            if host.endswith('l.instagram.com'):
                qs = parse_qs(parsed.query)
                target = (qs.get('u') or [None])[0]
                if not target:
                    return None
                raw = unquote(target)
                parsed = urlparse(raw)
                host = (parsed.netloc or '').lower()

            if 'instagram.com' not in host:
                return None

            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except Exception:
            return None

    def _extract_username_from_share_text(self, text, excluded_usernames=None):
        """Paylaşım kartı metninden kullanıcı adı çıkar (link yoksa fallback)."""
        excluded_usernames = {u.lower() for u in (excluded_usernames or set()) if u}
        if not text:
            return None

        patterns = [
            r'([A-Za-z0-9._]{1,30})\s+adlı\s+kişinin\s+(?:gönderisi|reels?\s+videosu|reel(?:i)?)',
            r'([A-Za-z0-9._]{1,30})\s+tarafından\s+paylaşılan',
            r'([A-Za-z0-9._]{1,30})\'s\s+(?:post|reel)',
            r'(?:post|reel)\s+by\s+([A-Za-z0-9._]{1,30})',
            r'@([A-Za-z0-9._]{1,30})',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            for m in matches:
                candidate = (m or '').lower().strip('.,:;!?)]}')
                if not self._is_valid_username(candidate):
                    continue
                if self._is_reserved_instagram_segment(candidate):
                    continue
                if candidate in excluded_usernames:
                    continue
                return candidate

        return None

    async def extract_username_from_thread_context(self):
        """Mesajdan çıkarılamazsa thread başlık/bağlamından kullanıcı adı bul."""
        try:
            hrefs = await self.page.evaluate("""
                () => {
                    const targets = [
                        ...document.querySelectorAll('header a[href^="/"]'),
                        ...document.querySelectorAll('main a[href^="/"]')
                    ];
                    return targets.map(a => a.getAttribute('href') || '').filter(Boolean);
                }
            """)
        except Exception:
            hrefs = []

        for href in hrefs or []:
            cleaned = href.strip().split('#')[0].split('?')[0]
            if not cleaned.startswith('/'):
                continue
            first = cleaned.strip('/').split('/')[0].lower() if cleaned.strip('/') else ''
            if not first or self._is_reserved_instagram_segment(first):
                continue
            if self._is_valid_username(first):
                return first

        return None

    async def extract_username_from_message(self, message_text, links):
        """Mesaj metni ve linklerden kullanıcı adını bul."""
        links = links or []

        for link in links:
            username = await self.resolve_username_from_instagram_url(link)
            if username:
                return username

        if message_text:
            mention_matches = re.findall(r'@([A-Za-z0-9._]{1,30})', message_text)
            for mention in mention_matches:
                candidate = mention.lower().strip('.,:;!?)]}')
                if self._is_valid_username(candidate):
                    return candidate

            # Güvenli fallback: sadece "hesap/user/kullanıcı" anahtar kelimelerinden sonra gelen token.
            contextual = re.findall(
                r'(?i)(?:hesap|kullanici|kullanıcı|user|username)\s*[:=\-]?\s*([A-Za-z0-9._]{1,30})',
                message_text
            )
            for token in contextual:
                candidate = token.lower().strip('.,:;!?)]}')
                if self._is_valid_username(candidate):
                    return candidate

        return None

    async def find_target_from_thread_messages(self, limit=60):
        """Konuşma mesajlarında paylaşılan içerikten hedef kullanıcıyı bul.

        Öncelik sırası:
        1) Post/Reel/Hesap linkleri
        """
        return await self.find_target_from_shared_links(limit=limit, excluded_usernames=set())

    async def find_target_from_shared_links(self, limit=60, excluded_usernames=None):
        """Sadece mesaj içindeki paylaşılan Instagram linklerinden hedef kullanıcıyı bul."""
        excluded_usernames = {u.lower() for u in (excluded_usernames or set()) if u}

        candidates = await self.get_recent_message_candidates(limit=limit)
        if not candidates:
            return None

        # En güncelden eskiye doğru incele.
        for item in reversed(candidates):
            text = (item or {}).get('text', '') or ''
            raw_links = (item or {}).get('links', []) or []
            links = []
            for link in raw_links:
                normalized = self._normalize_shared_instagram_link(link)
                if normalized and normalized not in links:
                    links.append(normalized)

            # Bu akışta yalnızca paylaşılan linklerden hedef çıkar.
            for link in links:
                if '/direct/' in link:
                    continue
                username = await self.resolve_username_from_instagram_url(link)
                if not username:
                    continue
                if username.lower() in excluded_usernames:
                    continue

                return {
                    'username': username,
                    'source_text': text,
                    'source_links': links,
                    'matched_link': link
                }

            # Link yoksa/çözülemezse paylaşım kartı metninden sahibi çıkar.
            text_username = self._extract_username_from_share_text(
                text,
                excluded_usernames=excluded_usernames
            )
            if text_username:
                return {
                    'username': text_username,
                    'source_text': text,
                    'source_links': links,
                    'matched_link': None
                }

        return None

    async def ensure_following(self, username):
        """Hesap takip edilmiyorsa takip et."""
        profile_url = f'https://www.instagram.com/{username}/'
        print(f"  → Profil kontrolü: @{username}")

        try:
            await self.page.goto(profile_url)
            await self.random_delay(1.0, 1.8)
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
                'button:has-text("Follow")',
                'div[role="button"]:has-text("Takip Et")',
                'div[role="button"]:has-text("Follow")'
            ]
            for selector in follow_selectors:
                try:
                    btn = await self.page.wait_for_selector(selector, timeout=2500)
                    if btn:
                        await btn.click()
                        await self.random_delay(1.5, 2.4)
                        # Tıklama sonrası durumun gerçekten değiştiğini doğrula.
                        verify_selectors = [
                            'button:has-text("Takiptesin")',
                            'button:has-text("Following")',
                            'button:has-text("Requested")',
                            'button:has-text("İstek Gönderildi")',
                            'div[role="button"]:has-text("Takiptesin")',
                            'div[role="button"]:has-text("Following")',
                            'div[role="button"]:has-text("Requested")'
                        ]
                        verified = False
                        for v_selector in verify_selectors:
                            try:
                                v_btn = await self.page.wait_for_selector(v_selector, timeout=1200)
                                if v_btn:
                                    verified = True
                                    break
                            except Exception:
                                pass

                        if not verified:
                            # Durum metni bazen geç güncelleniyor; kısa bir ek pencere daha ver.
                            await self.random_delay(1.2, 1.8)
                            for v_selector in verify_selectors:
                                try:
                                    v_btn = await self.page.wait_for_selector(v_selector, timeout=900)
                                    if v_btn:
                                        verified = True
                                        break
                                except Exception:
                                    pass

                        if verified:
                            print("  ✓ Hesap takip edildi")
                            return 'followed'

                        # Instagram bazen buton durumunu gecikmeli güncelliyor.
                        print("  ⚠ Takip butonuna tıklandı, durum doğrulanamadı (attempted)")
                        return 'follow_attempted'
                except:
                    pass

            print("  ⚠ Takip durumu net tespit edilemedi")
            return 'unknown'
        except Exception as e:
            print(f"  ✗ Takip kontrol hatası: {str(e)[:70]}")
            return 'error'

    async def leave_heart_on_current_thread(self, source_text='', source_links=None, source_item_id='', source_message_id='', source_graphql_thread_id='', thread_url='', source_username=''):
        """Açık DM konuşmasında hedef mesaja kalp reaksiyonu bırak ve doğrula."""
        source_links = source_links or []
        source_username = (source_username or '').strip().lower().lstrip('@')
        source_item_id = (source_item_id or '').strip()
        source_message_id = (source_message_id or '').strip()
        source_graphql_thread_id = (source_graphql_thread_id or '').strip()
        thread_id = self._extract_thread_id_from_url(thread_url) if thread_url else None
        self._last_reaction_debug = {
            'thread_url': thread_url,
            'source_item_id_present': bool(source_item_id),
            'source_message_id_present': bool(source_message_id),
            'source_graphql_thread_id_present': bool(source_graphql_thread_id),
            'ui_probe': [],
            'target_count': 0,
            'target_select_stage': '',
            'ui_path_error': '',
            'api_attempt': None
        }
        use_api_reaction = False
        if not use_api_reaction:
            self._last_reaction_debug['api_attempt'] = {
                'ok': False,
                'reason': 'ui_only_mode_api_disabled',
                'tried': []
            }

        def normalized_link_key(url):
            if not url:
                return ''
            normalized = self._normalize_shared_instagram_link(url) or url
            return normalized.strip().rstrip('/').lower()

        async def row_has_heart_reaction(row):
            try:
                return await row.evaluate(
                    """
                    (el) => {
                        const text = (el.innerText || '').toLowerCase();
                        if (text.includes('❤️') || text.includes('❤')) return true;

                        const labelNodes = el.querySelectorAll('[aria-label], [alt], [title]');
                        for (const node of labelNodes) {
                            const label = (
                                node.getAttribute('aria-label') ||
                                node.getAttribute('alt') ||
                                node.getAttribute('title') ||
                                ''
                            ).toLowerCase();
                            if (!label) continue;
                            if (label.includes('heart') || label.includes('kalp')) {
                                return true;
                            }
                        }
                        return false;
                    }
                    """
                )
            except Exception:
                return False

        async def item_has_reaction_via_api():
            if not thread_id or (not source_item_id and not source_message_id):
                return False

            try:
                return await self.page.evaluate(
                    """
                    async ({ threadId, itemId, messageId }) => {
                        try {
                            const cookie = document.cookie || '';
                            const csrfMatch = cookie.match(/(?:^|;\\s*)csrftoken=([^;]+)/i);
                            const csrf = csrfMatch ? decodeURIComponent(csrfMatch[1]) : '';

                            const resp = await fetch(`/api/v1/direct_v2/threads/${threadId}/?limit=100`, {
                                credentials: 'include',
                                headers: {
                                    'x-requested-with': 'XMLHttpRequest',
                                    'x-csrftoken': csrf,
                                    'x-ig-app-id': '936619743392459'
                                }
                            });
                            if (!resp.ok) return false;
                            const json = await resp.json();
                            const items = ((json || {}).thread || {}).items || [];
                            const item = items.find(i => {
                                const iid = String(i?.item_id || '').trim();
                                const mid = String(i?.message_id || '').trim();
                                const cc = String(i?.client_context || '').trim();
                                const pk = String(i?.pk || '').trim();

                                if (itemId && (itemId === iid || itemId === cc || itemId === pk)) return true;
                                if (messageId && (messageId === mid || messageId === cc || messageId === iid)) return true;
                                return false;
                            });
                            if (!item) return false;

                            const reactions = item.reactions || null;
                            const reactionCount = reactions
                                ? ((Array.isArray(reactions.emojis) ? reactions.emojis.length : 0)
                                    + (Array.isArray(reactions.likes) ? reactions.likes.length : 0)
                                    + Number(reactions.count || 0)
                                    + Number(reactions.like_count || 0))
                                : 0;
                            const hasViewerReaction = !!(item.has_viewer_reaction || item.viewer_reaction);
                            return hasViewerReaction || reactionCount > 0;
                        } catch (_) {
                            return false;
                        }
                    }
                    """,
                    {'threadId': thread_id, 'itemId': source_item_id, 'messageId': source_message_id}
                )
            except Exception:
                return False

        async def send_heart_reaction_via_api():
            if not source_message_id or not source_graphql_thread_id:
                return {
                    'ok': False,
                    'reason': 'missing_message_or_graphql_thread_id',
                    'tried': []
                }

            try:
                result = await self.page.evaluate(
                    """
                    async ({ messageId, graphqlThreadId }) => {
                        const out = { ok: false, reason: 'unknown', tried: [] };
                        try {
                            const cookie = document.cookie || '';
                            const csrfMatch = cookie.match(/(?:^|;\\s*)csrftoken=([^;]+)/i);
                            const csrf = csrfMatch ? decodeURIComponent(csrfMatch[1]) : '';
                            const dsUserMatch = cookie.match(/(?:^|;\\s*)ds_user_id=([^;]+)/i);
                            const dsUserId = dsUserMatch ? decodeURIComponent(dsUserMatch[1]) : '0';

                            const fbDtsgEl = document.querySelector('input[name="fb_dtsg"]');
                            const lsdEl = document.querySelector('input[name="lsd"]');
                            const fbDtsg = fbDtsgEl ? (fbDtsgEl.value || '') : '';
                            const lsd = lsdEl ? (lsdEl.value || '') : '';

                            // jazoest hesaplama (Meta formlarında sık kullanılan kontrol alanı)
                            let jazoest = '';
                            if (fbDtsg) {
                                let sum = 0;
                                for (const ch of fbDtsg) sum += ch.charCodeAt(0);
                                jazoest = '2' + String(sum);
                            }

                            const headers = {
                                'x-requested-with': 'XMLHttpRequest',
                                'x-csrftoken': csrf,
                                'x-ig-app-id': '936619743392459',
                                'x-fb-friendly-name': 'IGDirectReactionSendMutation',
                                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'
                            };

                            const variables = JSON.stringify({
                                input: {
                                    emoji: '❤',
                                    item_id: '',
                                    message_id: messageId,
                                    reaction_status: 'created',
                                    thread_id: graphqlThreadId
                                }
                            });

                            const form = new URLSearchParams();
                            form.set('av', dsUserId || '0');
                            form.set('__user', '0');
                            form.set('__a', '1');
                            form.set('__d', 'www');
                            form.set('__comet_req', '7');
                            form.set('fb_api_caller_class', 'RelayModern');
                            form.set('fb_api_req_friendly_name', 'IGDirectReactionSendMutation');
                            form.set('server_timestamps', 'true');
                            form.set('qpl_active_flow_ids', '354954279');
                            form.set('fb_api_analytics_tags', '["qpl_active_flow_ids=354954279"]');
                            form.set('variables', variables);
                            form.set('doc_id', '24374451552236906');
                            if (fbDtsg) form.set('fb_dtsg', fbDtsg);
                            if (lsd) form.set('lsd', lsd);
                            if (jazoest) form.set('jazoest', jazoest);

                            try {
                                const resp = await fetch('/api/graphql', {
                                    method: 'POST',
                                    credentials: 'include',
                                    headers,
                                    body: form.toString()
                                });
                                let payload = null;
                                let rawText = '';
                                try {
                                    rawText = await resp.text();
                                    const cleaned = (rawText || '').replace(/^for \\(;;\\);\\s*/, '').trim();
                                    payload = cleaned ? JSON.parse(cleaned) : null;
                                } catch (_) {
                                    payload = null;
                                }

                                const hasErrors = !!(payload && Array.isArray(payload.errors) && payload.errors.length > 0);
                                const topLevelErrorCode = (payload && payload.error) ? Number(payload.error) : 0;
                                const hasTopLevelError = !!topLevelErrorCode;
                                const dataKeys = payload && payload.data ? Object.keys(payload.data) : [];
                                const hasDataPayload = dataKeys.length > 0;

                                out.tried.push({
                                    url: '/api/graphql',
                                    status: resp.status,
                                    hasErrors,
                                    hasTopLevelError,
                                    topLevelErrorCode,
                                    dataKeys,
                                    hasDataPayload,
                                    errorCount: payload && Array.isArray(payload.errors) ? payload.errors.length : 0,
                                    firstError: (payload && Array.isArray(payload.errors) && payload.errors[0])
                                        ? String(payload.errors[0].message || 'unknown_error')
                                        : '',
                                    errorSummary: (payload && payload.errorSummary) ? String(payload.errorSummary) : '',
                                    rawPreview: (rawText || '').slice(0, 180)
                                });

                                if (resp.ok && !hasErrors && !hasTopLevelError && hasDataPayload) {
                                    out.ok = true;
                                    out.reason = 'ok';
                                } else if (!resp.ok) {
                                    out.reason = `http_${resp.status}`;
                                } else if (hasTopLevelError) {
                                    out.reason = topLevelErrorCode === 1357001
                                        ? 'auth_login_required'
                                        : `graphql_top_level_error_${topLevelErrorCode}`;
                                } else if (hasErrors) {
                                    out.reason = 'graphql_errors';
                                } else if (!payload) {
                                    out.reason = 'invalid_or_empty_json_payload';
                                } else if (!hasDataPayload) {
                                    out.reason = 'graphql_data_empty';
                                } else {
                                    out.reason = 'no_ok_without_errors';
                                }
                            } catch (_) {
                                out.tried.push({ url: '/api/graphql', status: -1 });
                                out.reason = 'fetch_exception';
                            }

                            return out;
                        } catch (_) {
                            out.reason = 'evaluate_exception';
                            return out;
                        }
                    }
                    """,
                    {'messageId': source_message_id, 'graphqlThreadId': source_graphql_thread_id}
                )

                await self.random_delay(0.5, 0.9)
                if isinstance(result, dict):
                    return result
                return {
                    'ok': False,
                    'reason': 'invalid_api_result_type',
                    'tried': []
                }
            except Exception:
                return {
                    'ok': False,
                    'reason': 'python_exception',
                    'tried': []
                }

        async def click_heart_via_reaction_menu(row):
            try:
                await row.hover()
            except Exception:
                pass

            open_menu_selectors = [
                'button[aria-label*="Add reaction"]',
                'button[aria-label*="Reaction"]',
                'button[aria-label*="Tepki"]',
                '[aria-label*="React"]',
                '[aria-label*="Tepki"]',
                '[aria-label*="reaction"]',
                'button[aria-label*="emoji"]',
                'div[role="button"][aria-label*="React"]',
                'div[role="button"][aria-label*="Tepki"]'
            ]

            opened = False
            for selector in open_menu_selectors:
                try:
                    btn = await row.query_selector(selector)
                    if not btn:
                        btn = await self.page.query_selector(selector)
                    if btn:
                        await btn.click(timeout=1500)
                        await self.random_delay(0.5, 0.9)
                        opened = True
                        break
                except Exception:
                    continue

            if not opened:
                return False

            heart_selectors = [
                '[aria-label="❤️"]',
                '[aria-label*="red heart"]',
                '[aria-label*="Heart"]',
                '[aria-label*="Kalp"]',
                '[aria-label*="love"]',
                'button:has-text("❤️")',
                'div[role="button"]:has-text("❤️")'
            ]
            for selector in heart_selectors:
                try:
                    heart_btn = await self.page.query_selector(selector)
                    if heart_btn:
                        await heart_btn.click(timeout=1800)
                        await self.random_delay(0.6, 1.0)
                        return True
                except Exception:
                    continue

            return False

        async def resolve_reaction_surface(row):
            """Satır içinde reaksiyon bırakmaya en uygun hedef elementi bul."""
            try:
                handle = await row.evaluate_handle(
                    """
                    (el) => {
                        const preferred = [
                            'div[role="button"]',
                            'a[href*="instagram.com"]',
                            'span[dir="auto"]',
                            'div[dir="auto"]'
                        ];
                        for (const sel of preferred) {
                            const node = el.querySelector(sel);
                            if (node) return node;
                        }
                        return el;
                    }
                    """
                )
                as_el = handle.as_element()
                return as_el or row
            except Exception:
                return row

        async def capture_ui_probe(row, stage='attempt'):
            """Hedef satırdaki reaksiyonla ilgili UI sinyallerini topla."""
            try:
                probe = await row.evaluate(
                    """
                    (el) => {
                        const getCount = (sel) => el.querySelectorAll(sel).length;
                        const text = (el.innerText || '').trim().slice(0, 160);
                        const reactionBtnCount = getCount('button[aria-label*="reaction" i], [aria-label*="tepki" i], [aria-label*="react" i]');
                        const heartCount = getCount('[aria-label*="heart" i], [aria-label*="kalp" i], [aria-label="❤️"], [aria-label="❤"]');
                        const linkCount = getCount('a[href*="instagram.com"]');
                        const buttonCount = getCount('button, div[role="button"]');
                        return {
                            stage,
                            textPreview: text,
                            reactionBtnCount,
                            heartCount,
                            linkCount,
                            buttonCount,
                            hasRoleRow: (el.getAttribute('role') || '').toLowerCase() === 'row'
                        };
                    }
                    """,
                    stage
                )
            except Exception:
                probe = {'stage': stage, 'error': 'probe_exception'}

            ui_probe = self._last_reaction_debug.setdefault('ui_probe', [])
            ui_probe.append(probe)
            if len(ui_probe) > 20:
                del ui_probe[0:len(ui_probe) - 20]

        # Önce hedef mesajı link/text üzerinden bulup reaksiyon dene.
        try:
            async def resolve_row_handle(el):
                try:
                    row_handle = await el.evaluate_handle(
                        """
                        (node) => node.closest('div[role="row"], [role="listitem"], li') || node
                        """
                    )
                    row_el = row_handle.as_element()
                    return row_el or el
                except Exception:
                    return el

            targets = []
            source_link_keys = {normalized_link_key(link) for link in source_links if normalized_link_key(link)}

            async def collect_targets_once():
                found = []

                if source_link_keys:
                    anchors = await self.page.query_selector_all('a[href]')
                    for anchor in reversed(anchors):
                        href = ''
                        try:
                            href = await anchor.evaluate("el => el.href || el.getAttribute('href') || ''")
                        except Exception:
                            continue

                        if normalized_link_key(href) in source_link_keys:
                            row = await resolve_row_handle(anchor)
                            found.append((row, row))

                if source_text:
                    msg_nodes = await self.page.query_selector_all('span[dir="auto"], div[dir="auto"]')
                    for node in reversed(msg_nodes):
                        try:
                            text = (await node.inner_text()).strip()
                        except Exception:
                            continue

                        if text and source_text[:80] in text:
                            row = await resolve_row_handle(node)
                            found.append((row, row))

                if source_username:
                    rows = await self.page.query_selector_all('div[role="row"], [role="listitem"], li')
                    for row in reversed(rows):
                        try:
                            is_match = await row.evaluate(
                                """
                                (el, username) => {
                                    const t = (el.innerText || '').toLowerCase();
                                    if (t.includes(`@${username}`) || t.includes(username)) return true;
                                    const hrefs = [...el.querySelectorAll('a[href]')]
                                        .map(a => (a.href || '').toLowerCase());
                                    return hrefs.some(h => h.includes(`/` + username + `/`) || h.endsWith('/' + username));
                                }
                                """,
                                source_username
                            )
                            if is_match:
                                found.append((row, row))
                        except Exception:
                            continue

                return found

            targets = await collect_targets_once()
            self._last_reaction_debug['target_select_stage'] = 'initial_collect'

            # Eşleşme yoksa konuşma içinde biraz yukarı kaydırıp tekrar ara.
            if not targets:
                for _ in range(6):
                    try:
                        await self.page.mouse.wheel(0, -1200)
                        await self.random_delay(0.25, 0.45)
                    except Exception:
                        pass
                    targets = await collect_targets_once()
                    if targets:
                        self._last_reaction_debug['target_select_stage'] = 'after_scroll_collect'
                        break

            if not targets:
                try:
                    rows = await self.page.query_selector_all('div[role="row"], [role="listitem"], li')
                    for row in reversed(rows):
                        has_instagram_link = await row.evaluate(
                            """
                            (el) => [...el.querySelectorAll('a[href]')]
                                .some(a => (a.href || '').includes('instagram.com'))
                            """
                        )
                        if has_instagram_link:
                            print("  ⚠ Hedef satır bulunamadı, son Instagram linkli satır fallback denenecek")
                            targets.append((row, row))
                            self._last_reaction_debug['target_select_stage'] = 'fallback_last_instagram_link_row'
                            break
                except Exception:
                    pass

            self._last_reaction_debug['target_count'] = len(targets)

            seen_rows = set()
            attempted_rows = 0
            for row, action_target in targets:
                try:
                    row_key = await row.evaluate("el => (el.innerText || '').slice(0, 120)")
                except Exception:
                    row_key = str(id(row))
                if row_key in seen_rows:
                    continue
                seen_rows.add(row_key)
                attempted_rows += 1
                await capture_ui_probe(row, stage='target_selected')

                had_reaction_before = await row_has_heart_reaction(row)
                if had_reaction_before or await item_has_reaction_via_api():
                    print("  ✓ Hedef mesajda zaten kalp reaksiyonu var")
                    return True

                reaction_verified = False
                interactive_target = await resolve_reaction_surface(row)
                await capture_ui_probe(row, stage='before_dblclick')

                for _ in range(2):
                    try:
                        await row.scroll_into_view_if_needed()
                        await interactive_target.hover()
                    except Exception:
                        pass
                    try:
                        await interactive_target.click(timeout=1800)
                    except Exception:
                        pass
                    await interactive_target.dblclick(timeout=2500)
                    await self.random_delay(0.8, 1.2)
                    if await row_has_heart_reaction(row) or await item_has_reaction_via_api():
                        reaction_verified = True
                        break

                if reaction_verified:
                    print("  ✓ Hedef mesaja kalp reaksiyonu bırakıldı (doğrulandı)")
                    return True

                # Çift tık başarısızsa reaction menüsünden kalp dene.
                menu_clicked = await click_heart_via_reaction_menu(row)
                await capture_ui_probe(row, stage='after_menu_attempt')
                if menu_clicked and (await row_has_heart_reaction(row) or await item_has_reaction_via_api()):
                    print("  ✓ Hedef mesaja kalp reaksiyonu bırakıldı (menü + doğrulama)")
                    return True

                print("  ⚠ Bu aday mesajda reaksiyon doğrulanamadı, sonraki aday deneniyor")

            if attempted_rows > 0:
                print(f"  ⚠ {attempted_rows} aday mesaj denendi ancak reaksiyon doğrulanamadı")
                return False
        except Exception as e:
            self._last_reaction_debug['ui_path_error'] = str(e)[:180]
            print(f"  ⚠ UI reaction akış hatası: {str(e)[:120]}")

        print("  ⚠ Hedef mesaja doğrudan reaksiyon bırakma başarısız")
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
            'follow_attempted': 0,
            'already': 0,
            'hearted': 0,
            'skipped': 0,
            'details': []
        }

        follow_status_cache = {}
        for i, thread_href in enumerate(thread_links, 1):
            thread_url = f'https://www.instagram.com{thread_href}' if thread_href.startswith('/') else thread_href
            print(f"\n[{i}/{len(thread_links)}] Konuşma işleniyor...")
            results['processed'] += 1

            try:
                await self.page.goto(thread_url)
                await self.random_delay(2, 4)

                # Konuşma partnerini hedef dışı tut (ör: @seferumutkutlu)
                partner_username = await self.extract_username_from_thread_context()
                excluded = {partner_username.lower()} if partner_username else set()

                api_targets = await self.find_target_from_thread_api(
                    thread_url=thread_url,
                    excluded_usernames=excluded
                )
                candidates_count = len(api_targets or [])
                if candidates_count > 0:
                    print(f"  [DEBUG] API'den {candidates_count} geçerli hedef bulundu")

                targets_to_process = list(api_targets or [])
                if not targets_to_process:
                    fallback_target = await self.find_target_from_shared_links(
                        limit=60,
                        excluded_usernames=excluded
                    )
                    if fallback_target and fallback_target.get('username'):
                        fallback_target.setdefault('already_reacted', False)
                        targets_to_process.append(fallback_target)

                if not targets_to_process:
                    print("  ⚠ Paylaşılan post/reel/hesap linkinden hedef bulunamadı")
                    results['skipped'] += 1
                    results['details'].append({
                        'thread': thread_url,
                        'status': 'skipped_no_shared_target',
                        'partner_username': partner_username,
                        'message_preview': '',
                        'links_found': [],
                        'api_targets_found': candidates_count
                    })
                    continue

                # Max 15 hedef işle (browser crash'ını önlemek için)
                max_targets = 15
                deduped_targets = []
                seen_target_keys = set()
                for target in targets_to_process:
                    item_id = (target.get('item_id') or '').strip()
                    username_key = (target.get('username') or '').strip().lower()
                    link_key = (target.get('matched_link') or '').strip()
                    text_key = (target.get('source_text') or '').strip()[:80]
                    key = item_id or f"{username_key}|{link_key}|{text_key}"
                    if key in seen_target_keys:
                        continue
                    seen_target_keys.add(key)
                    deduped_targets.append(target)

                pending_targets = []
                for target in deduped_targets:
                    if target.get('already_reacted'):
                        results['skipped'] += 1
                        results['details'].append({
                            'thread': thread_url,
                            'username': (target or {}).get('username'),
                            'status': 'skipped_already_reacted',
                            'follow_status': None,
                            'hearted': False
                        })
                        continue
                    pending_targets.append(target)

                # Sadece konuşmada görünür/somut eşleşmesi olan hedefleri işle.
                visible_candidates = await self.get_recent_message_candidates(limit=80)

                def norm_link_key(url):
                    normalized = self._normalize_shared_instagram_link(url) or (url or '')
                    return normalized.strip().rstrip('/').lower()

                visible_link_keys = set()
                visible_texts = []
                for candidate in (visible_candidates or []):
                    c_text = (candidate.get('text') or '').strip()
                    if c_text:
                        visible_texts.append(c_text)
                    for c_link in (candidate.get('links') or []):
                        key = norm_link_key(c_link)
                        if key:
                            visible_link_keys.add(key)

                if not visible_link_keys and not visible_texts:
                    filtered_targets = pending_targets
                else:
                    filtered_targets = []
                    for target in pending_targets:
                        t_text = (target.get('source_text') or '').strip()
                        t_links = target.get('source_links') or []
                        t_link_keys = {norm_link_key(link) for link in t_links if norm_link_key(link)}

                        link_visible = bool(t_link_keys and (t_link_keys & visible_link_keys))
                        text_visible = False
                        if t_text:
                            head = t_text[:70]
                            text_visible = any(head and head in v_text for v_text in visible_texts)

                        if link_visible or text_visible:
                            filtered_targets.append(target)
                        else:
                            results['skipped'] += 1
                            results['details'].append({
                                'thread': thread_url,
                                'username': (target or {}).get('username'),
                                'status': 'skipped_target_not_visible',
                                'follow_status': None,
                                'hearted': False
                            })

                pending_targets = filtered_targets

                if not pending_targets:
                    print("  ✓ Bu konuşmada tepkisiz/emojisiz uygun paylaşım kalmadı")
                    await self.random_delay(0.8, 1.3)
                    continue

                for target in pending_targets[:max_targets]:
                    username = (target or {}).get('username')
                    source_text = (target or {}).get('source_text', '')
                    source_links = (target or {}).get('source_links', [])
                    source_item_id = (target or {}).get('item_id', '')
                    source_message_id = (target or {}).get('message_id', '')
                    source_graphql_thread_id = (target or {}).get('graphql_thread_id', '')

                    print(
                        "  [REACTION DEBUG] "
                        f"item_id={'set' if source_item_id else 'empty'}, "
                        f"message_id={'set' if source_message_id else 'empty'}, "
                        f"graphql_thread_id={'set' if source_graphql_thread_id else 'empty'}"
                    )

                    if not username:
                        results['skipped'] += 1
                        results['details'].append({
                            'thread': thread_url,
                            'status': 'skipped_invalid_target',
                            'partner_username': partner_username,
                            'message_preview': (source_text or '')[:120],
                            'links_found': (source_links or [])[:5]
                        })
                        continue

                    if username in follow_status_cache:
                        follow_status = follow_status_cache[username]
                        print(f"  ↺ Takip durumu cache kullanıldı: @{username} -> {follow_status}")
                    else:
                        follow_status = await self.ensure_following(username)
                    follow_status_cache[username] = follow_status

                    if follow_status == 'followed':
                        results['followed'] += 1
                    elif follow_status == 'follow_attempted':
                        results['follow_attempted'] += 1
                    elif follow_status == 'already_following':
                        results['already'] += 1

                    hearted = False
                    if follow_status in ('followed', 'already_following', 'follow_attempted'):
                        # Profilden geri dönüp aynı konuşmada kalp bırak
                        await self.page.goto(thread_url)
                        await self.random_delay(0.7, 1.2)
                        hearted = await self.leave_heart_on_current_thread(
                            source_text=source_text,
                            source_links=source_links,
                            source_item_id=source_item_id,
                            source_message_id=source_message_id,
                            source_graphql_thread_id=source_graphql_thread_id,
                            thread_url=thread_url,
                            source_username=username
                        )
                        if hearted:
                            results['hearted'] += 1
                    else:
                        print("  ⚠ Takip başarısız/doğrulanamadı, bu mesaja tepki bırakılmadı")

                    results['details'].append({
                        'thread': thread_url,
                        'username': username,
                        'follow_status': follow_status,
                        'hearted': hearted,
                        'reaction_debug': {
                            'item_id_present': bool(source_item_id),
                            'message_id_present': bool(source_message_id),
                            'graphql_thread_id_present': bool(source_graphql_thread_id),
                            'ui_probe': (getattr(self, '_last_reaction_debug', {}) or {}).get('ui_probe', []),
                            'target_count': (getattr(self, '_last_reaction_debug', {}) or {}).get('target_count', 0),
                            'target_select_stage': (getattr(self, '_last_reaction_debug', {}) or {}).get('target_select_stage', ''),
                            'ui_path_error': (getattr(self, '_last_reaction_debug', {}) or {}).get('ui_path_error', ''),
                            'api_attempt': (getattr(self, '_last_reaction_debug', {}) or {}).get('api_attempt')
                        }
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
        print(f"Takip denendi: {results['follow_attempted']}")
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

    async def capture_reaction_signature(self, max_threads=1, wait_seconds=240):
        """DM reaction request'ini manuel aksiyondan yakala ve dosyaya yaz."""
        print(f"\n{'='*50}")
        print("REACTION CAPTURE MODU")
        print(f"{'='*50}")

        thread_links = await self.get_recent_thread_links(max_threads=max_threads)
        if not thread_links:
            print("⚠ Capture için konuşma bulunamadı.")
            return {'captured': 0, 'requests': []}

        thread_href = thread_links[0]
        thread_url = f'https://www.instagram.com{thread_href}' if thread_href.startswith('/') else thread_href
        await self.page.goto(thread_url)
        await self.random_delay(2, 3)

        print("\n1) Açık konuşmada herhangi bir paylaşıma elle reaction (kalp) bırak")
        print("2) Reaction bıraktıktan sonra terminale dönüp ENTER'a bas")
        print(f"3) Otomatik dinleme aktif (max {wait_seconds} sn)")

        captured_all = []

        def is_candidate_reaction(url, method, post_data):
            if method.upper() != 'POST':
                return False
            url_l = (url or '').lower()
            body_l = (post_data or '').lower()

            if 'instagram.com' not in url_l:
                return False

            # direct / graphql / xdt_api kanallarında reaction benzeri tokenları yakala.
            channel_tokens = ('direct', 'direct_v2', 'graphql', 'xdt_api')
            if not any(tok in url_l or tok in body_l for tok in channel_tokens):
                return False

            reaction_tokens = ('reaction', 'reactions', 'send_item', 'emoji', 'like', 'heart')
            return any(tok in url_l or tok in body_l for tok in reaction_tokens)

        def on_request(req):
            try:
                post_data = req.post_data or ''
                url_l = (req.url or '').lower()

                # Çok fazla log büyümesini önlemek için yalnızca Instagram POST isteklerini topla.
                if req.method.upper() != 'POST' or 'instagram.com' not in url_l:
                    return

                item = {
                    'ts': int(time.time()),
                    'method': req.method,
                    'url': req.url,
                    'post_data': post_data,
                    'headers': {
                        'x-csrftoken': req.headers.get('x-csrftoken', ''),
                        'x-ig-app-id': req.headers.get('x-ig-app-id', ''),
                        'content-type': req.headers.get('content-type', ''),
                    }
                }

                captured_all.append(item)
                if len(captured_all) > 500:
                    del captured_all[0:len(captured_all)-500]

                if is_candidate_reaction(req.url, req.method, post_data):
                    print(f"[CAPTURE:CANDIDATE] {req.method} {req.url}")
                else:
                    print(f"[CAPTURE:POST] {req.method} {req.url}")
            except Exception:
                pass

        self.context.on('request', on_request)
        try:
            await asyncio.wait_for(
                asyncio.to_thread(input, "\n[Reaction bıraktıktan sonra ENTER] > "),
                timeout=wait_seconds
            )
            # ENTER sonrası in-flight isteklerin düşmesi için kısa bekleme.
            await self.random_delay(2.0, 3.0)
        except asyncio.TimeoutError:
            print("⚠ Capture timeout: Süre doldu.")
        finally:
            try:
                self.context.remove_listener('request', on_request)
            except Exception:
                pass

        dedup = []
        seen = set()
        for item in captured_all:
            key = f"{item.get('method')}|{item.get('url')}|{item.get('post_data')}"
            if key in seen:
                continue
            seen.add(key)
            dedup.append(item)

        reaction_candidates = [
            item for item in dedup
            if is_candidate_reaction(item.get('url', ''), item.get('method', ''), item.get('post_data', ''))
        ]

        # Son 20 POST isteği debug için sakla.
        tail_posts = dedup[-20:]

        result = {
            'captured': len(reaction_candidates),
            'captured_all_posts': len(dedup),
            'thread_url': thread_url,
            'requests': reaction_candidates,
            'post_tail': tail_posts
        }

        with open('reaction_capture.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        if reaction_candidates:
            print(f"\n✓ Capture başarılı: {len(reaction_candidates)} reaction-aday request bulundu")
            print("Sonuç dosyası: reaction_capture.json")
        else:
            print("\n⚠ Reaction-aday request yakalanamadı")
            print(f"Ama {len(dedup)} adet Instagram POST yakalandı, reaction_capture.json içinde post_tail bölümünü kontrol edeceğim.")

        return result


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


async def main_capture_reaction(max_threads=1, profile_name='default'):
    """DM reaction network isteğini yakalamak için manuel capture modu."""
    bot = InstagramBot(headless=False, profile_name=profile_name)

    try:
        await bot.start()

        if not await bot.login():
            print("Giriş başarısız. Program sonlandırılıyor.")
            return

        result = await bot.capture_reaction_signature(max_threads=max_threads)
        print(f"Capture sonucu: {result.get('captured', 0)} request")
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

    if args[0] == '--capture-reaction':
        parsed['mode'] = 'capture_reaction'
        parsed['max_threads'] = 1
        cursor = 1
        if cursor < len(args) and not args[cursor].startswith('--'):
            try:
                parsed['max_threads'] = int(args[cursor])
                cursor += 1
            except ValueError:
                print("Geçersiz konuşma limiti, varsayılan 1 kullanılacak.")
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
        elif parsed['mode'] == 'capture_reaction':
            asyncio.run(main_capture_reaction(
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
            print("  python instagram_bot.py --capture-reaction 1 --profile deneme")
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
