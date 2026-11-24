# Read the same DDC and SAIF; inspect object connections without changing activity.
proc OptionalAuditReport {Path Body} {
    if {[catch {uplevel 1 [list redirect $Path $Body]} Why]} {
        set F [open ${Path}.error.txt w]; puts $F "$Why\n$::errorInfo"; close $F
        puts "OPTIONAL_AUDIT_REPORT_UNAVAILABLE: $Path"
    }
}
proc FlatText {Value} {return [string map {\t { } \r { } \n { }} $Value]}
proc OptionalAttribute {Object Attribute} {
    if {[catch {get_attribute -quiet $Object $Attribute} Value]} {return "<unavailable>"}
    return [FlatText $Value]
}
if {[catch {
    cd $::env(TPU_OBJECT_CASE)
    set target_library [list $::env(TPU_STDCELL_DB)]
    set link_library [concat [list *] $target_library [list $::env(TPU_SRAM_DB)]]
    read_ddc $::env(TPU_POWER_DDC)
    current_design e203_subsys_nice_core
    if {![link]} {error "Frozen candidate link failed"}
    set Clocks [all_clocks]
    if {[sizeof_collection $Clocks]!=1 || abs([get_attribute $Clocks period]-6.666667)>0.000001} {
        error "Original clock constraints changed"
    }
    if {[sizeof_collection [get_cells -hierarchical -filter {ref_name == RAMSP1024X16}]]!=56} {
        error "Reviewed SRAM count changed"
    }
    reset_switching_activity -all
    if {[read_saif -input $::env(TPU_OBJECT_SAIF) -instance_name SharedTest/Cpu/u_e203_cpu/u_e203_nice_core -verbose] eq "0"} {
        error "SAIF annotation failed"
    }
    redirect coverage.rpt {report_saif -hierarchy}
    redirect missing.rpt {report_saif -hierarchy -missing}
    foreach Command {get_switching_activity report_activity report_saif report_power_calculation} {
        if {[llength [info commands $Command]]} {
            OptionalAuditReport ${Command}_help.txt {help $Command}
            if {[llength [info commands man]]} {OptionalAuditReport ${Command}_manual.txt {man $Command}}
        }
    }
    if {[llength [info commands man]]} {OptionalAuditReport PWR19_manual.txt {man PWR-19}}
    OptionalAuditReport activity_detail.rpt {report_activity -verbose}
    OptionalAuditReport net_attributes.txt {list_attributes -application -class net}
    set Nets [dict create]
    foreach_in_collection Item [get_nets -hierarchical] {dict set Nets [get_object_name $Item] $Item}
    set Cells [dict create]
    foreach_in_collection Item [get_cells -hierarchical] {dict set Cells [get_object_name $Item] $Item}
    set Ports [dict create]
    set NetPorts [dict create]
    foreach_in_collection Item [get_ports *] {
        dict set Ports [get_object_name $Item] $Item
        foreach_in_collection Net [get_nets -quiet -of_objects $Item] {
            dict lappend NetPorts [get_object_name $Net] $Item
        }
    }
    set Pins [dict create]
    # Only build the larger pin index if the request set needs it.
    set F [open objects.tsv r]; set Requests [split [read $F] "\n"]; close $F
    set NeedPins 0
    foreach Line [lrange $Requests 1 end] {
        if {$Line eq ""} {continue}
        set Fields [split $Line "\t"]
        if {[lindex $Fields 1] eq "PIN" || ([lindex $Fields 1] eq "AUTO" && ![dict exists $Nets [lindex $Fields 2]])} {set NeedPins 1}
    }
    if {$NeedPins} {
        foreach_in_collection Item [get_pins -hierarchical] {dict set Pins [get_object_name $Item] $Item}
    }
    set F [open object_connections.tsv w]
    puts $F "id\tkind\tname\treason\tstatus\tinput_pins\toutput_pins\tinout_pins\ttop_ports\tport_query\tdriver_refs\tsink_refs\tconstant_value\tswitching_activity"
    set Details [open connection_details.tsv w]
    puts $Details "id\tobject\tneighbor\tdirection\treference\thierarchical"
    set Seen 0
    foreach Line [lrange $Requests 1 end] {
        if {$Line eq ""} {continue}
        lassign [split $Line "\t"] Id Kind Name Reason
        set Object ""; set Status ABSENT_FROM_DDC_INDEX; set In 0; set Out 0; set Io 0
        set TopCount -1; set PortQuery NOT_RUN; set Drivers {}; set Sinks {}; set Constant ""; set Activity ""
        if {$Kind ne "PIN" && [dict exists $Nets $Name]} {
            set Object [dict get $Nets $Name]; set Status NET_FOUND
            foreach_in_collection Pin [get_pins -quiet -of_objects $Object] {
                set Direction [get_attribute $Pin direction]
                set Owner [get_cells -quiet -of_objects $Pin]
                set Ref ""; set Hier ""
                if {[sizeof_collection $Owner]==1} {
                    set Ref [get_attribute $Owner ref_name]
                    set Hier [get_attribute $Owner is_hierarchical]
                }
                if {$Direction eq "in"} {incr In; lappend Sinks $Ref}
                if {$Direction eq "out"} {incr Out; lappend Drivers $Ref}
                if {$Direction eq "inout"} {incr Io}
                puts $Details "$Id\t$Name\t[get_object_name $Pin]\t$Direction\t$Ref\t$Hier"
            }
            set PortQuery OK; set TopCount 0
            if {[dict exists $NetPorts $Name]} {
                set ConnectedPorts [dict get $NetPorts $Name]
                set TopCount [llength $ConnectedPorts]
                foreach Port $ConnectedPorts {
                    puts $Details "$Id\t$Name\t[get_object_name $Port]\t[get_attribute $Port direction]\t<TOP_PORT>\tfalse"
                }
            }
            set Constant [OptionalAttribute $Object constant_value]
            set Activity [OptionalAttribute $Object switching_activity]
        } elseif {[dict exists $Pins $Name]} {
            set Object [dict get $Pins $Name]; set Status PIN_FOUND
            set Activity [OptionalAttribute $Object switching_activity]
        } elseif {[dict exists $Cells $Name]} {
            set Object [dict get $Cells $Name]; set Status CELL_FOUND
        } elseif {[dict exists $Ports $Name]} {
            set Object [dict get $Ports $Name]; set Status PORT_FOUND
        }
        puts $F "$Id\t$Kind\t$Name\t$Reason\t$Status\t$In\t$Out\t$Io\t$TopCount\t$PortQuery\t[join [lsort -unique $Drivers] ,]\t[join [lsort -unique $Sinks] ,]\t$Constant\t$Activity"
        if {[string first CLOCK_SOURCE_REVIEW $Reason]>=0 && $Object ne "" && [llength [info commands get_switching_activity]]} {
            OptionalAuditReport clock_${Id}_toggle.txt {puts [get_switching_activity -toggle_rate $Object]}
            OptionalAuditReport clock_${Id}_probability.txt {puts [get_switching_activity -static_probability $Object]}
        }
        incr Seen
    }
    close $F; close $Details
    puts "ACTIVITY_OBJECT_AUDIT_DDC_COMPLETE: queries=$Seen; connections inspected; no activity override or design mutation"
} Why]} {
    puts stderr "ACTIVITY_OBJECT_AUDIT_ERROR: $Why"
    puts stderr $::errorInfo
    exit 1
}
exit 0
