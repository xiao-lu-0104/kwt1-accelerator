# Bulk collection selection avoids per-cell copying while preserving AreaClass.
proc MakePowerGroups {} {
    upvar 1 Groups Groups Keys Keys
    set All [get_cells -hierarchical -filter {is_hierarchical == false}]
    foreach Key $Keys {set Expected($Key) 0}
    foreach_in_collection C $All {
        set Ref [get_attribute $C ref_name]
        if {$Ref in {**logic_0** **logic_1**}} {continue}
        incr Expected([AreaClass [get_object_name $C] $Ref])
    }
    set NonConstant [filter_collection $All {ref_name != **logic_0** && ref_name != **logic_1**}]
    array set Filters {
        ACCELERATOR_LOGIC_AND_INTERFACES {full_name =~ u_e203_cpu/u_e203_nice_core/* && ref_name != RAMSP1024X16 && ref_name != RAMSP4096X16}
        ACCELERATOR_PRIVATE_SRAM {full_name =~ u_e203_cpu/u_e203_nice_core/* && ref_name == RAMSP1024X16}
        REUSED_CPU_AND_INTERNAL_ICB_LOGIC {full_name =~ u_e203_cpu/* && full_name !~ u_e203_cpu/u_e203_nice_core/*}
        SHARED_ITCM_MACROS {full_name =~ u_e203_srams/u_e203_itcm_ram/* && ref_name == RAMSP4096X16}
        SHARED_DTCM_MACROS {full_name =~ u_e203_srams/u_e203_dtcm_ram/* && ref_name == RAMSP4096X16}
        SHARED_TCM_BINDING_LOGIC {full_name =~ u_e203_srams/* && ref_name != RAMSP4096X16 && ref_name != RAMSP1024X16}
        OTHER_SYSTEM_LOGIC {full_name !~ u_e203_cpu/* && full_name !~ u_e203_srams/*}
    }
    foreach Key $Keys {
        set Groups($Key) [filter_collection $NonConstant $Filters($Key)]
        if {[sizeof_collection $Groups($Key)] != $Expected($Key)} {
            error "Bulk power grouping count differs from AreaClass: $Key"
        }
        foreach_in_collection C $Groups($Key) {
            if {[AreaClass [get_object_name $C] [get_attribute $C ref_name]] ne $Key} {
                error "Bulk power grouping membership mismatch: $Key [get_object_name $C]"
            }
        }
        PowerMark "GROUP_SELECTED $Key count=$Expected($Key)"
    }
}
