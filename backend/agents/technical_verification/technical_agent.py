from typing import Any, Callable, Dict, Optional, Tuple


class TechnicalVerificationAgent:
    def __init__(self, registry):
        self.registry = registry

    def verify(
        self,
        *,
        root_cid: str,
        options: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Tuple[Dict[str, Any], str]:
        tool_options = dict(options or {})
        if progress_callback is not None:
            tool_options["_progress_callback"] = progress_callback

        data = self.registry.execute(
            "technical.verify_all@v1",
            {"rootCid": root_cid, "options": tool_options},
        )
        return data, self._build_summary(data)

    def _build_summary(self, result: Dict[str, Any]) -> str:
        success = result.get("success") is True
        failures = result.get("failures") or []
        claims = result.get("claims") or []

        if success:
            return "Technical verification passed (all checks OK)."

        codes = [f.get("code") for f in failures if isinstance(f, dict) and f.get("code")]
        unique_codes = []
        for c in codes:
            if c not in unique_codes:
                unique_codes.append(c)

        headline = f"Technical verification failed ({len(failures)} failure(s))."
        if unique_codes:
            headline += " Codes: " + ", ".join(unique_codes[:6]) + ("…" if len(unique_codes) > 6 else "")

        # Add quick signal on provenance/governance if present.
        cont = next((c for c in claims if c.get("type") == "provenance.continuity"), None)
        gov = next((c for c in claims if c.get("type") == "provenance.governance"), None)
        extras = []
        if isinstance(cont, dict) and cont.get("verified") is False:
            extras.append("provenance continuity broken")
        if isinstance(gov, dict) and gov.get("verified") is False:
            extras.append("governance mismatch")
        if extras:
            headline += " Signals: " + "; ".join(extras) + "."

        return headline
