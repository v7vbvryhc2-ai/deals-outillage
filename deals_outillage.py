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
        img = re.search(r'url="(https://static-pepper[^"]+)"', item)
        price = p.group(1) if p else ""
        merch = m.group(1) if m else ""
        link  = l.group(1).strip() if l else ""
        image = img.group(1) if img else ""
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
                      "merch": merch, "link": link, "image": image})
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

def generate_html(history):
    now = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
    deals_json = json.dumps(history[-200:], ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Deals Outillage ≥30%</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'Segoe UI',sans-serif; background:#0f172a; color:#e2e8f0; min-height:100vh; }}
  header {{ background:linear-gradient(135deg,#1e40af,#7c3aed); padding:24px; text-align:center; }}
  header h1 {{ font-size:2rem; font-weight:700; }}
  header p {{ opacity:.8; margin-top:6px; }}
  .stats {{ display:flex; gap:12px; justify-content:center; flex-wrap:wrap; padding:20px; }}
  .stat {{ background:#1e293b; border-radius:12px; padding:16px 24px; text-align:center; border:1px solid #334155; }}
  .stat .num {{ font-size:2rem; font-weight:700; color:#60a5fa; }}
  .stat .label {{ font-size:.8rem; color:#94a3b8; margin-top:4px; }}
  .controls {{ padding:0 20px 16px; display:flex; gap:12px; flex-wrap:wrap; align-items:center; }}
  .controls input {{ flex:1; min-width:200px; padding:10px 16px; background:#1e293b; border:1px solid #334155; border-radius:8px; color:#e2e8f0; font-size:.95rem; }}
  .controls select {{ padding:10px 16px; background:#1e293b; border:1px solid #334155; border-radius:8px; color:#e2e8f0; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:16px; padding:0 20px 40px; }}
  .card {{ background:#1e293b; border-radius:16px; border:1px solid #334155; overflow:hidden; transition:transform .2s,box-shadow .2s; }}
  .card:hover {{ transform:translateY(-4px); box-shadow:0 12px 40px rgba(0,0,0,.4); }}
  .card-img {{ width:100%; height:160px; object-fit:contain; background:#0f172a; padding:12px; }}
  .card-img-placeholder {{ width:100%; height:160px; background:#0f172a; display:flex; align-items:center; justify-content:center; font-size:3rem; }}
  .badge {{ display:inline-block; background:#dc2626; color:#fff; font-weight:700; font-size:1.1rem; padding:4px 12px; border-radius:20px; margin:12px 12px 0; }}
  .card-body {{ padding:12px; }}
  .card-title {{ font-size:.95rem; font-weight:600; color:#f1f5f9; margin-bottom:8px; line-height:1.4; }}
  .card-meta {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }}
  .price {{ font-size:1.2rem; font-weight:700; color:#34d399; }}
  .merch {{ font-size:.8rem; color:#94a3b8; background:#0f172a; padding:3px 8px; border-radius:6px; }}
  .card-date {{ font-size:.75rem; color:#64748b; margin-bottom:10px; }}
  .btn {{ display:block; text-align:center; background:linear-gradient(135deg,#3b82f6,#8b5cf6); color:#fff; padding:10px; border-radius:8px; text-decoration:none; font-weight:600; font-size:.9rem; }}
  .btn:hover {{ opacity:.9; }}
  .empty {{ text-align:center; padding:60px; color:#64748b; font-size:1.1rem; }}
  .updated {{ text-align:center; padding:8px; color:#475569; font-size:.8rem; }}
</style>
</head>
<body>
<header>
  <h1>🔧 Deals Outillage ≥30%</h1>
  <p>Scan automatique toutes les heures — Source : Dealabs.com</p>
</header>

<div class="stats">
  <div class="stat"><div class="num" id="total">0</div><div class="label">Deals trouvés</div></div>
  <div class="stat"><div class="num" id="best">0%</div><div class="label">Meilleure remise</div></div>
  <div class="stat"><div class="num" id="shops">0</div><div class="label">Enseignes</div></div>
</div>

<div class="controls">
  <input type="text" id="search" placeholder="🔍 Rechercher (perceuse, bosch...)" oninput="filter()">
  <select id="sort" onchange="filter()">
    <option value="pct">Remise décroissante</option>
    <option value="date">Plus récents</option>
    <option value="price">Prix croissant</option>
  </select>
</div>

<div class="grid" id="grid"></div>
<div class="updated">Dernière mise à jour : {now}</div>

<script>
const RAW = {deals_json};
const deals = RAW.slice().reverse();

function pctColor(p) {{
  if (p >= 60) return '#f97316';
  if (p >= 45) return '#ef4444';
  return '#dc2626';
}}

function parsePrice(s) {{
  if (!s) return 9999;
  return parseFloat(s.replace(/[^0-9,\.]/g,'').replace(',','.')) || 9999;
}}

function filter() {{
  const q = document.getElementById('search').value.toLowerCase();
  const sort = document.getElementById('sort').value;
  let filtered = deals.filter(d =>
    d.title.toLowerCase().includes(q) ||
    d.merch.toLowerCase().includes(q)
  );
  if (sort === 'pct') filtered.sort((a,b) => b.pct - a.pct);
  else if (sort === 'date') filtered.sort((a,b) => (b.date||'').localeCompare(a.date||''));
  else if (sort === 'price') filtered.sort((a,b) => parsePrice(a.price) - parsePrice(b.price));
  render(filtered);
}}

function render(list) {{
  const grid = document.getElementById('grid');
  if (!list.length) {{ grid.innerHTML='<div class="empty">Aucun deal trouvé 🔍</div>'; return; }}
  grid.innerHTML = list.map(d => `
    <div class="card">
      ${{d.image
        ? `<img class="card-img" src="${{d.image}}" alt="${{d.title}}" loading="lazy" onerror="this.style.display='none'">`
        : `<div class="card-img-placeholder">🔧</div>`
      }}
      <span class="badge" style="background:${{pctColor(d.pct)}}">-${{d.pct}}%</span>
      <div class="card-body">
        <div class="card-title">${{d.title}}</div>
        <div class="card-meta">
          <span class="price">${{d.price || 'Prix ?'}}</span>
          <span class="merch">${{d.merch}}</span>
        </div>
        ${{d.date ? `<div class="card-date">📅 ${{d.date}}</div>` : ''}}
        <a href="${{d.link}}" target="_blank" class="btn">Voir le deal →</a>
      </div>
    </div>
  `).join('');

  // Stats
  document.getElementById('total').textContent = list.length;
  document.getElementById('best').textContent = Math.max(...list.map(d=>d.pct)) + '%';
  document.getElementById('shops').textContent = new Set(list.map(d=>d.merch)).size;
}}

filter();
</script>
</body>
</html>"""

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

html_page = generate_html(history)
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_page)

print(f"Page web generee: {len(history)} deals")
