import os
import json
import time
import re
from datetime import datetime, timedelta
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# --- 共通セットアップ ---
def setup_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    # ボット検知を回避するための追加オプション
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # navigator.webdriver を false に上書きして自動操作であることを隠す
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver

def get_detail_info(driver, url):
    """詳細ページから会場と時間を抽出する"""
    venue = "詳細を確認"
    time_info = " "
    try:
        driver.get(url)
        time.sleep(3) # 読み込みを3秒確実に待機（安定化）
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # 1. 構造化データの抽出 (JSON-LD)
        json_ld = soup.find('script', type='application/ld+json')
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                if isinstance(data, dict):
                    if 'location' in data and 'name' in data['location']:
                        venue = data['location']['name']
                    if 'startDate' in data:
                        dt = datetime.fromisoformat(data['startDate'].replace('Z', '+00:00'))
                        time_info = dt.strftime('%H:%M~')
            except Exception:
                pass

        # 2. フォールバック
        if venue == "詳細を確認" or time_info == " ":
            table = soup.find('table')
            if table:
                for row in table.find_all('tr'):
                    th = row.find('th')
                    td = row.find('td')
                    if th and td:
                        th_text = th.get_text(strip=True)
                        td_text = td.get_text(strip=True)
                        if "会場" in th_text:
                            venue = td_text
                        elif "時間" in th_text or "開場" in th_text:
                            time_info = td_text
    except Exception as e:
        print(f"詳細ページの取得失敗: {url} -> {e}")
    
    return venue, time_info

# --- 各グループのスクレイピングロジック ---
def scrape_chumtoto(driver):
    """ちゃむととのスケジュールスクレイピング"""
    events = []
    base_url = "https://chumtoto.jp/schedule/"
    print("ちゃむととのスケジュールを取得中...")
    try:
        driver.get(base_url)
        time.sleep(4) # カレンダー展開まで4秒確実に待つ
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        calendar_days = soup.find_all('div', class_='full-calendar-day')
        
        for day_div in calendar_days:
            date_class = day_div.get('class', [])
            date_str = None
            for c in date_class:
                if re.match(r'^\d{4}-\d{2}-\d{2}$', c):
                    date_str = c
                    break
            
            if not date_str:
                continue
                
            event_items = day_div.find_all('div', class_='full-calendar-item')
            for item in event_items:
                link_tag = item.find('a')
                if link_tag:
                    title = link_tag.get_text(strip=True)
                    url = link_tag.get('href')
                    
                    if any(e['title'] == title and e['start'] == date_str for e in events):
                        continue
                        
                    events.append({
                        "title": f"【ちゃむ】{title}",
                        "start": date_str,
                        "url": url,
                        "group": "ChumToto"
                    })
    except Exception as e:
        print(f"ちゃむととの取得エラー: {e}")
    return events

def scrape_kyurushite(driver, group_name, base_url):
    """きゅるして / にじコン 等の共通系スケジュールスクレイピング"""
    events = []
    print(f"{group_name} のスケジュールを取得中...")
    try:
        driver.get(base_url)
        time.sleep(4) # 4秒確実に待つ
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        calendar_days = soup.find_all('div', class_='full-calendar-day')
        
        for day_div in calendar_days:
            date_class = day_div.get('class', [])
            date_str = None
            for c in date_class:
                if re.match(r'^\d{4}-\d{2}-\d{2}$', c):
                    date_str = c
                    break
            
            if not date_str:
                continue
                
            event_items = day_div.find_all('div', class_='full-calendar-item')
            for item in event_items:
                link_tag = item.find('a')
                if link_tag:
                    title = link_tag.get_text(strip=True)
                    url = link_tag.get('href')
                    events.append({
                        "title": f"【{group_name}】{title}",
                        "start": date_str,
                        "url": url,
                        "group": group_name
                    })
    except Exception as e:
        print(f"{group_name} の取得エラー: {e}")
    return events

def scrape_2zicon(driver):
    """虹コンのスケジュールスクレイピング"""
    return scrape_kyurushite(driver, "虹コン", "https://2zicon.tokyo/schedule/")

def scrape_dspm(driver, group_name, domain, path):
    """DSPM系（さよステ / meme）のスケジュールスクレイピング"""
    events = []
    print(f"{group_name} のスケジュールを取得中...")
    try:
        driver.get(domain + path)
        time.sleep(4)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        if "vertical_calendar" in path:
            items = soup.find_all('div', class_='event-item')
        else:
            links = soup.find_all('a', href=re.compile(r'/schedules/\d+'))
            for link in links:
                title_elem = link.find(class_='title')
                date_elem = link.find(class_='date')
                if title_elem and date_elem:
                    title = title_elem.get_text(strip=True)
                    date_raw = date_elem.get_text(strip=True)
                    date_match = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', date_raw)
                    if date_match:
                        date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                        events.append({
                            "title": f"【{group_name}】{title}",
                            "start": date_str,
                            "url": domain + link.get('href'),
                            "group": group_name
                        })
    except Exception as e:
        print(f"{group_name} の取得エラー: {e}")
    return events


# --- メイン実行処理 ---
if __name__ == "__main__":
    driver = setup_driver()
    all_data = []

    # 順次スクレイピングを開始
    all_data.extend(scrape_chumtoto(driver))
    all_data.extend(scrape_kyurushite(driver, "きゅるして", "https://www.kyurushite.com/schedule/"))
    all_data.extend(scrape_2zicon(driver))
    all_data.extend(scrape_dspm(driver, "さよステ", "https://sayostay.dspm.jp", "/schedules/menu/18610"))
    all_data.extend(scrape_dspm(driver, "meme", "https://www.memetokyo.com", "/vertical_calendar"))
    
    # 1. 重複排除
    unique_events = list({(ev['title'], ev['start']): ev for ev in all_data}.values())
    print(f"総イベント数: {len(unique_events)} 件を取得しました。詳細情報を解析中...")

    # 2. 各イベントの詳細ページにアクセスして会場・時間を取得
    for ev in unique_events:
        if ev.get('url'):
            print(f"詳細解析中: {ev['title']}")
            venue, time_info = get_detail_info(driver, ev['url'])
            ev['venue'] = venue
            ev['time_info'] = time_info
        else:
            ev['venue'] = "詳細を確認"
            ev['time_info'] = ""

    driver.quit()

    # 3. ローカルの履歴管理データ(data.json)の更新処理
    old_data_dict = {}
    if os.path.exists('data.json'):
        try:
            with open('data.json', 'r', encoding='utf-8') as f:
                old_list = json.load(f)
                old_data_dict = {(ev['title'], ev['start']): ev.get('added_at') for ev in old_list}
        except Exception as e:
            print(f"前回のデータ読み込みに失敗しました: {e}")

    current_now = datetime.now().isoformat()

    for ev in unique_events:
        key = (ev['title'], ev['start'])
        if key in old_data_dict:
            ev['added_at'] = old_data_dict[key]
        else:
            ev['added_at'] = current_now

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(unique_events, f, ensure_ascii=False, indent=4)
    print("ローカルの data.json を更新しました。")


    # 4. 【追加機能】ChumTotoのデータのみ新しいスプシに同期
    chumtoto_only = [ev for ev in unique_events if ev.get('group') == 'ChumToto']

    formatted_events = []
    for ev in chumtoto_only:
        date_str = ev['start'].split('T')[0] if 'T' in ev['start'] else ev['start']
        formatted_events.append({
            "date": date_str,
            "title": ev['title'].replace('【ちゃむ】', ''),
            "venue": ev.get('venue', '詳細を確認'),
            "time": ev.get('time_info', ''),
            "url": ev.get('url', '')
        })

    GAS_URL = "https://script.google.com/macros/s/AKfycbxTpsaay81w4DDRfjfui7pfmnlc4aDaOPJx_fy4Shf275gpnyUZ9R-ObhAWQOMVOwyP/exec"

    payload = {
        "action": "sync_schedule",
        "events": formatted_events
    }

    print(f"GoogleスプレッドシートへChumTotoの公式スケジュール（計 {len(formatted_events)} 件）を同期中...")
    try:
        response = requests.post(GAS_URL, json=payload, headers={'Content-Type': 'text/plain'})
        print("スプシ同期結果:", response.text)
    except Exception as e:
        print(f"スプレッドシートへのデータ送信中にエラーが発生しました: {e}")

    print("すべての工程が正常に終了しました！")
