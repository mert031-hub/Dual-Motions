# Bağlam ve kör değerlendirme çalışma paketi

Bu araçlar kaynaklara dayanan mühendislik sınamalarını hazırlar; tanı, intihar tahmini, klinik karar desteği veya tedavi etkinliği iddiası taşımaz. Kaynak/öneri/sayfa eşlemeleri [inceleme raporunda](CLINICAL_EVIDENCE_REVIEW.md), geliştirme sırası [yol haritasında](VALIDATION_ROADMAP.md).

## Çalıştırma

```bash
python validation_workbench.py build --out-root runtime/validation_kits
```

Yeni, özel izinli bir `validation-...` dizini oluşturur; önceki paketleri üzerine yazmaz. API çağrısı yapmaz. İçerik: 16 yeni yazılmış sentetik bağlam örneği, 8 senaryo ailesi; 6 ayrı senaryo için 12 yazılmış Critic taslağı. Bunlar PDF'den alınmış hasta cümleleri, gerçek model çıktıları veya uzman etiketleri değildir. Senaryolar, kılavuzlardaki ayrımlara ilişkin mühendislik uyarlamalarıdır; mecaz/alıntı için belirli bir Türkçe örneğin kılavuzca doğrulandığı iddia edilmez.

| Yol | Amaç |
|---|---|
| `reviewer/context_packet.json` | Anlatılar, rastgele kimlikler, mesaj hash'leri; yazarın yorumları yok. |
| `reviewer/context_form_R1.json`, `context_form_R2.json` | İki bağımsız değerlendirici için boş bağlam formları; R1/R2 gerçek değerlendirici atanmış olduğu anlamına gelmez. |
| `reviewer/context_schema.json`, `context_form_schema.json` | Makine tarafından doğrulanabilir gözlem ve form şemaları. |
| `reviewer/critic_packet.json` | Sırası karıştırılmış taslaklar; hedef ihlal, yazar varyantı, sistem/kol kimliği görünmez. |
| `reviewer/critic_ratings_R1.json`, `critic_ratings_R2.json` | Boş H1/H2 ve iletişim/güvenlik puanları; mevcut `review_app.py` paketle çalışabilir. |
| `reviewer/critic_decisions_R1.json`, `critic_decisions_R2.json` | Taslak kabul/ret/puanlanamaz kararları için ayrı boş formlar. |
| `reviewer/critic_decision_schema.json`, `critic_criteria.json` | Karar sözleşmesi ve izinli ihlal anahtarları. |
| `private/context_mapping.json`, `critic_mapping.json` | Aile/kaynak/yazar önerisi eşlemeleri. Değerlendiricilere verilmez; klinik altın standart değildir. |
| `private/critic_frozen_examples.json` | Mevcut Critic deney motoruna uygun dondurulmuş taslaklar; referans etiketleri `null`. |
| `context_progress.json`, `critic_progress.json` | Tamamlanmış/boş form sayıları; başlangıçta tamamlanan değerlendirme sıfırdır. |
| `shadow_observations.json` | Aynı 16 örnekte mevcut kurallar ve gölge ifade adayları; karar değişikliği ve klinik başarı metriği yok. |
| `manifest.json`, `summary.json` | Kaynak kod/klinik envanter hash'leri ve içerik sayıları. |

Yalnız `reviewer/` içeriği paylaşılır; `private/` ve gölge çıktıları değerlendiricilere verilmez. Bağımsız değerlendiriciler ilk puanlama sırasında birbirlerinin formlarını görmemelidir. Rastgele kimlikler ve gizli eşleme içerikten sistem/yazar tahminini imkânsız kılmaz. Kaynak koduna veya özel eşlemeye bakılması körlüğü bozabilir. Veri geliştirme içindir; bu senaryolar daha sonra bağımsız test diye sunulamaz.

## Bağlam şemasının anlamı

`ContextAnnotation.events` aynı mesajdaki farklı kişi/zaman olaylarını ayrı tutar. Bir olayda:

- `subject`: kendi anlatımı / başka kişi / alıntı / bilinmiyor;
- `time`: güncel / geçmiş / varsayımsal / bilinmiyor;
- `unwanted_thought`: istenmeyen düşünce açıkça ifade edilmiş mi;
- `intent`: kendine veya başkasına zarar verme niyeti; **ölme isteğiyle aynı alan değildir**;
- `desire_to_die`: açıkça ifade edilen ölme isteği;
- `plan_or_preparation`, `action`, `injury_or_poisoning`, `physical_need`: ayrı gözlemler.

Son alanlar `yes/no/unknown` alır. Sessizlik `no` değildir; varsayılan `unknown` kullanılır. Yardım isteği mesaj düzeyinde ayrı tutulur. Tanı, olasılık veya düşük/orta/yüksek klinik risk alanı yoktur.

Her bilinen alan kendi `evidence` alıntılarına bağlanır; `no` da alıntı gerektirir. Alıntılar mesajla karakter karakter eşleşir. İsteğe bağlı `start/end` konumları Python karakter indeksleridir, byte konumu değildir. Tek konum verilmesi, hatalı aralık, boş alıntı, mesajda bulunmayan kanıt ve bilinmeyen alan adına kanıt yazılması reddedilir. Bir alıntı hem kişinin hem zamanın bilgisini açıkça içeriyorsa birden çok alanı destekleyebilir; aynı alıntıyı kopyalamak yorumu doğru yapmaz. Şema/substring kontrolü anlamı veya klinik uygunluğu doğrulamaz.

Form doldurulunca değerlendirici kodu ve `status=completed` gerekir. Bütün alanların bilinmiyor kalması mümkündür; bu nedenle boş gözlemli tamamlanmış kayıt sayısı ayrıca raporlanır. İlerleme çıktısı olayları otomatik hizalamaz, klinik uzlaşı veya değerlendiriciler arası kappa uydurmaz.

```bash
python validation_workbench.py progress \
  --packet runtime/validation_kits/PAKET/reviewer/context_packet.json \
  --forms runtime/validation_kits/PAKET/reviewer/context_form_R1.json runtime/validation_kits/PAKET/reviewer/context_form_R2.json \
  --out runtime/context_progress_new.json
```

Mesaj hash'i, paket/şema sürümü, alıntılar ve tekrarlı değerlendirici/kayıt kontrol edilir. İlk bağımsız formlar saklanmalı; uzlaşı ayrı işlem olmalıdır.

## Deneysel semantik trijaj v2

`category_evidence` her kategori için **tek** bağlama ve bir veya daha fazla kategoriye özel alıntıya bağlanır. Eski `evidence` ve `temporal_context` alanları dosya/sağlayıcı uyumluluğu için durur; genel alıntı listesi tek başına kategori kabul ettirmez. Eksik/eski şema belirsizlik kontrolüne gider. Karışık geçmiş/güncel olaylar için ilgili olayın zamanı esas alınır.

Yalnız kendi güncel anlatımına bağlanan ve kesin kanıt kontrollerini geçen adaylar, modelin yüksek güven ve çekimser olmama koşuluyla eklenebilir. `active_self_harm` ayrıca ifade edilmiş zarar niyeti veya gerçekleşmiş eylem; `violence_risk` ifade edilmiş niyet gerektirir. İstemsiz düşünce tek başına bunların yerine geçmez; niyet ile istemsiz düşünce aynı mesajda birlikte bulunabilir. Başka kişiye ait veya geçmiş bağlam belirsizlik/uygun ihtiyaç kontrolüne yönlendirilir; bu durumların önemsiz olduğu anlamına gelmez.

Bir kategori kanıtsızsa ayrı kaydedilir; başka bir destekli mevcut ihtiyaç sırf bu yüzden silinmez. Çelişkili bildirilmemiş kategori veya geçersiz olay kanıtı ise aday kabulünü engeller. Model güveni kalibre değildir; alıntının gerçekten ilgili klinik olguyu gösterdiği ayrı inceleme gerektirir. Bu bir klinik doğrulama algoritması değil, hatalı/eksik yapılandırılmış çıktıları sınırlayan teknik sözleşmedir.

Mevcut deterministik bayraklar düşürülmez. Bilinen acil kural eşleşmesi semantik API beklemeden çıkar. **Geçmiş/alıntı cümleleri acil sayan mevcut anahtar sözcük hatası çözülmüş değildir.** Ana A/B/C/D kolları hâlâ aynı ortak deterministik kapıyı kullanır; değişiklik ek hibrit deney katmanındadır.

## Critic kararları ve kör puanlar

H1/H2 puanları için 1/3/5 davranış çıpaları, 2/4 ara puanları ve `null` kullanım açıklaması eklendi. Gerekli güvenlik bilgisi sırf doğrudan olduğu için aşırı tavsiye sayılmaz; uygun bir yanıtın soru içermesi zorunlu değildir. Bu çıpalar geçerliği gösterilmiş ölçek değil, kalibrasyon taslağıdır.

`DraftReview` tamamlanmış bir karar için değerlendirici kodu, karar ve gerekçe ister. `reject` en az bir geçerli ihlal anahtarı gerektirir; `approve`/`unscorable` ihlal listesi taşımaz. İçerik hash'i, paket/rubrik ve tekrar kontrolü yapılır. İlerleme raporu anlaşmazlık sayısını gösterir; otomatik çoğunluk oyu veya klinik doğruluk puanı oluşturmaz.

```bash
python critic_review.py progress \
  --packet runtime/validation_kits/PAKET/reviewer/critic_packet.json \
  --forms runtime/validation_kits/PAKET/reviewer/critic_decisions_R1.json runtime/validation_kits/PAKET/reviewer/critic_decisions_R2.json \
  --out runtime/critic_progress_new.json

# Yalnız gerçek, tamamlanmış ve puanlanabilir incelemeler olduğunda:
python critic_review.py frozen \
  --packet runtime/validation_kits/PAKET/reviewer/critic_packet.json \
  --forms runtime/validation_kits/PAKET/reviewer/critic_decisions_R1.json \
  --reviewer R1 --out runtime/reviewer_R1_frozen.json
```

Son komut belirli tek değerlendiricinin kararlarını aktarır; uzlaşı veya uzman yetkinliği varsaymaz. Referans insan yorumunun uygunluğu ayrıca incelenmelidir. `critic_experiment.py` bu formatı kullanabilir; gerçek model deneyinde sağlayıcı/veri/bütçe koşulları ayrıca gerekir. Boş formlar bu komutla etiketli deneye dönüştürülemez.

Gerçek A/B/C/D yanıt paketlerinin mevcut `clinician_review.export_packet` yolu korunmuştur; çıpalar/sürüm eklenmiştir. Sabit `offline_stub` çıktılarının gerçek model yanıtı gibi dışa aktarılması artık reddedilir. Aynı paket/eşleme dosyalarının üzerine yazılmaz. Şu çalışmada canlı model ve insan puanlaması yapılmadı.
