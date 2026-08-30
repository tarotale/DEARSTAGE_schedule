import os
import json
import time
import re
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# --- Google Calendar API 用モジュール ---
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ==========================================
# Google カレンダー連携設定
# ==========================================
SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'credentials.json')
CALENDAR_ID = 'chumtoto.calendar@gmail.com'
TARGET_GROUPS = ["[ChumToto]", "[さよステ]"]


def get_calendar_service():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('calendar', 'v3', credentials=creds)


def sync_selected_events_to_gcal(events):
    target_events = [
        ev for ev in events 
        if any(ev['title'].startswith(prefix) for prefix in TARGET_GROUPS)
    ]
    
    if not target_events:
        print("[Google Calendar] 対象となるイベント（ChumToto / さよステ）はありませんでした。")
        return

    print(f"[Google Calendar] 同期対象イベント: {len(target_events)} 件")
    
    try:
        service = get_calendar_service()
    except Exception as e:
        print(f"[Google Calendar] API認証エラー: {e}")
        return

    now = datetime.utcnow()
    time_min = (now - timedelta(days=30)).isoformat() + 'Z'
    
    try:
        existing_events_res = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            singleEvents=True
        ).execute()
        existing_events = existing_events_res.get('items', [])
    except Exception as e:
        print(f"[Google Calendar] 既存イベント取得エラー: {e}")
        return

    existing_keys = set()
    for item in existing_events:
        start_date = item.get('start', {}).get('date') or item.get('start', {}).get('dateTime', '')[:10]
        existing_keys.add((item.get('summary'), start_date))

    added_count = 0
    for ev in target_events:
        key = (ev['title'], ev['start'])
        if key in existing_keys:
            continue

        description_lines = []
        if ev.get('venue'): description_lines.append(f"会場: {ev['venue']}")
        if ev.get('time'):  description_lines.append(f"時間: {ev['time']}")
        if ev.get('url'):   description_lines.append(f"詳細URL: {ev['url']}")
        
        description_text = "\n".join(description_lines)

        event_body = {
            'summary': ev['title'],
            'location': ev.get('venue', ''),
            'description': description_text,
            'start': {'date': ev['start']},
            'end': {'date': ev['start']},
        }

        try:
            service.events().insert(calendarId=CALENDAR_ID, body=event_body).execute()
            print(f"[Google Calendar] 登録完了: {ev['title']} ({ev['start']})")
            added_count += 1
            time.sleep(0.5)
        except Exception as e:
            print(f"[Google Calendar] 登録失敗 ({ev['title']}): {e}")

    print(f"[Google Calendar] 同期完了: {added_count} 件の新規予定を追加しました。")


def setup_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    try:
        driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": "Asia/Tokyo"})
    except Exception:
        pass
    return driver


def get_detail_info(driver, url):
    """詳細ページから会場、時間、および日付を抽出する"""
    venue = "詳細を確認"
    time_info = ""
    exact_date = None

    try:
        driver.get(url)
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # 1. 構造化タグ優先
        v_el = soup.select_one('.p-clubScheduleArticle__place__text span, .p-clubScheduleDetail__venue, .tribe-events-pro-venue__name, .tribe-venue')
        t_el = soup.select_one('.p-clubScheduleArticle__description__item, .p-clubScheduleDetail__time, .tribe-events-pro-full-date, .tribe-events-schedule')
        if v_el: venue = v_el.get_text(strip=True)
        if t_el: time_info = t_el.get_text(strip=True)
        
        # 2. 本文テキスト解析
        content = soup.select_one('.common__article, .article__content, .body, .c-clubWysiwyg, .tribe-events-single-event-description, .p-clubScheduleArticle__description')
        
        if content:
            # パターンA: 見出しと内容が分かれている場合
            for tag in content.find_all(['h4', 'strong']):
                label = tag.get_text(strip=True)
                data = ""
                if tag.next_sibling and isinstance(tag.next_sibling, str):
                    data = tag.next_sibling.strip()
                if not data or data in ["：", ":"]:
                    next_el = tag.find_next(['p', 'span'])
                    if next_el: data = next_el.get_text(strip=True)

                if "時間" in label or "公演時間" in label:
                    time_info = data.replace("：", "").replace(":", "").strip()
                elif ("日時" in label) and not time_info:
                    time_info = data.replace("：", "").replace(":", "").strip()
                elif "場所" in label or "会場" in label:
                    venue = data.replace("：", "").replace(":", "").strip()

            # パターンB: 改行区切りのテキスト解析
            if venue == "詳細を確認" or not time_info:
                lines = [line.strip() for line in content.get_text("\n").split("\n") if line.strip()]
                for line in lines:
                    if any(k in line for k in ["■場所", "■会場", "会場：", "会場:", "場所：", "場所:"]):
                        res = re.sub(r'^(■場所|■会場|会場|場所)[：:]\s*', '', line).strip()
                        if res: venue = res
                    if any(k in line for k in ["■時間", "時間：", "時間:", "公演時間"]):
                        res = re.sub(r'^(■時間|公演時間|時間)[：:]\s*', '', line).strip()
                        if res: time_info = res

        # 3. 日付の精密抽出（日付ズレ防止用のフォールバック）
        full_text = soup.get_text()
        d_match = re.search(r'(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})', full_text)
        if d_match:
            exact_date = f"{d_match.group(1)}-{int(d_match.group(2)):02d}-{int(d_match.group(3)):02d}"

        if not time_info:
            dt_el = soup.select_one('.p-clubScheduleArticle__dateTime span, .article__date')
            if dt_el: 
                time_info = re.sub(r'^\d{4}[/.]\d{2}[/.]\d{2}\(.\)\s*', '', dt_el.get_text(strip=True))

    except Exception as e:
        print(f"Detail parse warning at {url}: {e}")
    
    return venue, time_info, exact_date


def scrape_tribe_v2(driver, group_name, url):
    """提示された確実版ロジックをトレースした共通スクレイピング関数（ChumToto・きゅるして対応）"""
    events = []
    current_url = url
    while current_url:
        try:
            print(f"{group_name} 取得中: {current_url}")
            driver.get(current_url)
            time.sleep(8)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            days = soup.select('.tribe-events-calendar-month__day')
            links_to_crawl = []
            
            for day in days:
                time_tag = day.select_one('time.tribe-events-calendar-month__day-date-daynum')
                if not time_tag or not time_tag.has_attr('datetime'): continue
                date_str = time_tag['datetime']
                event_links = day.select('a.tribe-events-calendar-month__multiday-event-hidden-link, a.tribe-events-calendar-month__calendar-event-title-link')
                
                for link in event_links:
                    href = link.get('href')
                    title_el = link.select_one('h3') or link
                    title = title_el.get_text(strip=True)
                    if title and href:
                        links_to_crawl.append({"title": title, "url": href, "date": date_str})
            
            for item in links_to_crawl:
                v, tm, exact_date = get_detail_info(driver, item['url'])
                
                clean_title = (
                    item['title']
                    .replace('【ちゃむ】', '')
                    .replace('[ChumToto]', '')
                    .replace('【きゅるして】', '')
                    .replace('[きゅるして]', '')
                    .strip()
                )
                final_date = exact_date or item['date']

                events.append({
                    "group": group_name,
                    "date": final_date,
                    "start": final_date,
                    "title": f"[{group_name}] {clean_title}",
                    "clean_title": clean_title,
                    "venue": v,
                    "time": tm,
                    "url": item['url'],
                    "allDay": True
                })
                
            next_link = soup.select_one('a.tribe-events-c-top-bar__nav-link--next, a.tribe-common-c-btn-icon--caret-right')
            current_url = next_link.get('href') if next_link and next_link.has_attr('href') else None
        except Exception as e:
            print(f"{group_name} 一覧取得エラー: {e}")
            break
            
    return events


def scrape_2zicon(driver):
    """虹コン：当月全ページ + 先12ヶ月巡回"""
    name = "虹コン"
    base_url = "https://2zicon.tokyo"
    events = []
    now = datetime.now()
    current_url = f"{base_url}/information/schedule/"
    while current_url:
        try:
            driver.get(current_url)
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            for it in soup.select('.info__item'):
                link = it.select_one('a.info__link')
                text_el = it.select_one('.info__text')
                d_el = it.select_one('.info__date')
                if not link or not text_el or not d_el: continue
                title = text_el.get_text(strip=True)
                f_url = base_url + link.get('href') if link.get('href').startswith('/') else link.get('href')
                d_match = re.search(r'\d{4}-\d{2}-\d{2}', d_el.get_text(strip=True).replace('.', '-'))
                if d_match:
                    v, tm, exact_date = get_detail_info(driver, f_url)
                    final_date = exact_date or d_match.group()
                    events.append({
                        "group": name,
                        "date": final_date,
                        "start": final_date,
                        "title": f"[{name}] {title}",
                        "venue": v,
                        "time": tm,
                        "url": f_url,
                        "allDay": True
                    })
            next_btn = soup.select_one('a.pagi__btn--next')
            current_url = (base_url + next_btn.get('href')) if next_btn and next_btn.has_attr('href') else None
        except: break

    for i in range(1, 13):
        target = now + timedelta(days=31 * i)
        cal_url = f"{base_url}/information/schedule?getYear={target.year}&getMonth={target.month}"
        try:
            driver.get(cal_url)
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            for it in soup.select('.info__item'):
                link, text_el, d_el = it.select_one('a.info__link'), it.select_one('.info__text'), it.select_one('.info__date')
                if not link or not text_el or not d_el: continue
                title = text_el.get_text(strip=True)
                f_url = base_url + link.get('href') if link.get('href').startswith('/') else link.get('href')
                d_match = re.search(r'\d{4}-\d{2}-\d{2}', d_el.get_text(strip=True).replace('.', '-'))
                if d_match:
                    v, tm, exact_date = get_detail_info(driver, f_url)
                    final_date = exact_date or d_match.group()
                    events.append({
                        "group": name,
                        "date": final_date,
                        "start": final_date,
                        "title": f"[{name}] {title}",
                        "venue": v,
                        "time": tm,
                        "url": f_url,
                        "allDay": True
                    })
        except: continue
    return events


def scrape_dspm(driver, name, base_url, menu_path):
    """さよステ / meme：日付ズレ補正対応"""
    events = []
    now = datetime.now()
    for i in range(0, 13):
        target = now + timedelta(days=31 * i)
        t_m = f"{target.year}-{str(target.month).zfill(2)}"
        u = f"{base_url}{menu_path}?start={t_m}-01" if "schedules" in menu_path else f"{base_url}{menu_path}/{target.year}/{target.month}"
        try:
            driver.get(u)
            time.sleep(5)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            items = []
            
            if "vertical_calendar" in menu_path: # meme
                for li in soup.select('li.list-group-item'):
                    t_tag, inner = li.select_one('time'), li.select_one('.fc-event-inner')
                    if not t_tag or not inner: continue
                    title = inner.get_text(strip=True)
                    dm = re.findall(r'\d+', t_tag.get_text())
                    if len(dm)<3: continue
                    ds = f"{dm[0]}-{int(dm[1]):02d}-{int(dm[2]):02d}"
                    for a in li.select('a.tag-event, a.tag-live'):
                        items.append({"url": base_url + a.get('href'), "date": ds, "title": title})
            else: # sayostay
                for td in soup.select('td.fc-daygrid-day'):
                    ds = td.get('data-date')
                    if not ds or not ds.startswith(t_m): continue
                    for a in td.select('a.fc-daygrid-event'):
                        t_el = a.select_one('.fc-event-title')
                        items.append({"url": base_url + a.get('href'), "date": ds, "title": t_el.get_text(strip=True) if t_el else ""})
            
            for it in items:
                v, tm, exact_date = get_detail_info(driver, it['url'])
                final_start = exact_date if exact_date else it['date']
                events.append({
                    "group": name,
                    "date": final_start,
                    "start": final_start,
                    "title": f"[{name}] {it['title']}", 
                    "venue": v, 
                    "time": tm, 
                    "url": it['url'], 
                    "allDay": True
                })
        except Exception as e:
            print(f"Scrape dspm error ({name}): {e}")
            continue
    return events


def main():
    driver = setup_driver()
    all_data = []
    
    # 確実版ロジックをトレースしたスクレイピング実行
    all_data.extend(scrape_tribe_v2(driver, "ChumToto", "https://chumtoto.jp/schedule/"))
    all_data.extend(scrape_tribe_v2(driver, "きゅるして", "https://www.kyurushite.com/schedule/"))
    
    # その他グループ
    all_data.extend(scrape_2zicon(driver))
    all_data.extend(scrape_dspm(driver, "さよステ", "https://sayostay.dspm.jp", "/schedules/menu/18610"))
    all_data.extend(scrape_dspm(driver, "meme", "https://www.memetokyo.com", "/vertical_calendar"))
    
    driver.quit()

    # 1. 重複排除
    unique_events = list({(ev['title'], ev['start']): ev for ev in all_data}.values())

    # 2. 前回データの比較と added_at の保持
    old_data_dict = {}
    if os.path.exists('data.json'):
        try:
            with open('data.json', 'r', encoding='utf-8') as f:
                old_list = json.load(f)
                # payload形式・平坦形式の両方に対応
                items = old_list.get('events', []) if isinstance(old_list, dict) else old_list
                old_data_dict = {(ev['title'], ev['start']): ev.get('added_at') for ev in items}
        except Exception as e:
            print(f"前回のデータ読み込みに失敗しました: {e}")

    current_now = datetime.now().isoformat()

    for ev in unique_events:
        key = (ev['title'], ev['start'])
        if key in old_data_dict and old_data_dict[key]:
            ev['added_at'] = old_data_dict[key]
        else:
            ev['added_at'] = current_now

    # 3. JSON保存 (GAS・フロント統合ペイロード形式)
    payload = {
        "action": "sync_schedule",
        "events": unique_events
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"全工程完了。合計 {len(unique_events)} 件保存完了。")

    # 4. カレンダー同期
    sync_selected_events_to_gcal(unique_events)


if __name__ == "__main__":
    main()
