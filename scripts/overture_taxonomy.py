"""Conservative, explainable labels for the overture catalogue.

The primary type describes the kind of request. Instrument and topic are
separate facets; BCO amendment progress describes process, not disposition.
"""
from __future__ import annotations

import re


def classify(title: str, outcome: str = "", bco_stage_override: str = "") -> dict[str, str]:
    text = re.sub(r"\s+", " ", title).strip()
    low = text.lower()
    process_text = f"{title} {outcome}"
    instrument_patterns = [
        (r"\bbook of church order\b|\bBCO\b", "BCO"),
        (r"\bRAO\b|\brules of assembly operations\b", "RAO"),
        (r"\bwestminster confession\b|\bwestminster standards\b|\blarger catechism\b|\bshorter catechism\b", "Westminster Standards"),
        (r"\bdirectory of worship\b", "Directory for Worship"),
        (r"\bmanual\b|\bstanding rules\b", "GA manual or rules"),
    ]
    mentions = [(match.start(), label) for pattern, label in instrument_patterns
                if (match := re.search(pattern, text, re.I))]
    instrument = min(mentions)[1] if mentions else ""

    explicit_amendment = re.search(r"\b(amend|amending|amendment)\b", low)
    instrument_change = instrument and re.search(
        r"\b(revise|revision|change|strike|suspend|insert|delete|add|replace|modify|clarify|restore)\b"
        r"|\bprovide\b.{0,50}\b(in|to)\b",
        low,
    )
    boundary_request = (
        re.search(r"\b(boundar|dissolv|erect|organize|reorganize|merge|divide|form|transfer|expand|adjust)\w*\b", low)
        and re.search(r"presbyter|county|counties|geographic", low)
    )
    study_request = re.search(r"\b(study|investigat|explor)\w*\b", low) or re.search(
        r"\b(appoint|erect|establish|form|create|request)\b.{0,70}\bcommittee\b", low
    ) or re.search(r"\bad interim committee\b", low)
    if explicit_amendment:
        kind = "Amendment"
    elif boundary_request:
        kind = "Presbytery structure or boundary"
    elif study_request:
        kind = "Study or committee request"
    elif instrument_change:
        kind = "Amendment"
    elif re.search(r"\b(complaint|appeal|judicial|reference)\b", low):
        kind = "Judicial review or redress"
    elif re.search(r"\b(statement|declaration|position paper|pastoral letter|testimony|policy|affirm|reaffirm|commend|protest|oppose|petition|discourage|encourage|urge|promote|express thanks)\b", low):
        kind = "Statement or policy request"
    elif re.search(r"\b(direct|instruct|authorize|appoint|commission|send|request|allow|adopt|assign|convert|continue|call|launch|limit|invite|increase|prohibit|decline|prepare|replace|require|retain|provide|remove|permit|make|pool|review|reconsider|revise|return|acknowledge|discontinue|grant|demand|keep|rule)\w*\b", low):
        kind = "Direct action request"
    else:
        kind = "Other or unclear request"

    if kind == "Amendment" and instrument == "BCO":
        if re.search(r"\bnot ratified\b|\bconcurrence was not received\b|\bfailed to receive.{0,80}presbyter", process_text, re.I):
            stage = "Not ratified"
        elif (re.search(r"\b(two-thirds|2/3).{0,100}\bpresbyter", process_text, re.I)
                or re.search(r"\b(enacted|ratified|final approval|final adoption)\b", process_text, re.I)):
            stage = "Ratification or enactment recorded"
        elif re.search(r"\bamendments?\b.{0,60}\bnot sent (?:down )?(?:to presbyteries|for ratification)?\b|\bnot sent (?:down )?for ratification\b", process_text, re.I):
            stage = "Not sent down for ratification"
        elif re.search(r"\b(advice and consent|approved by.{0,40}presbyter|sent (?:down )?to.{0,40}presbyter|presbyter.{0,40}(approve|ratif))", process_text, re.I):
            stage = "Presbytery review recorded"
        elif re.search(r"\b(adopted|approved|recommended)\b", process_text, re.I):
            stage = "GA action recorded; presbytery stage unclear"
        else:
            stage = "BCO amendment; stage unclear"
    else:
        stage = "—"
    if bco_stage_override:
        stage = bco_stage_override

    topics = []
    topic_rules = [
        (r"presbyter", "Presbytery"), (r"ordination|ordain|minister|elder|deacon", "Church office"),
        (r"worship|sacrament|baptis|communion", "Worship and sacraments"),
        (r"mission|evangel|church plant", "Mission and evangelism"),
        (r"seminary|theological education|training", "Ministerial education"),
        (r"sexual|marriage|abortion|ethic", "Ethics and family"),
        (r"budget|treasurer|administr|headquarters", "Denominational administration"),
        (r"court|judicial|complaint|appeal", "Church courts"),
    ]
    for pattern, label in topic_rules:
        if re.search(pattern, low) and len(topics) < 2:
            topics.append(label)
    if not topics:
        topics.append("General Assembly business")
    return {"type": kind, "instrument": instrument or "—", "topic": "; ".join(topics), "bco_stage": stage}
