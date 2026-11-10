
"""Deterministic mock LLM for offline testing."""

from __future__ import annotations

from difflib import get_close_matches
import re

from backend.llm.base import (
    LLMClarificationRequiredError,
    LLMParseError,
    LLMProvider,
)
from backend.models.intent import (
    Constraints,
    LossTolerance,
    Metric,
    MetricConstraint,
    MetricUnit,
    Objective,
    Operator,
    StructuredIntent,
    Target,
)
from backend.models.canonical_intent import Comparison

_HOST_RE = r"([a-zA-Z][\w-]*)"

_ENDPOINT_RE = re.compile(
    rf"\bbetween\s+{_HOST_RE}\s+and\s+{_HOST_RE}\b"
    rf"|\bfrom\s+{_HOST_RE}\s+to\s+{_HOST_RE}\b"
    rf"|\bgive\s+{_HOST_RE}\s+to\s+{_HOST_RE}\b",
    re.IGNORECASE,
)

_EXPLICIT_COMPARISON_RE = re.compile(
    r"\b(?P<metric>packet[\s_-]+loss|latency|bandwidth)\s*"
    r"(?P<comparison><=|>=|<|>)\s*(?P<value>[\d.]+)\s*"
    r"(?P<unit>mbps|ms|%)",
    re.IGNORECASE,
)
_TEXT_COMPARISON_RE = re.compile(
    r"\b(?P<metric>packet[\s_-]+loss|latency|bandwidth|throughput|delay)\b"
    r"(?:(?!\b(?:packet[\s_-]+loss|latency|bandwidth|throughput|delay)\b)"
    r"[\w\s'-]){0,48}?"
    r"(?P<comparison>less than or equal to|greater than or equal to|"
    r"no less than|no more than|less than|greater than|at least|at most|"
    r"above|over|more than|minimum|below|under|exactly|equal to)\s*"
    r"(?P<value>[\d.]+)\s*"
    r"(?P<unit>mbps|ms|%|percent)?",
    re.IGNORECASE,
)
_REVERSE_BANDWIDTH_RE = re.compile(
    r"\b(?:(?P<comparison>less than or equal to|greater than or equal to|"
    r"no less than|no more than|less than|greater than|at least|at most|"
    r"above|over|more than|below|under)\s+)?"
    r"(?P<value>[\d.]+)\s*mbps\s*(?:or\s+)?"
    r"(?P<suffix_comparison>or more|or higher|or above|or less|or lower)?"
    r"(?:\s+(?:of\s+)?(?:the\s+)?(?:bandwidth|throughput|capacity))?\b",
    re.IGNORECASE,
)

_LOSS_TOLERANCE_RE = re.compile(
    r"tolerate\s+(some|high|low|medium)\s+packet\s+loss",
    re.IGNORECASE,
)

_METRIC_PATTERNS = [
    (
        Metric.BANDWIDTH,
        MetricUnit.MBPS,
        re.compile(
            r"bandwidth\s+between\s+([\d.]+)\s+and\s+([\d.]+)\s*mbps",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:at\s+least|minimum|min)\s+([\d.]+)\s*mbps",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:at\s+most|maximum|max|no\s+more\s+than)\s+([\d.]+)\s*mbps",
            re.IGNORECASE,
        ),
        re.compile(r"(?:maximize|highest)\s+(?:the\s+)?bandwidth", re.IGNORECASE),
        re.compile(r"(?:minimize|lowest)\s+(?:the\s+)?bandwidth", re.IGNORECASE),
    ),
    (
        Metric.LATENCY,
        MetricUnit.MS,
        re.compile(
            r"latency\s+between\s+([\d.]+)\s+and\s+([\d.]+)\s*ms",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:at\s+least|minimum|min)\s+([\d.]+)\s*ms",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:at\s+most|maximum|max|no\s+more\s+than)\s+([\d.]+)\s*ms",
            re.IGNORECASE,
        ),
        re.compile(r"(?:maximize|highest)\s+(?:the\s+)?latency", re.IGNORECASE),
        re.compile(r"(?:minimize|lowest)\s+(?:the\s+)?latency|lowest[\s-]latency", re.IGNORECASE),
    ),
    (
        Metric.JITTER,
        MetricUnit.MS,
        re.compile(
            r"jitter\s+between\s+([\d.]+)\s+and\s+([\d.]+)\s*ms",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:at\s+least|minimum|min)\s+([\d.]+)\s*ms\s+jitter",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:at\s+most|maximum|max|no\s+more\s+than)\s+([\d.]+)\s*ms\s+jitter",
            re.IGNORECASE,
        ),
        re.compile(r"maximize\s+(?:the\s+)?jitter", re.IGNORECASE),
        re.compile(r"minimize\s+(?:the\s+)?jitter", re.IGNORECASE),
    ),
    (
        Metric.PACKET_LOSS,
        MetricUnit.PERCENT,
        re.compile(
            r"packet\s+loss\s+between\s+([\d.]+)\s+and\s+([\d.]+)\s*%",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:at\s+least|minimum|min)\s+([\d.]+)\s*%\s+packet\s+loss",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:at\s+most|maximum|max|no\s+more\s+than)\s+([\d.]+)\s*%\s+packet\s+loss",
            re.IGNORECASE,
        ),
        re.compile(r"maximize\s+(?:the\s+)?packet\s+loss", re.IGNORECASE),
        re.compile(r"minimize\s+(?:the\s+)?packet\s+loss", re.IGNORECASE),
    ),
    (
        Metric.AVAILABILITY,
        MetricUnit.PERCENT,
        re.compile(
            r"availability\s+between\s+([\d.]+)\s+and\s+([\d.]+)\s*%",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:at\s+least|minimum|min)\s+([\d.]+)\s*%\s+availability",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:at\s+most|maximum|max|no\s+more\s+than)\s+([\d.]+)\s*%\s+availability",
            re.IGNORECASE,
        ),
        re.compile(r"maximize\s+(?:the\s+)?availability", re.IGNORECASE),
        re.compile(r"minimize\s+(?:the\s+)?availability", re.IGNORECASE),
    ),
]

_SPELLINGS = {
    "fastest", "route", "from", "between", "latency", "bandwidth",
    "throughput", "delay", "packet", "loss", "minimize", "maximize",
    "minimum", "maximum", "least", "quickest", "shortest", "support",
    "provide", "maintain", "ensure", "traffic", "hosts",
}


class MockLLM(LLMProvider):

    @property
    def name(self) -> str:
        return "mock"

    def parse_intent(
        self,
        natural_language: str,
        *,
        source: str | None = None,
        destination: str | None = None,
    ) -> StructuredIntent:

        text = _normalize_request(natural_language.strip())

        if not text:
            raise LLMParseError("Natural-language intent cannot be empty")

        # The offline provider is deliberately conservative; unlike a configured
        # semantic model, it can only interpret its documented vocabulary.
        endpoints = self._extract_endpoints(text)

        if endpoints is None and source is not None and destination is not None:
            endpoints = (source, destination)

        if endpoints is None:
            raise LLMParseError(
                "Could not identify source and destination hosts."
            )

        source, destination = endpoints

        try:
            metrics = self._extract_metrics(text)
            metrics.extend(self._extract_objectives(text, metrics))
            objective = None
            target = None

            for metric in metrics[:]:
                if (
                    metric.metric == Metric.LATENCY
                    and metric.optimization == Operator.MINIMIZE
                    and re.search(
                        r"\b(?:minimi[sz]e|lowest|least|fastest|quickest)\b",
                        text,
                        re.I,
                    )
                ):
                    objective = Objective.MINIMIZE_LATENCY
                    metrics.remove(metric)
                    break

            legacy_bandwidth = re.search(
                r"\bprovide\s+at\s+least\s+([\d.]+)\s*mbps\b",
                text,
                re.I,
            )
            if legacy_bandwidth:
                target = Target(
                    bandwidth_mbps=float(legacy_bandwidth.group(1))
                )
                objective = Objective.MIN_BANDWIDTH
                metrics = [
                    metric
                    for metric in metrics
                    if metric.metric != Metric.BANDWIDTH
                ]

            if not metrics and objective is None:
                if re.search(r"\b(faster|fast|better|improve|optimi[sz]e)\b", text, re.I):
                    raise LLMClarificationRequiredError(
                        "Do you mean lower latency, higher bandwidth, or another network metric?"
                    )
                if re.search(r"\b(another|other)\s+(?:route|path)\b", text, re.I):
                    raise LLMClarificationRequiredError(
                        "Which previous route should be avoided? No prior route context was provided."
                    )
                raise LLMParseError(
                    "Mock parser could not identify a supported metric or constraint. "
                    "Select a configured LLM provider for broader language understanding."
                )

            return StructuredIntent(
                objective=objective,
                source=source,
                destination=destination,
                target=target,
                constraints=Constraints(
                    metrics=metrics,
                    loss_tolerance=self._extract_loss_tolerance(text),
                ),
            )

        except LLMParseError:
            raise

        except Exception as exc:
            raise LLMParseError(str(exc)) from exc

    @staticmethod
    def _extract_endpoints(text: str) -> tuple[str, str] | None:

        match = _ENDPOINT_RE.search(text)

        if not match:
            return None

        groups = match.groups()

        if groups[0] is not None:
            return groups[0], groups[1]

        if groups[2] is not None:
            return groups[2], groups[3]

        return groups[4], groups[5]

    @staticmethod
    def _extract_metrics(text: str) -> list[MetricConstraint]:

        metrics = []
        explicit_metrics = set()

        comparison_map = {
            "<": Comparison.LT,
            "<=": Comparison.LTE,
            ">": Comparison.GT,
            ">=": Comparison.GTE,
            "below": Comparison.LT,
            "under": Comparison.LT,
            "less than": Comparison.LT,
            "less than or equal to": Comparison.LTE,
            "greater than": Comparison.GT,
            "greater than or equal to": Comparison.GTE,
            "at most": Comparison.LTE,
            "no more than": Comparison.LTE,
            "above": Comparison.GT,
            "over": Comparison.GT,
            "more than": Comparison.GT,
            "at least": Comparison.GTE,
            "no less than": Comparison.GTE,
            "minimum": Comparison.GTE,
            "or more": Comparison.GTE,
            "or higher": Comparison.GTE,
            "or above": Comparison.GTE,
            "or less": Comparison.LTE,
            "or lower": Comparison.LTE,
            "exactly": Comparison.EQ,
            "equal to": Comparison.EQ,
        }
        metric_map = {
            "latency": Metric.LATENCY,
            "delay": Metric.LATENCY,
            "bandwidth": Metric.BANDWIDTH,
            "throughput": Metric.BANDWIDTH,
            "packet loss": Metric.PACKET_LOSS,
            "packet_loss": Metric.PACKET_LOSS,
            "packet-loss": Metric.PACKET_LOSS,
        }
        unit_map = {
            Metric.LATENCY: MetricUnit.MS,
            Metric.BANDWIDTH: MetricUnit.MBPS,
            Metric.PACKET_LOSS: MetricUnit.PERCENT,
        }
        explicit_matches = (
            list(_EXPLICIT_COMPARISON_RE.finditer(text))
            + list(_TEXT_COMPARISON_RE.finditer(text))
        )
        for match in explicit_matches:
            metric_name = re.sub(r"[\s_-]+", " ", match.group("metric").lower())
            metric = metric_map[metric_name]
            unit_value = match.group("unit")
            if (
                unit_value
                and unit_value.lower() not in {
                    unit_map[metric].value.lower(),
                    "percent" if metric == Metric.PACKET_LOSS else "",
                }
            ):
                continue
            metrics.append(
                MetricConstraint(
                    metric=metric,
                    unit=unit_map[metric],
                    comparison=comparison_map[
                        match.group("comparison").lower()
                    ],
                    value=float(match.group("value")),
                )
            )
            explicit_metrics.add(metric)

        for match in _REVERSE_BANDWIDTH_RE.finditer(text):
            if Metric.BANDWIDTH in explicit_metrics:
                continue
            comparison_text = (
                match.group("comparison") or match.group("suffix_comparison")
            )
            if comparison_text is None:
                continue
            comparison = comparison_map[comparison_text.lower()]
            metrics.append(
                MetricConstraint(
                    metric=Metric.BANDWIDTH,
                    unit=MetricUnit.MBPS,
                    comparison=comparison,
                    value=float(match.group("value")),
                )
            )
            explicit_metrics.add(Metric.BANDWIDTH)

        for (
            metric,
            unit,
            range_re,
            minimum_re,
            maximum_re,
            maximize_re,
            minimize_re,
        ) in _METRIC_PATTERNS:
            if metric in explicit_metrics:
                continue

            range_match = range_re.search(text)

            if range_match:
                lower, upper = map(float, range_match.groups())

                metrics.append(
                    MetricConstraint(
                        metric=metric,
                        unit=unit,
                        min_value=lower,
                        max_value=upper,
                    )
                )
                continue

            minimum_match = minimum_re.search(text)
            maximum_match = maximum_re.search(text)

            min_value = (
                float(minimum_match.group(1))
                if minimum_match else None
            )

            max_value = (
                float(maximum_match.group(1))
                if maximum_match else None
            )

            if min_value is not None or max_value is not None:
                metrics.append(
                    MetricConstraint(
                        metric=metric,
                        unit=unit,
                        min_value=min_value,
                        max_value=max_value,
                    )
                )
                continue

            if maximize_re.search(text):
                metrics.append(
                    MetricConstraint(
                        metric=metric,
                        unit=unit,
                        optimization=Operator.MAXIMIZE,
                    )
                )
                continue

            if minimize_re.search(text):
                metrics.append(
                    MetricConstraint(
                        metric=metric,
                        unit=unit,
                        optimization=Operator.MINIMIZE,
                    )
                )

        return metrics

    @staticmethod
    def _extract_loss_tolerance(text: str) -> LossTolerance | None:
        match = _LOSS_TOLERANCE_RE.search(text)
        if not match:
            return None
        level = match.group(1).upper()
        return LossTolerance("MEDIUM" if level == "SOME" else level)

    @staticmethod
    def _extract_objectives(
        text: str,
        existing: list[MetricConstraint],
    ) -> list[MetricConstraint]:
        existing_optimizations = {
            constraint.metric
            for constraint in existing
            if constraint.optimization is not None
        }
        objectives: list[MetricConstraint] = []
        patterns = (
            (
                Metric.LATENCY,
                MetricUnit.MS,
                Operator.MINIMIZE,
                r"\bminimi[sz]e\s+(?:the\s+)?(?:latency|delay)\b|"
                r"\blowest[\s-]+latency\b|\bleast\s+possible\s+delay\b|"
                r"\b(?:fastest|quickest|shortest)\s+(?:route|path)\b",
            ),
            (
                Metric.BANDWIDTH,
                MetricUnit.MBPS,
                Operator.MAXIMIZE,
                r"\b(?:maximi[sz]e|highest|greatest)\b.{0,45}"
                r"\b(?:bandwidth|throughput|capacity)\b",
            ),
            (
                Metric.PACKET_LOSS,
                MetricUnit.PERCENT,
                Operator.MINIMIZE,
                r"\b(?:minimi[sz]e|lowest|least)\s+(?:the\s+)?"
                r"packet[\s_-]+loss\b",
            ),
        )
        for metric, unit, direction, pattern in patterns:
            if metric in existing_optimizations or re.search(pattern, text, re.I):
                if re.search(pattern, text, re.I) and metric not in existing_optimizations:
                    objectives.append(
                        MetricConstraint(
                            metric=metric,
                            unit=unit,
                            optimization=direction,
                        )
                    )
        return objectives

def _normalize_request(text: str) -> str:
    corrections = {
        "fastes": "fastest",
        "fastest": "fastest",
        "rout": "route",
        "frm": "from",
        "latncy": "latency",
        "bandwith": "bandwidth",
        "througput": "throughput",
    }

    def correct(match: re.Match[str]) -> str:
        token = match.group(0)
        lower = token.lower()
        correction = corrections.get(lower)
        if correction is None and len(lower) >= 4:
            correction = next(
                iter(get_close_matches(lower, _SPELLINGS, n=1, cutoff=0.82)),
                None,
            )
        if correction is None:
            return token
        return correction.capitalize() if token[0].isupper() else correction

    normalized = re.sub(r"[A-Za-z]+", correct, text)
    normalized = re.sub(r"\bthroughput\b", "bandwidth", normalized, flags=re.I)
    normalized = re.sub(r"\bdelay\b", "latency", normalized, flags=re.I)
    return normalized
