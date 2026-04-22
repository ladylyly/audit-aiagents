import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.agents.technical_verification.technical_agent import TechnicalVerificationAgent
from backend.integrations.llm_client import LLMClient, extract_cid_from_text
from backend.services.ipfs_fetcher import IpfsFetchConfig, IpfsFetcher, default_ipfs_config
from backend.services.provenance_graph import build_provenance_graph
from backend.services.tool_registry.default_registry import create_default_registry


@dataclass(frozen=True)
class OrchestratorConfig:
    max_nodes: int = 50
    ipfs: IpfsFetchConfig = default_ipfs_config()
    llm_mode: str = "plan_and_route"  # plan_and_route | route_only | off
    llm_strict: bool = True
    domain_summary_llm_enabled: bool = True


class Orchestrator:
    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self.config = config or OrchestratorConfig()
        self.ipfs_fetcher = IpfsFetcher(self.config.ipfs)
        self.registry = create_default_registry()
        self.technical_agent = TechnicalVerificationAgent(self.registry)
        self._llm: Optional[LLMClient] = None

    def _get_llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm

    def build_graph(self, root_cid: str) -> Dict[str, Any]:
        """
        Build the provenance graph by following the linked component credentials.
        """
        return build_provenance_graph(
            root_cid,
            self.ipfs_fetcher.fetch_json,
            max_nodes=self.config.max_nodes,
        )

    def fetch_vcs_for_graph(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fetch the VC payload for each node in the graph.
        """
        vcs_by_cid: Dict[str, Any] = {}
        for n in graph.get("nodes") or []:
            cid = n.get("cid") if isinstance(n, dict) else None
            if not cid or cid in vcs_by_cid:
                continue
            vcs_by_cid[cid] = self.ipfs_fetcher.fetch_json(cid)
        return vcs_by_cid

    def run_technical_verification(
        self,
        *,
        root_cid: str,
        options: Optional[Dict[str, Any]] = None,
        progress_callback=None,
    ):
        opts = dict(options or {})
        if "maxNodes" not in opts:
            opts["maxNodes"] = self.config.max_nodes
        opts = {k: v for k, v in opts.items() if v is not None}
        return self.technical_agent.verify(
            root_cid=root_cid,
            options=opts,
            progress_callback=progress_callback,
        )

    def run_compliance(
        self,
        *,
        root_cid: str,
        graph: Dict[str, Any],
        vcs_by_cid: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        tool_input = {"rootCid": root_cid, "graph": graph, "vcsByCid": vcs_by_cid}
        for key in (
            "rulepackId",
            "rulepackIds",
            "rulepackPath",
            "rulepackPaths",
            "rulepackIndexPath",
            "assessmentDate",
            "secondaryLegislationReady",
        ):
            if isinstance(options, dict) and key in options:
                tool_input[key] = options[key]
        return self.registry.execute(
            "compliance.verify@v1",
            tool_input,
        )

    def run_certification(
        self,
        *,
        root_cid: str,
        graph: Dict[str, Any],
        vcs_by_cid: Dict[str, Any],
        technical_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.registry.execute(
            "certification.verify@v1",
            {
                "rootCid": root_cid,
                "graph": graph,
                "vcsByCid": vcs_by_cid,
                "technicalResult": technical_result,
            },
        )

    def run_esg(self, *, root_cid: str, graph: Dict[str, Any], vcs_by_cid: Dict[str, Any]) -> Dict[str, Any]:
        return self.registry.execute(
            "esg.verify@v1",
            {"rootCid": root_cid, "graph": graph, "vcsByCid": vcs_by_cid},
        )

    def _build_supply_chain_profile(
        self,
        *,
        graph: Optional[Dict[str, Any]],
        vcs_by_cid: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not isinstance(vcs_by_cid, dict) or len(vcs_by_cid) == 0:
            nodes = (graph or {}).get("nodes") if isinstance(graph, dict) else []
            return {
                "nodeCount": len(nodes) if isinstance(nodes, list) else 0,
                "edgeCount": len((graph or {}).get("edges") or []) if isinstance(graph, dict) else 0,
                "countries": [],
                "countryCodes": [],
                "materials": [],
                "facilityRoles": [],
                "operationTags": [],
                "certificationNames": [],
                "topMaterials": [],
                "topCountries": [],
                "stageMix": {},
                "hasConflictMineralsClaims": False,
            }

        country_names = set()
        country_codes = set()
        material_counter: Counter[str] = Counter()
        operation_tag_counter: Counter[str] = Counter()
        role_counter: Counter[str] = Counter()
        certification_counter: Counter[str] = Counter()
        stage_counter: Counter[str] = Counter()
        has_conflict_claims = False
        root_product_name: Optional[str] = None

        root_cid = None
        if isinstance(graph, dict):
            node_index_by_cid = graph.get("nodeIndexByCid") or {}
            if isinstance(node_index_by_cid, dict):
                root_cid = next(
                    (cid for cid, idx in node_index_by_cid.items() if idx == 0),
                    None,
                )

        for cid, vc in vcs_by_cid.items():
            if not isinstance(vc, dict):
                continue
            subject = vc.get("credentialSubject") or {}
            if not isinstance(subject, dict):
                continue

            location = subject.get("location") or {}
            if isinstance(location, dict):
                country = location.get("country")
                country_code = location.get("countryCode")
                if isinstance(country, str) and country.strip():
                    country_names.add(country.strip())
                if isinstance(country_code, str) and country_code.strip():
                    country_codes.add(country_code.strip().upper())

            facility_role = subject.get("facilityRole")
            if isinstance(facility_role, str) and facility_role.strip():
                role_counter[facility_role.strip()] += 1

            for material in subject.get("materialTags") or []:
                if isinstance(material, str) and material.strip():
                    material_counter[material.strip()] += 1

            for tag in subject.get("operationTags") or []:
                if not isinstance(tag, str) or not tag.strip():
                    continue
                normalized = tag.strip()
                operation_tag_counter[normalized] += 1
                if normalized in {"upstream", "midstream", "downstream"}:
                    stage_counter[normalized] += 1

            for cert in subject.get("certifications") or []:
                if isinstance(cert, dict):
                    cert_name = cert.get("name")
                    if isinstance(cert_name, str) and cert_name.strip():
                        certification_counter[cert_name.strip()] += 1
                elif isinstance(cert, str) and cert.strip():
                    certification_counter[cert.strip()] += 1

            claims = subject.get("claims") or {}
            if isinstance(claims, dict) and isinstance(claims.get("conflict_minerals"), dict):
                has_conflict_claims = True

            if root_cid and cid == root_cid:
                product_name = subject.get("productName")
                if isinstance(product_name, str) and product_name.strip():
                    root_product_name = product_name.strip()

        nodes = (graph or {}).get("nodes") if isinstance(graph, dict) else []
        edges = (graph or {}).get("edges") if isinstance(graph, dict) else []
        return {
            "nodeCount": len(nodes) if isinstance(nodes, list) else len(vcs_by_cid),
            "edgeCount": len(edges) if isinstance(edges, list) else 0,
            "countries": sorted(country_names),
            "countryCodes": sorted(country_codes),
            "materials": sorted(material_counter.keys()),
            "facilityRoles": sorted(role_counter.keys()),
            "operationTags": sorted(operation_tag_counter.keys()),
            "certificationNames": sorted(certification_counter.keys()),
            "topMaterials": [
                {"name": name, "count": count}
                for name, count in material_counter.most_common(5)
            ],
            "topCountries": [
                {"name": name, "count": count}
                for name, count in Counter(
                    (vc.get("credentialSubject") or {}).get("location", {}).get("country")
                    for vc in vcs_by_cid.values()
                    if isinstance(vc, dict)
                    and isinstance(vc.get("credentialSubject"), dict)
                    and isinstance((vc.get("credentialSubject") or {}).get("location"), dict)
                    and (vc.get("credentialSubject") or {}).get("location", {}).get("country")
                ).most_common(5)
            ],
            "stageMix": {
                "upstream": stage_counter.get("upstream", 0),
                "midstream": stage_counter.get("midstream", 0),
                "downstream": stage_counter.get("downstream", 0),
            },
            "rootProductName": root_product_name,
            "hasConflictMineralsClaims": has_conflict_claims,
        }

    def run(self, request: Any) -> Dict[str, Any]:
        """
        Run the orchestration flow.

        `request` can be a string prompt / CID or a dict with `rootCid`,
        `userPrompt`, and optional `options`.
        """
        if isinstance(request, str):
            req: Dict[str, Any] = {"userPrompt": request}
        elif isinstance(request, dict):
            req = dict(request)
        else:
            raise TypeError("request must be a string or dict")

        user_prompt = req.get("userPrompt")
        root_cid = req.get("rootCid") or req.get("cid")
        if not root_cid and isinstance(user_prompt, str):
            root_cid = extract_cid_from_text(user_prompt)

        options: Dict[str, Any] = dict(req.get("options") or {})
        if "maxNodes" not in options:
            options["maxNodes"] = self.config.max_nodes

        llm_mode = (self.config.llm_mode or "plan_and_route").strip()
        llm_strict = bool(self.config.llm_strict)

        available_tools = [
            {"name": "build_graph", "args": {"rootCid": "string"}},
            {"name": "fetch_vcs_for_graph", "args": {"graph": "object"}},
            {"name": "run_technical_verification", "args": {"rootCid": "string", "options": "object"}},
            {"name": "run_compliance", "args": {"graph": "object", "vcsByCid": "object"}},
            {"name": "run_certification", "args": {"graph": "object", "vcsByCid": "object"}},
            {"name": "run_esg", "args": {"graph": "object", "vcsByCid": "object"}},
        ]

        policy = {
            "strict": llm_strict,
            "mandatoryTools": ["build_graph", "run_technical_verification"] if llm_strict else [],
        }

        orchestration_plan: Optional[Dict[str, Any]] = None
        routing_suggestions: List[Dict[str, Any]] = []

        # Default action list if no plan is accepted.
        actions = [
            {"tool": "build_graph", "options": {}},
            {"tool": "fetch_vcs_for_graph", "options": {}},
            {
                "tool": "run_technical_verification",
                "options": {
                    k: v
                    for k, v in {
                        "rpcUrl": options.get("rpcUrl") or _resolve_rpc_url(),
                        "contractAddress": options.get("contractAddress") or os.getenv("VERIFYING_CONTRACT"),
                    }.items()
                    if v is not None
                },
            },
            {"tool": "run_compliance", "options": {}},
            {"tool": "run_certification", "options": {}},
            {"tool": "run_esg", "options": {}},
        ]

        # Let the LLM suggest a plan when enabled.
        if llm_mode != "off":
            try:
                llm = self._get_llm()
                orchestration_plan = llm.plan_orchestration(
                    root_cid=root_cid,
                    user_prompt=user_prompt,
                    available_tools=available_tools,
                    policy=policy,
                )
                if isinstance(orchestration_plan.get("rootCid"), str) and not root_cid:
                    root_cid = orchestration_plan["rootCid"]
                if isinstance(orchestration_plan.get("route"), list):
                    routing_suggestions = [x for x in orchestration_plan["route"] if isinstance(x, dict)]
                if llm_mode == "plan_and_route" and isinstance(orchestration_plan.get("actions"), list):
                    actions = [x for x in orchestration_plan["actions"] if isinstance(x, dict)]
            except Exception as e:
                # Fall back to the default action list if planning fails.
                orchestration_plan = {"error": str(e)}

        validated_actions = self._validate_actions(actions, strict=llm_strict)
        stage1_trace = self._build_planning_trace(
            available_tools=available_tools,
            validated_actions=validated_actions,
            orchestration_plan=orchestration_plan,
        )

        if not root_cid or not isinstance(root_cid, str):
            return {
                "success": False,
                "failures": [{"code": "MISSING_ROOT", "reason": "rootCid is required"}],
                "orchestration_plan": orchestration_plan,
                "routing_suggestions": routing_suggestions,
            }

        # Run the validated tool sequence.
        graph: Optional[Dict[str, Any]] = None
        vcs_by_cid: Optional[Dict[str, Any]] = None
        technical_result: Optional[Dict[str, Any]] = None
        technical_summary: Optional[str] = None
        compliance_result: Optional[Dict[str, Any]] = None
        certification_result: Optional[Dict[str, Any]] = None
        esg_result: Optional[Dict[str, Any]] = None

        requested_tools = [action.get("tool") for action in validated_actions]
        domain_actions = {"run_technical_verification", "run_compliance", "run_certification", "run_esg"}

        if any(tool in {"build_graph", "fetch_vcs_for_graph"} or tool in domain_actions for tool in requested_tools):
            if graph is None:
                graph = self.build_graph(root_cid)
            if vcs_by_cid is None:
                vcs_by_cid = self.fetch_vcs_for_graph(graph)

        tech_action = next((a for a in validated_actions if a.get("tool") == "run_technical_verification"), None)
        compliance_action = next((a for a in validated_actions if a.get("tool") == "run_compliance"), None)
        esg_action = next((a for a in validated_actions if a.get("tool") == "run_esg"), None)
        certification_action = next((a for a in validated_actions if a.get("tool") == "run_certification"), None)

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_map = {}

            if tech_action is not None:
                opts = tech_action.get("options") if isinstance(tech_action.get("options"), dict) else {}
                run_options = {
                    "maxNodes": options.get("maxNodes", self.config.max_nodes),
                    "rpcUrl": _resolve_rpc_url(opts.get("rpcUrl") or options.get("rpcUrl")),
                    "contractAddress": opts.get("contractAddress")
                    or options.get("contractAddress")
                    or os.getenv("VERIFYING_CONTRACT"),
                }
                run_options = {k: v for k, v in run_options.items() if v is not None}
                future_map["technical"] = executor.submit(
                    self.technical_agent.verify,
                    root_cid=root_cid,
                    options=run_options,
                    progress_callback=req.get("_progress_callback"),
                )

            if compliance_action is not None:
                compliance_options = {
                    key: value
                    for key, value in {
                        "rulepackId": req.get("rulepackId"),
                        "rulepackIds": req.get("rulepackIds"),
                        "rulepackPath": req.get("rulepackPath"),
                        "rulepackPaths": req.get("rulepackPaths"),
                        "rulepackIndexPath": req.get("rulepackIndexPath"),
                        "assessmentDate": req.get("assessmentDate") or options.get("assessmentDate"),
                        "secondaryLegislationReady": req.get("secondaryLegislationReady")
                        or options.get("secondaryLegislationReady"),
                        **(
                            compliance_action.get("options")
                            if isinstance(compliance_action.get("options"), dict)
                            else {}
                        ),
                    }.items()
                    if value is not None
                }
                future_map["compliance"] = executor.submit(
                    self.run_compliance,
                    root_cid=root_cid,
                    graph=graph or {},
                    vcs_by_cid=vcs_by_cid or {},
                    options=compliance_options,
                )

            if esg_action is not None:
                future_map["esg"] = executor.submit(
                    self.run_esg,
                    root_cid=root_cid,
                    graph=graph or {},
                    vcs_by_cid=vcs_by_cid or {},
                )

            if "technical" in future_map:
                technical_result, technical_summary = future_map["technical"].result()
            if "compliance" in future_map:
                compliance_result = future_map["compliance"].result()
            if "esg" in future_map:
                esg_result = future_map["esg"].result()

        if certification_action is not None:
            certification_result = self.run_certification(
                root_cid=root_cid,
                graph=graph or {},
                vcs_by_cid=vcs_by_cid or {},
                technical_result=technical_result,
            )

        domain_status = self._build_domain_status(
            technical_result=technical_result,
            compliance_result=compliance_result,
            certification_result=certification_result,
            esg_result=esg_result,
        )

        explanation_candidates = self._build_explanation_candidates(
            root_cid=root_cid,
            technical_result=technical_result,
            technical_summary=technical_summary,
            compliance_result=compliance_result,
            certification_result=certification_result,
            esg_result=esg_result,
            domain_status=domain_status,
            graph=graph,
            vcs_by_cid=vcs_by_cid,
        )
        stage2_trace = self._plan_explanation_selection(
            llm_mode=llm_mode,
            root_cid=root_cid,
            candidates=explanation_candidates,
            domain_status=domain_status,
        )
        explanations = self._execute_explanation_selection(stage2_trace.get("selected") or [])
        supply_chain_profile = self._build_supply_chain_profile(graph=graph, vcs_by_cid=vcs_by_cid)
        domain_summaries = self._build_domain_summaries(
            domain_status=domain_status,
            domain_results={
                "technical": technical_result,
                "compliance": compliance_result,
                "certification": certification_result,
                "esg": esg_result,
            },
            explanations=explanations,
            supply_chain_profile=supply_chain_profile,
        )

        result_bundle = {
            "rootCid": root_cid,
            "graph": graph,
            "vcsByCid": vcs_by_cid,
            "nodeIndexByCid": (graph or {}).get("nodeIndexByCid") if isinstance(graph, dict) else None,
            "vcsByCidPresent": vcs_by_cid is not None,
            "supplyChainProfile": supply_chain_profile,
            "technical": technical_result,
            "technical_summary": technical_summary,
            "domainResults": {
                "technical": technical_result,
                "compliance": compliance_result,
                "certification": certification_result,
                "esg": esg_result,
            },
            "explanations": explanations,
            "domainSummaries": domain_summaries,
            "domainStatus": domain_status,
            "claims": (technical_result or {}).get("claims") if isinstance(technical_result, dict) else None,
            "routing_suggestions": routing_suggestions,
            "orchestration_plan": orchestration_plan,
            "validated_actions": validated_actions,
            "planningTrace": {
                "stage1": stage1_trace,
                "stage2": stage2_trace,
            },
        }

        overall_states = [status.get("state") for status in domain_status.values() if isinstance(status, dict)]
        success = bool(overall_states) and all(state == "pass" for state in overall_states)
        return {
            "success": success,
            "result_bundle": result_bundle,
        }

    def _validate_actions(self, actions: List[Dict[str, Any]], *, strict: bool) -> List[Dict[str, Any]]:
        allowed = {
            "build_graph",
            "fetch_vcs_for_graph",
            "run_technical_verification",
            "run_compliance",
            "run_certification",
            "run_esg",
        }
        filtered: List[Dict[str, Any]] = []

        for a in actions:
            tool = a.get("tool")
            if tool not in allowed:
                continue
            opts = a.get("options") if isinstance(a.get("options"), dict) else {}
            opts = {k: v for k, v in opts.items() if v is not None}
            filtered.append({"tool": tool, "options": opts})

        if strict:
            tools = [a["tool"] for a in filtered]
            if "build_graph" not in tools:
                filtered.insert(0, {"tool": "build_graph", "options": {}})
            if "run_technical_verification" not in tools:
                filtered.append({"tool": "run_technical_verification", "options": {}})
            if "run_compliance" not in tools:
                filtered.append({"tool": "run_compliance", "options": {}})
            if "run_certification" not in tools:
                filtered.append({"tool": "run_certification", "options": {}})
            if "run_esg" not in tools:
                filtered.append({"tool": "run_esg", "options": {}})

        # Keeping the execution order stable
        order = {
            "build_graph": 0,
            "fetch_vcs_for_graph": 1,
            "run_technical_verification": 2,
            "run_compliance": 3,
            "run_certification": 4,
            "run_esg": 5,
        }
        filtered.sort(key=lambda x: order.get(x["tool"], 999))
        return filtered

    def _build_explanation_candidates(
        self,
        *,
        root_cid: str,
        technical_result: Optional[Dict[str, Any]],
        technical_summary: Optional[str],
        compliance_result: Optional[Dict[str, Any]],
        certification_result: Optional[Dict[str, Any]],
        esg_result: Optional[Dict[str, Any]],
        domain_status: Dict[str, Dict[str, Any]],
        graph: Optional[Dict[str, Any]],
        vcs_by_cid: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []

        failures = (technical_result or {}).get("failures") or []
        if isinstance(failures, list) and failures:
            candidates.append(
                {
                    "tool": "technical.explain_failures@v1",
                    "input": {
                        "failures": failures,
                        "context": {
                            "rootCid": root_cid,
                            "technicalSummary": technical_summary,
                            "claims": (technical_result or {}).get("claims"),
                            "evidence": (technical_result or {}).get("evidence"),
                        },
                    },
                    "trigger": "technical_failures_present",
                }
            )

        comp_state = (domain_status.get("compliance") or {}).get("state")
        if comp_state in {"fail", "uncertain"} and isinstance(compliance_result, dict):
            candidates.append(
                {
                    "tool": "compliance.explain_findings@v1",
                    "input": {
                        "rootCid": root_cid,
                        "summary": compliance_result.get("summary") or {},
                        "rules": compliance_result.get("rules") or [],
                        "regulations": compliance_result.get("regulations") or [],
                        "nodeResults": compliance_result.get("nodeResults") or [],
                        "graphSummary": {
                            "nodeCount": len((graph or {}).get("nodes") or []),
                            "edgeCount": len((graph or {}).get("edges") or []),
                            "vcCount": len(vcs_by_cid or {}),
                        },
                    },
                    "trigger": "compliance_fail_or_uncertain",
                }
            )

        esg_state = (domain_status.get("esg") or {}).get("state")
        if esg_state in {"fail", "uncertain"} and isinstance(esg_result, dict):
            candidates.append(
                {
                    "tool": "esg.explain_assessment@v1",
                    "input": {
                        "rootCid": root_cid,
                        "scores": esg_result.get("scores") or {},
                        "verdict": esg_result.get("verdict"),
                        "flags": esg_result.get("flags") or [],
                        "findings": esg_result.get("findings") or [],
                        "narrativeSeed": esg_result.get("narrativeSeed") or "",
                        "coverage": (esg_result.get("meta") or {}).get("coverage") or {},
                    },
                    "trigger": "esg_non_pass",
                }
            )

        cert_state = (domain_status.get("certification") or {}).get("state")
        if cert_state in {"fail", "uncertain"} and isinstance(certification_result, dict):
            candidates.append(
                {
                    "tool": "certification.explain_findings@v1",
                    "input": {
                        "rootCid": root_cid,
                        "summary": certification_result.get("summary") or {},
                        "findings": certification_result.get("findings") or [],
                    },
                    "trigger": "certification_fail_or_uncertain",
                }
            )
        return candidates

    def _deterministic_explanation_fallback(
        self,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        selected = []
        skipped = []
        for candidate in candidates:
            selected.append(
                {
                    "tool": candidate.get("tool"),
                    "input": candidate.get("input") or {},
                    "rationale": f"Deterministic trigger: {candidate.get('trigger')}",
                    "confidence": 1.0,
                    "source": "fallback",
                }
            )
        return {
            "candidates": candidates,
            "llmProposal": None,
            "validatedSelection": selected,
            "selected": selected,
            "skipped": skipped,
            "fallbackReason": "deterministic_candidate_policy",
            "validationNotes": ["Used deterministic fallback candidate policy."],
        }

    def _plan_explanation_selection(
        self,
        *,
        llm_mode: str,
        root_cid: str,
        candidates: List[Dict[str, Any]],
        domain_status: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not candidates:
            return {
                "candidates": [],
                "llmProposal": {"selections": [], "notes": "No explanation candidates triggered."},
                "validatedSelection": [],
                "selected": [],
                "skipped": [],
                "fallbackReason": None,
                "validationNotes": ["No stage-2 candidates available."],
            }

        if llm_mode == "off":
            return self._deterministic_explanation_fallback(candidates)

        proposal = None
        try:
            proposal = self._get_llm().plan_explanation_tools(
                root_cid=root_cid,
                candidates=[
                    {"tool": c.get("tool"), "trigger": c.get("trigger")}
                    for c in candidates
                ],
                deterministic_summary={"domainStatus": domain_status},
            )
            validated = self._validate_explanation_selection(
                candidates=candidates,
                selections=proposal.get("selections"),
            )
            return {
                "candidates": candidates,
                "llmProposal": proposal,
                "validatedSelection": validated["validated"],
                "selected": validated["selected"],
                "skipped": validated["skipped"],
                "fallbackReason": None,
                "validationNotes": validated["notes"],
            }
        except Exception as exc:
            fallback = self._deterministic_explanation_fallback(candidates)
            fallback["llmProposal"] = proposal
            fallback["fallbackReason"] = f"llm_plan_invalid: {exc}"
            fallback["validationNotes"] = [f"LLM stage-2 plan invalid; fallback used: {exc}"]
            return fallback

    def _validate_explanation_selection(
        self,
        *,
        candidates: List[Dict[str, Any]],
        selections: Any,
    ) -> Dict[str, Any]:
        if not isinstance(selections, list):
            raise ValueError("selections must be a list")

        candidate_by_tool = {c.get("tool"): c for c in candidates if isinstance(c, dict)}
        allowed_tools = set(candidate_by_tool.keys())
        seen = set()
        validated = []
        selected = []
        skipped = []
        notes = []

        for item in selections:
            if not isinstance(item, dict):
                continue
            tool = item.get("tool")
            if tool not in allowed_tools:
                continue
            if tool in seen:
                continue
            seen.add(tool)

            is_selected = bool(item.get("selected"))
            confidence_raw = item.get("confidence")
            confidence = 0.5
            if isinstance(confidence_raw, (int, float)):
                confidence = max(0.0, min(1.0, float(confidence_raw)))

            validated_item = {
                "tool": tool,
                "input": candidate_by_tool[tool].get("input") or {},
                "selected": is_selected,
                "rationale": str(item.get("rationale") or ""),
                "confidence": confidence,
                "skip_reason": str(item.get("skip_reason") or ""),
                "source": "llm_stage2",
            }
            validated.append(validated_item)
            if is_selected:
                selected.append(validated_item)
            else:
                skipped.append(validated_item)

        # Add the remaining tools as skipped so the trace stays complete.
        missing = [tool for tool in allowed_tools if tool not in seen]
        for tool in missing:
            skipped_item = {
                "tool": tool,
                "input": candidate_by_tool[tool].get("input") or {},
                "selected": False,
                "rationale": "",
                "confidence": None,
                "skip_reason": "missing_from_llm_response",
                "source": "validator",
            }
            validated.append(skipped_item)
            skipped.append(skipped_item)
            notes.append(f"{tool} missing from LLM response; marked skipped.")

        return {"validated": validated, "selected": selected, "skipped": skipped, "notes": notes}

    def _execute_explanation_selection(self, selected: List[Dict[str, Any]]) -> Dict[str, Any]:
        output = {
            "technical": None,
            "compliance": None,
            "esg": None,
            "certification": None,
        }
        for item in selected:
            tool = item.get("tool")
            tool_input = item.get("input") or {}
            try:
                result = self.registry.execute(str(tool), tool_input)
            except Exception as exc:
                result = {"error": f"explanation_tool_failed: {exc}"}

            if tool == "technical.explain_failures@v1":
                output["technical"] = result
            elif tool == "compliance.explain_findings@v1":
                output["compliance"] = result
            elif tool == "esg.explain_assessment@v1":
                output["esg"] = result
            elif tool == "certification.explain_findings@v1":
                output["certification"] = result
        return output

    def _clip_text(self, value: Any, *, default: str = "", limit: int = 220) -> str:
        text = " ".join(str(value or "").strip().split())
        if not text:
            return default
        return text

    def _build_domain_summaries(
        self,
        *,
        domain_status: Dict[str, Dict[str, Any]],
        domain_results: Dict[str, Optional[Dict[str, Any]]],
        explanations: Dict[str, Any],
        supply_chain_profile: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        return {
            "technical": self._build_domain_summary(
                domain="technical",
                status=domain_status.get("technical") or {},
                result=domain_results.get("technical"),
                explanation=explanations.get("technical"),
                supply_chain_profile=supply_chain_profile,
            ),
            "compliance": self._build_domain_summary(
                domain="compliance",
                status=domain_status.get("compliance") or {},
                result=domain_results.get("compliance"),
                explanation=explanations.get("compliance"),
                supply_chain_profile=supply_chain_profile,
            ),
            "certification": self._build_domain_summary(
                domain="certification",
                status=domain_status.get("certification") or {},
                result=domain_results.get("certification"),
                explanation=explanations.get("certification"),
                supply_chain_profile=supply_chain_profile,
            ),
            "esg": self._build_domain_summary(
                domain="esg",
                status=domain_status.get("esg") or {},
                result=domain_results.get("esg"),
                explanation=explanations.get("esg"),
                supply_chain_profile=supply_chain_profile,
            ),
        }

    def _build_domain_summary(
        self,
        *,
        domain: str,
        status: Dict[str, Any],
        result: Optional[Dict[str, Any]],
        explanation: Any,
        supply_chain_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        state = self._domain_summary_state(status)
        fallback_text = self._build_domain_summary_fallback_text(
            domain=domain,
            state=state,
            status=status,
            result=result or {},
            explanation=explanation or {},
        )
        summary_text = None
        source = "deterministic_fallback"
        fallback_reason = None

        if self.config.domain_summary_llm_enabled:
            try:
                summary_text = self._clip_text(
                    self._get_llm().summarize_domain_assessment(
                        domain=domain,
                        supply_chain_profile=supply_chain_profile,
                        domain_status=status or {},
                        domain_result=result or {},
                        explanation=explanation or {},
                    ),
                    default="",
                    limit=520,
                )
                if summary_text:
                    source = "llm_domain_summary"
            except Exception as exc:
                summary_text = None
                fallback_reason = f"llm_summary_failed: {exc}"
        else:
            fallback_reason = "llm_summary_disabled"

        return {
            "domain": domain,
            "state": state,
            "summaryText": summary_text or fallback_text,
            "source": source,
            "fallbackReason": fallback_reason,
        }

    def _domain_summary_state(self, status: Dict[str, Any]) -> str:
        score = status.get("score")
        if isinstance(score, (int, float)):
            if score >= 85:
                return "pass"
            if score >= 55:
                return "uncertain"
            return "fail"

        state = str(status.get("state") or "pending")
        if state == "running":
            return "running"
        return state

    def _build_domain_summary_fallback_text(
        self,
        *,
        domain: str,
        state: str,
        status: Dict[str, Any],
        result: Dict[str, Any],
        explanation: Dict[str, Any],
    ) -> str:
        observations = [x for x in (status.get("observations") or []) if isinstance(x, str)]
        detail = [x for x in (status.get("detail") or []) if isinstance(x, str)]

        if domain == "technical":
            if state == "pass":
                return (
                    "The credential chain passed the technical verification path without recorded deterministic failures. "
                    "Signatures, proofs, anchors, and provenance checks remained consistent across the audited chain."
                )
            diagnoses = [d for d in (explanation.get("diagnoses") or []) if isinstance(d, dict)]
            first_diag = diagnoses[0].get("explanation") if diagnoses else None
            return self._clip_text(
                first_diag or observations[0] if observations else detail[0] if detail else "Technical verification requires review.",
                default="Technical verification requires review.",
                limit=520,
            )

        if domain == "compliance":
            rules = [r for r in (explanation.get("rules") or []) if isinstance(r, dict)]
            first_rule = rules[0].get("llmExplanation") if rules else None
            regulations = [r for r in (result.get("regulations") or []) if isinstance(r, dict)]
            if state == "pass":
                return (
                    "The compliance layer is broadly in range and does not show a material non-conformance in the current audit. "
                    "Any open points are limited observations or evidence gaps rather than a systemic compliance failure."
                )
            if regulations:
                regulation_lines = []
                for regulation in regulations[:3]:
                    short_name = regulation.get("shortName") or regulation.get("id") or "Regulation"
                    message = self._clip_text(regulation.get("message"), default="", limit=180)
                    summary = regulation.get("summary") or {}
                    if not message:
                        failed = int(summary.get("fail", 0) or 0)
                        uncertain = int(summary.get("uncertain", 0) or 0)
                        passed = int(summary.get("pass", 0) or 0)
                        applicable = int(summary.get("applicable", 0) or (passed + failed + uncertain))
                        if failed > 0:
                            message = (
                                f"{failed} of {applicable or failed} applicable checks failed"
                                if applicable
                                else f"{failed} checks failed"
                            )
                        elif uncertain > 0:
                            message = (
                                f"{uncertain} of {applicable or uncertain} applicable checks remain uncertain"
                                if applicable
                                else f"{uncertain} checks remain uncertain"
                            )
                        elif passed > 0:
                            message = "Applicable checks passed."
                        else:
                            message = "Checks require review."
                    regulation_lines.append(f"{short_name}: {message}")
                if regulation_lines:
                    return " ".join(regulation_lines)
            return self._clip_text(
                first_rule or observations[0] if observations else detail[0] if detail else "Compliance evaluation requires review.",
                default="Compliance evaluation requires review.",
                limit=520,
            )

        if domain == "certification":
            findings = [f for f in (explanation.get("findings") or []) if isinstance(f, dict)]
            first_finding = findings[0].get("llmExplanation") if findings else None
            if state == "pass":
                return (
                    "The audited chain retains the required certification coverage without a blocking lapse. "
                    "No certification anomaly in this report currently outweighs the broader passing result."
                )
            return self._clip_text(
                first_finding or observations[0] if observations else detail[0] if detail else "Certification evaluation requires review.",
                default="Certification evaluation requires review.",
                limit=520,
            )

        if state == "pass":
            return (
                "The ESG domain does not show a material breach in the current audit. "
                "The most important takeaway is that the reported sub-scores remain within an acceptable range for this supply chain."
            )
        llm_explanation = explanation.get("llmExplanation") if isinstance(explanation, dict) else None
        return self._clip_text(
            llm_explanation or observations[0] if observations else detail[0] if detail else "ESG evaluation requires review.",
            default="ESG evaluation requires review.",
            limit=520,
        )

    def _build_planning_trace(
        self,
        *,
        available_tools: List[Dict[str, Any]],
        validated_actions: List[Dict[str, Any]],
        orchestration_plan: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        selected_tools = {action.get("tool") for action in validated_actions if isinstance(action, dict)}
        available_tool_names = [
            tool.get("name")
            for tool in available_tools
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        ]

        llm_rationale = {}
        if isinstance(orchestration_plan, dict) and isinstance(orchestration_plan.get("toolRationale"), dict):
            llm_rationale = orchestration_plan.get("toolRationale") or {}

        selected: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        for tool_name in available_tool_names:
            rationale = llm_rationale.get(tool_name) if isinstance(llm_rationale, dict) else None
            rationale_text = rationale.get("rationale") if isinstance(rationale, dict) else None
            confidence = rationale.get("confidence") if isinstance(rationale, dict) else None
            item = {
                "tool": tool_name,
                "rationale": rationale_text or "No LLM rationale provided.",
                "confidence": confidence if isinstance(confidence, (int, float)) else None,
            }
            if tool_name in selected_tools:
                selected.append(item)
            else:
                skipped.append(item)

        return {
            "selected": selected,
            "skipped": skipped,
        }

    def _build_domain_status(
        self,
        *,
        technical_result: Optional[Dict[str, Any]],
        compliance_result: Optional[Dict[str, Any]],
        certification_result: Optional[Dict[str, Any]],
        esg_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        def score_from_state_and_ratio(
            *,
            state: str,
            passed: int,
            uncertain: int,
            failed: int,
            total: int,
        ) -> int:
            if total <= 0:
                return 0
            if failed == 0 and uncertain == 0 and passed == total:
                return 100

            raw = int(round(((passed + 0.35 * uncertain) / total) * 100))
            if state == "fail":
                return max(0, min(49, raw))
            if state == "uncertain":
                return max(55, min(79, raw))
            return max(80, min(100, raw))

        def result_to_status(name: str, result: Optional[Dict[str, Any]], *, source: str) -> Dict[str, Any]:
            if not isinstance(result, dict):
                return {"state": "pending", "detail": [f"{name} tool not executed"], "source": source}
            raw = str(result.get("status") or "pending").lower()
            if raw in {"pending", "running"}:
                state = "pending"
            else:
                success = result.get("success")
                if success is True:
                    state = "pass"
                elif success is False:
                    state = "fail"
                else:
                    state = "uncertain"
            detail = []
            if isinstance(result.get("summary"), dict):
                s = result["summary"]
                detail.append(f"pass={s.get('pass', 0)} fail={s.get('fail', 0)} uncertain={s.get('uncertain', 0)}")
            else:
                detail.append(str(result.get("message") or "Not yet implemented"))
            return {"state": state, "detail": detail, "source": source}

        def build_technical_status(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            if not isinstance(result, dict):
                return {"state": "pending", "detail": ["Verification in progress"], "source": "deterministic"}

            success = result.get("success") is True
            failures = [f for f in (result.get("failures") or []) if isinstance(f, dict)]
            failure_codes = [f.get("code") for f in failures if f.get("code")]
            step_status = ((result.get("evidence") or {}).get("stepStatus") or {})
            failed_steps = [
                {
                    "key": key,
                    "label": step.get("label") or key,
                    "detail": step.get("detail"),
                }
                for key, step in step_status.items()
                if isinstance(step, dict) and step.get("status") == "failed"
            ]

            if success:
                score = 100
                detail = ["All checks passed"]
            else:
                # Each recorded failure reduces the score
                score = max(0, 100 - len(failures) * 12)
                detail = failure_codes[:6] if failure_codes else ["Verification failed"]

            observations = []
            for step in failed_steps[:10]:
                line = f"{step['label']}"
                if step.get("detail"):
                    line += f": {step['detail']}"
                observations.append(line)

            return {
                "state": "pass" if success else "fail",
                "detail": detail,
                "source": "deterministic",
                "score": score,
                "findings": len(failures),
                "observations": observations,
            }

        def build_compliance_status(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            base = result_to_status("Compliance", result, source="deterministic")
            if not isinstance(result, dict):
                return base

            summary = result.get("summary") or {}
            rules = [rule for rule in (result.get("rules") or []) if isinstance(rule, dict)]
            regulations = [
                regulation for regulation in (result.get("regulations") or []) if isinstance(regulation, dict)
            ]
            passed = int(summary.get("pass", 0))
            failed = int(summary.get("fail", 0))
            uncertain = int(summary.get("uncertain", 0))
            not_applicable = int(summary.get("not_applicable", 0))
            total = passed + failed + uncertain + not_applicable

            base["score"] = score_from_state_and_ratio(
                state=base["state"],
                passed=passed,
                uncertain=uncertain,
                failed=failed,
                total=total,
            )
            base["findings"] = failed + uncertain

            articles = []
            for rule in rules:
                article_label = rule.get("articleRef") or rule.get("id")
                if rule.get("paragraphRef"):
                    article_label = f"{article_label} {rule.get('paragraphRef')}"
                articles.append(
                    {
                        "id": article_label,
                        "title": rule.get("title"),
                        "status": rule.get("status"),
                        "detail": rule.get("reason"),
                    }
                )
            base["articles"] = articles
            base["summary"] = {
                "pass": passed,
                "fail": failed,
                "uncertain": uncertain,
                "not_applicable": not_applicable,
                "applicable": passed + failed + uncertain,
                "total": total,
            }
            base["coverage"] = result.get("coverage") or {}
            base["nodeResults"] = result.get("nodeResults") or []

            grouped_regulations = []
            for regulation in regulations:
                regulation_meta = regulation.get("regulation") or {}
                grouped_chapters = []
                for chapter in regulation.get("chapters") or []:
                    if not isinstance(chapter, dict):
                        continue
                    grouped_rules = []
                    for rule in chapter.get("rules") or []:
                        if not isinstance(rule, dict):
                            continue
                        grouped_rules.append(
                            {
                                "id": rule.get("id"),
                                "articleRef": rule.get("articleRef"),
                                "paragraphRef": rule.get("paragraphRef"),
                                "title": rule.get("title"),
                                "status": rule.get("status"),
                                "reason": rule.get("reason"),
                                "encodable": rule.get("encodable"),
                                "encodabilityReason": rule.get("encodabilityReason"),
                                "evidencePointers": rule.get("evidencePointers") or [],
                                "escalation": rule.get("escalation"),
                            }
                        )
                    grouped_chapters.append(
                        {
                            "id": chapter.get("id"),
                            "title": chapter.get("title"),
                            "status": chapter.get("status"),
                            "applicable": chapter.get("applicable"),
                            "applicabilityExplanation": chapter.get("applicabilityExplanation"),
                            "summary": chapter.get("summary") or {},
                            "coverage": chapter.get("coverage") or {},
                            "rules": grouped_rules,
                        }
                    )
                grouped_regulations.append(
                    {
                        "id": regulation_meta.get("id"),
                        "shortName": regulation_meta.get("shortName"),
                        "title": regulation_meta.get("title"),
                        "status": regulation.get("status"),
                        "applicable": regulation.get("applicable"),
                        "applicabilityExplanation": regulation.get("applicabilityExplanation"),
                        "message": regulation.get("message"),
                        "summary": regulation.get("summary") or {},
                        "coverage": regulation.get("coverage") or {},
                        "chapters": grouped_chapters,
                    }
                )
            base["regulations"] = grouped_regulations
            base["regulationCount"] = len(grouped_regulations)

            failed_rules = [rule for rule in rules if rule.get("status") == "fail"]
            uncertain_rules = [rule for rule in rules if rule.get("status") == "uncertain"]
            regulation_lines = []
            if grouped_regulations:
                regulation_lines.append(
                    f"{len(grouped_regulations)} regulation{'s' if len(grouped_regulations) != 1 else ''} evaluated"
                )
            if passed + failed + uncertain:
                regulation_lines.append(
                    f"{passed + failed + uncertain} applicable rule{'s' if (passed + failed + uncertain) != 1 else ''}"
                )
            if failed:
                regulation_lines.append(f"{failed} failed rule{'s' if failed != 1 else ''}")
            if uncertain:
                regulation_lines.append(f"{uncertain} uncertain rule{'s' if uncertain != 1 else ''}")
            if not_applicable:
                regulation_lines.append(
                    f"{not_applicable} not-applicable rule{'s' if not_applicable != 1 else ''}"
                )

            regulation_findings = [
                f"{regulation.get('shortName') or regulation.get('id')}: {regulation.get('message')}"
                for regulation in grouped_regulations
                if regulation.get("status") in {"fail", "uncertain", "not_applicable"}
            ]
            rule_findings = [
                f"{(rule.get('articleRef') or rule.get('id'))} — {rule.get('title')}: {rule.get('reason')}"
                for rule in (failed_rules[:5] + uncertain_rules[:5])
                if rule.get("reason")
            ]
            base["detail"] = regulation_lines or [
                f"{(rule.get('articleRef') or rule.get('id'))}: {rule.get('reason')}"
                for rule in (failed_rules[:2] + uncertain_rules[:1])
                if rule.get("reason")
            ] or base.get("detail")
            base["observations"] = regulation_findings[:4] + rule_findings[:6]
            base["actions"] = [
                {
                    "text": f"Resolve {rule.get('articleRef') or rule.get('id')} — {rule.get('title')}: {rule.get('reason')}",
                    "deadline": None,
                }
                for rule in failed_rules[:5]
                if rule.get("reason")
            ]
            return base

        def build_certification_status(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            base = result_to_status("Certification", result, source="deterministic")
            if not isinstance(result, dict):
                return base
            findings = result.get("findings") or []
            certifications = []
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                passed_cids = [str(cid) for cid in (finding.get("passedCids") or []) if cid]
                applicable_cids = [str(cid) for cid in (finding.get("applicableCids") or []) if cid]
                primary_cid = passed_cids[0] if passed_cids else (finding.get("cid") if finding.get("cid") else None)
                certifications.append(
                    {
                        "name": finding.get("displayName") or finding.get("certificationId"),
                        "title": primary_cid,
                        "status": finding.get("status") if finding.get("status") != "not_applicable" else "info",
                        "detail": finding.get("reason"),
                        "certificationId": finding.get("certificationId"),
                        "passingCids": passed_cids,
                        "applicableCids": applicable_cids,
                        "passingNodeCount": finding.get("passingNodeCount", len(passed_cids)),
                        "applicableNodeCount": finding.get("applicableNodeCount", len(applicable_cids)),
                        "matchedNodeCount": finding.get("matchedNodeCount", 0),
                        "failureType": finding.get("failureType"),
                        "warnings": [str(item) for item in (finding.get("warnings") or []) if item],
                    }
                )
            if "summary" in result and isinstance(result["summary"], dict):
                summary = result["summary"]
                passed = int(summary.get("pass", 0))
                failed = int(summary.get("fail", 0))
                uncertain = int(summary.get("uncertain", 0))
                not_applicable = int(summary.get("not_applicable", 0))
                total = len(certifications) or (passed + failed + uncertain + int(summary.get("not_applicable", 0)))
                base["score"] = int(round((passed / total) * 100)) if total > 0 else 0
                base["findings"] = failed + uncertain
                base["summary"] = {
                    "pass": passed,
                    "fail": failed,
                    "uncertain": uncertain,
                    "not_applicable": not_applicable,
                    "applicable": passed + failed + uncertain,
                    "total": total,
                }
                base["detail"] = [f"{passed} of {total} certifications validated across the supply chain"]
                base["observations"] = [
                    f"{item['name']}: {item['detail']}"
                    for item in certifications
                    if item.get("status") in {"fail", "uncertain"}
                ][:7]
                base["actions"] = [
                    {
                        "text": f"Review {item['name']}: {item['detail']}",
                        "deadline": None,
                    }
                    for item in certifications
                    if item.get("status") in {"fail", "uncertain"}
                ][:7]
            base["nodeResults"] = result.get("nodeResults") or []
            base["certifications"] = certifications[:7]
            return base

        def build_esg_status(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            base = result_to_status("ESG", result, source="deterministic")
            if not isinstance(result, dict):
                return base
            ui = result.get("ui") or {}
            base["score"] = ui.get("score")
            base["findings"] = ui.get("findings", len(result.get("findings") or []))
            base["detail"] = ui.get("detail") or base.get("detail")
            base["observations"] = ui.get("observations") or []
            base["actions"] = [x for x in (ui.get("actions") or []) if isinstance(x, dict)]
            base["breakdown"] = ui.get("breakdown") or {}
            base["items"] = ui.get("items") or []
            base["flags"] = result.get("flags") or []
            base["verdict"] = result.get("verdict")
            base["acled"] = ui.get("acled") or {}
            base["coverage"] = (result.get("meta") or {}).get("coverage") or {}
            base["confidence"] = (result.get("meta") or {}).get("confidence")
            return base

        return {
            "technical": build_technical_status(technical_result),
            "compliance": build_compliance_status(compliance_result),
            "certification": build_certification_status(certification_result),
            "esg": build_esg_status(esg_result),
        }


def _parse_gateways_env(value: str) -> List[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def _resolve_rpc_url(explicit: Optional[str] = None) -> Optional[str]:
    return (
        explicit
        or os.getenv("RPC_HTTPS_URL")
        or os.getenv("RPC_URL")
        or os.getenv("RPC_WSS_URL")
    )


def create_orchestrator_from_env() -> Orchestrator:
    ipfs_cfg = default_ipfs_config()

    gateways = os.getenv("IPFS_GATEWAYS")
    ipfs_cfg = IpfsFetchConfig(
        gateways=_parse_gateways_env(gateways) if gateways else list(ipfs_cfg.gateways),
        timeout_s=float(os.getenv("IPFS_TIMEOUT_S", str(ipfs_cfg.timeout_s))),
        retries=int(os.getenv("IPFS_RETRIES", str(ipfs_cfg.retries))),
        backoff_s=float(os.getenv("IPFS_BACKOFF_S", str(ipfs_cfg.backoff_s))),
        jitter_s=float(os.getenv("IPFS_JITTER_S", str(ipfs_cfg.jitter_s))),
    )

    cfg = OrchestratorConfig(
        max_nodes=int(os.getenv("PROVENANCE_MAX_NODES", "50")),
        ipfs=ipfs_cfg,
        llm_mode=os.getenv("ORCH_LLM_MODE", "plan_and_route"),
        llm_strict=os.getenv("ORCH_LLM_STRICT", "1") != "0",
        domain_summary_llm_enabled=os.getenv("DOMAIN_SUMMARY_LLM", "1").strip().lower() not in {"0", "false", "no", "off"},
    )
    return Orchestrator(cfg)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m backend.agents.orchestrator.orchestrator <rootCid-or-prompt>")

    arg = sys.argv[1]
    orch = create_orchestrator_from_env()
    out = orch.run({"userPrompt": arg, "rootCid": arg if arg.startswith(("Qm", "bafy")) else None})
    print(out.get("result_bundle", {}).get("technical_summary") or "")
    print("success =", out.get("success"))
