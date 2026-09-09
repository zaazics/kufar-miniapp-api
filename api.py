import json
import asyncio
import os
import re
from datetime import datetime

from aiohttp import web, ClientTimeout, ClientSession, TCPConnector
from bs4 import BeautifulSoup

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1",
    "Referer": "https://www.kufar.by/"
}

CATEGORIES = {
    "phones": {
        "name": "📱 Телефоны",
        "url": "https://www.kufar.by/l/mobilnye-telefony",
        "keywords": ["iPhone", "Samsung", "Xiaomi", "Pixel", "OnePlus", "Honor", "Huawei"]
    },
    "consoles": {
        "name": "🎮 Игровые приставки",
        "url": "https://www.kufar.by/l/igrovye-pristavki-i-aksessuary",
        "keywords": ["PlayStation", "PS4", "PS5", "Xbox", "Nintendo", "Switch"]
    },
    "gpu": {
        "name": "🖥 Видеокарты",
        "url": "https://www.kufar.by/l/videokarty",
        "keywords": ["RTX", "GTX", "Radeon", "видеокарта", "GPU"]
    },
    "cpu": {
        "name": "⚡ Процессоры",
        "url": "https://www.kufar.by/l/processory",
        "keywords": ["Intel", "AMD", "Core", "Ryzen"]
    },
    "laptops": {
        "name": "💻 Ноутбуки",
        "url": "https://www.kufar.by/l/noutbuki",
        "keywords": ["ноутбук", "MacBook", "Acer", "ASUS", "Lenovo", "HP", "Dell"]
    },
    "monitors": {
        "name": "🖥 Мониторы",
        "url": "https://www.kufar.by/l/monitory",
        "keywords": ["монитор", "4K", "144Hz", "IPS", "OLED"]
    }
}


# ============================================================
# ПАРСИНГ (без lxml)
# ============================================================

async def fetch_page(url: str) -> str | None:
    try:
        timeout = ClientTimeout(total=15)
        connector = TCPConnector(ssl=False)
        async with ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(url, headers=HEADERS) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    print(f"❌ HTTP ошибка: {response.status}")
                    return None
    except Exception as e:
        print(f"⚠️ Ошибка fetcher: {e}")
        return None


def extract_ads(html: str, category: str = None) -> list:
    # Используем html.parser вместо lxml
    soup = BeautifulSoup(html, "html.parser")
    ads = []
    
    cards_container = soup.find('div', class_='styles_cards___qpff')
    if not cards_container:
        return []
    
    cards = cards_container.find_all('section')
    
    keywords = CATEGORIES.get(category, {}).get('keywords', []) if category else []
    
    for card in cards:
        try:
            link_tag = card.find('a', class_='styles_wrapper__yaLfq')
            if not link_tag:
                continue
            
            url = link_tag.get('href')
            if url and url.startswith('/'):
                url = f"https://www.kufar.by{url}"
            
            title_tag = card.find('h3', class_='styles_title__ARIVF')
            title = title_tag.text.strip() if title_tag else "Без названия"
            
            if keywords and not any(k.lower() in title.lower() for k in keywords):
                continue
            
            price_tag = card.find('p', class_='styles_price__9JZaB')
            if price_tag:
                price_span = price_tag.find('span')
                price = price_span.text.strip() if price_span else price_tag.text.strip()
            else:
                price = "Цена не указана"
            
            city_tag = card.find('div', class_='styles_secondary__NEYhw')
            city = "Город не указан"
            if city_tag:
                city_p = city_tag.find('p')
                if city_p:
                    city = city_p.text.strip()
            
            time_tag = card.find('time')
            time_published = time_tag.text.strip() if time_tag else "Не указано"
            
            price_value = None
            price_clean = re.sub(r'[^\d]', '', price) if price else ''
            if price_clean:
                try:
                    price_value = int(price_clean)
                except:
                    pass
            
            ad = {
                "title": title,
                "price": price,
                "price_value": price_value,
                "city": city,
                "time": time_published,
                "url": url
            }
            ads.append(ad)
            
        except Exception as e:
            print(f"⚠️ Ошибка парсинга: {e}")
            continue
    
    return ads


def calculate_average_price(ads: list) -> float:
    prices = [a['price_value'] for a in ads if a.get('price_value')]
    if len(prices) < 3:
        return sum(prices) / len(prices) if prices else 0
    
    prices.sort()
    cut = int(len(prices) * 0.15)
    if cut > 0:
        prices = prices[cut:-cut]
    
    return sum(prices) / len(prices) if prices else 0


def analyze_prices(ads: list) -> dict:
    if not ads:
        return {"ads": [], "avg_price": 0, "best_deal": None}
    
    avg_price = calculate_average_price(ads)
    best_deal = None
    
    for ad in ads:
        if ad.get('price_value') and avg_price:
            diff = avg_price - ad['price_value']
            if diff > avg_price * 0.15:
                if not best_deal or diff > (best_deal.get('savings', 0)):
                    best_deal = {
                        **ad,
                        "savings": diff,
                        "savings_percent": round((diff / avg_price) * 100, 1)
                    }
    
    return {
        "ads": ads,
        "avg_price": round(avg_price, 2),
        "best_deal": best_deal
    }


def filter_by_price(ads: list, price_filter: str) -> list:
    if price_filter == 'all':
        return ads
    
    ranges = {
        '0-100': (0, 100),
        '100-300': (100, 300),
        '300-500': (300, 500),
        '500-1000': (500, 1000),
        '1000+': (1000, float('inf'))
    }
    
    min_price, max_price = ranges.get(price_filter, (0, float('inf')))
    return [a for a in ads if a.get('price_value') and min_price <= a['price_value'] <= max_price]


def filter_by_city(ads: list, city_filter: str) -> list:
    if city_filter == 'all':
        return ads
    
    city_map = {
        'minsk': 'Минск',
        'gomel': 'Гомель',
        'mogilev': 'Могилев',
        'vitebsk': 'Витебск',
        'grodno': 'Гродно',
        'brest': 'Брест'
    }
    
    city_name = city_map.get(city_filter, '')
    if not city_name:
        return ads
    
    return [a for a in ads if city_name.lower() in a.get('city', '').lower()]


# ============================================================
# ХРАНИЛИЩЕ
# ============================================================

favorites = {}

def add_favorite(user_id: int, ad: dict):
    if user_id not in favorites:
        favorites[user_id] = []
    if not any(f['url'] == ad['url'] for f in favorites[user_id]):
        favorites[user_id].append(ad)
    return favorites[user_id]

def remove_favorite(user_id: int, url: str):
    if user_id in favorites:
        favorites[user_id] = [f for f in favorites[user_id] if f['url'] != url]
    return favorites.get(user_id, [])

def get_favorites(user_id: int) -> list:
    return favorites.get(user_id, [])


# ============================================================
# API
# ============================================================

async def handle_api(request):
    try:
        if request.method == 'GET':
            return await handle_get(request)
        elif request.method == 'POST':
            return await handle_post(request)
        return web.json_response({"error": "Метод не поддерживается"}, status=405)
    except Exception as e:
        print(f"❌ Ошибка API: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_get(request):
    params = request.query
    action = params.get('action')
    
    if action == 'get_ads':
        return await get_ads_handler(params)
    elif action == 'get_favorites':
        return await get_favorites_handler(params)
    elif action == 'get_categories':
        return await get_categories_handler()
    elif action == 'health':
        return web.json_response({"status": "OK", "timestamp": datetime.now().isoformat()})
    
    return web.json_response({"error": "Неизвестное действие"})


async def handle_post(request):
    data = await request.json()
    action = data.get('action')
    
    if action == 'save_ad':
        return await save_ad_handler(data)
    elif action == 'remove_favorite':
        return await remove_favorite_handler(data)
    
    return web.json_response({"error": "Неизвестное действие"})


async def get_ads_handler(params):
    category = params.get('category', 'phones')
    page = int(params.get('page', 1))
    search = params.get('search', '').strip()
    price_filter = params.get('price', 'all')
    city_filter = params.get('city', 'all')
    user_id = params.get('user_id')
    
    category_data = CATEGORIES.get(category)
    if not category_data:
        return web.json_response({"error": "Категория не найдена"})
    
    url = f"{category_data['url']}?sort=lst.d"
    
    html = await fetch_page(url)
    if not html:
        return web.json_response({"error": "Не удалось загрузить страницу"})
    
    ads = extract_ads(html, category)
    
    if search:
        ads = [a for a in ads if search.lower() in a.get('title', '').lower()]
    
    ads = filter_by_city(ads, city_filter)
    ads = filter_by_price(ads, price_filter)
    
    analysis = analyze_prices(ads)
    avg_price = analysis['avg_price']
    best_deal = analysis['best_deal']
    
    for ad in ads:
        ad['is_best'] = best_deal and ad.get('url') == best_deal.get('url')
        if avg_price and ad.get('price_value'):
            diff = avg_price - ad['price_value']
            if diff > 0:
                ad['savings'] = round(diff, 2)
                ad['savings_percent'] = round((diff / avg_price) * 100, 1)
    
    if user_id:
        favs = get_favorites(int(user_id))
        fav_urls = [f['url'] for f in favs]
        for ad in ads:
            ad['is_favorite'] = ad.get('url') in fav_urls
    
    ads_per_page = 5
    total = len(ads)
    total_pages = max(1, (total + ads_per_page - 1) // ads_per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * ads_per_page
    end = min(start + ads_per_page, total)
    
    return web.json_response({
        "ads": ads[start:end],
        "total": total,
        "page": page,
        "totalPages": total_pages,
        "avg_price": avg_price,
        "best_deal": best_deal
    })


async def get_favorites_handler(params):
    user_id = params.get('user_id')
    if not user_id:
        return web.json_response({"favorites": []})
    return web.json_response({"favorites": get_favorites(int(user_id))})


async def get_categories_handler():
    categories = [{"key": key, "name": cat['name']} for key, cat in CATEGORIES.items()]
    return web.json_response({"categories": categories})


async def save_ad_handler(data):
    user_id = data.get('user_id')
    if not user_id:
        return web.json_response({"error": "Не указан пользователь"})
    
    ad = {
        "url": data.get('url', ''),
        "title": data.get('title', ''),
        "price": data.get('price', ''),
        "city": data.get('city', ''),
        "saved_at": datetime.now().isoformat()
    }
    
    add_favorite(int(user_id), ad)
    return web.json_response({"message": "✅ Сохранено в избранное!", "favorites": get_favorites(int(user_id))})


async def remove_favorite_handler(data):
    user_id = data.get('user_id')
    url = data.get('url')
    
    if not user_id or not url:
        return web.json_response({"error": "Недостаточно данных"})
    
    remove_favorite(int(user_id), url)
    return web.json_response({"message": "🗑 Удалено из избранного", "favorites": get_favorites(int(user_id))})


# ============================================================
# ЗАПУСК
# ============================================================

async def health_check(request):
    return web.json_response({"status": "OK", "service": "kufar-miniapp-api"})


async def start_api_server():
    app = web.Application()
    app.router.add_get('/api', handle_api)
    app.router.add_post('/api', handle_api)
    app.router.add_get('/health', health_check)
    app.router.add_get('/', health_check)
    
    # CORS
    async def cors_middleware(app, handler):
        async def middleware(request):
            response = await handler(request)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            return response
        return middleware
    
    app.middlewares.append(cors_middleware)
    
    port = int(os.environ.get('PORT', 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"✅ API сервер запущен на порту {port}")
    print(f"📍 Health check: http://localhost:{port}/health")
    print(f"📍 API: http://localhost:{port}/api")
    
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(start_api_server())
    except KeyboardInterrupt:
        print("👋 Сервер остановлен")
