# Round-Robin Arbiter (`rr_arb`): Synthesis Trials

A round-robin arbiter written in SystemVerilog, synthesized with open-source tools
(Yosys + ABC) against the SkyWater SKY130 high-density standard-cell library to
estimate **area**, **critical-path delay (Fmax)** and **logic depth**.

## Repository layout

```
.
├── rr_arb.sv        # RTL: round-robin arbiter (top module: rr_arb)
├── abc.constr       # ABC constraints (driving cell + output load)
├── levels.py        # Logic-depth analyzer for the mapped netlist
├── runs/            # Generated outputs (netlist, stats, logs)
│   ├── rr_arb_net.v     # Gate-level netlist
│   ├── case_stat.txt    # Cell counts and area (stat -liberty)
│   └── yosys.log        # Full synthesis log (contains ABC delay)
└── README.md
```

## Prerequisites

| Tool | Purpose |
|------|---------|
| [Yosys](https://github.com/YosysHQ/yosys) (bundles ABC) | Synthesis and technology mapping |
| SKY130 PDK via [Volare](https://github.com/efabless/volare) | Liberty timing library |
| Python 3 | Runs `levels.py` |

The Liberty file used is the typical corner (tt, 25 °C, 1.8 V):

```
$HOME/.volare/sky130B/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
```

## ABC constraints (`abc.constr`)

```
set_driving_cell sky130_fd_sc_hd__dfxtp_1
set_load 0.002
```

- `set_driving_cell`: inputs are driven with the strength and slew of a flop output.
- `set_load`: each output sees 0.002 pF (2 fF), roughly one flop D pin. Liberty cap units are pF.

Create it with:

```bash
printf 'set_driving_cell sky130_fd_sc_hd__dfxtp_1\nset_load 0.002\n' > abc.constr
```

Keep these values identical across experiments so results are comparable.

## Running the synthesis

```bash
mkdir -p runs

export LIB="$HOME/.volare/sky130B/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"

yosys -p "read_verilog -sv rr_arb.sv; \
  synth -top rr_arb -flatten; \
  dfflibmap -liberty $LIB; \
  abc -D 1000 -constr abc.constr -liberty $LIB; \
  opt_clean -purge; \
  tee -o runs/case_stat.txt stat -liberty $LIB; \
  write_verilog -noattr runs/rr_arb_net.v" | tee runs/yosys.log

grep -E "Delay =" runs/yosys.log

python3 levels.py runs/rr_arb_net.v
```

### What each step does

| Step | Purpose |
|------|---------|
| `read_verilog -sv` | Parse the SystemVerilog source |
| `synth -top rr_arb -flatten` | Generic synthesis, flattening the hierarchy |
| `dfflibmap -liberty` | Map flip-flops to real SKY130 flop cells (must run **before** `abc`) |
| `abc -D 1000 -constr ... -liberty` | Map combinational logic to SKY130 cells, targeting 1000 ps |
| `opt_clean -purge` | Remove unused cells and wires |
| `stat -liberty` | Report cell counts and area |
| `write_verilog -noattr` | Write the mapped gate-level netlist |
| `levels.py` | Compute logic depth (levels of logic) |

## Reading the results

### Delay and Fmax

The `Delay =` line in `runs/yosys.log` is the ABC-reported **combinational** critical path in ps:

```
ABC: WireLoad = "none"  Gates = ...  Area = ...  Delay = XXXX.XX ps
```

This excludes flop clk-to-q and setup. Estimate the minimum clock period as:

```
T_min ≈ t_clk-to-q + t_comb + t_setup      (≈ 0.3 ns + t_comb + 0.1 ns for dfxtp_1, tt corner)
Fmax  ≈ 1 / T_min
```

Check exact flop timing in the Liberty file for your slew and load.

### Area

```bash
grep -i "chip area" runs/case_stat.txt
```

Units are µm². Make sure flops show up as `sky130_fd_sc_hd__df*` cells, not
generic `$_DFF_*` cells; otherwise the total is understated.

### Logic levels

`levels.py` reports the longest chain of cells in the netlist. It should treat
flop outputs as start points and flop D inputs as end points.

## Synthesis trials

Fill in one row per run. The target `-D` is a goal for ABC, not a hard limit.

| Trial | Design change / ABC option | `-D` (ps) | Delay (ps) | Area (µm²) | Levels | Est. Fmax (MHz) |
|-------|----------------------------|-----------|------------|------------|--------|-----------------|
| 1 | Baseline | 1000 | 3790 | 2584 | 14 | 244 |
| 2 | | | | | | |
| 3 | | | | | | |

## Notes and limitations

- **Pre-layout, no wire parasitics.** ABC reports `WireLoad = "none"`, so the numbers
  are optimistic. They are suited to comparing architectures, not to sign-off.
- **Typical corner only.** Worst-case corners (ss, low voltage, high temperature) will be slower.
- **No true STA.** ABC's delay is a combinational estimate. For full timing with clock
  constraints, run OpenSTA or OpenROAD on `runs/rr_arb_net.v`.
- **Results vary with constraints.** Changing `set_driving_cell`, `set_load` or `-D` changes the numbers.


