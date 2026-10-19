# Builds rapport.docx and rapport.pdf from rapport.html with Microsoft Word.
# Run from this folder:  powershell -ExecutionPolicy Bypass -File build.ps1
# After the first build, edit rapport.docx directly in Word and export the PDF from Word.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = [string](Join-Path $here 'rapport.html')  # plain strings: Word's COM calls can hang on wrapped ones
$docx = [string](Join-Path $here 'rapport.docx')
$pdf = [string](Join-Path $here 'rapport.pdf')

# Start from clean outputs.
Remove-Item $docx, $pdf -ErrorAction SilentlyContinue

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0  # never wait on a hidden dialog
$doc = $word.Documents.Open($source, $false, $true)
$doc.ActiveWindow.View.Type = 3  # print layout

# Embed the pictures in the document instead of linking to the image files.
for ($i = 1; $i -le $doc.InlineShapes.Count; $i++) {
    $shape = $doc.InlineShapes.Item($i)
    if ($shape.Type -eq 4) {  # linked picture
        $shape.LinkFormat.SavePictureWithDocument = $true
        $shape.LinkFormat.BreakLink()
    }
}

# Word's HTML import adds paragraph spacing inside table cells; remove it and use small cell padding.
for ($i = 1; $i -le $doc.Tables.Count; $i++) {
    $table = $doc.Tables.Item($i)
    $table.Range.ParagraphFormat.SpaceBefore = 0
    $table.Range.ParagraphFormat.SpaceAfter = 0
    $table.TopPadding = 2; $table.BottomPadding = 2; $table.LeftPadding = 4; $table.RightPadding = 4
}

# Replace the [TOC] paragraph with a real, updatable table of contents.
$range = $doc.Content
if ($range.Find.Execute('[TOC]')) {
    $range.Text = ''
    $doc.TablesOfContents.Add($range, $true, 1, 2) | Out-Null
}

# Page numbers in the footer, centred.
$doc.Sections.Item(1).Footers.Item(1).PageNumbers.Add(1, $true) | Out-Null

$doc.SaveAs2($docx, 16)  # .docx
$doc.ExportAsFixedFormat($pdf, 17)  # PDF
$doc.Close($false)
$word.Quit()
Write-Output "Built $docx and $pdf"
