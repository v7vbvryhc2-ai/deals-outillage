import json, re, os, urllib.parse, urllib.request
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

TOKEN   = os.environ["TELEGRAM_TOKEN"]
CHAT    = os.environ["CHAT_ID"]
SEEN    = "seen_deals.json"
HISTORY = "deals_history.json"

KW = ["perceuse","visseuse","meuleuse","scie","ponceuse","marteau","perforateur",
      "tronconneuse","debroussailleuse","souffleur","compresseur","tondeuse",
      "taille-haie","niveau laser","outillage","parkside","bosch","makita",
      "dewalt","milwaukee","ryobi","einhell","worx","stanley","karcher",
      "nettoyeur","fer a souder","scie circulaire","scie sauteuse","outil",
      "visseuse","tournevis","niveau","perceuse","cloueur","rabot","raboteuse",
      "affuteuse","meuleuse","polisseuse","souffleur","aspirateur atelier"]

STORES = [
    ("Leroy Merlin", "https://www.leroymerlin.be/fr/promotions/outillage-electrique"),
    ("Leroy Merlin FR", "https://www.leroymerlin.fr/promotions/outillage-electrique/"),
    ("Brico", "https://www.brico.be/fr/outillage/"),
    ("Gamma", "https://www.gamma.be/nl/gereedschap/aanbiedingen/"),
    ("Hubo", "https://www.hubo.be/nl/gereedschap/"),
    ("Castorama", "https://www.castorama.fr/outillage/r-outillage-electrique.html?prefn1=isPromo&prefv1=true"),
    ("Mr Bricolage", "https://www.mr-bricolage.be/fr/outillage-electrique/promotions"),
    ("Toolstation", "https://www.toolstation.be/fr/promotions/"),
    ("Amazon FR", "https://www.amazon.fr/s?rh=n%3A13920671%2Cp_n_pct-off-with-tax%3A30-&sort=discount-rank"),
    ("Cdiscount", "https://www.cdiscount.com/bricolage/outillage/l-bricolage_outillage.html?SortBy=DiscountDesc"),
    ("Bol.com", "https://www.bol.com/be/nl/l/gereedschap/36491/?sort=promodiscount&filterSelected=promotion_label%3Aopruiming"),
    ("Action", "https://www.action.com/fr-be/c/outillage/"),
    ("Lidl", "https://www.lidl.be/fr/c/outillage/c3210"),
    ("Bricomarché", "https://www.bricomarche.com/outillage/outillage-electrique"),
    ("Weldom", "https://www.weldom.fr/promotions/outillage"),
]

def load_json(f, default):
    try:
        with open(f) as fp: return json.load(fp)
    except: return default

def save_json(f, data):
    with open(f, "w") as fp: json.dump(data, fp, ensure_ascii=False, indent=2)

def is_tool(text):
    t = text.lower()
    return any(k in t for k in KW)

def calc_discount(old, new):
    try:
        o, n = float(str(old).replace(',','.')), float(str(new).replace(',','.'))
        if o > n > 0:
            return int((o - n) / o * 100)
    except: pass
    return 0

def parse_price(s):
    if not s: return None
    try:
        return float(re.sub(r'[^\d,.]','', str(s)).replace(',','.'))
    except: return None

def extract_from_page(page, store_name):
    deals = []
    url = page.url

    # 1) JSON-LD structured data
    for script in page.query_selector_all('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.inner_text())
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get('@type') == 'ItemList':
                    items += [e.get('item', e) for e in item.get('itemListElement', [])]
                if item.get('@type') == 'Product':
                    name = item.get('name', '')
                    if not name or not is_tool(name): continue
                    offers = item.get('offers', {})
                    if isinstance(offers, list): offers = offers[0] if offers else {}
                    price = parse_price(offers.get('price'))
                    high  = parse_price(offers.get('highPrice') or item.get('offers', {}).get('highPrice'))
                    pct   = calc_discount(high, price) if high and price else 0
                    if pct >= 30:
                        deals.append({
                            "id": re.sub(r'[^\w]','', name[:20] + str(price)),
                            "title": name[:100], "price": f"{price}€",
                            "pct": pct, "merch": store_name,
                            "link": offers.get('url', url), "image": ""
                        })
        except: pass

    # 2) HTML patterns — old price in <s> or .old-price, new price nearby
    try:
        html = page.content()
        # Amazon pattern
        if 'amazon' in url:
            blocks = re.findall(
                r'<span[^>]*s-price-instructions-style[^>]*>.*?'
                r'(\d+[,\.]\d+).*?</span>.*?'
                r'<span[^>]*a-price-whole[^>]*>(\d+)',
                html, re.DOTALL)
            for old, new in blocks[:20]:
                pct = calc_discount(old, new)
                if pct >= 30:
                    title_m = re.search(r'<span[^>]*a-size-base-plus[^>]*>([^<]{10,80})', html)
                    if title_m and is_tool(title_m.group(1)):
                        deals.append({
                            "id": f"amz_{new}_{old}",
                            "title": title_m.group(1), "price": f"{new}€",
                            "pct": pct, "merch": "Amazon",
                            "link": url, "image": ""
                        })

        # Generic: find % discount badges
        pct_badges = re.findall(r'[-–]\s*(\d{2,3})\s*%', html)
        if any(int(p) >= 30 for p in pct_badges):
            # Try to extract product cards around these badges
            for pct_str in pct_badges:
                pct = int(pct_str)
                if pct < 30: continue
                # Find context around the badge
                idx = html.find(f'-{pct_str}%') or html.find(f'– {pct_str}%')
                if idx < 0: continue
                ctx = html[max(0,idx-500):idx+500]
                # Look for a product name in that context
                name_candidates = re.findall(r'(?:alt|title|aria-label)="([^"]{10,80})"', ctx)
                for name in name_candidates:
                    if is_tool(name) and len(deals) < 50:
                        price_m = re.search(r'([\d]+[,\.][\d]{2})\s*€', ctx)
                        link_m  = re.search(r'href="(/[^"]{5,100})"', ctx)
                        deals.append({
                            "id": re.sub(r'[^\w]','', name[:20]+pct_str),
                            "title": name[:100],
                            "price": f"{price_m.group(1)}€" if price_m else "?",
                            "pct": pct, "merch": store_name,
                            "link": (page.url.split('/')[0]+'//'+page.url.split('/')[2]+link_m.group(1)) if link_m else url,
                            "image": ""
                        })
                        break
    except: pass

    # Deduplicate within this store
    seen_ids = set()
    unique = []
    for d in deals:
        if d["id"] not in seen_ids:
            seen_ids.add(d["id"])
            unique.append(d)
    return unique

def scrape_all():
    all_deals = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="fr-BE",
            viewport={"width": 1280, "height": 900}
        )
        for store_name, url in STORES:
            page = ctx.new_page()
            try:
                print(f"Scan {store_name}...")
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(4000)
                # Scroll to load lazy content
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(2000)
                deals = extract_from_page(page, store_name)
                print(f"  → {len(deals)} deals ≥30%")
                all_deals.extend(deals)
            except PwTimeout:
                print(f"  → Timeout sur {store_name}")
            except Exception as e:
                print(f"  → Erreur {store_name}: {e}")
            finally:
                page.close()
        ctx.close()
        browser.close()
    return all_deals

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
    deals_json = json.dumps(history[-300:], ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Deals Outillage ≥30%</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}}
header{{background:linear-gradient(135deg,#1e40af,#7c3aed);padding:24px;text-align:center}}
header h1{{font-size:2rem;font-weight:700}}
header p{{opacity:.8;margin-top:6px;font-size:.9rem}}
.stats{{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;padding:20px}}
.stat{{background:#1e293b;border-radius:12px;padding:16px 24px;text-align:center;border:1px solid #334155}}
.stat .num{{font-size:2rem;font-weight:700;color:#60a5fa}}
.stat .label{{font-size:.8rem;color:#94a3b8;margin-top:4px}}
.controls{{padding:0 20px 16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center}}
.controls input,.controls select{{padding:10px 16px;background:#1e293b;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:.9rem}}
.controls input{{flex:1;min-width:200px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;padding:0 20px 40px}}
.card{{background:#1e293b;border-radius:16px;border:1px solid #334155;overflow:hidden;transition:transform .2s,box-shadow .2s;cursor:pointer}}
.card:hover{{transform:translateY(-4px);box-shadow:0 12px 40px rgba(0,0,0,.4)}}
.card-img{{width:100%;height:160px;object-fit:contain;background:#0f172a;padding:12px}}
.card-img-placeholder{{width:100%;height:160px;background:#0f172a;display:flex;align-items:center;justify-content:center;font-size:3rem}}
.badge{{display:inline-block;color:#fff;font-weight:700;font-size:1.1rem;padding:4px 12px;border-radius:20px;margin:12px 12px 0}}
.card-body{{padding:12px}}
.card-title{{font-size:.9rem;font-weight:600;color:#f1f5f9;margin-bottom:8px;line-height:1.4}}
.card-meta{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.price{{font-size:1.1rem;font-weight:700;color:#34d399}}
.merch{{font-size:.75rem;color:#94a3b8;background:#0f172a;padding:3px 8px;border-radius:6px}}
.card-date{{font-size:.72rem;color:#64748b;margin-bottom:10px}}
.btn{{display:block;text-align:center;background:linear-gradient(135deg,#3b82f6,#8b5cf6);color:#fff;padding:10px;border-radius:8px;text-decoration:none;font-weight:600;font-size:.85rem}}
.btn:hover{{opacity:.9}}
.empty{{text-align:center;padding:60px;color:#64748b;font-size:1.1rem}}
.updated{{text-align:center;padding:8px;color:#475569;font-size:.8rem;margin-bottom:10px}}
</style>
</head>
<body>
<header>
  <h1>🔧 Deals Outillage ≥30%</h1>
  <p>Scan toutes les heures • Leroy Merlin • Brico • Gamma • Hubo • Castorama • Amazon • Cdiscount • Toolstation • Bol.com • Action • Lidl • et plus</p>
</header>
<div class="stats">
  <div class="stat"><div class="num" id="total">0</div><div class="label">Deals trouvés</div></div>
  <div class="stat"><div class="num" id="best">0%</div><div class="label">Meilleure remise</div></div>
  <div class="stat"><div class="num" id="shops">0</div><div class="label">Boutiques</div></div>
</div>
<div class="controls">
  <input type="text" id="search" placeholder="🔍 Rechercher (perceuse, bosch, makita...)" oninput="filter()">
  <select id="sort" onchange="filter()">
    <option value="pct">Remise décroissante</option>
    <option value="date">Plus récents</option>
    <option value="price">Prix croissant</option>
  </select>
  <select id="store" onchange="filter()">
    <option value="">Toutes les boutiques</option>
  </select>
</div>
<div class="grid" id="grid"></div>
<div class="updated">Dernière mise à jour : {now}</div>
<script>
const RAW={deals_json};
const deals=RAW.slice().reverse();
const storeSelect=document.getElementById('store');
const stores=[...new Set(deals.map(d=>d.merch))].sort();
stores.forEach(s=>{{const o=document.createElement('option');o.value=s;o.textContent=s;storeSelect.appendChild(o)}});
function pctColor(p){{return p>=60?'#f97316':p>=45?'#ef4444':'#dc2626'}}
function parsePrice(s){{if(!s)return 9999;return parseFloat(s.replace(/[^0-9,\.]/g,'').replace(',','.'))||9999}}
function filter(){{
  const q=document.getElementById('search').value.toLowerCase();
  const sort=document.getElementById('sort').value;
  const store=document.getElementById('store').value;
  let f=deals.filter(d=>(d.title.toLowerCase().includes(q)||d.merch.toLowerCase().includes(q))&&(!store||d.merch===store));
  if(sort==='pct')f.sort((a,b)=>b.pct-a.pct);
  else if(sort==='date')f.sort((a,b)=>(b.date||'').localeCompare(a.date||''));
  else f.sort((a,b)=>parsePrice(a.price)-parsePrice(b.price));
  render(f);
}}
function render(list){{
  const grid=document.getElementById('grid');
  if(!list.length){{grid.innerHTML='<div class="empty">Aucun deal trouvé 🔍</div>';return}}
  grid.innerHTML=list.map(d=>`
    <a href="${{d.link}}" target="_blank" class="card">
      ${{d.image?`<img class="card-img" src="${{d.image}}" alt="${{d.title}}" loading="lazy" onerror="this.parentNode.querySelector('.card-img-placeholder').style.display='flex';this.style.display='none'">`:`<div class="card-img-placeholder">🔧</div>`}}
      <span class="badge" style="background:${{pctColor(d.pct)}}">-${{d.pct}}%</span>
      <div class="card-body">
        <div class="card-title">${{d.title}}</div>
        <div class="card-meta"><span class="price">${{d.price||'?'}}</span><span class="merch">${{d.merch}}</span></div>
        ${{d.date?`<div class="card-date">📅 ${{d.date}}</div>`:''}}
        <span class="btn">Voir le deal →</span>
      </div>
    </a>`).join('');
  document.getElementById('total').textContent=list.length;
  const pcts=list.map(d=>d.pct).filter(Boolean);
  document.getElementById('best').textContent=(pcts.length?Math.max(...pcts):0)+'%';
  document.getElementById('shops').textContent=new Set(list.map(d=>d.merch)).size;
}}
filter();
</script>
</body>
</html>"""

# ── MAIN ──────────────────────────────────────────────────────────────────────
seen    = set(load_json(SEEN, []))
history = load_json(HISTORY, [])
now_str = datetime.utcnow().strftime("%d/%m/%Y %H:%M")
new     = []

all_deals = scrape_all()

for d in all_deals:
    if d["id"] not in seen:
        d["date"] = now_str
        new.append(d)
        seen.add(d["id"])
        history.append(d)

print(f"\nTotal: {len(all_deals)} deals scannés, {len(new)} nouveaux")

if new:
    new.sort(key=lambda x: x["pct"], reverse=True)
    msg = f"🔧 Deals Outillage ≥30% - {now_str}\n\n"
    for d in new[:10]:
        msg += f"[-{d['pct']}%] {d['title'][:65]}\n{d['price']} chez {d['merch']}\n{d['link']}\n\n"
    if len(new) > 10:
        msg += f"... et {len(new)-10} autres deals\n\n"
    msg += f"👉 Dashboard: https://v7vbvryhc2-ai.github.io/deals-outillage/"
    if len(msg) > 4000: msg = msg[:4000]
    print("Telegram:", tg(msg))

save_json(SEEN, list(seen)[-1000:])
save_json(HISTORY, history[-300:])

html = generate_html(history)
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"Dashboard: {len(history)} deals au total")
