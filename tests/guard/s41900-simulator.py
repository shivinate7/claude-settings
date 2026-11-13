# section 41900
FAMILY = "simulator"
#
# Owner rulings. A boot is an `xcodebuild -destination` that names a shut-down simulator, or the
# simulator MCP control tool's `launch` naming a shut-down device. The cap and twin rules judge only
# those. A raw `xcrun simctl boot` is refused by simulator-boot-bypass before either is read.
#   simulator-boot-cap   refuses a boot while the machine is busy by the load brake's bar, naming the reading.
#                        The booted count does not decide it (decision sims-load-brake-only); a cloud session is not braked.
#   simulator-boot-twin  refuses a boot while an IDLE booted device of the same deviceTypeIdentifier
#                        and runtime exists, naming its UDID. "Idle" is the shutdown tier's own
#                        test (owner 2026-10-10): booted 1 hour or more, no outside holder process,
#                        Simulator.app and Xcode.app not running, both reads readable. "Booted 1
#                        hour" is the newest line in <config>/state/sim-boots.jsonl. Unrecorded is
#                        not idle.
#   A simulator case runs under a machine reading: its `load` (see add in hooks/test_guard.py), else the neutral one.
#   simulator-boot-route   refuses an xcodebuild -destination that names a shut-down device, judged after
#                          cap and twin. The remedy is sim-test for `test`, else the generic destination.
#   simulator-boot-lease   refuses an MCP launch of a shut-down device, held lock or not: a launch needs a lease,
#                          and `sim-lease` is the Mac's one queue for phone simulators (decision sim-test-is-the-one-boot-path,
#                          ruling 5). Judged after cap and twin. The reason names sim-test and the lease. A booted
#                          device is never refused.
# A fake `xcrun` and `ps` on PATH answer `simctl list devices` and the process table. A reason names
# UDIDs and device names only, never the config folder or the record file.

SIM_MCP = "mcp__Claude_Code_iOS_Simulator__control"
SIM_RT = "com.apple.CoreSimulator.SimRuntime.iOS-26-0"
SIM_RT_OLD = "com.apple.CoreSimulator.SimRuntime.iOS-25-0"
SIM_TYPE_PRO = "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro"
SIM_TYPE_AIR = "com.apple.CoreSimulator.SimDeviceType.iPad-Air"
SIM_TYPE_MINI = "com.apple.CoreSimulator.SimDeviceType.iPhone-16-Mini"
SIM_UA = "1A2B3C4D-0000-4000-8000-00000000000A"   # Alpha Pro, booted
SIM_UB = "1A2B3C4D-0000-4000-8000-00000000000B"   # Beta Air, booted
SIM_UC = "1A2B3C4D-0000-4000-8000-00000000000C"   # Gamma Mini, shut down
SIM_UT0 = "1A2B3C4D-0000-4000-8000-0000000000D0"  # Idle Pro, booted: the twin
SIM_UT1 = "1A2B3C4D-0000-4000-8000-0000000000D1"  # Twin Pro, shut down
SIM_UE = "1A2B3C4D-0000-4000-8000-00000000000E"  # Named-UDID Mini, booted: its name is SIM_UC
SIM_UF = "1A2B3C4D-0000-4000-8000-00000000000F"  # Delta, shut down on RT only
SIM_UDA = "1A2B3C4D-0000-4000-8000-0000000000D3"  # Delta, shut down on RT_OLD (25.0), listed first
SIM_UDB = "1A2B3C4D-0000-4000-8000-0000000000D4"  # Delta, shut down on RT (26.0), listed second
SIM_RT17 = "com.apple.CoreSimulator.SimRuntime.iOS-17-0"
SIM_U17 = "1A2B3C4D-0000-4000-8000-0000000000D5"  # Delta, booted on RT17 (17.0): the copy OS=17.0 names
# The launchd_sim of each booted device: the pid and the start time the fake `ps` gives it, and the
# same pair in the boot record. A record that names another pid or start time is an older boot.
SIM_UG = "1A2B3C4D-0000-4000-8000-0000000000D7"  # Gamma Pad, booted in the lease section's three-booted case
LAUNCHD_PID = {SIM_UA: 4001, SIM_UB: 4002, SIM_UT0: 4003, SIM_UE: 4004, SIM_U17: 4005, SIM_UG: 4006}
LSTART = "Sat Oct 10 07:00:00 2026"
# The machine readings a simulator case runs under (see decide, and add's `load`). SIM_BUSY is over the memory bar of
# the load brake (85%), SIM_UNREAD leaves every reading unread, which counts as normal. SIM_DISK_BUSY is over the disk
# bar only (9.4 GB free of 926: under the busy line, above the full line). SIM_BOTH_BUSY is over both bars.
SIM_BUSY = {"memory_pct": 91.7, "disk_free_gb": 500.0, "disk_total_gb": 926.0}
SIM_DISK_BUSY = {"memory_pct": 40.0, "disk_free_gb": 9.4, "disk_total_gb": 926.0}
SIM_BOTH_BUSY = {"memory_pct": 91.7, "disk_free_gb": 9.4, "disk_total_gb": 926.0}
SIM_UNREAD = {"memory_pct": None, "disk_free_gb": None, "disk_total_gb": None}
LAUNCHD_CMD = ("/Library/Developer/PrivateFrameworks/CoreSimulator.framework/Versions/A/"
               "Resources/launchd_sim")


def sim_iso(seconds_ago):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds_ago))


# Step sim-machine-lock (one lock per Mac, roadmap 55264090): a raw simctl boot is refused.
def sim_boot_by_destination(udid):
    """An xcodebuild destination that boots `udid`, so the cap and twin rules judge the boot."""
    return "xcodebuild build -scheme App -destination 'platform=iOS Simulator,id=" + udid + "'"


def make_fake_xcrun(folder, rows, pid_starts=None, ps_log=None):
    """A stand-in `xcrun` that answers every call with the device list in ROWS. PID_STARTS and PS_LOG are make_fake_ps's.

    ROWS are (udid, name, state, deviceTypeIdentifier, runtime). The fake prints with the shell's
    printf builtin, so it needs no other program on the PATH. Windows has no xcrun, so no case
    using this runs there (see register_simulator_boot_cases).
    """
    grouped = {}
    for udid, name, state, dtype, runtime in rows:
        grouped.setdefault(runtime, []).append({
            "udid": udid, "name": name, "state": state, "deviceTypeIdentifier": dtype,
            "isAvailable": True})
    text = json.dumps({"devices": grouped})
    assert "'" not in text, "the printf body is single-quoted"
    path = os.path.join(folder, "xcrun")
    write(path, "#!/bin/sh\nprintf '%s' '" + text + "'\n")
    os.chmod(path, 0o755)
    # A quiet process table beside it: readable, with each booted device's launchd_sim and no holder.
    make_fake_ps(folder, [("1", "0", "0", "/sbin/launchd")] + [
        (str(LAUNCHD_PID[udid]), "1", "0", LAUNCHD_CMD + " " + udid)
        for udid, _, state, _, _ in rows if state == "Booted"], pid_starts=pid_starts, ps_log=ps_log)
    return folder


def write_sim_records(config_dir, records):
    """The boot record, one JSON line per boot: {udid, name, deviceTypeIdentifier, runtime, at,
    launchd_pid, launchd_start}. The last two name the boot's launchd_sim, as `ps` prints them."""
    write(os.path.join(config_dir, "state", "sim-boots.jsonl"),
          "".join(json.dumps(r) + "\n" for r in records))


def register_simulator_boot_cases():
    twin_idle_rec = {"udid": SIM_UT0, "name": "Idle Pro", "deviceTypeIdentifier": SIM_TYPE_PRO,
                     "runtime": SIM_RT, "at": sim_iso(2 * 3600),
                     "launchd_pid": LAUNCHD_PID[SIM_UT0], "launchd_start": LSTART}

    def twin_rows(state_of_ut0_runtime=SIM_RT, type_of_ut0=SIM_TYPE_PRO):
        return [(SIM_UT0, "Idle Pro", "Booted", type_of_ut0, state_of_ut0_runtime),
                (SIM_UT1, "Twin Pro", "Shutdown", SIM_TYPE_PRO, SIM_RT)]

    fixtures = {
        # two booted, one shut down (a different device type, so the twin rule stays quiet)
        "cap": (make_fake_xcrun(os.path.join(ROOT, "sim_cap"), [
            (SIM_UA, "Alpha Pro", "Booted", SIM_TYPE_PRO, SIM_RT),
            (SIM_UB, "Beta Air", "Booted", SIM_TYPE_AIR, SIM_RT),
            (SIM_UC, "Gamma Mini", "Shutdown", SIM_TYPE_MINI, SIM_RT)]), None),
        # one booted: a second may still boot
        "one": (make_fake_xcrun(os.path.join(ROOT, "sim_one"), [
            (SIM_UA, "Alpha Pro", "Booted", SIM_TYPE_PRO, SIM_RT),
            (SIM_UC, "Gamma Mini", "Shutdown", SIM_TYPE_MINI, SIM_RT)]), None),
        "twin": (make_fake_xcrun(os.path.join(ROOT, "sim_twin"), twin_rows()),
                 [twin_idle_rec]),
        "twin_recent": (make_fake_xcrun(os.path.join(ROOT, "sim_twin_recent"), twin_rows()),
                        [dict(twin_idle_rec, at=sim_iso(10 * 60))]),
        "twin_unrecorded": (make_fake_xcrun(os.path.join(ROOT, "sim_twin_unrecorded"), twin_rows()),
                            []),
        "twin_other_runtime": (make_fake_xcrun(os.path.join(ROOT, "sim_twin_other_runtime"),
                                               twin_rows(state_of_ut0_runtime=SIM_RT_OLD)),
                               [dict(twin_idle_rec, runtime=SIM_RT_OLD)]),
        "twin_other_type": (make_fake_xcrun(os.path.join(ROOT, "sim_twin_other_type"),
                                            twin_rows(type_of_ut0=SIM_TYPE_AIR)),
                            [dict(twin_idle_rec, deviceTypeIdentifier=SIM_TYPE_AIR)]),
        # The twin was booted 2 hours ago and shut down, then booted by hand: the live launchd_sim
        # has a new pid and start time, and the record is the older boot.
        "twin_rebooted": (make_fake_xcrun(os.path.join(ROOT, "sim_twin_rebooted"), twin_rows()),
                          [dict(twin_idle_rec, launchd_pid=4900,
                                launchd_start="Fri Oct 9 09:00:00 2026")]),
        # One idle recorded twin (Idle Pro, 26.0) and Delta shut down on two runtimes. The fake xcrun
        # groups rows by runtime in first-seen order, so the 25.0 copy comes first in the device list:
        # a check of only the first hit sees 25.0, not the twin's 26.0.
        "twin_two_runtimes": (make_fake_xcrun(os.path.join(ROOT, "sim_twin_two_rt"), [
            (SIM_UDA, "Delta", "Shutdown", SIM_TYPE_PRO, SIM_RT_OLD),
            (SIM_UT0, "Idle Pro", "Booted", SIM_TYPE_PRO, SIM_RT),
            (SIM_UDB, "Delta", "Shutdown", SIM_TYPE_PRO, SIM_RT)]), [twin_idle_rec]),
        # Two booted, plus a booted device named like the shut-down target's UDID.
        "cap_udid_name": (make_fake_xcrun(os.path.join(ROOT, "sim_cap_udid_name"), [
            (SIM_UA, "Alpha Pro", "Booted", SIM_TYPE_PRO, SIM_RT),
            (SIM_UB, "Beta Air", "Booted", SIM_TYPE_AIR, SIM_RT),
            (SIM_UE, SIM_UC, "Booted", SIM_TYPE_MINI, SIM_RT),
            (SIM_UC, "Gamma Mini", "Shutdown", SIM_TYPE_MINI, SIM_RT)]), None),
        # Two booted, plus a Gamma Mini booted on one runtime beside a shut-down one on
        # another runtime.
        "cap_name_split": (make_fake_xcrun(os.path.join(ROOT, "sim_cap_name_split"), [
            (SIM_UA, "Alpha Pro", "Booted", SIM_TYPE_PRO, SIM_RT),
            (SIM_UB, "Beta Air", "Booted", SIM_TYPE_AIR, SIM_RT),
            (SIM_UE, "Gamma Mini", "Booted", SIM_TYPE_MINI, SIM_RT),
            (SIM_UC, "Gamma Mini", "Shutdown", SIM_TYPE_MINI, SIM_RT_OLD)]), None),
        # Exactly two booted: the booted Gamma Mini is on RT (26.0), its shut-down
        # twin on RT_OLD (25.0). OS= in a -destination picks which copy the boot names.
        "cap_os_split": (make_fake_xcrun(os.path.join(ROOT, "sim_cap_os_split"), [
            (SIM_UA, "Alpha Pro", "Booted", SIM_TYPE_PRO, SIM_RT),
            (SIM_UE, "Gamma Mini", "Booted", SIM_TYPE_MINI, SIM_RT),
            (SIM_UC, "Gamma Mini", "Shutdown", SIM_TYPE_MINI, SIM_RT_OLD)]), None),
        # Exactly two booted. Delta is shut down on one runtime only.
        "cap_latest": (make_fake_xcrun(os.path.join(ROOT, "sim_cap_latest"), [
            (SIM_UA, "Alpha Pro", "Booted", SIM_TYPE_PRO, SIM_RT),
            (SIM_UE, "Gamma Mini", "Booted", SIM_TYPE_MINI, SIM_RT),
            (SIM_UF, "Delta", "Shutdown", SIM_TYPE_AIR, SIM_RT)]), None),
        # Delta shut down on 25.0 (listed first) and booted on 17.0. OS=17.0 names only the booted copy, so a
        # destination that picks the 17.0 runtime boots nothing.
        "os_two_rt": (make_fake_xcrun(os.path.join(ROOT, "sim_os_two_rt"), [
            (SIM_UDA, "Delta", "Shutdown", SIM_TYPE_PRO, SIM_RT_OLD),
            (SIM_U17, "Delta", "Booted", SIM_TYPE_PRO, SIM_RT17)]), None),
    }
    cfgs = {}
    for name, (folder, records) in fixtures.items():
        cfg = os.path.join(ROOT, "simcfg_" + name)
        os.makedirs(cfg, exist_ok=True)
        if records is not None:
            write_sim_records(cfg, records)
        cfgs[name] = (folder, cfg)

    def on(name):
        folder, cfg = cfgs[name]
        return folder + os.pathsep + PY_PATH, cfg

    cap_path, cap_cfg = on("cap")
    one_path, one_cfg = on("one")
    twin_path, twin_cfg = on("twin")
    os_two_path, os_two_cfg = on("os_two_rt")

    # Rule simulator-boot-cap. The reason names both booted UDIDs.
    # The bypass rule judges a raw boot on its text, before the cap rule reads the device list.
    sh("boot a third simulator with two booted: bash simctl boot, bypass first",
       "xcrun simctl boot " + SIM_UC, "deny", rule="simulator-boot-bypass",
       env_path=cap_path, config=cap_cfg, carries="sim-test")
    sh("boot a third simulator with two booted and a busy machine: xcodebuild destination",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,name=Gamma Mini'",
       "deny", rule="simulator-boot-cap", load=SIM_BUSY, env_path=cap_path, config=cap_cfg,
       carries=(SIM_UA, SIM_UB))
    # The refusal's remedy matches the reading that tripped it: memory busy waits, disk busy frees disk space, both do both.
    # The memory-only case is the control: its remedy is the wait alone.
    sh("boot a third simulator with a busy memory and a disk under the bar: the remedy waits, names no disk space",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,name=Gamma Mini'",
       "deny", rule="simulator-boot-cap", load=SIM_BUSY, env_path=cap_path, config=cap_cfg,
       carries=("memory 91.7%", "until the load"), lacks=("free disk space", "Free disk space"))
    sh("boot a third simulator with a busy disk and a memory under the bar: the remedy frees disk space, no wait",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,name=Gamma Mini'",
       "deny", rule="simulator-boot-cap", load=SIM_DISK_BUSY, env_path=cap_path, config=cap_cfg,
       carries=("disk 9.4 GB free of 926 GB", ("free disk space", "Free disk space")), lacks=("until the load",))
    sh("boot a third simulator with a busy memory and a busy disk: the remedy waits and frees disk space",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,name=Gamma Mini'",
       "deny", rule="simulator-boot-cap", load=SIM_BOTH_BUSY, env_path=cap_path, config=cap_cfg,
       carries=("memory 91.7%", "disk 9.4 GB free of 926 GB", "until the load",
                ("free disk space", "Free disk space")))
    add("boot a third simulator with two booted and a busy machine: simulator MCP launch",
        "deny", rule="simulator-boot-cap", load=SIM_BUSY, tool=SIM_MCP, action="launch", device=SIM_UC,
        env_path=cap_path, config=cap_cfg, carries=(SIM_UA, SIM_UB))
    add("boot a third simulator with two booted and a busy machine: simulator MCP launch names it by udid",
        "deny", rule="simulator-boot-cap", load=SIM_BUSY, tool=SIM_MCP, action="launch", udid=SIM_UC,
        env_path=cap_path, config=cap_cfg, carries=(SIM_UA, SIM_UB))
    add("boot a third simulator with two booted and a busy machine: MCP launch, empty device, udid names it",
        "deny", rule="simulator-boot-cap", load=SIM_BUSY, tool=SIM_MCP, action="launch", device="", udid=SIM_UC,
        env_path=cap_path, config=cap_cfg, carries=(SIM_UA, SIM_UB))
    add("boot a third simulator with two booted and a busy machine: MCP launch, list in device, udid names it",
        "deny", rule="simulator-boot-cap", load=SIM_BUSY, tool=SIM_MCP, action="launch", device=["x"], udid=SIM_UC,
        env_path=cap_path, config=cap_cfg, carries=(SIM_UA, SIM_UB))
    add("boot a third simulator with two booted and a busy machine: MCP launch, dict in udid, device names it",
        "deny", rule="simulator-boot-cap", load=SIM_BUSY, tool=SIM_MCP, action="launch", device=SIM_UC,
        udid={"x": 1}, env_path=cap_path, config=cap_cfg, carries=(SIM_UA, SIM_UB))
    add("boot a third simulator with two booted and a busy machine: MCP launch, lowercase udid",
        "deny", rule="simulator-boot-cap", load=SIM_BUSY, tool=SIM_MCP, action="launch", udid=SIM_UC.lower(),
        env_path=cap_path, config=cap_cfg, carries=(SIM_UA, SIM_UB))
    sh("boot a third simulator with two booted: bash simctl boot, lowercase udid, bypass first",
       "xcrun simctl boot " + SIM_UC.lower(), "deny", rule="simulator-boot-bypass",
       env_path=cap_path, config=cap_cfg, carries="sim-test")
    # A booted device whose name is the shut-down target's UDID must not skip the boot check.
    udid_name_path, udid_name_cfg = on("cap_udid_name")
    add("boot a shut-down device by udid, a booted device is named like that udid: MCP launch",
        "deny", rule="simulator-boot-cap", load=SIM_BUSY, tool=SIM_MCP, action="launch", udid=SIM_UC,
        env_path=udid_name_path, config=udid_name_cfg, carries=(SIM_UA, SIM_UB))
    # A name with one booted copy and one shut-down copy on another runtime is a shut-down hit.
    name_split_path, name_split_cfg = on("cap_name_split")
    add("boot a shut-down copy by name, a booted copy shares the name: MCP launch",
        "deny", rule="simulator-boot-cap", load=SIM_BUSY, tool=SIM_MCP, action="launch", device="Gamma Mini",
        env_path=name_split_path, config=name_split_cfg, carries=(SIM_UA, SIM_UB))
    os_split_path, os_split_cfg = on("cap_os_split")
    # OS=26.0 names the booted copy, so the boot is a no-op: allowed.
    sh("control: OS= picks the booted copy of a name, the boot is a no-op: xcodebuild destination",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,name=Gamma Mini,OS=26.0'",
       "allow", env_path=os_split_path, config=os_split_cfg)
    # OS=25.0 names the shut-down copy on a busy machine: the boot is refused.
    sh("boot the shut-down copy by OS= with the cap full and busy: xcodebuild destination",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,name=Gamma Mini,OS=25.0'",
       "deny", rule="simulator-boot-cap", load=SIM_BUSY, env_path=os_split_path, config=os_split_cfg,
       carries=(SIM_UA, SIM_UE))
    # OS=latest is no version, so it matches no runtime. The guard must not allow a boot on it
    # when the only Delta copy is shut down: a busy machine refuses the boot.
    latest_path, latest_cfg = on("cap_latest")
    sh("boot a shut-down device by name with OS=latest, cap full and busy: xcodebuild destination",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,name=Delta,OS=latest'",
       "deny", rule="simulator-boot-cap", load=SIM_BUSY, env_path=latest_path, config=latest_cfg,
       carries=(SIM_UA, SIM_UE))
    # A numeric OS that matches no copy must not leave zero hits. Delta is shut down on 26.0.
    sh("boot a shut-down device by name with OS=26.0.0, cap full and busy: xcodebuild destination",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,name=Delta,OS=26.0.0'",
       "deny", rule="simulator-boot-cap", load=SIM_BUSY, env_path=latest_path, config=latest_cfg,
       carries=(SIM_UA, SIM_UE))
    sh("boot a shut-down device by name with two OS keys, cap full and busy: xcodebuild destination",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,name=Delta,OS=latest,OS=25.0'",
       "deny", rule="simulator-boot-cap", load=SIM_BUSY, env_path=latest_path, config=latest_cfg,
       carries=(SIM_UA, SIM_UE))
    # Delta is on two runtimes; OS=latest names neither, so every shut-down copy must be judged.
    twin_two_path, twin_two_cfg = on("twin_two_runtimes")
    sh("boot a shut-down copy with an idle twin on its runtime, OS=latest: xcodebuild destination",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,name=Delta,OS=latest'",
       "deny", rule="simulator-boot-twin", env_path=twin_two_path, config=twin_two_cfg,
       carries=(SIM_UT0,))
    # An id= destination names one device. OS=26.0 must not hide a shut-down 25.0 copy from the check.
    sh("boot a shut-down 25.0 copy by id with OS=26.0, cap full and busy: xcodebuild destination",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UC
       + ",OS=26.0'", "deny", rule="simulator-boot-cap", load=SIM_BUSY, env_path=os_split_path,
       config=os_split_cfg, carries=(SIM_UA, SIM_UE))
    # The boot cap follows the machine, not the count (decision sims-load-brake-only). Two booted on a quiet machine:
    # the cap lets the boot through, so the route rule (xcodebuild) and the lease rule (MCP) judge it instead.
    sh("boot a third simulator with two booted, a quiet machine: xcodebuild destination is judged by the route rule",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,name=Gamma Mini'",
       "deny", rule="simulator-boot-route", env_path=cap_path, config=cap_cfg)
    add("boot a third simulator with two booted, a quiet machine: MCP launch is judged by the lease rule",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", device=SIM_UC,
        env_path=cap_path, config=cap_cfg, carries=LEASE_CARRIES)
    # The MCP launch cases from here to the twin section boot through the simulator MCP tool, with no lock
    # held. simulator-boot-route judges only xcodebuild destinations, so an xcodebuild boot of a shut-down
    # device would be refused by it before the cap or twin rule is read. Every MCP launch of a shut-down device
    # is refused by simulator-boot-lease once cap and twin pass, so the refusal here is the lease: it shows
    # that cap and twin did not fire.
    add("lease: one booted, an MCP launch of a shut-down device with no lock is refused by the lease",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", device=SIM_UC,
        env_path=one_path, config=one_cfg, carries=("sim-test", "lease"))
    add("lease: one booted, an MCP launch that names the shut-down device by udid is refused by the lease",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", udid=SIM_UC,
        env_path=one_path, config=one_cfg, carries=("sim-test", "lease"))
    add("lease: an MCP launch of a booted device with no lock is allowed",
        "allow", tool=SIM_MCP, action="launch", device=SIM_UA, env_path=one_path, config=one_cfg)
    # A name that differs from the device's name only in case or in outer spaces still names that device.
    add("lease: an MCP launch naming the shut-down device in lowercase is refused by the lease",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", device="gamma mini",
        env_path=one_path, config=one_cfg, carries=("sim-test", "lease"))
    add("lease: an MCP launch naming the shut-down device with a leading space is refused by the lease",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", device=" Gamma Mini",
        env_path=one_path, config=one_cfg, carries=("sim-test", "lease"))
    add("lease: an MCP launch naming the shut-down device with a trailing space is refused by the lease",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", device="Gamma Mini ",
        env_path=one_path, config=one_cfg, carries=("sim-test", "lease"))
    add("control: an MCP launch of a name no device holds is allowed, the name matches nothing",
        "allow", tool=SIM_MCP, action="launch", device="Zeta Mini", env_path=one_path, config=one_cfg)
    # Devices unreadable: a failing `simctl list` leaves no device list, so the boot rules fail open, the lease too.
    unreadable = os.path.join(ROOT, "sim_unreadable")
    os.makedirs(unreadable, exist_ok=True)
    write(os.path.join(unreadable, "xcrun"), "#!/bin/sh\nexit 1\n")
    os.chmod(os.path.join(unreadable, "xcrun"), 0o755)
    add("control: an MCP launch of a shut-down device with an unreadable device list is allowed (fail open)",
        "allow", tool=SIM_MCP, action="launch", device=SIM_UC,
        env_path=unreadable + os.pathsep + PY_PATH, config=one_cfg)
    sh("boot a second simulator with one booted: bash simctl boot, bypass first",
       "xcrun simctl boot " + SIM_UC, "deny", rule="simulator-boot-bypass",
       env_path=one_path, config=one_cfg, carries="sim-test")
    sh("control: a read of the device list is not a boot",
       "xcrun simctl list devices", "allow", env_path=cap_path, config=cap_cfg)
    # Owner ruling 2026-10-10: the cap counts every booted device. One is recorded and idle, the
    # other is owner-booted and unrecorded; both count.
    mixed_cap_cfg = os.path.join(ROOT, "simcfg_cap_mixed")
    os.makedirs(mixed_cap_cfg, exist_ok=True)
    write_sim_records(mixed_cap_cfg, [sim_boot_record(SIM_UA, "Alpha Pro", SIM_TYPE_PRO, SIM_RT,
                                                      2 * 3600)])
    sh("boot a third simulator: a recorded idle device and an owner-booted one both count",
       sim_boot_by_destination(SIM_UC), "deny", rule="simulator-boot-cap", load=SIM_BUSY,
       env_path=cap_path, config=mixed_cap_cfg, carries=(SIM_UA, SIM_UB))

    # Rule simulator-boot-twin. The reason names the idle twin's UDID.
    sh("boot a device with an idle booted twin: xcodebuild destination by udid",
       sim_boot_by_destination(SIM_UT1), "deny", rule="simulator-boot-twin",
       env_path=twin_path, config=twin_cfg, carries=(SIM_UT0,))
    add("boot a device with an idle booted twin: simulator MCP launch",
        "deny", rule="simulator-boot-twin", tool=SIM_MCP, action="launch", device=SIM_UT1,
        env_path=twin_path, config=twin_cfg, carries=(SIM_UT0,))
    add("boot a device with an idle booted twin: simulator MCP launch names it by udid",
        "deny", rule="simulator-boot-twin", tool=SIM_MCP, action="launch", udid=SIM_UT1,
        env_path=twin_path, config=twin_cfg, carries=(SIM_UT0,))
    # Each launch below is refused by the lease, so the twin rule did not fire: the lease is the rule named.
    add("twin not idle: a twin booted 10 minutes ago does not fire the twin rule; the lease refuses the launch",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", device=SIM_UT1,
        env_path=folder_path("twin_recent"), config=cfgs["twin_recent"][1], carries=("sim-test", "lease"))
    add("twin not idle: an unrecorded booted twin does not fire the twin rule; the lease refuses the launch",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", device=SIM_UT1,
        env_path=folder_path("twin_unrecorded"), config=cfgs["twin_unrecorded"][1], carries=("sim-test", "lease"))
    add("twin not matched: an idle twin on another runtime does not fire the twin rule; the lease refuses",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", device=SIM_UT1,
        env_path=folder_path("twin_other_runtime"), config=cfgs["twin_other_runtime"][1],
        carries=("sim-test", "lease"))
    add("twin not matched: an idle twin of another device type does not fire the twin rule; the lease refuses",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", device=SIM_UT1,
        env_path=folder_path("twin_other_type"), config=cfgs["twin_other_type"][1], carries=("sim-test", "lease"))
    add("twin not idle: a twin booted by hand after its recorded boot does not fire the twin rule; the lease refuses",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", device=SIM_UT1,
        env_path=folder_path("twin_rebooted"), config=cfgs["twin_rebooted"][1], carries=("sim-test", "lease"))

    # Rule simulator-boot-route (decision sim-test-is-the-one-boot-path, ruling 5). An xcodebuild whose
    # -destination names a shut-down simulator is refused after the cap and twin rules. The remedy depends
    # on the action: `test` names sim-test, any other action names the generic destination. A booted
    # device is not a boot, so it is allowed. The "one" fixture holds one booted device and one shut-down
    # device of another type, so neither the cap nor the twin rule judges these commands.
    generic = "generic/platform=iOS Simulator"
    # The remedy is the phrase "Run `sim-test", not the bare word: the refusal's own text also names the
    # sim-test lock, so the bare word would hold whatever remedy the refusal printed.
    sh("route: a test of a shut-down simulator by id names sim-test",
       "xcodebuild test -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UC + "'",
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg, carries="Run `sim-test")
    sh("route: a test with the action after its options, a shut-down simulator by name, names sim-test",
       "xcodebuild -scheme App -destination 'platform=iOS Simulator,name=Gamma Mini' test",
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg, carries="Run `sim-test")
    sh("route: a build of a shut-down simulator names the generic destination",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UC + "'",
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg, carries=generic)
    sh("route: build-for-testing of a shut-down simulator by name names the generic destination",
       "xcodebuild build-for-testing -scheme App -destination 'platform=iOS Simulator,name=Gamma Mini'",
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg, carries=generic)
    sh("route: no action on a shut-down simulator names the generic destination",
       "xcodebuild -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UC + "'",
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg, carries=generic)
    sh("control: a test of a booted simulator by id is allowed",
       "xcodebuild test -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UA + "'",
       "allow", env_path=one_path, config=one_cfg)
    sh("control: a build of a booted simulator by name is allowed",
       "xcodebuild build -scheme App -destination 'platform=iOS Simulator,name=Alpha Pro'",
       "allow", env_path=one_path, config=one_cfg)
    # Order: route is judged after cap and twin, so a test of a shut-down device that either rule
    # refuses names that rule, not simulator-boot-route.
    sh("route is judged after the cap: a test of a shut-down simulator with two booted and a busy machine names the cap",
       "xcodebuild test -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UC + "'",
       "deny", rule="simulator-boot-cap", load=SIM_BUSY, env_path=cap_path, config=cap_cfg, carries=(SIM_UA, SIM_UB))
    sh("route is judged after the twin: a test of a shut-down twin names the idle twin",
       "xcodebuild test -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UT1 + "'",
       "deny", rule="simulator-boot-twin", env_path=twin_path, config=twin_cfg, carries=(SIM_UT0,))

    # The route rule judges an xcodebuild boot wherever it sits: inside a wrapper (bash -c, sh -lc), with a `)`
    # glued to the destination, or after an option with a colon (`-only-testing:X`). Each case pins that the boot
    # is refused with its remedy, since a boot the route misses skips the lock.
    sh("route: a test of a shut-down simulator inside bash -c names sim-test",
       "bash -c \"xcodebuild test -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UC + "'\"",
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg, carries="Run `sim-test")
    sh("route: a test of a shut-down simulator inside sh -lc names sim-test",
       "sh -lc 'xcodebuild test -scheme App -destination \"platform=iOS Simulator,id=" + SIM_UC + "\"'",
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg, carries="Run `sim-test")
    # Its control: a raw boot inside the same wrapper is refused by the bypass rule today, so the wrapper is read.
    sh("route: a raw boot inside bash -c is refused by the bypass rule (control: the wrapper is read)",
       "bash -c \"xcrun simctl boot " + SIM_UC + "\"", "deny", rule="simulator-boot-bypass",
       env_path=one_path, config=one_cfg, carries="sim-test")
    sh("route: a test in a subshell, the closing paren glued to the destination, names sim-test",
       "(cd ios && xcodebuild test -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UC + "')",
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg, carries="Run `sim-test")
    # Its control: the same subshell with the paren apart from the quote. The guard reads this one today, so the
    # glued case fails on the glue, not on the subshell.
    sh("route: a test in a subshell, the closing paren apart from the destination, names sim-test (control)",
       "(cd ios && xcodebuild test -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UC + "' )",
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg, carries="Run `sim-test")
    sh("route: a test with -only-testing before the action names sim-test",
       "xcodebuild -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UC + "' -only-testing:AppTests test",
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg, carries="Run `sim-test")

    # The remedy names sim-test with the xcodebuild arguments only. The shell's redirects and a background `&`
    # are not arguments of xcodebuild, so the remedy holds none of them, whether spaced or glued to a quote.
    sh("route: a test of a shut-down simulator with 2>&1 names sim-test -scheme App, with no redirect word",
       "xcodebuild test -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UC + "' 2>&1",
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg,
       carries="Run `sim-test -scheme App", lacks=("2>&1", ">", "&"))
    sh("route: a test of a shut-down simulator with > out.log names sim-test -scheme App, with no > word",
       "xcodebuild test -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UC + "' > out.log",
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg,
       carries="Run `sim-test -scheme App", lacks=(">",))
    sh("route: a test of a shut-down simulator, the quote glued to a trailing &, names sim-test -scheme App",
       'xcodebuild test -scheme App -destination "platform=iOS Simulator,id=' + SIM_UC + '"&',
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg,
       carries="Run `sim-test -scheme App", lacks=("&",))
    sh("route: a test of a shut-down simulator, the quote glued to a redirect, names sim-test -scheme App",
       'xcodebuild test -scheme App -destination "platform=iOS Simulator,id=' + SIM_UC + '">/dev/null',
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg,
       carries="Run `sim-test -scheme App", lacks=(">",))
    # A boolean flag between the scheme and the action is no option with a value, so the action is still `test`.
    sh("route: a boolean flag before the action, -skipMacroValidation, still names sim-test",
       "xcodebuild -scheme App -skipMacroValidation test -destination 'platform=iOS Simulator,id=" + SIM_UC + "'",
       "deny", rule="simulator-boot-route", env_path=one_path, config=one_cfg, carries="Run `sim-test")
    # OS=17.0 picks the 17.0 copy of Delta, which is booted, so nothing is booted and the route allows. The
    # control is the same destination without the glued paren. Today the glued value reads OS as "17.0)",
    # drops the runtime filter, and judges the shut-down 25.0 copy too.
    sh("route: OS=17.0 in a subshell, its paren glued to the value, judges the 17.0 copy only: booted, so allowed",
       "(cd ios && xcodebuild test -scheme App -destination 'platform=iOS Simulator,name=Delta,OS=17.0')",
       "allow", env_path=os_two_path, config=os_two_cfg)
    sh("control: OS=17.0 with no glued paren judges the 17.0 copy only: booted, so allowed",
       "xcodebuild test -scheme App -destination 'platform=iOS Simulator,name=Delta,OS=17.0'",
       "allow", env_path=os_two_path, config=os_two_cfg)

    # The sim-test lock does not decide an MCP launch: a shut-down device is refused by the lease whether the
    # lock is held or free. So the held case names the lease, and no case reads the lock's age or its holder's
    # liveness. The lock is one fixture, built just before its case.
    def lock_config(name, pid_text):
        cfg = os.path.join(ROOT, "simcfg_lock_" + name)
        lock = os.path.join(cfg, "state", "sim-test.lock")

        def build():
            os.makedirs(lock, exist_ok=True)
            write(os.path.join(lock, "pid"), pid_text + "\n")
        lazy_fixture([cfg], build)
        return cfg

    # The test runner's own pid is alive for as long as the cases run, so the lock is held.
    live_cfg = lock_config("live", str(os.getpid()))
    add("lease: a live lock holder does not lift the lease: an MCP launch of a shut-down device is refused",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", device=SIM_UC,
        env_path=one_path, config=live_cfg, carries=("sim-test", "lease"))
    add("lease: a live lock holder does not lift the lease: an MCP launch by udid is refused",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", udid=SIM_UC,
        env_path=one_path, config=live_cfg, carries=("sim-test", "lease"))
    add("lease: a live lock holder does not refuse an MCP launch of a booted device",
        "allow", tool=SIM_MCP, action="launch", device=SIM_UA, env_path=one_path, config=live_cfg)


def folder_path(name):
    return os.path.join(ROOT, "sim_" + name) + os.pathsep + PY_PATH


def make_fake_ps(folder, rows, rc=0, pid_starts=None, ps_log=None):
    """Replace the quiet `ps` in FOLDER with one that answers the process table ROWS, (pid, ppid,
    uid, command), or fails with RC. A row carries no single quote.

    PID_STARTS, when given, maps a pid to the start text its `-o lstart=` read answers, or to None for a
    dead pid. A pid that is not a key is dead too, so a fixture's shape never decides a liveness case. A
    read that names `pid=` gets "PID START", as the launchd reads do. Without it, the launchd answers stand.
    PS_LOG, when given, is a file that each call appends its argv to, one line per call."""
    if rc:
        body = "exit %d\n" % rc
    else:
        table = "".join("%s %s %s %s\n" % row for row in rows)
        starts = [pid for pid, _, _, cmd in rows if "launchd_sim" in cmd]
        # A call whose argv names `lstart` gets "PID START" lines when its -o list names pid=,
        # else "START" lines, one per launchd_sim row. Any other call gets the process table.
        pid_lines = "".join("%s %s\n" % (pid, LSTART) for pid in starts)
        start_lines = "".join(LSTART + "\n" for _ in starts)
        for text in (table, pid_lines, start_lines):
            assert "'" not in text, "the printf body is single-quoted"
        body = ("case \"$*\" in\n"
                "  *lstart*) case \"$*\" in *pid=*) printf '%s' '" + pid_lines + "' ;;"
                " *) printf '%s' '" + start_lines + "' ;; esac ;;\n"
                "  *) printf '%s' '" + table + "' ;;\n"
                "esac\n")
        if pid_starts is not None:
            # A `-o` word of the read names its pid: that pid answers its own start, and any other pid, or a
            # mapped None, answers nothing and fails, as `ps` does for a dead pid.
            arms = ""
            for pid, text in pid_starts.items():
                if text:
                    assert "'" not in text, "the printf body is single-quoted"
                    arms += ("%d) case \"$*\" in *pid=*) printf '%%s %%s\\n' '%d' '%s' ;;"
                             " *) printf '%%s\\n' '%s' ;; esac; exit 0 ;;\n" % (pid, pid, text, text))
            body = ("case \"$*\" in\n"
                    "  *lstart*) for a in \"$@\"; do case \"$a\" in\n" + arms +
                    "  esac; done; exit 1 ;;\n"
                    "  *) printf '%s' '" + table + "' ;;\n"
                    "esac\n")
    if ps_log:
        assert "'" not in ps_log, "the log path is single-quoted"
        body = "printf '%%s\\n' \"$*\" >> '%s'\n" % ps_log + body
    ps = os.path.join(folder, "ps")
    write(ps, "#!/bin/sh\n" + body)
    os.chmod(ps, 0o755)
    return folder


def sim_boot_record(udid, name, dtype, runtime, seconds_ago):
    """One boot-record line: {udid, name, deviceTypeIdentifier, runtime, at, launchd_pid,
    launchd_start}, `at` ISO-8601 UTC. The launchd fields name the boot's launchd_sim."""
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds_ago))
    return {"udid": udid, "name": name, "deviceTypeIdentifier": dtype, "runtime": runtime,
            "at": at, "launchd_pid": LAUNCHD_PID[udid], "launchd_start": LSTART}


def register_simulator_hold_cases():
    """The reuse rule reads the shutdown tier's own idle test: a twin that a process holds, or that
    Simulator.app or Xcode.app keeps in use, is not idle, so it is not offered. The device's own
    launchd_sim is not a holder of itself. Every `ps` here is a fixture, never the real table."""
    # The table holds the twin's own launchd_sim, which the record names, and nothing else.
    quiet = [("1", "0", "0", "/sbin/launchd"),
             (str(LAUNCHD_PID[SIM_UT0]), "1", "0", LAUNCHD_CMD + " " + SIM_UT0)]
    twin = [(SIM_UT0, "Idle Pro", "Booted", SIM_TYPE_PRO, SIM_RT),
            (SIM_UT1, "Twin Pro", "Shutdown", SIM_TYPE_PRO, SIM_RT)]
    cfg = os.path.join(ROOT, "simcfg_hold")
    os.makedirs(cfg, exist_ok=True)
    write_sim_records(cfg, [sim_boot_record(SIM_UT0, "Idle Pro", SIM_TYPE_PRO, SIM_RT, 2 * 3600)])

    def env_for(name, ps_rows, ps_rc=0):
        path = os.path.join(ROOT, "sim_" + name)
        make_fake_xcrun(path, twin)
        make_fake_ps(path, ps_rows, ps_rc)
        return path + os.pathsep + PY_PATH

    sh("boot a device with an idle twin: the twin's own launchd_sim is not a holder",
       sim_boot_by_destination(SIM_UT1), "deny", rule="simulator-boot-twin",
       env_path=env_for("hold_own", quiet), config=cfg, carries=(SIM_UT0,))
    holds = [
        ("a twin held by a process outside its tree is not idle", quiet + [
            ("500", "400", "0", "xcrun simctl spawn " + SIM_UT0 + " log stream")]),
        ("a twin named by a process is not idle", quiet + [
            ("500", "1", "0", "/usr/local/bin/probe --device Idle Pro")]),
        ("a twin is not idle while Simulator.app runs", quiet + [
            ("600", "1", "0", "/Applications/Simulator.app/Contents/MacOS/Simulator")]),
        ("a twin is not idle while Xcode.app runs", quiet + [
            ("600", "1", "0", "/Applications/Xcode.app/Contents/MacOS/Xcode")]),
    ]
    # Each launch is refused by the lease, so the twin rule did not fire on the held or unreadable twin.
    for index, (label, rows) in enumerate(holds):
        add(label + ": the twin rule does not fire; the lease refuses the launch",
            "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", device=SIM_UT1,
            env_path=env_for("hold_%d" % index, rows), config=cfg, carries=("sim-test", "lease"))
    add("a twin is not idle when the process table cannot be read: the twin rule does not fire; the lease refuses",
        "deny", rule="simulator-boot-lease", tool=SIM_MCP, action="launch", device=SIM_UT1,
        env_path=env_for("hold_ps_rc", [], ps_rc=1), config=cfg, carries=("sim-test", "lease"))


def register_simulator_bypass_cases():
    """Rule simulator-boot-bypass (step sim-machine-lock): a boot that sim-test did not make is refused
    on the command text alone, before any simctl list. So these cases set no fake xcrun, and each deny
    names sim-test. The controls only read, print or quote a boot, and are allowed."""
    raw = "xcrun simctl boot " + SIM_UC
    denied = (
        ("xcrun simctl boot", raw),
        ("bare simctl boot", "simctl boot " + SIM_UC),
        ("open -a Simulator", "open -a Simulator"),
        ("open -a Simulator.app", "open -a Simulator.app"),
        ("open -a quoted Simulator", 'open -a "Simulator"'),
        ("open of the Simulator.app path", "open /Applications/Simulator.app"),
        ("open -b the simulator bundle id", "open -b com.apple.iphonesimulator"),
        ("bash -c wraps the boot", "bash -c '" + raw + "'"),
        ("a cd before the boot", "cd x && " + raw),
        ("a comment opener in a string before the boot", 'echo "# note" && ' + raw),
        ("a lone quote in text before a bare boot", 'echo "it\'s up" && simctl boot ' + SIM_UC),
        ("xargs of a list into a boot", "xcrun simctl list | grep X | xargs xcrun simctl boot"),
        ("xargs of an echo into a boot", "echo " + SIM_UC + " | xargs xcrun simctl boot"),
        ("open -ga Simulator", "open -ga Simulator"),
        ("open -na Simulator", "open -na Simulator"),
        ("open -an Simulator", "open -an Simulator"),
        # A regression guard: a boot in a command substitution, refused now.
        ("a boot in a command substitution", "echo $(xcrun simctl boot " + SIM_UC + ")"),
    )
    for name, command in denied:
        sh("simulator-boot-bypass: " + name, command, "deny", rule="simulator-boot-bypass",
           cwd=NOGIT, carries="sim-test")
    allowed = (
        ("sim-test with a scheme", "sim-test -scheme X"),
        ("simctl shutdown", "xcrun simctl shutdown " + SIM_UC),
        ("simctl list devices", "xcrun simctl list devices"),
        ("grep for the boot text", "grep 'simctl boot' f"),
        ("echo of the boot text", 'echo "simctl boot"'),
        ("open -a Safari", "open -a Safari"),
        ("open a README", "open README.md"),
        ("open -n a README", "open -n README.md"),
        ("open -g a URL", "open -g https://x"),
        ("simctl bootstatus", "xcrun simctl bootstatus " + SIM_UC),
        ("a heredoc body that holds the boot", "cat > notes.md <<'EOF'\n" + raw + "\nEOF"),
        ("a multi-line quoted string whose middle line is the boot",
         'echo "first line\n' + raw + '\nlast line"'),
    )
    for name, command in allowed:
        sh("control: " + name, command, "allow", cwd=NOGIT)


def sim_bypass_override_check(timed):
    """The owner override lifts simulator-boot-bypass. With no override a raw boot is refused. A timed
    override (`override 15m`) lets it through until it ends. A one-act override lets it through once."""
    def check():
        kind = "timed" if timed else "once"
        config, session = ov_config("sim-bypass-" + kind), "ov-sim-bypass-" + kind
        rule = "simulator-boot-bypass"

        def call(seconds):
            return lambda: ov_call("Bash", {"command": "xcrun simctl boot " + SIM_UC}, NOGIT,
                                   config, session, seconds)

        ok, why = ov_story([("with no override", call(0), "deny", rule)])
        if not ok:
            return False, why
        note = ov_type(config, session, "override 15m" if timed else "override")
        if timed:
            steps = [("first call", call(60), "allow", rule),
                     ("call just before the end", call(OV_TIMED_SECONDS - 1), "allow", rule),
                     ("call at the end instant", call(OV_TIMED_SECONDS), "deny", rule)]
        else:
            steps = [("first call", call(60), "allow", rule),
                     ("second call, override spent", call(120), "deny", rule)]
        ok, why = ov_story(steps, note)
        if not ok:
            return False, why
        return True, "denied with no override, then allowed %s" % (
            "until the end" if timed else "once")
    return check


def sim_override_check(name, rule, tool, tool_input, path):
    """The owner override lifts RULE. With no override the call is refused. After `override` the same call
    is allowed once, and the second call is refused again. The call runs on PATH, so RULE is what refuses it."""
    def check():
        config, session = ov_config(name), "ov-" + name

        def call(seconds):
            return lambda: ov_call(tool, tool_input, NOGIT, config, session, seconds, env_path=path)

        ok, why = ov_story([("with no override", call(0), "deny", rule)])
        if not ok:
            return False, why
        note = ov_type(config, session, "override")
        ok, why = ov_story([("first call", call(60), "allow", rule),
                            ("second call, override spent", call(120), "deny", rule)], note)
        if not ok:
            return False, why
        return True, "denied with no override, then allowed once"
    return check


def sim_route_override_check():
    """The owner override lifts simulator-boot-route. A test of a shut-down device is refused with no override.
    The call runs on the "one" fixture (one booted, one shut down), so the route rule is what refuses it."""
    command = "xcodebuild test -scheme App -destination 'platform=iOS Simulator,id=" + SIM_UC + "'"
    return sim_override_check("sim-route-override", "simulator-boot-route", "Bash",
                              {"command": command}, folder_path("one"))


def sim_lease_override_check():
    """The owner override lifts simulator-boot-lease. An MCP launch of a shut-down device, with no lock held, is
    refused with no override. The "one" fixture has one booted device, so the cap does not fire."""
    return sim_override_check("sim-lease-override", "simulator-boot-lease", SIM_MCP,
                              {"action": "launch", "device": SIM_UC}, folder_path("one"))


# --------------------------------------------------------------------------- the lease allow
# Decision sim-test-is-the-one-boot-path, ruling 5, and decision sim-lease-tool. An MCP launch of a shut-down
# phone simulator is allowed when THIS session holds a LIVE lease whose slot maps to the launched device's UDID.
# The cap and twin rules still refuse first, and a lease that cannot be read keeps the refusal. Liveness is
# sim-lease's reap: the pid is alive and `ps -o lstart=` gives the recorded start. The slot map is the one in
# skills/ios-apps/SKILL.md, Phone simulators (lines 67-69), typed here as data. The test does not import it from
# bin/sim-lease, so a missing constant there fails an assert and not an import. Each case differs from the allow
# case in one input.
LEASE_RULE = "simulator-boot-lease"
LEASE_CARRIES = ("sim-test", "lease")
LEASE_SLOT_UDID = {"1": "3553660D-315C-4B9C-8614-039D7A5B637E",     # Duo 1
                   "2": "801F55F4-F666-4C6D-AB04-7DF77C953974",     # Duo 2
                   "pro": "86F9268A-A905-4B82-9BC0-D7EBB682D341"}   # iPhone 18 Pro
LEASE_DUO1, LEASE_DUO2, LEASE_PRO = LEASE_SLOT_UDID["1"], LEASE_SLOT_UDID["2"], LEASE_SLOT_UDID["pro"]
LEASE_DECOY = "1A2B3C4D-0000-4000-8000-0000000000D6"  # named "Duo 1", but not Duo 1's UDID: a name match would allow it
LEASE_PID = os.getpid()    # a live holder for the whole run
LEASE_OTHER_PID = 4243     # another session's holder, live in the fake ps
LEASE_WAIT_PID = 4244      # a waiter, live in the fake ps
LEASE_DEAD_PID = 4194311   # above any pid_max, so no process holds it
LEASE_START = "Wed Nov  4 03:00:00 2026"
LEASE_REUSED_START = "Mon Nov  2 09:00:00 2026"   # the start of another process that reuses LEASE_PID
LEASE_OWN, LEASE_OTHER = "sess-own-0001", "sess-other-0002"
LEASE_ENV = {"CI": None, "GITHUB_ACTIONS": None}  # sim-lease's no-op reads CI; the guard's lease read must not


def lease_entry(slot, pid=LEASE_PID, start=LEASE_START, session=LEASE_OWN):
    """One lease record as sim-lease's take writes it: the slot is a string, the device is `pro` or `duo`."""
    return {"pid": pid, "start": start, "device": "pro" if slot == "pro" else "duo",
            "session": session, "slot": slot}


def lease_fixture(name, rows, pid_starts, leases=None, queue=(), raw=None, as_dir=False, records=None, ps_log=False):
    """A case folder of its own: a fake xcrun that lists ROWS and a fake ps that answers PID_STARTS (a booted
    device's launchd_sim is always alive, as on the Mac). The config dir holds leases.json as LEASES with QUEUE,
    as RAW text, as a directory (AS_DIR), or as no file at all. PS_LOG logs each fake ps call to ps.log in the
    config dir. Returns (PATH, config dir)."""
    folder = os.path.join(ROOT, "simlease_" + name)
    starts = {LAUNCHD_PID[udid]: LSTART for udid, _, state, _, _ in rows if state == "Booted" and udid in LAUNCHD_PID}
    starts.update(pid_starts)
    cfg = os.path.join(ROOT, "simlease_cfg_" + name)
    make_fake_xcrun(folder, rows, pid_starts=starts, ps_log=os.path.join(cfg, "ps.log") if ps_log else None)
    lease_file = os.path.join(cfg, "state", "sim-lease", "leases.json")
    os.makedirs(cfg, exist_ok=True)
    if as_dir:
        os.makedirs(lease_file, exist_ok=True)
    elif raw is not None:
        write(lease_file, raw)
    elif leases is not None:
        write(lease_file, json.dumps({"leases": leases, "queue": list(queue)}))
    if records is not None:
        write_sim_records(cfg, records)
    return folder + os.pathsep + PY_PATH, cfg


def lease_launch(name, expected, fixture, device=None, udid=None, session=LEASE_OWN, rule=None, carries=None, raw=None,
                 load=None):
    """One MCP launch case against FIXTURE, naming the device by DEVICE or by UDID. SESSION rides on the payload,
    and None sends no session key. A deny carries LEASE_CARRIES unless CARRIES says otherwise. LOAD is the reading
    the run sees (add's `load`); None is the neutral one. Returns the case."""
    env_path, config = fixture
    tool_input = {"action": "launch"}
    if device is not None:
        tool_input["device"] = device
    if udid is not None:
        tool_input["udid"] = udid
    if carries is None:
        carries = LEASE_CARRIES if expected == "deny" else ()
    add(name, expected, rule=rule, tool=SIM_MCP, env_path=env_path, config=config, session=session,
        carries=carries, env=LEASE_ENV, raw=raw, load=load, **tool_input)
    return CASES[-1]


# The one liveness read of a lease: bin/sim-lease's start_time runs `ps -o lstart= -p PID`. The table read and
# the launchd read carry other argv, so this form counts only the lease reads.
LEASE_PS_READ = re.compile(r"-o lstart= -p \d+")


def lease_ps_count_check(case, want):
    """The held-lease read costs one `ps` per lease (decision sim-test-is-the-one-boot-path, ruling 7). CASE runs
    under a fake ps that logs each call, and the check counts the lease reads among them. It does not judge the
    decision, which the case asserts itself. Returns the check."""
    log = os.path.join(case["config"], "ps.log")

    def check():
        if os.path.exists(log):
            os.remove(log)
        decide(case)
        calls = []
        if os.path.exists(log):
            with open(log) as handle:
                calls = handle.read().splitlines()
        reads = [c for c in calls if LEASE_PS_READ.fullmatch(c)]
        if len(reads) != want:
            return False, "the launch made %d lease reads (ps -o lstart= -p PID), want %d" % (len(reads), want)
        return True, "the launch made %d lease reads, one per lease" % len(reads)
    return check


def lease_no_write_check(case):
    """The lease read writes nothing (decision sim-lease-tool: the guard reads leases.json and never takes its
    lock). CASE is a refusal over a dead lease, the one read that a reaping reader would rewrite: it is refused,
    and leases.json and the lock keep the same bytes. A reader that reaps through sim-lease's State rewrites the
    file and creates the lock."""
    state = os.path.join(case["config"], "state", "sim-lease")

    def snapshot():
        return {n: (open(os.path.join(state, n), "rb").read() if os.path.exists(os.path.join(state, n)) else None)
                for n in ("leases.json", "lock")}

    def check():
        before = snapshot()
        decision, _ = decide(case)
        after = snapshot()
        if decision != "deny":
            return False, "the dead lease was %s, not refused" % decision
        changed = [n for n in before if before[n] != after[n]]
        if changed:
            return False, "the lease read changed sim-lease's %s" % " and ".join(changed)
        return True, "the dead lease is refused and sim-lease's files keep their bytes"
    return check


def lease_fake_ps_check():
    """The lease fixtures' fake ps answers each pid it names with that pid's start, and no other pid. The liveness
    cases decide on that answer, so a fixture that answered the wrong pid would decide them (scope before subject)."""
    own_ps = os.path.join(ROOT, "simlease_own_slot1", "ps")
    reused_ps = os.path.join(ROOT, "simlease_reused", "ps")

    def read(ps, *args):
        r = subprocess.run([ps, "-o", *args], capture_output=True, text=True)
        return r.returncode, r.stdout.strip()

    def check():
        got = read(own_ps, "lstart=", "-p", str(LEASE_PID))
        if got != (0, LEASE_START):
            return False, "the live pid's start read %r, not the recorded start" % (got,)
        rc, text = read(own_ps, "lstart=", "-p", str(LEASE_DEAD_PID))
        if rc == 0 and text:
            return False, "the dead pid answered a start"
        got = read(reused_ps, "lstart=", "-p", str(LEASE_PID))
        if got != (0, LEASE_REUSED_START):
            return False, "the reused pid's start read %r, not its own start" % (got,)
        launchd = LAUNCHD_PID[SIM_UB]
        got = read(own_ps, "pid=,lstart=", "-p", str(launchd))
        if got != (0, "%d %s" % (launchd, LSTART)):
            return False, "a booted device's launchd_sim read %r" % (got,)
        return True, "the fake ps answers each named pid and no other"
    return check


def register_simulator_lease_cases():
    """The lease allow and its controls. Returns the dead-lease case, which lease_no_write_check runs, and the
    lease read counts as (label, check) pairs for LOG_CHECKS."""
    rows = [(LEASE_DUO1, "iPhone Duo A", "Shutdown", SIM_TYPE_MINI, SIM_RT),
            (LEASE_DUO2, "iPhone Duo B", "Shutdown", SIM_TYPE_MINI, SIM_RT),
            (LEASE_PRO, "iPhone 18 Pro", "Shutdown", SIM_TYPE_PRO, SIM_RT),
            (LEASE_DECOY, "Duo 1", "Shutdown", SIM_TYPE_MINI, SIM_RT),
            (SIM_UB, "Beta Air", "Booted", SIM_TYPE_AIR, SIM_RT)]
    cap_rows = rows + [(SIM_UA, "Alpha Pro", "Booted", SIM_TYPE_PRO, SIM_RT)]
    twin_rows = [(LEASE_DUO1, "iPhone Duo A", "Shutdown", SIM_TYPE_PRO, SIM_RT),
                 (SIM_UT0, "Idle Pro", "Booted", SIM_TYPE_PRO, SIM_RT)]
    live = {LEASE_PID: LEASE_START}
    slot1 = [lease_entry("1")]
    duo1, duo2 = "iPhone Duo A", "iPhone Duo B"

    # The allow: this session's live lease, and its slot maps to the launched device.
    own1 = lease_fixture("own_slot1", rows, live, slot1)
    lease_launch("lease allow: this session's live slot 1 lease, a launch of Duo 1 by name is allowed",
                 "allow", own1, device=duo1)
    lease_launch("lease allow: this session's live slot 1 lease, a launch of Duo 1 by udid is allowed",
                 "allow", own1, udid=LEASE_DUO1)
    lease_launch("lease allow: this session's live slot 1 lease, a launch of Duo 1 by lowercase udid is allowed",
                 "allow", own1, udid=LEASE_DUO1.lower())
    lease_launch("control: this session's live slot 1 lease, a launch of a booted device is allowed (no boot)",
                 "allow", own1, device="Beta Air")
    own2 = lease_fixture("own_slot2", rows, live, [lease_entry("2")])
    lease_launch("lease allow: this session's live slot 2 lease, a launch of Duo 2 by name is allowed",
                 "allow", own2, device=duo2)
    own_pro = lease_fixture("own_pro", rows, live, [lease_entry("pro")])
    lease_launch("lease allow: this session's live pro lease, a launch of the 18 Pro by name is allowed",
                 "allow", own_pro, device="iPhone 18 Pro")
    # Full: another session holds slot 2 and a third waits. This session's slot 1 allows Duo 1 and no other.
    full = lease_fixture("full", rows, {LEASE_PID: LEASE_START, LEASE_OTHER_PID: LEASE_START,
                                        LEASE_WAIT_PID: LEASE_START},
                         [lease_entry("1"), lease_entry("2", pid=LEASE_OTHER_PID, session=LEASE_OTHER)],
                         queue=[{"pid": LEASE_WAIT_PID, "start": LEASE_START, "device": "duo",
                                 "session": LEASE_OTHER}])
    lease_launch("lease allow: a full state, this session's slot 1 lease allows a launch of Duo 1",
                 "allow", full, device=duo1)
    lease_launch("lease: a full state, this session's slot 1 lease does not allow a launch of Duo 2",
                 "deny", full, device=duo2, rule=LEASE_RULE)

    # Refused: no lease, a dead or reused holder, a queue place, another session, a lease for another device.
    lease_launch("lease: no lease file, a launch of Duo 1 is refused", "deny",
                 lease_fixture("no_file", rows, live), device=duo1, rule=LEASE_RULE)
    lease_launch("lease: an empty lease list, a launch of Duo 1 is refused", "deny",
                 lease_fixture("empty_list", rows, live, []), device=duo1, rule=LEASE_RULE)
    lease_launch("lease: an empty object, a launch of Duo 1 is refused", "deny",
                 lease_fixture("empty_object", rows, live, raw="{}"), device=duo1, rule=LEASE_RULE)
    dead_case = lease_launch("lease: a dead lease (its pid is not alive) is refused", "deny",
                             lease_fixture("dead", rows, live, [lease_entry("1", pid=LEASE_DEAD_PID)]),
                             device=duo1, rule=LEASE_RULE)
    lease_launch("lease: a reused pid (its start differs from the lease's) is refused", "deny",
                 lease_fixture("reused", rows, {LEASE_PID: LEASE_REUSED_START}, slot1),
                 device=duo1, rule=LEASE_RULE)
    lease_launch("lease: this session only queued, not granted, is refused", "deny",
                 lease_fixture("queued", rows, live, [], queue=slot1), device=duo1, rule=LEASE_RULE)
    lease_launch("lease: another session's live slot 1 lease on Duo 1 does not allow this session", "deny",
                 lease_fixture("other_session", rows, live, [lease_entry("1", session=LEASE_OTHER)]),
                 device=duo1, rule=LEASE_RULE)
    lease_launch("lease: this session's slot 1 lease does not allow a launch of Duo 2", "deny",
                 own1, device=duo2, rule=LEASE_RULE)
    lease_launch("lease: this session's pro lease does not allow a launch of Duo 1", "deny",
                 own_pro, device=duo1, rule=LEASE_RULE)
    lease_launch("lease: a name no lease maps is refused: the decoy named Duo 1 is not Duo 1's udid", "deny",
                 own1, device="Duo 1", rule=LEASE_RULE)
    lease_launch("lease: the decoy's udid is refused by this session's slot 1 lease", "deny",
                 own1, udid=LEASE_DECOY, rule=LEASE_RULE)

    # A name that two shut-down devices share resolves to both UDIDs. The launch is allowed only when this
    # session's live leases hold every one of them (sim_lease_holds is all, not any). Duo 2 is on the older runtime.
    shared = [(LEASE_DUO1, "iPhone Duo", "Shutdown", SIM_TYPE_MINI, SIM_RT),
              (LEASE_DUO2, "iPhone Duo", "Shutdown", SIM_TYPE_MINI, SIM_RT_OLD)] + rows[2:]
    lease_launch("lease: a shared name, this session's slot 1 lease alone is refused: Duo 2 is not held",
                 "deny", lease_fixture("shared_slot1", shared, live, slot1), device="iPhone Duo", rule=LEASE_RULE)
    lease_launch("lease: a shared name, this session's slot 2 lease alone is refused: Duo 1 is not held",
                 "deny", lease_fixture("shared_slot2", shared, live, [lease_entry("2")]),
                 device="iPhone Duo", rule=LEASE_RULE)
    both = lease_fixture("shared_slot12", shared, live, [lease_entry("1"), lease_entry("2")], ps_log=True)
    shared_case = lease_launch("control: a shared name, this session's slot 1 and slot 2 leases together are allowed",
                               "allow", both, device="iPhone Duo")
    booted_case = lease_launch("control: a booted device under this session's slot 1 and slot 2 leases is allowed",
                               "allow", both, device="Beta Air")

    # An empty session never matches: on the lease side, on the payload side, or on both.
    blank = lease_fixture("blank_session", rows, live, [lease_entry("1", session="")])
    lease_launch("lease: a lease with an empty session does not match a payload that names a session", "deny",
                 blank, device=duo1, rule=LEASE_RULE)
    lease_launch("lease: a lease with an empty session does not match a payload with no session", "deny",
                 blank, device=duo1, session=None, rule=LEASE_RULE)
    lease_launch("lease: this session's lease does not match a payload whose session is empty", "deny",
                 own1, device=duo1, session=None, rule=LEASE_RULE,
                 raw=json.dumps({"tool_name": SIM_MCP, "tool_input": {"action": "launch", "device": duo1},
                                 "session_id": ""}))

    # A lease file that cannot be read keeps the refusal.
    lease_launch("lease: a lease file that is not JSON keeps the refusal", "deny",
                 lease_fixture("garbage", rows, live, raw="not json {"), device=duo1, rule=LEASE_RULE)
    lease_launch("lease: a lease file that is a directory keeps the refusal", "deny",
                 lease_fixture("as_dir", rows, live, as_dir=True), device=duo1, rule=LEASE_RULE)
    lease_launch("lease: a lease file of the wrong shape keeps the refusal", "deny",
                 lease_fixture("wrong_shape", rows, live, raw='{"leases": "x", "queue": []}'),
                 device=duo1, rule=LEASE_RULE)
    lease_launch("lease: a lease record with no pid keeps the refusal", "deny",
                 lease_fixture("no_pid", rows, live,
                               [{"start": LEASE_START, "device": "duo", "session": LEASE_OWN, "slot": "1"}]),
                 device=duo1, rule=LEASE_RULE)

    # The cap and the twin still refuse first, with this session's live lease in place.
    lease_launch("lease: this session's live slot 1 lease, cap full and busy: simulator-boot-cap still refuses first",
                 "deny", lease_fixture("cap_full", cap_rows, live, slot1), device=duo1,
                 rule="simulator-boot-cap", load=SIM_BUSY, carries=(SIM_UA, SIM_UB))
    # The boot cap follows the machine, not the count (decision sims-load-brake-only). This session's live slot 1 lease
    # for the Duo launch: a quiet, unread or cloud machine lets the boot through whatever the count, and a busy one refuses it.
    sim_type_pad = "com.apple.CoreSimulator.SimDeviceType.iPad-Pro-13-inch"  # no other row has this type
    cap3_rows = cap_rows + [(SIM_UG, "Gamma Pad", "Booted", sim_type_pad, SIM_RT)]
    shut_rows = [row for row in cap_rows if row[2] != "Booted"]
    lease_launch("lease: this session's live slot 1 lease, three booted, a quiet machine: allowed, no count cap",
                 "allow", lease_fixture("three_quiet", cap3_rows, live, slot1), device=duo1)
    lease_launch("lease: this session's live slot 1 lease, two booted, a quiet machine: allowed, no count cap",
                 "allow", lease_fixture("two_quiet", cap_rows, live, slot1), device=duo1)
    lease_launch("lease: this session's live slot 1 lease, two booted, an unread machine: allowed",
                 "allow", lease_fixture("two_unread", cap_rows, live, slot1), device=duo1, load=SIM_UNREAD)
    cloud_path, cloud_cfg = lease_fixture("two_cloud", cap_rows, live, slot1)
    add("lease: this session's live slot 1 lease, two booted, a cloud session on a busy machine: allowed, not braked",
        "allow", tool=SIM_MCP, action="launch", device=duo1, env_path=cloud_path, config=cloud_cfg,
        session=LEASE_OWN, env=dict(LEASE_ENV, CLAUDE_CODE_REMOTE="true"), load=SIM_BUSY)
    lease_launch("lease: this session's live slot 1 lease, none booted, a busy machine: the busy bar refuses it",
                 "deny", lease_fixture("none_busy", shut_rows, live, slot1), device=duo1,
                 rule="simulator-boot-cap", carries=("memory",), load=SIM_BUSY)
    lease_launch("lease: this session's live slot 1 lease, an idle twin: simulator-boot-twin still refuses first",
                 "deny", lease_fixture("twin", twin_rows, live, slot1,
                                       records=[sim_boot_record(SIM_UT0, "Idle Pro", SIM_TYPE_PRO, SIM_RT,
                                                                2 * 3600)]),
                 device=duo1, rule="simulator-boot-twin", carries=(SIM_UT0,))
    ps_counts = [("simulator: a held-lease allow of two leases makes two lease reads, one ps per lease (ruling 7)",
                  lease_ps_count_check(shared_case, 2)),
                 ("simulator: a launch of a booted device makes no lease read (ruling 7)",
                  lease_ps_count_check(booted_case, 0))]
    return dead_case, ps_counts


# The simulator cases need a POSIX shell for the fake xcrun and ps. Windows has neither to fake, so
# on Windows the simulator family holds no case, and GUARD_FAMILY=simulator runs none and fails.
