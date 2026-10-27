`timescale 1ns / 1ps
// One shared 4-output x 16-input signed int8 dot-product datapath.
// W4 values are sign-extended by the caller. Exact tree, int32 wraparound.
module kwt_mac16x4 (
    input wire clk, input wire rst_n, input wire valid_in,
    input wire [127:0] a, input wire [511:0] w,
    input wire [127:0] acc_in,
    output reg valid_out, output wire [127:0] acc_out
);
    genvar c,i;
    generate for(c=0;c<4;c=c+1) begin: g_ch
        wire signed [15:0] p[0:15];
        wire signed [16:0] s1[0:7];
        wire signed [17:0] s2[0:3];
        wire signed [18:0] s3[0:1];
        wire signed [19:0] total;
        reg signed [31:0] q;
        for(i=0;i<16;i=i+1) begin: g_p
            assign p[i]=$signed(a[i*8 +: 8]) * $signed(w[(c*16+i)*8 +: 8]);
        end
        for(i=0;i<8;i=i+1) begin: g_s1
            assign s1[i]=$signed({p[2*i][15],p[2*i]})+$signed({p[2*i+1][15],p[2*i+1]});
        end
        for(i=0;i<4;i=i+1) begin: g_s2
            assign s2[i]=$signed({s1[2*i][16],s1[2*i]})+$signed({s1[2*i+1][16],s1[2*i+1]});
        end
        for(i=0;i<2;i=i+1) begin: g_s3
            assign s3[i]=$signed({s2[2*i][17],s2[2*i]})+$signed({s2[2*i+1][17],s2[2*i+1]});
        end
        assign total=$signed({s3[0][18],s3[0]})+$signed({s3[1][18],s3[1]});
        always @(posedge clk or negedge rst_n)
            if(!rst_n) q<=0;
            else if(valid_in) q<=$signed(acc_in[c*32 +: 32])+total;
        assign acc_out[c*32 +: 32]=q;
    end endgenerate
    always @(posedge clk or negedge rst_n)
        if(!rst_n) valid_out<=0; else valid_out<=valid_in;
endmodule
