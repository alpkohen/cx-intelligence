"""
CX Intelligence - merkezi yapılandırma.
Tüm sabitler ve RSS/Tavily konfigürasyonu buradan yönetilir.
"""

# CX / çağrı merkezi odaklı arama konuları (Tavily ve bağlam için referans)
TOPICS = [
    "call center",
    "contact center",
    "customer experience",
    "CX",
    "customer service",
    "müşteri deneyimi",
    "çağrı merkezi",
    "customer success",
    "NPS",
    "CSAT",
    "voice of customer",
    "customer journey",
    "CCaaS",
    "contact center AI",
    "workforce management",
]

# Bu puanın altındaki içerikler e-postaya dahil edilmez
MIN_SCORE_TO_SEND = 5

# Günlük özetde en fazla kaç içerik gösterilecek
MAX_ITEMS_PER_EMAIL = 20

# RSS kaynakları (sektör blogları, Reddit, akademik akış vb.)
RSS_FEEDS = [
    # === SEKTÖRÜN EN İYİ KAYNAKLARI ===
    "https://www.cxnetwork.com/rss/articles",
    "https://www.cxnetwork.com/rss/cx-reports",
    "https://www.cxnetwork.com/rss/news",
    "https://www.cxtoday.com/feed/",
    "https://customerthink.com/feed/",
    "https://cxm.co.uk/feed/",
    "https://www.customerexperiencedive.com/feeds/news.rss",
    "https://www.callcentrehelper.com/articles/feed",
    "https://www.sqmgroup.com/rss/blog",
    # === DÜŞÜNCE LİDERLERİ ===
    "https://hyken.com/blog/feed/",
    "https://blakemichellemorgan.com/feed/",
    "https://adrianswinscoe.com/feed/",
    "https://www.stevenvanbelleghem.com/blog/rss.xml",
    # === PLATFORM BLOĞLARI ===
    "https://www.zendesk.com/blog/feed/",
    "https://www.genesys.com/blog/rss",
    "https://www.sprinklr.com/blog/feed/",
    "https://www.qualtrics.com/blog/feed/",
    "https://www.forrester.com/blogs/feed/",
    "https://callminer.com/blog/feed/",
    "https://www.nextiva.com/blog/feed/",
    # === CALL CENTER ODAKLI ===
    "https://www.customerserv.com/blog/rss.xml",
    "https://www.strategiccontact.com/blog/feed/",
    # === REDDIT ===
    "https://www.reddit.com/r/callcenter/.rss",
    "https://www.reddit.com/r/customerservice/.rss",
    "https://www.reddit.com/r/CustomerSuccess/.rss",
    # === AKADEMİK ===
    "https://arxiv.org/rss/cs.HC",
]

# Tavily arama sorguları (web üzerinden güncel içerik)
TAVILY_QUERIES = [
    "call center customer experience research report 2025",
    "contact center AI automation trends",
    "CX technology industry analysis",
    "customer service workforce management report",
    "NPS CSAT contact center benchmark study",
    "CCaaS cloud contact center news",
]

# Claude model (3.5 Sonnet)
CLAUDE_MODEL = "claude-3-5-sonnet-20240620"

# Puanlama için tek istekte işlenecek içerik sayısı
SCORER_BATCH_SIZE = 10
