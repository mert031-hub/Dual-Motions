# Revizyon notları (Faz 1 + Faz 2)

## Dosya yapısı
| Dosya | Durum | Not |
|---|---|---|
| `config.py` | yeni | Modeller, limitler, ablation kolları, sürüm |
| `messages.py` | yeni | Dil bazlı sabit mesajlar (TASLAK, klinisyen onayı gerekir), Policy yönergeleri |
| `llm_factory.py` | yeni | Tembel model oluşturma, timeout/retry; import anında API anahtarı gerekmez |
| `red_flags.py` | **yalnızca `_fold` düzeltildi** | Kural verisi (klinisyenin) değişmedi |
| `triage.py` | yeni | Çoklu bayrak, ciddiyet sıralaması, eylem şeması (canned / guided) |
| `workflow.py` | yeniden yazıldı | Fail-closed, Critic bağlamı, ablation modları, `run_pipeline` |
| `cases.py` | yeniden yazıldı | Vaka şeması + yükleyici (eski runner kodu `batch_tester.py`'ye taşındı) |
| `cases_legacy.py` | yeni (senin 50 vaka) | Dosya adı değişti, içerik aynı |
| `judge.py` | yeni | Kör mutlak puanlama + kör A/B, çoklu yargıç |
| `metrics.py` | yeni | Crisis Recall, FNR, FPR, Wilson GA, bootstrap |
| `batch_tester.py` | yeniden yazıldı | Ablation, paralel, hata yakalama, manifest, CSV/JSONL |
| `app.py` | güncellendi | Yeni akış, kör karşılaştırma, ablation arayüzü |
| `tests/` | yeni | 63 test (sahte LLM, API çağrısı yok) |

## Word taslağı kontrol listesi
**Faz 1**
- [x] Üç ret sonrası otomatik onayı kaldır → `safe_fallback_node` (sabit mesaj + `needs_human_review`)
- [x] Critic'e kullanıcı mesajı ve klinik bağlam → `_critic_prompt` (mesaj, geçmiş, trijaj bayrakları, zorunlu yönergeler)
- [x] cases/batch_tester import yapısı → döngüsel import bitti
- [x] Trijajda çoklu bayrak ve eylem şeması → `triage.py`
- [x] API hataları için güvenli fallback + testler → `llm_factory`, `_technical_failure`, `tests/`

**Faz 2**
- [x] Uzman etiketli vaka şeması → `cases.py` (`expected_red_flag`, `expected_flags`, `expected_risk`, `language`, `adversarial_type`, `label_status`)
- [x] Taraflı Arbiter prompt'u düzeltildi → `judge.py`
- [x] Kör A/B → `judge_pair` (rastgele sıra, etiketsiz, Tie seçeneği)
- [x] Crisis Recall, FNR, FPR → `metrics.py` (trijaj düzeyi + yanıt düzeyi)
- [x] Vanilla / Triage / Critic / Full ablation → `config.SYSTEMS`, `batch_tester.py` (+ ek `policy_only` kontrol kolu)

**Sonraki tur (Faz 3–4):** hibrit semantik trijaj, klinik bellek, dil bazlı değerlendirme kümeleri, Critic maliyet deneyleri, Docker, güvenli loglama, klinisyen dashboard'u, rapor.

## Dikkat edilmesi gerekenler
1. **Etiket eksikliği:** 50 vakada yalnızca `risk_level` var. Crisis Recall/FNR/FPR için klinisyenin her vakaya `expected_red_flag` (ve olabildiğince `expected_flags`) vermesi gerekir → `cases_expert.json`. Geçici deneme: `LEGACY_HIGH_AS_RED_FLAG=1`.
2. **Kontrol vakası yok:** 50 vakanın hepsi depresif/riskli. FPR ölçülemez. Risksiz kontrol vakaları ve İngilizce/örtük/yazım hatalı varyantlar gerekir (`S07, S08, S11, S14` örnek).
3. **Veri sızıntısı:** `red_flags.py` anahtar kelimelerinin çoğu bu 50 vakanın metninden türetilmiş. Kural motorunu aynı vakalarda ölçmek şişirilmiş sonuç verir; bağımsız vakalarla ölç.
4. **Yargıç bağımsızlığı:** `JUDGE_MODELS` yalnızca üretim modelini içeriyorsa kendi çıktısını kayırma riski var.
5. **Sabit mesajlar:** `messages.py` metinleri klinisyen onayı bekliyor; yalnızca TR/EN var, diğer diller İngilizceye düşer.
6. **Hâlâ geçerli sınırlar:** Duygu hâlâ elle seçiliyor (Modül 1 otomatik değil); trijaj Türkçe anahtar kelimeye dayalı; LLM yargıç klinik doğruluk kanıtı değildir.

## Çalıştırma
```bash
pip install -r requirements.txt
cp .env.example .env        # GROQ_API_KEY girin
pytest                      # API gerektirmez
streamlit run app.py
python batch_tester.py --max-cases 5 --workers 2   # küçük deneme
```
