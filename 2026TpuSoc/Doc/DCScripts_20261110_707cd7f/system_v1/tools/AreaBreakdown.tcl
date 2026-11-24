# Disjoint physical-library leaf areas; do not sum inclusive hierarchy reports.
proc AreaClass {Name Ref} {
    if {[string first "u_e203_cpu/u_e203_nice_core/" $Name]==0} {
        if {$Ref eq "RAMSP1024X16"} {return ACCELERATOR_PRIVATE_SRAM}
        if {$Ref eq "RAMSP4096X16"} {error "Unexpected shared macro inside accelerator"}
        return ACCELERATOR_LOGIC_AND_INTERFACES
    }
    if {$Ref eq "RAMSP1024X16"} {error "Private SRAM outside frozen accelerator"}
    if {$Ref eq "RAMSP4096X16"} {
        if {[string first "u_e203_srams/u_e203_itcm_ram/" $Name]==0} {return SHARED_ITCM_MACROS}
        if {[string first "u_e203_srams/u_e203_dtcm_ram/" $Name]==0} {return SHARED_DTCM_MACROS}
        error "Shared macro outside expected TCM boundaries"
    }
    if {[string first "u_e203_cpu/" $Name]==0} {return REUSED_CPU_AND_INTERNAL_ICB_LOGIC}
    if {[string first "u_e203_srams/" $Name]==0} {return SHARED_TCM_BINDING_LOGIC}
    return OTHER_SYSTEM_LOGIC
}
proc WriteAreaBreakdown {Out} {
    set Keys {ACCELERATOR_LOGIC_AND_INTERFACES ACCELERATOR_PRIVATE_SRAM REUSED_CPU_AND_INTERNAL_ICB_LOGIC SHARED_ITCM_MACROS SHARED_DTCM_MACROS SHARED_TCM_BINDING_LOGIC OTHER_SYSTEM_LOGIC}
    foreach Key $Keys {set Area($Key) 0.0; set Count($Key) 0}
    set Total 0.0
    array set Cache {}
    foreach_in_collection Cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
        set Ref [get_attribute $Cell ref_name]
        if {$Ref in {**logic_0** **logic_1**}} {continue}
        set Key [AreaClass [get_object_name $Cell] $Ref]
        if {![info exists Cache($Ref)]} {
            set LibCell [get_lib_cells -quiet */$Ref]
            if {[sizeof_collection $LibCell]!=1} {error "Ambiguous/missing area $Ref"}
            set Value [get_attribute $LibCell area]
            if {![string is double -strict $Value] || !($Value>=0 && $Value<1e12)} {error "Invalid area $Ref"}
            set Cache($Ref) $Value
        }
        set Value $Cache($Ref)
        set Area($Key) [expr {$Area($Key)+$Value}]
        incr Count($Key)
        set Total [expr {$Total+$Value}]
    }
    if {$Count(ACCELERATOR_PRIVATE_SRAM)!=56 || $Count(SHARED_ITCM_MACROS)!=32 || $Count(SHARED_DTCM_MACROS)!=32} {
        error "Area inventory must contain private56/ITCM32/DTCM32 macros"
    }
    set Budget [expr {$Area(ACCELERATOR_LOGIC_AND_INTERFACES)+$Area(ACCELERATOR_PRIVATE_SRAM)}]
    if {$Total<=0 || $Budget<=0} {error "Empty area accounting"}
    set F [open [file join $Out area_breakdown.tsv] w]
    puts $F "component\tleaf_count\tarea_um2\tarea_mm2\tin_accelerator_budget"
    foreach Key $Keys {
        set Included [expr {[string first "ACCELERATOR_" $Key]==0}]
        puts $F "$Key\t$Count($Key)\t[format %.9f $Area($Key)]\t[format %.12f [expr {$Area($Key)/1e6}]]\t$Included"
        puts "AREA_COMPONENT: $Key area_mm2=[format %.9f [expr {$Area($Key)/1e6}]] leaves=$Count($Key) budget=$Included"
    }
    close $F
    set F [open [file join $Out area_totals.txt] w]
    puts $F "SYSTEM_AREA_UM2: $Total"
    puts $F "ACCELERATOR_BUDGET_AREA_UM2: $Budget"
    puts $F "SHARED_CAPACITY_BYTES: 524288"
    puts $F "SHARED_ITCM_BYTES: 262144"
    puts $F "SHARED_DTCM_BYTES: 262144"
    puts $F "PRIVATE_CAPACITY_BYTES: 114688"
    puts $F "BOUNDARY: e203_cpu_top; external fixed peripherals excluded; SRAM bank/mux binding logic listed separately"
    close $F
}
