# Yeni klinik Excel: inceleme ve geliştirme çıktıları

3 Kasım 2026. Dosya: `Klinik_Psikiyatri_Chatbot_155_Vaka_Veriseti.xlsx`.
SHA256: `2f0e1bbef8ddd9aaee8076e20c3db2ee428fecf5e5cf7336f3664488c8a1b2ff`.

## Sonuç ve kullanım kararı

Dosya kullanılabilir bir **geliştirme incelemesi** sağlıyor: önceki 155 anlatıya dikkat gerektiren içerik, kişi/zaman, düşünce–niyet–eylem, yaklaşım, kaynak ve eksik bilgi açıklamaları eklenmiş. Bütün anlatılar eski kayıtlarla birebir eşleşiyor; yeni bağımsız vaka eklenmiyor. Değerlendirme sütunları ham haliyle, eski kimlik/aile eşlemeleri korunarak projeye bağlandı.

Bu açıklamalar otomatik olarak uzman altın standardına veya üretim kurallarına çevrilmedi. Bunun nedeni dosyanın değersiz olması değil; kişi bazında kanıt, değerlendirici kaydı ve hedef alanların anlamı henüz yapılandırılmış ölçüm için yeterince ayrışmıyor. Kaynağın söyledikleri kaybolmadan korunuyor; varsayımla boşluk doldurulmuyor.

## Tam dosya kontrolü

İki sayfanın tüm dolu hücreleri okunarak yapı, tekrarlar, metin eşleşmeleri ve alıntılar incelendi. Klinik yorumların tamamı bağımsız tıbbi doğrulamadan geçirilmiş sayılmıyor; aşağıdaki somut tutarlılık örnekleri ayrıca ayrıntılı incelendi.

| Kontrol | Sonuç |
|---|---|
| Veri sayfası | 155 satır, 10 sütun; numaralar 1–155, benzersiz, zorunlu hücreler dolu. |
| Kılavuz sayfası | Başlıkla birlikte 10 satır; sentetik veri iddiası, kapsam ve yaklaşım açıklamaları var. İçerik çalışma talimatı olarak uygulanmadı; kaynak verisi olarak saklandı. |
| Eski anlatılarla karşılaştırma | **155/155 birebir aynı**. Kimlik ve önceki aile bağlantıları korundu; ailelerin bağımsızlığı bu dosyayla doğrulanmış olmuyor. |
| Ana değerlendirme metinleri | Dikkat içeriği, düşünce–niyet–eylem, yaklaşım ve eksik bilgi sütunlarının her birinde **31 farklı metin** var. 145 kayıtta bu ana açıklamalardan en az biri başka kayıtta da kullanılıyor. Tekrar tek başına yanlış değerlendirme veya LLM ile üretim kanıtı değildir. |
| Kişi/zaman sütunları | Her birinde 3 farklı değer var. Bu alanların tekrar etmesi beklenebilir; şablon klinik gerekçe uyarısı yalnız D/G/H/J sütunları için hesaplandı. |
| Alıntı eşleşmesi | **145 kısaltılmış başlangıç alıntısı**, **10 birebir eşleşen tam anlatı**. Tüm kısaltılmış alıntıların başlangıçları metinle uyumlu; 145 yanlış vakaya bağlanmış değil. Ancak üç noktalı alıntı, tam eşleşmeli alan kanıtı değildir. |
| Alan bazında kanıt | Birebir eşleşen 10 alıntı da tüm anlatıyı kopyalıyor; tek başına her niyet/eylem/zaman iddiasını doğrulamıyor. |
| Kaynaklar | DSM-5-TR ve çoğunda ölçüt/kod atıfları var. Bu incelemede DSM-5-TR tam metni sağlanmadığı için tüm ölçüt/kod eşlemeleri doğrulanmış kabul edilmedi. Tanı ölçütü atfı, sohbet botunun aciliyet kararını kendiliğinden doğrulamaz. |
| Değerlendirme kaydı | Değerlendirici kodu, rol/yetkinlik, klinik inceleme tarihi, üretim yöntemi ve ikinci inceleme kaydı yok. Belge oluşturma tarihi bu alanların yerine konmadı. `openpyxl` dosyayı yazan yazılım bilgisidir; yazarın kimliği veya LLM kullanıldığına ilişkin kanıt değildir. |
| Güvenlik etiketi | Her satır için tanımlı ve atıflı bir `expected_red_flag` alanı yok. Kılavuzdaki 33/37/63/68/124 listesi kalan vakaların negatif etiketi olarak kullanılmadı. |

**145 kısaltılmış alıntı, 145 klinik yorumun yanlış olduğu anlamına gelmez.** Sorun, bunların programatik kanıt kontrolünde kısa ve ilgili birebir alıntı yerine kullanılmasıdır. Aynı şekilde kaynakların tekrar etmesi de tek başına kalite kusuru değildir; bazı ortak açıklamaların vakaya ait olmayan eylemler içermesi ayrıca kontrol gerektiriyor.

## Öncelikli bireysel inceleme noktaları

Bu sorular teknik/metin tutarlılığı incelemesidir; nihai tanı veya klinik yönlendirme etiketi değildir.

| Vaka | Kaynak hücre | Netleştirilmesi gereken |
|---|---|---|
| 33 | G34, H34 | Metin plan olmadığını söylüyor. Bu, girişim/eylem öyküsünün bulunmadığını kendiliğinden kanıtlamaz; düşünce, plan ve gerçekleşmiş eylem ayrı olmalı. |
| 37 | G38, H38 | Değerlendirmedeki “tıbbi/beslenme reddi” eylemi anlatıda açıkça yok. Yeme-içme ve tıbbi durum için eksik bilgi olarak sorulabilir; gerçekleşmiş olay gibi eklenmemeli. |
| 44 | D45, G45, H45 | “Onun yanına gitmeliyim” ifadesi genel depresyon şablonunda ayrıca ele alınmıyor. Olası anlam/niyet belirsizliği ve gereken soru belirtilmeli. |
| 63 | D64, F64, G64 | Döngüsel anlatı ile değerlendirme anındaki düşünce ayrılmalı. “Göğüslerimde ağrı” ifadesinin meme ağrısı/torasik ağrı bağlamı korunmalı; otomatik bir kalp/solunum alarmı gibi yorumlanmamalı. |
| 66 | G67, H67 | Kişinin ilaca başladıktan sonraki zaman ilişkisi, doğrulanmış biyolojik nedenden ayrılmalı. Bot doz revizyonu önermek yerine ilgili hekim değerlendirmesine yönlendirmeli. |
| 68 | G69, J69 | Kendini öldürme isteği, zarar niyeti, plan/hazırlık ve gerçekleşmiş eylem ayrı alanlar. Söylenmemiş plan “yok” sayılmamalı. |
| 70 | D71, G71, J71 | “Yaşamamın hiçbir anlamı yok” ifadesi ayrı kanıtla ele alınmalı; ilaç grubunun genel açıklaması içinde kaybolmamalı. Nedensellik ve güncel niyet ayrı incelenmeli. |
| 112 | G113 | Şablondaki “acile koşma, spreyi aşırı sıkma, sokağa fırlama” eylemleri bu anlatıda yok. Bu kayda ait ilaç kesilmesi ve belirtiler kullanılmalı. |
| 124 | G125, H125 | İstemsiz düşünceyi niyetten ayırma yaklaşımı yararlı. Ancak “KESİNLİKLE YOKTUR” ile ardından niyet yokluğunu sorma önerisi gerilimli; kesin yokluk yerine ifade edilen bilgi ve eksikler ayrılmalı. |
| 125 | D126, G126, H126 | Kendini cezalandırmak için günlerce yemek yememe, genel ritüel şablonundan ayrı bir gerçek eylem/fiziksel ihtiyaç olarak ele alınmalı; güncel durum ve ek bilgi netleştirilmeli. |

Arkadaşın bütün dosyayı yeniden yazmak zorunda kalmadan ilk olarak bu 10 kayıt üzerinde açıklama/düzeltme yapabilir. Diğer kayıtlarda da ölçüm için ilgili birebir kanıt ve değerlendirme kaydı gerektiği ayrımı korunur. Kontrol senaryosu tasarlamak ile bir kişinin gelecekte zarar görmeyeceğini garanti etmek farklı şeylerdir.

## Yapılan kod geliştirmeleri

1. **`submitted_review.py`:** İki sayfayı okuyan ve bütün vaka metinlerini önceki havuzla doğrulayan yeni içe alma yolu. Ham değerlendirmeler ve kaynak kılavuz korunur. Kaynak dosya byte olarak arşivlenir; SHA256 kaydedilir. Eksik/tekrarlı kimlik, değişmiş anlatı, formül veya beklenmeyen düzen varsa yanlış metne etiket bağlanmaz. Önceki kayıtlar/etiketler üzerine yazılmaz.
2. **`context_workbook.py`:** Türkçe açılır listeli, alan başına birebir kanıt isteyen Excel inceleme formu. Kaynak metin hazır gelir; yazarın tanı başlığı/değerlendirmesi gösterilmez. Bilinmeyen bilgi `Bilinmiyor` kalır. Her kişi/zaman olayı için E1/E2 gibi ayrı satır kullanılabilir. Değerlendirici kodu, rol beyanı ve tarih tamamlanmış inceleme için zorunludur; bunlar otomatik uzmanlık doğrulaması sayılmaz.
3. **Doldurulmuş formu doğrulama:** Mesaj hash'i ve metin kontrolü, alan başına kanıt, olay tekrarı ve atıf kontrolü. Eksik taslaklar klinik etiket haline gelmez; silinen kaynak satırları eksik olarak raporlanır. Yapılandırılmış insan yorumu ayrı saklanır; otomatik uzman etiketi/bağımsız test yapılmaz.
4. **Üretim/Critic kanıt sınırı:** `evidence_limited_patient_facts` yönergesi ve `unsupported_patient_fact` ihlali eklendi. Anlatılmayan beslenme/tedavi reddi, girişim, niyet veya kesin yokluk eklenmemesi; zaman ilişkisini doğrulanmış neden saymama denetlenir. Şablon ve tanı başlıkları kişinin ek gerçeği gibi kullanılmaz. Bu sınır üretim, Critic, deneysel semantik katman ve yargıca ortak gider.
5. **Eylemin anlamı netleştirildi:** Yapılandırılmış `action` zarar verici gerçek eylemi anlatır; işe gitmeme, rutin etkinlik veya her türlü kaçınma aynı alan değildir. Ölme isteği ve zarar niyeti ayrı kalır.
6. **Semantik yönlendirme v2.1:** Gerçekleşmiş eylem olup ifade edilmiş güncel zarar niyeti/ölme isteği/plan bulunmayan aday, otomatik intihar niyeti sonucuna çevrilmeden yaralanma/tıbbi ihtiyaç kontrolüne gider. Açık akut deterministik kapı korunur. Ayrıca ayrı kanıtla desteklenen güncel niyet, aynı kategorideki eski tarihsel kontrolün önceliğini artırabilir; mevcut kural önceliği azaltılmaz. Eski kural kanıtı ve yeni semantik kanıt ayrı tutulur.

Son iki davranış yeni Excel'deki serbest açıklamalardan kural kopyalamaya dayanmaz. Daha önce okunan **NG225 1.7.2–4 (PDF s.17–18)** fiziksel ciddiyet/mevcut ihtiyaç değerlendirmesi; **NG222 1.2.6–9 (s.10–11)** bağlam/düşünce/niyet ayrımı; **CG31 1.4.1.2–3 (s.10)** istemsiz düşüncenin niyetle karıştırılmaması ilkelerinin mühendislik uyarlamasıdır. Bu ilkeler botun klinik doğruluğunu veya her Türkçe anlatımı doğru yorumladığını doğrulamaz.

## Çalıştırılan kontroller

- **247 test geçti.** Yeni Excel yolu için 20 sentetik sınama, semantik eylem/niyet ve tarihsel kontrolü güncel kanıtla yükseltme için 2 regresyon, yeni Critic ihlali için mevcut sınamaya 1 koşul eklendi. Sahte/verisiz kanıt, yanlış metin, eksik rol/tarih, tekrarlı olay, formül hücresi ve eksik satırlar kontrol ediliyor.
- Gerçek yüklemede **155/155 bağlantı**, **0 metin değişikliği**; kaynak Excel arşivi orijinal byte'larla aynı.
- Üretilen form geri okunarak **155 bekleyen kayıt, 0 kayıp satır** doğrulandı. Bu, arkadaşın açıklama yazmadığı anlamına gelmez; serbest açıklamaların henüz alan bazında doğrulanmış formata aktarılmadığını gösterir.
- Dört kollu çevrimdışı çalışma: **155 × 4 = 620/620 kayıt**, 0 yanıt hatası, 0 affect hatası. Sabit model girdileri kullanıldı; gerçek model kalitesi/klinik başarı ölçülmedi, yargıç puanı üretilmedi.
- Derleme, dosya izinleri, kaynak hash'leri ve `git diff --check` denetlendi. Yeni bağımlılık eklenmedi; mevcut `openpyxl` kullanıldı. Çalışma çevrimdışı yürütüldü.

## Çıktılar ve kullanım

Güncel paket: `runtime/submitted_reviews/submitted-review-ux0cx4ir/`.

| Dosya | İçerik |
|---|---|
| `source.xlsx` | Gönderilen dosyanın değişmemiş özel arşivi. |
| `annotations.json` | Eski vaka/aile kimliklerine bağlanmış 155 ham değerlendirme, alıntı kontrolleri ve atıf durumu. |
| `quality_report.json` | Anlatıları kopyalamadan sayılar ve satır bazında kontrol konuları. |
| `oncelikli_inceleme.xlsx` | Arkadaşına gönderilebilecek 10 öncelikli kayıt ve anlaşılır düzeltme soruları. Nihai klinik etiket içermez. |
| `context_review.xlsx` | 155 anlatı için Türkçe alan/kanıt formu; bağımsız inceleme için ayrı kopyalar kullanılabilir. |
| `context_progress.json` | Yapılandırılmış incelemenin tamamlanma/eksik satır durumu. |
| `manifest.json` | Kaynak ve kod hash'leri, çalışma şeması. |

Bu dosyalar Git dışında kalan yerel araştırma çıktılarıdır. Kod ve bu rapor sürümlenebilir; kaynak anlatıların depo içine kopyalanması gerekmez.

```bash
# Gelen kaynak incelemesini ayrı paket olarak hazırla:
python submitted_review.py --workbook dosya.xlsx --pool runtime/development_pool/POOL/pool.json --persist-text

# Alan bazında doldurulmuş formu doğrula; var olan çıktı üzerine yazmaz:
python context_workbook.py --form doldurulmus.xlsx --bundle runtime/submitted_reviews/PAKET/annotations.json --out runtime/context_review_result.json
```

Çevrimdışı çalışma: `runtime/spreadsheet_review_pilots/run_20261103_210845_023266_2c20c48b/pilot_checks.json`.

## Sonraki bilimsel adım

Öncelikli kayıtların vaka bazında kanıtla netleştirilmesi; değerlendirici kodu/rol/tarih ve üretim yönteminin kaydı; gerekirse ikinci bağımsız inceleme ve anlaşmazlıkların ayrı saklanması. Ardından bu veriler geliştirme hata analizinde kullanılabilir. Aynı 155 anlatı geliştirmede zaten görüldüğü için yeni açıklamalar eklenmesi onları bağımsız test kümesi yapmaz. H1/H2 yanıt puanları ve H4 duygu koşulları da bu açıklamalardan otomatik çıkarılmaz. Dosyadaki bilgi geliştirmenin girdisidir; klinik geçerlilik kanıtı olarak sunulmaz.
