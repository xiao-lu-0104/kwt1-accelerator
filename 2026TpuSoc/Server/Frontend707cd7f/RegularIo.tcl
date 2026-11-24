# Source only after a new, independently saved 707cd7f placed checkpoint.
proc IoBox {Object} {
    set B [get_attribute $Object bbox]
    if {[llength $B]!=2 || [llength [lindex $B 0]]!=2 || [llength [lindex $B 1]]!=2} {
        error "Unexpected native physical bbox: [get_object_name $Object] $B"
    }
    return [concat [lindex $B 0] [lindex $B 1]]
}
proc IoLayers {Object} {
    if {![catch {get_attribute $Object layer_name} L] && [string trim $L] ne ""} {
        return $L
    }
    set Layers {}
    foreach_in_collection S [get_shapes -of_objects $Object] {
        lappend Layers [get_attribute $S layer_name]
    }
    if {![llength $Layers]} {error "No native layer for [get_object_name $Object]"}
    return [join [lsort -unique $Layers] ,]
}
proc IoConstrain {Name Layer X Y} {
    set P [get_ports -quiet [list $Name]]
    if {[sizeof_collection $P]!=1 || [get_object_name $P] ne $Name} {error "Port resolution changed: $Name"}
    PrStep io_location [list set_individual_pin_constraints -ports $P -allowed_layers [list $Layer] -location [list $X $Y]]
}
foreach {N O} {
    set_individual_pin_constraints {-ports -allowed_layers -location}
    set_block_pin_constraints {-self -corner_keepout_distance -pin_spacing_distance -stacking_allowed -hard_constraints}
    place_pins {-self} get_terminals {-of_objects} get_shapes {-of_objects}
} {PrNeed $N $O}
foreach L {M3 M4} {
    if {[sizeof_collection [get_layers -quiet $L]]!=1} {error "IO layer absent: $L"}
    set Pitch [get_attribute [get_layers $L] pitch]
    foreach V $Pitch {
        if {![string is double -strict $V] || abs($V-0.14)>0.000001} {error "Unreviewed IO routing pitch: $L $Pitch"}
    }
    if {![llength $Pitch]} {error "Empty routing pitch for $L"}
}
# Native block boundary, not the core box or a guessed utilization-derived size.
set Boundary [get_attribute [current_block] boundary]
set Xs {};set Ys {}
foreach P $Boundary {
    if {[llength $P]!=2} {error "Nonrectangular/unsupported die boundary representation"}
    lappend Xs [lindex $P 0];lappend Ys [lindex $P 1]
}
if {[llength $Xs]<4} {error "Expected native rectangular die polygon"}
set Xs [lsort -real -unique $Xs];set Ys [lsort -real -unique $Ys]
if {[llength $Xs]!=2 || [llength $Ys]!=2} {error "Nonrectangular die is not supported by this IO plan"}
set F [open DieBoundary.txt w]
puts $F "[lindex $Xs 0] [lindex $Ys 0] [lindex $Xs 1] [lindex $Ys 1]"
close $F
set Ports [get_ports -quiet *]
set F [open PortInventory.tsv w];puts $F "port\tdirection"
foreach_in_collection P $Ports {
    set Name [get_object_name $P]
    # PG nets are created without signal ports. If a power port appears, require explicit review.
    if {$Name in {VDD VSS VDDCE VDDPE VSSE}} {error "Unexpected top PG port needs separate handling: $Name"}
    puts $F "$Name\t[get_attribute $P direction]"
}
close $F
PrRecord IO_PLAN [exec python3 [file join [file dirname [info script]] PinPlan.py] [pwd]]
PrStep io_block_rules [list set_block_pin_constraints -self -allowed_layers {M3 M4} \
    -corner_keepout_distance 20 -pin_spacing_distance 0.84 -stacking_allowed none -hard_constraints location]
source PinPlan.tcl
PrStep io_place [list place_pins -self]
# Save before detailed terminal collection or checks: a failed audit must retain the result.
PrStep save_io_block [list save_block]
PrStep save_io_library [list save_lib]
PrStep write_io_def [list write_def placed_707cd7f.def]
set F [open PortTerminalGeometry.tsv w]
puts $F "port\tterminal\tx1\ty1\tx2\ty2\tlayers"
foreach_in_collection P $Ports {
    set T [get_terminals -of_objects $P]
    if {[sizeof_collection $T]!=1} {error "Expected one physical signal terminal per port: [get_object_name $P]"}
    puts $F "[get_object_name $P]\t[get_object_name $T]\t[join [IoBox $T] \t]\t[IoLayers $T]"
}
close $F
PrNeed check_pin_placement {}
PrStep native_pin_check [list redirect pin_placement_check.rpt [list check_pin_placement]]
# Collect the 120 macros' actual PG geometry for the next independent PG stage.
# Collection errors remain visible and do not masquerade as power connectivity success.
set F [open MacroPgGeometry.tsv w]
puts $F "instance\tref\tpin\tshape\tlayers\tx1\ty1\tx2\ty2\tstatus"
set MacroPgErrors 0
foreach_in_collection C [get_cells -hierarchical -filter {ref_name == RAMSP1024X16 || ref_name == RAMSP4096X16}] {
    set CName [get_object_name $C];set Ref [get_attribute $C ref_name]
    set Count 0
    if {[catch {
        foreach_in_collection P [get_pins -physical_context -of_objects $C] {
            set Name [get_object_name $P];set Base [lindex [split $Name /] end]
            if {$Base ni {VDD VSS VDDCE VDDPE VSSE}} {continue}
            incr Count
            set Shapes [get_shapes -of_objects $P]
            if {[sizeof_collection $Shapes]==0} {
                puts $F "$CName\t$Ref\t$Base\tPIN_BBOX\t[IoLayers $P]\t[join [IoBox $P] \t]\tPIN_BBOX_ONLY_REVIEW"
            } else {
                foreach_in_collection S $Shapes {
                    puts $F "$CName\t$Ref\t$Base\t[get_object_name $S]\t[IoLayers $S]\t[join [IoBox $S] \t]\tSHAPE_CAPTURED"
                }
            }
        }
        if {$Count==0} {error "No PG pins enumerated"}
    } Why]} {
        incr MacroPgErrors
        puts $F "$CName\t$Ref\tERROR\t-\t-\t-\t-\t-\t-\t$Why"
    }
}
close $F
PrRecord MACRO_PG_GEOMETRY_ERRORS $MacroPgErrors
PrRecord PG_STATUS PITCH42_CANDIDATE_SAVED_NOT_COMPILED_OR_CONNECTED_ACCEPTANCE
PrRecord IO_STATUS NATIVE_TERMINALS_EXPORTED_FOR_INDEPENDENT_COORDINATE_VALIDATION
