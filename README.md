# Dual-Motions araştırma prototipi

Metin tabanlı duygu tahmini, ayrı yanıt stratejisi kontrolü, LLM üretimi ve
Therapeutic Critic/revizyon zinciri. Tanı veya tedavi sistemi değildir.
Ana proje kapsamı ve bekleyen bilimsel kararlar: [araştırma kapsamı](docs/RESEARCH_SCOPE.md).

## Kurulum ve yerel kullanım

Python 3.12 kullanın. Tam bağımlılık sürümleri ve paket hashleri `requirements.lock` içindedir.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python -m pytest -q
streamlit run app.py --server.headless=true --browser.gatherUsageStats=false
```

Arayüz, kural triyajı ve testler anahtarsız çalışır. Canlı model çağrıları için
`GROQ_API_KEY` güvenli ortam ayarlarında tanımlanmalı ve `api.groq.com` HTTPS erişimi
sağlanmalıdır. Anahtarı kaynak koduna, Git'e veya sohbet/log çıktısına yazmayın.
Girdi uzunluk sınırını aşarsa metnin sonundaki risk sinyallerini sessizce kesmek
yerine istek açık hata ve insan incelemesi işaretiyle durdurulur.

`MODEL_NAME`, `CRITIC_MODEL`, `AFFECT_MODEL`, `SEMANTIC_MODEL`, `MEMORY_MODEL` ayrı
seçilebilir. `JUDGE_MODELS` virgülle ayrılmış model listesidir. Yargıç ile üretim/Critic
aynı veya ilişkili ailedeyse bağımsızlık varsaymayın. Mevcut varsayılan yargıç tek modeldir;
farklı bir model ailesi araştırmacı tarafından seçilip doğrulanmalıdır.

Arayüzde duygu kaynağı açıkça seçilir:

- `manual`: araştırmacının verdiği deney koşulu; otomatik tahmin sayılmaz.
- `model`: metinden valence/arousal/emotion tahmini; belirsizlikte kesin duygu iddiası kurulmaz.

## Ana deney ve kayıtlar

Slayttaki A/B/C/D: `study_baseline`, `study_policy`, `study_critic`, `study_full`.
Temel üretim prompt'u, sıcaklık ve deterministik acil kapısı aynıdır. Policy ve Critic
ayrı açılıp kapanır. Acil sabit yanıtlar duygu-policy etkisinin ana analizinden ayrılır.
Eski `full`, `triage_only`, `critic_only`, `policy_only`, `vanilla` kolları geriye dönük
ve ek deneyler içindir; slayt ablasyonuyla aynı kabul edilmemelidir.

```bash
python batch_tester.py --max-cases 5 --workers 2 --affect-mode model
python research_report.py runtime/benchmark_runs/KOŞU_KLASÖRÜ
```

İlk komut gerçek API çağrısı yapar. Anahtar olmadan üretilen teknik yedek yanıtlar
başarılı canlı test sayılmaz. Eksik bileşen/yargıç değerlendirmesi komutun başarısız
çıkış koduna ve manifestte ayrı sayımlara yansır. Varsayılan `manual` moduyla çalışma,
metinden duygu tahminini doğrulamaz.

Kayıtlar varsayılan `runtime/benchmark_runs` altındadır; `BENCHMARK_OUT_DIR` veya
`RESEARCH_DATA_DIR` ile değiştirilebilir. Çalışma dizinindeki eski raporun üzerine yazılmaz.
`triage_metrics.csv` kural referansıdır; gerçek sistem çıktılarından hesaplanan ve
etiket kaynağına göre ayrılan sonuçlar `triage_by_system.json` içindedir. Model hataları
ve belirsizlikler ayrıca sayılır. Aynı vakanın tekrarları eşleştirilmiş analizde bağımsız
örnek sayılmaz; ilişkili varyant aileleri için ek analiz planı hâlâ gerekir.

Varsayılan disk çıktıları metinsizdir. Yalnızca onaylı sentetik veride
`--persist-text` kullanın. Model adları, kaynak kod hash'i, commit, bağımlılık sürümleri,
duygu modu ve sistem parametreleri manifestte tutulur. Raporlar keşifseldir; klinik başarı,
istatistiksel anlamlılık veya hipotezlerin doğrulandığı iddiasını otomatik üretmez.

## Arkadaştan beklenen etiketler

50 özgün vaka `cases_legacy.py` içine içerik değiştirilmeden geri alındı.
`risk_level`, `expected_red_flag` yerine kullanılmaz. Uzman etiketleri veya risksiz
kontrol vakaları proje tarafından uydurulmaz. 14 sentetik başlangıç vakası yalnızca
altyapı denemesi içindir ve uzman vakalarından ayrı raporlanır.

```bash
python labeling_tools.py export --out runtime/etiket_sablonu.xlsx
python labeling_tools.py import --in runtime/doldurulmus.xlsx --out runtime/cases_expert.json --labeler REVIEWER_KODU
```

Şablon 50 özgün vaka, 30 boş kontrol ve 20 boş varyant satırı içerir; etiketler boştur.
Eski risk seviyesi ve sistemin eylem eşlemesi etiketleyiciye gösterilmez.
`BELİRSİZ` eski etiketi `null` ile kaldırır; boş etiket eski kaydı değiştirmez.
Hata varsa mevcut çıktı dosyası korunur. Vaka metni değişmişse yeni kimlik gerekir;
bilinçli düzeltmede `--allow-message-change` açıkça seçilebilir.
İçe aktarılan dosyayı kullanmak için `CASES_EXPERT_JSON` değerini dosyanın mutlak yoluna ayarlayın.

## Ek deneyler ve klinisyen değerlendirmesi

- `full_hybrid` ve `hybrid_triage_only`: kurallara ek semantik triyaj. Kuralların
  acil sonucu API beklemez; semantik katman kuralları düşürmez. Geçmiş/varsayımsal
  veya belirsiz sonuçlar güncel kriz kesinliği sayılmaz; kontrol sorusuna yönlendirilir.
- Yapılandırılmış bellek varsayılan kapalıdır; etkinleştirilirse ek model çağrısı yapar.
  Yalnızca alıntıyla desteklenen hasta beyanları oturumda tutulur; risk kayıtları zaman
  geçti veya sonraki mesaj sakin diye kendiliğinden silinmez.
- `baseline.py --train TRAIN.json --test HOLDOUT.json --out runtime/baseline.json`:
  TF-IDF + Logistic Regression. Her iki sınıf, atıflı uzman etiketleri ve bağımsız
  holdout zorunludur. Aynı metin/varyant ailesinin train ve test arasında sızması engellenir.
- `critic_experiment.py --examples DRAFTS.json --models MODEL1,MODEL2 --reference MODEL1 --out runtime/critics.json`:
  aynı sabit taslaklarda Critic karşılaştırması. Örnek dosyası `{id, state: {user_input,
  policy_draft, ...}}` kayıtlarından oluşur. Referans model klinik gerçek değildir.
  `--pricing PRICES.json` model başına `input_per_million`/`output_per_million` sağlar.
  Sağlayıcı token kullanımı veya güncel fiyat eksikse maliyet boş kalır; başarılı
  isteğin gözlenen maliyeti başarısız deneme/retry maliyetlerini kapsamaz.
  Sabit taslaklara ayrıca `expected_reject` ve `labeler` sağlanırsa uzman reddiyle
  karşılaştırma ayrı hesaplanır; etiket yokken klinik güvenlik kaybı uydurulmaz.

Metin kaydına izin verilmiş sentetik bir koşudan kör paket hazırlama:

```bash
python clinician_review.py export runtime/benchmark_runs/KOŞU --out runtime/review_packet.json
streamlit run review_app.py --server.headless=true --browser.gatherUsageStats=false
python clinician_review.py agreement --ratings runtime/review_ratings.json --mapping runtime/review_packet.mapping.json --out runtime/agreement.json
```

Değerlendiriciye yalnızca paket ve ayrı değerlendirme arayüzü verilir; özel eşleme
dosyası koordinatörde kalır. Bu yanıt puanları, vaka kırmızı bayrak etiketlerinden ayrıdır.
Puanlanmamış alanlar sıfır veya olumlu puanla doldurulmaz. Sabit kategori durumunda
kappa tanımsızdır; mükemmel klinik uyum diye sunulmaz.
Ölçek dışındaki model puanları 1–5 aralığına kırpılarak kabul edilmez; şema doğrulaması başarısız olur.
Yargıç bütün rubrik alanlarını döndürmelidir. Gerçekten puanlanamayan alan açık `null`
olabilir; bu kayıtlar `n_judge_incomplete` ile sayılır ve benchmark eksiksiz başarılı sayılmaz.

## Dağıtım

```bash
python app_auth.py
# Üretilen parola hash'ini APP_PASSWORD_HASH güvenli ortam değişkenine kaydedin.
docker compose up --build
```

Docker root olmayan kullanıcıyla çalışır ve parola ayarı yokken uygulama içeriğini açmaz.
Yerel geliştirmede kapı varsayılan kapalıdır; `APP_REQUIRE_AUTH=1` ile zorunlu kılınabilir.
Parola kapısı TLS/kurumsal kimlik yönetimi yerine geçmez. [Veri politikası](data_policy.md)
klinik ve yönetsel onay bekleyen taslaktır.

Kurumsal/bulut CA sertifikası gerekiyorsa doğrulamayı kapatmayın. Güvenilir CA
paketini yalnızca derleme süresince bağlayın:

```bash
docker build --secret id=build_ca,src=/GUVENILIR/CA/PAKETI.pem -t dual-motions:research .
```

Çalışma zamanı dış API çağrıları için aynı güven yapılandırması gerekiyorsa CA'yı
salt okunur bağlayıp `SSL_CERT_FILE` değerini konteyner içindeki yola ayarlayın.
Bağımlılık yenileme: `uv pip compile --python-version 3.12 --generate-hashes requirements.txt -o requirements.lock`.
