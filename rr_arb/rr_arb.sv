// Round-robin arbiter, 32 requesters, single flat module (no instantiations,
// no functions, plain Verilog-2005 constructs so any frontend accepts it).
// mask_st holds the bits strictly ABOVE the last granted requester.
module rr_arb (
  input  [31:0] in,
  input         in_valid,
  output [31:0] out_gnt,
  output        out_valid,
  input         clk,
  input         rst
);

  reg  [31:0] mask_st;
  wire [31:0] mask_nxt;
  wire [31:0] in_masked = in & mask_st;

  // ---- Kogge-Stone prefix OR on unmasked requests: pre_u[i] = |in[i:0] ----
  wire [31:0] u1 = in | (in << 1);
  wire [31:0] u2 = u1 | (u1 << 2);
  wire [31:0] u3 = u2 | (u2 << 4);
  wire [31:0] u4 = u3 | (u3 << 8);
  wire [31:0] pre_u = u4 | (u4 << 16);

  // ---- Kogge-Stone prefix OR on masked requests: pre_m[i] = |in_masked[i:0] ----
  wire [31:0] m1 = in_masked | (in_masked << 1);
  wire [31:0] m2 = m1 | (m1 << 2);
  wire [31:0] m3 = m2 | (m2 << 4);
  wire [31:0] m4 = m3 | (m3 << 8);
  wire [31:0] pre_m = m4 | (m4 << 16);

  // One-hot lowest requester, and "any request" flags
  wire [31:0] gnt_u   = pre_u & ~(pre_u << 1);
  wire [31:0] gnt_m   = pre_m & ~(pre_m << 1);
  wire        gnt_v_u = pre_u[31];
  wire        gnt_v_m = pre_m[31];

  // Use masked result if anyone is above the pointer, otherwise wrap around.
  // New mask = bits strictly above the granted bit (= pre << 1).
  assign mask_nxt  = gnt_v_m ? (pre_m << 1) : (pre_u << 1);
  assign out_gnt   = !in_valid ? 32'd0 : (gnt_v_m ? gnt_m : gnt_u);
  assign out_valid = in_valid & (gnt_v_m | gnt_v_u);

  // Advance the pointer only when a grant is actually issued.
  always @(posedge clk) begin
    if (rst)            mask_st <= 32'd0;
    else if (out_valid) mask_st <= mask_nxt;
  end

endmodule
