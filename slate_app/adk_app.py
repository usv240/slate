from __future__ import annotations

import os

from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.apps import App

from .grafana_mcp import query_loki, query_prometheus, query_tempo


MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

watch = LlmAgent(
    name="Watch",
    model=MODEL,
    instruction="Read the deterministic jeopardy gate and use query_prometheus through Grafana MCP. Report whether sustained burn evidence exists. Do not diagnose and do not create a verdict.",
    tools=[query_prometheus],
    output_key="watch_evidence",
)

diagnose = LlmAgent(
    name="Diagnose",
    model=MODEL,
    instruction="Using {watch_evidence}, correlate real Loki logs and Tempo traces through Grafana MCP. Classify codec fault, poison input, timeout, capacity starvation, or QC rule change. Every claim must name the MCP result that supports it.",
    tools=[query_loki, query_tempo],
    output_key="diagnosis",
)

remediate = LlmAgent(
    name="Remediate",
    model=MODEL,
    instruction="Using {watch_evidence} and {diagnosis}, propose three options with estimated schedule cost. Never execute, scale, requeue, annotate, or change a deadline. A delivery supervisor owns the decision.",
    output_key="remediation_options",
)

root_agent = SequentialAgent(name="SlateDeliverySupervisor", sub_agents=[watch, diagnose, remediate])
app = App(root_agent=root_agent, name="slate")
