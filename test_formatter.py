import bot_bridge as b

samples = [
    "**bold** dan *italic* lalu __bold2__ dan _italic2_",
    "# Header 1\n## Header 2\nIni **penting** banget",
    "Kode inline `print(123)` dan link [Google](https://google.com)",
    "Contoh code:\n```python\ndef hitung_ndvi(nir, red):\n    return (nir - red) / (nir + red + 1e-6)\n```\nLalu bullet:\n- poin satu\n- poin dua\n> ini quote\n---\nSelesai",
    "Raw **banyak** **bintang** tanpa close *",
    "\x1b[31mMerah ANSI\x1b[0m dan **bold**",
    "# Ringkasan\n**File dibuat:** `src/ndvi.py`\n**Status:** ✅ Berhasil\n\nLangkah:\n1. Buat fungsi\n2. Test `pytest`\n```bash\npytest -v\n```\nLihat [docs](https://example.com) untuk detail.",
]

for i, s in enumerate(samples):
    html = b.markdown_to_telegram_html(s)
    open(f"out_{i}.html","w",encoding="utf-8").write(html)
    print(f"sample {i} OK len={len(html)}")
    # also check contains raw **
    if "**" in html:
        print(f"  WARN sample {i} masih ada **")
    print(html[:1000].replace("\n","\\n")[:500])
    print("---")

# test chunking panjang
long_body = "# Judul\n" + "Lorem ipsum **bold** " * 500 + "\n\n```python\n" + "x=1\n"*800 + "```\nAkhir dengan *italic* dan [link](https://example.com)"
chunks = b.build_telegram_chunks(long_body, "prompt test yang panjang banget buat header: buatkan file hello.py yang print halo dunia dengan fitur tambahan", limit=4000)
print(f"\nchunk test: total={len(chunks)} lens={[len(c) for c in chunks]}")
for idx, c in enumerate(chunks):
    open(f"chunk_{idx}.html","w",encoding="utf-8").write(c)
    # verify no chunk >4000
    assert len(c) <= 4000, f"chunk {idx} too long {len(c)}"
    # verify pre balance approx
    if c.count("<pre>") != c.count("</pre>"):
        # allow language variant
        if c.count("<pre>") != c.count("</pre>") and c.count("<pre><code") != c.count("</code></pre>"):
            print(f"  WARN chunk {idx} pre unbalanced {c.count('<pre>')} vs {c.count('</pre>')}")

print("chunk test OK")

# test build with short
short = "**Selesai**\nFile `hello.py` dibuat."
chunks2 = b.build_telegram_chunks(short, "buatkan hello.py", limit=4000)
print(f"short chunks={len(chunks2)}")
print(chunks2[0][:1000])
