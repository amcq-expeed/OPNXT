param(
  [string]$DocsDir = "docs",
  [string]$OutDir = "docs/pdf",
  [string]$CssPath = "templates/pandoc/style.css"
)

function Test-ToolCommand {
  param([Parameter(Mandatory=$true)][string]$Name)
  $found = Get-Command $name -ErrorAction SilentlyContinue
  if (-not $found) {
    Write-Host "[!] Missing required tool: $name" -ForegroundColor Yellow
    Write-Host "    Please install Pandoc: https://pandoc.org/installing.html" -ForegroundColor Yellow
    Write-Host "    Please install wkhtmltopdf: https://wkhtmltopdf.org/downloads.html" -ForegroundColor Yellow
    throw "Missing tool: $name"
  }
}

Test-ToolCommand -Name pandoc
Test-ToolCommand -Name wkhtmltopdf

New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

$files = Get-ChildItem -Path $DocsDir -Filter *.md -File
if (-not $files) {
  Write-Host "No Markdown files found in $DocsDir" -ForegroundColor Yellow
  exit 0
}

foreach ($f in $files) {
  $base = [System.IO.Path]::GetFileNameWithoutExtension($f.Name)
  $out = Join-Path $OutDir ($base + ".pdf")
  Write-Host ("Rendering {0} -> {1}" -f $f.FullName, $out)
  $pandocArgs = @("-s", $f.FullName, "-t", "html5", "--pdf-engine=wkhtmltopdf", "-o", $out)
  if (Test-Path $CssPath) { $pandocArgs = $pandocArgs + @("-c", $CssPath) }
  $metaTitle = @("--metadata", ("title={0}" -f $base))
  pandoc @pandocArgs @metaTitle
}

Write-Host "Done. PDFs in $OutDir" -ForegroundColor Green
