import re
import ssl
import sys
import urllib.error
import urllib.request

REDIRECT_RE = re.compile(
    r"https://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/[^\s\)]+"
)

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def resolve_url(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            return r.url
    except urllib.error.HTTPError as e:
        # redirects were followed; final page may 4xx/5xx but e.url is the real target
        if e.url and e.url != url:
            return e.url
        print(f"  ! failed: {url[:80]}... ({e})", file=sys.stderr)
        return url
    except Exception as e:
        print(f"  ! failed: {url[:80]}... ({e})", file=sys.stderr)
        return url


def resolve_text(text, verbose=True):
    urls = list(dict.fromkeys(REDIRECT_RE.findall(text)))
    if not urls:
        return text
    if verbose:
        print(f"resolving {len(urls)} redirect link(s)...", file=sys.stderr)
    for i, u in enumerate(urls, 1):
        real = resolve_url(u)
        if real and real != u:
            text = text.replace(u, real)
            if verbose:
                print(f"  [{i}/{len(urls)}] {real}", file=sys.stderr)
        elif verbose:
            print(f"  [{i}/{len(urls)}] (unchanged)", file=sys.stderr)
    return text
