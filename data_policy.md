# Araştırma verisi politikası — onay bekleyen taslak

Bu bir veri yönetişimi veya etik kurul onayı değildir. Prototip, slayt 11 ve 14 uyarınca
kontrollü sentetik senaryolar içindir; gerçek hasta verisi girilmemelidir.

- 50 eski senaryonun metni korunur. `risk_level`, uzman kırmızı bayrak etiketi değildir.
  Arkadaştan beklenen etiketler ve risksiz kontroller sisteme uydurularak eklenmez.
- `cases_expert.json` yalnızca atıflı uzman içe aktarımıyla oluşur. BELİRSİZ kaydı
  `expected_red_flag=null` olarak korunur ve oranlardan çıkarılır. Dosyayı Git'e eklemeyin.
- Sohbet ve yapılandırılmış bellek Streamlit oturumunda tutulur; varsayılan denetim
  kaydı konuşma, alıntı, model yanıtı veya tanı içermez. Oturumlar arası kalıcı bellek yoktur.
- Benchmark metinleri varsayılan olarak diske yazılmaz. `--persist-text` yalnızca
  paylaşımı onaylı sentetik senaryolarda kullanılmalıdır. Açıldığında üretilen CSV/JSONL
  ve kör değerlendirme paketleri metin içerir; bunlar denetim logundan ayrı araştırma verisidir.
- `mask_identifiers` yalnızca basit e-posta ve numara örüntülerini maskeler; isimleri,
  adresleri veya bağlamsal tanımlayıcıları anonimleştirdiği iddia edilmez. Metinli denetim
  kaydı uygulamada varsayılan olarak açılmaz.
- Kör değerlendirme paketinin `.mapping.json` dosyası yalnızca koordinatörde kalır.
  Değerlendiriciye ayrı `review_app.py` ve yalnızca kör paket verilir.
- `AuditLog.purge(retention_days)` yalnızca kendi denetim dosyalarını siler. Dağıtım
  yöneticisi onaylanan saklama süresini belirleyip zamanlanmış görev kurmalıdır; kodda
  kendiliğinden klinik saklama süresi varsayılmaz. Benchmark ve etiket dosyalarının
  silinmesi ayrıca yönetilir. Sohbet temizleme, o oturumun denetim kayıtlarını da kaldırır.
- Parola kapısı araştırma erişimi içindir. Üretim kimlik yönetimi, TLS, merkezi hız
  sınırlaması, rol ayrımı, erişim incelemesi ve yedek silme süreçleri yerine geçmez.
  Docker dağıtımı parola ayarı yokken uygulama içeriğini açmaz; yerel geliştirme varsayılanı parolasızdır.

Gerçek katılımcılı kullanım öncesinde klinik ekip; aydınlatılmış onam, etik kurul,
veri işleme/yurt dışı aktarım koşulları, saklama-silme takvimi, kriz yönlendirmesi ve
sabit mesajları ayrıca onaylamalıdır. Bu belgede bir uyumluluk sertifikası iddiası yoktur.
