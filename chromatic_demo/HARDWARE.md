# Chromatic MCU Port Findings

Inspected October 5, 2026. Public source only; no device port opened, firmware changed, cartridge accessed, or RF test performed by this research worker.

## Immediate Prototype Route

The native Game Boy Color snapshot demo is the smaller first experiment. Generate a bounded NPC reply on the host, package it with selected Tuxemon assets into the ROM, then run that ROM through the existing native execution path. This avoids replacing MCU display, settings, battery, and sleep behavior. A reply baked into a ROM is a snapshot: live handheld-to-model conversations require a proven bidirectional mailbox or firmware client later.

USB cartridge programming or ROM loading is distinct from MCU flashing. The stock MCU console has `fwversion` and `poke`; it has no host framebuffer upload, arbitrary text display, or physical button telemetry command. Do not claim a live LLM connection on the device merely because host generation and a new ROM both work.

## Verified Source Baselines

- MCU: `ModRetro/oss-chromatic-console-mcu`, commit `e03a6baeec49cceda38057d5aed4ae006624c698`; local checkout `/private/tmp/tuxemon-hardware-research`.
- FPGA: `ModRetro/oss-chromatic-console-fpga`, commit `8b4c965dc3a57fd4412836c136b5228a63c72803`; local checkout `/private/tmp/tuxemon-hardware-research-fpga`.
- MCU `sdkconfig.defaults` declares app version `0.13.7`, Chromatic version `4.5`, and 4 MiB flash. `dependencies.lock` declares target `esp32`. These are source baseline values, not a reading of Sam's connected unit.
- MCU README recommends ESP-IDF v5.3. No `idf.py` or `xtensa-esp32-elf-gcc` was found in this worker's environment. The runtime has `rustup`, which does not establish an ESP32 Rust target or working firmware toolchain.

## MCU Display and Inputs

`main/main.c` allocates a DMA framebuffer of 160 × 144 `lv_color_t` pixels, registers LVGL v8 in direct/full-refresh mode, and sends the whole framebuffer by 40 MHz quad SPI to the FPGA. GPIO definitions live in `main/board.h`; the display route uses ESP32 VSPI with command and address fields. A second FreeRTOS task runs `lv_timer_handler` on core 1. `main/gfx.c` calls `OSD_HandleInputs` and `OSD_Draw` from an LVGL timer.

`main/fpga_rx.c` decodes the FPGA UART protocol and feeds `Button_Update` on `kRxCmd_Buttons`. `components/button/button.c` converts input bitmap transitions to consumed press events. `Button_GetState` clears each returned event and suppresses Select. A separate prototype handler must own input dispatch instead of calling this function after existing OSD widgets consume the same events.

`components/osd/osd.c` tracks menu visibility. The physical FPGA menu state controls whether the MCU framebuffer is composited: `esp32t/src/rtl/BSP/vid_system_top.sv` samples `~BTN_MENU` and blends non-magenta pixels into both LCD and UVC paths. RGB565 `0xF81F` is transparent. An MCU scene can plausibly fill the menu screen with opaque pixels while Menu is open; this has not been tested on the connected unit. Do not assume the MCU can independently force full-screen display while the menu is closed.

`main/fpga_tx.c` sends brightness, system configuration, palette data, version requests, and button pokes. Neither inspected MCU commands nor FPGA system-monitor handlers supply a proven ROM-visible dialogue mailbox. `esp32t/src/rtl/BSP/system_monitor.sv` sends button data primarily while the menu is open or explicitly requested.

## Wi-Fi Work Required

No Wi-Fi, network-interface, or HTTP initialization exists in the inspected MCU source. ESP32 capability alone does not prove an antenna, usable RF link, radio performance, or free RAM on this device revision. These remain unknown until a controlled build and physical scan/connect test.

The highest-risk integration detail is power management. `main/pwrmgr.c` starts a one-shot 100 ms idle timer; FPGA UART receive activity pets it. Expiry pauses FPGA TX/RX, flushes UART1, resets buttons, hides the OSD, and calls `esp_light_sleep_start`. Stock wake-up uses the FPGA UART GPIO. A live network request could be interrupted if prototype activity does not participate in this policy.

A focused later MCU change should:

1. Add a compile-time disabled-by-default prototype component and register its serial commands before `esp_console_start_repl` in `main/main.c`.
2. Add a small opaque scene and dialogue panel to `main/gfx.c`, preserving ordinary settings outside prototype mode. Apply network responses through a queue consumed by the LVGL task; do not mutate LVGL objects from network callbacks.
3. Give prototype and network work an explicit busy/idle lease in `main/pwrmgr.c`. Prevent the custom manual light-sleep path during active transactions and safely release the lease on timeout/cancel. Reconcile that policy with ESP-IDF Wi-Fi power management before enabling wireless operation.
4. Initialize NVS, `esp_netif`, the default event loop, Wi-Fi station mode, bounded reconnect, and saved credentials. Verify UART-based provisioning first. A temporary authenticated SoftAP setup page can follow after radio operation is demonstrated.
5. Send only NPC ID, allowed intent, locale, and bounded game context to a local paired companion. Receive a bounded text response and request ID. Discard stale replies when the player exits. Keep account tokens on the companion and use authored dialogue on timeout or disconnect.
6. Measure free heap, largest allocatable block, framebuffer behavior, reconnect behavior, and battery/power behavior on the real unit. Record observations before calling Wi-Fi support verified.

A command/response or scene-description protocol is preferable to continuously uploading full frames at the existing 115200 baud. The 46,080-byte raw framebuffer alone takes about four seconds at 8N1 wire rate, before framing and overhead. A ROM snapshot or compact scene command is much smaller.

## Rust Versus Existing Firmware

Keep Tuxemon-side generation and asset preparation in Python, matching the fork. A Rust host companion is possible if authentication or networking needs it. Replacing the working MCU application in Rust would also require preserving its C/LVGL bindings, FreeRTOS tasks, QSPI DMA, settings, FPGA UART protocol, and manual sleep policy. A later Rust component through a narrow C ABI is less invasive than a firmware rewrite, but it still adds the Xtensa Rust toolchain and build integration. The C ESP-IDF extension is the shortest hardware proof route. No unbuildable firmware files were added during this research.

## Update and Recovery Boundary

The official MCU README documents `idf.py -p PORT build flash monitor`, with 115200 baud. These are separate operations; build alone is safe to do before selecting a serial port. The FPGA exposes the MCU serial channel through a composite USB device. Opening a monitor or esptool can change serial control lines, so coordinate exclusive device ownership first.

The official FPGA README documents powered-on detection with `openFPGALoader --detect --cable gwu2x`, and persistent flashing with `openFPGALoader --write-flash --cable gwu2x --reset <file>`. It requires a build of openFPGALoader with GWU2X support. Its custom-modification section says changing the reported FPGA version allows MR Updater to restore the official release.

MR Updater has an official Apple Silicon download and is the documented standard restoration/update route. This is documentation evidence, not proof that recovery works after an arbitrary broken MCU image on Sam's unit. Before custom flashing, retain the matching known-good binaries, establish the exact selected device and installed versions, and verify the updater's restore path. Do not replace MCU or FPGA merely to run a native ROM snapshot. A custom image with a broken console, invalid boot layout, or unrecoverable board interaction needs a specifically tested recovery path.

## Sources

- [MCU README and source](https://github.com/ModRetro/oss-chromatic-console-mcu/tree/e03a6baeec49cceda38057d5aed4ae006624c698)
- [MCU framebuffer, QSPI, LVGL, and serial console](https://github.com/ModRetro/oss-chromatic-console-mcu/blob/e03a6baeec49cceda38057d5aed4ae006624c698/main/main.c)
- [MCU power management](https://github.com/ModRetro/oss-chromatic-console-mcu/blob/e03a6baeec49cceda38057d5aed4ae006624c698/main/pwrmgr.c)
- [MCU button event implementation](https://github.com/ModRetro/oss-chromatic-console-mcu/blob/e03a6baeec49cceda38057d5aed4ae006624c698/components/button/button.c)
- [FPGA source and flashing instructions](https://github.com/ModRetro/oss-chromatic-console-fpga/tree/8b4c965dc3a57fd4412836c136b5228a63c72803)
- [Official MR Updater](https://support.modretro.com/en_us/chromatic-firmware-updater-ryhoYnzCx)
