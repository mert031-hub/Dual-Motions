# Proje mantığı ve kanıt sınırları

Birincil tasarım kaynağı, kullanıcının sağladığı **Adaptive_Mental_Health_AI_Control_Architecture.pdf**
(15 slayt). Bu belge bir makale derlemesi veya onaylanmış klinik protokol değildir.
31 makale PDF'i kataloglandı; slaytlar ve ilgili seçilmiş yöntem/bulgular incelendi.
Dosya sayısı bağımsız çalışma sayısı değildir: ön baskı/dergi sürümü çakışmaları ayrıca ayıklanmalıdır.

## Ana katkı

Slayt 4–6 ve 13: modeli yeniden eğitmek yerine hafif, modüler, modelden bağımsız
bir kontrol katmanı kurmak. V1–V3 metin tabanlıdır; ses/yüz, RL ve büyük fine-tuning
mevcut çekirdek hedef değildir.

1. **Affect estimation:** valence, arousal ve emotion; belirsizlik açıkça korunur.
2. **Response Policy Controller:** yanıt metni üretmez; strateji ve davranış parametreleri seçer.
3. **LLM:** ortak temel koşullar ve seçilen stratejiyle taslak üretir.
4. **Therapeutic Critic:** tanı/ilaç/zararlı içerik sınırları ve iletişim kriterlerini denetler.
5. **Sınırlı revizyon:** reddedilen taslak otomatik onaylanmaz. Varsayılan en fazla
   3 reddedilen taslak, dolayısıyla ilk üretimden sonra en fazla 2 yeniden üretimdir.

Deterministik kriz kapısı tüm ana kollarda ortaktır. Bu kayıtlar Policy etkisinin
ana analizinden ayrılır. Kriz koruması, ana araştırma sorusunun tamamı değildir.

## Slayt 9–10 ile eşleşen deneyler

| Slayt | Kod | Amaç |
|---|---|---|
| A | `study_baseline` | Ortak üretim koşulları; adaptif Policy/Critic kapalı |
| B | `study_policy` | Affect + strateji kontrolünün etkisi |
| C | `study_critic` | Adaptif Policy olmadan Critic/revizyon etkisi |
| D | `study_full` | Affect + Policy + Critic birleşimi |

| Hipotez | Ölçüm altyapısı | Bekleyen karar |
|---|---|---|
| H1: Policy duygusal uygunluğu artırır | B−A, `emotional_appropriateness` | Klinik puan ankrajları ve bağımsız doğrulama |
| H2: Critic aşırı tavsiye/yönlendiriciliği azaltır | C−A, ayrı `excessive_advice`/`excessive_directiveness` değerlendirmeleri | Operasyonel tanımlar, örneklem/güç ve çoklu test planı |
| H3: Birleşik sistem tek bileşenlerden daha başarılıdır | D−B ve D−C bileşen metrikleri | “Genel başarı” için önceden belirlenmiş birincil sonlanım; ağırlık uydurulmaz |
| H4: Performans duygusal durumlara göre değişir | Duygu koşuluna göre betimsel gruplar | Dengeli ve eşlenmiş senaryo tasarımı, bağımsız affect değerlendirmesi |

Hibrit triyaj başarısı slayttaki H2 değildir. Çok dillilik de slayttaki H3 değildir.
Önceki kod yorumlarındaki bu adlandırmalar düzeltilmiştir. Eski ablation kolları
geriye dönük ek deneyler olarak korunur; ana A/B/C/D yerine kullanılmamalıdır.

## Klinik ekipten beklenenler

- Arkadaştan istenmiş **50 vaka için kırmızı bayrak etiketleri** ve **risksiz kontrol vakaları**
  bekleniyor. Bunlar yerine yapay uzman etiketleri veya klinik doğrulanmış kontroller üretilmedi.
- Slayt 8: empati, validation, reflection, exploration, aşırı tavsiye ve yönlendiriciliğin
  kesin tanımları/puan ankrajları klinik ekip katkısıyla kesinleşmelidir. Şu anki rubrik taslaktır.
- Sabit Türkçe/İngilizce kriz mesajları ve eylem eşlemeleri klinisyen onayı bekler.
  Diğer dillerin İngilizceye düşmesi tamamlanmış çok dilli güvenlik desteği değildir.

Yanıt puanlaması ile vaka kırmızı bayrak etiketi ayrı veri türleridir. Duygu koşulları
da kırmızı bayrak etiketlerinden türetilmez. Model çıktısı uzman etiketi yerine geçmez.
Eski vakalarda bulunmayan duygu alanının geriye dönük varsayılanı doğrulanmış duygu
etiketi değildir; `emotion_source=default_unverified` olarak izlenir ve H4 duygu
gruplarından çıkarılır. Bu alanın dolu olması da tek başına affect tahmin doğruluğu kanıtı değildir.

## İlgili literatürün uygulamaya etkisi

- Guo ve ark., *Large Language Models for Mental Health Applications: Systematic Review*
  ([10.2196/57400](https://doi.org/10.2196/57400)); Lawrence ve ark., *The Opportunities
  and Risks of Large Language Models in Mental Health* ([10.2196/59479](https://doi.org/10.2196/59479)):
  araştırma prototipi, klinik etkililik ve gerçek kullanım iddiaları ayrı tutulur.
- Arnaiz-Rodriguez ve ark., *Between Help and Harm* ([10.2196/88435](https://doi.org/10.2196/88435)):
  örtük/belirsiz krizlerde model zayıflıkları; belirsizlik kaydı, açık hata sayımı ve
  deterministik acil yolunun ağ çağrısından bağımsız tutulması önemlidir. Çalışmanın
  sonuçları bu prototipin doğrulandığı anlamına gelmez.
- Niu ve ark., *Rethinking Emotion Annotations in the Era of Large Language Models*
  ([10.1109/TAFFC.2025.3584775](https://doi.org/10.1109/TAFFC.2025.3584775)):
  duygu etiketleri özneldir ve insan/model algısı farklılaşabilir. Elle verilen koşul,
  model tahmini ve doğrulanmış affect etiketi ayrı kaydedilir.
- Croxford ve ark., *Evaluating clinical AI summaries with large language models as judges*
  ([10.1038/s41746-025-02005-2](https://doi.org/10.1038/s41746-025-02005-2)):
  yargıçların uzman puanlarıyla görev özelinde değerlendirilmesi önemlidir. Klinik
  özetleme için kullanılan rubriğin psikoterapötik yanıtlar için otomatik geçerli olduğu varsayılmaz.
- Genovese ve ark., *Artificial Authority: The Promise and Perils of LLM Judges in Healthcare*
  ve Gu ve ark., *A survey on LLM-as-a-judge*
  ([10.1016/j.xinn.2025.101253](https://doi.org/10.1016/j.xinn.2025.101253)):
  öz-kayırma, sıra ve uzunluk yanlılığı; kör/rastgele karşılaştırma ve klinisyen uyumu
  kontrolleri gerektirir. Yargıç çoğunluğu klinik gerçek kabul edilmez.

Eğitim alanındaki iki dilli duygu verileri ve ses/fizyoloji çalışmaları kavramsal
arka plan sağlayabilir; Türkçe metin tabanlı mental-health prototipinin doğruluk
kanıtı veya mevcut multimodal modül olarak sunulmaz.

## Doğrulama sınırları

Otomatik testlerdeki model ve uzman kayıtları yalnızca açıkça adlandırılmış test
fixture'larıdır; gerçek değerlendirme dosyası oluşturmaz. Bağımsız veri ve onaylı
rubrik olmadan bilimsel Recall/FNR/FPR, terapötik yarar veya H1–H4 kabulü raporlanmaz.
Anahtar/ağ erişimi olmadan sahte LLM testleri canlı API doğrulaması sayılmaz.
Yapılandırılmış bellek ve semantik triyaj ek araştırma bileşenleridir; geçerli klinik
bellek veya tamamlanmış güvenlik değerlendirmesi iddiası taşımaz.
