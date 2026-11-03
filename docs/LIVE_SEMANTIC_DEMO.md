# Canlı semantik API denemesi

Mevcut sağlayıcı **Groq**, anahtar değişkeni **GROQ_API_KEY**. `SEMANTIC_MODEL` yalnız bağlam çıkarımı modelini seçer; varsayılan `openai/gpt-oss-120b` Groq üzerinden çağrılır. Bu, OpenAI API anahtarı gerektiren bir bağlantı değildir. Modelin hesaptaki güncel erişilebilirliği canlı çağrı yapılmadan doğrulanmış sayılmaz.

## 1. Gizli ayarı ve ağ erişimini ekleyin

Groq konsolunda bir anahtar oluşturun: https://console.groq.com/keys . Bulut ortamının gizli ortam değişkenlerine `GROQ_API_KEY` adıyla ekleyin. Anahtarı sohbet, kaynak kod veya komut satırı geçmişine yazmayın. Normal ortam değişkeni olarak `SEMANTIC_MODEL=openai/gpt-oss-120b` seçilebilir.

Kısıtlı ağ kullanılan bu ortamda `api.groq.com` için HTTPS erişimi gerekir. 27 Ekim kontrolünde anahtar değişkeni yoktu, alan adı mevcut izin listesinde görünmüyordu; canlı kimlik doğrulama veya ağ testi yapılmadı. Desteklenen bulut ortamı yapılandırmasından host erişimini ve gizli değişkeni uygulayın; gerekiyorsa ortamı yenileyin. Yerel ağ politikası dosyasını düzenlemek erişim sağlamaz.

## 2. Ağsız hazırlık kontrolü

Mevcut çalışma klasöründe:

```bash
cd /workspace/Dual-Motions
.venv/bin/python live_semantic_demo.py
```

`key_variable_present=true` yalnız değişkenin dolu olduğunu söyler; anahtarın geçerliliğini veya ağ erişimini doğrulamaz. Bu komut API çağrısı yapmaz.

## 3. Dört sentetik örnekle küçük canlı deneme

```bash
MAX_RETRIES=0 STRUCTURED_RETRIES=0 REQUEST_TIMEOUT=20 \
  .venv/bin/python live_semantic_demo.py --live
```

Bu komut Groq'a gerçek istek gönderir ve sağlayıcının ücret/kota koşullarına tabidir. İki örnek açık deterministik kapıda sonuçlanır; diğer iki örnekte semantik çıkarım denenir. Bu ayarla SDK/şema yeniden denemeleri kapalıdır. Tam sohbet, Affect, Critic ve yargıç çalıştırılmaz; başlangıç denemesi yalnız bağlam katmanını inceler. Dört örnek: geçmiş söz, istemsiz zarar korkusu, açık güncel niyet, akut fiziksel belirti.

Çıktı `runtime/semantic_live_demos/semantic-live-.../report.json` yoluna yazılır. Model, prompt sürümü, denenip denenmediği, kabul/reddedilen kategoriler, çekimserlik ve hata türleri görünür. Anahtar, sağlayıcı hata gövdesi, hasta anlatısı ve model alıntıları dosyaya yazılmaz. Yalnız projede yazılmış sentetik örnekler gönderilir.

- `semantic_attempted=false`: bu örnekte deterministik kapı API beklememiştir.
- `semantic_error_type` dolu: bağlantı, yetki, model veya şema sorunu vardır; başarılı sınıflama değildir.
- `abstained=true`: model veya kanıt kontrolü belirsizlik bildirmiştir; klinik karar değildir.
- `rejected_categories`: teknik kanıt/bağlam kontrolünü geçmeyen adaylar.
- `clinical_metrics=null`: bağımsız referans olmadığı için doğruluk puanı üretilmez.

`AuthenticationError` anahtar/yetki; `APIConnectionError` bağlantı/proxy/TLS; `RateLimitError` kota/hız sınırı; `BadRequestError` model veya istek/şema uyumu; `ValidationError` yapılandırılmış çıktı kontrolü açısından incelenmelidir. Yalnız hata türü kesin kök nedeni göstermez. Anahtarın veya hassas metinlerin loga basılması gerekmez.

## Klinik sınırların uygulanması

`semantic_triage.py` sürümlü `clinical_constraints.py` yönergelerini, olay/kişi/zaman şemasını ve kategoriye özel kanıt koşullarını kullanır. Modelden kaynaklardan bağımsız klinik kurallar uydurması istenmez. Bu mevcut sürümde tam PDF arama/RAG veya fine-tuning yoktur. API bağlantısının kurulması Türkçe klinik geçerlilik sağlamaz; kaynaklı kuralların gerçek model davranışına yansıması, ardından bağımsız insan değerlendirmesi ayrıca sınanır.

Tam sohbet arayüzüne geçildiğinde `streamlit run app.py` ile sistem seçicisinde `E2: Full + Hibrit Trijaj` kullanılabilir. Bu mod üretim/Critic ve seçime bağlı Affect gibi ek çağrılar yapar. Ana A/B/C/D araştırma kolları otomatik olarak hibrite dönüştürülmez; karşılaştırılabilirlik korunur.
