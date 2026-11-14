# Araştırma verisi politikası — onay bekleyen taslak

Bu bir veri yönetişimi veya etik kurul onayı değildir. Prototip, slayt 11 ve 14 uyarınca
kontrollü sentetik senaryolar içindir; gerçek hasta verisi girilmemelidir.

- Vaka metinleri sentetiktir. `risk_level`, uzman kırmızı bayrak etiketi değildir.
  Uzman (kırmızı bayrak) etiketleri klinisyen tarafından verilmiş ve atıflı olarak içe
  aktarılmıştır (`labeler` alanı); etiketlerle sistem çıktısı arasında farklılık olduğunda
  uzman etiketi referanstır. Etiketler ve risksiz kontroller proje tarafından uydurulmaz.
- `cases_expert.json`, etiket şablonları (`*.xlsx`, `etiketler/`) ve geçici etiket dosyaları
  yalnızca yerelde tutulur; Git'e, Docker imajına ve paylaşılan Project/doküman alanlarına
  eklenmez. Paylaşılan alanlara yalnızca vaka metni içermeyen özetler ve sayılar konur.
  BELİRSİZ kaydı `expected_red_flag=null` olarak korunur ve oranlardan çıkarılır.
- Gizli bilgiler (API anahtarı, parola hash'i) yalnızca yerel `.env` veya güvenli ortam
  değişkenlerinde tutulur; kaynak koduna, Git'e, paylaşılan Project/doküman alanlarına ve
  sohbet/log çıktısına yazılmaz. Açığa çıkan anahtar iptal edilip yenilenir.
- Sohbet ve yapılandırılmış bellek Streamlit oturumunda tutulur; varsayılan denetim
  kaydı konuşma, alıntı, model yanıtı veya tanı içermez. Oturumlar arası kalıcı bellek yoktur.
- Benchmark ve `hybrid_eval.py` çıktıları varsayılan olarak vaka metni içermez.
  `--persist-text` yalnızca paylaşımı onaylı sentetik senaryolarda kullanılmalıdır. Açıldığında
  üretilen CSV/JSONL ve kör değerlendirme paketleri metin içerir; bunlar denetim logundan
  ayrı araştırma verisidir.
- Vaka metinleri değerlendirme sırasında harici model sağlayıcısına (Groq, yargıç modeli)
  gönderilir. Yalnızca sentetik veri için kabul edilebilir; gerçek veride yurt dışı aktarım
  koşulları ayrıca onaylanmalıdır.
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
