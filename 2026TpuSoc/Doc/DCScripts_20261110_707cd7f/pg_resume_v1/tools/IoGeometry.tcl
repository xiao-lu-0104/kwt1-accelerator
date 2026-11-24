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
