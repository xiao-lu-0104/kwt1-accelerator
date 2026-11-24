# 42um pitch proposal only. Source only after macro-pin/via/blockage review.
if {![info exists PgGeometryReviewed] || !$PgGeometryReviewed} {
    error "Review current MacroPgGeometry.tsv and resolve macro/via/M4 blockage strategy before PG generation"
}
create_pg_mesh_pattern MESH707CD7F_42_CANDIDATE -layers {
    {{vertical_layer: M2} {width: 0.28} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
    {{horizontal_layer: M3} {width: 0.28} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
    {{vertical_layer: M4} {width: 0.28} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
    {{horizontal_layer: M5} {width: 0.28} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
    {{vertical_layer: M6} {width: 0.56} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
    {{horizontal_layer: M7} {width: 1.12} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
    {{vertical_layer: TM2} {width: 1.68} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
}
# No strategies/compile_pg: all widths/offsets/vias/blockages remain candidate values.
