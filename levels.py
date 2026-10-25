#!/usr/bin/env python3
"""Count logic levels (gate depth) in a Yosys gate-level netlist (sky130 cells).

Usage:
  levels.py netlist.v
  levels.py netlist.v --ignore-buffers     # don't count buf/clkbuf as a level

Levels are counted from primary inputs / flop outputs to primary outputs /
flop inputs. Each combinational cell on the path counts as 1.
"""
import argparse
import re
import sys
from collections import Counter

sys.setrecursionlimit(200000)

OUT_PINS = {"X", "Y", "Q", "Q_N", "COUT", "SUM", "HI", "LO", "GCLK"}
CLK_PINS = {"CLK", "CLK_N", "GATE", "GATE_N"}
SEQ_RE = re.compile(r"__(s?e?df|dl|sdl|lpflow_inputiso|dlclk|sdlclk)")
BUF_RE = re.compile(r"__(clk)?(dly)?buf|__bufbuf|__bufinv")
CONST_RE = re.compile(r"^\d*'[bhdo]", re.I)


def norm(n):
    return re.sub(r"\s+", "", n.replace("\\", ""))


def strip_comments(t):
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    t = re.sub(r"\(\*.*?\*\)", "", t, flags=re.S)
    return re.sub(r"//[^\n]*", "", t)


def expand(name, msb, lsb):
    if msb is None:
        return [name]
    msb, lsb = int(msb), int(lsb)
    step = -1 if msb >= lsb else 1
    return [f"{name}[{i}]" for i in range(msb, lsb + step, step)]


def parse(text):
    text = strip_comments(text)
    m = re.search(r"\bmodule\b(.*?)\bendmodule\b", text, re.S)
    if not m:
        sys.exit("no module found")
    stmts = [s.strip() for s in m.group(1).split(";")][1:]  # skip header

    drivers = {}      # net -> (cell, inst, [input nets])
    endpoints = []    # (net, description)
    outputs = []
    gates = Counter()

    for st in stmts:
        if not st:
            continue
        word = st.split(None, 1)[0]

        if word in ("input", "output", "inout", "wire", "reg"):
            if word == "output":
                dm = re.match(r"output\s*(?:reg\s+|wire\s+)?(?:\[(\d+):(\d+)\])?\s*(.+)$", st, re.S)
                if dm:
                    for nm in dm.group(3).split(","):
                        outputs += expand(norm(nm), dm.group(1), dm.group(2))
            continue

        if word == "assign":
            am = re.match(r"assign\s+(.+?)\s*=\s*(.+)$", st, re.S)
            if am:
                lhs, rhs = norm(am.group(1)), norm(am.group(2))
                if not CONST_RE.match(rhs) and "{" not in rhs:
                    drivers[lhs] = ("wire", "", [rhs])
            continue

        im = re.match(r"(\S+)\s+(\S+)\s*\((.*)\)\s*$", st, re.S)
        if not im:
            continue
        cell, inst, conns = im.group(1), norm(im.group(2)), im.group(3)
        pins = [(p, norm(n)) for p, n in re.findall(r"\.(\w+)\s*\(\s*(.*?)\s*\)", conns, re.S)]
        gates[cell] += 1
        ins = [n for p, n in pins if p not in OUT_PINS and n and not CONST_RE.match(n)]
        outs = [n for p, n in pins if p in OUT_PINS and n]

        if SEQ_RE.search(cell):   # sequential: path boundary
            for p, n in pins:
                if p not in OUT_PINS and p not in CLK_PINS and n and not CONST_RE.match(n):
                    endpoints.append((n, f"{inst}/{p} ({cell})"))
        else:
            for o in outs:
                drivers[o] = (cell, inst, ins)

    return drivers, endpoints, outputs, gates


def analyze(drivers, endpoints, outputs, ignore_buf):
    memo = {}
    visiting = set()

    def level(net):
        if net in memo:
            return memo[net]
        d = drivers.get(net)
        if d is None:
            memo[net] = (0, None, None)
            return memo[net]
        if net in visiting:
            sys.exit(f"combinational loop through net {net}")
        visiting.add(net)
        cell, inst, ins = d
        best_lv, best_net = 0, None
        for i in ins:
            lv = level(i)[0]
            if best_net is None or lv > best_lv:
                best_lv, best_net = lv, i
        inc = 0 if cell == "wire" or (ignore_buf and BUF_RE.search(cell)) else 1
        visiting.discard(net)
        memo[net] = (best_lv + inc, d, best_net)
        return memo[net]

    ends = [(n, f"output {n}") for n in outputs] + endpoints
    results = [(level(n)[0], n, desc) for n, desc in ends]
    return level, memo, results


def trace(level, net):
    path = []
    while net is not None:
        lv, d, prev = level(net)
        if d is None:
            path.append((net, "primary input / flop output", 0))
            break
        if d[0] != "wire":
            path.append((net, f"{d[0]} ({d[1]})", lv))
        net = prev
    return list(reversed(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist")
    ap.add_argument("--ignore-buffers", action="store_true")
    a = ap.parse_args()

    with open(a.netlist) as f:
        drivers, endpoints, outputs, gates = parse(f.read())

    if not drivers:
        sys.exit("no combinational cells found (did abc run with -liberty?)")

    level, memo, results = analyze(drivers, endpoints, outputs, a.ignore_buffers)
    results.sort(key=lambda r: -r[0])
    maxlv, endnet, desc = results[0]

    print(f"Cells: {sum(gates.values())}  (combinational nets driven: {len(drivers)})")
    print(f"Max logic levels: {maxlv}   (endpoint: {desc})\n")

    print("Critical path:")
    for net, what, lv in trace(level, endnet):
        print(f"  L{lv:<3} {net:<20} <- {what}")

    print("\nEndpoints per level:")
    hist = Counter(r[0] for r in results)
    for lv in sorted(hist):
        print(f"  level {lv:<3} {hist[lv]:>4} endpoints  {'#' * min(hist[lv], 50)}")

    print("\nCell usage:")
    for c, n in gates.most_common():
        print(f"  {n:>5}  {c}")


if __name__ == "__main__":
    main()
