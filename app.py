from flask import Flask, render_template, redirect, url_for, flash, request, session
import requests
import json
from datetime import datetime
from flask import send_file
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Секретный ключ для сессий

# Фильтр для преобразования UNIX-времени
@app.template_filter('datetimeformat')
def datetimeformat(value):
    try:
        return datetime.utcfromtimestamp(value).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return value


@app.before_request
def check_api_key():
    """
    Проверяем, введён ли API-ключ для всех страниц,
    кроме главной и статических файлов.
    """
    if request.endpoint not in ['home', 'static'] and 'api_key' not in session:
        flash("Сначала введите API-ключ.", "danger")
        return redirect(url_for('home'))


@app.route('/', methods=['GET', 'POST'])
def home():
    """
    Главная страница, где пользователь вводит API-ключ.
    """
    if request.method == 'POST':
        api_key = request.form.get('api_key')
        if api_key:
            session['api_key'] = api_key  # Сохраняем API-ключ в сессии
            flash("Удачная авторизация!", "success")
            return redirect(url_for('menu'))
        else:
            flash("Пожалуйста, введите ваш API-ключ.", "danger")
    return render_template('home.html')


@app.route('/menu')
def menu():
    """
    Главное меню.
    """
    return render_template('menu.html')


@app.route('/buff-search', methods=['GET', 'POST'])
def buff_search():
    """
    Поиск товара на Buff по JSON-данным.
    """
    results = []
    if request.method == 'POST':
        item_name = request.form.get('item_name')
        items = goods_data.get("items", {})
        for item_name_key, item_data in items.items():
            if item_name.lower() in item_name_key.lower():
                goods_id = item_data.get("buff163_goods_id")
                item_info = get_item_info(goods_id)
                results.append({
                    "name": item_name_key,
                    "goods_id": goods_id,
                    "prices": item_info
                })
                break
        else:
            flash(f"Товар '{item_name}' не найден в списке.", "danger")
            return redirect(url_for('menu'))
    return render_template('buff_search.html', results=results)


@app.route('/sales-history', methods=['GET', 'POST'])
def sales_history():
    """
    История продаж.
    """
    sales_data = None
    market_hash_name = None
    if request.method == 'POST':
        market_hash_name = request.form.get('market_hash_name')
        sales_data = get_sales_history(market_hash_name)
    return render_template('sales_history.html', sales_data=sales_data, market_hash_name=market_hash_name)


@app.route('/order-history', methods=['GET'])
def order_history():
    """
    История ордеров.
    """
    page = request.args.get('page', 0, type=int)
    orders = get_order_history(page)
    return render_template('order_history.html', orders=orders, page=page)


@app.route('/bid-ask', methods=['GET', 'POST'])
def bid_ask():
    """
    Стакан bid/ask.
    """
    bid_ask_data = None
    market_hash_name = None
    if request.method == 'POST':
        market_hash_name = request.form.get('market_hash_name')
        bid_ask_data = get_bid_ask(market_hash_name)
    return render_template('bid_ask.html', bid_ask_data=bid_ask_data, market_hash_name=market_hash_name)


def get_item_info(goods_id):
    """Получение информации о товаре с сайта Buff."""
    url = f"https://buff.163.com/api/market/goods/sell_order?game=csgo&goods_id={goods_id}&page_num=1"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if "data" in data and "items" in data["data"]:
            return [
                {
                    "price": item["price"],
                    "link": f"https://buff.163.com/goods/{goods_id}?from=market#tab=selling"
                }
                for item in data["data"]["items"]
            ]
    return None


def get_sales_history(market_hash_name):
    """Получение истории продаж."""
    url = "https://market.csgo.com/api/v2/get-list-items-info"
    params = {
        "key": session['api_key'],  # Используем ключ из сессии
        "list_hash_name[]": market_hash_name
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        try:
            data = response.json()
            return data.get("data", {}).get(market_hash_name, {})  # Проверьте вложенные ключи
        except ValueError:
            return {}
    return {}



def get_order_history(page=0):
    """Получение истории ордеров."""
    url = "https://market.csgo.com/api/v2/get-orders-log"
    params = {
        "key": session['api_key'],  # Используем ключ из сессии
        "page": page
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        try:
            return response.json().get("orders", [])
        except ValueError:
            return []
    return []


def get_bid_ask(market_hash_name):
    """Получение стакана bid/ask."""
    url = "https://market.csgo.com/api/v2/bid-ask"
    params = {
        "key": session['api_key'],  # Используем ключ из сессии
        "hash_name": market_hash_name
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        try:
            data = response.json()
            return {"bid": data.get("bid", []), "ask": data.get("ask", [])}
        except ValueError:
            return {"bid": [], "ask": []}
    return {"bid": [], "ask": []}


def load_goods_from_json(file_path):
    """Загрузка товаров из JSON."""
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


# Путь к JSON-файлу
GOODS_FILE = r"C:\Users\Castle\Desktop\goods_data.json"
goods_data = load_goods_from_json(GOODS_FILE)

@app.route('/set-rates', methods=['GET', 'POST'])
def set_rates():
    """
    Установка курсов валют (USDT/RUB и CNY/USDT).
    """
    if request.method == 'POST':
        usdt_to_rub = request.form.get('usdt_to_rub')
        cny_to_usdt = request.form.get('cny_to_usdt')

        if usdt_to_rub and cny_to_usdt:
            # Сохраняем курсы в сессии или базе данных
            session['usdt_to_rub'] = float(usdt_to_rub)
            session['cny_to_usdt'] = float(cny_to_usdt)

            flash("Курсы успешно обновлены!", "success")
            return redirect(url_for('menu'))
        else:
            flash("Пожалуйста, заполните оба поля.", "danger")

    # Передаём текущие значения курсов (если они есть)
    usdt_to_rub = session.get('usdt_to_rub', '')
    cny_to_usdt = session.get('cny_to_usdt', '')

    return render_template('set_rates.html', usdt_to_rub=usdt_to_rub, cny_to_usdt=cny_to_usdt)

@app.route('/marketcs-search', methods=['GET', 'POST'])
def marketcs_search():
    """
    Поиск товаров на MarketCS по market_hash_name.
    """
    results = []
    if request.method == 'POST':
        market_hash_name = request.form.get('market_hash_name')
        if market_hash_name:
            url = "https://market.csgo.com/api/v2/search-item-by-hash-name"
            params = {
                "key": session.get("api_key", ""),  # Используем API-ключ из сессии
                "hash_name": market_hash_name
            }
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    # Обработка корректных данных из API
                    for item in data.get("data", []):
                        results.append({
                            "market_hash_name": market_hash_name,
                            "price": item.get("price", 0) / 100,  # Цена в API возвращается в копейках
                            "link": f"https://market.csgo.com/item/{item.get('id', '')}"
                        })
                else:
                    flash("Товар не найден или произошла ошибка.", "danger")
            else:
                flash("Не удалось получить данные от API.", "danger")
    return render_template('marketcs_search.html', results=results)


@app.route('/combined-search', methods=['GET', 'POST'])
def combined_search():
    """
    Объединённый поиск по Buff и MarketCS с вводом курсов.
    """
    results = []
    usdt_to_rub = session.get('usdt_to_rub', 75.0)  # Значение по умолчанию
    cny_to_usdt = session.get('cny_to_usdt', 6.5)  # Значение по умолчанию

    if request.method == 'POST':
        # Сохраняем введенные курсы
        usdt_to_rub = float(request.form.get('usdt_to_rub', usdt_to_rub))
        cny_to_usdt = float(request.form.get('cny_to_usdt', cny_to_usdt))
        session['usdt_to_rub'] = usdt_to_rub
        session['cny_to_usdt'] = cny_to_usdt

        # Получаем название товара
        item_name = request.form.get('item_name')

        # Поиск по Buff
        buff_results = []
        items = goods_data.get("items", {})
        for item_name_key, item_data in items.items():
            if item_name.lower() in item_name_key.lower():
                goods_id = item_data.get("buff163_goods_id")
                item_info = get_item_info(goods_id)
                for info in item_info:
                    buff_results.append({
                        "description": item_name_key,
                        "buff_price": float(info["price"])
                    })
                break

        # Поиск по MarketCS
        market_results = []
        url = "https://market.csgo.com/api/v2/search-item-by-hash-name"
        params = {
            "key": session.get("api_key", ""),
            "hash_name": item_name
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                for item in data.get("data", []):
                    market_results.append({
                        "description": item_name,
                        "market_price": item.get("price", 0) / 100  # Цена в рублях
                    })

        # Объединяем результаты Buff и MarketCS
        for buff in buff_results:
            matching_market = next((m for m in market_results if m["description"] == buff["description"]), None)
            if matching_market:
                results.append({
                    "description": buff["description"],
                    "buff_price": buff["buff_price"],
                    "market_price": matching_market["market_price"]
                })

        session['combined_results'] = results  # Сохраняем результаты для выгрузки

    return render_template('combined_search.html', results=results, usdt_to_rub=usdt_to_rub, cny_to_usdt=cny_to_usdt)


@app.route('/export-to-excel', methods=['POST'])
def export_to_excel():
    """
    Выгрузка объединённых данных в Excel.
    """
    combined_results = session.get('combined_results', [])

    if not combined_results:
        flash("Нет данных для экспорта.", "danger")
        return redirect(url_for('combined_search'))

    # Создание DataFrame и экспорт в Excel
    df = pd.DataFrame(combined_results)
    file_path = "/tmp/combined_results.xlsx"
    df.to_excel(file_path, index=False)

    return send_file(file_path, as_attachment=True, download_name="combined_results.xlsx")

@app.route('/export-to-google-sheet', methods=['POST'])
def export_to_google_sheet():
    """
    Выгрузка первой строки объединённых данных в Google Таблицу с новым расчётом.
    """
    combined_results = session.get('combined_results', [])
    if not combined_results:
        flash("Нет данных для экспорта.", "danger")
        return redirect(url_for('combined_search'))

    # Получаем первую строку данных
    first_result = combined_results[0]

    # Получаем курсы из формы
    try:
        usdt_to_rub = float(request.form.get('usdt_to_rub', 75.0))
        cny_to_usdt = float(request.form.get('cny_to_usdt', 6.5))
    except ValueError:
        flash("Неверные значения курсов валют.", "danger")
        return redirect(url_for('combined_search'))

    # Расчёты
    try:
        buff_price = first_result["buff_price"]
        market_price = first_result["market_price"]
        description = first_result["description"]

        # Цена DM после комиссии (5%)
        priceDMAdjusted = market_price * 0.95

        # Перевод цены Buff в рубли
        calculation = (buff_price / cny_to_usdt) * usdt_to_rub

        # Профит (RUB)
        result = priceDMAdjusted - calculation
        newResult = result * 0.95

        # Профит (%)
        percentageOfCalculation = (newResult / calculation) * 100 if calculation else 0
    except Exception as e:
        flash(f"Ошибка при расчёте данных: {e}", "danger")
        return redirect(url_for('combined_search'))

    # URL вашей Google Таблицы
    sheet_url = "https://docs.google.com/spreadsheets/d/1ORqmR_om7tPQKd2GKPJZdQS35_5aZxE5sXdO1VjioeU/edit"

    try:
        # Подключение к Google Sheets
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        credentials = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(credentials)

        # Открытие таблицы
        sheet = client.open_by_url(sheet_url).sheet1

        # Если таблица пуста, записываем заголовки
        if sheet.row_count == 0:
            headers = ["Цена Buff (CNY)", "Цена DM (RUB)", "курс usdt/rub (RUB)", "курс cny/usdt (CNY)", "Профит (RUB)", "Профит %", "Description"]
            sheet.append_row(headers)

        # Запись первой строки данных
        sheet.append_row([
            round(buff_price, 2),                 # Цена Buff (CNY)
            round(market_price, 2),              # Цена DM (RUB)
            round(usdt_to_rub, 2),               # Курс USDT к RUB
            round(cny_to_usdt, 2),               # Курс CNY к USDT
            round(newResult, 2),                 # Профит (RUB)
            round(percentageOfCalculation, 2),   # Профит (%)
            description                          # Название
        ])

        flash("Первая строка успешно добавлена в Google Таблицу.", "success")
    except Exception as e:
        flash(f"Ошибка при экспорте данных: {e}", "danger")

    return redirect(url_for('combined_search'))





if __name__ == '__main__':
    app.run(debug=True)
