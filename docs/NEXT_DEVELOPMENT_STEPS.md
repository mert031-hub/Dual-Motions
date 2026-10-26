# İfade incelemesi ve A/B/C/D geliştirme pilotu

Bu araçlar etiket bekleyen geliştirme havuzuyla çalışır; klinik doğrulama veya
bağımsız test değildir. 155 vaka/rengi uygulama yükleyicisine eklemezler.

## İfade varyantlarını inceleme

```bash
python expression_review.py --pool runtime/development_pool/POOL_DIZINI/pool.json
```

`review.json`, mevcut gerçek triyaj çıktısının yanında yeni ifade adaylarını ve
geçmiş/olumsuzlama/alıntı/varsayımsal anlatım ipuçlarını kaydeder. Ekli kaynak kod
çalıştırılmaz. Anlatım ve alıntılar çıktıda tekrarlanmaz. Ek ifadeler
`RED_FLAG_RULES` içine eklenmez; hiçbir acil bayrak düşürülmez. Bu bir gölge
incelemesidir, devreye alınmış yeni güvenlik politikası değildir.

Geçmiş veya alıntı içinde mevcut kuralın acil sonuç üretmesi dahil bilinen
bağlam sorunları ana uygulamada devam eder. Noktalama temelli yerel bağlam ve
regex'ler tam dil/niyet çözümlemesi değildir; ipucu bulunmaması güncel niyeti
kanıtlamaz. Adaylar bağımsız klinisyen incelemesi ve ayrı regresyon örnekleriyle
onaylanmadan uygulamanın kararlarına taşınmamalıdır. Geliştirmede kullanılan
vakalar artık bağımsız test olarak sunulamaz.

## A/B/C/D planı ve çevrimdışı koşu

```bash
python study_pilot.py plan --pool runtime/development_pool/POOL_DIZINI/pool.json --ids 1,33,124
python study_pilot.py offline --pool runtime/development_pool/POOL_DIZINI/pool.json --ids 1,33,124
```

Kimlikler açıkça seçilir; renkler etiket veya örnekleme ölçütü değildir. Plan
kaynak hash'ini, aileleri, modelleri, dört kolu ve tekrarları kaydeder. Tüm kollarda
ortak kriz kapısı, temel üretim koşulları korunur. Affect modu modeldir; dosyanın
tanı başlığından sahte duygu referansı çıkarılmaz. Karşılaştırma çiftleri:
B−A, C−A, D−B ve D−C. Var olan deney/yargıç motoru yeniden kullanılır.

`offline`, gerçek dört kollu akışı sabit model fixture'larıyla çalıştırır. Affect
fixture'ı belirsizdir, Critic onayı betiklenmiştir. Provider çağrısı yapılmaz.
Yargıç kapalıdır: fixture puanlarıyla kalite/hipotez sonucu üretilmez. Manifest,
JSON ve Markdown araştırma raporu `offline_infrastructure_only` olarak işaretlenir.
Bu mod otomatik duygu tahmini veya gerçek Critic başarısı doğrulaması değildir.

`arm_comparison.json` aynı vaka/tekrardaki dört kolun triyajını, stratejisini,
Critic kararını, revizyonunu, mantıksal çağrı sayısını, gecikmesini ve hata durumunu
bir arada verir. Metinler varsayılan kayıtlarda saklanmaz; izinli veri için
`--persist-text` kullanılırsa yanıtlar mevcut `responses.csv/jsonl` içine yazılır.
Bu bir mühendislik karşılaştırmasıdır; kör insan değerlendirme paketi ayrı araçtır.

```bash
# Gerçek provider çağrısı yapar; güvenli ortamda GROQ_API_KEY ve
# api.groq.com HTTPS erişimi gerekir. Bu geliştirmede canlı çalıştırılmadı.
python study_pilot.py live --pool runtime/development_pool/POOL_DIZINI/pool.json --ids 1,33,124 --judge
```

Canlı ve çevrimdışı işlemler farklı dizinlere yazılır. API isteği/retry/token
sayısı görev sayısından türetilmez. Token kaydı henüz eklenmedi; çıktıda null ve
`not_instrumented` olarak belirtilir. Kaynak renkleri klinik pozitif/negatif
metriğine çevrilmez; tüm hedef etiketler boş kalır. H3 için bileşik başarı puanı
yoktur; H4 için uzman duygu koşulları ve dengeli tasarım beklenir. Aileler arası
bağımsızlık kurulmadığı için model puanları teyit edici istatistiksel sonuç değildir.

Testler:

```bash
python -m pytest -q test_development_next_steps.py
python -m pytest -q
```

Klinisyenle birlikte doldurulabilecek kısa form:
[Katkı ve soru formu](CLINICIAN_QUESTIONS.md).
