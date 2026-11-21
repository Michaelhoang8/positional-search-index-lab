"""Optional browser QA of every saved query, code-point highlight and viewport."""

import argparse
import importlib.metadata
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def check(out, channel):
    out.mkdir(parents=True, exist_ok=True)
    evidence = json.loads(
        (ROOT / "docs/assets/explorer.json").read_text(encoding="utf-8")
    )
    documents = {row["id"]: row for row in evidence["corpus"]}
    results = []
    with sync_playwright() as playwright:
        options = {"headless": True}
        if channel:
            options["channel"] = channel
        browser = playwright.chromium.launch(**options)
        for width in (390, 1440):
            page = browser.new_page(viewport={"width": width, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto((ROOT / "docs/report.html").as_uri(), wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            assert page.locator("#query-select option").count() == len(
                evidence["results"]
            )
            for number, result in enumerate(evidence["results"]):
                page.locator("#query-select").select_option(str(number))
                cards = page.locator(".result")
                assert cards.count() == len(result["hits"])
                for index, hit in enumerate(result["hits"]):
                    card = cards.nth(index)
                    original = documents[hit["doc_id"]]["text"]
                    assert card.get_attribute("data-doc-id") == hit["doc_id"]
                    assert card.locator(".snippet").text_content() == original
                    marks = card.locator("mark")
                    assert marks.count() == len(hit["highlights"])
                    for mark_index, (start, end) in enumerate(hit["highlights"]):
                        mark = marks.nth(mark_index)
                        assert mark.text_content() == original[start:end]
                        assert int(mark.get_attribute("data-start")) == start
                        assert int(mark.get_attribute("data-end")) == end
                assert page.evaluate("document.documentElement.scrollWidth") <= width
            page.locator("#query-select").select_option("0")
            detail = page.locator("details").first
            detail.locator("summary").focus()
            page.keyboard.press("Enter")
            assert detail.get_attribute("open") is not None
            page.keyboard.press("Enter")
            assert detail.get_attribute("open") is None
            scroll_checks = 0
            for region in page.locator(".table-scroll,.diagram-scroll").all():
                assert region.get_attribute("role") == "region"
                assert region.get_attribute("aria-label")
                assert region.get_attribute("tabindex") == "0"
                if region.evaluate("e=>e.scrollWidth>e.clientWidth"):
                    region.focus()
                    page.keyboard.press("ArrowRight")
                    page.wait_for_timeout(200)
                    assert region.evaluate("e=>e.scrollLeft") > 0
                    scroll_checks += 1
            for href in page.locator("a[href]").evaluate_all(
                "links=>links.map(a=>a.getAttribute('href'))"
            ):
                if not urlparse(href).scheme and not href.startswith("#"):
                    assert (
                        (ROOT / "docs" / unquote(href.split("#")[0])).resolve().exists()
                    ), href
            assert page.locator("img").evaluate_all(
                "images=>images.every(i=>i.complete&&i.naturalWidth>0)"
            )
            assert not errors, errors
            page.evaluate("scrollTo(0,0)")
            page.screenshot(path=str(out / f"overview-{width}.png"))
            page.locator("#results").scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"results-{width}.png"))
            results.append(
                {
                    "width": width,
                    "queries_checked": len(evidence["results"]),
                    "keyboard_scroll_regions": scroll_checks,
                    "page_errors": errors,
                    "horizontal_page_overflow": False,
                }
            )
            page.close()
        browser.close()
    (out / "checks.json").write_text(
        json.dumps(
            {"playwright": importlib.metadata.version("playwright"), "checks": results},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/browser-review")
    parser.add_argument(
        "--channel", default=None, help="Use msedge for an installed Edge browser"
    )
    args = parser.parse_args()
    check(args.out, args.channel)
