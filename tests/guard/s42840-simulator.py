# section 42840
FAMILY = "simulator"
if os.name != "nt":
    register_simulator_boot_cases()
    register_simulator_hold_cases()
    register_simulator_bypass_cases()
    # LOG_CHECKS_EXTRA joined LOG_CHECKS above this section, so the override checks join LOG_CHECKS here.
    for sim_timed in (False, True):
        sim_label = ("simulator: an owner override lifts a raw boot until it ends (a timed override)"
                     if sim_timed else
                     "simulator: an owner override lifts a raw boot once (a one-act override)")
        LOG_FAMILY[sim_label] = FAMILY
        LOG_CHECKS = LOG_CHECKS + ((sim_label, sim_bypass_override_check(sim_timed)),)
    sim_route_label = "simulator: an owner override lifts a test of a shut-down device (simulator-boot-route)"
    LOG_FAMILY[sim_route_label] = FAMILY
    LOG_CHECKS = LOG_CHECKS + ((sim_route_label, sim_route_override_check()),)
    sim_lease_label = "simulator: an owner override lifts an MCP launch of a shut-down device (simulator-boot-lease)"
    LOG_FAMILY[sim_lease_label] = FAMILY
    LOG_CHECKS = LOG_CHECKS + ((sim_lease_label, sim_lease_override_check()),)
    lease_dead_case, lease_ps_counts = register_simulator_lease_cases()
    lease_write_label = "simulator: the lease read writes nothing: a dead lease is refused and sim-lease's files keep their bytes"
    LOG_FAMILY[lease_write_label] = FAMILY
    LOG_CHECKS = LOG_CHECKS + ((lease_write_label, lease_no_write_check(lease_dead_case)),)
    for ps_count_label, ps_count_check in lease_ps_counts:
        LOG_FAMILY[ps_count_label] = FAMILY
        LOG_CHECKS = LOG_CHECKS + ((ps_count_label, ps_count_check),)
    lease_ps_label = "simulator: the lease fixtures' fake ps answers each named pid's start and no other"
    LOG_FAMILY[lease_ps_label] = FAMILY
    LOG_CHECKS = LOG_CHECKS + ((lease_ps_label, lease_fake_ps_check()),)
else:
    skip_case("simulator: the boot, hold and bypass rules, every case of the family", NO_SIMULATOR)



def sim_test_cap_check():
    """No booted-count cap is set anywhere (decision sims-load-brake-only): bin/sim-test has no CAP line, and the
    guard has no SIM_BOOT_CAP. The load brake is the only gate on a boot."""
    with open(os.path.join(HERE, "..", "bin", "sim-test"), encoding="utf-8") as f:
        caps = re.findall(r"^CAP=", f.read(), re.M)
    guard_cap = getattr(_load_guard_module(), "SIM_BOOT_CAP", None)
    if caps or guard_cap is not None:
        return False, "a booted-count cap is still set: bin/sim-test CAP lines %d, guard SIM_BOOT_CAP %r" % (
            len(caps), guard_cap)
    return True, "bin/sim-test and the guard set no booted-count cap"


# LOG_CHECKS_EXTRA has already joined LOG_CHECKS above, so this check joins LOG_CHECKS itself.
SIM_TEST_CAP_LABEL = "simulator: bin/sim-test and the guard set no booted-count cap"
LOG_CHECKS = LOG_CHECKS + ((SIM_TEST_CAP_LABEL, sim_test_cap_check),)
LOG_FAMILY[SIM_TEST_CAP_LABEL] = FAMILY
FIXTURELESS_CHECKS.add(sim_test_cap_check)

