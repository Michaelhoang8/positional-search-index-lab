"""Render exact saved retrieval results, original spans and positional diagrams."""

from datetime import datetime, timezone
import csv
import hashlib
import html
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results/published"
SCALE = ROOT / "results/scale"
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"


def load(name):
    return json.loads((RUN / name).read_text(encoding="utf-8"))


def posting_diagram(index):
    # Data values come directly from the committed index, not hand-drawn counts.
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="370" viewBox="0 0 1120 370" role="img" aria-labelledby="title desc">',
        '<title id="title">Recorded postings and Boolean candidates</title><desc id="desc">Cache and latency postings with exact positions, then their intersection and union</desc>',
        '<rect width="1120" height="370" fill="#fbf9f4"/>',
    ]
    for column, term in enumerate(["cache", "latency"]):
        x = 35 + column * 370
        parts.append(
            f'<text x="{x}" y="42" font-family="Georgia,serif" font-size="27" fill="#642d3e">{term}</text>'
        )
        for row, (doc_id, positions) in enumerate(index["postings"][term].items()):
            y = 85 + row * 46
            parts.append(
                f'<line x1="{x+10}" y1="{y-12}" x2="{x+32}" y2="{y-12}" stroke="#bfb5a5"/><text x="{x+42}" y="{y-7}" font-family="monospace" font-size="17" fill="#262522">{doc_id} → {html.escape(str(positions))}</text>'
            )
    intersection = sorted(
        set(index["postings"]["cache"]) & set(index["postings"]["latency"])
    )
    union = sorted(set(index["postings"]["cache"]) | set(index["postings"]["latency"]))
    parts += [
        '<line x1="735" y1="30" x2="735" y2="330" stroke="#d3c9bb"/>',
        '<text x="775" y="55" font-family="monospace" font-size="14" fill="#746b61">AND CANDIDATES</text>',
        f'<text x="775" y="90" font-family="monospace" font-size="18" fill="#642d3e">{", ".join(intersection)}</text>',
        '<text x="775" y="160" font-family="monospace" font-size="14" fill="#746b61">OR / BM25 CANDIDATES</text>',
        f'<text x="775" y="195" font-family="monospace" font-size="18" fill="#642d3e">{", ".join(union[:3])}</text>',
        f'<text x="775" y="227" font-family="monospace" font-size="18" fill="#642d3e">{", ".join(union[3:])}</text>',
        '<text x="35" y="344" font-family="monospace" font-size="13" fill="#746b61">Lists contain zero-based token positions. Original character spans are stored separately.</text>',
        "</svg>",
    ]
    (ASSETS / "postings.svg").write_text(
        "\n".join(parts) + "\n", encoding="utf-8", newline="\n"
    )


def build():
    ASSETS.mkdir(parents=True, exist_ok=True)
    corpus, index, results, environment = (
        load(name)
        for name in ["corpus.json", "index.json", "results.json", "environment.json"]
    )
    with (RUN / "summary.csv").open(encoding="utf-8", newline="") as stream:
        summaries = list(csv.DictReader(stream))
    with (RUN / "measurements.csv").open(encoding="utf-8", newline="") as stream:
        timings = list(csv.DictReader(stream))
    with (SCALE / "summary.csv").open(encoding="utf-8", newline="") as stream:
        scale_summary = list(csv.DictReader(stream))
    with (SCALE / "measurements.csv").open(encoding="utf-8", newline="") as stream:
        scale_timings = list(csv.DictReader(stream))
    scale_env = json.loads((SCALE / "environment.json").read_text(encoding="utf-8"))
    scale_build_ms = (
        statistics.median(
            int(row["elapsed_ns"]) for row in scale_timings if row["method"] == "build"
        )
        / 1_000_000
    )
    scale_rows = "".join(
        f"<tr><td>{html.escape(row['query'])}</td><td>{row['mode']}</td><td>{row['documents']}</td>"
        f"<td>{int(row['indexed_median_ns'])/1e6:.3f}</td><td>{int(row['scan_median_ns'])/1e6:.3f}</td></tr>"
        for row in scale_summary
    )
    scale_html = f"""<h3>256-document comparison</h3>
<p>A separate seeded corpus contains {scale_env['characters']:,} original code points and {scale_env['tokens']:,} tokens. All ten fixed queries reconcile exact document order, token positions and original spans against an independent scanner; BM25 scores agree within 10⁻¹² relative and absolute tolerance.</p>
<div class="table-scroll" role="region" aria-label="256-document query timings, scroll horizontally" tabindex="0"><table class="wide-table"><thead><tr><th>QUERY</th><th>MODE</th><th>HITS</th><th>INDEX MEDIAN / ms</th><th>SCAN MEDIAN / ms</th></tr></thead><tbody>{scale_rows}</tbody></table></div>
<p class="note">Seven warmed repetitions per method and query, with shuffled method order. The scanner tokenizes all original documents each call. The index uses retained postings and also builds highlights and score explanations. These methods do different internal work; this is a comparison with an unindexed scan, not a universal speedup claim.</p>
<div class="layout"><p>Seven separately timed index builds have a median of {scale_build_ms:.3f} ms. Build cost is excluded from query times and must be paid before reuse. The corpus has only 39 terms and synthetic frequency patterns; no relevance judgments are supplied.</p><aside class="aside">Corpus JSON: {scale_env['corpus_json_bytes']:,} bytes.<br>Index JSON: {scale_env['index_json_bytes']:,} bytes.<br>Compact index serialization includes original text and positions. File sizes exclude Python object overhead.</aside></div>
<div class="links"><a href="../results/scale/corpus.json">256-document corpus</a><a href="../results/scale/index.json">Full scale index</a><a href="../results/scale/results.json">Both methods’ matches</a><a href="../results/scale/measurements.csv">147 raw timings</a><a href="../results/scale/summary.csv">Medians and observed ranges</a><a href="../results/scale/environment.json">Measured environment</a></div>"""
    posting_diagram(index)
    explorer = {"corpus": corpus, "results": results, "summaries": summaries}
    (ASSETS / "explorer.json").write_text(
        json.dumps(explorer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    best = results[0]["hits"][0]
    explanations = "".join(
        f"<tr><td>{item['term']}</td><td>{item['tf']}</td><td>{item['df']}</td><td>{item['idf']:.6f}</td><td>{item['saturation']:.6f}</td><td>{item['contribution']:.6f}</td></tr>"
        for item in best["explanation"]
    )
    unicode_rows = []
    for query_id in [
        "unicode-street",
        "unicode-ligature",
        "unicode-composed",
        "unicode-sigma",
    ]:
        case = next(row for row in results if row["id"] == query_id)
        hit = case["hits"][0]
        text = index["documents"][hit["doc_id"]]["text"]
        for match in hit["matches"]:
            original = text[match["start"] : match["end"]]
            unicode_rows.append(
                f"<tr><td>{html.escape(original)}</td><td>{html.escape(case['query'])}</td><td>[{match['start']}, {match['end']})</td><td>{match['end']-match['start']}</td></tr>"
            )
    build_median = (
        statistics.median(
            int(row["elapsed_ns"]) for row in timings if row["operation"] == "build"
        )
        / 1000
    )
    report = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Positional search index</title>
<style>
:root{--paper:#fbf9f4;--ink:#262522;--wine:#642d3e;--muted:#746b61;--line:#d7cdbf;--mark:#f3df9f}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.65 system-ui,Segoe UI,sans-serif}header{border-top:7px solid var(--wine);border-bottom:1px solid var(--line);padding:22px 4vw;display:flex;justify-content:space-between;gap:25px;flex-wrap:wrap;font:12px ui-monospace,Consolas,monospace}nav{display:flex;gap:24px;flex-wrap:wrap}a{color:var(--wine);text-underline-offset:4px}nav a{text-decoration:none;color:var(--muted)}main{max-width:1220px;padding:0 40px;margin:auto}section{padding:68px 0;border-bottom:1px solid var(--line)}h1{font:clamp(48px,6.5vw,83px)/1.04 Georgia,serif;letter-spacing:-.035em;margin:20px 0 28px}h2{font:36px/1.2 Georgia,serif;letter-spacing:-.02em;margin:0 0 22px}h3{font:23px/1.3 Georgia,serif;margin:20px 0 12px}p{max-width:850px;margin:10px 0 21px}.lead{font-size:20px;max-width:820px}.kicker{font:12px ui-monospace,Consolas,monospace;color:var(--wine);letter-spacing:.08em}.facts{display:flex;gap:44px;flex-wrap:wrap;padding:25px 0;margin:25px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.facts b{display:block;font:35px Georgia,serif}.facts small{font-size:12px;color:var(--muted)}.layout{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(0,1fr);gap:55px}.aside{border-left:2px solid var(--line);padding-left:24px;color:var(--muted);font-size:14px}.querybar{border:1px solid #aa948a;background:#fffdf8;padding:18px 20px;margin:26px 0;display:grid;grid-template-columns:1fr auto;gap:15px;align-items:end}.querybar label{display:block;font-size:12px;color:var(--muted)}select{display:block;width:100%;min-width:0;max-width:100%;border:0;background:transparent;color:var(--wine);font:22px Georgia,serif;padding:9px 24px 4px 0}.querybar>div{min-width:0}.mode{font:12px ui-monospace,Consolas,monospace;border:1px solid var(--line);padding:6px 10px;color:var(--muted)}#query-summary{font-size:13px;color:var(--muted);margin-bottom:20px}.result{padding:25px 0;border-top:1px solid var(--line)}.result:first-child{border-top:0}.resulthead{display:flex;justify-content:space-between;align-items:baseline;gap:20px}.result h3{margin:0 0 12px;color:var(--wine)}.score{font:12px ui-monospace,Consolas,monospace;color:var(--muted);white-space:nowrap}.snippet{font:18px/1.8 Georgia,serif;white-space:pre-wrap;overflow-wrap:anywhere;max-width:960px}.docid{font:11px ui-monospace,Consolas,monospace;color:var(--muted);margin-bottom:9px}mark{background:var(--mark);color:inherit;padding:0 1px}details{margin-top:16px;font-size:13px;color:var(--muted)}summary{cursor:pointer;color:var(--wine)}details p{margin-top:12px;overflow-wrap:anywhere}.table-scroll,.diagram-scroll{max-width:100%;overflow-x:auto;overscroll-behavior-inline:contain}.table-scroll:focus-visible,.diagram-scroll:focus-visible{outline:2px solid var(--wine);outline-offset:4px}table{width:100%;border-collapse:collapse;font-size:14px;margin:22px 0}th,td{padding:12px 13px;text-align:left;border-bottom:1px solid var(--line)}th{font:11px ui-monospace,Consolas,monospace;color:var(--muted)}.wide-table{min-width:670px}img{width:100%;height:auto;display:block}.diagram-scroll img{min-width:950px}.note,figcaption{font-size:13px;color:var(--muted)}figure{margin:28px 0}figcaption{margin-top:12px}.tokenrow{display:flex;gap:12px;margin:25px 0;flex-wrap:wrap}.token{border:1px solid var(--line);padding:12px 22px;text-align:center;font:22px Georgia,serif;min-width:105px}.token small{display:block;font:11px/1.8 ui-monospace,Consolas,monospace;color:var(--muted)}.token.selected{background:var(--mark);border-color:#d4b564}.occurrences{display:grid;grid-template-columns:1fr 1fr;gap:30px}.formula{font:22px/1.8 Georgia,serif;color:var(--wine);overflow-wrap:anywhere;margin:22px 0}.links{display:flex;gap:22px;flex-wrap:wrap;font-size:14px;margin:25px 0}pre{padding:22px;background:#eee8de;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.8 ui-monospace,Consolas,monospace}code{font:13px ui-monospace,Consolas,monospace;overflow-wrap:anywhere}footer{max-width:1220px;padding:30px 40px 65px;margin:auto;font-size:12px;color:var(--muted)}@media(max-width:800px){main{padding:0 18px}section{padding:48px 0}.layout,.occurrences{grid-template-columns:1fr;gap:25px}.querybar{grid-template-columns:1fr}.mode{width:max-content}.resulthead{display:block}.score{display:block;margin-bottom:12px}.facts{gap:25px}h2{font-size:31px}footer{padding:28px 18px}.aside{padding-left:17px}}
</style></head><body><header><span>INFORMATION RETRIEVAL / POSITIONAL INDEX</span><nav aria-label="Report sections"><a href="#overview">Corpus</a><a href="#results">Results</a><a href="#positions">Positions</a><a href="#ranking">Ranking</a><a href="#unicode">Unicode</a><a href="#validation">Validation</a></nav></header><main>
<section id="overview"><div class="kicker">TERM / AND / OR / PHRASE / BM25</div><h1>Positional search index</h1><p class="lead">A source-built inverted index with exact normalized-token queries, overlapping phrase matches and per-term ranking explanations.</p><div class="facts"><div><b>12</b><small>owned synthetic documents</small></div><div><b>152</b><small>token occurrences</small></div><div><b>97</b><small>normalized terms</small></div><div><b>15</b><small>recorded queries</small></div></div><div class="layout"><p>The index stores token positions and half-open spans in the original text. Normalization can change a token's length; the highlighted characters always come from the original document.</p><aside class="aside">No web crawling, external corpus or human relevance labels. This report examines implementation behavior and evidence, not general search quality.</aside></div><div class="links"><a href="../results/published/corpus.json">Original corpus</a><a href="../results/published/index.json">Full index</a><a href="../results/published/postings.csv">Positional postings</a><a href="../README.md">Repository guide</a></div></section>
<section id="results"><h2>Recorded query results</h2><p>Select a saved Python query. The browser displays its actual result order, original-text highlights and explanations; it does not run a second search implementation.</p><div class="querybar"><div><label for="query-select">Recorded query</label><select id="query-select"></select></div><span class="mode" id="query-mode"></span></div><div id="query-summary" aria-live="polite"></div><div id="result-list"></div><noscript><p><a href="../results/published/results.json">Read the complete saved query results as JSON.</a></p></noscript></section>
<section id="positions"><h2>Posting lists and phrase positions</h2><p>AND intersects document sets; OR and BM25 use their union. Phrase queries first intersect the term document sets, then test adjacent token positions. These postings are drawn from the saved index.</p><figure><div class="diagram-scroll" role="region" aria-label="Postings diagram, scroll horizontally" tabindex="0"><img src="assets/postings.svg" alt="Exact cache and latency posting lists and their document intersection and union"></div></figure><h3>Overlapping phrase: “echo echo”</h3><div class="tokenrow"><div class="token selected"><small>POSITION 0</small>echo<small>CHARS [0,4)</small></div><div class="token selected"><small>POSITION 1</small>echo<small>CHARS [5,9)</small></div><div class="token selected"><small>POSITION 2</small>echo<small>CHARS [10,14)</small></div></div><div class="occurrences"><p>Occurrence one: positions <code>[0,1]</code>, original characters <code>[0,9)</code>.</p><p>Occurrence two: positions <code>[1,2]</code>, original characters <code>[5,14)</code>.</p></div><p>The result preserves both occurrences. Display highlights merge their overlap into <code>[0,14)</code>, so the shared middle word is marked once. Punctuation is a delimiter, so the phrase “search engine” also matches <code>search-engine</code> and <code>search, engine</code>.</p></section>
<section id="ranking"><div class="layout"><div><h2>BM25 score explanation</h2><p>For “cache latency,” the two identical short documents <code>d09</code> and <code>d10</code> receive exactly equal scores. Their document IDs break the tie. Repeating “cache” in the query produces the same ranking because query terms are deduplicated.</p><div class="formula">IDF(t) = ln[1 + (N − df + 0.5)/(df + 0.5)]<br>score = Σ IDF(t) · tf(k₁ + 1) /<br>[tf + k₁(1 − b + b · dl / avgdl)]</div></div><aside class="aside"><strong>Declared choices</strong><p>k₁ = 1.2; b = 0.75. N = 12 includes the empty document, and avgdl = 152 / 12. Terms missing from a document contribute zero.</p><p>The nonnegative IDF variant is documented explicitly. Scores are ranking weights, not relevance probabilities.</p></aside></div><h3>Top document d09: “cache latency”</h3><div class="table-scroll" role="region" aria-label="BM25 contributions, scroll horizontally" tabindex="0"><table class="wide-table"><thead><tr><th>TERM</th><th>TF</th><th>DF</th><th>IDF</th><th>TF SATURATION</th><th>CONTRIBUTION</th></tr></thead><tbody>@@EXPLANATIONS@@</tbody></table></div><p class="note">Full-precision score: @@BEST_SCORE@@. Displayed components are rounded; saved JSON retains every value.</p><p class="note">The positive IDF form also appears in <a href="https://lucene.apache.org/core/10_3_1/core/org/apache/lucene/search/similarities/BM25Similarity.html">Lucene's BM25 documentation</a>. This study does not reproduce Lucene's field statistics, encoded norms or complete scoring implementation. The probabilistic framework is described by <a href="https://doi.org/10.1561/1500000019">Robertson and Zaragoza</a>.</p></section>
<section id="unicode"><h2>Original spans after normalization</h2><p>Token boundaries are found in the original string before NFC normalization, case folding and a final NFC pass. Each match keeps the original code-point span, even if its normalized text expands or composes.</p><div class="table-scroll" role="region" aria-label="Unicode original spans, scroll horizontally" tabindex="0"><table class="wide-table"><thead><tr><th>ORIGINAL TEXT</th><th>QUERY</th><th>ORIGINAL SPAN</th><th>ORIGINAL CODE POINTS</th></tr></thead><tbody>@@UNICODE@@</tbody></table></div><div class="layout"><p><code>Straße</code> occupies six original code points but normalizes to seven in <code>strasse</code>. The single ligature <code>ﬃ</code> normalizes to three letters. A decomposed <code>Ångström</code> still highlights the combining marks in the original text.</p><aside class="aside">The browser slices <code>Array.from(originalText)</code>, not UTF-16 string offsets. This preserves Python code-point spans after non-BMP emoji. This tokenizer is not linguistic segmentation or a full Unicode word-boundary algorithm.</aside></div></section>
<section id="validation"><h2>Validation and reproduction</h2>@@SCALE@@<div class="layout"><div><h3>Independent oracles</h3><p>3,000 Boolean/phrase comparisons scan randomly generated ASCII documents with a separate regex oracle. Another 100 generated corpora compare BM25 against a separately rearranged formula across several k₁ and b settings.</p><p>Known Unicode vectors, repeated terms, overlapping phrases, punctuation, empty documents, exact-score ties, bounded JSON, original spans, source hashes and all stored evidence are checked.</p><h3>Actual measured calls</h3><p>Seven warmed index builds and seven complete calls for each of 15 queries: 112 timings. The recorded build median is @@BUILD_US@@ µs. File I/O and JSON serialization are outside the timer.</p></div><aside class="aside"><strong>Serialized size</strong><p>Original corpus JSON: 1,860 bytes. Index JSON: 26,708 bytes, including original text, token spans and postings. These are exact file sizes, not resident memory estimates or compressed-index results.</p><strong>Limits</strong><p>256 documents, 200,000 total code points, 4,096 tokens per document and 32 query tokens. No stemming, stopword removal, fuzzy matching, updates, persistence loading or production throughput claim.</p></aside></div><pre>python -m pip install -e .
python -m unittest discover -s tests -v
python -m searchlab query results/published/corpus.json --mode phrase --query "echo echo"
python scripts/run_study.py --out outputs/my-run
python scripts/run_scale.py --out outputs/my-scale</pre><div class="links"><a href="tokenization.md">Tokenization and offsets</a><a href="ranking.md">Ranking formula and limits</a><a href="methodology.md">Measurement method</a><a href="findings.md">Findings</a><a href="../results/published/manifest.json">Artifact hashes</a><a href="../results/published/measurements.csv">Raw timings</a></div><p class="note">AI-assisted implementation and documentation. All documents and queries are owned synthetic fixtures. No human relevance judgments or universal retrieval-quality claims are present.</p></section></main><footer>Positional search index lab · Original text, token positions and explainable ranking</footer>
<script id="retrieval-data" type="application/json">@@DATA@@</script><script>
const evidence=JSON.parse(document.getElementById('retrieval-data').textContent);const documents=new Map(evidence.corpus.map(d=>[d.id,d]));const select=document.getElementById('query-select'),list=document.getElementById('result-list');
evidence.results.forEach((result,i)=>{const option=document.createElement('option');option.value=i;option.textContent=result.query+' · '+result.mode;select.append(option)});
function markedText(text,spans){const fragment=document.createDocumentFragment(),chars=Array.from(text);let cursor=0;spans.forEach(([start,end])=>{fragment.append(document.createTextNode(chars.slice(cursor,start).join('')));const mark=document.createElement('mark');mark.textContent=chars.slice(start,end).join('');mark.dataset.start=start;mark.dataset.end=end;fragment.append(mark);cursor=end});fragment.append(document.createTextNode(chars.slice(cursor).join('')));return fragment}
function render(){const result=evidence.results[Number(select.value)],summary=evidence.summaries.find(s=>s.query_id===result.id);document.getElementById('query-mode').textContent=result.mode.toUpperCase();document.getElementById('query-summary').textContent=result.hits.length+' matched documents · '+result.candidate_ids.length+' posting candidates · median '+(Number(summary.median_ns)/1000).toFixed(2)+' µs across seven recorded calls';list.replaceChildren();if(!result.hits.length){const empty=document.createElement('p');empty.textContent='No matched documents in the saved result.';list.append(empty)}result.hits.forEach(hit=>{const doc=documents.get(hit.doc_id),article=document.createElement('article');article.className='result';article.dataset.docId=hit.doc_id;const id=document.createElement('div');id.className='docid';id.textContent=hit.doc_id;article.append(id);const head=document.createElement('div');head.className='resulthead';const title=document.createElement('h3');title.textContent=doc.title;head.append(title);const score=document.createElement('span');score.className='score';score.textContent=hit.score===null?hit.matches.length+' match occurrences':'BM25 '+hit.score.toFixed(6);head.append(score);article.append(head);const snippet=document.createElement('div');snippet.className='snippet';snippet.append(markedText(doc.text,hit.highlights));article.append(snippet);const detail=document.createElement('details');const label=document.createElement('summary');label.textContent='Matching positions'+(hit.explanation.length?' and score contributions':'');detail.append(label);const positions=document.createElement('p');positions.textContent=hit.matches.map(m=>'tokens ['+m.positions.join(',')+'] → original ['+m.start+','+m.end+')').join(' · ');detail.append(positions);hit.explanation.forEach(term=>{const line=document.createElement('p');line.textContent=term.term+': tf='+term.tf+', df='+term.df+', IDF='+term.idf.toFixed(6)+', length factor='+term.length_normalization.toFixed(6)+', contribution='+term.contribution.toFixed(6);detail.append(line)});article.append(detail);list.append(article)})}
select.addEventListener('change',render);render();
</script></body></html>"""
    replacements = {
        "EXPLANATIONS": explanations,
        "BEST_SCORE": str(best["score"]),
        "UNICODE": "".join(unicode_rows),
        "BUILD_US": f"{build_median:.2f}",
        "SCALE": scale_html,
        "DATA": json.dumps(explorer, ensure_ascii=False).replace("</", "<\\/"),
    }
    for key, value in replacements.items():
        report = report.replace("@@" + key + "@@", value)
    (DOCS / "report.html").write_text(report, encoding="utf-8", newline="\n")
    outputs = [DOCS / "report.html", ASSETS / "postings.svg", ASSETS / "explorer.json"]
    metadata = {
        "rendered_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256_lf": hashlib.sha256(
            Path(__file__).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        ).hexdigest(),
        "inputs": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(list(RUN.iterdir()) + list(SCALE.iterdir()))
            if p.is_file()
        },
        "outputs": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in outputs
        },
        "rendering": "Standard-library HTML/SVG from preserved results; original strings highlighted using code-point arrays",
    }
    (ASSETS / "provenance.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(DOCS / "report.html")


if __name__ == "__main__":
    build()
