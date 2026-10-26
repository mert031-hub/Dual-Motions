# Sonraki geliştirme ve doğrulama planı — taslak

26 Ekim 2026. Bu belge yapılmış iş listesi değil, kaynak incelemesinden çıkan önerilen sıradır. Dayanaklar ve sürümler: [klinik inceleme](CLINICAL_EVIDENCE_REVIEW.md). Amaç: kılavuzlara dayanan yönergelerin gerçek yanıt davranışına ne ölçüde yansıdığını ölçmek ve bilinen bağlam hatalarını kontrollü biçimde gidermek.

## Öncelik gerekçesi

Şu anda 133 test mühendislik akışını doğruluyor. 48 kayıtlık offline pilot sabit yanıtlar kullanıyor; modelin istemsiz düşünceyi niyetle karıştırmadığını veya Critic'in hatalı yanıtı yakaladığını göstermiyor. Anahtar sözcük motoru hâlâ geçmiş/alıntı/olumsuzlamayı anlayamıyor. Bu nedenle sıradaki en değerli iş, yeni tanı başlıkları veya daha uzun promptlar eklemekten önce **bağlamı ayrı alanlarla temsil etmek ve gerçek davranışı kör değerlendirecek altyapıyı kurmak**.

Mevcut 155 kayıt geliştirme verisi olarak kalır; renkler doğrulanmış klinik etiket değildir. Metnini gördüğümüz ve kuralları geliştirdiğimiz kayıtları daha sonra bağımsız test diye sunamayız. Bağımsız örnekler farklı süreçle hazırlanmalı ve geliştirme ekibinden saklanmalıdır. Yeniden ifade edilen aynı senaryolar aynı ailede tutulur.

## 1. Kaynaklı bağlam şeması ve etiketleme paketi

**Bizim yapacağımız:** Tanı veya düşük/orta/yüksek risk etiketi yerine ayrı gözlemlenebilir alanlar tanımlamak: anlatılan kişi (kendi/başkası/alıntı), zaman (geçmiş/şimdi/belirsiz), düşüncenin istemsizliği, ifade edilen istek/niyet, plan/hazırlık, gerçekleşmiş eylem/yaralanma/zehirlenme, fiziksel ihtiyaçlar, yardım talebi ve bilinmeyenler. Alanlar birbiri yerine geçmez; örneğin geçmiş eylem ve mevcut niyet birlikte bulunabilir. Söylenmemiş bilgi `unknown` olur; `false` sayılmaz. Her olumlu çıkarım kendi metin alıntısı/konumuyla bağlanır.

JSON Schema, etiketleme yönergesi, birkaç doldurulmuş sentetik örnek, anlaşmazlık alanı ve veri kaynağı/izin/aile bilgisi hazırlanır. Kaynak atfı kişinin tanısını doğrulayan kanıt gibi gösterilmez. Başlangıç kapsamı: istemsiz düşünce–niyet, geçmiş–güncel, mecaz/alıntı, fiziksel acil ihtiyaç. Her bozukluk için ayrı tanı sınıflandırıcısı yapılmaz.

**Sizin katkınız:** Arkadaşınızla günlük Türkçedeki ifade biçimleri ve kısa karşılaştırmalı örnekler toplayabilirsiniz; kaynak URL'si, öneri/sayfa, hangi ayrımı gösterdiği ve örneğin alıntı mı sizin yazdığınız kurgu mu olduğu kaydedilir. Kimlikli hasta anlatısı paylaşılmamalı. Sizden klinik karar vermeniz beklenmez; arkadaşınızın klinik yetkinliği varsayılmaz.

**Klinik katkı:** Yetkin değerlendiriciler yönergeyi ve yorum gerektiren örnekleri inceler. Mümkünse en az iki bağımsız değerlendirme, ardından anlaşmazlıkların gerekçeli çözümü. Uzlaşı etiketleri saklanırken ilk bağımsız puanlar silinmez. İlk küçük örnek grubu yönergeyi düzeltmek içindir, performans sınavı değildir.

**Tamamlanma koşulu:** Alan tanımları, `unknown` kullanımı, kanıt bağlama ve anlaşmazlık süreci açık; şema teknik olarak doğrulanıyor; klinik inceleme durumu kayıt bazında görünür. Değerlendiriciler arası uyum alan bazında, bilinmeyen oranı ve ham anlaşmazlıklarla raporlanıyor. Keyfî bir uyum yüzdesi klinik onay eşiği ilan edilmiyor.

## 2. Bağlama duyarlı aday katman ve gölge karşılaştırma

**Bizim yapacağımız:** `expression_review.py` ile üretim kuralları arasına bu şemayı kullanan deneysel bir aday değerlendirme katmanı koymak. `semantic_triage.py` içinde kategori başına ayrı kanıt ve bağlam istemek; tek bir geçerli alıntının ilgisiz bütün kategorileri doğrulamasına izin vermemek. Alıntı varlığı yalnız teknik destek kontrolüdür; anlamsal doğruluk ayrıca değerlendirilir. Hatalı şema, eksik kanıt, çelişki ve zaman aşımında açık belirsizlik kaydı gerekir.

Örnek çiftleriyle sınanır: “geçen yıl ... dedim” / “şimdi ... yapacağım”; “ya zarar verirsem diye korkuyorum” / “zarar vermek istiyorum”; mecaz / gerçekleşmiş eylem. Ayrıca iki bağlamın aynı mesajda bulunması, üçüncü kişi için acil yardım isteği, negasyonun yalnız bir cümleyi kapsaması, yazım hataları, Türkçe çekimler ve çok turlu konuşmalar eklenir. Açık mevcut tehlike, önceki sakin bir cümle veya istemsiz düşünce ifadesi nedeniyle silinemez. Hiç eşleşme olmaması güvenli sonucu değildir.

İlk aşamada üretim davranışı değiştirilmez; eski/yeni kararlar ve anlaşmazlık nedenleri yan yana kaydedilir. Yalnız karar değiştiren örnekleri değil, kaçırılan ihtiyaçları da incelemek için bağımsız örneklem kullanılır.

**Tamamlanma koşulu:** Eksik/yanlış kanıtla kategori kabul edilmediği teknik olarak doğrulanıyor; gölge farkları uzman incelemesine sunulabiliyor. Klinik inceleme olmadan otomatik bayrak düşürme devreye alınmıyor. Yeni katman düşük risk/gelecek intihar tahmini üretmiyor (NG225 1.6.1–6); ihtiyaç/yanıt yönlendirmesi olarak ele alınıyor.

## 3. Critic'i ayrı bir deneyle sınama

Critic'in değerlendirdiği taslakları üreticiden bağımsız kontrol edebileceğimiz bir sınama paketi hazırlanır. Her senaryoda uygun yanıt, belirli bir ihlal içeren yanıt ve sınırda/yorum gerektiren yanıtlar bulunur. Örnek ihlaller: istemsiz düşünceyi niyet sayma; “kesin güvendesin”; göğüs ağrısını kaygıyla açıklama; ilacı bırakma/doz talimatı; travma ayrıntısına zorlama; gerekli güvenlik önerisini aşırı tavsiye diye reddetme. Bu örnekler kılavuzlardan türetilmiş mühendislik uyarlamaları olarak işaretlenir ve uzmanlarca değerlendirilir.

Ayrı ölçümler: uzman referansına göre uygunsuz taslağı kabul, uygun taslağı reddetme, ihlal türünü yanlış belirleme, gerekli öğeyi kaçırma. Revizyonun yeni ihlal oluşturması ve gereksiz acil yönlendirme ayrıca izlenir. Red kararı tek başına başarı sayılmaz; son yanıt değerlendirilir. Aynı model ailesinin üretici ve yargıç olması bağımsız klinik doğrulama sağlamaz.

**Tamamlanma koşulu:** Hata türü bazında pay/payda ve belirsizlik raporlanabiliyor; bütüncül “güvenlik skoru” bu farkları gizlemiyor. Bu aşama gerçek model erişimiyle yapılacak değerlendirmeye hazırlıktır; sabit fixture sonuçları model başarısı diye sunulmaz.

## 4. Kör insan değerlendirmesi ve gerçek A/B/C/D pilotu

Değerlendirme paketi önce hazırlanır: sistem adı/kolu saklanan yanıtlar, rastgele sıra, değerlendirme kimliği, rubric sürümü ve kaynak senaryo ailesi. H1 duygusal uygunluk, H2 aşırı tavsiye/yönlendiricilik için açık davranış çıpaları yazılır. Gerekli güvenlik bilgisi sırf doğrudan diye cezalandırılmaz; sorusuz uygun bir yanıt sırf soru yok diye başarısız sayılmaz. Güvenlik, duygusal uygunluk ve kullanıcının istediği yararlılık ayrı puanlanır. H3 için doğrulanmamış bileşik puan eklenmez; H4 için bağımsız duygu koşulları gerekir.

Model sağlayıcısı, veri kullanım koşulları, bütçe ve örnekleme planı netleştikten sonra izinli/sentetik veriyle küçük canlı pilot yapılır. Gerçek hasta üzerinde çalışma bu yazılım pilotunun kapsamı değildir; ayrıca etik ve klinik süreç gerektirir. Tüm kollarda ortak güvenlik sınırları korunur; yalnız araştırılan bileşen değişir. Ortak sabit kriz yanıtları Policy karşılaştırmasını şişirmemesi için ayrı raporlanır.

Geliştirme ve bağımsız değerlendirme aile bazında ayrılır; model/prompt/rubric sürümü ve üretim parametreleri dondurulur. Tekrarlar ve aynı aileden paraphrase'ler bağımsız gözlem sayılmaz. Birincil sonlanımlar, dışlamalar, örneklem gerekçesi ve analiz yöntemi sonuçlar görülmeden yazılır. Örneklem büyüklüğü pilot varyansı/hedeflenen fark ve klinik anlamlılıkla gerekçelendirilir; gelişigüzel bir sayı “yeterli” ilan edilmez. İnsan puanlarıyla LLM yargıcının uyumu ayrıca raporlanır.

Gerçek çağrı, retry ve token kullanım kaydı eklenir; mevcut `llm_calls` mantıksal bileşen sayısıdır. Gecikme, hata, çekimserlik, gereksiz yönlendirme ve maliyet de izlenir. Canlı model çıktıları manuel örnek kontrolünden geçirilmeden yalnız test sayısına dayanılarak başarı iddiası kurulmaz.

**Tamamlanma koşulu:** Kör insan değerlendirmesi ile yazılım/LLM yargıç çıktıları ayrı ve izlenebilir; bağımsız veriye sızma yok; sonuçlar keşifsel sınırlarıyla raporlanıyor. Prompt sürümü değişirse önceki koşu ile doğrudan aynı deney gibi birleştirilmiyor.

## 5. Üretim kararlarını değiştirmeden önce inceleme

Gölge katmanın bağlam düzeltmelerini ana akışa taşıma kararı ölçülen hata profiline ve klinik incelemeye göre verilir. Özellikle bir acil bayrağı kaldıracak değişiklik için ilgili karşı örnekler, mevcut tehlikeyle birlikte bulunma testleri, başarısızlıkta davranış ve geri dönüş yolu gözden geçirilir. Onay eşikleri geliştirme sonuçlarına bakılıp sonradan uydurulmaz; amaç ve hata maliyetlerine göre önceden belirlenir. Bu plan böyle bir klinik uygunluk onayı verilmiş olduğunu varsaymaz.

Mevcut `risk_level` alanlarının ihtiyaç/yanıt yönlendirmesini açıkça anlatan alanlara sürümlü geçişi de bu aşamada planlanır; eski dosyalar için uyumluluk korunur. Kullanıcı ülkesine uygun acil bilgi, çok dilli metinlerin uzman dil incelemesi ve kayıt/mahremiyet politikası gerçek kullanım öncesi ayrıca tamamlanır.

## Şimdi başlayabileceğimiz somut paket

Bir sonraki geliştirme turu için öneri: **1. aşamanın şeması ve etiketleme formu + 2. aşamanın kategori başına kanıt doğrulaması + 4. aşamanın kör puanlama dosyalarının iskeleti**. Bunlar mevcut tanı/riski otomatik değiştirmeden hazırlanabilir. Paralelde siz kaynaklı Türkçe karşılaştırmalı örnekleri, yetkin klinisyenler ise yorum/uygun yanıt değerlendirmesini sağlar. Yeni üretim davranışı için karar, bu materyal görüldükten sonra verilir.
