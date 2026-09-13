# Fiverr Gig Copy — Excel Cleaner Pro

> Source: `docs/fiverr_gig_copy.md`. Read-only reference; regenerate from the
> demo portfolio + product code before publishing a versioned gig.

---

## SEO Titles (English)

1. **I will clean, fix and structure your Excel CSV data with an audit certificate**
2. **I will clean Excel spreadsheets: duplicates, dates, money, formatting**
3. **I will sanitize messy business data in Excel or CSV with a cleaning report**

Corto, con búsqueda de intención:
- "clean excel spreadsheet"
- "fix messy excel data"
- "excel data cleaning service"
- "clean csv data"
- "deduplicate excel"

---

## SEO Titles (Español)

1. **Limpiaré y estructuraré tus archivos Excel o CSV con reporte de auditoría**
2. **Limpiaré hojas de cálculo: duplicados, fechas, monetarios, formato**
3. **Sanitizaré datos sucios de negocios en Excel o CSV con certificado de limpieza**

---

## Gig Description — ENGLISH

**Don't deliver a spreadsheet that looks clean but breaks your formulas, your
invoices, or your client report. Send me your file and I'll return it clean,
structured, and fully documented.**

I fix the kind of Excel and CSV files that come from sales teams, accounting,
marketplaces, and legacy systems: uneven spacing, dates that don't match,
numbers stored as text, money formatted in two different ways, hidden blanks,
exact duplicates, and duplicate rows that only appear once you clean the data.

---

### What makes my work different

Most people clean Excel visually. I clean it with a **Zero-Trust cleanup engine**
running locally on your file, and I document every change.

Every job ends with a **cleaning report / audit certificate** that tells you:

- how many rows you started with and how many you ended with
- which columns changed
- which actions were applied
- which rows were removed (and why)
- which values became empty and why
- the validation result, with errors listed if anything couldn't be safely fixed

That means you're not just getting a file. You're getting proof of what changed.
If a client, accountant, or auditor asks later, you have the certificate.

---

### I clean all of this, precisely

**Text issues**
- trailing/leading spaces, hidden spaces, repeated blanks
- inconsistent capitalization where appropriate
- "N/A", "null", "-", "None" and other placeholder text converted to real blanks
- custom text patterns you ask me to replace

**Duplicates**
- exact duplicates
- duplicates that only show up after trimming spaces
- duplicates by a specific key — Email, DNI, SKU, phone, customer ID — so you
  keep one real record per identity

**Dates**
- mixed date formats (DD/MM/YYYY, MM/DD/YYYY, ISO YYYY-MM-DD)
- I detect format, apply date-first or month-first as appropriate, and
  standardize to a clean ISO-style date
- garbage that really isn't a date gets marked and converted to a clean blank
  with a warning — not silently dropped without a trace

**Money and numbers**
- US format: `1,250.50`
- EU/LatAm format: `1.250,50`
- with symbols: `$1,250.50`, `US$ 900,00`, `€ 1.200`
- negative/contable format in parentheses: `(450.00)` → `-450.00`
- percentage text if applicable
- numbers-as-text converted back to real numbers when that's the right fix
- I normalize by locale so money means the same value after cleaning, not a
  different number

**Structure**
- empty rows and empty columns removed cleanly
- column splitting (for example, full name → name + last name)
- column combining (for example, code + phone, or address parts)
- multi-sheet XLSX handled sheet by sheet

**Large jobs**
- folders of files (batch mode) when you have many spreadsheets to process
- a failed file never stops the whole batch; it's quarantined with a readable
  reason and reported in the master summary

---

### What you get back

One cleaned file, plus the audit report that accompanies it. Depending on the
package, the audit certificate is delivered as:

- an extra sheet inside the Excel file called `_Reporte_Auditoria`, or
- a plain-text certificate alongside the file
- (JSON certificate also available on request for automation/integration)

The report is human-readable and client-ready. It explains the work in the
language you prefer — I can deliver it in Spanish or English.

---

### How I work — safe, not risky

For client files, I don't guess. If a column needs to be changed, I plan the
change. If a value needs to be treated as missing, I mark it. If something
looks risky or ambiguous, I flag it. The Zero-Trust engine is designed around
one idea: if a change could alter important information, the job warns you or
stops rather than silently shipping a wrong number.

I keep your original file unchanged. You don't receive a file that replaced the
original — you receive a cleaned copy and a record of what was fixed.

---

### Good candidates for this gig

- sales/customer lists exported from a CRM or marketplace
- invoices, quotes, expense logs
- lead lists, contact lists, email lists
- inventory, SKU lists, product catalogs
- financial/accounting exports with mixed formats
- any Excel or CSV that "looks messy" and needs to feed another system

---

### What I need from you

- The file (or folder of files) to clean
- What the data represents (customers, invoices, products, etc.)
- The columns that identify a unique row, if deduplication matters
- Preferred date format, if you have one
- Anything that should NOT be touched

If you're not sure, just send the file and tell me what you want to do with it
next. I'll tell you what I can fix and what I'd recommend leaving alone.

---

### Packages

See the Packages section for price and scope. Custom offers are welcome for
larger folders, recurring cleanups, or datasets with special handling rules.

**Ready when you are — send the file and get a clean result and a certificate.**

---

### Section: Por qué confiar (trust section, English)

- Local, focused tool. Your file is processed locally on my machine. No cloud
  uploads for the cleanup step. The cleanup idea is yours and mine to handle.
- Deterministic cleanup. The same inputs, the same approved actions, the same
  outputs — every time.
- Traceable. Every job produces a certificate showing what changed.
- Safe by design. A validation step blocks the output if something was changed
  in a way that wasn't planned. The clean file only leaves when it passes.

---

## Packages (suggested)

Use real numbers after testing with your first clients; these are starting points
sized around rows and files, with the audit certificate in every package.

### BASIC — Quick fix + certificate

**Best for:** one small/medium messy file, up to ~250 rows.

Includes:
- Receive and analyze one Excel or CSV file
- Clean: spaces, obvious duplicates, N/A/null conversion, simple date/number
  normalization
- One round of cleaning with the audit certificate (PDF/text report)
- Delivery in Excel or CSV as requested

**Price suggestion:** USD 5–8

**Delivery:** 1 day

---

### STANDARD — Real cleanup + deduplicated + certificate

**Best for:** a single complex file up to ~2,000 rows, or a small batch of
related files.

Includes:
- Everything in Basic, plus:
- Duplicate removal by a chosen key (Email/DNI/SKU/phone) — tell me which
  column identifies a unique record
- Better date normalization (mixed formats, day-first or month-first as needed)
- Better number/money normalization (US and EU formats, currency symbols,
  parentheses negatives)
- Column split or merge if it helps the structure
- Two rounds of review with me before final delivery
- Audit certificate in Excel (extra sheet) and as a text file
- Language of certificate: Spanish or English, your choice

**Price suggestion:** USD 15–25

**Delivery:** 2 days

---

### PREMIUM — Folder cleanup + master summary + certificate

**Best for:** a folder of files (sales exports, daily logs, supplier lists, etc.),
or one large dataset with many columns.

Includes:
- Everything in Standard, plus:
- Batch processing of a whole folder of files
- Per-file cleanup report
- Master summary: how many files processed, how many succeeded, how many were
  quarantined, totals of rows cleaned
- Quarantine handling: a file that can't be cleaned goes to a separate folder
  with a readable reason, never silently dropped
- Extra QA pass on the final files
- Certificate per file + master summary
- Certificate in your preferred language (Spanish or English)

**Price suggestion:** USD 40–80, or custom for very large batches

**Delivery:** 3–5 days, depending on folder size

---

## FAQ

**1. Do I need to understand Excel formulas or code?**
No. Send the file and tell me what the data is for. I'll ask a couple of
practical questions if anything is ambiguous, and I'll explain what I changed.

**2. Will my original file be overwritten?**
No. I work on a copy. You get back a cleaned file and, in every package, an
audit report showing what changed. Your original stays as you sent it.

**3. I have a folder with many Excel files. Can you clean them all at once?**
Yes. The Standard package can cover a small batch; the Premium package is
designed for folder/workflow cleaning with a master summary. Tell me how many
files and roughly how big each one is.

**4. What if some rows are wrong and I'm not sure whether to delete them?**
Tell me the rule. For example: "keep the first row for each Email", "these
columns identify a customer", or "don't delete anything in column X". If it's
not clear, I'll flag it instead of guessing and deleting real data.

**5. What exactly do I receive?**
The cleaned Excel/CSV file, plus an audit certificate explaining what was fixed,
what was removed, and what was validated. The certificate can be an extra sheet
in the file, a text file, or both — you decide. I can deliver it in Spanish or
English.

**6. Can you match a specific date format or currency format?**
Yes. Tell me the target format (for example "keep DD/MM/YYYY" or "everything in
USD format with two decimals"). If the source is ambiguous, I'll tell you what
I assumed before I deliver, not after.

**7. What if my file has personal data? Is it safe?**
The cleanup itself is local and private. Since the work is done on my machine and
the file isn't uploaded for the cleanup step, you're in control of your data.
If the file is especially sensitive, tell me and I'll confirm the handling.

**8. What if you can't fix something?**
You'll see it in the audit report. The whole point of the certificate is to show
not only what was fixed, but also what couldn't be safely fixed — so there are no
surprises later.

---

## FAQ — Español

**1. ¿Necesito saber de Excel o programación?**
No. Enviá el archivo y decime para qué sirven los datos. Si algo es ambiguo te
hago un par de preguntas prácticas y te explico qué cambié.

**2. ¿Se reemplaza mi archivo original?**
No. Trabajo sobre una copia. Recibí un archivo limpio y, en todos los paquetes,
un reporte de auditoría que dice qué se cambió. El original se queda como lo
enviaste.

**3. Tengo una carpeta con muchos Excel. ¿Puede limpiarlos todos?**
Sí. El paquete Standard puede cubrir un lote pequeño; el Premium está diseñado
para limpieza por carpeta con resumen maestro. Decime cuántos archivos y
cómo de grandes son.

**4. Hay filas raras y no sé si borrarlas.**
Decime la regla. Por ejemplo: "guardá la primera fila por Email", "estas
columnas identifican un cliente", "no borres nada de la columna X". Si no está
claro, te lo paso a flaggeo en lugar de borrar datos reales adivinando.

**5. ¿Qué recibo exactamente?**
El archivo Excel/CSV limpio, más un certificado de auditoría que dice qué se
arregló, qué se eliminó y qué se validó. El certificado puede ser una pestaña
extra en el archivo, un archivo de texto, o ambos. Lo puedo entregar en español
o en inglés.

**6. ¿Puede respetar un formato de fecha o moneda concreto?**
Sí. Decime el formato objetivo (por ejemplo "dejar DD/MM/AAAA" o "todo en
formato USD con dos decimales"). Si el original es ambiguo, te digo qué asumo
antes de entregar, no después.

**7. ¿Y si el archivo tiene datos personales? ¿Es seguro?**
La limpieza es local y privada. Como el trabajo se hace en mi máquina y el
archivo no se sube para la etapa de limpieza, tú controlás tus datos. Si es
muy sensible, decírmelo y confirmamos cómo lo manejamos.

**8. ¿Y si no puede arreglar algo?**
Sale en el reporte de auditoría. De hecho, de ahí viene la utilidad del
certificado: muestra no solo lo arreglado, sino también lo que no pudo
arreglarse de forma segura, sin sorpresas después.

---

## Notes for the seller (not part of the gig text)

- Replace price/delivery numbers with real ones after the first few orders.
- The audit certificate is the differentiator; lead with it in the description
  and the FAQ, not in the packages only.
- Use the demo portfolio (`demo_portfolio/`) for before/after screenshots:
  `1_original_sucio.xlsx` vs `2_resultado_limpio.xlsx`, plus one of the
  audit reports.
- If a client wants English and you deliver Spanish by habit, the certificate
  should still be correct; the request for "English certificate" is the prompt
  to switch `language="en"`.
- For recurring clients, the same audit format makes follow-up work fast to
  explain and fast to repeat.
