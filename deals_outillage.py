import urllib.request, urllib.parse, re, json, os
from datetime import datetime

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT  = os.environ["CHAT_ID"]
SEEN  = "seen_deals.json"
HISTORY = "deals_history.json"

FEEDS = [
    ("https://www.dealabs.com/rss/groupe/outillage", "Outillage"),
    ("https://www.dealabs.com/rss/groupe/jardin-bricolage", "Jardin/Bricolage"),
]

KW = ["perceuse","visseuse","meuleuse","scie","ponceuse","marteau","perforateur",
      "tronconneuse","debroussailleuse","souffleur","compresseur","tondeuse",
      "taille-haie","niveau laser","outillage","parkside","bosch","makita",
      "dewalt","milwaukee","ryobi","einhell","worx","stanley","karcher",
      "nettoyeur","fer a souder","scie circulaire","scie sauteuse","outil"]

H = {"User-Agent": "Mozilla/5.0"}

def load_json(f, default):
    try:
        with open(f) as fp: return json.load(fp)
    except: return default

def save_json(f, data):
    with open(f, "w") as fp: json.dump(data, fp, ensure_ascii=False, indent=2)

def parse(html):
    r = []
    for item in re.findall(r"<item>(.*?)</item>", html, re.DOTALL):
        t = re.search(r"<title><!\[CDATA\[([^\]]+)\]", item)
        if not t: continue
        title = t.group(1).strip()
        p = re.search(r'price="([^"]+)"', item)
        m = re.search(r'merchant name="([^"]+)"', item)
        l = re.search(r"<link>([^<]+)</link>", item)
        d = re.search(r"<description><!\[CDATA\[(.*?)\]\]>", item, re.DOTALL)
        price = p.group(1) if p else ""
        merch = m.group(1) if m else ""
        link  = l.group(1).strip() if l else ""
        desc  = re.sub(r"<[^>]+>", " ", d.group(1)) if d else ""
        txt   = title + " " + desc
        pcts  = re.findall(r"[-]\s*(\d{2,3})\s*%", txt)
        pcts += re.findall(r"(\d{2,3})\s*%\s*(?:de remise|reduction|off|moins)", txt, re.IGNORECASE)
        pct = max([int(x) for x in pcts], default=0)
        if pct < 30 and price:
            try:
                curr = float(re.sub(r"[^\d,.]", "", price).replace(",", "."))
                fs = sorted(set([float(x.replace(",", ".")) for x in
                     re.findall(r"([0-9]+[,\.][0-9]{2})\s*", txt)]), reverse=True)
                if fs and fs[0] > curr * 1.43:
                    pct = int((fs[0] - curr) / fs[0] * 100)
            except: pass
        if pct >= 30 and any(k in txt.lower() for k in KW):
            did = re.search(r"/(\d+)$", link)
            r.append({"id": did.group(1) if did else link[-20:],
                      "title": title, "price": price, "pct": pct,
                      "merch": merch, "link": link})
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

def generate_readme(history):
    now = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
    lines = [
        "# 🔧 Deals Outillage — Tableau de bord",
        f"",
        f"**Dernière mise à jour :** {now}  ",
        f"**Total deals trouvés :** {len(history)}  ",
        f"**Source :** Dealabs.com (Outillage + Jardin/Bricolage)  ",
        f"**Filtre :** Remise ≥ 30%",
        f"",
        "---",
        "",
        "## 🏆 Deals actifs",
        "",
        "| Remise | Produit | Prix | Enseigne | Lien |",
        "|--------|---------|------|----------|------|",
    ]
    # Sort by discount desc, show last 50
    for d in sorted(history, key=lambda x: x["pct"], reverse=True)[:50]:
        title = d["title"][:55].replace("|", "-")
        lines.append(
            f"| **-{d['pct']}%** | {title} | {d['price']} | {d['merch']} | [Voir]({d['link']}) |"
        )
    lines += [
        "",
        "---",
        "",
        "## 📈 Historique complet",
        "",
        "| Date | Remise | Produit | Prix | Enseigne |",
        "|------|--------|---------|------|----------|",
    ]
    for d in reversed(history[-100:]):
        date = d.get("date", "")
        title = d["title"][:50].replace("|", "-")
        lines.append(f"| {date} | -{d['pct']}% | {title} | {d['price']} | {d['merch']} |")
    return "\n".join(lines)

# Main
seen    = set(load_json(SEEN, []))
history = load_json(HISTORY, [])
new     = []
now_str = datetime.utcnow().strftime("%d/%m/%Y %H:%M")

for url, cat in FEEDS:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=H), timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")
        for d in parse(html):
            if d["id"] not in seen:
                d["date"] = now_str
                new.append(d)
                seen.add(d["id"])
                history.append(d)
    except Exception as e:
        print(f"Erreur {cat}: {e}")

if not new:
    print("Aucun nouveau deal >=30%")
else:
    new.sort(key=lambda x: x["pct"], reverse=True)
    msg = f"Deals Outillage >=30% - {now_str}\n\n"
    for d in new:
        msg += f"[-{d['pct']}%] {d['title'][:65]}\n{d['price']} chez {d['merch']}\n{d['link']}\n\n"
    msg += f"{len(new)} deal(s) trouve(s)"
    if len(msg) > 4000: msg = msg[:4000]
    print("Telegram:", tg(msg))

save_json(SEEN, list(seen)[-500:])
save_json(HISTORY, history[-200:])

# Generate README dashboard
readme = generate_readme(history)
with open("README.md", "w") as f:
    f.write(readme)

print(f"Dashboard mis a jour: {len(history)} deals au total")
