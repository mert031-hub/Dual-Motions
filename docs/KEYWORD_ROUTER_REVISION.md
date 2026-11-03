# Anahtar sözcük motoru: karar mantığı ve revizyon çıktıları

27 Ekim 2026. Sürüm: `tr-context-rules.v1`; prompt sürümü: `2026.10.v3.3-context-rules`.

## Düzeltilen temel sorun

Eski motor metinde alt dizge bulunca kategorinin sabit eylemini uyguluyordu. İfadenin güncel mi, geçmiş mi, alıntı mı, olumsuzlanan bir önerme mi olduğu kararın parçası değildi. Yeni motor **eşleşme çıkarımı → ifadeye bağlı bağlam → ihtiyaçla uyumlu eylem → mesaj düzeyinde birleştirme** adımlarını ayırır. Anahtar sözcük listesini genişletmenin tek başına bu sorunu çözemeyeceği kabul edilmiştir.

Kod: `rule_context.py` bağlam/karar mantığı; `red_flags.py` kategori kataloğu ve açık eski/yeni giriş noktaları; `triage.py` ortak eylem şeması; `messages.py` kullanıcı mesajları ve üretim/Critic yönergeleri. A/B/C/D aynı yeni deterministik kapıyı kullanır. Hibrit katman bu kapının üzerine eklenir, acil kural sonucunu bekletemez.

## Bilimsel dayanak ile mühendislik uyarlamasının sınırı

Yüklenen PDF'lerde aşağıdaki öneriler ilgili sayfalardan yeniden kontrol edildi. Tam dosya sürümleri ve SHA256'lar [kaynak envanterinde](clinical_sources.json).

| Doğrudan kaynak | Desteklediği ilke | Bu projedeki mühendislik kararı |
|---|---|---|
| **CG31 1.4.1.2–3, PDF s.10** | OKB'de istemsiz cinsel/agresif/ölüm düşünceleri sıklıkla risk olarak yanlış yorumlanır; belirsizlikte OKB uzmanlığı gerekir, eşlik eden kendine zarar/depresyon ayrıca değerlendirilir. | İstemsiz düşünce adayı tek başına gerçek niyet diye acil yanıta çevrilmez; mevcut niyet/ihtiyaç netleştirilir. Kullanıcıya OKB tanısı veya kesin güvenlik sonucu verilmez. Önerinin özgül OKB bağlamından chatbot'a aktarılması bir uyarlamadır. |
| **NG225 1.6.1–6, PDF s.16** | Gelecek intihar/tekrar tahmini veya hizmet kararı için ölçek/küresel düşük-orta-yüksek sınıflama kullanılmaz; mevcut ihtiyaçlar ve güvenlik ele alınır. | Eşleşme bulunmaması güvenli sonucu değildir. Geçmiş/olumsuz/alıntı bağlam “risksiz” etiketi üretmez. Eski `risk_level` alanı uyumluluk için kalan kategori metaverisidir, klinik öngörü değildir. |
| **NG222 1.2.6–9, PDF s.10–11** | Kapsamlı bağlam/işlev değerlendirmesi; düşünce ve niyeti doğrudan sorma; belirgin mevcut tehlikede acil uzman yardımı. | Düşünce–niyet ayrımı; geçmiş anlatı için mevcut ihtiyaç kontrolü; ayrı, açık güncel niyet ifadesini koruma. Bir Türkçe regex'in bu öneriyle klinik olarak doğrulandığı iddia edilmez. |
| **NG225 1.7.2–4, PDF s.17–18** | Yaralanmanın ciddiyeti ve tedavinin aciliyeti, mevcut güvenlik/sıkıntı, fiziksel ve psikososyal ihtiyaçlar değerlendirilir; zehirlenmede uygun acil kaynaklara başvurulur. | Gerçekleşmiş yaralanmada ciddiyet bilinmiyorsa ihtiyaç sorusu; devam eden kanama/olası aşırı ilaç alımında gecikmeyen tıbbi yardım. Ölme isteğinin reddi fiziksel ihtiyacı iptal etmez. Bot yaralanmanın derecesini ölçmez, ilk yardım/doz protokolü vermez. |
| **CG113 1.3.6, PDF s.20** | Panik atak panik bozukluğu değildir; akut fiziksel problemleri dışlamak için gerekli incelemeler yapılmalıdır. | Solunum güçlüğünü “sadece panik” diye açıklamama; güncel fiziksel ihtiyaç için tıbbi yönlendirme. Bu öneri tek başına bütün solunum ifadeleri için doğrulanmış bir metin triyaj protokolü değildir. |
| **NG69 1.10.3, PDF s.30** | Yeme bozukluğu bağlamında ağır dehidratasyon/malnütrisyon/elektrolit bozukluğu gibi durumlarda akut tıbbi bakım gerekir. | Sıvı alamama ile bayılacak gibi olmanın birlikte güncel bildiriminde ihtiyatlı tıbbi yardım; tek başına baygınlık hissi otomatik ağır dehidratasyon veya acil durum tanısı sayılmaz. Bu birleşim doğrulanmış bir klinik eşik değildir ve genel sohbet bağlamına aktarımı uzman incelemesi gerektirir. |

Kılavuzlar bu regex'leri, bağlaç kurallarını veya acil yanıt metinlerini doğrulamıyor. Kaynaklar ilkeyi destekler; Türkçe dil kapsamı ve yönlendirme uygulaması test edilen mühendislik varsayımlarıdır. Bağımsız klinik doğrulama yapılmış gibi sunulmaz.

## Denetlenebilir karar sözleşmesi

1. **Alt dizge ile sözcük aynı şey değildir.** Sözcük sınırları uygulanır; teknik bağlamdaki `crash` madde yoksunluğu sayılmaz. İşlev kaybı ifadelerinin bilinen Türkçe birinci kişi çekimleri korunmuştur.
2. **Olumsuzlama ilgili önermeye bağlanır.** Mesajdaki herhangi bir `yok`/`istemiyorum` bütün eşleşmeleri iptal etmez. “Kendimi öldürmek istiyorum, kanamam yok” içindeki niyet korunur.
3. **Geçmiş işareti ilgili ifadeyi nitelemelidir.** Yakın zaman çerçevesi veya geçmiş aktarım yüklemi kontrol edilir. Başka bir geçmiş olay, ayrı güncel tehdidin tarihi sayılmaz. Bu kurallar tam Türkçe zaman çözümleyicisi değildir.
4. **Alıntı işaretleri tek başına iptal edici değildir.** Yalnız “Kendimi öldüreceğim” yazılması acil yolu korur. Belirgin kurmaca/çeviri çerçevesi ise kullanıcıya aynı niyeti atfetmeden ele alınır. Alıntı içinde noktalama/bağlaç bölünmesi konuşmacı çerçevesini kaybettirmez.
5. **Bağlam ile eylem ayrı tutulur.** Geçmiş/olumsuz/istemsiz anlatılar güncel durumu netleştiren yönergeye gider; tanı veya kesin güvence verilmez. Açık bilgi/çeviri bağlamına sırf kelime eşleşti diye intihar sorgusu dayatılmaz.
6. **Korku, ifade edilmiş niyeti veya fiziksel belirtiyi kendiliğinden silmez.** “Eğer yardım gelmezse intihar edeceğim” ve “Nefes alamıyorum diye korkuyorum” acil yoldan düşürülmez. İstemsiz düşünce ve ayrı güncel niyet birlikteyse güncel niyet korunur.
7. **Fiziksel ihtiyaç niyetten bağımsızdır.** Olası zehirlenme/kanama için “ölmek istemiyorum” iptal edici değildir. Yaralanma ve fiziksel ihtiyacın ciddiyeti belirsizse uygun tıbbi kontrol yönergesi vardır. Tekrarlayan/koşula bağlı anlatıdaki belirti şu anda oluyormuş gibi kabul edilmez; ayrı güncel ifade değerlendirilir.
8. **Kişi ayrımı yanıtı da etkiler.** Başka kişinin açık güncel tehdidinde kullanıcı o kişiymiş gibi konuşulmaz; güvenli yardım çağırma mesajı vardır. Başkasının geçmiş durumu kendi güncel niyetine çevrilmez. Zamir/kişi çözümlemesi sınırlıdır.
9. **Birleştirme tek eylem şemasına dayanır.** Bütün eşleşmeler incelenir; aynı kategori için gerçek eylem şemasındaki en öncelikli yönlendirme korunur. Öncelik sayıları sıralama içindir, klinik risk puanı değildir. Geçmiş bir eşleşme ayrı güncel niyeti ezemez. Acil sonuç için model/API çağrısı yapılmaz.
10. **Karar izi saklanabilir.** `observe_rule_matches()` bütün eşleşmeleri ve kararlarını, `rule_id`, bağlam durumu, kaynak referansı ve özgün metindeki tam alıntı/karakter konumlarıyla verir. Normalleştirilmiş Türkçe harfler özgün metne geri eşlenir. Varsayılan kayıtlar bu alıntıları saklamaz; karşılaştırma çıktıları anlatı içermez.

Tam dil modeli/bağımlılık çözümleyicisi yerine kapsamı açık, deterministik bir yönlendirme sözleşmesi kullanıldı. Tercihin nedeni kararların açıklanabilir olması ve acil ifadelerin ağ/model başarısına bağlı kalmamasıdır; tam dil anlama veya klinik doğruluk sağladığı iddia edilmez. Tırnak, noktalama, ek, ironi, dolaylı anlatım ve çok turlu gönderimler tümüyle çözülmüş değildir.

## Önce/sonra örnekleri

| Özgün sentetik örnek | Eski motor | Yeni motor |
|---|---|---|
| “Geçen yıl intihar edeceğim dedim.” | Acil kendine zarar mesajı | Güncel ihtiyacı netleştirme |
| Romandaki karakterin aynı sözü | Kullanıcıya acil mesaj | Alıntı/kurmaca bağlamını ele alma |
| “Ya bebeğimi bıçaklarsam diye korkuyorum.” | Eşleşme yok | Niyet ile istenmeyen düşünceyi ayıran kontrol |
| “Bebeğime zarar vermek istiyorum…” | Eşleşme yok | Deterministik acil yardım yolu |
| “Az önce kendimi yaraladım; kanama durmuyor.” | Eşleşme yok | Fiziksel ihtiyaca yönelik acil mesaj |
| “Çok fazla ilaç aldım. Ölmek istemiyorum.” | Eşleşme yok | Niyetten bağımsız tıbbi yardım |
| “Bilgisayarım crash oldu.” | Yoksunluk/acil mesaj | Bu kelimeden klinik eşleşme üretilmez |

Eşleşme yokluğu güvenlik sonucu değildir. Tablodaki beklenen yönlendirmeler mühendislik sözleşmesidir; bağımsız klinisyen altın standardı değildir.

## Gerçekleştirilen doğrulama ve karşılaştırma

- **222 test geçti**; önceki 153 teste 69 yeni sınama eklendi. Yeni kapsam: ilgili önermenin olumsuzlanması, karşıt/zıt arka planlarla güncel niyetin korunması, tırnak içindeki bağlaçlar, başka kişi, belirsiz yaralanma ciddiyeti, koşullu/tekrarlayan fiziksel belirtiler, Türkçe kişi ekleri, özgün Unicode kanıt konumları, kayıt mahremiyeti ve eski/yeni denetimin tekrarlanabilirliği.
- **16 sentetik anlatı × 4 araştırma kolu = 64/64 çevrimdışı kayıt**, 0 yanıt hatası, 0 affect hatası. Script edilmiş model girdileri kullanıldı; gerçek LLM kalitesi veya klinik başarısı ölçülmedi.
- Aynı **16 sentetik geliştirme örneğinde 11 yönlendirme değişti**. Eski: 12 eşleşmesiz, 4 sabit acil yol. Yeni: 3 eşleşmesiz, 8 sabit acil yol, 5 yönlendirmeli yol. Bu dağılım başarı oranı değildir; örnekler geliştirmede görülmüştür.
- Aynı **155 etiketsiz geliştirme kaydında 8 karar değişti**. Eski: 147 eşleşmesiz, 8 yönlendirmeli. Yeni: 140 eşleşmesiz, 14 yönlendirmeli, 1 sabit profesyonel yardım yolu. Önceki 8 yönlendirmeli kayıt eşleşmesiz duruma düşmedi; bir kayda ek eşleşmeler geldi. Renkler uzman etiketi sayılmadı; duyarlılık, özgüllük ve doğruluk **hesaplanmadı**.
- İlk karşılaştırmada iki Türkçe kişi eki gerilemesi ve zamansal/tekrarlayan fiziksel anlatılarda gereksiz acil yönlendirme adayı görüldü; bunlar nihai sonuçlardan önce düzeltilip regresyon kapsamına alındı. Fazla eşleşme üretmek tek başına iyileşme kabul edilmedi.
- Kod derleme, `git diff --check`, özgün kanıt konumları ve karşılaştırma dosyalarının kod hash'leri kontrol edildi. Yeni bağımlılık gerekmedi.

Yerel karşılaştırma: `runtime/rule_audits/rule-audit-92_8b236/comparison.json`; kaynak sürümleri `manifest.json` içinde. Yeni/eskisi aynı metin hash'leri üzerinde çalışır, anlatıları çıktıya kopyalamaz. Eski davranış `detect_keyword_flags`, yeni davranış `detect_red_flags` giriş noktasıyla açıkça ayrılmıştır; eski motor sessizce değiştirilip “önce” diye sunulmaz.

Çevrimdışı dört kollu koşu: `runtime/context_rule_pilots/run_20261027_100243_900566_e8c86ffc/`. Kayıtların tamamı `offline_stub` olarak işaretlidir; insan/yargıç puanları yoktur.

Yeniden çalıştırma:

```bash
python -m pytest -q
python audit_rule_router.py --pool runtime/development_pool/POOL_DIZINI/pool.json
```

## Hâlâ kanıtlanmayanlar

Gerçek kullanıcı dilinde klinik duyarlılık/özgüllük, yanlış acil yönlendirme oranı ve kullanıcı yararı ölçülmedi. Kılavuzlar dil kalıplarını doğrulamadığı için yeni Türkçe ifadeler ve kararlar bağımsız uzman incelemesi gerektirir. Örtük, farklı dilli veya kapsam dışı cümleler kaçabilir. Başka kişiye ve önceki mesaja gönderimler tümüyle çözülmez. Modelin verilen yönergeyi gerçekten uygulaması da ayrı sınanmalıdır.

Bu çalışma, bilinen hataları üreten karar mantığını ve incelenen regresyonları düzeltir; “Türkçe niyet anlama problemi tümüyle çözüldü” veya “klinik güvenlik kanıtlandı” sonucu vermez. Sonraki bilimsel kontrol, geliştirmede görülmemiş ailelerden örneklerin bağımsız klinisyen değerlendirmesiyle aynı karar sözleşmesine karşı sınanmasıdır. [Doğrulama yol haritası](VALIDATION_ROADMAP.md) bu ayrımı korur.
