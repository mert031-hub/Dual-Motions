# Etiket bekleyen geliştirme havuzu

Bu yol uygulamanın `cases.load_cases()` havuzundan ayrıdır. Kaynak renklerini uzman
etiketine dönüştürmez, `cases_expert.json` üretmez, kuralları değiştirmez ve API
çağrısı yapmaz. Ekli Python modülleri çalıştırılmaz; yalnız üst düzey literal
atamalar AST ile okunur. Veri dosyaları ve sonuçlar Git tarafından dışlanan
`runtime/` altında tutulur. Hassas veriyi Git'e eklemeyin.

## Hazırlama

Python 3.12 ortamını kullanın. Kaynak dosya yollarını elinizdeki dosyalara göre verin:

```bash
python development_pool.py prepare \
  --cases-python /path/klinik_veriseti_155_vaka.py \
  --report-python /path/klinik_veriseti_kirmizi_bayraklar.py \
  --document /path/Klinik_Veriseti_155_Vaka_Birinci_Agizdan.docx \
  --document /path/Klinik_Veriseti_Kirmizi_Bayraklar_Raporu.docx \
  --persist-text
```

`--persist-text`, bu işlemde kaynak dosyaların ve vaka metinlerinin yerel diskte
saklanacağını açıkça belirtir; yalnız kullanma izniniz olan veri için kullanın.
Varsayılan deney kayıtlarının metinsiz olması değişmez. Her hazırlama ayrı dizin
oluşturur. Dört kaynak dosya byte düzeyinde korunur ve SHA-256 değerleri kaydedilir.
Word belgeleri kaynak arşividir; bu komut Word–Python eşdeğerliği denetimi yapmaz.

`pool.json` içindeki `records` yalnız geliştirme içindir. `source_record` orijinal
Python kaydını, `source_color` doğrulanmamış rengi, `source_report_entry` varsa
rapordaki iddiayı korur. Bunlar `expected_red_flag`, `expected_flags`,
`expected_risk` veya duygu etiketi yerine geçmez; bu alanlar null kalır.

Kimlikler kaynak Python hash'inin öneki ve kaynak vaka numarasıyla adlandırılır.
Eski id+25 ve birebir aynı başlık kanıtı varsa `legacy_candidate_id` ve ortak
`family_id` kaydedilir. Bu bağ klinisyen/üretici teyidi bekleyen aile adayıdır;
anlamsal eşdeğerlik veya aynı klinik etiket garantisi değildir. Diğer kayıtlardaki
tekil aile kimlikleri bağımsızlık kanıtlamaz. Bu eşleme yalnız incelenen 155 vakalık
kaynak düzeni içindir; başka veri setlerine genel eşleme yöntemi olarak kullanmayın.

Bütün bu anlatımlar zaten incelendiği için tamamı `development_only` tutulur;
bu işlem bağımsız test/holdout ayırmaz. Gelecek bağımsız veri aile düzeyinde, henüz
kurallara/model seçimine göre incelenmeden ayrılmalıdır. Kaynak içindeki tanı ve
müdahale açıklamaları kullanıcıya gönderilecek talimat değildir.

## Mevcut deterministik davranışı kaydetme

Hazırlama komutunun yazdırdığı pool.json yolunu kullanın:

```bash
python development_pool.py snapshot --pool runtime/development_pool/POOL_DIZINI/pool.json
```

Bu komut depodaki gerçek `run_triage()` fonksiyonunu çalıştırır. Kayıt başına
bayraklar, eşleşen kural ifadesi, eylem, tier, sabit cevap anahtarları ve yönerge
anahtarlarını kaydeder. Ana workflow, semantik triyaj, üretim, Critic veya yargıç
çalışmaz. Bu çıktı tam sistem performansı değildir. Yeni kurallar eklendikten sonra
aynı havuzda tekrar çalıştırıp davranış değişikliği incelenebilir.

Her koşu ayrı, üzerine yazılmayan bir dizin oluşturur:

- `observations.json`: metinleri tekrar etmeden kayıt bazlı davranış ve sayımlar.
- `manifest.json`: havuz hash'i, kaynak hash'leri, kod hash'leri, Python sürümü,
  Git commit'i ve takip edilen dosya değişiklikleri. Yeni dosyalar henüz commitli
  değilse tam kod hash'leri yine kaydedilir; Git commit'i tek başına koşu sürümü değildir.
- `summary.md`: metinsiz, okunabilir vaka/renk/tier/kural tablosu.

Eşleşme olmaması güvenli demek değildir. Renk gruplarına göre sayımlar yalnız
betimseldir; Recall/FNR/FPR veya pozitif/negatif doğruluk hesabı yapılmaz. Metinlerin
kendisi havuzda saklanır; gözlem çıktısı anlatımları içermez, yalnız kural sözlüğündeki
eşleşen ifadeyi içerir. Kaynak veya metin değişirse eski kayıtların üzerine yazmak
yerine yeni havuz hazırlayın.

## Doğrulama

```bash
python -m pytest -q test_development_pool.py
python -m pytest -q
```

Testler; kaynak kodun çalıştırılmamasını, kimlik çakışmalarının reddini, renklerin
uzman etiketi yapılmamasını, aile bağında başlık kanıtını, gerçek triyaj gözlemini,
metin bütünlüğünü ve tekrar koşularda eski çıktıların korunmasını denetler.
