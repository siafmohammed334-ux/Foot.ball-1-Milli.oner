"""يولّد أسئلة جديدة كل يوم، مبنية على أخبار كرة القدم الحالية + معلومات ثابتة متنوعة.
بيحفظها في questions/YYYY-MM-DD-N.json ويحدّث questions/manifest.json"""
import datetime, json, os, re, sys, glob, random, urllib.request

CALLS = int(os.environ.get("CALLS", "3"))         # عدد مرات الطلب في اليوم
PER_CALL = int(os.environ.get("PER_CALL", "50"))  # أسئلة في كل طلب  (3×50 = 150 يومياً)
MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
API_KEY = os.environ["ANTHROPIC_API_KEY"]
TODAY = datetime.date.today()

TOPICS = [
    "كأس العالم (تاريخ، هدافين، نهائيات)", "دوري أبطال أوروبا", "الدوري الإنجليزي الممتاز",
    "الدوري الإسباني وريال مدريد وبرشلونة", "الدوري الإيطالي والألماني والفرنسي",
    "الأهلي والزمالك والدوري المصري", "المنتخب المصري ومحمد صلاح", "كأس الأمم الأفريقية ومنتخبات أفريقيا",
    "كأس آسيا والدوريات العربية والسعودي", "كوبا أمريكا وكأس أمم أوروبا", "أساطير اللاعبين (ميسي، رونالدو، مارادونا، بيليه)",
    "المدربون الكبار", "الأرقام القياسية والبطولات", "الانتقالات والصفقات الكبرى", "الكرة الذهبية والجوائز الفردية",
    "الملاعب والأندية وتاريخها", "قواعد اللعبة والتحكيم", "أهداف وأحداث لا تُنسى في تاريخ الكرة",
]

def norm(t):
    t = re.sub(r"[\u064B-\u0652\u0640]", "", t)
    t = re.sub(r"[إأآا]", "ا", t).replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"[^\w\s]", " ", t).split()

def valid(r):
    return (isinstance(r, list) and len(r) == 6
            and all(isinstance(x, str) and x.strip() for x in r[:5])
            and len({x.strip() for x in r[1:5]}) == 4 and r[5] in (1, 2, 3))

def load_all():
    qs = json.load(open("questions.json", encoding="utf-8"))
    for f in sorted(glob.glob("questions/20*.json")):
        qs += json.load(open(f, encoding="utf-8"))
    return qs

def ask(topics, sample):
    prompt = f"""اليوم هو {TODAY.isoformat()}. اكتب {PER_CALL} سؤال اختيار من متعدد عن كرة القدم للرجال فقط، بالعربية، لمسابقة "من سيربح المليون".
المحاور اليوم: {" + ".join(topics)}.
ابحث أولاً على الإنترنت عن آخر أخبار ونتائج وأحداث كرة القدم (آخر أسبوعين) واكتب منها حوالي ثلث الأسئلة، وباقي الأسئلة معلومات ثابتة ومؤكدة.
قواعد صارمة:
- المعلومة لازم تكون صحيحة ومؤكدة 100% (لو مش متأكد اتركها)، وإجابة واحدة صحيحة فقط، و3 خيارات غلط منطقية ومختلفة.
- أي سؤال عن حدث حالي لازم يحدد الموسم أو التاريخ في صياغته (مثال: "في موسم 2026/27" أو "حتى أكتوبر 2026") عشان يفضل صحيح بعد ما الأخبار تتغير.
- المستويات: 1 متوسط، 2 بين المتوسط والصعب، 3 صعب شوية لكن مشهور (توزيع تقريبي 35% / 40% / 25%).
- نوّع الأفكار ولا تكرر نفس الفكرة بصيغ مختلفة. ولا تكرر هذه الأسئلة: {json.dumps(sample, ensure_ascii=False)}
الصيغة النهائية: ضع القائمة داخل <json></json> فقط، كل عنصر: ["السؤال","الإجابة الصحيحة","خطأ1","خطأ2","خطأ3",المستوى]"""
    body = {"model": MODEL, "max_tokens": 20000,
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}],
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
        headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    resp = json.load(urllib.request.urlopen(req, timeout=600))
    text = "".join(b.get("text", "") for b in resp["content"] if b.get("type") == "text")
    m = re.findall(r"<json>(.*?)</json>", text, re.S)
    if not m:
        return []
    raw = re.sub(r"^```(?:json)?|```$", "", m[-1].strip(), flags=re.M).strip()
    return json.loads(raw)

def main():
    existing = load_all()
    seen_exact = {" ".join(norm(q[0])) for q in existing}
    recent_sets = [set(norm(q[0])) for q in existing[-20000:]]
    sample = [q[0] for q in random.sample(existing, min(40, len(existing)))]
    base = TODAY.toordinal() * CALLS
    files = []
    for n in range(CALLS):
        topics = [TOPICS[(base + n * 2) % len(TOPICS)], TOPICS[(base + n * 2 + 1) % len(TOPICS)]]
        try:
            new = ask(topics, sample)
        except Exception as e:
            print("call failed:", e); continue
        keep = []
        for r in new:
            if not valid(r):
                continue
            r = [x.strip() for x in r[:5]] + [r[5]]
            key = " ".join(norm(r[0])); ws = set(key.split())
            if key in seen_exact:
                continue
            if any(len(ws & o) / max(1, len(ws | o)) > 0.7 for o in recent_sets):  # شبه مكرر
                continue
            seen_exact.add(key); recent_sets.append(ws); keep.append(r)
        if keep:
            name = f"{TODAY.isoformat()}-{n + 1}.json"
            json.dump(keep, open("questions/" + name, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
            files.append(name); print(name, len(keep))
    if not files:
        sys.exit("no questions added")
    man = json.load(open("questions/manifest.json"))
    man["files"] = man.get("files", []) + [f for f in files if f not in man.get("files", [])]
    json.dump(man, open("questions/manifest.json", "w"), separators=(",", ":"))

if __name__ == "__main__":
    main()
