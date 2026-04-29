"""
CX Intelligence - merkezi yapılandırma.
Tüm sabitler ve RSS/Tavily konfigürasyonu buradan yönetilir.
"""

# CX / çağrı merkezi odaklı arama başlıkları (ileride Tavily/embeddings ile kullanılabilir)
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
    "voc voice of customer",
    "customer journey",
    "CCaaS",
    "contact center AI",
    "workforce management WFM",
    "customer churn retention",
    "CX analytics VOC",
]

# Bu puanın altındaki içerikler e-postaya dahil edilmez
MIN_SCORE_TO_SEND = 5

# Günlük özetde en fazla kaç içerik gösterilecek
MAX_ITEMS_PER_EMAIL = 20

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
]

# Claude model — güncel liste: https://docs.anthropic.com/en/docs/about-claude/models/overview
# Eski tarihli snapshot'lar (ör. claude-3-5-sonnet-20240620) API'de 404 döner.
CLAUDE_MODEL = "claude-sonnet-4-6"

# Puanlama için tek istekte işlenecek içerik sayısı
SCORER_BATCH_SIZE = 10
