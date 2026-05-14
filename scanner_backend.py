from __future__ import annotations

import re
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, make_response, request

try:
    from flask_cors import CORS
except ImportError:  # pragma: no cover - manual CORS fallback is below
    CORS = None


APP_NAME = "DS Digital Designs Website Opportunity Scanner"
USER_AGENT = "DSDigitalDesigns-WebsiteOpportunityScanner/1.0"
REQUEST_TIMEOUT = 12
LINK_CHECK_LIMIT = 15
MAX_TOOL_OUTPUT = 4500

ALLOWED_ORIGINS = {
    "http://127.0.0.1:8080",
    "http://localhost:8080",
    "http://100.118.56.21:8080",
    "https://dsdigitaldesigns.org",
    "https://www.dsdigitaldesigns.org",
    "https://dylanmsprouse3455.github.io",
}

TOOL_NAMES = [
    "whatweb",
    "nmap",
    "nikto",
    "sslscan",
    "dig",
    "whois",
    "curl",
    "wafw00f",
    "nuclei",
    "subfinder",
    "amass",
    "testssl.sh",
]

ADVANCED_TOOL_COMMANDS = {
    "whatweb": lambda url, host: (["whatweb", "--no-errors", "--color=never", url], 20),
    "curl": lambda url, host: (["curl", "-I", "-L", "--max-time", "10", url], 12),
    "dig_a": lambda url, host: (["dig", host, "A"], 8),
    "dig_mx": lambda url, host: (["dig", host, "MX"], 8),
    "dig_txt": lambda url, host: (["dig", host, "TXT"], 8),
    "whois": lambda url, host: (["whois", host], 12),
    "sslscan": lambda url, host: (["sslscan", "--no-colour", host], 25),
    "wafw00f": lambda url, host: (["wafw00f", url], 20),
    "nmap": lambda url, host: (["nmap", "-Pn", "-T2", "--top-ports", "25", "--open", host], 40),
    "nikto": lambda url, host: (["nikto", "-h", url, "-nointeractive"], 45),
}

app = Flask(__name__)
if CORS:
    CORS(app, origins=list(ALLOWED_ORIGINS))


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


@app.route("/api/website-opportunity-scan", methods=["OPTIONS"])
def website_opportunity_options():
    return make_response("", 204)


@app.get("/health")
def health():
    return jsonify({"ok": True, "name": APP_NAME})


@app.post("/api/website-opportunity-scan")
def website_opportunity_scan():
    payload = request.get_json(silent=True) or {}
    raw_url = str(payload.get("url", "")).strip()
    requested_mode = str(payload.get("mode", "standard")).strip().lower() or "standard"
    authorized = payload.get("authorized") is True

    if requested_mode not in {"standard", "advanced"}:
        return jsonify({"ok": False, "error": "Scan mode must be standard or advanced."}), 400

    try:
        normalized_url, hostname = normalize_url_and_hostname(raw_url)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    tools_available = detect_tools()

    if requested_mode == "advanced" and not authorized:
        return jsonify(
            {
                "ok": False,
                "mode": "live",
                "scan_mode": "advanced",
                "authorized_advanced": False,
                "error": "Advanced scans require confirmation that you own this domain or have permission to test it.",
                "tools_available": tools_available,
                "tool_results": {},
            }
        ), 403

    try:
        result = run_standard_scan(raw_url, normalized_url, hostname)
    except Exception as exc:  # Keep API stable if a site has unusual behavior.
        return jsonify({"ok": False, "error": f"Scanner could not complete the standard checks: {exc}"}), 502

    result["scan_mode"] = requested_mode
    result["authorized_advanced"] = requested_mode == "advanced" and authorized
    result["tools_available"] = tools_available
    result["tool_results"] = {}
    result["tools_used_standard"] = []
    result["tools_used_advanced"] = []

    if requested_mode == "advanced":
        tool_results = run_advanced_tools(normalized_url, hostname, tools_available)
        result["tool_results"] = tool_results
        result["tools_used_advanced"] = [name for name, data in tool_results.items() if data.get("ran")]
        apply_advanced_findings(result, tool_results)

    return jsonify(result)


def normalize_url_and_hostname(raw_url: str) -> tuple[str, str]:
    if not raw_url:
        raise ValueError("Missing URL.")

    candidate = raw_url.strip()
    if not re.match(r"^https?://", candidate, flags=re.I):
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname or not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,63}", hostname):
        raise ValueError("Enter a valid website domain or URL.")

    netloc = hostname
    if parsed.port:
        netloc = f"{hostname}:{parsed.port}"

    path = parsed.path or "/"
    normalized = parsed._replace(scheme=parsed.scheme.lower(), netloc=netloc, path=path, params="", fragment="").geturl()
    return normalized, hostname


def detect_tools() -> dict[str, bool]:
    return {tool: shutil.which(tool) is not None for tool in TOOL_NAMES}


def safe_run_tool(command: list[str], timeout: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
        output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part)
        return {
            "ran": True,
            "returncode": completed.returncode,
            "timed_out": False,
            "raw_excerpt": trim_output(output),
            "error": "" if completed.returncode == 0 else trim_output(completed.stderr.strip() or completed.stdout.strip()),
        }
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(part for part in [decode_tool_output(exc.stdout), decode_tool_output(exc.stderr)] if part)
        return {
            "ran": True,
            "returncode": None,
            "timed_out": True,
            "raw_excerpt": trim_output(output),
            "error": f"Tool timed out after {timeout} seconds.",
        }
    except OSError as exc:
        return {"ran": False, "returncode": None, "timed_out": False, "raw_excerpt": "", "error": str(exc)}


def trim_output(value: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n...[trimmed]"


def decode_tool_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def fetch_url(url: str, method: str = "GET", timeout: int = REQUEST_TIMEOUT) -> requests.Response:
    return requests.request(
        method,
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        timeout=timeout,
        allow_redirects=True,
    )


def run_standard_scan(input_url: str, normalized_url: str, hostname: str) -> dict[str, Any]:
    started = time.perf_counter()
    response = fetch_url(normalized_url)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    final_url = response.url
    final_parsed = urlparse(final_url)
    base_url = f"{final_parsed.scheme}://{final_parsed.netloc}"
    html = response.text or ""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    meta_description = get_meta_content(soup, "description")
    h1_tags = [clean_text(tag.get_text(" ", strip=True)) for tag in soup.find_all("h1")]
    h2_count = len(soup.find_all("h2"))
    words = re.findall(r"\b[\w'-]+\b", visible_text)
    links = collect_links(soup, final_url, hostname)
    security_headers = analyze_security_headers(response.headers)
    contact = analyze_contact_signals(soup, visible_text, links)
    seo = analyze_seo_signals(soup, title, meta_description, h1_tags, base_url)
    action = analyze_action_signals(soup, visible_text)
    mobile = analyze_mobile_signals(soup, html)
    technical = analyze_technical_signals(soup, response, links, final_url)
    broken_samples = check_internal_links(links["internal"][:LINK_CHECK_LIMIT])
    dns_checks = resolve_dns(hostname)

    raw_checks = {
        "status_code": response.status_code,
        "redirect_chain": [item.url for item in response.history] + [final_url],
        "response_time_ms": elapsed_ms,
        "title": title,
        "meta_description": meta_description,
        "h1_count": len(h1_tags),
        "h1_first": h1_tags[0] if h1_tags else "",
        "h2_count": h2_count,
        "word_count": len(words),
        "https_active": final_parsed.scheme == "https",
        "security_headers": security_headers,
        "contact": contact,
        "seo": seo,
        "customer_action": action,
        "mobile": mobile,
        "technical": technical,
        "dns": dns_checks,
        "broken_link_sample": broken_samples,
    }

    scores = score_checks(raw_checks)
    issues = build_issues(raw_checks, scores)
    fastest_win = choose_fastest_win(issues, raw_checks)
    overall = round(sum(scores.values()) / len(scores))
    scores["overall_score"] = overall

    return {
        "ok": True,
        "mode": "live",
        "scan_mode": "standard",
        "authorized_advanced": False,
        "input_url": input_url,
        "normalized_url": normalized_url,
        "final_url": final_url,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "scores": scores,
        "top_issues": issues[:3],
        "fastest_win": fastest_win,
        "raw_checks": raw_checks,
        "summary": build_summary(scores, raw_checks),
    }


def clean_text(value: str) -> str:
    return unescape(re.sub(r"\s+", " ", value or "").strip())


def get_meta_content(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)})
    return clean_text(tag.get("content", "")) if tag else ""


def collect_links(soup: BeautifulSoup, final_url: str, hostname: str) -> dict[str, list[str]]:
    internal: list[str] = []
    external: list[str] = []
    seen = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(final_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        clean = parsed._replace(fragment="").geturl()
        if clean in seen:
            continue
        seen.add(clean)
        if (parsed.hostname or "").lower().rstrip(".") == hostname:
            internal.append(clean)
        else:
            external.append(clean)
    return {"internal": internal, "external": external}


def analyze_security_headers(headers: requests.structures.CaseInsensitiveDict) -> dict[str, bool]:
    names = [
        "Content-Security-Policy",
        "Strict-Transport-Security",
        "X-Frame-Options",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",
    ]
    return {name: bool(headers.get(name)) for name in names}


def analyze_contact_signals(soup: BeautifulSoup, text: str, links: dict[str, list[str]]) -> dict[str, Any]:
    all_hrefs = [tag.get("href", "") for tag in soup.find_all("a", href=True)]
    lower_text = text.lower()
    phone_pattern = re.compile(r"(?:\+?1[\s.-]?)?(?:\(?[2-9]\d{2}\)?[\s.-]?)\d{3}[\s.-]?\d{4}")
    email_pattern = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
    return {
        "contact_page_link_found": any("contact" in urlparse(url).path.lower() for url in links["internal"]),
        "visible_phone_found": bool(phone_pattern.search(text)),
        "visible_email_found": bool(email_pattern.search(text)),
        "tel_link_found": any(href.lower().startswith("tel:") for href in all_hrefs),
        "email_link_found": any(href.lower().startswith("mailto:") for href in all_hrefs),
        "privacy_policy_link_found": "privacy policy" in lower_text or any("privacy" in urlparse(url).path.lower() for url in links["internal"]),
        "footer_found": bool(soup.find("footer")),
    }


def analyze_seo_signals(soup: BeautifulSoup, title: str, meta_description: str, h1_tags: list[str], base_url: str) -> dict[str, Any]:
    og_tags = soup.find_all("meta", property=re.compile(r"^og:", re.I))
    canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
    return {
        "title_present": bool(title),
        "title_length": len(title),
        "meta_description_present": bool(meta_description),
        "meta_description_length": len(meta_description),
        "h1_present": bool(h1_tags),
        "canonical_tag_found": bool(canonical),
        "open_graph_tags_found": len(og_tags),
        "sitemap_found": quick_url_exists(urljoin(base_url, "/sitemap.xml")),
        "robots_found": quick_url_exists(urljoin(base_url, "/robots.txt")),
    }


def analyze_action_signals(soup: BeautifulSoup, text: str) -> dict[str, Any]:
    lower = text.lower()
    cta_keywords = ["call", "contact", "book", "schedule", "quote", "request", "appointment", "get started"]
    forms = soup.find_all("form")
    return {
        "cta_keywords_found": [word for word in cta_keywords if word in lower],
        "contact_form_clues_found": bool(forms) or any(word in lower for word in ["submit", "message", "your email", "your phone"]),
        "phone_link_found": any((tag.get("href") or "").lower().startswith("tel:") for tag in soup.find_all("a", href=True)),
    }


def analyze_mobile_signals(soup: BeautifulSoup, html: str) -> dict[str, Any]:
    viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    css_responsive_clues = len(re.findall(r"@media|max-width|min-width|clamp\(|vw|vh", html, flags=re.I))
    return {
        "viewport_meta_found": bool(viewport),
        "responsive_clues": css_responsive_clues,
    }


def analyze_technical_signals(soup: BeautifulSoup, response: requests.Response, links: dict[str, list[str]], final_url: str) -> dict[str, Any]:
    return {
        "page_size_bytes": len(response.content or b""),
        "script_count": len(soup.find_all("script")),
        "image_count": len(soup.find_all("img")),
        "internal_link_count": len(links["internal"]),
        "external_link_count": len(links["external"]),
        "content_type": response.headers.get("Content-Type", ""),
        "final_url": final_url,
    }


def quick_url_exists(url: str) -> bool:
    try:
        response = fetch_url(url, method="GET", timeout=6)
        return response.status_code < 400
    except requests.RequestException:
        return False


def check_internal_links(urls: list[str]) -> list[dict[str, Any]]:
    results = []
    for url in urls:
        try:
            response = fetch_url(url, method="HEAD", timeout=5)
            if response.status_code in {403, 405}:
                response = fetch_url(url, method="GET", timeout=6)
            results.append({"url": url, "status_code": response.status_code, "ok": response.status_code < 400})
        except requests.RequestException as exc:
            results.append({"url": url, "status_code": None, "ok": False, "error": str(exc)})
    return results


def resolve_dns(hostname: str) -> dict[str, Any]:
    try:
        return {"a_record_found": True, "addresses": socket.gethostbyname_ex(hostname)[2][:5]}
    except OSError:
        return {"a_record_found": False, "addresses": []}


def score_checks(raw: dict[str, Any]) -> dict[str, int]:
    contact = raw["contact"]
    seo = raw["seo"]
    action = raw["customer_action"]
    mobile = raw["mobile"]
    security_headers = raw["security_headers"]
    broken = raw["broken_link_sample"]
    technical = raw["technical"]

    trust = 35
    trust += 15 if raw["https_active"] else 0
    trust += 10 if contact["contact_page_link_found"] else 0
    trust += 10 if contact["visible_phone_found"] or contact["tel_link_found"] else 0
    trust += 10 if contact["visible_email_found"] or contact["email_link_found"] else 0
    trust += 8 if contact["privacy_policy_link_found"] else 0
    trust += min(12, sum(security_headers.values()) * 2)

    clarity = 30
    clarity += 15 if seo["title_present"] and 20 <= seo["title_length"] <= 70 else 7 if seo["title_present"] else 0
    clarity += 15 if seo["meta_description_present"] and 70 <= seo["meta_description_length"] <= 170 else 7 if seo["meta_description_present"] else 0
    clarity += 12 if seo["h1_present"] else 0
    clarity += 8 if seo["canonical_tag_found"] else 0
    clarity += 8 if seo["open_graph_tags_found"] else 0
    clarity += 6 if seo["sitemap_found"] else 0
    clarity += 6 if seo["robots_found"] else 0

    customer = 35
    customer += min(25, len(action["cta_keywords_found"]) * 5)
    customer += 15 if action["contact_form_clues_found"] else 0
    customer += 10 if action["phone_link_found"] else 0
    customer += 10 if contact["contact_page_link_found"] else 0

    mobile_score = 45
    mobile_score += 30 if mobile["viewport_meta_found"] else 0
    mobile_score += min(20, mobile["responsive_clues"] * 2)
    mobile_score += 5 if technical["page_size_bytes"] < 2_500_000 else 0

    broken_count = sum(1 for item in broken if not item["ok"])
    technical_score = 45
    technical_score += 15 if raw["status_code"] < 400 else 0
    technical_score += 15 if raw["response_time_ms"] < 2500 else 7 if raw["response_time_ms"] < 5000 else 0
    technical_score += min(15, sum(security_headers.values()) * 3)
    technical_score -= min(20, broken_count * 5)

    return {
        "trust_score": clamp_score(trust),
        "google_clarity_score": clamp_score(clarity),
        "customer_action_score": clamp_score(customer),
        "mobile_score": clamp_score(mobile_score),
        "technical_health_score": clamp_score(technical_score),
    }


def clamp_score(value: int | float) -> int:
    return int(max(0, min(100, round(value))))


def issue(issue_id: str, title: str, category: str, severity: str, found: str, matters: str, impact: str, fix: str, priority: int, difficulty: str) -> dict[str, Any]:
    return {
        "id": issue_id,
        "title": title,
        "category": category,
        "severity": severity,
        "what_we_found": found,
        "why_it_matters": matters,
        "business_impact": impact,
        "suggested_fix": fix,
        "priority": priority,
        "difficulty": difficulty,
    }


def build_issues(raw: dict[str, Any], scores: dict[str, int]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    seo = raw["seo"]
    contact = raw["contact"]
    action = raw["customer_action"]
    mobile = raw["mobile"]
    headers = raw["security_headers"]
    broken_count = sum(1 for item in raw["broken_link_sample"] if not item["ok"])

    if not raw["https_active"]:
        issues.append(issue("https", "Trust signal issue", "Trust", "high", "The final page did not load over HTTPS.", "Customers expect the browser to show a secure connection before they share information.", "Improving this trust signal can reduce hesitation before contact or quote requests.", "Enable HTTPS and redirect HTTP traffic to the secure version.", 1, "moderate"))
    if not seo["meta_description_present"]:
        issues.append(issue("meta-description", "Search result messaging opportunity", "Google Clarity", "medium", "The homepage is missing a meta description.", "Searchers often see this text before choosing whether to click.", "A clear snippet can bring more qualified visitors from search.", "Add a concise meta description that explains the offer, location, and next step.", 2, "easy"))
    if not seo["h1_present"]:
        issues.append(issue("h1", "Page headline clarity opportunity", "Google Clarity", "medium", "No clear H1 headline was found.", "A strong main heading helps visitors and search engines understand the page quickly.", "Clearer page structure can improve trust and reduce confusion.", "Add one descriptive H1 that names the main offer or business category.", 3, "easy"))
    if not contact["contact_page_link_found"]:
        issues.append(issue("contact-link", "Contact path could be clearer", "Customer Action", "high", "A contact page link was not obvious in the sampled homepage links.", "Local customers often look for a simple way to reach the business.", "A clearer contact path can turn more visitors into leads.", "Add a visible Contact, Book, Quote, or Call link in the main navigation.", 1, "easy"))
    if not action["cta_keywords_found"]:
        issues.append(issue("cta", "Customer action flow can be strengthened", "Customer Action", "medium", "The homepage text did not show strong action wording like quote, book, call, or schedule.", "Visitors need a direct next step when they are ready to act.", "Clear action language can increase calls, forms, and quote requests.", "Add one primary action near the top of the page and repeat it naturally lower on the page.", 2, "easy"))
    if not mobile["viewport_meta_found"]:
        issues.append(issue("viewport", "Mobile readiness signal missing", "Mobile Experience", "high", "The page is missing a viewport meta tag.", "Without it, mobile browsers may render the page awkwardly.", "Better mobile presentation helps visitors stay engaged on phones.", "Add a viewport meta tag and verify the page on common mobile widths.", 1, "easy"))
    missing_headers = [name for name, present in headers.items() if not present]
    if len(missing_headers) >= 3:
        issues.append(issue("security-headers", "Browser protection signals missing", "Technical Health", "medium", f"{len(missing_headers)} common browser protection headers were not detected.", "These headers help browsers handle framing, content types, referrers, and permissions more predictably.", "Adding them can improve confidence and technical quality without changing the design.", "Add appropriate security headers at the hosting or server level.", 4, "moderate"))
    if broken_count:
        issues.append(issue("sample-broken-links", "Link maintenance opportunity", "Technical Health", "medium", f"{broken_count} sampled internal link(s) did not return a clean response.", "Dead or blocked links interrupt the customer journey.", "Cleaning up link paths can keep visitors moving toward contact or purchase.", "Review sampled internal links and update, redirect, or remove stale URLs.", 3, "moderate"))

    if not issues:
        issues.append(issue("optimize-cta", "Fast conversion polish opportunity", "Customer Action", "low", "The main signals looked healthy in this first pass.", "Even healthy sites can usually make the next step easier to notice.", "Small CTA and proof-point improvements can lift results without a full rebuild.", "Tighten the homepage hero message, primary CTA, and trust proof near the top.", 5, "easy"))

    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(issues, key=lambda item: (severity_order.get(item["severity"], 3), item["priority"]))


def choose_fastest_win(issues: list[dict[str, Any]], raw: dict[str, Any]) -> dict[str, str]:
    easy = next((item for item in issues if item["difficulty"] == "easy"), issues[0])
    return {
        "title": easy["title"],
        "reason": easy["why_it_matters"],
        "suggested_action": easy["suggested_fix"],
        "estimated_difficulty": easy["difficulty"],
    }


def build_summary(scores: dict[str, int], raw: dict[str, Any]) -> str:
    return (
        "Steve reviewed the public homepage experience, trust signals, search clarity, customer action flow, "
        "mobile readiness, and technical basics. The report highlights the clearest opportunities to help the "
        f"site earn confidence and move visitors toward action. {raw['technical']['internal_link_count']} internal "
        "link(s) were found on the page and a small sample was checked."
    )


def run_advanced_tools(url: str, hostname: str, tools_available: dict[str, bool]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for key, builder in ADVANCED_TOOL_COMMANDS.items():
        tool = key.split("_", 1)[0]
        if not tools_available.get(tool):
            results[key] = {"ran": False, "summary": f"{tool} is not installed.", "raw_excerpt": "", "error": "Tool not found."}
            continue
        command, timeout = builder(url, hostname)
        result = safe_run_tool(command, timeout)
        result["summary"] = summarize_tool_result(key, result.get("raw_excerpt", ""))
        results[key] = result
    return results


def summarize_tool_result(name: str, raw: str) -> str:
    lower = (raw or "").lower()
    if name == "whatweb":
        return "Platform/technology identified." if raw else "No technology summary returned."
    if name == "curl":
        return "Header response collected for business-facing technical review." if raw else "No header response returned."
    if name.startswith("dig"):
        return "DNS record information collected." if raw else "No DNS output returned."
    if name == "whois":
        return "Domain registration details collected." if raw else "No WHOIS output returned."
    if name == "sslscan":
        if "accepted" in lower or "tls" in lower:
            return "HTTPS certificate and protocol signals reviewed."
        return "SSL scan returned limited information."
    if name == "wafw00f":
        if "is behind" in lower or "detected" in lower:
            return "Site appears to use traffic protection."
        return "No obvious traffic protection product was identified."
    if name == "nmap":
        return "Public service check completed; any open items are phrased as public services, not vulnerabilities."
    if name == "nikto":
        return "Basic web server hygiene output collected for authorized review."
    return "Tool output collected."


def apply_advanced_findings(result: dict[str, Any], tool_results: dict[str, dict[str, Any]]) -> None:
    issues = list(result.get("top_issues", []))
    raw_checks = result.setdefault("raw_checks", {})
    raw_checks["advanced_tool_summary"] = {name: data.get("summary", "") for name, data in tool_results.items()}

    nmap_raw = tool_results.get("nmap", {}).get("raw_excerpt", "")
    open_lines = [line for line in nmap_raw.splitlines() if re.search(r"\bopen\b", line)]
    if open_lines:
        issues.append(issue(
            "public-services",
            "Public service detected",
            "Technical Health",
            "low",
            f"The authorized advanced check found {len(open_lines)} public service line(s).",
            "Public services can be normal, but business owners should know what is intentionally exposed.",
            "This supports better hosting hygiene and vendor conversations without assuming a problem.",
            "Confirm each public service is expected with the hosting provider or technical maintainer.",
            5,
            "moderate",
        ))

    waf_raw = tool_results.get("wafw00f", {}).get("raw_excerpt", "").lower()
    if "is behind" in waf_raw or "detected" in waf_raw:
        raw_checks["traffic_protection_detected"] = True

    result["top_issues"] = sorted(issues, key=lambda item: item["priority"])[:3]
    result["summary"] += " Advanced authorized tooling was also run and translated into business-facing notes."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
