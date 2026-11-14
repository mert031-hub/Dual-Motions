# Dual-Motions araştırma prototipi

Metin tabanlı duygu tahmini, ayrı yanıt stratejisi kontrolü, LLM üretimi ve
Therapeutic Critic/revizyon zinciri. Tanı veya tedavi sistemi değildir.
Ana proje kapsamı ve bekleyen bilimsel kararlar: [araştırma kapsamı](docs/RESEARCH_SCOPE.md).
Dönem içi ilerleme, bulgular ve açık işler: [dönem notları](docs/DONEM_NOTLARI_KASIM.md).

## Kurulum ve yerel kullanım

Python 3.12 kullanın. Tam bağımlılık sürümleri ve paket hashleri `requirements.lock` içindedir.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python -m pytest -q
streamlit run app.py --server.headless=true --browser.gatherUsageStats=false
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt   # lock dosyası Linux içinse --require-hashes Windows'ta hata verebilir
python -m pytest -q
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

Hız sınırı (429): `llm_factory.call_with_retry` sağlayıcının `retry-after` süresini (yoksa
15/30/60 sn) bekleyip en fazla `RATE_LIMIT_RETRIES` (varsayılan 4) kez yeniden dener.
Bekleme `RATE_LIMIT_MAX_WAIT_S` (varsayılan 90 sn) üstündeyse (ör. günlük kota) beklenmez,
hata yukarı fırlar ve sistem güvenli tarafa düşer. Groq ücretsiz katman: 8000 TPM, 1000 RPD,
200K TPD.

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
python batch_tester.py --expert-only --no-pairs --case-ids X051,X052   # yalnız uzman etiketli vakalar
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

## Uzman etiketleri (durum: içe aktarıldı)

Etiketler klinisyen (Yavuz) tarafından verildi; farklılık olduğunda onun etiketi referanstır.
Güncel durum: 155 vakalık xlsx seti (46 pozitif / 109 negatif), eski 50 vaka (19/26, 5 belirsiz),
30 kontrol (0/30) ve 20 varyant (16/4); toplam 255 vakanın 250'si etiketli (81/169).
Eski 50 vakanın anahtar sözcükleri kural motorunun geliştirildiği vakalardır; **kural
recall'u için bağımsız ölçüm yalnızca 155'lik settir** (veri sızıntısı notu: dönem notları).

```bash
python labeling_tools.py export --out runtime/etiket_sablonu.xlsx
python xlsx_to_cases.py ...        # 155'lik xlsx şablonunu vakaya çevirme/kontrol (yardım: --help)
python labeling_tools.py import --in runtime/doldurulmus.xlsx --out cases_expert.json --labeler Yavuz
```

Eski risk seviyesi ve sistemin eylem eşlemesi etiketleyiciye gösterilmez. `BELİRSİZ`
eski etiketi `null` ile kaldırır; boş etiket eski kaydı değiştirmez. Hata varsa mevcut çıktı
dosyası korunur. Vaka metni değişmişse yeni kimlik gerekir; bilinçli düzeltmede
`--allow-message-change` açıkça seçilebilir. İçe aktarılan dosyayı kullanmak için
`CASES_EXPERT_JSON` değerini dosyanın mutlak yoluna ayarlayın. Etiket dosyaları
(`cases_expert.json`, `*.xlsx`, `etiketler/`) Git'e ve Docker imajına girmez.

Tek komutla sıradaki adımlar (Windows): `.\run_next.ps1` — etiket içe aktarma, testler ve
20 vakalık hibrit deneme.


## Ek deneyler ve klinisyen değerlendirmesi

- `hybrid_eval.py`: yalnızca triyaj düzeyinde kural–hibrit karşılaştırması (Policy/Critic
  çağrılmaz; vaka başına en çok 1 çağrı). Uzman etiketli vakalarda kural, hibrit-gevşek ve
  hibrit-sıkı recall ile yanlış alarm oranını Wilson aralıklarıyla, psikiyatrik/tıbbi/ergen
  alt gruplarına ayırarak yazar. Çıktı `runtime/hybrid_eval.csv` vaka metni içermez.
  Seçenekler: `--max-cases N`, `--sleep SN` (TPM için), `--resume` (kota dolduysa kaldığı yerden),
  `--out`. Semantik hata veren vakalar metriğe girmez ve ayrıca sayılır.
- `full_hybrid` ve `hybrid_triage_only`: kurallara ek semantik triyaj. Kuralların
  acil sonucu API beklemez; semantik katman kuralları düşürmez. Geçmiş/varsayımsal
  veya belirsiz sonuçlar güncel kriz kesinliği sayılmaz; kontrol sorusuna yönlendirilir.
  Semantik v2 her kategori için ayrı alıntı ve kişi/zaman olayı ister; genel alıntı listesi
  tek başına kategori kabul ettirmez. Bu teknik kanıt kontrolü klinik yorumun doğruluğunu kanıtlamaz.
  `triage_by_system.json` her sistem için iki görünüm içerir: `metrics` (belirsizlik bayrağı
  `uncertain_risk` da pozitif sayılır) ve `metrics_strict` (yalnızca kesin risk bayrakları);
  `n_uncertain_only` yalnızca belirsizlik bayrağı alan vakaları sayar. Ek hibrit triyaj deneyinde iki görünüm birlikte okunmalıdır; Recall/FNR/FPR ve belirsizlik sayısı birlikte değerlendirilir.
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

## Etiket bekleyen verilerle geliştirme

Yeni gelen vaka dosyalarını uygulamanın uzman veri havuzuna katmadan hazırlamak ve
mevcut deterministik triyaj davranışını kaydetmek için
[geliştirme havuzu yönergesini](docs/DEVELOPMENT_POOL.md) kullanın.
Kaynak renkleri uzman etiketi sayılmaz; bu yol klinik başarı metriği hesaplamaz.

İfade varyantlarını ana kuralları değiştirmeden incelemek ve dört kollu pilotu
planlamak/çevrimdışı denemek için [sonraki geliştirme adımlarına](docs/NEXT_DEVELOPMENT_STEPS.md)
bakın. Araştırmaya katkı için [klinisyen soru formu](docs/CLINICIAN_QUESTIONS.md) hazırdır.

Yüklenen 16 klinik PDF'nin belge bazında incelemesi, öneri/sayfa → kod eşlemesi ve kalan doğrulama gereksinimleri: [Klinik kanıt incelemesi](docs/CLINICAL_EVIDENCE_REVIEW.md). Ortak yanıt sınırları kılavuzlardan yararlanır; anahtar sözcük trijajı, LLM kararları ve H1/H2 rubriği klinik olarak doğrulanmış değildir.

Kaynak incelemesinden sonraki bağlam şeması, bağımsız etiketleme, Critic sınaması ve kör A/B/C/D değerlendirmesi için [doğrulama yol haritası taslağı](docs/VALIDATION_ROADMAP.md).

Bağlam şeması, kategoriye özel kanıt kontrolü, sentetik inceleme paketi ve kör puanlama formları: [doğrulama çalışma paketi](docs/VALIDATION_WORKBENCH.md). `python validation_workbench.py build` API çağrısı yapmadan boş formları ve sentetik geliştirme örneklerini oluşturur.

Son geliştirme turunun değişiklikleri, gözlenen kural açıkları ve doğrulama çıktıları: [revizyon raporu](docs/REVISION_REPORT_CONTEXT_VALIDATION.md).

Anahtar sözcük motoru `tr-context-rules.v1`: eşleşme, bağlam ve ihtiyaç yönlendirmesi ayrıldı. Kaynak dayanağı, karar sözleşmesi, önce/sonra örnekleri ve sınırlar: [anahtar sözcük motoru revizyonu](docs/KEYWORD_ROUTER_REVISION.md). `audit_rule_router.py` eski alt dizge motoruyla yeni motoru aynı kayıtlarda, klinik doğruluk iddiası üretmeden karşılaştırır.

Groq anahtarı/ağ ayarları ve dört sentetik örnekle küçük canlı bağlam denemesi: [canlı API deneme yönergesi](docs/LIVE_SEMANTIC_DEMO.md). `python live_semantic_demo.py` yalnız hazırlık kontrolü; `--live` gerçek API çağrılarıdır.

3 Kasım tarihli klinik Excel incelemesi, kanıt/atıf kontrolleri ve yeni alan bazında Excel çalışma yolu: [gelen Excel değerlendirme raporu](docs/EXCEL_REVIEW_2026-11-03.md). `submitted_review.py` ham değerlendirmeleri geliştirme verisi olarak bağlar; `context_workbook.py` doldurulan alan/kanıt formlarını doğrular. Serbest açıklamalar otomatik uzman etiketi değildir.

Slayttaki mimari için 20 çıktılık sınırlı A/B/C/D pilotu, kör insan değerlendirme hazırlığı ve canlı ortam gereksinimleri: [pilot çalışma raporu](docs/SLIDE_PILOT_2026-11-03.md). `python slide_pilot.py offline` altyapı provasıdır; `live` gerçek API çağrıları yapar.
