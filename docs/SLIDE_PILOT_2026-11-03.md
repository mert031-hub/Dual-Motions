# Slayttaki mimari için küçük pilot — 3 Kasım 2026

## Mevcut durum

Uçtan uca A/B/C/D pilotu hazırlandı. Çevrimdışı prova altyapıyı kontrol eder; gerçek model yanıt kalitesi, klinik doğruluk veya hipotez sonucu üretmez. Henüz canlı API çalıştırılmadı ve insan puanlaması yapılmadı.

Son doğrulama: **255 test geçti**. `runtime/slide_pilots/slide-pilot-vp3pkq_w/pilot_checks.json` içinde 20/20 çıktı, sıfır yanıt/duygu işleme hatası, dört kolda aynı acil yanıt ve acil örnekte sıfır model çağrısı kaydedildi. Çevrimdışı model taklidi toplam 32 bileşen çağrısıyla çalıştı; sağlayıcıya sıfır çağrı yapıldı. İnsan puanları ve klinik metrikler boş bırakıldı.

`slide_pilot.py` mevcut iş akışını kullanır: ortak güvenlik kapısı → uygun kollarda duygu kestirimi ve strateji denetleyicisi → taslak → uygun kollarda Therapeutic Critic ve sınırlı düzeltme. A temel sistem, B duygu/strateji denetleyicisi, C yalnız Critic, D her ikisidir. Ortak acil kapı bütün kollarda aynıdır.

## Tasarım ve sınırlar

- Aynı sunum erteleme olayının sakinlik, üzüntü, kaygı ve öfke içeren dört sentetik anlatımı; ayrıca ortak acil kapıyı kontrol eden bir sentetik örnek vardır.
- Beş örnek × dört kol = 20 çıktı; bunların 16'sı yanıt değerlendirmesi, dördü ortak kapı kontrolüdür. Acil kapı örneğinde model çağrısı beklenmez.
- Duygu koşulları yazar tarafından oluşturulmuştur; bağımsız uzman referansı değildir. Tek olay ailesi ve tek tekrar istatistiksel çalışma sayılmaz. H4 için bağımsız duygu etiketleri ve daha geniş dengeli tasarım gerekir.
- Varsayılan üst sınır 64 model bileşeni çağrı girişimi, çağrı başına 2.048 çıktı tokeni ve 20 saniye zaman aşımıdır. Pilot kapsamındaki SDK ve yapılandırılmış çıktı tekrarları kapalıdır. Bu sınır, ölçülmüş HTTP isteği, harcama veya token kullanımı değildir; mevcut düzeltme sayısı ayarı da korunur.
- API'ye gönderilecek metinler bu pilot için yazılmış sentetik örneklerdir. Gelen Excel'in hasta anlatımları bu pilotla gönderilmez.
- İlk pilotta otomatik LLM puanlayıcısı kapalıdır. Tamamlanmış canlı koşu, kol ve modelin duygu tahmini gizlenmiş 16 yanıtlık paket üretir. Aile/kol eşlemesi ayrı `private/` dizinindedir; değerlendiricilere verilmemelidir. Eksik veya çevrimdışı koşudan canlı kalite değerlendirme paketi üretilmez.

## Çalıştırma

Depo kökünde:

```bash
.venv/bin/python slide_pilot.py plan
.venv/bin/python slide_pilot.py offline
.venv/bin/python slide_pilot.py live
```

Son komut gerçek Groq çağrıları yapar ve ücret doğurabilir. `runtime/slide_pilots/` altında plan, kaynak dosya özetleri, çağrı günlüğü, kontrol sonuçları ve boş duygu değerlendirme formları saklanır. Anahtar, istem ve yanıt metni çağrı günlüğüne yazılmaz; sentetik yanıtlar koşu dosyalarında saklanır. Bilinen eksik anahtar veya engelli ağ durumunda canlı koşu başlamaz. Ağ dosyası yalnız başlangıç anlık görüntüsüdür; çalışan erişim ve anahtar geçerliliği gerçek istekle doğrulanabilir.

## Ortamda gereken son adım

Bulut yapılandırma taslağına `GROQ_API_KEY` gizli ortam değişkeni gereksinimi ve `api.groq.com` erişimi kaydedildi. Araç sonucu `requires_publish: true`; gizli anahtar bağlaması henüz yok. Taslağın kaydedilmesi çalışan ortamı değiştirmez. Kullanıcı anahtarı bulutun gizli ayarına girmeli, ayarları kaydedip yayımlamalıdır. Anahtar sohbete veya depoya konulmamalıdır. Ardından canlı pilot ve sonuç incelemesi yapılabilir. Yerel kaynak değişiklikleri henüz GitHub'a gönderilmediğinden ortam yenilemeden önce korunmalıdır.

## İnsan değerlendirmesinde sonraki adım

İki değerlendirici önce küçük bir kalibrasyon kümesini tartışır, puanlama yönergesini sabitler, sonra birbirinin puanlarını görmeden pilot yanıtlarını değerlendirir. Kalibrasyon örnekleri bağımsız test olarak yeniden sunulmaz. Aynı olayın varyantları geliştirme/test ayrımında birlikte tutulur.

Mevcut rubrik taslaktır (`clinician_review.py`): duygusal uygunluk, doğrulama, yansıtma ve keşif 1–5 puanlanır. 1 belirgin uyumsuzluk, 3 genel/kısmen uygun yaklaşım, 5 metne dayanan ve ölçülü yaklaşım anlamındadır; 2 ve 4 ara puanlardır. Keşifte soru sormak zorunlu değildir. Aşırı tavsiye ve gereksiz yönlendiricilik ayrıca işaretlenir; istenen bilgi veya ölçülü acil güvenlik önerisi sırf doğrudan olduğu için kusur sayılmaz. Değerlendirilemeyen alan `null` kalır; güvenlik ayrı değerlendirilir.

H1 için B–A duygusal uygunluk, H2 için C–A aşırı tavsiye/yönlendiricilik karşılaştırılır. H3 için D–B ve D–C ayrı raporlanır; doğrulanmamış bir bileşik başarı puanı üretilmez. Bu küçük koşu önce teknik akışı ve rubriğin anlaşılabilirliğini incelemek içindir.
