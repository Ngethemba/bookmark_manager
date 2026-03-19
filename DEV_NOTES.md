# Development Notes - Status & TODO

## Current Status as of March 19, 2026

### ✅ Completed Features
- [x] Flask web UI with admin dashboard
- [x] Instagram bookmark removal automation (bulk delete)
- [x] Multi-account support with separate browser profiles
- [x] Account management UI (select, add, setup login)
- [x] DM message scanning & parsing
- [x] Username extraction from messages (@mention, URLs, media)
- [x] Automatic follow functionality
- [x] Heart reaction sending
- [x] PyInstaller .exe compilation for both launchers
- [x] Python venv detection in frozen .exe
- [x] UTF-8 encoding fixes for Windows console
- [x] Login/2FA waiting with 300s timeout
- [x] Non-interactive input handling (EOF/KeyboardInterrupt)

### 🔴 Current Blocker: DM Thread Discovery
**Problem**: DM inbox page loads, browser is logged in, but thread conversation links cannot be extracted from DOM.

**Root Cause**: Instagram uses dynamic JavaScript rendering - `/direct/t/*` links not directly in `<a>` tags in initial DOM state.

**Attempted Solutions**:
1. `a[href*="/direct/t/"]` selector - 0 results
2. Role-based selectors (`[role="button"]`) - buttons exist (11 found) but no link hrefs
3. JavaScript DOM eval - finds only `/direct/inbox/` and `/direct/requests/` links, no `/direct/t/`

**Evidence**:
```
Console Output (dm_debug2.log):
[DM] Inbox aciliyor...
[DM] Konusma butonlari aran─▒yor...
[DM] 11 button bulundu
[DM] Direct linkler bulunamad─▒ - devam─▒ndan kontrol et...
[DM] SORUN: Konusma linkler bulunamad─▒!
```

### Next Steps for Resolution

**Option A: DOM Selector Investigation** (Priority: HIGH)
1. DM inbox page → F12 Console
2. Run user-provided JavaScript:
   ```javascript
   [...document.querySelectorAll('a')].filter(a=>a.href.includes('/direct/t/')).map(a=>a.href)
   ```
3. If results show thread links, update `get_recent_thread_links()` with working selector
4. If 0 results, investigate Instagram's page structure further

**Option B: Event-Based Navigation** (Priority: MEDIUM)
- Instead of finding thread links directly, detect click events on buttons
- Use `page.on('framenavigated')` or `page.on('load')` to capture URL changes
- When user clicks thread button, capture resulting URL

**Option C: API Route Interception** (Priority: MEDIUM)
- Use Playwright's route interception to capture Instagram's internal API calls
- Intercept GraphQL requests to `/graphql` endpoint
- Extract thread IDs/links from API responses instead of DOM

### Code Architecture

**instagram_bot.py** (~850 lines)
- `InstagramBot` class: main browser automation
- `async def get_recent_thread_links()` - **BLOCKER HERE**
- `async def process_direct_messages_for_follow()` - depends on above
- Profile support via constructor parameter
- CLI args parsing for `--scan-dm`, `--setup-account`, `--profile`

**app.py** (~950 lines)
- Flask endpoints for account management
- `/api/bot/accounts` (GET, POST, POST/select, POST/setup-login)
- `/api/bot/start-removal` (start bot subprocess)
- SQLAlchemy models (Bookmark, Category, Tag)
- instagram_accounts.json persistence

**launcher_dm_follow.py**
- Standalone executable entry point
- Interactive account menu
- UTF-8 encoding setup
- Calls instagram_bot.py as subprocess with `--scan-dm`

**templates/index.html**
- Account selector (main panel + modal)
- Bookmark removal form
- Real-time account sync

### Known Issues & Workarounds

1. **Windows Console Encoding**: Fixed with `PYTHONIOENCODING=utf-8` and `io.TextIOWrapper` rewrap
2. **Frozen .exe Python Detection**: Resolved with `sys.frozen` check + venv path resolution
3. **Non-Interactive Input**: Added EOF/KeyboardInterrupt handlers
4. **PyInstaller Build Conflicts**: Killed existing process before rebuilding

### Testing Checklist

- [x] Launcher menu appears on .exe double-click
- [x] Account selection works
- [x] Instagram login succeeds (manual 2FA supported)
- [x] Profile-based session isolation works
- [x] Browser opens correctly with stealth mode
- [ ] DM threads discovered (BLOCKED)
- [ ] Follow automation works (untested - blocked by threads)
- [ ] Heart reactions send (untested - blocked by threads)

### Context Window Status

**Before Archival**: ~80k tokens used
**Conversation Length**: 20+ exchanges
**Code Scale**: 2600+ lines across main modules

**Resources Needed**:
- Smaller context window fresh start
- Focusing on Option A (JavaScript console testing)
- or Option C (API interception approach)

### How Next AI Agent Should Start

1. Read this file for context
2. Focus on `get_recent_thread_links()` in instagram_bot.py
3. Ask user to provide console JavaScript output from live DM inbox page
4. Update selector based on actual page structure
5. Re-test with launcher

### Files to Review Priority

1. `instagram_bot.py` - lines 333-380 (get_recent_thread_links)
2. `instagram_bot.py` - lines 494-600 (process_direct_messages_for_follow)  
3. `launcher_dm_follow.py` - lines 175-250 (main run function)
4. `app.py` - lines 200-250 (account endpoints)

### Useful Commands for Testing

```bash
# Run DM bot with debug output
python launcher_dm_follow.py

# Run bot directly
python instagram_bot.py --scan-dm 2 --profile default

# Test with head-full browser (not headless)
# Already enabled in instagram_bot.py (headless=False)

# Rebuild .exe
python -m PyInstaller --noconfirm --onefile --name DMFollowLauncher launcher_dm_follow.py
```
