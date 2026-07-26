"""Real static security linting for file content Nancy is about to write --
ported in spirit from Hermes' security-guidance plugin (25 regex/lookbehind
rules over write_file/patch output). Zero LLM tokens: pure regex over the
content string, run right before the write's Telegram approval request goes
out, so a risky pattern shows up in what the user is approving instead of
silently landing on disk.

This is advisory, not a gate -- it never blocks a write itself (that's what
the approval step immediately after it is for); it just makes sure the human
approving the write can see what a quick static scan noticed.
"""
from __future__ import annotations

import re
from typing import List, NamedTuple


class LintFinding(NamedTuple):
    rule: str
    message: str


_RULES: List[tuple] = [
    ("unsafe-deserialization", re.compile(r'\bpickle\.loads?\s*\('), "pickle.load(s) can execute arbitrary code from untrusted data"),
    ("unsafe-deserialization", re.compile(r'\byaml\.load\s*\((?!.*Loader=yaml\.SafeLoader)'), "yaml.load without SafeLoader can execute arbitrary code"),
    ("code-injection", re.compile(r'\beval\s*\('), "eval() on any non-constant input is arbitrary code execution"),
    ("code-injection", re.compile(r'\bexec\s*\('), "exec() on any non-constant input is arbitrary code execution"),
    ("command-injection", re.compile(r'\bos\.system\s*\('), "os.system() with any interpolated input is a shell-injection risk"),
    ("command-injection", re.compile(r'subprocess\.(run|call|Popen|check_output)\([^)]*shell\s*=\s*True'), "subprocess with shell=True and interpolated input is a shell-injection risk"),
    ("sql-injection", re.compile(r'(execute|executemany)\s*\(\s*f["\']'), "f-string interpolated directly into a SQL execute() call -- use parameterized queries"),
    ("sql-injection", re.compile(r'(execute|executemany)\s*\([^)]*%\s*\('), "% string formatting interpolated into SQL -- use parameterized queries"),
    ("xss-sink", re.compile(r'dangerouslySetInnerHTML'), "dangerouslySetInnerHTML with unsanitized input is a real XSS sink"),
    ("xss-sink", re.compile(r'\.innerHTML\s*='), "assigning to innerHTML with unsanitized input is a real XSS sink"),
    ("xss-sink", re.compile(r'document\.write\s*\('), "document.write with any dynamic input is a real XSS sink"),
    ("crypto-footgun", re.compile(r'\bhashlib\.md5\s*\('), "MD5 is broken for any security-relevant use (integrity/passwords)"),
    ("crypto-footgun", re.compile(r'\bhashlib\.sha1\s*\('), "SHA-1 is broken for any security-relevant use"),
    ("crypto-footgun", re.compile(r'\brandom\.(random|randint|choice)\s*\('), "the `random` module is not cryptographically secure -- use `secrets` for tokens/keys"),
    ("crypto-footgun", re.compile(r'DES|RC4\b'), "DES/RC4 are broken ciphers"),
    ("hardcoded-secret", re.compile(r'(api[_-]?key|secret|password|token)\s*=\s*["\'][A-Za-z0-9_\-]{16,}["\']', re.I), "looks like a hardcoded credential -- use an environment variable instead"),
    ("xxe", re.compile(r'etree\.parse\s*\((?!.*resolve_entities\s*=\s*False)'), "XML parsing without disabling entity resolution is an XXE risk"),
    ("missing-sri", re.compile(r'<script[^>]+src=["\']https?://(?!.*integrity=)', re.I), "external <script> tag with no Subresource Integrity (SRI) hash"),
    ("path-traversal", re.compile(r'open\s*\([^)]*\+.*request\.'), "path built from request input passed directly to open() -- validate/normalize first"),
    ("insecure-transport", re.compile(r'verify\s*=\s*False'), "TLS certificate verification disabled (verify=False)"),
    ("insecure-transport", re.compile(r'ssl\._create_unverified_context'), "unverified SSL context disables certificate validation"),
    ("debug-flag", re.compile(r'\bDEBUG\s*=\s*True\b'), "DEBUG=True should never ship to production"),
    ("ci-injection", re.compile(r'\$\{\{\s*github\.event\.(issue|pull_request)\.(title|body)\s*\}\}'), "untrusted GitHub Actions expression interpolated directly into a run: step -- use an env var instead"),
    ("weak-permission", re.compile(r'chmod\s*\(\s*[^,]+,\s*0o777\s*\)'), "chmod 0o777 grants world write access"),
    ("assert-for-security", re.compile(r'^\s*assert\s+.*(auth|permission|is_admin)', re.I | re.M), "assert is stripped under python -O -- don't use it for real security checks"),
]


def lint_content(content: str) -> List[LintFinding]:
    findings: List[LintFinding] = []
    for rule, pattern, message in _RULES:
        if pattern.search(content):
            findings.append(LintFinding(rule=rule, message=message))
    return findings


def format_findings(findings: List[LintFinding]) -> str:
    if not findings:
        return ""
    lines = [f"- [{f.rule}] {f.message}" for f in findings]
    return "\n\nStatic security scan flagged:\n" + "\n".join(lines)
