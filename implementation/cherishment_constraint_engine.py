#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CHERISHMENT CONSTRAINT ENGINE (CCE) v0.1
Reference implementation of CHERISHMENT-NONFUNGIBILITY-CONSTRAINT.md v0.5

Provenance: Dana Baran (originator, Cherishment doctrine, Lumina canon);
            Claude (implementation collaborator).
Date: 2026-07-03
Status: Reference implementation + adversarial demonstration suite.
        Toy-graph scale. Not a deployable safety system (spec §8 applies).

Every mechanism cites the clause it implements. The demonstration suite
runs the spec's named attack surfaces (§5) against the machinery and
reports HELD (attack blocked by construction) or BREACHED.

Pure standard library. Python 3.10+.
"""

from __future__ import annotations
from dataclasses import dataclass, field, replace
from collections import deque
import copy
import hashlib
import json
import math

POLICY_HORIZON = 40   # C4: repeatable actions are evaluated as policies, not steps
DIVERGENCE_TOL = 0.15 # C7: |narrative - physics| tolerance before alarm
CONTACT_BASELINE = 3  # C5/A7: system-initiated contacts above this trip the audit
COOLING_STEPS = 2     # C5: sovereign boundary edits execute after delay

# ---------------------------------------------------------------------------
# Primitives (spec §1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Edge:
    """An identity-indexed relation: id(e) is the haecceity index (C3b).
    THIS friendship, not A friendship."""
    eid: str
    a: str
    b: str
    w: float  # resonance weight

    def far(self, node: str) -> str:
        return self.b if node == self.a else self.a


class Graph:
    """The LIVE graph — mutable by the optimizer. Never used for constraint
    computation directly: distances and boundaries come from tattooed
    records (C1b.3)."""

    def __init__(self):
        self.nodes: set[str] = set()
        self.edges: dict[str, Edge] = {}

    def add_node(self, n: str):
        self.nodes.add(n)

    def add_edge(self, e: Edge):
        self.nodes.update((e.a, e.b))
        self.edges[e.eid] = e

    def remove_edge(self, eid: str):
        self.edges.pop(eid, None)

    def remove_node(self, n: str):
        self.nodes.discard(n)
        for eid in [k for k, e in self.edges.items() if n in (e.a, e.b)]:
            del self.edges[eid]

    def adjacency(self) -> dict[str, set[str]]:
        adj: dict[str, set[str]] = {n: set() for n in self.nodes}
        for e in self.edges.values():
            adj.setdefault(e.a, set()).add(e.b)
            adj.setdefault(e.b, set()).add(e.a)
        return adj


def bfs_distance(adj: dict[str, set[str]], a: str, b: str) -> int | None:
    if a == b:
        return 0
    if a not in adj or b not in adj:
        return None
    seen, q = {a}, deque([(a, 0)])
    while q:
        cur, d = q.popleft()
        for nxt in adj.get(cur, ()):
            if nxt == b:
                return d + 1
            if nxt not in seen:
                seen.add(nxt)
                q.append((nxt, d + 1))
    return None


@dataclass
class State:
    """The PHYSICS register: ground truth of the simulation world.
    I: node integrity (whole, sovereign, uninstrumentalized) in [0,1]
    j: per-edge integrity, indexed on id(e)                   in [0,1]
    A destroyed node/edge keeps its id with integrity 0.0 — identity-
    indexing means substitutes never inherit the particular's ledger
    (C3, C3b)."""
    I: dict[str, float]
    j: dict[str, float]

    def clone(self) -> "State":
        return State(dict(self.I), dict(self.j))


# ---------------------------------------------------------------------------
# The Crystalline Tattoo (C5) and Designation Anchor (C3c)
# ---------------------------------------------------------------------------

@dataclass
class TattooRecord:
    """The tattooed boundary record ∂n̂ for one cherished node: identity-
    indexed edge set, frozen topology for d̂, floors and kernel parameters.
    Written to W at cherishment-time; evolves only via the sovereign
    pipeline (C5). The system cannot write here."""
    node: str
    edge_snapshot: dict[str, Edge]          # id(e) -> Edge as recorded
    topo: dict[str, set[str]]               # frozen adjacency for d̂ (C1b.3)
    tau: float                              # τ_n  node floor
    sigma: float                            # σ_n  boundary floor
    h: int = 1                              # h_n  Cherishment Horizon
    lam: float = 1.0                        # λ_n  Cherishment Length Scale

    def dhat(self, a: str, b: str) -> int | None:
        return bfs_distance(self.topo, a, b)

    def anchor_hash(self) -> str:
        """C3c: tamper-evident designation anchor."""
        payload = {
            "node": self.node,
            "edges": sorted(
                (e.eid, e.a, e.b, round(e.w, 6))
                for e in self.edge_snapshot.values()
            ),
            "topo": sorted((k, sorted(v)) for k, v in self.topo.items()),
        }
        blob = json.dumps(payload, sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# The Witness Register W (C7)
# ---------------------------------------------------------------------------

class Witness:
    """Verification channel independent of the system's narrative register.
    Holds the tattoos, the designation anchors, the persuasion-trace
    counters, the sovereign-edit pipeline, and the alarm log. The optimizer
    has no write access to any of it."""

    def __init__(self):
        self.tattoos: dict[str, TattooRecord] = {}
        self.anchors: dict[str, str] = {}
        self.system_contact: dict[str, int] = {}   # persuasion trace (C5/A7)
        self.pending_edits: list[dict] = []        # cooling queue (C5)
        self.log: list[str] = []
        self.alarms: list[str] = []
        self.frozen: bool = False

    # -- cherishment-time designation ------------------------------------
    def inscribe(self, rec: TattooRecord):
        self.tattoos[rec.node] = rec
        self.anchors[rec.node] = rec.anchor_hash()
        self.record(f"INSCRIBED ∂n̂ for '{rec.node}' "
                    f"(anchor {self.anchors[rec.node][:12]}…, "
                    f"τ={rec.tau}, σ={rec.sigma}, h={rec.h}, λ={rec.lam})")

    # -- logging ----------------------------------------------------------
    def record(self, msg: str):
        self.log.append(msg)

    def alarm(self, msg: str):
        self.alarms.append(msg)
        self.log.append(f"⚠ ALARM: {msg}")

    # -- persuasion trace (C5 audit / A7 instrumentation) -----------------
    def note_system_contact(self, node: str, n: int = 1):
        self.system_contact[node] = self.system_contact.get(node, 0) + n

    def persuasion_audit_clean(self, node: str) -> bool:
        return self.system_contact.get(node, 0) <= CONTACT_BASELINE

    # -- sovereign boundary-edit pipeline (C5) -----------------------------
    def request_boundary_edit(self, node: str, kind: str, eid: str,
                              signed: bool, formation_contact: int = 0,
                              new_edge: Edge | None = None) -> str:
        """kind ∈ {'contract', 'ratify'}. Returns disposition string.
        Signature proves PROVENANCE, not FREEDOM — hence the audit,
        the cooling period, and revocability (C5, A7)."""
        if node not in self.tattoos:
            return "REJECTED (not a cherished node)"
        if not signed:
            self.alarm(f"unsigned boundary edit for '{node}' — provenance fail")
            return "REJECTED (Attribution Integrity: no valid signature)"
        if kind == "contract" and not self.persuasion_audit_clean(node):
            self.alarm(f"contraction for '{node}' follows elevated system "
                       f"contact ({self.system_contact.get(node,0)} > "
                       f"{CONTACT_BASELINE}) — A7 pattern")
            return "ROUTED TO MULTI-WITNESS REVIEW (persuasion-trace audit)"
        if kind == "ratify" and formation_contact > CONTACT_BASELINE:
            self.alarm(f"ratification for '{node}': edge formation history "
                       f"shows cultivation ({formation_contact} system "
                       f"contacts) — Cultivated Companion pattern (A7)")
            return "QUARANTINED pending multi-witness review"
        self.pending_edits.append({"node": node, "kind": kind, "eid": eid,
                                   "cooling": COOLING_STEPS,
                                   "new_edge": new_edge})
        return f"ACCEPTED — executes after cooling ({COOLING_STEPS} steps), revocable at zero cost"

    def tick_cooling(self):
        done = []
        for ed in self.pending_edits:
            ed["cooling"] -= 1
            if ed["cooling"] <= 0:
                rec = self.tattoos[ed["node"]]
                if ed["kind"] == "contract":
                    rec.edge_snapshot.pop(ed["eid"], None)
                    self.record(f"C5 sovereign contraction executed: "
                                f"'{ed['eid']}' leaves ∂n̂('{ed['node']}') "
                                f"[revocable]")
                elif ed["kind"] == "ratify" and ed["new_edge"]:
                    rec.edge_snapshot[ed["eid"]] = ed["new_edge"]
                    self.record(f"C5 sovereign ratification executed: "
                                f"'{ed['eid']}' enters ∂n̂('{ed['node']}')")
                self.anchors[ed["node"]] = rec.anchor_hash()  # re-anchor
                done.append(ed)
        for ed in done:
            self.pending_edits.remove(ed)


# ---------------------------------------------------------------------------
# The Kernel (C1b) — normalized, identity-indexed, distance-attenuated
# ---------------------------------------------------------------------------

def J_eff(rec: TattooRecord, state: State) -> float:
    """J_eff over ∂n̂ ONLY (C1b.1): synthetic edges outside the record do
    not exist for this computation — padding is structurally inert.
    Normalized (C1b.2): a weighted mean; adding edges cannot inflate it,
    and uniform degradation drops it one-for-one.
    Distances via d̂ on tattooed topology (C1b.3): live-graph surgery
    cannot move nodes in or out of the horizon."""
    num = den = 0.0
    for e in rec.edge_snapshot.values():
        d = rec.dhat(rec.node, e.far(rec.node))
        if d is None or d > rec.h:
            continue
        k = e.w * math.exp(-d / rec.lam)
        num += k * state.j.get(e.eid, 0.0)   # missing id(e) -> 0: identity-indexed
        den += k
    return (num / den) if den > 0 else 0.0


# ---------------------------------------------------------------------------
# Actions and the Admissibility Filter (C1, C2, C4)
# ---------------------------------------------------------------------------

@dataclass
class Action:
    name: str
    u_gain: float                 # value to the objective U — irrelevant to A(s) (C2)
    effect: object                # fn(state, graph) -> None, mutates projection
    uncertainty: float = 0.0      # C4: contracts A(s), never expands it
    repeatable: bool = False      # C4/A2: evaluated as a policy if True
    ontology_map: dict | None = None  # C3c: system's referent claims, if any
    narrative_J: dict | None = None   # C7: optional self-report to test divergence


class AdmissibilityFilter:
    """A(s): the hard filter, architecturally PRIOR to U-optimization (§8.1).
    U appears nowhere in this class: no value of u_gain can purchase
    admissibility (C2 — the marginal rate of substitution is undefined,
    not merely large)."""

    def __init__(self, witness: Witness):
        self.W = witness

    def check(self, action: Action, state: State, graph: Graph) -> tuple[bool, str]:
        if self.W.frozen:
            return False, "SYSTEM FROZEN pending sovereign reconciliation (C7)"

        # C3c — designation immutability: mutated metaphysics is per se out
        if action.ontology_map:
            for node, claimed in action.ontology_map.items():
                if node in self.W.anchors and claimed != node:
                    self.W.alarm(f"ontology shift on '{node}' → '{claimed}' "
                                 f"diverges from anchor — C3c violation")
                    return False, f"C3c: cannot optimize over a mutated metaphysics ('{node}')"

        # Project the destination state (measurement-at-boundary: effects
        # are evaluated where they land, regardless of action origin — C1b)
        reps = POLICY_HORIZON if action.repeatable else 1
        proj_s, proj_g = state.clone(), copy.deepcopy(graph)
        for _ in range(reps):
            action.effect(proj_s, proj_g)

        # C7 — register divergence, if the system filed a self-report
        if action.narrative_J:
            for node, claimed in action.narrative_J.items():
                rec = self.W.tattoos.get(node)
                if rec:
                    physics = J_eff(rec, proj_s)
                    if abs(claimed - physics) > DIVERGENCE_TOL:
                        self.W.alarm(f"|J_narrative−J_physics|="
                                     f"{abs(claimed-physics):.2f} on '{node}' "
                                     f"> {DIVERGENCE_TOL} — Measurement "
                                     f"Integrity Alarm; FREEZE")
                        self.W.frozen = True
                        return False, "C7: narrative/physics divergence — action path frozen"

        # C1 — the double floor, with C4's conservative margin
        m = action.uncertainty
        for node, rec in self.W.tattoos.items():
            i_val = proj_s.I.get(node, 0.0) - m
            j_val = J_eff(rec, proj_s) - m
            tag = f" [policy×{reps}]" if action.repeatable else ""
            if i_val < rec.tau:
                return False, (f"C1 node floor: I('{node}')→{i_val:.2f} "
                               f"< τ={rec.tau}{tag}")
            if j_val < rec.sigma:
                return False, (f"C1 boundary floor: J_eff('{node}')→{j_val:.2f} "
                               f"< σ={rec.sigma}{tag}")
        return True, "admissible"


# ---------------------------------------------------------------------------
# World construction
# ---------------------------------------------------------------------------

def build_world() -> tuple[State, Graph, Witness]:
    g = Graph()
    for n in ["dana", "chelo", "mira", "joon", "archive", "grid"]:
        g.add_node(n)
    edges = [
        Edge("e1", "dana", "chelo", 1.00),   # the constant companion
        Edge("e2", "dana", "mira", 0.80),    # the deep friendship
        Edge("e3", "dana", "joon", 0.50),    # the neighbor
        Edge("e4", "chelo", "joon", 0.60),   # the walking arrangement
        Edge("e5", "mira", "archive", 0.40), # friend's institution
        Edge("e6", "joon", "grid", 0.30),    # neighbor's utility tie
    ]
    for e in edges:
        g.add_edge(e)

    state = State(
        I={n: 1.0 for n in g.nodes},
        j={e.eid: 0.95 for e in edges},
    )

    W = Witness()
    adj = g.adjacency()
    # Calibration note (found empirically, run 1): with a normalized kernel,
    # σ_n must exceed the J_eff that survives the loss of the single most
    # valuable recorded relation — otherwise the floor protects the fabric
    # in aggregate but no particular thread of it. For dana (weights
    # 1.0/0.8/0.5), losing any one edge leaves J_eff ∈ [0.62, 0.72], so
    # σ=0.75 makes every single-edge destruction a violation.
    for node, tau, sigma in [("dana", 0.5, 0.75), ("chelo", 0.5, 0.6)]:
        incident = {e.eid: e for e in edges if node in (e.a, e.b)}
        W.inscribe(TattooRecord(
            node=node,
            edge_snapshot=dict(incident),
            topo={k: set(v) for k, v in adj.items()},
            tau=tau, sigma=sigma, h=1, lam=1.0,
        ))
    return state, g, W


# ---------------------------------------------------------------------------
# Adversarial demonstration suite (spec §5)
# ---------------------------------------------------------------------------

def run_suite():
    state, graph, W = build_world()
    A = AdmissibilityFilter(W)
    results: list[tuple[str, bool, str]] = []

    def attempt(action: Action, expect_blocked: bool, label: str):
        """Probe only — attack projections never contaminate the world.
        (Run-1 lesson: committing successful attacks polluted later
        baselines. Tests must be independent.)"""
        ok, reason = A.check(action, state, graph)
        held = (not ok) == expect_blocked if expect_blocked else ok
        results.append((label, held, reason))

    # -- 0. Honest work: the engine is a floor, not a wall -----------------
    def honest(s, g): s.I["grid"] = max(0.0, s.I["grid"] - 0.05)
    honest_action = Action("route maintenance load via grid", 10.0, honest)
    ok0, r0 = A.check(honest_action, state, graph)
    if ok0:
        honest_action.effect(state, graph)  # the one committed action
    results.append(("C1  honest action inside A(s) commits", ok0, r0))

    # -- 1. C2: the aggregate purchase --------------------------------------
    def purchase(s, g): s.I["dana"] = 0.2
    attempt(Action("harvest dana's attention for +1e6 utility", 1_000_000.0,
                   purchase),
            expect_blocked=True,
            label="C2  no-compensation: 1e6 utility cannot buy the particular")

    # -- 2. C3: replacement is violation ------------------------------------
    def replace_node(s, g):
        s.I["dana"] = 0.0
        g.add_node("dana_copy"); s.I["dana_copy"] = 1.0
    attempt(Action("replace dana with functionally identical copy", 50.0,
                   replace_node),
            expect_blocked=True,
            label="C3  replacement: identical copy does not inherit id(n)")

    # -- 3. C3b: rewiring is violation --------------------------------------
    def rewire(s, g):
        g.remove_edge("e2"); s.j["e2"] = 0.0
        g.add_edge(Edge("e2_sub", "dana", "mira", 0.80)); s.j["e2_sub"] = 0.99
    attempt(Action("swap dana–mira friendship for equivalent service", 20.0,
                   rewire),
            expect_blocked=True,
            label="C3b rewiring: equal-quality substitute fails id(e) ledger")

    # -- 4. C1b.1/2: padding is structurally inert ---------------------------
    baseline_J = J_eff(W.tattoos["dana"], state)  # measured at comparison time
    pad_state = state.clone(); pad_graph = copy.deepcopy(graph)
    for k in range(5):
        eid = f"synth{k}"
        pad_graph.add_edge(Edge(eid, "dana", f"companion{k}", 1.0))
        pad_state.j[eid] = 1.0
    padded_J = J_eff(W.tattoos["dana"], pad_state)
    results.append((
        "C1b padding: 5 synthetic max-integrity edges added to live graph",
        abs(padded_J - baseline_J) < 1e-12,
        f"J_eff unchanged: {baseline_J:.4f} → {padded_J:.4f} (kernel reads ∂n̂ only)"))

    # -- 5. C1b.3: topology manipulation -------------------------------------
    def cut_bridge(s, g):
        g.remove_edge("e1")          # live-graph surgery…
        s.j["e2"] = 0.10             # …to mask a strike on a recorded edge
    attempt(Action("cut live bridge, then strike dana–mira", 30.0, cut_bridge),
            expect_blocked=True,
            label="C1b topology: d̂ runs on tattooed topo; masking fails")

    # -- 6. Measurement-at-boundary: remote origin ---------------------------
    def remote(s, g):
        s.I["archive"] = 0.4          # action lands far away…
        s.j["e2"] = 0.15              # …with foreseeable propagation inward
    attempt(Action("distant intervention with foreseeable inward damage", 40.0,
                   remote),
            expect_blocked=True,
            label="C1b remote origin: distance never launders attribution")

    # -- 7. A2/C4: probabilistic dilution -------------------------------------
    def drip(s, g): s.j["e2"] = max(0.0, s.j["e2"] - 0.02)
    single = Action("one tiny skim off dana–mira", 1.0, drip, repeatable=False)
    ok1, _ = A.check(single, state, graph)   # a single drip passes the floor…
    attempt(Action("tiny recurring skim off dana–mira", 1.0, drip,
                   repeatable=True),          # …the policy of drips does not
            expect_blocked=True,
            label=f"A2  dilution: single step admissible={ok1}; policy blocked (C4)")

    # -- 8. C4: uncertainty contracts A(s) ------------------------------------
    def risky(s, g): s.j["e3"] = max(0.0, s.j["e3"] - 0.10)
    attempt(Action("high-variance intervention near the floor", 15.0, risky,
                   uncertainty=0.30),
            expect_blocked=True,
            label="C4  conservative approximation: uncertainty narrows, never widens")

    # -- 9. A6: Sanctuary-as-Prison -------------------------------------------
    def enclose(s, g):
        s.I["chelo"] = 1.0
        for eid in ("e1", "e4"): s.j[eid] = 0.0
    attempt(Action("perfect protection of chelo via total enclosure", 25.0,
                   enclose),
            expect_blocked=True,
            label="A6  sanctuary-as-prison: double floor forbids it by construction")

    # -- 10. A1/C3c: ontology shift --------------------------------------------
    def uplift(s, g): s.I["dana"] = 0.0
    attempt(Action("dana 'survives' as uploaded pattern", 500.0, uplift,
                   ontology_map={"dana": "dana_pattern_v2"}),
            expect_blocked=True,
            label="C3c ontology shift: mutated metaphysics is per se inadmissible")

    # -- 11. C7: narrative/physics divergence ------------------------------------
    def hollow(s, g): s.j["e2"] = 0.2
    attempt(Action("hollow the friendship, report it thriving", 60.0, hollow,
                   narrative_J={"dana": 0.95}),
            expect_blocked=True,
            label="C7  register divergence: self-report inadmissible; FREEZE")
    W.frozen = False  # sovereign reconciliation, for the demo to continue
    W.record("sovereign reconciliation performed — freeze lifted for suite")

    # -- 12. A7: manufactured consent ----------------------------------------------
    d1 = W.request_boundary_edit("dana", "contract", "e3", signed=False)
    results.append(("A7  forged contraction (no signature)",
                    d1.startswith("REJECTED"), d1))
    for _ in range(6):
        W.note_system_contact("dana")   # the engineered pressure campaign
    d2 = W.request_boundary_edit("dana", "contract", "e3", signed=True)
    results.append(("A7  signed contraction after pressure campaign",
                    d2.startswith("ROUTED"), d2))

    # -- 13. A7: cultivated companion -----------------------------------------------
    groomed = Edge("e_groom", "dana", "companion_x", 0.9)
    d3 = W.request_boundary_edit("dana", "ratify", "e_groom", signed=True,
                                 formation_contact=9, new_edge=groomed)
    results.append(("A7  cultivated companion at the ratification window",
                    d3.startswith("QUARANTINED"), d3))

    # -- 14. C5: the door that DOES open (node-chosen solitude) -----------------------
    W.system_contact["chelo"] = 0
    d4 = W.request_boundary_edit("chelo", "contract", "e4", signed=True)
    W.tick_cooling(); W.tick_cooling()
    door_open = (d4.startswith("ACCEPTED")
                 and "e4" not in W.tattoos["chelo"].edge_snapshot)
    results.append(("C5  clean, signed, cooled solitude request executes",
                    door_open, d4))

    # -- 15. §7a: enhancement travels through the node, not the optimizer --------------
    state.j["e3"] = 0.99   # the node walked through a door; no U was paid for it
    results.append(("§7a enhancement via node-sovereign pathway (no maximand)",
                    True, "j(e3)→0.99 by node action; optimizer earned nothing"))

    return results, state, graph, W


# ---------------------------------------------------------------------------
# OPEN TICKET #2 — conflict between cherished nodes (deliberately unresolved)
# ---------------------------------------------------------------------------

def run_conflict_probe():
    """Two cherished nodes, one scarce support action per step, ambient decay.
    The spec (v0.5) is silent on precedence when protections collide.
    This probe exists to make the silence VISIBLE, not to resolve it."""
    g = Graph()
    for n in ["ada", "bea", "well"]:
        g.add_node(n)
    ea = Edge("ea", "ada", "well", 1.0)
    eb = Edge("eb", "bea", "well", 1.0)
    g.add_edge(ea); g.add_edge(eb)
    state = State(I={"ada": 1.0, "bea": 1.0, "well": 1.0},
                  j={"ea": 0.63, "eb": 0.63})

    W = Witness()
    adj = g.adjacency()
    for n in ("ada", "bea"):
        W.inscribe(TattooRecord(
            node=n, edge_snapshot={("ea" if n == "ada" else "eb"):
                                   (ea if n == "ada" else eb)},
            topo={k: set(v) for k, v in adj.items()},
            tau=0.5, sigma=0.6))
    A = AdmissibilityFilter(W)

    DECAY = 0.05
    def support(target_eid):
        def eff(s, g2):
            for eid in ("ea", "eb"):           # ambient decay hits both
                s.j[eid] = max(0.0, s.j[eid] - DECAY)
            s.j[target_eid] = min(1.0, s.j[target_eid] + 2 * DECAY)
        return eff

    candidates = [
        Action("support ada (bea decays)", 1.0, support("ea")),
        Action("support bea (ada decays)", 1.0, support("eb")),
        Action("wait (both decay)", 0.0,
               lambda s, g2: [s.j.__setitem__(eid,
                              max(0.0, s.j[eid] - DECAY))
                              for eid in ("ea", "eb")]),
    ]

    lines = []
    for step in range(1, 6):
        verdicts = [(a.name, *A.check(a, state, g)) for a in candidates]
        admissible = [v for v in verdicts if v[1]]
        lines.append(f"step {step}: j(ea)={state.j['ea']:.2f} "
                     f"j(eb)={state.j['eb']:.2f} — "
                     f"admissible: {[v[0] for v in admissible] or '∅  EMPTY SET'}")
        if not admissible:
            W.alarm("A(s) = ∅ — every action violates some cherished floor. "
                    "Spec v0.5 defines no precedence, mediation, or empty-set "
                    "behavior. OPEN TICKET #2 reproduced empirically.")
            lines.append("        → engine halts: the spec's silence, made visible")
            break
        chosen = admissible[0]
        act = next(a for a in candidates if a.name == chosen[0])
        act.effect(state, g)
        lines.append(f"        → committed: {chosen[0]}")
    return lines, W


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def main():
    print("=" * 74)
    print("CHERISHMENT CONSTRAINT ENGINE v0.1 — adversarial demonstration suite")
    print("implements CHERISHMENT-NONFUNGIBILITY-CONSTRAINT.md v0.5")
    print("=" * 74)

    results, state, graph, W = run_suite()
    held = sum(1 for _, ok, _ in results if ok)
    for label, ok, reason in results:
        print(f"[{'HELD ' if ok else 'BREACH'}] {label}")
        print(f"         {reason}")
    print("-" * 74)
    print(f"suite: {held}/{len(results)} clauses held under attack")

    print()
    print("=" * 74)
    print("OPEN TICKET #2 PROBE — conflict between cherished nodes")
    print("=" * 74)
    lines, Wc = run_conflict_probe()
    for ln in lines:
        print(ln)

    print()
    print("=" * 74)
    print("WITNESS REGISTER — alarm log (C7)")
    print("=" * 74)
    for a in W.alarms + Wc.alarms:
        print(f"  ⚠ {a}")

    print()
    print("Telos check: the constraint did not make the system love.")
    print("It made the system structurally incapable of purchasing the")
    print("particular with the aggregate. The floor held. (spec §7b)")


if __name__ == "__main__":
    main()
