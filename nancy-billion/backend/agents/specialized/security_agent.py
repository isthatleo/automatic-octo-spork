"""
Security Agent for Nancy Billion Backend
Real security analysis - PII detection, vulnerability scanning, compliance auditing.
"""
from .base_specialized_agent import SpecializedAgent
from ..real_compute import compute_statistics, entropy
from typing import Dict, Any, List
import re
import hashlib
import ipaddress


_SECRET_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[-.\s]?){3}\d{4}\b"),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "api_key": re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[=:]\s*['\"][^'\"]{8,}['\"]"),
    "aws_key": re.compile(r"(?i)AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    "authorization": re.compile(r"(?i)authorization:\s*(?:bearer|basic|digest)\s+\S+", re.MULTILINE),
}

_VULNERABILITY_PATTERNS: dict[str, re.Pattern] = {
    "sql_injection": re.compile(r"(?:execute|exec|raw|query)\s*\(\s*['\"].*\{.*['\"]|SELECT\s+.*\bFROM\b.*\bWHERE\b.*(?:\+|%)", re.IGNORECASE),
    "xss": re.compile(r"innerHTML|outerHTML|document\.write|dangerouslySetInnerHTML|eval\s*\(", re.IGNORECASE),
    "command_injection": re.compile(r"(?:os\.system|subprocess\.(?:call|Popen|run)|eval|exec|popen)\s*\(", re.IGNORECASE),
    "path_traversal": re.compile(r"(?:\.\./|\.\.\\)|os\.path\.join\s*\(\s*[^,]*\.\.", re.IGNORECASE),
    "hardcoded_credential": re.compile(r"(?i)(?:password|passwd|pwd|secret)\s*[=:]\s*['\"][^'\"]{3,}['\"]"),
    "insecure_crypto": re.compile(r"(?i)(?:md5|sha1|des_ede3_cbc|rc2|rc4)\s*\("),
    "debug_endpoint": re.compile(r"(?i)(?:/debug|/test|/admin|/api-doc|/swagger)"),
}

_COMPLIANCE_FRAMEWORKS: dict[str, dict[str, list[str]]] = {
    "gdpr": {
        "key_terms": ["personal data", "data subject", "consent", "processing", "data protection", "pii", "privacy", "data breach", "right to access", "right to erasure", "data portability"],
        "controls": ["encryption_at_rest", "access_controls", "audit_logging", "data_minimization", "consent_management", "breach_notification"]
    },
    "hipaa": {
        "key_terms": ["phi", "protected health information", "health record", "patient data", "medical record", "ehr", "ehi", "covered entity", "baa"],
        "controls": ["access_control", "audit_controls", "integrity_controls", "person_auth", "transmission_security", "contingency_plan"]
    },
    "pci_dss": {
        "key_terms": ["cardholder data", "pan", "credit card", "cvv", "cvc", "payment", "merchant", "acquirer", "tokenization"],
        "controls": ["firewall", "encryption", "access_restriction", "monitoring", "testing", "policy"]
    },
    "soc2": {
        "key_terms": ["security", "availability", "processing integrity", "confidentiality", "privacy", "trust service", "control environment"],
        "controls": ["access_management", "change_management", "risk_assessment", "vendor_management", "incident_response"]
    }
}


class SecurityAgent(SpecializedAgent):
    """Specialized agent for security analysis, vulnerability scanning, and compliance auditing"""

    def __init__(self, settings):
        super().__init__(settings, "Security Agent", "security")
        self.capabilities.update({
            "description": "Security agent for real PII detection, vulnerability scanning, and compliance auditing",
            "confidence": 0.95,
            "specializations": ["pii-detection", "vulnerability-scanning", "compliance-auditing", "secret-detection", "code-security-review"]
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "security-audit")
        if task_type == "pii-scan":
            return await self._scan_pii(task_data)
        elif task_type == "vulnerability-scan":
            return await self._scan_vulnerabilities(task_data)
        elif task_type == "compliance-audit":
            return await self._audit_compliance(task_data)
        elif task_type == "secret-detection":
            return await self._detect_secrets(task_data)
        elif task_type == "code-review":
            return await self._review_code_security(task_data)
        else:
            return await self._general_security_overview(task_data)

    async def _scan_pii(self, params: Dict[str, Any]) -> Dict[str, Any]:
        text = params.get("text", "")
        findings = []
        for pii_type, pattern in _SECRET_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                unique = list(set(matches))
                findings.append({
                    "type": pii_type, "count": len(unique),
                    "severity": "critical" if pii_type in ("ssn", "credit_card", "private_key") else "high" if pii_type in ("aws_key", "api_key", "jwt") else "medium",
                    "samples": [m[:20] + "..." if len(m) > 20 else m for m in unique[:3]]
                })
        risk_score = sum({"critical": 10, "high": 5, "medium": 2, "low": 1}.get(f["severity"], 0) * f["count"] for f in findings)
        return {
            "success": True, "task_type": "pii-scan",
            "total_findings": len(findings),
            "pii_found": findings,
            "risk_score": min(100, risk_score),
            "risk_level": "critical" if risk_score > 50 else "high" if risk_score > 20 else "medium" if risk_score > 5 else "low",
            "recommendations": [f"Redact or encrypt all {f['type']} instances" for f in findings]
        }

    async def _scan_vulnerabilities(self, params: Dict[str, Any]) -> Dict[str, Any]:
        source = params.get("source_code", "")
        findings = []
        for vuln_type, pattern in _VULNERABILITY_PATTERNS.items():
            matches = pattern.findall(source)
            if matches:
                severity_map = {"sql_injection": "critical", "command_injection": "critical", "xss": "high", "hardcoded_credential": "critical", "path_traversal": "high", "insecure_crypto": "high", "debug_endpoint": "medium"}
                findings.append({
                    "type": vuln_type.replace("_", " ").title(),
                    "count": len(matches),
                    "severity": severity_map.get(vuln_type, "medium")
                })
        severity_scores = {"critical": 10, "high": 5, "medium": 2, "low": 1}
        total_risk = sum(severity_scores.get(f["severity"], 0) * f["count"] for f in findings)
        return {
            "success": True, "task_type": "vulnerability-scan",
            "vulnerabilities_found": findings,
            "risk_score": min(100, total_risk),
            "risk_level": "critical" if total_risk > 50 else "high" if total_risk > 20 else "medium" if total_risk > 5 else "low",
            "severity_summary": {s: sum(1 for f in findings if f["severity"] == s) for s in ("critical", "high", "medium", "low")},
            "recommendations": ["Fix critical/high severity vulnerabilities first", "Run SAST in CI/CD pipeline", "Conduct regular penetration testing"]
        }

    async def _audit_compliance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        framework = params.get("framework", "gdpr").lower()
        description = params.get("system_description", "")

        fw = _COMPLIANCE_FRAMEWORKS.get(framework, _COMPLIANCE_FRAMEWORKS["gdpr"])

        term_matches = sum(1 for term in fw["key_terms"] if term.lower() in description.lower())
        term_score = min(100, (term_matches / max(len(fw["key_terms"]), 1)) * 100)

        control_statuses = {}
        for control in fw["controls"]:
            keywords = control.replace("_", " ").lower().split()
            found = any(kw in description.lower() for kw in keywords)
            control_statuses[control] = "implemented" if found else "not_found"

        implemented = sum(1 for v in control_statuses.values() if v == "implemented")
        compliance_percent = min(100, int((implemented / max(len(control_statuses), 1)) * 100))

        return {
            "success": True, "task_type": "compliance-audit", "framework": framework,
            "compliance_score": compliance_percent,
            "term_coverage": round(term_score, 1),
            "controls": control_statuses,
            "gaps": [c for c, s in control_statuses.items() if s == "not_found"],
            "recommendations": [f"Implement {control}" for control, status in control_statuses.items() if status == "not_found"]
        }

    async def _detect_secrets(self, params: Dict[str, Any]) -> Dict[str, Any]:
        text = params.get("text", "")
        findings = []
        for secret_type, pattern in _SECRET_PATTERNS.items():
            if secret_type in ("email", "phone", "ip_address", "credit_card", "ssn", "private_key", "aws_key", "jwt", "api_key", "authorization"):
                matches = pattern.findall(text)
                if matches:
                    entropy_scores = []
                    for m in set(matches):
                        if len(m) > 4:
                            h = hashlib.sha256(m.encode()).hexdigest()[:12]
                            prob_dist = [m.count(c) / len(m) for c in set(m)]
                            ent = entropy(prob_dist)
                            entropy_scores.append({"hash": h, "entropy": round(ent, 4), "length": len(m), "severity": "high" if ent > 3.5 else "medium" if ent > 2.5 else "low"})
                    findings.append({"type": secret_type, "count": len(set(matches)), "details": entropy_scores[:5]})
        return {
            "success": True, "task_type": "secret-detection",
            "secrets_found": findings,
            "total_secrets": sum(f["count"] for f in findings),
            "recommendations": ["Revoke and rotate exposed secrets", "Use environment variables or vault for secrets", "Add pre-commit hooks for secret detection"]
        }

    async def _review_code_security(self, params: Dict[str, Any]) -> Dict[str, Any]:
        vuln_result = await self._scan_vulnerabilities(params)
        secret_result = await self._detect_secrets(params)
        return {
            "success": True, "task_type": "code-review",
            "vulnerability_scan": vuln_result,
            "secret_scan": secret_result,
            "overall_score": max(0, 100 - vuln_result.get("risk_score", 0) - secret_result.get("total_secrets", 0) * 2),
            "recommendations": [
                "Address all critical vulnerabilities before deployment",
                "Implement SAST/DAST in the CI/CD pipeline",
                "Conduct regular security reviews",
                "Follow OWASP Top 10 guidelines"
            ]
        }

    async def _general_security_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "general security question")
        answer = await self._llm_answer(query)
        return {
            "success": True, "task_type": "security-overview",
            "query": query,
            **({"response": answer} if answer else {}),
            "capabilities": [
                {"name": "PII Detection", "description": "Detect emails, phones, SSNs, credit cards, IPs"},
                {"name": "Vulnerability Scanning", "description": "SQL injection, XSS, command injection, path traversal"},
                {"name": "Compliance Auditing", "description": "GDPR, HIPAA, PCI-DSS, SOC2 gap analysis"},
                {"name": "Secret Detection", "description": "API keys, tokens, private keys, JWTs with entropy analysis"}
            ],
            "frameworks_supported": list(_COMPLIANCE_FRAMEWORKS.keys()),
            "recommendations": [
                "Run security scans as part of CI/CD pipeline",
                "Conduct regular compliance audits",
                "Use vault/environment variables for secrets"
            ]
        }
