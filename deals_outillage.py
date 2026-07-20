import json, re, os, urllib.parse, urllib.request
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

TOKEN   = os.environ["TELEGRAM_TOKEN"]
CHAT    = os.environ["CHAT_ID"]
SEEN    = "seen_deals.json"
HISTORY = "deals_history.json"

KW_OUTILLAGE = [
    "perceuse","visseuse","meuleuse","scie","ponceuse","marteau","perforateur",
    "tronconneuse","souffleur","compresseur","karcher","nettoyeur haute pression",
    "fer a souder","scie circulaire","scie sauteuse","scie sabre","outil electrique",
    "cloueur","agrafeuse","rabot","affuteuse","polisseuse","decapeur","chalumeau",
    "niveau laser","outillage","parkside","bosch","makita","dewalt","milwaukee",
    "ryobi","einhell","worx","stanley","hikoki","festool","metabo","facom","fabre",
    "aspirateur atelier","visseuse a choc","perceuse visseuse"
]

KW_JARDINAGE = [
    "tondeuse","robot tondeuse","taille-haie","taille haie","debroussailleuse",
    "scarificateur","aerateur","souffleur feuilles","aspirateur feuilles",
    "tuyau arrosage","arroseur","pompe arrosage","programmateur arrosage",
    "serre","brouette","composteur","broyeur","bache","bordure jardin",
    "motoculteur","motobineuse","elagueur","coupe bordure","rotofil",
    "pulverisateur","traitement jardin","engrais","terreau","pot fleur",
    "jardinage","husqvarna","stihl","greenworks","ego","ferrex","florabest",
    "gardena","kress","outils jardin","bêche","fourche","binette","râteau",
    "pelle","transplantoir","sécateur","cisaille","echenilloir","griffe",
    "piscine","spa","pompe piscine","robot piscine","liner","bache piscine",
    "parasol","salon jardin","barbecue","plancha","table jardin","chaise jardin"
]

KW_ALL = list(set(KW_OUTILLAGE + KW_JARDINAGE))

STORES = [
    # Outillage
    ("Leroy Merlin", "https://www.leroymerlin.be/fr/promotions/outillage-electrique", "Outillage"),
    ("Leroy Merlin FR", "https://www.leroymerlin.fr/promotions/outillage-electrique/", "Outillage"),
    ("Brico", "https://www.brico.be/fr/outillage/", "Outillage"),
    ("Gamma", "https://www.gamma.be/nl/gereedschap/aanbiedingen/", "Outillage"),
    ("Hubo", "https://www.hubo.be/nl/gereedschap/", "Outillage"),
    ("Castorama", "https://www.castorama.fr/outillage/r-outillage-electrique.html?prefn1=isPromo&prefv1=true", "Outillage"),
    ("Toolstation", "https://www.toolstation.be/fr/promotions/", "Outillage"),
    ("Amazon FR outils", "https://www.amazon.fr/s?rh=n%3A13920671%2Cp_n_pct-off-with-tax%3A30-&sort=discount-rank", "Outillage"),
    ("Cdiscount outils", "https://www.cdiscount.com/bricolage/outillage/l-bricolage_outillage.html?SortBy=DiscountDesc", "Outillage"),
    ("Bol.com outils", "https://www.bol.com/be/nl/l/gereedschap/36491/?sort=promodiscount", "Outillage"),
    ("Lidl outils", "https://www.lidl.be/fr/c/outillage/c3210", "Outillage"),
    ("Action outils", "https://www.action.com/fr-be/c/outillage/", "Outillage"),
    ("Bricomarché", "https://www.bricomarche.com/outillage/outillage-electrique", "Outillage"),
    ("Mr Bricolage", "https://www.mr-bricolage.be/fr/outillage-electrique/promotions", "Outillage"),
    ("Weldom outils", "https://www.weldom.fr/promotions/outillage", "Outillage"),
    # Jardinage
    ("Leroy Merlin Jardin", "https://www.leroymerlin.be/fr/promotions/jardin", "Jardinage"),
    ("Leroy Merlin FR Jardin", "https://www.leroymerlin.fr/promotions/jardin/", "Jardinage"),
    ("Brico Jardin", "https://www.brico.be/fr/jardin/", "Jardinage"),
    ("Gamma Jardin", "https://www.gamma.be/nl/tuin/aanbiedingen/", "Jardinage"),
    ("Hubo Jardin", "https://www.hubo.be/nl/tuin/", "Jardinage"),
    ("Castorama Jardin", "https://www.castorama.fr/jardin/r-jardin.html?prefn1=isPromo&prefv1=true", "Jardinage"),
    ("Amazon FR Jardin", "https://www.amazon.fr/s?rh=n%3A592765011%2Cp_n_pct-off-with-tax%3A30-&sort=discount-rank", "Jardinage"),
    ("Cdiscount Jardin", "https://www.cdiscount.com/jardin/l-jardin.html?SortBy=DiscountDesc", "Jardinage"),
    ("Bol.com Jardin", "https://www.bol.com/be/nl/l/tuin/24798/?sort=promodiscount", "Jardinage"),
    ("Lidl Jardin", "https://www.lidl.be/fr/c/jardin/c1570", "Jardinage"),
    ("Action Jardin", "https://www.action.com/fr-be/c/jardin/", "Jardinage"),
    ("Bricomarché Jardin", "https://www.bricomarche.com/jardin", "Jardinage"),
    ("Mr Bricolage Jardin", "https://www.mr-bricolage.be/fr/jardin/promotions", "Jardinage"),
]

def load_json(f, default):
    try:
        with open(f) as fp: return json.load(fp)
    except: return default

def save_json(f, data):
    with open(f, "w") as fp: json.dump(data, fp, ensure_ascii=False, indent=2)

def is_relevant(text, category):
    t = text.lower()
    kw = KW_JARDINAGE if category == "Jardinage" else KW_OUTILLAGE
    return any(k in t for k in kw) or any(k in t for k in KW_ALL)

def calc_discount(old, new):
    try:
        o, n = float(str(old).replace(',','.')), float(str(new).replace(',','.'))
        if o > n > 0: return int((o - n) / o * 100)
    except: pass
    return 0

def parse_price(s):
    if not s: return None
    try: return float(re.sub(r'[^\d,.]','', str(s)).replace(',','.'))
    except: return None

def extract_from_page(page, store_name, category):
    deals = []
    url = page.url

    # JSON-LD
    for script in page.query_selector_all('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.inner_text())
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get('@type') == 'ItemList':
                    items += [e.get('item', e) for e in item.get('itemListElement', [])]
                if item.get('@type') == 'Product':
                    name = item.get('name', '')
                    if not name or not is_relevant(name, category): continue
                    offers = item.get('offers', {})
                    if isinstance(offers, list): offers = offers[0] if offers else {}
                    price = parse_price(offers.get('price'))
                    high  = parse_price(offers.get('highPrice'))
                    pct   = calc_discount(high, price) if high and price else 0
                    if pct >= 30:
                        deals.append({
                            "id": re.sub(r'[^\w]','', name[:20]+str(price)),
                            "title": name[:100], "price": f"{price}€",
                            "pct": pct, "merch": store_name, "category": category,
                            "link": offers.get('url', url), "image": ""
                        })
        except: pass

    # % badges dans HTML
    try:
        html = page.content()
        for pct_str in re.findall(r'[-–]\s*(\d{2,3})\s*%', html):
            pct = int(pct_str)
            if pct < 30: continue
            idx = html.find(f'-{pct_str}%')
            if idx < 0: continue
            ctx = html[max(0,idx-600):idx+600]
            names = re.findall(r'(?:alt|title|aria-label)="([^"]{10,80})"', ctx)
            for name in names:
                if is_relevant(name, category) and len(deals) < 80:
                    pm = re.search(r'([\d]+[,\.][\d]{2})\s*€', ctx)
                    lm = re.search(r'href="(/[^"]{5,120})"', ctx)
                    base = page.url.split('/')[0]+'//'+page.url.split('/')[2]
                    deals.append({
                        "id": re.sub(r'[^\w]','', name[:20]+pct_str+category[:3]),
                        "title": name[:100],
                        "price": f"{pm.group(1)}€" if pm else "?",
                        "pct": pct, "merch": store_name, "category": category,
                        "link": base+lm.group(1) if lm else url,
                        "image": ""
                    })
                    break
    except: pass

    seen_ids, unique = set(), []
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
            locale="fr-BE", viewport={"width": 1280, "height": 900}
        )
        for store_name, url, category in STORES:
            page = ctx.new_page()
            try:
                print(f"[{category}] Scan {store_name}...")
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(4000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(2000)
                deals = extract_from_page(page, store_name, category)
                print(f"  → {len(deals)} deals ≥30%")
                all_deals.extend(deals)
            except PwTimeout:
                print(f"  → Timeout {store_name}")
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
<html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Deals Outillage & Jardinage ≥30%</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}}
header{{background:linear-gradient(135deg,#1e40af,#16a34a);padding:24px;text-align:center}}
header h1{{font-size:2rem;font-weight:700}}
header p{{opacity:.8;margin-top:6px;font-size:.85rem}}
.stats{{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;padding:20px}}
.stat{{background:#1e293b;border-radius:12px;padding:16px 24px;text-align:center;border:1px solid #334155;min-width:120px}}
.stat .num{{font-size:2rem;font-weight:700;color:#60a5fa}}
.stat .label{{font-size:.75rem;color:#94a3b8;margin-top:4px}}
.controls{{padding:0 20px 16px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
.controls input,.controls select{{padding:9px 14px;background:#1e293b;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:.9rem}}
.controls input{{flex:1;min-width:180px}}
.tabs{{display:flex;gap:8px;padding:0 20px 16px}}
.tab{{padding:8px 20px;border-radius:20px;border:1px solid #334155;cursor:pointer;font-size:.9rem;transition:all .2s}}
.tab.active{{background:#3b82f6;border-color:#3b82f6;font-weight:600}}
.tab:not(.active){{color:#94a3b8}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:14px;padding:0 20px 40px}}
.card{{background:#1e293b;border-radius:14px;border:1px solid #334155;overflow:hidden;transition:transform .2s,box-shadow .2s;text-decoration:none;color:inherit;display:block}}
.card:hover{{transform:translateY(-3px);box-shadow:0 10px 35px rgba(0,0,0,.4)}}
.card-img{{width:100%;height:150px;object-fit:contain;background:#0f172a;padding:10px}}
.placeholder{{width:100%;height:150px;background:#0f172a;display:flex;align-items:center;justify-content:center;font-size:2.5rem}}
.badge-row{{display:flex;align-items:center;gap:8px;padding:10px 12px 0}}
.badge{{color:#fff;font-weight:700;font-size:1rem;padding:3px 10px;border-radius:16px}}
.cat-badge{{font-size:.7rem;padding:2px 8px;border-radius:10px;font-weight:600}}
.cat-outillage{{background:#1e40af;color:#93c5fd}}
.cat-jardinage{{background:#14532d;color:#86efac}}
.card-body{{padding:10px 12px 12px}}
.card-title{{font-size:.88rem;font-weight:600;color:#f1f5f9;margin-bottom:8px;line-height:1.4;min-height:40px}}
.card-meta{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.price{{font-size:1.1rem;font-weight:700;color:#34d399}}
.merch{{font-size:.72rem;color:#94a3b8;background:#0f172a;padding:2px 7px;border-radius:5px}}
.card-date{{font-size:.7rem;color:#64748b;margin-bottom:8px}}
.btn{{display:block;text-align:center;background:linear-gradient(135deg,#3b82f6,#8b5cf6);color:#fff;padding:9px;border-radius:7px;font-weight:600;font-size:.82rem}}
.empty{{text-align:center;padding:60px;color:#64748b}}
.footer{{text-align:center;padding:8px;color:#475569;font-size:.78rem;margin-bottom:10px}}
</style></head><body>
<header>
  <h1>🔧🌿 Deals Outillage & Jardinage ≥30%</h1>
  <p>Scan toutes les heures • Leroy Merlin • Brico • Gamma • Hubo • Castorama • Amazon • Cdiscount • Toolstation • Bol.com • Lidl • Action • et plus</p>
</header>
<div class="stats">
  <div class="stat"><div class="num" id="total">0</div><div class="label">Total deals</div></div>
  <div class="stat"><div class="num" id="cnt-out">0</div><div class="label">🔧 Outillage</div></div>
  <div class="stat"><div class="num" id="cnt-jar">0</div><div class="label">🌿 Jardinage</div></div>
  <div class="stat"><div class="num" id="best">0%</div><div class="label">Meilleure remise</div></div>
  <div class="stat"><div class="num" id="shops">0</div><div class="label">Boutiques</div></div>
</div>
<div class="tabs">
  <div class="tab active" onclick="setTab('all',this)">Tout</div>
  <div class="tab" onclick="setTab('Outillage',this)">🔧 Outillage</div>
  <div class="tab" onclick="setTab('Jardinage',this)">🌿 Jardinage</div>
</div>
<div class="controls">
  <input type="text" id="search" placeholder="🔍 Rechercher (perceuse, tondeuse, bosch...)" oninput="filter()">
  <select id="sort" onchange="filter()">
    <option value="pct">Remise décroissante</option>
    <option value="date">Plus récents</option>
    <option value="price">Prix croissant</option>
  </select>
  <select id="store" onchange="filter()"><option value="">Toutes les boutiques</option></select>
</div>
<div class="grid" id="grid"></div>
<div class="footer">Dernière mise à jour : {now} • <a href="https://github.com/v7vbvryhc2-ai/deals-outillage" style="color:#60a5fa">GitHub</a></div>
<script>
const RAW={deals_json};
const deals=RAW.slice().reverse();
let activeTab='all';
const storeSelect=document.getElementById('store');
[...new Set(deals.map(d=>d.merch))].sort().forEach(s=>{{const o=document.createElement('option');o.value=s;o.textContent=s;storeSelect.appendChild(o)}});
function pctColor(p){{return p>=70?'#f97316':p>=50?'#ef4444':p>=40?'#dc2626':'#b91c1c'}}
function parsePrice(s){{if(!s)return 9999;return parseFloat(s.replace(/[^0-9,\.]/g,'').replace(',','.'))||9999}}
function setTab(t,el){{activeTab=t;document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));el.classList.add('active');filter()}}
function filter(){{
  const q=document.getElementById('search').value.toLowerCase();
  const sort=document.getElementById('sort').value;
  const store=document.getElementById('store').value;
  let f=deals.filter(d=>
    (activeTab==='all'||d.category===activeTab)&&
    (d.title.toLowerCase().includes(q)||d.merch.toLowerCase().includes(q))&&
    (!store||d.merch===store)
  );
  if(sort==='pct')f.sort((a,b)=>b.pct-a.pct);
  else if(sort==='date')f.sort((a,b)=>(b.date||'').localeCompare(a.date||''));
  else f.sort((a,b)=>parsePrice(a.price)-parsePrice(b.price));
  render(f);
}}
function render(list){{
  const grid=document.getElementById('grid');
  if(!list.length){{grid.innerHTML='<div class="empty">Aucun deal trouvé 🔍</div>';return}}
  const icon=d=>d.category==='Jardinage'?'🌿':'🔧';
  grid.innerHTML=list.map(d=>`
    <a href="${{d.link}}" target="_blank" class="card">
      ${{d.image?`<img class="card-img" src="${{d.image}}" alt="${{d.title}}" loading="lazy" onerror="this.style.display='none'">`:`<div class="placeholder">${{icon(d)}}</div>`}}
      <div class="badge-row">
        <span class="badge" style="background:${{pctColor(d.pct)}}">-${{d.pct}}%</span>
        <span class="cat-badge ${{d.category==='Jardinage'?'cat-jardinage':'cat-outillage'}}">${{icon(d)}} ${{d.category||'Outillage'}}</span>
      </div>
      <div class="card-body">
        <div class="card-title">${{d.title}}</div>
        <div class="card-meta"><span class="price">${{d.price||'?'}}</span><span class="merch">${{d.merch}}</span></div>
        ${{d.date?`<div class="card-date">📅 ${{d.date}}</div>`:''}}
        <span class="btn">Voir le deal →</span>
      </div>
    </a>`).join('');
  const all=deals;
  document.getElementById('total').textContent=list.length;
  document.getElementById('cnt-out').textContent=all.filter(d=>d.category==='Outillage').length;
  document.getElementById('cnt-jar').textContent=all.filter(d=>d.category==='Jardinage').length;
  const pcts=list.map(d=>d.pct).filter(Boolean);
  document.getElementById('best').textContent=(pcts.length?Math.max(...pcts):0)+'%';
  document.getElementById('shops').textContent=new Set(list.map(d=>d.merch)).size;
}}
filter();
</script></body></html>"""

# Main
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

print(f"\nTotal: {len(all_deals)} deals, {len(new)} nouveaux")

if new:
    new.sort(key=lambda x: x["pct"], reverse=True)
    out = [d for d in new if d.get("category") == "Outillage"]
    jar = [d for d in new if d.get("category") == "Jardinage"]
    msg = f"🔧🌿 Deals ≥30% - {now_str}\n\n"
    if out:
        msg += "🔧 OUTILLAGE\n"
        for d in out[:5]:
            msg += f"[-{d['pct']}%] {d['title'][:60]}\n{d['price']} chez {d['merch']}\n{d['link']}\n\n"
    if jar:
        msg += "🌿 JARDINAGE\n"
        for d in jar[:5]:
            msg += f"[-{d['pct']}%] {d['title'][:60]}\n{d['price']} chez {d['merch']}\n{d['link']}\n\n"
    reste = len(new) - len(out[:5]) - len(jar[:5])
    if reste > 0: msg += f"... et {reste} autres\n\n"
    msg += f"👉 https://v7vbvryhc2-ai.github.io/deals-outillage/"
    if len(msg) > 4000: msg = msg[:4000]
    print("Telegram:", tg(msg))

save_json(SEEN, list(seen)[-1000:])
save_json(HISTORY, history[-300:])
with open("index.html", "w", encoding="utf-8") as f:
    f.write(generate_html(history))
print(f"Dashboard: {len(history)} deals total")
