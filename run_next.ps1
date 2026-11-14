# Sıradaki adımlar (Windows PowerShell). Her adım hata verirse durur. Çalıştırmadan önce .env içinde GROQ_API_KEY olmalı.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$py = '.\.venv\Scripts\python.exe'
function Step($name, [scriptblock]$cmd) {
    Write-Host "`n=== $name ===" -ForegroundColor Cyan
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "Adım başarısız: $name" }
}
Step '1/5 Etiket doğrulama (155)'   { & $py xlsx_to_cases.py check --filled .\etiket_sablonu_xlsx155_dolu.xlsx }
Step '2/5 İçe aktar (155)'          { & $py labeling_tools.py import --in .\etiket_sablonu_xlsx155_dolu.xlsx --out cases_expert.json --labeler Yavuz }
Step '3/5 İçe aktar (eski 50)'      { & $py labeling_tools.py import --in .\etiket_sablonu_eski50_dolu.csv --out cases_expert.json --labeler Yavuz }
Step '4/5 Birim testleri'           { & $py -m pytest -q }
Step '5/5 Hibrit trijaj (küçük deneme: 20 vaka)' { & $py hybrid_eval.py --max-cases 20 --sleep 3 }
Write-Host "`nHatasızsa tam koşu: $py hybrid_eval.py --sleep 3   (kota dolarsa --resume ekle)" -ForegroundColor Green
