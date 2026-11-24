# Apply AFTER initial mapping so each synchronizer bit has a real cell and D pin.
if {$Top eq "E203Tpu"} {
    # Check both stages after initial mapping and again after optimization. No global
    # asynchronous clock group; every bundled-data path keeps a delay bound.
    set Sync [FindCells {(RequestSynchronizer|AcknowledgeSynchronizer)_reg\[[01]\]$}]
    set First [FindCells {(RequestSynchronizer|AcknowledgeSynchronizer)_reg\[0\]$}]
    if {[sizeof_collection $Sync] != 8 || [sizeof_collection $First] != 4} {
        error "Expected eight synchronizer flops and four first stages"
    }
    set_dont_touch $Sync true
    foreach_in_collection Cell $First {
        set D ""
        foreach_in_collection Pin [get_pins -of_objects $Cell] {
            if {[string match */D [get_object_name $Pin]]} {set D [add_to_collection $D $Pin]}
        }
        if {[sizeof_collection $D] != 1} {error "Missing synchronizer D pin"}
        set_false_path -to $D
    }
    foreach {Channel Budget} [list RequestChannel 6.666667 ResponseChannel $CpuPeriod] {
        set FromCells [FindCells "${Channel}/SourcePayload_reg"]
        set ToCells [FindCells "${Channel}/DestinationData_reg"]
        if {![sizeof_collection $FromCells] || ![sizeof_collection $ToCells]} {error "Missing $Channel data registers"}
        set From [RegisterPins $FromCells clock]
        set To [RegisterPins $ToCells data]
        # Synopsys SDC syntax (not Vivado -datapath_only). Max/min delay replace
        # the fictitious phase relationship ONLY on the handshake payload bus.
        set_max_delay $Budget -ignore_clock_latency -from $From -to $To
        set_min_delay 0.000 -ignore_clock_latency -from $From -to $To
        group_path -name $Channel -from $From -to $To
        puts "CDC_BUDGET: $Channel max=$Budget ns; min=0 ns; handshake payload only"
    }
}
