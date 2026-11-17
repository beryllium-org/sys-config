#!/usr/bin/env python

import json
import re, os, sys, time, shlex, curses, shutil
import argparse, subprocess, signal
from pathlib import Path
from datetime import datetime

# If running on the dumbest terminal on earth, fix env and reexec.
if "TERM" in os.environ and os.environ["TERM"] == "xterm-kitty":
    os.environ["TERM"] = "xterm-256color"
    os.execv(sys.executable, [sys.executable] + sys.argv)

from beryllium import dt
from beryllium import utilities
from beryllium import curseapp as c

c.APP_NAME = "Beryllium OS System Configurator"
LOG_FILE = None
DRYRUN = False
ROOT_MODE = False


# ---------- CACHE FUNCTIONS ------------

CACHE_FILE = f"/tmp/config_cache.{os.geteuid()}.json"


def load_cache() -> dict:
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def write_cache(payload: dict) -> None:
    tmp = f"{CACHE_FILE}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f)
        os.rename(tmp, CACHE_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# --------------- RUNNER ----------------

elevator = utilities.Elevator()


def handle_stupid(signum=None, frame=None) -> None:
    pass


signal.signal(signal.SIGQUIT, handle_stupid)
signal.signal(signal.SIGTSTP, handle_stupid)


def cmdr(cmd: list, elevate: bool = False, label: "str | None" = None) -> "str | int":
    output = []
    if DRYRUN:
        if c.stdscr is not None:
            c.stdscr.clear()
            c.stdscr.addstr(1, 2, label, curses.A_BOLD | curses.A_UNDERLINE)
            c.draw_border()
        output = "DRYRUN: " + " ".join(cmd)
        if c.stdscr is not None:
            c.stdscr.addstr(3, 2, output)
            c.stdscr.refresh()
        else:
            print(output)
        return output

    proc_cm = None
    if elevate and not ROOT_MODE:
        auth = False
        if not elevator.spawned:
            auth = True
            if c.stdscr is not None:
                c.suspend()
            print("Authenticating..")
        try:
            proc_cm = elevator.run(" ".join(shlex.quote(part) for part in cmd))
        except RuntimeError:
            if auth:
                if c.stdscr is not None:
                    c.stdscr.addstr(
                        1,
                        2,
                        "Authentication Failed!",
                        curses.A_BOLD | curses.A_UNDERLINE,
                    )
                    c.resume()
                    c.draw_border()
                else:
                    print("Authentication Failed!")
                return -1
            raise
        if auth and c.stdscr is not None:
            c.resume()
    else:
        proc_cm = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )

    with proc_cm as proc:
        try:
            y = 3
            ym = 0
            xm = None
            limit = 0
            if c.stdscr is not None:
                c.stdscr.clear()
                c.stdscr.addstr(1, 2, label, curses.A_BOLD | curses.A_UNDERLINE)
                c.draw_border()
                ym, xm = c.stdscr.getmaxyx()
                limit = int(ym) - 2
                c.stdscr.refresh()
            clines = []
            eoc = False
            for uline in proc.stdout:
                clines = [uline] if c.stdscr is None else c.lw([uline], xm)
                for line in clines:
                    if "[[EOC]]" in line:
                        eoc = True
                        break
                    if c.stdscr is not None:
                        if y < limit:
                            c.stdscr.addstr(y if y <= limit else limit, 2, line)
                        else:
                            for i in range(3, limit):
                                c.clear_line(i)
                                c.stdscr.addstr(i, 2, output[y - limit - 3 + i][:-1])
                        y += 1
                        c.draw_border()
                        c.stdscr.refresh()
                    else:
                        print(line, end="")
                    output.append(line)
                if eoc:
                    break
            proc.wait()
        except KeyboardInterrupt:
            try:
                proc.kill()
            except:
                pass
            return -1
    returncode = proc.returncode
    return "".join(output)


def cli_runner(cmd: str, elevate: bool = False) -> None:
    global LOG_FILE, ROOT_MODE

    result = cmdr(cmd, elevate)

    if LOG_FILE is not None and isinstance(result, str):
        with open(LOG_FILE, "a") as f:
            f.write(f"$ {' '.join(cmd)}\n")
            f.write(result + "\n")

    if result == -1:
        print("\nABORTED")


def tui_runner(
    label: str, cmd: list, elevate: bool = False, prompt: bool = True
) -> None:
    global LOG_FILE, ROOT_MODE

    c.stdscr.clear()
    c.draw_border()
    c.stdscr.addstr(1, 2, label, curses.A_BOLD | curses.A_UNDERLINE)
    # c.stdscr.addstr(
    #     4,
    #     2,
    #     ("#" if elevate else "$") + " " + " ".join(cmd if not elevate else cmd[1:]),
    # )
    c.stdscr.refresh()

    output = cmdr(cmd, elevate, label)

    if LOG_FILE is not None and isinstance(output, str):
        with open(LOG_FILE, "a") as f:
            f.write(f"$ {' '.join(cmd)}\n{output}\n")

    maxy, _ = c.stdscr.getmaxyx()

    if not prompt:
        if DRYRUN:
            time.sleep(3)
        return

    c.stdscr.attron(curses.A_REVERSE)
    c.stdscr.addstr(
        maxy - 2,
        2,
        " " + ("ABORTED" if output == -1 else "OK") + " - Press Enter to return ",
    )
    c.stdscr.attroff(curses.A_REVERSE)
    c.stdscr.refresh()
    while c.stdscr.getch() != ord("\n"):
        pass
    c.wait_clear()


def runner(
    cmd: list, elevate=True, label: str = c.APP_NAME, prompt: bool = True
) -> None:
    if c.stdscr is None:
        cli_runner(cmd, elevate=elevate)
    else:
        tui_runner(label, cmd, elevate=elevate, prompt=prompt)


def mrunner(
    cmds: list, elevate=True, label: str = c.APP_NAME, prompt: bool = True
) -> None:
    cmd = " && ".join(" ".join(shlex.quote(b) for b in a) for a in cmds)
    runner(["sh", "-c", cmd], elevate, label, prompt)


def elevated_file_write(filepath: str, content: str) -> None:
    escaped_lines = [
        '"'
        + line.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
        + '"'
        for line in content.splitlines()
    ]

    printf_part = 'printf "%s\\n" ' + " ".join(escaped_lines)
    full_cmd = f'{printf_part} | tee "{filepath}" > /dev/null'

    runner(["sh", "-c", full_cmd], True, f"Writing {filepath}", False)


def debug_info() -> None:
    grub = dt.grub_exists()
    ext = dt.extlinux_exists()
    efi = dt.booted_with_edk()
    c.message(
        [
            f"GRUB: {grub}",
            f"EXTLINUX: {ext}",
            f"EFI: {efi}",
            f"Elevated: {elevator.spawned}",
            f"DryRun: {DRYRUN}",
        ],
        "Debug Information",
    )
    runner(
        ["ping", "-c", "4", "feline.gr"],
        True,
        "test wrapping",
    )


def normalize_filename(filename: str, extension: str) -> str:
    base = os.path.basename(filename)
    name, ext = os.path.splitext(base)
    return f"{name}.{extension}"


def set_base_dtb(dtb: str = None) -> None:
    grub = dt.grub_exists()
    ext = dt.extlinux_exists()
    normalized_dtb = None
    matched_dtb = None
    dtb_cache = dt.gencache()

    if dtb is not None:
        bases = []
        for i in list(dtb_cache["base"].keys()):
            bases.append(normalize_filename(i, "dtb"))

        normalized_dtb = normalize_filename(dtb, "dtb")

        if (normalized_dtb is None) or (normalized_dtb not in bases):
            c.message(
                [f'DTB "{dtb}" not found on system, refusing to continue.'], "ERROR"
            )
            return

        matched_dtb = utilities.match_filename(
            normalized_dtb, list(dtb_cache["base"].keys())
        )
        if matched_dtb is None:
            c.message(["Failed to match DTB!"], "ERROR")
            return
    else:
        c.message("Refusing to unset Base DTB!", "ERROR")
        return

    if grub:
        grubcfg = dt.parse_grub()

        if not dt.uefi_overriden():
            grubdtbn = matched_dtb
            if grubdtbn.startswith("/boot/"):
                grubdtbn = grubdtbn[6:]
            grubcfg["GRUB_DTB"] = grubdtbn

            grubcfg = dt.encode_grub(grubcfg)

            if not DRYRUN:
                elevated_file_write("/etc/default/grub", grubcfg)
            else:
                c.message(
                    [
                        "The GRUB config would have been updated with the following:",
                        "",
                        grubcfg,
                    ],
                    "DRYRUN Simulated Output",
                )

            runner(
                ["grub-mkconfig", "-o", "/boot/grub/grub.cfg"],
                True,
                "Update GRUB Configuration",
            )
        else:
            # Remove all old Base DTBs
            efidir = dt.detect_efidir()
            listing = utilities.ls(efidir + "/dtb/base/")

            cmds = []
            if listing:
                cmds.append(["rm", "-v"] + [str(p) for p in listing])
            cmds.append(["cp", "-v", matched_dtb, efidir + "/dtb/base/"])

            # Changes here must also be performed down in set_overlays
            if normalized_dtb == "rk3588s-fydetab-duo.dtb":
                cmds.append(
                    [
                        "cp",
                        "-v",
                        matched_dtb,
                        efidir + "/dtb/base/rk3588s-tablet-12c-linux.dtb",
                    ]
                )
            elif normalized_dtb == "rk3588-firefly-itx-3588j.dtb":
                cmds.append(
                    [
                        "cp",
                        "-v",
                        matched_dtb,
                        efidir + "/dtb/base/itx-3588j.dtb",
                    ]
                )
            elif normalized_dtb == "rk3588-rock-5b-plus.dtb":
                cmds.append(
                    ["cp", "-v", matched_dtb, efidir + "/dtb/base/rk3588-rock-5bp.dtb"]
                )
            cmds.append(["sync", efidir])
            mrunner(cmds, True, "Performing Changes")

    if ext:
        extcfg = dt.parse_uboot()

        extcfg["U_BOOT_FDT"] = normalized_dtb

        extcfg = dt.encode_uboot(extcfg)

        if not DRYRUN:
            elevated_file_write("/etc/default/u-boot", extcfg)
        else:
            c.message(
                [
                    "The u-boot config would have been updated with the following:",
                    "",
                    extcfg,
                ],
                "DRYRUN Simulated Output",
            )

        runner(
            ["u-boot-update"],
            True,
            "Trigger U-Boot Update",
        )


def set_overlays(dtbos: list = []) -> None:
    grub = dt.grub_exists()
    ext = dt.extlinux_exists()

    normalized_dtbos = set()
    matched_dtbos = set()
    dtb_cache = dt.gencache()

    if dtbos:
        overlays = []

        # Populate overlays cache with trimmed names
        for i in list(dtb_cache["overlays"].keys()):
            overlays.append(normalize_filename(i, "dtbo"))

        # Format inputted dtbos
        for i in dtbos:
            normalized_dtbos.add(normalize_filename(i, "dtbo"))

        # Ensure they all exist
        for i in normalized_dtbos:
            if (i is None) or i not in overlays:
                c.message(
                    [f'Overlay "{i}" not found on system, refusing to continue.'],
                    "ERROR",
                )
                return

        # Match inputted dtbos
        for i in normalized_dtbos:
            matched_dtbos.add(
                utilities.match_filename(i, list(dtb_cache["overlays"].keys()))
            )

        # Ensure they all exist
        for i in matched_dtbos:
            if i is None:
                c.message(
                    [f'Overlay "{i}" failed to match, refusing to continue.'], "ERROR"
                )
                return

    if grub:
        efidir = dt.detect_efidir()

        if not dt.uefi_overriden():
            if c.confirm(
                [
                    "IMPORTANT NOTICE --!!-- IMPORTART NOTICE",
                    "",
                    "Upon the next reboot UEFI setup may be required!",
                    "",
                    "To enter into UEFI setup you can either:",
                    " - Hold down ESC",
                    "  or",
                    ' - Select "Enter UEFI Setup" from within the GRUB Bootloader',
                    "",
                    "In the UEFI setup menu you need to select:",
                    "",
                    "Device Manager > Rockchip Platform Configuration > ACPI / Device Tree",
                    "",
                    "And do the following:",
                    "",
                    ' - Set "Config Table Mode" to "Device Tree" or "Both"',
                    ' - Change "Support DTB override & overlays" to "Enabled"',
                    "",
                    "IMPORTANT NOTICE --!!-- IMPORTART NOTICE",
                    "",
                    "",
                    "Press Y to continue, or N to abort this operation.",
                ],
                "UEFI Setup required!",
            ):
                grubcfg = dt.parse_grub()

                # Fetch original base DTB
                base_dtb_normalized = normalize_filename(grubcfg["GRUB_DTB"], "dtb")
                base_dtb_path = utilities.match_filename(
                    base_dtb_normalized, list(dtb_cache["base"].keys())
                )
                if base_dtb_path is None:
                    c.message(["Failed to match DTB!"], "ERROR")
                    return

                cmds = [
                    ["mkdir", "-vp", efidir + "/dtb/base/", efidir + "/dtb/overlays/"],
                    ["cp", "-v", base_dtb_path, efidir + "/dtb/base/"],
                ]

                # Copy base DTB, changes here must be also be performed to set_base_dtb
                if base_dtb_normalized == "rk3588s-fydetab-duo.dtb":
                    cmds.append(
                        [
                            "cp",
                            "-v",
                            base_dtb_path,
                            efidir + "/dtb/base/rk3588s-tablet-12c-linux.dtb",
                        ]
                    )
                elif base_dtb_normalized == "rk3588-rock-5b-plus.dtb":
                    cmds.append(
                        [
                            "cp",
                            "-v",
                            base_dtb_path,
                            efidir + "/dtb/base/rk3588-rock-5bp.dtb",
                        ]
                    )
                elif base_dtb_normalized == "rk3588-firefly-itx-3588j.dtb":
                    cmds.append(
                        [
                            "cp",
                            "-v",
                            base_dtb_path,
                            efidir + "/dtb/base/itx-3588j.dtb",
                        ]
                    )
                cmds.append(["sync", efidir])

                mrunner(cmds, True, "Performing Changes", False)

                # Disable dtb in grub
                del grubcfg["GRUB_DTB"]
                grubcfg = dt.encode_grub(grubcfg)

                if not DRYRUN:
                    elevated_file_write("/etc/default/grub", grubcfg)
                else:
                    c.message(
                        [
                            "The GRUB config would have been updated with the following:",
                            "",
                            grubcfg,
                        ],
                        "DRYRUN Simulated Output",
                    )

                runner(
                    ["grub-mkconfig", "-o", "/boot/grub/grub.cfg"],
                    True,
                    "Update GRUB Configuration",
                )
            else:
                c.message(["Cannot continue, returning."], "ABORTED")
                return

        # Remove all current DTBOs
        listing = []
        listing_str = ""
        try:
            listing = utilities.ls(efidir + "/dtb/overlays/")
            listing_str = " ".join(str(p) for p in listing)
        except Exception as err:
            if not DRYRUN:
                raise err

        if listing_str:
            cmds = [["rm", "-v", listing_str]]

        for dtbo in matched_dtbos:
            cmds.append(["cp", "-v", dtbo, efidir + "/dtb/overlays/"])

        mrunner(cmds, True, "Updating Overlays")

    if ext:
        extcfg = dt.parse_uboot()

        if dtbos:
            for i in range(len(dtbos)):
                dtbos[i] = normalize_filename(dtbos[i], "dtbo")
                dtbo_path = utilities.match_filename(
                    dtbos[i], list(dtb_cache["overlays"].keys())
                )
                if dtbo_path is None:
                    c.message(
                        [
                            f'Overlay "{dtbos[i]}" not found on system, refusing to continue.'
                        ],
                        "ERROR",
                    )
                    return

            extcfg["U_BOOT_FDT_OVERLAYS"] = " ".join(dtbos)
        else:
            if "U_BOOT_FDT_OVERLAYS" in extcfg.keys():
                del extcfg["U_BOOT_FDT_OVERLAYS"]

        extcfg = dt.encode_uboot(extcfg)

        if not DRYRUN:
            elevated_file_write("/etc/default/u-boot", extcfg)
        else:
            c.message(
                [
                    "The u-boot config would have been updated with the following:",
                    "",
                    extcfg,
                ],
                "DRYRUN Simulated Output",
            )

        runner(
            ["u-boot-update"],
            True,
            "Trigger U-Boot Update",
        )


# -------- ACTIVATABLE COMMANDS ---------


def filesystem_maint() -> None:
    cmd = [
        "sh",
        "-c",
        'findmnt -n -o FSTYPE / | grep -q btrfs && echo "Detected BTRFS root, performing balance operation." && echo && echo "Running 50% balance (Step 1/3)" && btrfs balance start -dusage=50 -musage=50 / && echo "Running 30% balance (Step 2/3)" && btrfs balance start -dusage=30 -musage=30 / && echo "Running 75% balance (Step 3/3)" && btrfs balance start -dusage=75 -musage=75 /',
    ]
    if c.confirm(
        [
            "This will perform a BTRFS balance operation.",
            "",
            "Authentication will be required, do you wish to continue?",
        ],
        "Filesystem Maintenance",
    ):
        runner(cmd, True, "Filesystem Maintenance")


def filesystem_check() -> None:
    cmd = [
        "sh",
        "-c",
        'findmnt -n -o FSTYPE / | grep -q btrfs && echo "Detected BTRFS root, performing scrub." && btrfs scrub start -Bd /',
    ]
    if c.confirm(
        [
            "This will perform a full BTRFS scrub operation.",
            "Cancelling is not adviced.",
            "",
            "Save your work before continuing.",
            "",
            "ARE YOU SURE YOU WANT TO CONTINUE?",
        ],
        "Filesystem Check",
    ):
        runner(cmd, True, "Filesystem Check")


def filesystem_resize() -> None:
    cmd = [
        "sh",
        "-c",
        'systemctl enable resizefs && echo "The filesystem will be expanded upon the next reboot!"',
    ]
    if c.confirm(
        [
            "This enables a service present and used upon the first boot of the device.",
            "This is a safe operation.",
            "",
            "Do you wish to continue?",
        ],
        "Pancake spirit",
    ):
        runner(cmd, True, "Filesystem Resize")
    else:
        c.message(["This incident will be reported to Santa Claus."], "Pancake spirit")


def wipe_journal() -> None:
    cmd = [
        "sh",
        "-c",
        'journalctl --rotate && journalctl --vacuum-time=1s && echo "Journal wiped."',
    ]
    if c.confirm(
        [
            "This wipes all system logs, including runtime logs.",
            "This is a safe operation.",
        ],
        "Journal Cleaner",
    ):
        runner(cmd, True, "Journal Cleaner")


def mkinit() -> None:
    cmd = ["sh", "-c", "mkinitcpio -P"]

    # Detect dracut
    dracut_path = shutil.which("dracut-rebuild")
    if dracut_path:
        cmd.clear()
        cmd += ["sh", "-c", "dracut-rebuild"]

    if c.confirm(
        [
            "This will regenerate InitCPIO.",
            "Unless something is broken, this is a safe operation.",
        ],
        "Regenerate InitCPIO",
    ):
        runner(cmd, True, "Regenerate InitCPIO")


def migrate_cpio() -> None:
    c.message(["Migration between mkinitcpio & dracut not yet supported"], "Error")


def pacman_sync() -> None:
    hook_path = Path("/usr/share/libalpm/hooks/ZZ-sync.hook")
    exists = hook_path.exists()

    if c.confirm(
        [
            ("Remove" if exists else "Install") + " the pacman sync hook?",
            "",
            "This hook will automatically sync all filesystems after every transaction.",
            "This takes time but should result to less damage if power is lost after updates.",
            "This is a safe operation.",
        ],
        "Pacman Sync Hook",
    ):
        if exists:
            runner(
                ["sh", "-c", f"rm {hook_path!s}"],
                True,
                "Pacman Sync Hook",
                False,
            )
        else:
            hook_content = (
                "[Trigger]\n"
                "Operation = Install\n"
                "Operation = Upgrade\n"
                "Operation = Remove\n"
                "Type = Package\n"
                "Target = *\n"
                "\n"
                "[Action]\n"
                "Description = Flushing file system buffers...\n"
                "When = PostTransaction\n"
                "Exec = /bin/sh -c 'sync; sync; sync'\n"
            )

            elevated_file_write(hook_path, hook_content)
    else:
        return

    c.message(
        ["Pacman Sync Hook " + ("removed" if exists else "installed") + "."],
        "Pacman Sync Hook",
    )


def uboot_migrator() -> bool:
    if (not dt.extlinux_exists()) or dt.booted_with_edk():
        return True  # UEFI system

    installed = dt.safe_exists("/usr/bin/u-boot-update")
    if not installed:
        runner(
            [
                "sh",
                "-c",
                "pacman -Sy && pacman -S --noconfirm u-boot-update",
            ],
            True,
            "Installing U-Boot Updater",
            prompt=False,
        )

    extcfg = dt.parse_uboot()  # Will load defaults if not found
    if extcfg["U_BOOT_IS_SETUP"] == "false":
        res = c.confirm(
            [
                "Migrating to u-boot-update is required!",
                "",
                "Please make sure a system backup is available.",
                "Press Y to continue, N to abort.",
            ],
            "U-Boot-Update Migrator",
        )
        if not res:
            return False

        oldextcfg = dt.parse_extlinux_conf(
            Path("/boot/extlinux/extlinux.conf").read_text()
        )

        labels = oldextcfg["labels"]
        _, label_data = next(iter(labels.items()))

        extcfg["U_BOOT_IS_SETUP"] = "true"
        extcfg["U_BOOT_MENU_LABEL"] = "Beryllium OS"
        extcfg["U_BOOT_COPY_DTB_TO_BOOT"] = "true"

        if "append" in label_data:
            params = label_data["append"]
            extcfg["U_BOOT_PARAMETERS"] = re.sub(r"\s*root=[^\s]+", "", params).strip()

        if "fdt" in label_data:
            dtb = label_data["fdt"]
            extcfg["U_BOOT_FDT"] = dtb[dtb.rfind("/") + 1 :]
        else:
            if "U_BOOT_FDT" in extcfg:
                del extcfg["U_BOOT_FDT"]

        if "fdtoverlays" in label_data:
            dtbos = label_data["fdtoverlays"]
            for i in range(len(dtbos)):
                dtbos[i] = normalize_filename(dtbos[i], "dtbo")
            extcfg["U_BOOT_FDT_OVERLAYS"] = " ".join(
                i.rsplit("/", 1)[-1] for i in dtbos
            )

        extcfg = dt.encode_uboot(extcfg)

        if not DRYRUN:
            elevated_file_write("/etc/default/u-boot", extcfg)
        else:
            c.message(
                [
                    "The U-Boot config would have been updated with the following:",
                    "",
                    extcfg,
                ],
                "DRYRUN Simulated Output",
            )

        runner(
            ["u-boot-update"],
            True,
            "Trigger U-Boot Update",
        )

        c.message(["Migration complete!"], "U-Boot-Update Migrator")
    return True


def gen_dt_report() -> list:
    dts = dt.gencache()
    txt = ["Base Device Trees:"]
    if dts["base"]:
        maxnl = max(len(v["name"]) for v in dts["base"].values())
        maxde = max(
            max(
                len(v["description"] if v["description"] is not None else [])
                for v in dts["base"].values()
            ),
            11,
        )
        maxco = max(len(",".join(v["compatible"])) for v in dts["base"].values())
        txt.append(f'{"NAME".ljust(maxnl)} | {"DESCRIPTION".ljust(maxde)} | COMPATIBLE')
        for tree in sorted(list(dts["base"].keys())):
            base = dts["base"][tree]
            name = base["name"]
            desc = base["description"] or ""

            compat = base["compatible"]
            if compat:
                compat_str = " ".join(compat)
            else:
                compat_str = ""

            txt.append(f"{name.ljust(maxnl)} | {desc.ljust(maxde)} | {compat_str}")
    else:
        txt.append("No base DTBs detected on the system.")
    txt += ["", "Overlays:"]
    if dts["overlays"]:
        maxnl = max(len(v["name"]) for v in dts["overlays"].values())
        maxde = max(
            max(
                len(v["description"] if v["description"] is not None else [])
                for v in dts["overlays"].values()
            ),
            11,
        )
        maxco = max(len(",".join(v["compatible"])) for v in dts["overlays"].values())
        txt.append(f'{"NAME".ljust(maxnl)} | {"DESCRIPTION".ljust(maxde)} | COMPATIBLE')
        for tree in sorted(list(dts["overlays"].keys())):
            overlay = dts["overlays"][tree]
            name = overlay["name"]
            desc = overlay["description"] or ""

            compat = overlay["compatible"]
            if compat:
                compat_str = " ".join(compat)
            else:
                compat_str = ""

            txt.append(f"{name.ljust(maxnl)} | {desc.ljust(maxde)} | {compat_str}")
    else:
        txt.append("No overlays detected on the system.")
    ovs = ["  - " + c for c in dt.identify_overlays()]
    txt += ["", "Enabled Overlays:"] + ovs
    txt += ["", "Live System Tree:"]
    base, overlays = dt.detect_live()
    txt += [f"Base: {base}", "", "Live Overlay-like entries (diffs):"]
    for line in overlays:
        txt.append("  + " + line)
    return txt


def dt_manager(cmd: list = []) -> None:
    c.message(["Please wait..", ""], "Generating Device Tree Caches", False)

    migrated = uboot_migrator()
    if not migrated:
        return

    dts = dt.gencache()
    if not dts["base"]:
        c.message(["No Device Trees were detected!"], "Device Tree Manager")
        return

    if c.stdscr is None:
        if not cmd:
            print("No operations specified.\n\nUsage: list/base/overlay\n")
        else:
            if cmd[0] == "list":
                print("\n".join(gen_dt_report()))
            elif cmd[0] == "base":
                if len(cmd) > 1:
                    set_base_dtb(cmd[1])
                else:
                    live, _ = dt.detect_live()
                    if live:
                        live = str(live)
                        live = live[live.rfind("/") + 1 : live.rfind(".")]
                        print(f"Currently booted base DTB: {live}.dtb")
            elif cmd[0] == "overlay":
                if len(cmd) > 1:
                    if cmd[1] == "enable":
                        existing = dt.identify_overlays()
                        dtbos = cmd[2:]
                        for i in range(len(existing)):
                            existing[i] = normalize_filename(existing[i], "dtbo")
                        for i in range(len(dtbos)):
                            dtbos[i] = normalize_filename(dtbos[i], "dtbo")
                        for i in dtbos:
                            if i not in existing:
                                existing.append(i)
                        set_overlays(existing)
                    elif cmd[1] == "disable":
                        existing = dt.identify_overlays()
                        dtbos = cmd[2:]
                        for i in range(len(existing)):
                            existing[i] = normalize_filename(existing[i], "dtbo")
                        for i in range(len(dtbos)):
                            dtbos[i] = normalize_filename(dtbos[i], "dtbo")
                        for i in dtbos:
                            if i in existing:
                                existing.remove(i)
                        set_overlays(existing)
                    else:
                        print(
                            "Invalid operation specified.\n\nUsage: enable/disable overlay.dtbo\n"
                        )
                else:
                    print(
                        "No operations specified.\n\nUsage: enable/disable overlay.dtbo\n"
                    )
            else:
                print("Invalid operation specified.\n\nUsage: list/base/overlay\n")
        return

    options = [
        "Set the Base Device Tree",
        "Enable / Disable Overlays",
        "View Currently Enabled Trees",
        "Main Menu",
    ]

    while True:
        selection = c.draw_menu("Device Tree Manager", options)
        if selection is None or options[selection] == "Main Menu":
            return

        c.stdscr.clear()
        c.stdscr.refresh()
        if options[selection] == "Set the Base Device Tree":
            maxnl = max(len(v["name"]) for v in dts["base"].values())
            maxde = max(
                len(v["description"] if v["description"] is not None else [])
                for v in dts["base"].values()
            )
            maxco = max(len(",".join(v["compatible"])) for v in dts["base"].values())

            basedt = []
            matchdt = []
            preselect = -1
            live, _ = dt.detect_live()
            if live:
                live = str(live)
                live = live[live.rfind("/") + 1 : live.rfind(".")]

            for tree in sorted(list(dts["base"].keys())):
                base = dts["base"][tree]
                name = base["name"]

                compat = base["compatible"]
                if compat:
                    compat_str = " ".join(compat)
                else:
                    compat_str = ""

                basedt.append(f"{name.ljust(maxnl)} | {compat_str}")
                if name == live:
                    preselect = len(matchdt)
                matchdt.append(tree)

            res = c.selector(basedt, False, "Select a device Tree", preselect=preselect)

            if res is not None:
                sel = c.confirm(
                    [
                        "Confirm the following changes:",
                        "",
                        "Base DTB set to:",
                        matchdt[res],
                    ],
                    "Confirm System Changes",
                )

                if sel:
                    set_base_dtb(matchdt[res])

        if options[selection] == "Enable / Disable Overlays":
            if not dts["overlays"]:
                c.message(
                    ["No overlays were detected on the system!"], "Device Tree Manager"
                )
                continue

            maxnl = max(len(v["name"]) for v in dts["overlays"].values())
            maxde = max(
                len(v["description"] if v["description"] is not None else [])
                for v in dts["overlays"].values()
            )
            maxco = max(
                len(",".join(v["compatible"])) for v in dts["overlays"].values()
            )

            basedt = []
            matchdt = []
            live = dt.identify_overlays()
            preselect = []

            for i in range(len(live)):
                live[i] = str(live[i])
                live[i] = live[i][live[i].rfind("/") + 1 : live[i].rfind(".")]

            for tree in sorted(list(dts["overlays"].keys())):
                base = dts["overlays"][tree]
                name = base["name"]
                desc = base["description"] or ""

                compat = base["compatible"]
                if compat:
                    compat_str = " ".join(compat)
                else:
                    compat_str = ""

                basedt.append(f"{name.ljust(maxnl)} | {compat_str}")
                if name in live:
                    preselect.append(len(matchdt))
                matchdt.append(tree)

            res = c.selector(basedt, True, "Select overlays", preselect=preselect)

            if res:
                dtbos = []
                for i in res:
                    dtbos.append(matchdt[i])

                res = c.confirm(
                    [
                        "Confirm the following changes:",
                        "",
                        "Overlays set to:",
                    ]
                    + dtbos,
                    "Confirm System Changes",
                )

                if res:
                    set_overlays(dtbos)

        if options[selection] == "View Currently Enabled Trees":
            c.message(gen_dt_report(), "Overlay Information")


def hack_pipewire() -> None:
    res = False
    service_path = Path.home() / ".config/systemd/user/pipewire.service"
    service_content = """[Unit]
Description=PipeWire Multimedia Service

# We require pipewire.socket to be active before starting the daemon, because
# while it is possible to use the service without the socket, it is not clear
# why it would be desirable.
#
# A user installing pipewire and doing `systemctl --user start pipewire`
# will not get the socket started, which might be confusing and problematic if
# the server is to be restarted later on, as the client autospawn feature
# might kick in. Also, a start of the socket unit will fail, adding to the
# confusion.
#
# After=pipewire.socket is not needed, as it is already implicit in the
# socket-service relationship, see systemd.socket(5).
Requires=pipewire.socket

[Service]
CPUAccounting=true
CPUQuota=10%
LockPersonality=yes
MemoryDenyWriteExecute=yes
NoNewPrivileges=yes
RestrictNamespaces=yes
SystemCallArchitectures=native
SystemCallFilter=@system-service
Type=simple
ExecStart=/usr/bin/pipewire
Restart=on-failure
Slice=session.slice

[Install]
Also=pipewire.socket
WantedBy=default.target
"""

    if service_path.exists():
        if c.confirm(["Remove the hack?"], "Pipewire CPU Fix") and not DRYRUN:
            service_path.unlink()
        else:
            return
    else:
        if c.confirm(["Apply the hack?"], "Pipewire CPU Fix") and not DRYRUN:
            service_path.parent.mkdir(parents=True, exist_ok=True)
            service_path.write_text(service_content)
        else:
            return
        res = True

    c.message(
        [
            "Pipewire CPU Fix " + ("applied" if res else "removed") + ".",
            "Relog or Reboot to apply.",
        ],
        "Pipewire CPU Fix",
    )


def hack_wol() -> None:
    cmd = [
        "bash",
        "-c",
        'pacman -Qi beryllium-wol &>/dev/null && echo "Removing.." && pacman -R --noconfirm beryllium-wol || { echo "Installing.."; pacman -Sy; pacman -S --noconfirm beryllium-wol; }',
    ]
    if c.confirm(["Toggle the Wake-On-Lan hack?"], "Wake On Lan"):
        runner(cmd, True, "Wake On Lan")


def hack_gpgme() -> None:
    cmd = [
        "bash",
        "-c",
        "if [[ -L /usr/lib/libgpgme.so.11 ]]; then "
        + 'echo "Removing symlink.."; rm /usr/lib/libgpgme.so.11; '
        + "elif [[ -e /usr/lib/libgpgme.so.11 ]]; then "
        + 'echo "File exists and is not a symlink. Doing nothing."; '
        + "else "
        + 'echo "Creating symlink.."; ln -s /usr/lib/libgpgme.so /usr/lib/libgpgme.so.11; '
        + "fi",
    ]
    if c.confirm(
        [
            "This hack applies / removes a gnupg fix to counter ALARM's stupidity.",
            "This should be removed once ALARM updates.",
        ],
        "ALARM IS STUPID",
    ):
        runner(cmd, True, "ALARM IS STUPID")


def hack_journal_persistent() -> None:
    dropin_path = Path("/etc/systemd/journald.conf.d/00-beryllium-volatile.conf")
    dropin_content = "[Journal]\nStorage=volatile\n"
    journal_dir = Path("/var/log/journal")

    if dropin_path.exists():
        if not c.confirm(
            [
                "Persistent journaling is currently disabled.",
                "",
                "Re-enable it? Logs will be stored on disk again.",
            ],
            "Persistent Journaling",
        ):
            return
        if not DRYRUN:
            dropin_path.unlink()
            try:
                dropin_path.parent.rmdir()
            except OSError:
                pass
            journal_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "sh",
            "-c",
            "systemctl restart systemd-journald && systemctl restart systemd-journal-flush",
        ]
        runner(cmd, True, "Persistent Journaling")
        c.message(["Persistent journaling re-enabled."], "Persistent Journaling")
    else:
        if not c.confirm(
            [
                "Disable persistent journaling?",
                "",
                "Logs will be kept in RAM only and are lost on reboot.",
                "All on-disk journal data will be discarded.",
            ],
            "Persistent Journaling",
        ):
            return
        if not DRYRUN:
            dropin_path.parent.mkdir(parents=True, exist_ok=True)
            dropin_path.write_text(dropin_content)
        cmd = [
            "sh",
            "-c",
            "systemctl stop systemd-journald.socket systemd-journald.service"
            " && rm -rf /var/log/journal"
            " && systemctl start systemd-journald.socket",
        ]
        runner(cmd, True, "Persistent Journaling")
        c.message(
            [
                "Persistent journaling disabled.",
                "Logs are stored in RAM only and are lost on reboot.",
            ],
            "Persistent Journaling",
        )


def hack_readonly() -> None:
    module_dir = Path("/usr/lib/dracut/modules.d/99beryllium-readonly")

    module_setup = """#!/bin/bash
# Standalone module: enabled whenever requested explicitly.
check() {
    return 0
}

install() {
    dracut_install mount umount mkdir mountpoint
    dracut_install awk tr
    instmods overlay
    instmods vfat nls_cp437 nls_iso8859-1
    inst_hook pre-pivot 01 "$moddir/beryllium-readonly-mount.sh"
}
"""
    mount_hook = """#!/bin/sh
# Re-mount the real root as an OverlayFS with a tmpfs upper.
# The toggle is a marker file (beryllium-ro) on the persistent boot
# filesystem: /boot on u-boot systems, /boot/efi on UEFI systems.
# Marker present -> boot read-write; absent -> read-only overlay root.
# All writes land in RAM and are discarded at shutdown.
# Installed as a pre-pivot hook: it is sourced after /sysroot is
# mounted by sysroot.mount and before switch_root moves it to /.
# Mount hooks are only a fallback on systemd dracut, so mount would
# never run.
BASE=/run/beryllium-readonly
UPPER=$BASE/upper
WORK=$BASE/work
LOWER=$BASE/lower
FLAGDIR=/run/beryllium-readonly-flag

readonly_boot() {
    warn "beryllium-readonly: booting with a read-only root"
}

boot_rw() {
    warn "beryllium-readonly: falling back to a read-write root"
    return 0
}

# Real root must be mounted by now. If it is not, there is nothing to
# shadow, so continue booting as the read-write root.
[ -d /sysroot/usr ] && mountpoint -q /sysroot || {
    warn "beryllium-readonly: /sysroot is not mounted; booting read-write"
    return 0
}

# fstab line for a given mountpoint, without comment lines.
boot_spec() {
    awk -v mp="$1" '
        /^[ \\t]*#/ { next }
        $2 == mp { print; exit }
    ' /sysroot/etc/fstab
}

# Returns 0 only if the marker is found on the given mountpoint.
check_for_marker() {
    mp=$1
    spec=$(boot_spec "$mp")
    [ -n "$spec" ] || {
        warn "beryllium-readonly: no fstab entry for $mp; continuing"
        return 1
    }
    dev=$(printf %s "$spec" | awk '{ print $1 }')
    fstype=$(printf %s "$spec" | awk '{ print $3 }')
    case "$dev" in
        UUID=*|PARTUUID=*)
            # /dev/disk/by-uuid/by-partuuid entries are lowercase for
            # most filesystems, but FAT-family UUIDs are uppercase
            # (e.g. /dev/disk/by-uuid/B022-79C2).
            id=${dev#*=}
            case "$fstype" in
                vfat|msdos|exfat) id=$(printf %s "$id" | tr 'a-f' 'A-F') ;;
                *) id=$(printf %s "$id" | tr 'A-F' 'a-f') ;;
            esac
            case "$dev" in
                UUID=*) dev=/dev/disk/by-uuid/$id ;;
                PARTUUID=*) dev=/dev/disk/by-partuuid/$id ;;
            esac
            ;;
        LABEL=*) dev=/dev/disk/by-label/$(printf %s "${dev#LABEL=}") ;;
        PARTLABEL=*) dev=/dev/disk/by-partlabel/$(printf %s "${dev#PARTLABEL=}") ;;
    esac
    if mount -t "$fstype" -o ro "$dev" $FLAGDIR; then
        ret=1
        [ -e $FLAGDIR/beryllium-ro ] && ret=0
        umount $FLAGDIR
        return $ret
    fi
    warn "beryllium-readonly: cannot mount $mp to check the marker; continuing"
    return 1
}

# The marker may live on /boot (u-boot layouts) or /boot/efi (UEFI
# layouts). A marker in any location is sufficient for a read-write
# boot; absence everywhere defaults to read-only.
if ! mkdir -p $FLAGDIR; then
    warn "beryllium-readonly: cannot create $FLAGDIR; defaulting to read-only root"
elif check_for_marker /boot || check_for_marker /boot/efi; then
    info "beryllium-readonly: marker found, booting read-write"
    return 0
fi

size_kb=$(awk '/MemTotal/ { print int($2 / 2) }' /proc/meminfo)
[ -n "$size_kb" ] && [ "$size_kb" -gt 0 ] || {
    warn "beryllium-readonly: cannot size tmpfs"
    boot_rw
    return 0
}

mkdir -p $BASE || { boot_rw; return 0; }
mount -t tmpfs -o size=${size_kb}k tmpfs $BASE || { boot_rw; return 0; }
mkdir -p $UPPER $WORK $LOWER || { boot_rw; return 0; }

mount --bind /sysroot $LOWER || { boot_rw; return 0; }

mount -t overlay overlay \\
    -o lowerdir=$LOWER,upperdir=$UPPER,workdir=$WORK \\
    /sysroot || {
    warn "beryllium-readonly: overlay mount failed"
    umount $LOWER
    umount $BASE
    boot_rw
    return 0
}

# Present an ephemeral fstab to the real root, copied up into the
# overlay upper so it vanishes at reboot: the root entry is dropped
# (systemd-remount-fs cannot remount an overlay root and would fail),
# and btrfs subvolume mounts (/home, /var/log, ...) become read-only
# so no writes persist through them. /boot (and the ESP) keep their
# options: the marker must stay writable.
awk '
    /^[ \t]*#/ { print; next }
    $2 == "/" { print "# " $0 "  # beryllium-readonly: overlay root"; next }
    $3 == "btrfs" && $2 !~ /^\\/boot/ && NF >= 4 {
        opts = $4
        gsub(/(^|,)ro(,|$)/, ",", opts)
        gsub(/(^|,)rw(,|$)/, ",", opts)
        sub(/^,/, "", opts)
        sub(/,$/, "", opts)
        $4 = (opts == "" ? "ro" : "ro," opts)
    }
    { print }
' /sysroot/etc/fstab > /sysroot/etc/fstab.beryllium-readonly \
    && mv /sysroot/etc/fstab.beryllium-readonly /sysroot/etc/fstab \\
    || warn "beryllium-readonly: cannot adjust the fstab; subvolume mounts will persist"

readonly_boot
return 0
"""

    def _boot_marker_path() -> "Path | None":
        # /boot on u-boot systems (boot partition mount), /boot/efi on
        # UEFI systems (ESP mount). /proc/self/mounts escapes spaces
        # as \040.
        with open("/proc/self/mounts", "r") as mounts:
            for line in mounts:
                fields = line.split()
                if len(fields) < 3:
                    continue
                mountpoint = fields[1].replace("\\040", " ")
                if mountpoint == "/boot":
                    return Path("/boot/beryllium-ro")
                if mountpoint == "/boot/efi":
                    return Path("/boot/efi/beryllium-ro")
        return None

    if shutil.which("dracut-rebuild") is None:
        c.message(
            ["dracut-rebuild is not installed, cannot manage the image."],
            "Read-Only Root",
        )
        return

    marker_path = _boot_marker_path()
    if marker_path is None:
        c.message(
            [
                "Neither /boot nor /boot/efi is a mountpoint.",
                "There is no persistent location for the toggle marker.",
            ],
            "Read-Only Root",
        )
        return

    root_overlaid = False
    with open("/proc/self/mounts", "r") as mounts:
        for line in mounts:
            fields = line.split()
            if len(fields) > 2 and fields[1] == "/" and fields[2] == "overlay":
                root_overlaid = True
                break

    marker_exists = marker_path.exists()
    marker_arg = shlex.quote(str(marker_path))

    module_version = "4"

    def _install_module_files() -> None:
        module_dir.mkdir(parents=True, exist_ok=True)
        (module_dir / "module-setup.sh").write_text(module_setup)
        (module_dir / "beryllium-readonly-mount.sh").write_text(mount_hook)
        (module_dir / "version").write_text(module_version + "\n")
        os.chmod(module_dir / "beryllium-readonly-mount.sh", 0o755)

    installed_version = None
    if module_dir.exists():
        try:
            installed_version = (module_dir / "version").read_text().strip()
        except OSError:
            installed_version = None
    module_stale = module_dir.exists() and installed_version != module_version

    # The authoritative staleness is what is in the initramfs image,
    # not the disk copy: the disk files can be current while the image
    # still holds an older module.
    image_version = None
    if module_dir.exists():
        try:
            image_version = (module_dir / "image-version").read_text().strip()
        except OSError:
            image_version = None
    rebuild_needed = (
        not module_dir.exists() or module_stale or image_version != module_version
    )

    def _stamp_cmd() -> str:
        # Writes the image stamp only when the rebuild actually
        # succeeded, so a failed rebuild leaves the image visibly
        # stale and the next toggle retries.
        return (
            "printf "
            + shlex.quote("%s\n")
            + " "
            + shlex.quote(module_version)
            + " > "
            + shlex.quote(str(module_dir / "image-version"))
        )

    if module_dir.exists() and not marker_exists:
        # Enabled -> disable is a single marker write, safe on every
        # layout from every kind of session (the marker lives on a
        # mount outside the overlay).
        if not c.confirm(
            [
                "Read-only root is currently enabled.",
                "",
                "Disable it? The next boot will be read-write.",
                "This writes a marker file to " + str(marker_path) + ".",
                "The running session keeps its RAM-backed root until reboot.",
            ],
            "Read-Only Root",
        ):
            return
        if not DRYRUN:
            try:
                marker_path.write_text("disabled\n")
                os.sync()
            except OSError:
                c.message(
                    ["Failed to write the marker file."],
                    "Read-Only Root",
                )
                return
            if rebuild_needed and not root_overlaid:
                # Self-heal the module and rebuild the initramfs now.
                # Safe here: the marker forces a read-write boot.
                if module_stale:
                    try:
                        shutil.rmtree(module_dir)
                    except OSError:
                        pass
                try:
                    _install_module_files()
                    os.sync()
                except OSError:
                    pass
                runner(
                    [
                        "sh",
                        "-c",
                        "dracut-rebuild && " + _stamp_cmd() + " && sync",
                    ],
                    True,
                    "Read-Only Root",
                )
        c.message(
            [
                "Read-only root disabled.",
                "Applies on the next reboot.",
            ],
            "Read-Only Root",
        )
        return

    # Enabling.
    if rebuild_needed and root_overlaid:
        c.message(
            [
                "The root is overlaid this boot: the rebuilt initramfs",
                "(and /boot itself on the UEFI layout) would be written",
                "to RAM only and lost, leaving the module in a limbo state.",
                "Disable the read-only root first (one marker write), reboot,",
                "then run this again from the read-write system, or use a chroot.",
            ],
            "Read-Only Root",
        )
        return

    messages = [
        "Enable a read-only root?",
        "",
        "The real root is shadowed by an OverlayFS with a tmpfs upper (half of RAM).",
        "All writes to the root are discarded at the next reboot:",
        "installs, updates and host-key changes appear to work but vanish.",
        "Btrfs subvolume mounts (/home, /var/log, ...) are re-mounted",
        "read-only via an ephemeral fstab, so nothing persists through",
        "them either; only the boot filesystem stays read-write.",
        "",
        "The toggle is a marker file at " + str(marker_path) + ":",
        "present = read-write boot, absent = read-only boot.",
        "Further toggles only touch the marker, no initramfs rebuilds.",
        "",
        "EXPERIMENTAL: this has not been tested broadly and may lead to",
        "unforeseen consequences, up to and including an unbootable system.",
        "Test at your own risk; the marker fallback should keep the next",
        "boot read-write if the rebuild fails, but nothing is guaranteed.",
    ]
    if rebuild_needed:
        messages += [
            "",
            "This (re)installs the dracut module and regenerates the",
            "initramfs now.",
        ]
    if not c.confirm(messages, "Read-Only Root"):
        return

    if not DRYRUN:
        if rebuild_needed:
            try:
                if module_stale:
                    shutil.rmtree(module_dir)
                _install_module_files()
            except OSError:
                c.message(
                    ["Failed to install the dracut module."],
                    "Read-Only Root",
                )
                return
            # Safety latch: if the rebuild fails or the machine dies
            # mid-rebuild, the marker keeps the system read-write and
            # recoverable instead of leaving a stale enabled state.
            try:
                marker_path.write_text("disabled\n")
                os.sync()
            except OSError:
                c.message(
                    [
                        "Failed to write the marker file.",
                        "The module is installed but stays disabled.",
                    ],
                    "Read-Only Root",
                )
                return

        else:
            try:
                marker_path.unlink()
                os.sync()
            except OSError:
                c.message(
                    ["Failed to remove the marker file."],
                    "Read-Only Root",
                )
                return

    if rebuild_needed:
        runner(
            [
                "sh",
                "-c",
                "dracut-rebuild && "
                + _stamp_cmd()
                + " && rm -f "
                + marker_arg
                + " && sync",
            ],
            True,
            "Read-Only Root",
        )
        if not DRYRUN and marker_path.exists():
            # dracut-rebuild failed or was aborted, so the marker write
            # kept the system read-write instead of enabling.
            c.message(
                [
                    "The initramfs rebuild failed or was aborted.",
                    "Read-only root was not enabled; the next boot",
                    "stays read-write.",
                ],
                "Read-Only Root",
            )
            return

    c.message(
        [
            "Read-only root enabled.",
            "Applies on the next reboot.",
        ],
        "Read-Only Root",
    )


def pacman_integrity() -> None:
    cmd = [
        "sh",
        "-c",
        r"""echo "Running.." && pacman -Qkk 2>/dev/null | awk '
/:.*(missing|Size mismatch|MODIFIED)/ &&
$0 !~ /\.json|\.conf|\.pac(new|save|orig)/ &&
$0 !~ /\/\.?(bashrc|bash_profile|zshrc|profile)$/ &&
$0 !~ /^.*\/etc\/(shells|subgid|subuid|environment|sudoers|passwd|shadow|group|gshadow|fstab|mtab|issue|default\/|skel\/|locale\.gen|ssh\/|libvirt\/|pacman\.d\/mirrorlist|conf\.d\/snapper)/ &&
$0 !~ /\/usr\/share\/(doc|man)|\.cache/ {
    pkg = gensub(/:.*$/, "", 1, $0);
    issues[pkg]++;
    print;
    found = 1;
}
END {
    if (found) {
        print "\n==== Summary ====";
        for (p in issues) print p ": " issues[p] " issue(s)";
    } else {
        print "+++ No integrity issues found. +++";
    }
}
'""",
    ]
    runner(cmd, False, "Check Packages Integrity")


def install_recommends() -> None:
    cmd = [
        "sh",
        "-c",
        "pacman -Sy && pacman -S --noconfirm --needed"
        + " legcord-bin"
        + " ayugram-desktop"
        + " thunderbird"
        + " gnome-disk-utility"
        + " mpv"
        + " libreoffice-fresh"
        + " timeshift"
        + " proton-run"
        + " evince"
        + " loupe",
    ]
    if c.confirm(
        [
            "This will install the following packages:",
            "",
            " - legcord-bin",
            " - ayugram-desktop",
            " - thunderbird",
            " - gnome-disk-utility",
            " - mpv",
            " - libreoffice-fresh",
            " - timeshift",
            " - proton-run",
            " - evince",
            " - loupe",
            "",
            "Are you sure you wish to continue?",
        ],
        "Install Recommended Packages",
    ):
        runner(cmd, True, "Install Recommended Packages")


def install_docker() -> None:
    cmd = [
        "sh",
        "-c",
        "pacman -Sy && pacman -S --noconfirm --needed"
        + " docker"
        + " docker-buildx"
        + " docker-compose"
        + " pigz"
        + " criu"
        + " && systemctl disable --now systemd-networkd-wait-online"
        + " && systemctl mask systemd-networkd-wait-online"
        + " && systemctl enable --now docker",
    ]
    if c.confirm(
        [
            "This will install AND ENABLE the following packages:",
            "",
            " - docker",
            " - docker-buildx",
            " - docker-compose",
            " - pigz",
            " - criu",
            "",
            "Are you sure you wish to continue?",
        ],
        "Install Docker",
    ):
        runner(cmd, True, "Install Docker")


def install_steam() -> None:
    cmd = [
        "sh",
        "-c",
        "pacman -Sy && pacman -S --noconfirm --needed steam",
    ]
    if c.confirm(
        [
            "This will install the Steam package.",
            "",
            "Are you sure you wish to continue?",
        ],
        "Install Steam",
    ):
        runner(cmd, True, "Install Steam")


def install_development() -> None:
    cmd = [
        "sh",
        "-c",
        "pacman -Sy && pacman -S --noconfirm --needed"
        + " python-prettytable"
        + " devtools"
        + " grub"
        + " parted"
        + " gptfdisk"
        + " edk2-rk3588-devel"
        + " dtc"
        + " xmlto"
        + " docbook-xsl"
        + " kmod"
        + " bc"
        + " uboot-tools"
        + " beryllium-tools",
    ]
    if c.confirm(
        [
            "This will install the following packages:",
            "",
            " - python-prettytable",
            " - devtools" " - grub",
            " - parted",
            " - gptfdisk",
            " - edk2-rk3588-devel",
            " - dtc",
            " - xmlto",
            " - docbook-xsl",
            " - kmod",
            " - bc",
            " - uboot-tools",
            " - beryllium-tools",
            "",
            "Are you sure you wish to continue?",
        ],
        "Install Beryllium OS Development Packages",
    ):
        runner(cmd, True, "Install Beryllium OS Development Packages")


def install_gnome() -> None:
    cmd = [
        "sh",
        "-c",
        "pacman -Sy && pacman -S --noconfirm --needed"
        + " gnome-app-list"
        + " gnome-autoar"
        + " gnome-backgrounds"
        + " gnome-bluetooth-3.0"
        + " gnome-calculator"
        + " gnome-characters"
        + " gnome-clocks"
        + " gnome-color-manager"
        + " gnome-control-center"
        + " gnome-desktop"
        + " gnome-desktop-4"
        + " gnome-desktop-common"
        + " gnome-disk-utility"
        + " gnome-keybindings"
        + " gnome-keyring"
        + " gnome-menus"
        + " gnome-online-accounts"
        + " gnome-power-manager"
        + " gnome-session"
        + " gnome-settings-daemon"
        + " gnome-shell"
        + " gnome-shell-extensions"
        + " gnome-system-monitor"
        + " gnome-themes-extra"
        + " gnome-tweaks"
        + " gnome-user-share"
        + " gnome-weather"
        + " polkit-gnome"
        + " xdg-desktop-portal-gnome"
        + " extension-manager"
        + " evince"
        + " caribou"
        + " nautilus"
        + " nautilus-python"
        + " libnautilus-extension"
        + " gdm",
    ]
    if c.confirm(
        [
            "This will install the following packages:",
            "",
            " - gnome-app-list",
            " - gnome-autoar",
            " - gnome-backgrounds",
            " - gnome-bluetooth-3.0",
            " - gnome-calculator",
            " - gnome-characters",
            " - gnome-clocks",
            " - gnome-color-manager",
            " - gnome-control-center",
            " - gnome-desktop",
            " - gnome-desktop-4",
            " - gnome-desktop-common",
            " - gnome-disk-utility",
            " - gnome-keybindings",
            " - gnome-keyring",
            " - gnome-menus",
            " - gnome-online-accounts",
            " - gnome-power-manager",
            " - gnome-session",
            " - gnome-settings-daemon",
            " - gnome-shell",
            " - gnome-shell-extensions",
            " - gnome-system-monitor",
            " - gnome-themes-extra",
            " - gnome-tweaks",
            " - gnome-user-share",
            " - gnome-weather",
            " - polkit-gnome",
            " - xdg-desktop-portal-gnome",
            " - extension-manager",
            " - evince",
            " - caribou",
            " - nautilus",
            " - nautilus-python",
            " - libnautilus-extension",
            " - gdm",
            "",
            "Are you sure you wish to continue?",
        ],
        "Install GNOME Desktop",
    ):
        runner(cmd, True, "Install GNOME Desktop")

    if c.confirm(
        [
            "Enable the Gnome Display Manager (GDM)?",
            "",
            "This will disable your existing Display Manager automatically.",
        ],
        "Enable Gnome Display Manager",
    ):
        symlink_path = Path("/etc/systemd/system/display-manager.service")

        dewit = False
        if symlink_path.is_symlink():
            current_target = symlink_path.resolve().name
            if current_target != "gdm.service":
                runner(
                    ["systemctl", "disable", current_target],
                    True,
                    "Disable existing Display Manager",
                    False,
                )
                dewit = True
        else:
            dewit = True

        if dewit:
            runner(["systemctl", "enable", "gdm.service"], True, "Enable GDM", False)

        c.message(
            [
                "Done.",
                "",
                "Upon the next system restart you will be greeted by GDM and GNOME.",
            ],
            "Install GNOME Desktop",
        )


def unlock_pacman() -> None:
    cmd = [
        "bash",
        "-c",
        '[ -f /var/lib/pacman/db.lck ] && ! pgrep -x pacman >/dev/null && { sudo rm -f /var/lib/pacman/db.lck && echo "Pacman DB lock removed."; } || echo "No action needed."',
    ]
    elevate = True
    runner(cmd, True, "Unlock Pacman Database")


def autoremove() -> None:
    cmd = [
        "bash",
        "-c",
        "while pacman -Qdtq >/dev/null 2>&1; do sudo pacman -Rns --noconfirm $(pacman -Qdtq); done",
    ]
    elevate = True
    if c.confirm(
        [
            "This will REMOVE ALL PACKAGES that aren't:",
            " - Depended upon by another package",
            "  AND",
            " - Haven't been installed manually.",
            "",
            "Are you SURE you want this?",
        ],
        "Remove Unused Packages",
    ):
        runner(cmd, True, "Remove Unused Packages")


def repos_stable() -> None:
    c.message(["The repo switcher is temporarily disabled, sorry."], "Error")
    return

    if c.confirm(
        [
            "Stable repositories receive a minimum amount of testing",
            "to ensure system stability.",
            "",
            "If you want to make this system not break that often with updates,",
            "you're adviced to switch to them. This change can always be reverted.",
            "",
            "Switch to stable repos?",
        ],
        "Switch to stable repositories",
    ):
        # Fix stable-mirrorlist in filesystem
        elevated_file_write(
            "/etc/pacman.d/stable-mirrorlist",
            "## Stable Mirrorlist\nServer = https://mirror.bredos.org/repo/$repo/$arch\n",
        )

        # Read existing pacman.conf
        with open("/etc/pacman.conf") as f:  # Assume it's readable
            lines = f.readlines()
            modified = False

            for i, line in enumerate(lines):
                clean_line = line.strip()

                if clean_line in ["[core]", "[extra]"]:
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        # Only replace if it is currently pointing to the standard list
                        if next_line == "Include = /etc/pacman.d/mirrorlist":
                            lines[i + 1] = "Include = /etc/pacman.d/stable-mirrorlist\n"
                            modified = True

        # Write back modified pacman.conf
        if modified:
            elevated_file_write("/etc/pacman.conf", "".join(lines))
            pass
        else:
            pass


def repos_latest() -> None:
    c.message(["The repo switcher is temporarily disabled, sorry."], "Error")
    return

    if c.confirm(
        [
            "Latest repositories pull from upsteam Arch Linux ARM",
            "and are outside of testing.",
            "",
            "You're likely to see updates causing breakage.",
            "You'll receive the latest and greatest as fast as possible.",
            "",
            "Switch to latest repos?",
        ],
        "Switch to latest repositories",
    ):
        # Fix stable-mirrorlist in filesystem
        elevated_file_write(
            "/etc/pacman.d/stable-mirrorlist",
            "## Stable Mirrorlist\nServer = https://mirror.bredos.org/repo/$repo/$arch\n",
        )

        # Read existing pacman.conf
        with open("/etc/pacman.conf") as f:  # Assume it's readable
            lines = f.readlines()
            modified = False

            for i, line in enumerate(lines):
                clean_line = line.strip()

                if clean_line in ["[core]", "[extra]"]:
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        # Only replace if it is currently pointing to the standard list
                        if next_line == "Include = /etc/pacman.d/stable-mirrorlist":
                            lines[i + 1] = "Include = /etc/pacman.d/mirrorlist\n"
                            modified = True

        # Write back modified pacman.conf
        if modified:
            elevated_file_write("/etc/pacman.conf", "".join(lines))
            pass
        else:
            pass


def upkeep_menu():
    c.menu(
        "System Upkeep",
        {
            "Perform Filesystem Maintenance": filesystem_maint,
            "Check & Repair Filesystem": filesystem_check,
            "Expand Fileystem": filesystem_resize,
            "Check Packages Integrity": pacman_integrity,
            "Clean the system journal": wipe_journal,
            "Regenerate initcpio": mkinit,
        },
    )


def tweaks_menu() -> None:
    c.menu(
        "System Tweaks",
        {
            "General: Pipewire CPU fix": hack_pipewire,
            "General: Wake On Lan": hack_wol,
            "General: Pacman Sync hook": pacman_sync,
            "General: Persistent Journaling": hack_journal_persistent,
            "General: Read-Only Root (OverlayFS)": hack_readonly,
            "ARM: Apply GNUPG fix": hack_gpgme,
        },
    )


def packages_menu() -> None:
    c.menu(
        "Packages",
        {
            "Switch repositories": repos_menu,
            "Install Recommended Desktop Packages": install_recommends,
            "Install Docker": install_docker,
            "Install Steam": install_steam,
            "Install Beryllium OS Development Packages": install_development,
            "Install GNOME Desktop": install_gnome,
            "Unlock Pacman Database": unlock_pacman,
            "Autoremove Unused packages": autoremove,
            "Check Packages Integrity": pacman_integrity,
        },
    )


def migrations_menu() -> None:
    c.menu(
        "Migrations",
        {
            "Migrate initcpio": migrate_cpio,
        },
    )


def repos_menu() -> None:
    c.menu(
        "Repositories",
        {
            "Switch to the stable repositories": repos_stable,
            "Switch to the latest repositories": repos_latest,
        },
    )


def updater():
    c.message(["The updater is currently not implemented, sorry."], "Error")


def main_menu():
    c.init()
    c.menu(
        c.APP_NAME,
        {
            "Device Tree Manager": dt_manager,
            "Update the system": updater,
            "System Upkeep": upkeep_menu,
            "System Tweaks": tweaks_menu,
            "Migrations": migrations_menu,
            "Packages": packages_menu,
            # "Debug": debug_info,
        },
        "Exit",
    )


def tui():
    try:
        main_menu()
    finally:
        c.suspend()


# -------------- CLI LOGIC --------------


def dp(args):
    cmd = args.command

    if cmd == "dt":
        dt_manager(cmd=args.cmd)
    elif cmd == "updater":
        updater()
    elif cmd == "upkeep":
        if args.action == "maintenance":
            filesystem_maint()
        elif args.action == "check":
            filesystem_check()
        elif args.action == "expand":
            filesystem_resize()
        elif args.action == "journal":
            wipe_journal()
        elif args.action == "initcpio":
            mkinit()
    elif cmd == "tweaks":
        if args.action == "pipewire":
            hack_pipewire()
        elif args.action == "wol":
            hack_wol()
        elif args.action == "pacmansync":
            pacman_sync()
        elif args.action == "gpgme":
            hack_gpgme()
        elif args.action == "journal":
            hack_journal_persistent()
        elif args.action == "readonly":
            hack_readonly()
    elif cmd == "migrations":
        if args.action == "cpio":
            migrate_cpio()
    elif cmd == "packages":
        if args.action == "install":
            if args.target == "recommends":
                install_recommends()
            elif args.target == "docker":
                install_docker()
            elif args.target == "steam":
                install_steam()
            elif args.target == "development":
                install_development()
            elif args.target == "gnome":
                install_gnome()
        elif args.action == "unlock":
            unlock_pacman()
        elif args.action == "autoremove":
            autoremove()
        elif args.action == "integrity":
            pacman_integrity()
    elif cmd == "repos":
        if args.action == "stable":
            repos_stable()
        elif args.action == "latest":
            repos_latest()
    # elif cmd == "debug":
    #     debug_info()
    else:
        print("Unknown command")


# ----------------- MISC ------------------
def check_root() -> bool:
    if os.geteuid():
        return False
    return True


# -------------- ENTRY POINT --------------


def main():
    global LOG_FILE, NOCONFIRM, DRYRUN, ROOT_MODE
    parser = argparse.ArgumentParser(prog="bredos-config", description=c.APP_NAME)
    parser.add_argument(
        "--log",
        "-l",
        action="store_true",
        help="Log output to bredos-config-<date>.txt",
    )
    parser.add_argument(
        "--dryrun",
        "--dry-run",
        "-n",
        action="store_true",
        help="Simulate running commands (SAFE).",
    )
    parser.add_argument(
        "--noconfirm",
        "--no-confirm",
        "-c",
        action="store_true",
        help="Do not ask for confirmations.",
    )
    subparsers = parser.add_subparsers(dest="command")

    dt_parser = subparsers.add_parser("dt")
    dt_sub = dt_parser.add_argument("cmd", nargs=argparse.REMAINDER)

    updater_parser = subparsers.add_parser("updater")

    upkeep_parser = subparsers.add_parser("upkeep")
    upkeep_sub = upkeep_parser.add_subparsers(dest="action")
    upkeep_sub.add_parser("maintenance")
    upkeep_sub.add_parser("check")
    upkeep_sub.add_parser("expand")
    upkeep_sub.add_parser("journal")
    upkeep_sub.add_parser("initcpio")

    # Hacks
    hack_parser = subparsers.add_parser("tweaks")
    hack_sub = hack_parser.add_subparsers(dest="action")
    hack_sub.add_parser("pipewire")
    hack_sub.add_parser("wol")
    hack_sub.add_parser("gpgme")
    hack_sub.add_parser("pacmansync")
    hack_sub.add_parser("journal")
    hack_sub.add_parser("readonly")

    # Migrations
    migrations_parser = subparsers.add_parser("migrations")
    migrations_sub = migrations_parser.add_subparsers(dest="action")
    migrations_sub.add_parser("cpio")

    # Packages
    pac_parser = subparsers.add_parser("packages")
    pac_sub = pac_parser.add_subparsers(dest="action", required=True)

    # install sub-subcommands
    install_parser = pac_sub.add_parser("install")
    install_sub = install_parser.add_subparsers(dest="target", required=True)
    install_sub.add_parser("recommends")
    install_sub.add_parser("docker")
    install_sub.add_parser("steam")
    install_sub.add_parser("development")
    install_sub.add_parser("gnome")
    install_sub.add_parser("unlock")

    # Packages other actions
    pac_sub.add_parser("integrity")
    pac_sub.add_parser("unlock")
    pac_sub.add_parser("autoremove")

    # Info
    subparsers.add_parser("info")

    # Repos
    repos_parser = subparsers.add_parser("repos")
    repos_sub = repos_parser.add_subparsers(dest="action", required=True)
    repos_sub.add_parser("stable")
    repos_sub.add_parser("latest")

    # Debug
    # subparsers.add_parser("debug")

    args = parser.parse_args()

    if args.command == "upkeep" and args.action is None:
        upkeep_parser.print_help()
        sys.exit(1)

    if args.command == "tweaks" and args.action is None:
        hack_parser.print_help()
        sys.exit(1)

    if args.command == "migrations" and args.action is None:
        migrations_parser.print_help()
        sys.exit(1)

    # Save command log
    if args.log:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        LOG_FILE = f"bredos-config-{timestamp}.txt"

    if args.noconfirm:
        c.NOCONFIRM = True

    if args.dryrun:
        DRYRUN = True
        c.DRYRUN = True

    if check_root():
        ROOT_MODE = True

    if args.command is None:
        tui()
    else:
        dp(args)


if __name__ == "__main__":
    main()
