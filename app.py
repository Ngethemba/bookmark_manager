"""
Sosyal Medya Yer İşareti Yöneticisi
Instagram Kaydedilenler ve X Yer İşaretleri Yönetim Uygulaması
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
import os
import re
import sys
import urllib.request
import urllib.error
from html.parser import HTMLParser

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bookmarks.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Veritabanı Modelleri
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    color = db.Column(db.String(7), default='#3498db')
    bookmarks = db.relationship('Bookmark', backref='category', lazy=True)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)

bookmark_tags = db.Table('bookmark_tags',
    db.Column('bookmark_id', db.Integer, db.ForeignKey('bookmark.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

class Bookmark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    url = db.Column(db.String(1000), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(1000))
    platform = db.Column(db.String(20), nullable=False)  # 'instagram' veya 'x'
    original_author = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    saved_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_favorite = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    tags = db.relationship('Tag', secondary=bookmark_tags, lazy='subquery',
                          backref=db.backref('bookmarks', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'description': self.description,
            'image_url': self.image_url,
            'platform': self.platform,
            'original_author': self.original_author,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'saved_at': self.saved_at.isoformat() if self.saved_at else None,
            'is_favorite': self.is_favorite,
            'is_archived': self.is_archived,
            'notes': self.notes,
            'category': self.category.name if self.category else None,
            'category_id': self.category_id,
            'tags': [tag.name for tag in self.tags]
        }

# Ana Sayfa
@app.route('/')
def index():
    return render_template('index.html')

# Tüm yer işaretlerini getir
@app.route('/api/bookmarks', methods=['GET'])
def get_bookmarks():
    platform = request.args.get('platform')
    category_id = request.args.get('category_id')
    search = request.args.get('search')
    show_archived = request.args.get('archived', 'false') == 'true'
    favorites_only = request.args.get('favorites', 'false') == 'true'
    
    query = Bookmark.query
    
    if not show_archived:
        query = query.filter_by(is_archived=False)
    
    if platform:
        query = query.filter_by(platform=platform)
    
    if category_id:
        query = query.filter_by(category_id=int(category_id))
    
    if favorites_only:
        query = query.filter_by(is_favorite=True)
    
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            db.or_(
                Bookmark.title.ilike(search_term),
                Bookmark.description.ilike(search_term),
                Bookmark.original_author.ilike(search_term),
                Bookmark.notes.ilike(search_term)
            )
        )
    
    bookmarks = query.order_by(Bookmark.saved_at.desc()).all()
    return jsonify([b.to_dict() for b in bookmarks])

# Yeni yer işareti ekle
@app.route('/api/bookmarks', methods=['POST'])
def add_bookmark():
    data = request.json
    
    bookmark = Bookmark(
        title=data.get('title', 'Başlıksız'),
        url=data['url'],
        description=data.get('description'),
        image_url=data.get('image_url'),
        platform=data['platform'],
        original_author=data.get('original_author'),
        notes=data.get('notes'),
        category_id=data.get('category_id')
    )
    
    # Etiketleri ekle
    if 'tags' in data:
        for tag_name in data['tags']:
            tag = Tag.query.filter_by(name=tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.session.add(tag)
            bookmark.tags.append(tag)
    
    db.session.add(bookmark)
    db.session.commit()
    
    return jsonify(bookmark.to_dict()), 201

# Yer işaretini güncelle
@app.route('/api/bookmarks/<int:id>', methods=['PUT'])
def update_bookmark(id):
    bookmark = Bookmark.query.get_or_404(id)
    data = request.json
    
    if 'title' in data:
        bookmark.title = data['title']
    if 'description' in data:
        bookmark.description = data['description']
    if 'notes' in data:
        bookmark.notes = data['notes']
    if 'is_favorite' in data:
        bookmark.is_favorite = data['is_favorite']
    if 'is_archived' in data:
        bookmark.is_archived = data['is_archived']
    if 'category_id' in data:
        bookmark.category_id = data['category_id']
    
    if 'tags' in data:
        bookmark.tags = []
        for tag_name in data['tags']:
            tag = Tag.query.filter_by(name=tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.session.add(tag)
            bookmark.tags.append(tag)
    
    db.session.commit()
    return jsonify(bookmark.to_dict())

# Yer işaretini sil
@app.route('/api/bookmarks/<int:id>', methods=['DELETE'])
def delete_bookmark(id):
    bookmark = Bookmark.query.get_or_404(id)
    db.session.delete(bookmark)
    db.session.commit()
    return jsonify({'message': 'Silindi'}), 200

# Toplu silme
@app.route('/api/bookmarks/bulk-delete', methods=['POST'])
def bulk_delete():
    ids = request.json.get('ids', [])
    Bookmark.query.filter(Bookmark.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'message': f'{len(ids)} yer işareti silindi'}), 200

# Toplu arşivleme
@app.route('/api/bookmarks/bulk-archive', methods=['POST'])
def bulk_archive():
    ids = request.json.get('ids', [])
    Bookmark.query.filter(Bookmark.id.in_(ids)).update({Bookmark.is_archived: True}, synchronize_session=False)
    db.session.commit()
    return jsonify({'message': f'{len(ids)} yer işareti arşivlendi'}), 200

# Kategoriler
@app.route('/api/categories', methods=['GET'])
def get_categories():
    categories = Category.query.all()
    return jsonify([{'id': c.id, 'name': c.name, 'color': c.color} for c in categories])

@app.route('/api/categories', methods=['POST'])
def add_category():
    data = request.json
    category = Category(name=data['name'], color=data.get('color', '#3498db'))
    db.session.add(category)
    db.session.commit()
    return jsonify({'id': category.id, 'name': category.name, 'color': category.color}), 201

@app.route('/api/categories/<int:id>', methods=['DELETE'])
def delete_category(id):
    category = Category.query.get_or_404(id)
    # Kategorideki yer işaretlerinin kategorisini null yap
    Bookmark.query.filter_by(category_id=id).update({Bookmark.category_id: None})
    db.session.delete(category)
    db.session.commit()
    return jsonify({'message': 'Kategori silindi'}), 200

# Etiketler
@app.route('/api/tags', methods=['GET'])
def get_tags():
    tags = Tag.query.all()
    return jsonify([{'id': t.id, 'name': t.name} for t in tags])

# İçe aktarma (JSON formatında)
@app.route('/api/import', methods=['POST'])
def import_bookmarks():
    data = request.json
    imported_count = 0
    
    for item in data.get('bookmarks', []):
        bookmark = Bookmark(
            title=item.get('title', 'Başlıksız'),
            url=item['url'],
            description=item.get('description'),
            image_url=item.get('image_url'),
            platform=item.get('platform', 'unknown'),
            original_author=item.get('original_author'),
        )
        db.session.add(bookmark)
        imported_count += 1
    
    db.session.commit()
    return jsonify({'message': f'{imported_count} yer işareti içe aktarıldı'}), 201

# ============ INSTAGRAM VERİ DOSYASI İÇE AKTARMA ============
@app.route('/api/import/instagram', methods=['POST'])
def import_instagram_data():
    """
    Instagram'dan indirilen veri dosyasını işle
    Desteklenen formatlar:
    - saved_posts.json
    - your_saved_posts.json (yeni format)
    """
    data = request.json
    imported_count = 0
    skipped_count = 0
    errors = []
    
    # Debug: Gelen veriyi logla
    print(f"[DEBUG] Instagram import - Veri tipi: {type(data)}")
    if isinstance(data, dict):
        print(f"[DEBUG] Anahtarlar: {list(data.keys())[:10]}")
    elif isinstance(data, list):
        print(f"[DEBUG] Liste uzunluğu: {len(data)}")
        if len(data) > 0:
            print(f"[DEBUG] İlk eleman tipi: {type(data[0])}")
            if isinstance(data[0], dict):
                print(f"[DEBUG] İlk eleman anahtarları: {list(data[0].keys())}")
    
    try:
        # Instagram veri formatlarını dene
        saved_items = []
        
        # Format 1: saved_saved_media (eski format)
        if isinstance(data, dict) and 'saved_saved_media' in data:
            print("[DEBUG] Format: saved_saved_media")
            for item in data['saved_saved_media']:
                if 'string_list_data' in item:
                    for string_data in item['string_list_data']:
                        if 'href' in string_data:
                            saved_items.append({
                                'url': string_data['href'],
                                'timestamp': string_data.get('timestamp'),
                                'title': item.get('title', '')
                            })
        
        # Format 2: saved_posts (alternatif)
        elif isinstance(data, dict) and 'saved_posts' in data:
            print("[DEBUG] Format: saved_posts")
            for item in data['saved_posts']:
                if 'string_list_data' in item:
                    for string_data in item['string_list_data']:
                        if 'href' in string_data:
                            saved_items.append({
                                'url': string_data['href'],
                                'timestamp': string_data.get('timestamp'),
                                'title': item.get('title', '')
                            })
        
        # Format 3: Doğrudan liste (yeni Instagram formatı)
        elif isinstance(data, list):
            print(f"[DEBUG] Format: Liste ({len(data)} eleman)")
            for item in data:
                if isinstance(item, dict):
                    # Yeni format: string_map_data içinde media bilgisi
                    if 'string_map_data' in item:
                        media_data = item['string_map_data']
                        url = None
                        title = ''
                        timestamp = None
                        
                        # URL'yi bul
                        if 'Saved on' in media_data:
                            timestamp = media_data.get('Saved on', {}).get('timestamp')
                        
                        # Media URI
                        for key in ['Media', 'URI', 'Link']:
                            if key in media_data and media_data[key].get('href'):
                                url = media_data[key]['href']
                                break
                        
                        if url:
                            saved_items.append({'url': url, 'timestamp': timestamp, 'title': title})
                    
                    # string_list_data formatı
                    elif 'string_list_data' in item:
                        for string_data in item['string_list_data']:
                            if 'href' in string_data:
                                saved_items.append({
                                    'url': string_data['href'],
                                    'timestamp': string_data.get('timestamp'),
                                    'title': item.get('title', '')
                                })
                    
                    # Basit format: doğrudan href/url
                    else:
                        url = item.get('href') or item.get('url') or item.get('link') or item.get('uri')
                        if url:
                            saved_items.append({
                                'url': url,
                                'timestamp': item.get('timestamp'),
                                'title': item.get('title', '')
                            })
        
        # Format 4: saved_collections (koleksiyonlar)
        if isinstance(data, dict) and 'saved_collections' in data:
            print("[DEBUG] Format: saved_collections")
            for collection in data['saved_collections']:
                for item in collection.get('string_list_data', []):
                    if 'href' in item:
                        saved_items.append({
                            'url': item['href'],
                            'timestamp': item.get('timestamp'),
                            'title': collection.get('title', '')
                        })
        
        # Format 5: İç içe yapı kontrolü (herhangi bir key altında)
        if isinstance(data, dict) and len(saved_items) == 0:
            print("[DEBUG] Alternatif format aranıyor...")
            for key, value in data.items():
                if isinstance(value, list):
                    print(f"[DEBUG] '{key}' altında {len(value)} eleman bulundu")
                    for item in value:
                        if isinstance(item, dict):
                            # href ara
                            url = None
                            if 'string_list_data' in item:
                                for sd in item['string_list_data']:
                                    if 'href' in sd:
                                        url = sd['href']
                                        break
                            elif 'string_map_data' in item:
                                for k, v in item['string_map_data'].items():
                                    if isinstance(v, dict) and 'href' in v:
                                        url = v['href']
                                        break
                            else:
                                url = item.get('href') or item.get('url') or item.get('uri')
                            
                            if url and 'instagram.com' in url:
                                saved_items.append({
                                    'url': url,
                                    'timestamp': item.get('timestamp'),
                                    'title': item.get('title', '')
                                })
        
        print(f"[DEBUG] Toplam bulunan URL: {len(saved_items)}")
        
        # Kaydet
        for item in saved_items:
            url = item['url']
            
            # Zaten var mı kontrol et
            existing = Bookmark.query.filter_by(url=url).first()
            if existing:
                skipped_count += 1
                continue
            
            # Tarih dönüşümü
            saved_at = None
            if item.get('timestamp'):
                try:
                    saved_at = datetime.fromtimestamp(item['timestamp'])
                except:
                    pass
            
            bookmark = Bookmark(
                title=item.get('title') or 'Instagram Gönderi',
                url=url,
                platform='instagram',
                original_author=extract_username(url, 'instagram'),
                saved_at=saved_at or datetime.utcnow()
            )
            db.session.add(bookmark)
            imported_count += 1
        
        db.session.commit()
        
        message = f'{imported_count} Instagram kaydı içe aktarıldı'
        if skipped_count > 0:
            message += f' ({skipped_count} zaten mevcuttu)'
        
        if imported_count == 0 and skipped_count == 0:
            return jsonify({
                'error': 'Hiç kayıt bulunamadı',
                'hint': 'JSON dosyasının formatı desteklenmiyor olabilir. Dosyanın ilk birkaç satırını paylaşır mısınız?',
                'imported': 0,
                'skipped': 0
            }), 400
        
        return jsonify({
            'message': message,
            'imported': imported_count,
            'skipped': skipped_count
        }), 201
        
    except Exception as e:
        import traceback
        print(f"[ERROR] {traceback.format_exc()}")
        return jsonify({
            'error': f'Dosya işlenirken hata: {str(e)}',
            'hint': 'Instagram veri formatını kontrol edin'
        }), 400

# ============ X (TWITTER) VERİ DOSYASI İÇE AKTARMA ============
@app.route('/api/import/twitter', methods=['POST'])
def import_twitter_data():
    """
    X/Twitter'dan indirilen veri dosyasını işle
    Desteklenen formatlar:
    - bookmarks.js (Twitter arşivi)
    - bookmark.json
    """
    data = request.json
    imported_count = 0
    skipped_count = 0
    
    try:
        bookmarks_list = []
        
        # Format 1: bookmarks array
        if isinstance(data, list):
            bookmarks_list = data
        # Format 2: {"bookmark": [...]}
        elif 'bookmark' in data:
            bookmarks_list = data['bookmark']
        # Format 3: {"bookmarks": [...]}
        elif 'bookmarks' in data:
            bookmarks_list = data['bookmarks']
        # Format 4: {"data": {"bookmark_timeline": {...}}}
        elif 'data' in data:
            timeline = data.get('data', {}).get('bookmark_timeline_v2', {})
            if 'timeline' in timeline:
                entries = timeline.get('timeline', {}).get('instructions', [])
                for instruction in entries:
                    if 'entries' in instruction:
                        for entry in instruction['entries']:
                            content = entry.get('content', {})
                            if 'itemContent' in content:
                                tweet = content['itemContent'].get('tweet_results', {}).get('result', {})
                                if tweet:
                                    bookmarks_list.append({'tweet': tweet})
        
        # İşle
        for item in bookmarks_list:
            tweet_data = item.get('tweet', item)
            
            # Tweet ID bul
            tweet_id = (
                tweet_data.get('tweetId') or 
                tweet_data.get('id') or 
                tweet_data.get('id_str') or
                tweet_data.get('rest_id')
            )
            
            if not tweet_id:
                continue
            
            # URL oluştur
            url = f"https://x.com/i/status/{tweet_id}"
            
            # Zaten var mı kontrol et
            existing = Bookmark.query.filter_by(url=url).first()
            if not existing:
                # Alternatif URL formatını da kontrol et
                alt_url = f"https://twitter.com/i/status/{tweet_id}"
                existing = Bookmark.query.filter_by(url=alt_url).first()
            
            if existing:
                skipped_count += 1
                continue
            
            # İçerik ve kullanıcı bilgilerini çıkar
            full_text = (
                tweet_data.get('fullText') or 
                tweet_data.get('full_text') or 
                tweet_data.get('text') or
                tweet_data.get('legacy', {}).get('full_text', '')
            )
            
            # Kullanıcı adı
            user_data = tweet_data.get('core', {}).get('user_results', {}).get('result', {})
            screen_name = (
                tweet_data.get('screen_name') or
                tweet_data.get('user', {}).get('screen_name') or
                user_data.get('legacy', {}).get('screen_name')
            )
            
            # Tarih
            created_at = tweet_data.get('created_at') or tweet_data.get('legacy', {}).get('created_at')
            saved_at = None
            if created_at:
                try:
                    # Twitter tarih formatı: "Wed Oct 10 20:19:24 +0000 2018"
                    saved_at = datetime.strptime(created_at, '%a %b %d %H:%M:%S %z %Y')
                except:
                    pass
            
            bookmark = Bookmark(
                title=full_text[:200] if full_text else 'X Gönderi',
                url=url,
                description=full_text if len(full_text) > 200 else None,
                platform='x',
                original_author=f"@{screen_name}" if screen_name else None,
                saved_at=saved_at or datetime.utcnow()
            )
            db.session.add(bookmark)
            imported_count += 1
        
        db.session.commit()
        
        message = f'{imported_count} X yer işareti içe aktarıldı'
        if skipped_count > 0:
            message += f' ({skipped_count} zaten mevcuttu)'
        
        return jsonify({
            'message': message,
            'imported': imported_count,
            'skipped': skipped_count
        }), 201
        
    except Exception as e:
        return jsonify({
            'error': f'Dosya işlenirken hata: {str(e)}',
            'hint': 'X/Twitter veri formatını kontrol edin'
        }), 400

# URL'den platform algılama
def detect_platform(url):
    url_lower = url.lower()
    if 'instagram.com' in url_lower or 'instagr.am' in url_lower:
        return 'instagram'
    elif 'twitter.com' in url_lower or 'x.com' in url_lower or 't.co' in url_lower:
        return 'x'
    return 'unknown'

# URL'den kullanıcı adı çıkarma
def extract_username(url, platform):
    try:
        if platform == 'instagram':
            # instagram.com/username/ veya instagram.com/p/xxx/
            match = re.search(r'instagram\.com/([^/]+)', url)
            if match and match.group(1) not in ['p', 'reel', 'stories', 'tv']:
                return f"@{match.group(1)}"
            # Post URL'sinden kullanıcı adı çıkaramayız
        elif platform == 'x':
            # twitter.com/username/status/xxx veya x.com/username/status/xxx
            match = re.search(r'(?:twitter|x)\.com/([^/]+)', url)
            if match and match.group(1) not in ['i', 'search', 'explore', 'home']:
                return f"@{match.group(1)}"
    except:
        pass
    return None

# Basit HTML meta tag parser
class MetaTagParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta_tags = {}
        self.title = None
        self.in_title = False
        
    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self.in_title = True
        elif tag == 'meta':
            attrs_dict = dict(attrs)
            # og: tags
            if 'property' in attrs_dict and 'content' in attrs_dict:
                self.meta_tags[attrs_dict['property']] = attrs_dict['content']
            # name tags
            if 'name' in attrs_dict and 'content' in attrs_dict:
                self.meta_tags[attrs_dict['name']] = attrs_dict['content']
    
    def handle_data(self, data):
        if self.in_title:
            self.title = data.strip()
            
    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False

# URL'den bilgi çekme
@app.route('/api/fetch-url-info', methods=['POST'])
def fetch_url_info():
    url = request.json.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'URL gerekli'}), 400
    
    # Platform algıla
    platform = detect_platform(url)
    username = extract_username(url, platform)
    
    result = {
        'url': url,
        'platform': platform,
        'title': None,
        'description': None,
        'image_url': None,
        'original_author': username
    }
    
    # Meta tag'leri çekmeye çalış
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')[:50000]  # İlk 50KB
            
            parser = MetaTagParser()
            parser.feed(html)
            
            # Öncelik sırası: og:title > twitter:title > title
            result['title'] = (
                parser.meta_tags.get('og:title') or 
                parser.meta_tags.get('twitter:title') or 
                parser.title or
                'Başlıksız'
            )
            
            result['description'] = (
                parser.meta_tags.get('og:description') or 
                parser.meta_tags.get('twitter:description') or 
                parser.meta_tags.get('description')
            )
            
            result['image_url'] = (
                parser.meta_tags.get('og:image') or 
                parser.meta_tags.get('twitter:image')
            )
            
    except Exception as e:
        # Hata olsa bile platform ve username bilgisini döndür
        result['title'] = 'Başlıksız'
        print(f"URL fetch error: {e}")
    
    return jsonify(result)

# Çoklu URL ekleme
@app.route('/api/bookmarks/bulk-add', methods=['POST'])
def bulk_add_bookmarks():
    urls = request.json.get('urls', [])
    category_id = request.json.get('category_id')
    added_count = 0
    errors = []
    
    for url in urls:
        url = url.strip()
        if not url:
            continue
            
        try:
            platform = detect_platform(url)
            username = extract_username(url, platform)
            
            # Aynı URL zaten var mı kontrol et
            existing = Bookmark.query.filter_by(url=url).first()
            if existing:
                errors.append(f"Zaten mevcut: {url[:50]}...")
                continue
            
            bookmark = Bookmark(
                title=f"{platform.upper()} - {username or 'Gönderi'}" if platform != 'unknown' else url[:100],
                url=url,
                platform=platform if platform != 'unknown' else 'instagram',
                original_author=username,
                category_id=category_id if category_id else None
            )
            db.session.add(bookmark)
            added_count += 1
            
        except Exception as e:
            errors.append(f"Hata: {url[:30]}... - {str(e)}")
    
    db.session.commit()
    
    return jsonify({
        'message': f'{added_count} yer işareti eklendi',
        'added': added_count,
        'errors': errors
    }), 201

# İstatistikler
@app.route('/api/stats', methods=['GET'])
def get_stats():
    total = Bookmark.query.count()
    instagram_count = Bookmark.query.filter_by(platform='instagram').count()
    x_count = Bookmark.query.filter_by(platform='x').count()
    favorites_count = Bookmark.query.filter_by(is_favorite=True).count()
    archived_count = Bookmark.query.filter_by(is_archived=True).count()
    
    return jsonify({
        'total': total,
        'instagram': instagram_count,
        'x': x_count,
        'favorites': favorites_count,
        'archived': archived_count
    })

# ============ INSTAGRAM BOT API ============
import subprocess
import threading

ACCOUNTS_FILE = os.path.join(os.path.dirname(__file__), 'instagram_accounts.json')


def load_instagram_accounts():
    """Instagram bot profillerini yükle."""
    default_data = {
        'selected': 'default',
        'accounts': [
            {
                'id': 'default',
                'name': 'Varsayılan Hesap',
                'profile': 'default'
            }
        ]
    }

    if not os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, indent=2, ensure_ascii=False)
        return default_data

    try:
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or 'accounts' not in data:
            return default_data
        if not data.get('accounts'):
            return default_data
        if not data.get('selected'):
            data['selected'] = data['accounts'][0]['id']
        return data
    except Exception:
        return default_data


def save_instagram_accounts(data):
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def slugify_account_id(name):
    slug = re.sub(r'[^A-Za-z0-9._-]+', '-', (name or '').strip().lower())
    slug = slug.strip('-._')
    return slug or 'hesap'


def get_selected_account(data):
    selected = data.get('selected')
    for account in data.get('accounts', []):
        if account.get('id') == selected:
            return account
    return data.get('accounts', [None])[0]

# Bot durumu
bot_status = {
    'running': False,
    'progress': 0,
    'total': 0,
    'message': '',
    'results': None
}


@app.route('/api/bot/accounts', methods=['GET'])
def get_bot_accounts():
    data = load_instagram_accounts()
    return jsonify(data)


@app.route('/api/bot/accounts', methods=['POST'])
def add_bot_account():
    payload = request.json or {}
    name = (payload.get('name') or '').strip()

    if not name:
        return jsonify({'error': 'Hesap adı gerekli'}), 400

    data = load_instagram_accounts()
    account_id = slugify_account_id(name)

    existing_ids = {a['id'] for a in data['accounts']}
    base_id = account_id
    suffix = 2
    while account_id in existing_ids:
        account_id = f'{base_id}-{suffix}'
        suffix += 1

    account = {
        'id': account_id,
        'name': name,
        'profile': account_id
    }
    data['accounts'].append(account)
    data['selected'] = account_id
    save_instagram_accounts(data)

    return jsonify({
        'message': f'{name} hesabı eklendi',
        'account': account,
        'selected': data['selected']
    }), 201


@app.route('/api/bot/accounts/select', methods=['POST'])
def select_bot_account():
    payload = request.json or {}
    account_id = payload.get('account_id')
    if not account_id:
        return jsonify({'error': 'account_id gerekli'}), 400

    data = load_instagram_accounts()
    account_exists = any(a['id'] == account_id for a in data['accounts'])
    if not account_exists:
        return jsonify({'error': 'Hesap bulunamadı'}), 404

    data['selected'] = account_id
    save_instagram_accounts(data)
    return jsonify({'message': 'Hesap seçildi', 'selected': account_id})


@app.route('/api/bot/accounts/setup-login', methods=['POST'])
def setup_bot_account_login():
    payload = request.json or {}
    account_id = payload.get('account_id')
    if not account_id:
        return jsonify({'error': 'account_id gerekli'}), 400

    data = load_instagram_accounts()
    account = next((a for a in data['accounts'] if a['id'] == account_id), None)
    if not account:
        return jsonify({'error': 'Hesap bulunamadı'}), 404

    base_dir = os.path.dirname(__file__)
    python_exe = sys.executable
    command = (
        f'cd /d "{base_dir}" && '
        f'"{python_exe}" instagram_bot.py --setup-account "{account["profile"]}"'
    )
    subprocess.Popen(
        ['cmd', '/k', command],
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )

    return jsonify({
        'message': f'{account["name"]} için giriş penceresi açıldı',
        'account': account
    })

@app.route('/api/bot/prepare-removal', methods=['POST'])
def prepare_removal():
    """Seçili Instagram yer işaretlerini kaldırmak için hazırla"""
    ids = request.json.get('ids', [])
    
    # Sadece Instagram gönderilerini al
    bookmarks = Bookmark.query.filter(
        Bookmark.id.in_(ids),
        Bookmark.platform == 'instagram'
    ).all()
    
    urls = [b.url for b in bookmarks]
    
    if not urls:
        return jsonify({
            'error': 'Seçili Instagram gönderisi bulunamadı'
        }), 400
    
    # URL'leri JSON dosyasına kaydet
    urls_file = os.path.join(os.path.dirname(__file__), 'pending_removals.json')
    with open(urls_file, 'w', encoding='utf-8') as f:
        json.dump({
            'urls': urls,
            'bookmark_ids': [b.id for b in bookmarks],
            'count': len(urls)
        }, f, indent=2, ensure_ascii=False)
    
    return jsonify({
        'message': f'{len(urls)} Instagram gönderisi kaldırılmaya hazır',
        'count': len(urls),
        'urls': urls[:5],  # İlk 5 tanesini göster
        'file': urls_file
    })

@app.route('/api/bot/start-removal', methods=['POST'])
def start_removal():
    """Instagram bot'unu başlat"""
    global bot_status
    
    if bot_status['running']:
        return jsonify({'error': 'Bot zaten çalışıyor'}), 400
    
    urls_file = os.path.join(os.path.dirname(__file__), 'pending_removals.json')
    
    if not os.path.exists(urls_file):
        return jsonify({'error': 'Önce kaldırılacak gönderileri seçin'}), 400
    
    with open(urls_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    bot_status = {
        'running': True,
        'progress': 0,
        'total': data['count'],
        'message': 'Bot başlatılıyor...',
        'results': None
    }
    
    payload = request.json or {}
    selected_account_override = payload.get('account_id')

    account_data = load_instagram_accounts()
    if selected_account_override:
        if not any(a['id'] == selected_account_override for a in account_data['accounts']):
            return jsonify({'error': 'Seçilen hesap bulunamadı'}), 404
        account_data['selected'] = selected_account_override
        save_instagram_accounts(account_data)

    selected_account = get_selected_account(account_data)
    profile_name = selected_account.get('profile', 'default') if selected_account else 'default'

    # Botu ayrı terminal penceresinde başlat (aktif Python yorumlayıcısını kullan)
    base_dir = os.path.dirname(__file__)
    python_exe = sys.executable
    command = (
        f'cd /d "{base_dir}" && '
        f'"{python_exe}" instagram_bot.py pending_removals.json --profile "{profile_name}" --yes'
    )
    subprocess.Popen(
        ['cmd', '/k', command],
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    
    return jsonify({
        'message': 'Bot başlatıldı! Yeni pencerede Instagram\'a giriş yapın.',
        'account': selected_account,
        'status': bot_status
    })

@app.route('/api/bot/status', methods=['GET'])
def get_bot_status():
    """Bot durumunu kontrol et"""
    global bot_status
    
    # Sonuç dosyasını kontrol et
    result_file = os.path.join(os.path.dirname(__file__), 'removal_result.json')
    if os.path.exists(result_file):
        with open(result_file, 'r', encoding='utf-8') as f:
            bot_status['results'] = json.load(f)
            bot_status['running'] = False
            bot_status['message'] = 'Tamamlandı'
        # Dosyayı sil (bir kere oku)
        os.remove(result_file)
    
    return jsonify(bot_status)

@app.route('/api/bot/mark-removed', methods=['POST'])
def mark_removed():
    """Başarıyla kaldırılan yer işaretlerini işaretle veya sil"""
    ids = request.json.get('ids', [])
    action = request.json.get('action', 'archive')  # 'archive' veya 'delete'
    
    if action == 'delete':
        Bookmark.query.filter(Bookmark.id.in_(ids)).delete(synchronize_session=False)
        message = f'{len(ids)} yer işareti silindi'
    else:
        Bookmark.query.filter(Bookmark.id.in_(ids)).update(
            {Bookmark.is_archived: True, Bookmark.notes: 'Instagram\'dan kaldırıldı'},
            synchronize_session=False
        )
        message = f'{len(ids)} yer işareti arşivlendi'
    
    db.session.commit()
    return jsonify({'message': message})

@app.route('/api/bot/reset', methods=['POST'])
def reset_bot():
    """Bot durumunu sıfırla"""
    global bot_status
    bot_status = {
        'running': False,
        'progress': 0,
        'total': 0,
        'message': 'Sıfırlandı',
        'results': None
    }
    
    # Sonuç dosyasını da temizle
    result_file = os.path.join(os.path.dirname(__file__), 'removal_result.json')
    if os.path.exists(result_file):
        os.remove(result_file)
    
    return jsonify({'message': 'Bot durumu sıfırlandı', 'status': bot_status})

# Veritabanını başlat
def init_db():
    with app.app_context():
        db.create_all()
        
        # Varsayılan kategoriler
        default_categories = [
            {'name': 'Eğitim', 'color': '#3498db'},
            {'name': 'Eğlence', 'color': '#e74c3c'},
            {'name': 'İlham', 'color': '#9b59b6'},
            {'name': 'Teknoloji', 'color': '#2ecc71'},
            {'name': 'Yemek', 'color': '#f39c12'},
            {'name': 'Seyahat', 'color': '#1abc9c'},
            {'name': 'Diğer', 'color': '#95a5a6'},
        ]
        
        for cat in default_categories:
            if not Category.query.filter_by(name=cat['name']).first():
                db.session.add(Category(**cat))
        
        db.session.commit()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
