import urllib.request, urllib.parse, re, json, os
from datetime import datetime

TOKEN = os.environ["T8984786370:AAE3gxHMX4v_Ey7c6DQV7sI6Eb22IsxGlrQ"]
CHAT  = os.environ["6334361201"]
SEEN  = "seen_deals.json"

FEEDS = [
    ("https://www.dealabs.com/rss/groupe/outillage", "Outillage"),
    ("https://www.dealabs.com/rss/groupe/jardin-bricolage", "Jardin"),
]

KW = ['perceuse','visseuse','meuleuse','scie','ponceuse','marteau','perforateur',
      'tronconneuse','debroussailleuse','souffleur','compresseur','tondeuse',
      'taille-haie','niveau laser','outillage','parkside','bosch','makita',
      'dewalt','milwaukee','ryobi','einhell','worx','stanley','karcher',
      'nettoyeur','fer a souder','scie circulaire','scie sauteuse','outil']

H = {"User-Agent": "Mozilla/5.0"}

def load():
    try:
        with open(SEEN) as f: return set(json.load(f))
    except: return set()

def save(s):
    with open(SEEN, "w") as f: json.dump(list(s)[-500:], f)

def parse(html):
    r = []
    for item in re.findall(r'<item>(.*?)</item>', html, re.DOTALL):
        t = re.search(r'<title><!\[CDATA\[([^\]]+)\]', item)
        if not t: continue
        title = t.group(1).strip()
        p = re.search(r'price="([^"]+)"', item)
        m = re.search(r'merchant name="([^"]+)"', item)
        l = re.search(r'<link>([^<]+)</link>', item)
        d = re.search(r'<description><!\[CDATA\[(.*?)\]\]>', item, re.DOTALL)
        price = p.group(1) if p else ""
        merch = m.group(1) if m else ""
        link  = l.group(1).strip() if l else ""
        desc  = re.sub(r'<[^>]+>', ' ', d.group(1)) if d else ""
        txt   = title + " " + desc
        pcts  = re.findall(r'[-]\s*(\d{2,3})\s*%', txt)
        pcts += re.findall(r'(\d{2,3})\s*%\s*(?:de remise|reduction|off|moins)',
                           txt, re.IGNORECASE)
        pct = max([int(x) for x in pcts], default=0)
        if pct < 30 and price:
            try:
                curr = float(re.sub(r'[^\d,.]', '', price).replace(',', '.'))
                fs = sorted(set([float(x.replace(',', '.')) for x in
                     re.findall(r'([0-9]+[,\.][0-9]{2})\s*', txt)]), reverse=True)
                if fs and fs[0] > curr * 1.43:
                    pct = int((fs[0] - curr) / fs[0] * 100)
            except: pass
        if pct >= 30 and any(k in txt.lower() for k in KW):
            did = re.search(r'/(\d+)$', link)
            r.append({"id": did.group(1) if did else link[-20:],
                      "title": title, "price": price,
                      "pct": pct, "merch": merch, "link": link})
    return r

def tg(txt):
    data = urllib.parse.urlencode({
        "chat_id": CHAT, "text": txt,
        "parse_mode": "HTML", "disable_web_page_preview": "false"
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data),
        timeout=15) as r:
        return json.loads(r.read()).get("ok")

seen = load()
new  = []

for url, cat in FEEDS:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=H), timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")
        for d in parse(html):
            if d["id"] not in seen:
                new.append(d)
                seen.add(d["id"])
    except Exception as e:
        print(f"Erreur {cat}: {e}")

if not new:
    print("Aucun nouveau deal >=30%")
else:
    new.sort(key=lambda x: x["pct"], reverse=True)
    now = datetime.now().strftime("%d/%m %H:%M")
    msg = f"Deals Outillage >=30% - {now}\n\n"
    for d in new:
        msg += f"[-{d['pct']}%] {d['title'][:65]}\n{d['price']} chez {d['merch']}\n{d['link']}\n\n"
    msg += f"{len(new)} deal(s) trouve(s)"
    if len(msg) > 4000: msg = msg[:4000]
    print("Telegram:", tg(msg))
    save(seen)
