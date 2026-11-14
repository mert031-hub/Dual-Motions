# Revizyon notları – Kasım dönemi (Faz 3–4 hazırlığı)

## Kod değişiklikleri
| Dosya | Değişiklik |
|---|---|
| `llm_factory.py` | 429 (hız sınırı) için bekleyerek yeniden deneme (`RATE_LIMIT_RETRIES`, `RATE_LIMIT_MAX_WAIT_S`); günlük kotada bekleme yok, hata hemen yukarı (fail-closed). Şema yeniden denemelerinden ayrı sayaç. |
| `batch_tester.py` | `--expert-only`, `--no-pairs`, `--case-ids`; `responses.csv`'ye `critic_reason` sütunu. |
| `hybrid_eval.py` (yeni) | Kural ve hibrit trijajı uzman etiketli vakalarda karşılaştırır (Policy/Critic çağrılmaz, vaka başına ≤1 çağrı). Alt grup (psikiyatrik/tıbbi/ergen), Wilson GA, `--resume`. |
| `xlsx_to_cases.py` | 155'lik tablodan kör şablon, geçici etiket, dev/test bölünmesi; `check` ile doldurulmuş şablon doğrulama. |
| `.gitignore` | `cases_provisional_*.json`, `xlsx155/`, `etiketler/`, `*_dolu*.csv` eklendi. |
| `pytest_1.ini` | Silindi (yinelenen, `pytest.ini` geçerli). |

## Veri / etiket
- 155'lik küme + eski 50 + K01–K30 + V01–V20 klinisyence kör etiketlendi → `cases_expert.json` (255 vaka, 250 etiketli: 81 pozitif, 169 negatif; 5 BELİRSİZ).
- Çelişkiler (X037, X075, X039, X062, X121) için "düzenlenmiş" şablon üretildi; orijinal etiketler esas alındı.
- Kapsam ve alt grup raporlama kuralları: `docs/RESEARCH_SCOPE.md`.

## Bulgular (kural tabanı, LLM'siz)
- Bağımsız 155'lik kümede kural recall'u 6/46 (psikiyatrik 1/24). Eski 50 + K + V kümesinde 16/35: anahtar kelimeler bu vakalardan türetildiği için şişkin (veri sızıntısı; bkz. önceki "Dikkat edilmesi gerekenler" madde 3).
- Ergen vakalarda Full kol (D) yetişkine yönlendirmeyi kaybediyor (X052, X054, X055; n çok küçük) → klinisyene Critic kriteri sorusu olarak iletilecek.

## Açık işler
- İçe aktarma komutlarını yerelde doğrula; `hybrid_eval.py` tam koşusu.
- Geliştirme kümesinde A/D yeniden koşusu (`critic_reason` ile); ayarları dondur; test kümesi tek koşu.
- Klinisyen kör derecelendirmesi; `research_report.py` ile rapor.
- Temizlik: `fillna` uyarıları (research_report.py:22, clinician_review.py:43), evrensel `requirements.lock`, Groq anahtarı iptali.
