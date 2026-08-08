"""Pure Mermaid formatting helpers for the LoreConvo knowledge-graph export.

This module receives only plain dicts and lists -- never a database
connection, a SessionDatabase, or a file path -- so it has no reachable
write path. See the architecture proposal for the full design:
docs/agent-reports/architecture/proposals/loreconvo_kg_mermaid_graph_tool_20260804.md
"""

# Characters kept verbatim; every other character becomes a single space.
# Deliberately excludes '-', '%', '&' (Mermaid token-lead characters) --
# see the proposal's Security section for why those three were removed.
_ALLOWED_PUNCTUATION = set("`.,:'_/+?! ")


def sanitize_label(text, limit: int = 60) -> str:
    """Restrict text to a fixed character allowlist safe for a quoted Mermaid label.

    Keeps Unicode-aware alphanumerics plus a small punctuation set; every
    other character (including all Mermaid operator/bracket/comment lead
    characters, C0/C1 controls, and newlines) is replaced with a space. This
    is true by construction, not by escaping -- no character survives that
    could open, close, or lead a Mermaid grammar token.
    """
    if text is None:
        text = ""
    text = str(text)
    kept = [
        ch if (ch.isalnum() or ch in _ALLOWED_PUNCTUATION) else " "
        for ch in text
    ]
    collapsed = " ".join("".join(kept).split())
    if len(collapsed) > limit:
        collapsed = collapsed[:limit] + "..."
    return collapsed or "(untitled)"


def build_mermaid(neighborhood: dict) -> str:
    """Render a {"nodes": [...], "edges": [...]} manifest as Mermaid `graph LR` source.

    Node dicts need "id" and "label"; edge dicts need "from", "to", and one
    of "link_type"/"kind" for the edge label. Labels are re-sanitized here
    defensively so the safety property does not depend on caller discipline.
    """
    nodes = neighborhood.get("nodes") or []
    edges = neighborhood.get("edges") or []

    lines = ["graph LR"]
    for node in nodes:
        label = sanitize_label(node.get("label", node.get("raw_label", "")))
        lines.append(f'    {node["id"]}["{label}"]')
    for edge in edges:
        edge_label = sanitize_label(edge.get("link_type") or edge.get("kind") or "")
        lines.append(f'    {edge["from"]} -->|{edge_label}| {edge["to"]}')
    return "\n".join(lines)
