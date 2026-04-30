"""
CX Intelligence - merkezi yapılandırma.
Tüm sabitler ve RSS/Tavily konfigürasyonu buradan yönetilir.
"""

# Her RSS kaynağından alınacak maksimum içerik sayısı (tek kaynağın listeyi doldurmasını önler)
RSS_MAX_ITEMS_PER_FEED = 3

# Bu puanın altı katman seçiminde üçüncü kademeye girmezken, günlük akışın ilk filtresinde
# artık `scorer.get_threshold()` kullanılır (standart: DEFAULT_SCORE_THRESHOLD, T1/T2_weekly: TIER1_SCORE_THRESHOLD).
MIN_SCORE_TO_SEND = 5

# Katmanlı içerik seçimi:
# 9-10 puan alanlar her zaman dahil (sınırsız)
# 7-8 puan: en fazla bu kadar
MAX_TIER2_ITEMS = 10
# 5-6 puan: en fazla bu kadar
MAX_TIER3_ITEMS = 5

# RSS kaynakları.
# Not: IDC Gartner vb. tam raporlar çoğu zaman ücret kapısı arkasındadır; günlükte genelde kamuya
# açık blog/duyuru/özet yakalanır. Birçok büyük site RSS kapatır ya da bot engeller — doğrulanan uçları tuttuk.
RSS_FEEDS = [
    # === CX MEDYA & TOPLULUK ===
    "https://www.cxnetwork.com/rss/articles",
    "https://www.cxnetwork.com/rss/cx-reports",
    "https://www.cxnetwork.com/rss/news",
    "https://www.cxtoday.com/feed/",
    "https://customerthink.com/feed/",
    "https://cxm.co.uk/feed/",
    "https://diginomica.com/feed/",
    "https://techcrunch.com/tag/customer-experience/feed/",
    "https://www.customerexperiencedive.com/feeds/news.rss",
    "https://www.callcentrehelper.com/articles/feed",
    "https://www.sqmgroup.com/rss/blog",
    # === ANALİST & ENTERPRİSE YAYIN RSS (kamuya açık duyuru/analiz) ===
    "https://www.forrester.com/blogs/feed/",
    "https://www.cio.com/feed/",
    # === PLATFORM & CX PLATFORM ŞİRKETLERİ ===
    "https://blog.hubspot.com/service/rss.xml",
    "https://blog.hubspot.com/customers/rss.xml",
    "https://www.salesforce.com/blog/feed/",
    "https://www.intercom.com/blog/feed/",
    "https://www.zendesk.com/blog/feed/",
    "https://www.genesys.com/blog/rss",
    "https://www.sprinklr.com/blog/feed/",
    "https://www.qualtrics.com/blog/feed/",
    "https://callminer.com/blog/feed/",
    "https://www.nextiva.com/blog/feed/",
    "https://www.ringcentral.com/us/en/blog/feed/",
    "https://blog.medallia.com/feed/",
    "https://blogs.perficient.com/feed/",
    # === DÜŞÜNCE LİDERLERİ ===
    "https://hyken.com/blog/feed/",
    "https://blakemichellemorgan.com/feed/",
    "https://adrianswinscoe.com/feed/",
    "https://www.stevenvanbelleghem.com/blog/rss.xml",
    # === CALL CENTER ODAKLI ===
    "https://www.customerserv.com/blog/rss.xml",
    "https://www.strategiccontact.com/blog/feed/",
    # === REDDIT ===
    "https://www.reddit.com/r/callcenter/.rss",
    "https://www.reddit.com/r/customerservice/.rss",
    "https://www.reddit.com/r/CustomerSuccess/.rss",
    # === AKADEMİK ===
    "https://arxiv.org/rss/cs.HC",
    # === BÜYÜK CCaaS PLATFORMLARI (eksik vendorlar) ===
    "https://www.nice.com/blog/rss",
    "https://www.five9.com/blog/rss",
    "https://www.talkdesk.com/blog/feed/",
    "https://www.avaya.com/blogs/feed/",
    "https://www.8x8.com/blog/rss",
    "https://www.verint.com/blog/rss",
    "https://blog.webex.com/feed/",
    # === WORKFORCE MANAGEMENT ===
    "https://www.calabrio.com/wfo/resource/blog/feed/",
    "https://workforce.nice.com/blog/rss",
    # === AI / CONVERSATIONAL AI ===
    "https://www.observe.ai/blog/rss.xml",
    "https://yellow.ai/blog/feed/",
    "https://cresta.com/blog/feed/",
    # === SEKTÖR ETKİNLİKLERİ & YAYINLAR ===
    "https://www.nojitter.com/rss.xml",
    "https://www.icmi.com/rss",
    "https://www.customercontactweekdigital.com/rss",
    # === SEYAHAT / HAVACILIK CX ===
    "https://skift.com/feed/",
    "https://simpleflying.com/feed/",
    # === MEDIUM TAG ===
    "https://medium.com/feed/tag/customer-experience",
    "https://medium.com/feed/tag/contact-center",
]

# Tavily: araştırma duyuruları, analist özeti haberleri, benchmark haberleri
# Tam PDF içerikler genelde aboneliktir; arama özeti/link + basın çıkışına düşer.
TAVILY_QUERIES = [
    "Gartner Forrester IDC customer experience contact center report 2026",
    "Gartner Magic Quadrant CCaaS customer service CX",
    "Forrester Wave customer service contact center CX platform evaluation",
    "IDC Worldwide customer experience CX market forecast report",
    "McKinsey customer experience personalization loyalty banking retail research insight",
    "Deloitte EY customer contact workforce transformation CX report",
    "PwC Bain customer expectation digital omnichannel CX study",
    "Harvard Stanford MIT customer experience CX strategy research publication",
    "Stanford HCI customer service conversational AI usability research paper",
    "call center contact center benchmarking KPI staffing research report",
    "contact center GenAI orchestration autonomous agent CX trend",
    "voice of customer VOC analytics enterprise XM Qualtrics Medallia",
    "NPS CSAT CES customer loyalty churn benchmark methodology industry",
    "CCaaS cloud contact center IPO funding market news consolidation",
    "EC261 airline customer service complaint handling contact center best practice",
    "BPO outsourcing customer service contact center market trends report 2026",
    "contact center training certification industry L&D learning development",
    "customer effort score CES friction reduction digital channel deflection",
    "AI agent orchestration autonomous customer service resolution rate benchmark",
    "Talkdesk Five9 NICE Verint CCaaS product update release announcement 2026",
    "customer service burnout agent wellbeing attrition contact center workforce",
]

# Tier-1 Tavily targeted sources (premium / analyst — günlük collect_all ile eklenir)
TIER1_TAVILY_QUERIES = [
    "site:gartner.com CX OR contact center OR customer experience",
    "site:forrester.com customer experience OR contact center",
    "site:mckinsey.com customer service OR customer experience",
    "site:pwc.com customer experience report OR whitepaper",
    "site:deloitte.com contact center OR customer experience whitepaper",
    "site:dimensiondata.com CX OR contact center benchmark",
    "site:cxnetwork.com report OR whitepaper OR research",
    "site:hbr.org customer experience OR service",
    "site:accenture.com customer experience report OR whitepaper",
    "site:capgemini.com customer experience OR contact center research",
]

# Haftalık derin rapor/beyaz kâğıt sorguları — weekly_deep_scan ile (scheduler Pazartesi)
WEEKLY_DEEP_QUERIES = [
    "CX whitepaper 2025",
    "contact center research report 2025",
    "customer experience benchmark 2025",
    "AI customer service whitepaper 2025",
    "workforce management contact center report 2025",
]

TIER1_SCORE_THRESHOLD = 6  # T1 ve T2_weekly kaynakları için minimum puan filtresi
DEFAULT_SCORE_THRESHOLD = 7  # Normal RSS ve standart Tavily içeriği için

# Puanlama için Haiku yeterli ve ~10x daha ucuzdur. Derin analiz gerekirse claude-sonnet-4-6 kullanılabilir.
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Puanlama için tek istekte işlenecek içerik sayısı
SCORER_BATCH_SIZE = 8

# LinkedIn e-posta bölümündeki copy-paste etiketi
LINKEDIN_SECTION_LABEL = "Alp LinkedIn projesine kopyala-yapıştır ile işle"
