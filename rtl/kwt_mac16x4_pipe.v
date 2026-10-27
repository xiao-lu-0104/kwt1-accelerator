`timescale 1ns/1ps
// 64 int8 MACs, II=1. A first-segment tag clears each output accumulator.
// Input mux capture, product, four tree levels and feedback are registered.
module kwt_mac16x4_pipe(
    input wire clk,rst_n,valid_in,first_in,
    input wire [127:0] a,
    input wire [511:0] w,
    output wire valid_out,
    output wire [127:0] acc_out
);
    reg [127:0] ar;
    reg [511:0] wr;
    reg [6:0] valid,first;
    always @(posedge clk) begin ar<=a;wr<=w;end
    always @(posedge clk or negedge rst_n)
        if(!rst_n) begin valid<=0;first<=0;end
        else begin valid<={valid[5:0],valid_in};first<={first[5:0],first_in};end
    assign valid_out=valid[6];
    genvar c,i;
    generate for(c=0;c<4;c=c+1) begin: g_ch
        reg signed [15:0] p[0:15];
        reg signed [16:0] s1[0:7];
        reg signed [17:0] s2[0:3];
        reg signed [18:0] s3[0:1];
        reg signed [19:0] total;
        reg signed [31:0] q;
        for(i=0;i<16;i=i+1) begin: g_p
            always @(posedge clk) p[i]<=$signed(ar[i*8 +: 8])*$signed(wr[(c*16+i)*8 +: 8]);
        end
        for(i=0;i<8;i=i+1) begin: g_s1
            always @(posedge clk) s1[i]<=$signed({p[2*i][15],p[2*i]})+$signed({p[2*i+1][15],p[2*i+1]});
        end
        for(i=0;i<4;i=i+1) begin: g_s2
            always @(posedge clk) s2[i]<=$signed({s1[2*i][16],s1[2*i]})+$signed({s1[2*i+1][16],s1[2*i+1]});
        end
        for(i=0;i<2;i=i+1) begin: g_s3
            always @(posedge clk) s3[i]<=$signed({s2[2*i][17],s2[2*i]})+$signed({s2[2*i+1][17],s2[2*i+1]});
        end
        always @(posedge clk) total<=$signed({s3[0][18],s3[0]})+$signed({s3[1][18],s3[1]});
        always @(posedge clk or negedge rst_n)
            if(!rst_n) q<=0;
            else if(valid[5]) q<=(first[5]?32'sd0:q)+total;
        assign acc_out[c*32 +: 32]=q;
    end endgenerate
endmodule
