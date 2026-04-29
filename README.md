# Günlük CX & Çağrı Merkezi Intelligence E-posta Sistemi

Her sabah (GitHub Actions ile Türkiye saati ~07:00) RSS akışları ve Tavily web aramasından çağrı merkezi / CX içerikleri toplanır; Anthropic Claude ile puanlanır; mükerrerler Google Sheets’te kontrol edilir; seçilen içerikler Resend ile HTML e-posta olarak gönderilir.

## Özellikler

- **Toplama:** `feedparser` ile `config.py` içinde listelenen (**≈57**) RSS akışı + `tavily-python` ile önceden tanımlı sorgular.
- **Puanlama:** `claude-haiku-4-5-20251001` (grup başına `SCORER_BATCH_SIZE` kadar öğe; `config.py` üzerinden ayarlanır).
- **Kalıcı kayıt:** Service account ile Google Sheets (`Sent Items`) üzerinden URL mükerrer kontrolü ve gönderim günlüğü (AI alanları dahil).
- **E-posta:** Resend API ile responsive, inline CSS HTML gövdesi ve puana göre renk kodlu rozetler.

## Gereksinimler

- Python **3.11+**
- Ücretli/ücretsiz API anahtarları: Anthropic, Tavily, Resend
- Google Cloud **service account** ve bir Google Sheets tablosu

## Kurulum (adım adım)

### 1. Repoyu klonlayın veya içeriği kopyalayın

Bu klasörün içeriği (`main.py`, `config.py`, vb.) GitHub deposunun **kök dizininde** olmalıdır. Yani ürettiğimiz `cx-intelligence` klasörü bir paket adıdır; push ederken dosyaları doğrudan repo köküne yerleştirin veya bu klasör içinde `git init` yaparak `.git` kökünün `main.py` ile aynı seviyede olduğundan emin olun.

**GitHub Actions:** Workflow dosyası `/.github/workflows/daily_email.yml` olarak **depo kökünde** bulunmalıdır (bu projede `.github` klasörü zaten bunun için yerinde).

Monorepo kullanıyorsanız ve kaynak kod `cx-intelligence/` alt klasöründe duruyorsa, workflow’a `defaults.run.working-directory: cx-intelligence` ekleyin ve cache satırında `cx-intelligence/requirements.txt` kullanın.

### 2. Sanal ortam ve bağımlılıklar

```bash
cd cx-intelligence
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Anthropic API anahtarı

1. [Anthropic Console](https://console.anthropic.com) üzerinden hesap oluşturun veya giriş yapın.
2. API Keys bölümünden yeni anahtar oluşturun.
3. Anahtarı `.env` içinde `ANTHROPIC_API_KEY` olarak saklayın.

### 4. Tavily API anahtarı

1. [tavily.com](https://tavily.com) üzerinden kayıt olun.
2. API anahtarını alın ve `.env` içinde `TAVILY_API_KEY` olarak ekleyin.

### 5. Resend ile e-posta

1. [resend.com](https://resend.com) hesabı açın ve domain doğrulamasını tamamlayın (gönderen adres için).
2. API anahtarını oluşturun.
3. `.env` içinde şunları doldurun: `RESEND_API_KEY`, `RESEND_FROM_EMAIL` (doğrulanmış gönderen), `RESEND_TO_EMAIL` (alıcı; virgülle birden fazla adres yazılabilir).

### 6. Google Cloud service account ve Sheets

1. [Google Cloud Console](https://console.cloud.google.com) içinde bir proje seçin veya oluşturun.
2. **APIs & Services → Enable APIs** bölümünden **Google Sheets API** ve **Google Drive API**’yi etkinleştirin (Drive, paylaşılan dosyaya erişim için gereklidir).
3. **IAM & Admin → Service Accounts** ile bir service account oluşturun.
4. Bu hesap için **JSON anahtarı** indirin (kimlik bilgisi dosyası).
5. Google Sheets’te yeni bir tablo oluşturun; ilk sekmenin adı **`Sent Items`** olmalıdır (ilk çalıştırmada otomatik oluşturulabilir; ilk satır başlıkları `URL`, `Title`, `Score`, `Date Sent`, `Source`, `Category`, `Summary (AI)`, `Why Relevant (AI)`, `Read Time (AI)` şeklinde yazılır).
6. Tabloyu service account e-postasıyla **Editör** olarak paylaşın (`client_email` alanı JSON içindedir).
7. Tablonun kimliğini URL’den kopyalayın (`GOOGLE_SHEET_ID`).
8. JSON dosyasının **tam içeriğini** tek satırda `.env` içinde `GOOGLE_SERVICE_ACCOUNT_JSON={...}` olarak saklayın.

### 7. Ortam değişkenleri

`.env.example` dosyasını `.env` olarak kopyalayın ve değerleri doldurun:

```bash
cp .env.example .env
```

`.env` dosyasını **asla** git’e eklemeyin.

### 8. Yerel test

```bash
source .venv/bin/activate
python main.py
```

Terminalde her adım Türkçe günlük olarak görünür.

### 9. GitHub Secrets ve zamanlama

Depoda **Settings → Secrets and variables → Actions** bölümünde şu secret’ları oluşturun:

| Secret | Açıklama |
|--------|-----------|
| `ANTHROPIC_API_KEY` | Claude API anahtarı |
| `TAVILY_API_KEY` | Tavily anahtarı |
| `RESEND_API_KEY` | Resend anahtarı |
| `RESEND_FROM_EMAIL` | Gönderen e-posta |
| `RESEND_TO_EMAIL` | Alıcı e-posta(ları) |
| `GOOGLE_SHEET_ID` | Tablo kimliği |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | JSON’un tam metni (tek satır) |

JSON secret’ını yapıştırırken kaçış karakterlerinin bozulmadığından emin olun; sorun yaşanırsa tek satır JSON’u doğrudan Raw olarak yapıştırın.

### 10. Actions’ı etkinleştirme

**Actions** sekmesinden workflow’un etkin olduğundan ve varsayılan dalınızda `.github/workflows/daily_email.yml` dosyasının bulunduğundan emin olun.

Varsayılan zamanlama: **Her gün 04:00 UTC** — Türkiye saati ile yaklaşık **07:00** (TRT, UTC+3).

### 11. Manuel tetikleme

GitHub’daki workflow sayfasından **Run workflow** ile `workflow_dispatch` üzerinden manuel çalıştırabilirsiniz.

## Yapılandırma sabitleri

`config.py` içinde RSS listesi, Tavily sorguları, `MIN_SCORE_TO_SEND`, `MAX_ITEMS_PER_EMAIL` ve konu başlıkları düzenlenebilir.

## Sorun giderme

- **Sheets “permission denied”:** Tabloyu service account ile paylaştığınızdan ve iki API’nin etkin olduğundan emin olun.
- **Resend gönderim hatası:** Gönderen domain ve SPF/DKIM doğrulamasını kontrol edin.
- **RSS boş:** Bazı kaynaklar geçici olarak engelleyebilir; günlüklerde hangi akışın atlandığı yazılır.
- **Tüm içerikler aynı rozette (ör. yalnızca 🟡 İLGİNİ ÇEKEBİLİR):** `scorer.py` içinde Claude’dan gelen puan okunmuyorsa bu görülebilir. `config.py` içindeki `MIN_SCORE_TO_SEND` değerini kontrol edin ve GitHub Actions (veya yerel) günlüklerinde `ortalama puan=` satırını arayın.

## Lisans

İç kullanım ve özelleştirme için projeyi özgürce kullanabilirsiniz.
