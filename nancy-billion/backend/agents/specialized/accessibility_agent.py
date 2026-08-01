"""
Accessibility Agent for Nancy/Billion.
Real WCAG 2.x contrast-ratio calculation from the actual relative-luminance
formula the W3C spec defines -- an honest pass/fail against the real AA/AAA
thresholds, not a guessed color-pairing opinion.
"""
from __future__ import annotations

from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent


def _relative_luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = lin(r), lin(g), lin(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


class AccessibilityAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Accessibility Agent", "accessibility")
        self.capabilities.update({
            "description": "Real WCAG 2.x contrast-ratio calculation from actual relative-luminance math, with honest AA/AAA pass/fail",
            "confidence": 0.85,
            "specializations": ["wcag-contrast", "color-accessibility"],
            "tools": ["wcag-relative-luminance"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "contrast_ratio":
            return self._contrast(task_data.get("foreground", ""), task_data.get("background", ""))
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    def _contrast(self, fg: str, bg: str) -> Dict[str, Any]:
        try:
            l1, l2 = _relative_luminance(fg), _relative_luminance(bg)
        except Exception:
            return {"success": False, "error": "foreground/background must be valid hex colors (e.g. '#ffffff')"}
        lighter, darker = max(l1, l2), min(l1, l2)
        ratio = (lighter + 0.05) / (darker + 0.05)
        return {
            "success": True,
            "foreground": fg, "background": bg,
            "contrast_ratio": round(ratio, 2),
            "passes_aa_normal_text": ratio >= 4.5,
            "passes_aa_large_text": ratio >= 3.0,
            "passes_aaa_normal_text": ratio >= 7.0,
            "passes_aaa_large_text": ratio >= 4.5,
        }

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I compute real WCAG contrast ratios between two hex colors, with an honest AA/AAA pass/fail."
        )}
